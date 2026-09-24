"""Train one Week 2 MIT-BIH candidate and evaluate the held-out test once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
from datetime import datetime, timezone

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from mitdb_baseline_model import MitdbBaselineCNN, architecture_metadata
from mitdb_week2_data import SPLITS, load_week1_splits
from week1_common import ML_ROOT, load_config, ml_path, require

SCIENTIFIC_SOURCE_FILES = (
    "ml/configs/mitdb_week2_baseline.json",
    "ml/src/mitdb_baseline_model.py",
    "ml/src/mitdb_week2_data.py",
    "ml/src/train_mitdb_baseline.py",
    "ml/src/week1_common.py",
    "ml/src/mitdb_common.py",
)


def save_json(path, value: dict | list) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_clean_scientific_sources() -> None:
    """Shared train/verify gate; unrelated dirty files do not affect it."""
    repo = ML_ROOT.parent
    for relative in SCIENTIFIC_SOURCE_FILES:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                                 cwd=repo, capture_output=True, check=False)
        require(tracked.returncode == 0, f"Scientific source is not tracked: {relative}")
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", relative],
                               cwd=repo, check=False)
        require(clean.returncode == 0, f"Scientific source/config differs from HEAD: {relative}")


def scientific_source_provenance(config_path) -> dict:
    """Bind a run to committed, unchanged executable source and config."""
    repo = ML_ROOT.parent
    require_clean_scientific_sources()
    require(config_path.resolve() == (repo / SCIENTIFIC_SOURCE_FILES[0]).resolve(),
            "Training must use the tracked Week 2 config")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip())
    return {"source_git_sha": commit,
            "source_files_sha256": {relative: sha256(repo / relative) for relative in SCIENTIFIC_SOURCE_FILES},
            "scientific_sources_clean": True, "worktree_dirty": dirty}


def write_run_manifest(output, results: dict) -> None:
    """Keep small Week 2 evidence under the existing provenance directory."""
    names = ("training_config.json", "architecture.json", "history.json", "metrics.json",
             "best_state_dict.pt", "best_checkpoint.pt")
    artifacts = {}
    for name in names:
        path = output / name
        artifacts[path.relative_to(ML_ROOT.parent).as_posix()] = {
            "sha256": sha256(path), "bytes": path.stat().st_size}
    manifest = {"schema_version": 1, "week": 2, "candidate": results["candidate"],
                "source_git_sha": results["provenance"]["source_git_sha"],
                "source_files_sha256": results["provenance"]["source_files_sha256"],
                "scientific_sources_clean": results["provenance"]["scientific_sources_clean"],
                "worktree_dirty": results["provenance"]["worktree_dirty"],
                "config_sha256": results["provenance"]["config_sha256"],
                "dataset_artifacts": results["provenance"]["dataset_artifacts"],
                "best_epoch": results["best_epoch"],
                "validation_accuracy": results["validation"]["accuracy"],
                "test_accuracy": results["test"]["accuracy"],
                "artifacts": artifacts}
    provenance_dir = ML_ROOT / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)
    save_json(provenance_dir / "week2_run_manifest.json", manifest)


def set_determinism(seed: int, threads: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.use_deterministic_algorithms(True)


def classification_metrics(truth: np.ndarray, predicted: np.ndarray, classes: dict) -> dict:
    count = len(classes)
    matrix = np.bincount(truth * count + predicted, minlength=count * count).reshape(count, count)
    support = matrix.sum(axis=1)
    predicted_count = matrix.sum(axis=0)
    tp = matrix.diagonal()
    precision = np.divide(tp, predicted_count, out=np.zeros(count, dtype=float), where=predicted_count != 0)
    recall = np.divide(tp, support, out=np.zeros(count, dtype=float), where=support != 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(count, dtype=float), where=(precision + recall) != 0)
    names = [name for name, _ in sorted(classes.items(), key=lambda item: item[1])]
    return {"accuracy": float(tp.sum() / len(truth)), "macro_f1": float(f1.mean()),
            "weighted_f1": float(np.dot(f1, support) / len(truth)),
            "confusion_matrix": matrix.tolist(),
            "per_class": {name: {"support": int(support[i]), "precision": float(precision[i]),
                                 "recall": float(recall[i]), "f1": float(f1[i])}
                          for i, name in enumerate(names)}}


def evaluate(model: nn.Module, loader: DataLoader, loss_fn: nn.Module,
             device: torch.device, classes: dict) -> dict:
    """Pure evaluation: eval mode, no gradients or optimizer access."""
    model.eval()
    total_loss = 0.0
    truth, predicted = [], []
    with torch.inference_mode():
        for signals, labels in loader:
            signals, labels = signals.to(device, non_blocking=True), labels.to(device, non_blocking=True)
            logits = model(signals)
            total_loss += loss_fn(logits, labels).item() * len(labels)
            truth.append(labels.cpu().numpy())
            predicted.append(logits.argmax(dim=1).cpu().numpy())
    metrics = classification_metrics(np.concatenate(truth), np.concatenate(predicted), classes)
    metrics["loss"] = total_loss / len(loader.dataset)
    return metrics


def train_epoch(model: nn.Module, loader: DataLoader, optimizer: torch.optim.Optimizer,
                loss_fn: nn.Module, device: torch.device) -> dict:
    model.train()
    total_loss = correct = total = 0
    for signals, labels in loader:
        signals, labels = signals.to(device, non_blocking=True), labels.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        logits = model(signals)
        loss = loss_fn(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(labels)
        correct += int((logits.argmax(dim=1) == labels).sum().item())
        total += len(labels)
    return {"loss": total_loss / total, "accuracy": correct / total}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mitdb_week2_baseline.json")
    args = parser.parse_args()
    config_path, settings = load_config(args.config)
    source = scientific_source_provenance(config_path)
    require(not (ML_ROOT / "provenance" / "week2_run_manifest.json").exists(),
            "Refusing to overwrite existing Week 2 evidence; use a separate run checkout")
    week1, identifiers, arrays = load_week1_splits(settings["week1_config"])
    require(settings["seed"] == week1["split"]["seed"], "Week 2 seed differs from Week 1 project seed")
    require(settings["class_weighting"] == "none" and settings["augmentation"] == "none"
            and settings["sampler"] == "shuffle_train_only", "Unsupported training intervention")
    require(settings["selection_metric"] == "validation_accuracy", "Unsupported selection metric")
    require(settings["optimizer"] == "AdamW" and settings["loss"] == "CrossEntropyLoss",
            "Unsupported optimizer or loss")
    require(settings["scheduler"]["name"] == "ReduceLROnPlateau", "Unsupported scheduler")
    require(settings["batch_size"] > 0 and settings["epochs"] > 0 and
            settings["early_stopping_patience"] > 0, "Invalid training duration or batch size")
    set_determinism(settings["seed"], settings["torch_threads"])
    use_cuda = torch.cuda.is_available() and settings["device"] in ("auto", "cuda")
    require(settings["device"] in ("auto", "cpu", "cuda"), "Invalid device setting")
    require(settings["device"] != "cuda" or use_cuda, "CUDA requested but unavailable")
    device = torch.device("cuda" if use_cuda else "cpu")
    output = ml_path(settings["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    model = MitdbBaselineCNN(settings["dropout"]).to(device)
    architecture = architecture_metadata(model, settings["candidate_name"])
    require(8 <= architecture["layer_count"] <= 12 and
            architecture["trainable_parameters"] < 250_000 and
            architecture["fp32_parameter_bytes"] < 1_000_000,
            "Candidate exceeds Week 2 architecture/footprint limits")
    save_json(output / "training_config.json", settings)
    save_json(output / "architecture.json", architecture)
    pin = device.type == "cuda"
    datasets = {split: TensorDataset(torch.from_numpy(arrays[split][0]).unsqueeze(1),
                                     torch.from_numpy(arrays[split][1])) for split in SPLITS}
    train_loader = DataLoader(datasets["train"], batch_size=settings["batch_size"], shuffle=True,
                              generator=torch.Generator().manual_seed(settings["seed"]),
                              num_workers=0, pin_memory=pin)
    val_loader = DataLoader(datasets["val"], batch_size=settings["batch_size"],
                            shuffle=False, num_workers=0, pin_memory=pin)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                                  weight_decay=settings["weight_decay"])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=settings["scheduler"]["factor"],
        patience=settings["scheduler"]["patience"])
    loss_fn = nn.CrossEntropyLoss()
    config_digest = sha256(config_path)
    provenance = {"seed": settings["seed"], **source,
                  "config_path": config_path.relative_to(ML_ROOT).as_posix(),
                  "config_sha256": config_digest, "dataset_artifacts": identifiers,
                  "started_utc": datetime.now(timezone.utc).isoformat(),
                  "device": str(device),
                  "device_name": torch.cuda.get_device_name(device) if use_cuda else platform.processor(),
                  "python_version": platform.python_version(),
                  "torch_version": str(torch.__version__), "cuda_version": torch.version.cuda}
    history = []
    best_accuracy, best_epoch, stale = -1.0, 0, 0
    checkpoint_path = output / "best_checkpoint.pt"
    state_path = output / "best_state_dict.pt"
    print(f"Week 2 candidate on {device}; {architecture['trainable_parameters']} trainable parameters", flush=True)
    for epoch in range(1, settings["epochs"] + 1):
        train = train_epoch(model, train_loader, optimizer, loss_fn, device)
        validation = evaluate(model, val_loader, loss_fn, device, week1["classes"])
        learning_rate = optimizer.param_groups[0]["lr"]
        history.append({"epoch": epoch, "learning_rate": learning_rate,
                        "train": train, "validation": validation})
        if validation["accuracy"] > best_accuracy:
            best_accuracy, best_epoch, stale = validation["accuracy"], epoch, 0
            state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
            torch.save(state, state_path)
            torch.save({"state_dict": state, "epoch": epoch, "validation": validation,
                        "provenance": provenance, "training_config": settings,
                        "architecture": architecture}, checkpoint_path)
        else:
            stale += 1
        save_json(output / "history.json", history)
        print(f"epoch={epoch} train_loss={train['loss']:.5f} train_acc={train['accuracy']:.5f} "
              f"val_loss={validation['loss']:.5f} val_acc={validation['accuracy']:.5f} "
              f"best_epoch={best_epoch} lr={learning_rate:.6g}", flush=True)
        scheduler.step(validation["accuracy"])
        if stale >= settings["early_stopping_patience"]:
            break
    selected = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model.load_state_dict(selected["state_dict"])
    model.to(device)
    test_loader = DataLoader(datasets["test"], batch_size=settings["batch_size"],
                             shuffle=False, num_workers=0, pin_memory=pin)
    test = evaluate(model, test_loader, loss_fn, device, week1["classes"])
    results = {"candidate": settings["candidate_name"], "best_epoch": best_epoch,
               "selection_metric": settings["selection_metric"], "test_evaluated_after_selection": True,
               "train_at_best_epoch": history[best_epoch - 1]["train"],
               "validation": selected["validation"], "test": test,
               "architecture": architecture, "provenance": provenance,
               "state_dict_file_bytes": state_path.stat().st_size,
               "checkpoint_file_bytes": checkpoint_path.stat().st_size,
               "state_dict_sha256": sha256(state_path), "checkpoint_sha256": sha256(checkpoint_path)}
    save_json(output / "metrics.json", results)
    write_run_manifest(output, results)
    print(f"best_epoch={best_epoch} val_accuracy={best_accuracy:.6f} test_accuracy={test['accuracy']:.6f}")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
