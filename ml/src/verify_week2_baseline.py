"""Read-only post-run verification of the selected Week 2 ECG baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from mitdb_baseline_model import MitdbBaselineCNN, architecture_metadata
from mitdb_week2_data import load_week1_splits
from train_mitdb_baseline import SCIENTIFIC_SOURCE_FILES, evaluate, set_determinism, sha256
from week1_common import ML_ROOT, load_config, ml_path, require, run_cli


ARTIFACT_NAMES = ("training_config.json", "architecture.json", "history.json",
                  "metrics.json", "best_state_dict.pt", "best_checkpoint.pt")


def same_metrics(actual: dict, recorded: dict, label: str) -> None:
    require(actual["confusion_matrix"] == recorded["confusion_matrix"],
            f"{label}: confusion matrix changed")
    for key in ("accuracy", "macro_f1", "weighted_f1", "loss"):
        require(math.isclose(actual[key], recorded[key], rel_tol=0, abs_tol=1e-4 if key == "loss" else 1e-12),
                f"{label}: {key} changed")
    require(actual["per_class"] == recorded["per_class"], f"{label}: per-class metrics changed")


def verify() -> dict:
    repo = ML_ROOT.parent
    config_path, settings = load_config("mitdb_week2_baseline.json")
    output = ml_path(settings["output_dir"])
    manifest_path = ML_ROOT / "provenance" / "week2_run_manifest.json"
    require(manifest_path.is_file(), f"Missing Week 2 run manifest: {manifest_path}")
    run = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_paths = {(output / name).relative_to(repo).as_posix() for name in ARTIFACT_NAMES}
    require(set(run["artifacts"]) == expected_paths, "Run manifest artifact set differs from config")
    for relative, entry in run["artifacts"].items():
        path = repo / relative
        require(path.is_file(), f"Missing Week 2 artifact: {relative}")
        require(path.stat().st_size == entry["bytes"] and sha256(path) == entry["sha256"],
                f"Week 2 artifact size/hash mismatch: {relative}")
    saved_config = json.loads((output / "training_config.json").read_text(encoding="utf-8"))
    saved_architecture = json.loads((output / "architecture.json").read_text(encoding="utf-8"))
    history = json.loads((output / "history.json").read_text(encoding="utf-8"))
    results = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    checkpoint = torch.load(output / "best_checkpoint.pt", map_location="cpu", weights_only=True)
    state = torch.load(output / "best_state_dict.pt", map_location="cpu", weights_only=True)
    require(saved_config == settings == checkpoint["training_config"], "Training config mismatch")
    require(results["candidate"] == settings["candidate_name"] == run["candidate"],
            "Candidate identifier mismatch")
    model = MitdbBaselineCNN(settings["dropout"]).eval()
    live_architecture = architecture_metadata(model, settings["candidate_name"])
    require(saved_architecture == live_architecture == results["architecture"] == checkpoint["architecture"],
            "Architecture metadata differs from live model")
    require(8 <= live_architecture["layer_count"] <= 12 and
            live_architecture["trainable_parameters"] < 250_000 and
            live_architecture["fp32_parameter_bytes"] < 1_000_000,
            "Architecture exceeds Week 2 limits")
    require(set(state) == set(checkpoint["state_dict"]) and
            all(torch.equal(state[key], checkpoint["state_dict"][key]) for key in state),
            "Checkpoint and state dict weights differ")
    model.load_state_dict(checkpoint["state_dict"])
    second = MitdbBaselineCNN(settings["dropout"]).eval()
    second.load_state_dict(state)

    source = results["provenance"]
    require(source == checkpoint["provenance"], "Checkpoint provenance differs from metrics")
    require(source["scientific_sources_clean"] is True and
            run["scientific_sources_clean"] is True, "Scientific sources were not clean at run time")
    require(source["source_git_sha"] == run["source_git_sha"], "Source commit mismatch")
    require(source["source_files_sha256"] == run["source_files_sha256"], "Source hashes differ")
    require(set(source["source_files_sha256"]) == set(SCIENTIFIC_SOURCE_FILES),
            "Incomplete scientific source hashes")
    require(source["config_sha256"] == run["config_sha256"] == sha256(config_path),
            "Week 2 config hash mismatch")
    for relative, digest in source["source_files_sha256"].items():
        require(sha256(repo / relative) == digest, f"Current scientific source changed: {relative}")
        blob = subprocess.run(["git", "show", f"{source['source_git_sha']}:{relative}"],
                              cwd=repo, capture_output=True, check=False)
        require(blob.returncode == 0, f"Source commit lacks {relative}")
        require(hashlib.sha256(blob.stdout).hexdigest() == digest,
                f"Source commit does not contain run source: {relative}")
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SCIENTIFIC_SOURCE_FILES],
                           cwd=repo, check=False)
    require(clean.returncode == 0, "Scientific source has uncommitted changes")

    week1, identifiers, arrays = load_week1_splits(settings["week1_config"])
    require(source["dataset_artifacts"] == run["dataset_artifacts"] == identifiers,
            "Week 1 dataset hash binding changed")
    require(source["seed"] == week1["split"]["seed"] == settings["seed"], "Seed mismatch")
    require(source["device"] in ("cpu", "cuda"), "Unknown training device in provenance")
    require(source["device"] != "cuda" or torch.cuda.is_available(),
            "Recorded CUDA run requires CUDA for exact prediction verification")
    device = torch.device(source["device"])
    set_determinism(settings["seed"], settings["torch_threads"])
    model.to(device)
    second.to(device)
    require(settings["selection_metric"] == results["selection_metric"] == "validation_accuracy" and
            results["test_evaluated_after_selection"] is True,
            "Validation-only selection contract changed")
    require(bool(history) and all(entry["epoch"] == index for index, entry in enumerate(history, 1)),
            "Epoch history is incomplete or unordered")
    best = max(history, key=lambda entry: entry["validation"]["accuracy"])
    require(best["epoch"] == results["best_epoch"] == checkpoint["epoch"] == run["best_epoch"],
            "Selected epoch was not the first validation-accuracy maximum")
    require(best["validation"] == results["validation"] == checkpoint["validation"],
            "Selected validation metrics differ")
    require(best["train"] == results["train_at_best_epoch"], "Selected train metrics differ")

    before = {name: value.clone() for name, value in model.state_dict().items()}
    loss_fn = nn.CrossEntropyLoss()
    recomputed = {}
    for split in ("val", "test"):
        x, y = arrays[split]
        loader = DataLoader(TensorDataset(torch.from_numpy(x).unsqueeze(1), torch.from_numpy(y)),
                            batch_size=settings["batch_size"], shuffle=False, num_workers=0)
        recomputed[split] = evaluate(model, loader, loss_fn, device, week1["classes"])
        same_metrics(recomputed[split], results["validation" if split == "val" else "test"], split)
    sample = torch.from_numpy(arrays["test"][0][:4]).unsqueeze(1).to(device)
    with torch.inference_mode():
        require(torch.equal(model(sample), second(sample)), "Reloaded checkpoint predictions differ")
    require(all(torch.equal(value, before[name]) for name, value in model.state_dict().items()) and
            all(parameter.grad is None for parameter in model.parameters()),
            "Verification updated model parameters")
    require(math.isclose(run["validation_accuracy"], results["validation"]["accuracy"], abs_tol=1e-12) and
            math.isclose(run["test_accuracy"], results["test"]["accuracy"], abs_tol=1e-12),
            "Run manifest metrics differ")
    require(results["test"]["accuracy"] >= 0.98, "Test accuracy below Week 2 target")
    require(results["state_dict_file_bytes"] == (output / "best_state_dict.pt").stat().st_size and
            results["checkpoint_file_bytes"] == (output / "best_checkpoint.pt").stat().st_size and
            results["state_dict_sha256"] == sha256(output / "best_state_dict.pt") and
            results["checkpoint_sha256"] == sha256(output / "best_checkpoint.pt"),
            "Metrics file checkpoint size/hash mismatch")
    return {"source_git_sha": source["source_git_sha"], "best_epoch": best["epoch"],
            "validation_accuracy": recomputed["val"]["accuracy"],
            "test_accuracy": recomputed["test"]["accuracy"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = verify()
    for key, value in result.items():
        print(f"{key}: {value}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
