"""Week 8 epoch runner. Proposed protocols allow pilot, never a long grid."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))

import numpy as np
import torch
from nopeek import nopeek_loss
from nopeek_data import load_train_val
from train_mitdb_baseline import classification_metrics, set_determinism
from week3_common import CHECKPOINT, load_model, need, read_json, sha
from week3_sv2_common import wrappers

SOURCES = ("ml/scripts/run_week8_nopeek.py", "ml/scripts/summarize_week8_nopeek.py", "ml/scripts/test_week8_nopeek.py",
           "ml/src/distance_correlation.py", "ml/src/nopeek.py", "ml/src/nopeek_data.py",
           "ml/src/train_mitdb_baseline.py", "ml/src/mitdb_week2_data.py",
           "ml/src/mitdb_baseline_model.py", "ml/src/mitdb_common.py", "ml/src/week1_common.py",
           "ml/scripts/week3_common.py", "ml/scripts/week3_sv2_common.py")
CLASSES = {"N": 0, "S": 1, "V": 2, "F": 3, "Q": 4}


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    payload = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload.encode("utf-8"))
    temporary.replace(path)


def atomic_torch(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(value, temporary)
    temporary.replace(path)


def state_digest(model):
    digest = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def config_digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_config(c, mode):
    need(c["schema_version"] == 1 and c["initial_checkpoint_sha256"] == CHECKPOINT, "Invalid protocol/checkpoint")
    need(c["splits"] == [2, 5, 8] and c["lambda1"] == [0, 0.1, 0.5, 1, 2, 5], "Full 18-combination grid required")
    need(c["seeds"] and len(c["seeds"]) == len(set(c["seeds"])) and
         all(type(s) is int and 0 <= s < 2**32 for s in c["seeds"]), "Invalid seeds")
    need(c["objective"] == "CE + lambda1 * biased_sample_distance_correlation_Rn", "Unsupported objective")
    need(type(c["batch_size"]) is int and c["batch_size"] >= 3, "Batch must be >=3")
    need(c["device"] in ("cpu", "cuda") and type(c["threads"]) is int and c["threads"] > 0
         and type(c["mkldnn"]) is bool, "Invalid compute policy")
    need(c["train_scope"] in ("head_only", "head_and_tail") and c["tail_mode"] == "eval_when_frozen", "Unsupported train scope")
    need(c["class_weighting"] == "none" and c["sampler"] == "shuffle_train_only" and
         c["augmentation"] == "none" and c["scheduler"] == "none", "Unsupported intervention")
    opt = c["optimizer"]
    need(opt["name"] == "Adam" and np.isfinite(opt["lr"]) and opt["lr"] > 0 and
         opt["betas"] == [0.9, 0.999] and opt["eps"] == 1e-8 and opt["weight_decay"] == 0, "Unsupported optimizer")
    p = c["training_policy"]
    need(all(type(p[k]) is int and p[k] > 0 for k in ("max_epochs", "early_stopping_patience")) and
         p["select_by"] == "validation_ce" and p["min_delta"] == 0 and
         p["ties"] == "earliest_epoch" and p["drop_last_train"] is True, "Unsupported selection policy")
    need(c["validation_policy"] == {"order": "frozen_row_order", "drop_last": False,
         "singleton_dcor": "exclude_from_dcor_only", "dcor_aggregation": "sample_weighted_batch_Rn"}, "Unsupported validation policy")
    need(mode in ("pilot", "grid"), "Invalid mode")
    if mode == "grid":
        a = c["approval"]
        need(a["status"] == "APPROVED" and bool(a["authority"]) and bool(a["evidence"]),
             "Long grid requires recorded protocol approval; pilot remains available")
    else:
        p = c["pilot"]
        need(p["splits"] == [2, 5, 8] and p["lambda1"] == [0, 0.5] and p["seeds"] == [c["seeds"][0]], "Pilot scope differs")
        need(all(type(p[k]) is int and p[k] > 0 for k in
                 ("train_samples", "validation_samples", "max_epochs", "patience")) and
             p["train_samples"] >= c["batch_size"] and p["validation_samples"] >= c["batch_size"] and
             p["max_epochs"] <= 3, "Invalid bounded pilot")


def configure_model(baseline, split, scope, device):
    model = copy.deepcopy(baseline).eval().to(device)
    head, tail = wrappers(model, split)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in (head.parameters() if scope == "head_only" else model.parameters()):
        parameter.requires_grad_(True)
    return model, head, tail


def set_mode(model, head, tail, training, scope):
    model.train(training)
    head.train(training)
    tail.train(training and scope == "head_and_tail")


def epoch_metrics(model, head, tail, data, order, config, lambda1, optimizer=None):
    training = optimizer is not None
    set_mode(model, head, tail, training, config["train_scope"])
    before = state_digest(model) if not training else None
    truth, predicted = [], []
    totals = {"ce": 0., "dcor": 0., "total": 0.}
    samples = dcor_samples = batches = 0
    device = next(model.parameters()).device
    batch_size = config["batch_size"]
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for start in range(0, len(order), batch_size):
            index = order[start:start+batch_size]
            if training and len(index) < batch_size:
                continue
            x, y = (torch.from_numpy(a[index].copy()).to(device) for a in data)
            if training:
                optimizer.zero_grad(set_to_none=True)
            z = head(x)
            logits = tail(z)
            if len(index) >= 2:
                loss, parts = nopeek_loss(logits, y, x, z, lambda1)
                totals["dcor"] += float(parts["dcor"].detach()) * len(index)
                dcor_samples += len(index)
            else:
                need(not training, "Singleton training batch")
                loss = torch.nn.functional.cross_entropy(logits, y)
                parts = {"ce": loss, "total": loss}
            need(all(bool(torch.isfinite(v)) for v in parts.values()), "Nonfinite loss")
            need(bool(torch.isfinite(logits).all()), "Nonfinite logits")
            if training:
                loss.backward()
                gradients = [p.grad for p in model.parameters() if p.requires_grad]
                need(all(g is not None and bool(torch.isfinite(g).all()) for g in gradients), "Missing/nonfinite gradient")
                optimizer.step()
                need(all(bool(torch.isfinite(p).all()) for p in model.parameters()), "Nonfinite parameter")
            for key in ("ce", "total"):
                totals[key] += float(parts[key].detach()) * len(index)
            truth.append(y.cpu().numpy())
            predicted.append(logits.detach().argmax(1).cpu().numpy())
            samples += len(index)
            batches += 1
    need(samples > 0 and dcor_samples > 0, "Empty metrics")
    if not training:
        need(state_digest(model) == before, "Validation modified model state")
    metrics = classification_metrics(np.concatenate(truth), np.concatenate(predicted), CLASSES)
    metrics.update(ce=totals["ce"]/samples, dcor=totals["dcor"]/dcor_samples,
                   total=totals["total"]/samples, samples=samples, dcor_samples=dcor_samples,
                   batches=batches, batch_size=batch_size, dropped_samples=len(order)-samples)
    return metrics


def selection(best, current):
    """Strict CE decrease; equality keeps earliest checkpoint."""
    return best is None or current["ce"] < best["ce"]


def run_one(baseline, arrays, config, split, lambda1, seed, output, artifacts, identity,
            max_epochs, patience, resume=False):
    set_determinism(seed, config["threads"])
    model, head, tail = configure_model(baseline, split, config["train_scope"], config["device"])
    initial_digest = state_digest(model)
    optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad],
                                lr=config["optimizer"]["lr"], betas=tuple(config["optimizer"]["betas"]),
                                eps=config["optimizer"]["eps"], weight_decay=config["optimizer"]["weight_decay"])
    history, best, best_epoch, bad_epochs, first_epoch = [], None, None, 0, 1
    run_id = f"s{split}-lambda{lambda1:g}-seed{seed}"
    expected = {"experiment_identity": identity, "split": split, "lambda1": lambda1, "seed": seed,
                "initial_state_sha256": initial_digest, "initial_checkpoint_sha256": CHECKPOINT}
    if resume:
        status = read_json(output / "status.json")
        need(status["identity"] == expected, "Run identity changed")
        if status["status"] == "COMPLETED":
            summary = read_json(output / "summary.json")
            need(summary["identity"] == expected and summary["status"] == "COMPLETED" and summary["run_id"] == run_id,
                 "Completed summary identity changed")
            need(summary["best_checkpoint"] == f"best-epoch-{summary['best_epoch']:03d}.pt", "Invalid checkpoint path")
            need(sha(artifacts / summary["best_checkpoint"]) == summary["checkpoint_sha256"], "Completed checkpoint changed")
            stored = torch.load(artifacts / summary["best_checkpoint"], map_location="cpu", weights_only=True)
            need(stored["identity"] == expected and stored["best"] == summary["validation"] and
                 stored["best_epoch"] == summary["best_epoch"], "Completed checkpoint binding changed")
            return summary
        need(status["status"] in ("FAILED", "INTERRUPTED", "RUNNING"), "Unsupported resume status")
        last = artifacts / "last.pt"
        if last.exists():
            state = torch.load(last, map_location=config["device"], weights_only=True)
            need(state["identity"] == expected, "Resume checkpoint identity changed")
            model.load_state_dict(state["state_dict"], strict=True)
            optimizer.load_state_dict(state["optimizer"])
            history, best, best_epoch, bad_epochs = (state[k] for k in ("history", "best", "best_epoch", "bad_epochs"))
            first_epoch = state["epoch"] + 1
            torch.set_rng_state(state["torch_rng"].cpu())
            if config["device"] == "cuda":
                torch.cuda.set_rng_state_all([v.cpu() for v in state["cuda_rng"]])
    else:
        output.mkdir(parents=True, exist_ok=False)
        artifacts.mkdir(parents=True, exist_ok=False)
    status = {"status": "RUNNING", "run_id": run_id, "identity": expected, "updated_at": now()}
    atomic_json(output / "status.json", status)
    try:
        for epoch in range(first_epoch, max_epochs+1):
            if bad_epochs >= patience:
                break
            started = time.monotonic()
            order = np.random.default_rng(np.random.SeedSequence([seed, epoch])).permutation(len(arrays["train"][0]))
            train = epoch_metrics(model, head, tail, arrays["train"], order, config, lambda1, optimizer)
            val = epoch_metrics(model, head, tail, arrays["val"], np.arange(len(arrays["val"][0])), config, lambda1)
            chosen = selection(best, val)
            if chosen:
                best, best_epoch, bad_epochs = val, epoch, 0
            else:
                bad_epochs += 1
            history.append({"epoch": epoch, "train": train, "validation": val,
                            "selected": chosen, "seconds": time.monotonic()-started})
            checkpoint = {"state_dict": model.state_dict(), "optimizer": optimizer.state_dict(), "epoch": epoch,
                          "identity": expected, "history": history, "best": best, "best_epoch": best_epoch,
                          "bad_epochs": bad_epochs, "torch_rng": torch.get_rng_state(),
                          "cuda_rng": torch.cuda.get_rng_state_all() if config["device"] == "cuda" else [],
                          "deployment_status": "EXPERIMENT_ONLY_NOT_APPROVED"}
            # Epoch filenames are immutable. A resume after a partial write must not erase evidence.
            if chosen:
                target = artifacts / f"best-epoch-{epoch:03d}.pt"
                need(not target.exists(), "Orphan best checkpoint exists; preserve it and use a fresh experiment")
                atomic_torch(target, checkpoint)
            atomic_torch(artifacts / "last.pt", checkpoint)
            atomic_json(output / "history.json", history)
            status.update(last_epoch=epoch, best_epoch=best_epoch, updated_at=now())
            atomic_json(output / "status.json", status)
            print(f"{run_id} epoch={epoch} val_ce={val['ce']:.6f} accuracy={val['accuracy']:.6f}", flush=True)
        need(best_epoch is not None, "No selected checkpoint")
        best_path = artifacts / f"best-epoch-{best_epoch:03d}.pt"
        selected = torch.load(best_path, map_location=config["device"], weights_only=True)
        need(selected["identity"] == expected and selected["best_epoch"] == best_epoch, "Best checkpoint binding mismatch")
        model.load_state_dict(selected["state_dict"], strict=True)
        reproduced = epoch_metrics(model, head, tail, arrays["val"], np.arange(len(arrays["val"][0])), config, lambda1)
        need(reproduced == best, "Reloaded checkpoint validation differs")
        summary = {"run_id": run_id, "split": split, "lambda1": lambda1, "seed": seed,
                   "status": "COMPLETED", "identity": expected, "best_epoch": best_epoch,
                   "epochs_completed": len(history), "stop_reason": "patience" if bad_epochs >= patience else "max_epochs",
                   "validation": best, "best_checkpoint": best_path.name, "checkpoint_sha256": sha(best_path),
                   "reload_validation_exact": True, "final_state_sha256": state_digest(model),
                   "deployment_status": "EXPERIMENT_ONLY_NOT_APPROVED"}
        atomic_json(output / "summary.json", summary)
        status.update(status="COMPLETED", updated_at=now())
        atomic_json(output / "status.json", status)
        return summary
    except BaseException as exc:
        status.update(status="INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAILED",
                      error_type=type(exc).__name__, updated_at=now())
        # Raw exception messages may contain personal absolute paths. Keep the type; CLI prints the traceback.
        atomic_json(output / "status.json", status)
        raise


def source_identity(config):
    return {"git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_sha256": {p: sha(ROOT / p) for p in SOURCES}, "config_sha256": config_digest(config)}


def validate_inventory(inventory, policy):
    expected = {f"s{s}-lambda{l:g}-seed{k}": (s, l, k)
                for k in policy["seeds"] for s in policy["splits"] for l in policy["lambda1"]}
    need(len(inventory) == len(expected) and len({r["run_id"] for r in inventory}) == len(expected),
         "Missing/duplicate inventory combinations")
    for row in inventory:
        need(row["run_id"] in expected and (row["split"], row["lambda1"], row["seed"]) == expected[row["run_id"]],
             "Inventory combination changed")
        need(row["status"] in ("NOT_STARTED", "RUNNING", "COMPLETED", "FAILED", "INTERRUPTED"), "Invalid run status")


def environment(config):
    return {"python": platform.python_version(), "platform": platform.system(), "torch": str(torch.__version__),
            "numpy": np.__version__, "cuda_build": torch.version.cuda, "device": config["device"],
            "device_name": torch.cuda.get_device_name(0) if config["device"] == "cuda" else platform.processor(),
            "threads": config["threads"], "mkldnn": config["mkldnn"],
            "deterministic_algorithms": True, "tf32": False, "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"]}


def _run(config_path, output, artifacts, mode="pilot", resume=False):
    config = read_json(config_path)
    validate_config(config, mode)
    output, artifacts = Path(output).resolve(), Path(artifacts).resolve()
    need((ROOT / "ml/results/week8-nopeek" / mode).resolve() in output.parents and
         (ROOT / "ml/artifacts/week8-nopeek" / mode).resolve() in artifacts.parents,
         "Outputs must be fresh children of separate Week8 pilot/grid roots")
    need(output != artifacts, "Distinct output and artifact roots required")
    if not resume:
        need(not output.exists() and not artifacts.exists(), "Refuse to overwrite experiment")
    else:
        need(output.is_dir() and artifacts.is_dir(), "Resume requires existing experiment")
    need(config["device"] != "cuda" or torch.cuda.is_available(), "CUDA unavailable")
    set_determinism(config["seeds"][0], config["threads"])
    torch.backends.mkldnn.enabled = config["mkldnn"]
    torch.backends.cudnn.allow_tf32 = False
    baseline, checkpoint = load_model(ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt", ROOT / "ml/src/mitdb_baseline_model.py")
    data_config, identifiers, arrays, metadata = load_train_val(checkpoint)
    identity = source_identity(config)
    identity.update(mode=mode, dataset=identifiers, environment=environment(config))
    indices = {s: np.arange(len(arrays[s][0])) for s in ("train", "val")}
    if mode == "pilot":
        for i, s in enumerate(("train", "val")):
            n = config["pilot"]["train_samples" if s == "train" else "validation_samples"]
            need(n <= len(indices[s]), "Pilot subset too large")
            indices[s] = np.sort(np.random.default_rng(config["seeds"][0]+i).choice(indices[s], n, replace=False))
    selected = {s: (arrays[s][0][idx].copy(), arrays[s][1][idx].copy()) for s, idx in indices.items()}
    samples = {s: [{"row_index": int(i), "sample_id": metadata[s].iloc[i].sample_id,
                    "patient_id": str(metadata[s].iloc[i].patient_id), "class_index": int(arrays[s][1][i])}
                   for i in idx] for s, idx in indices.items()}
    data = {"bindings": identifiers, "classes": CLASSES, "normalization_fit": "train", "test_arrays_opened": False,
            "splits": {s: {"samples": len(arrays[s][0]), "patients": sorted(metadata[s].patient_id.unique().tolist()),
                           "records": sorted(metadata[s].record_id.unique().tolist()),
                           "class_counts": np.bincount(arrays[s][1], minlength=5).tolist()} for s in ("train", "val")}}
    identity["selected_samples_sha256"] = config_digest(samples)
    if resume:
        need(read_json(output / "identity.json") == identity, "Source/config/data/environment changed; resume refused")
        need(read_json(output / "selected_samples.json") == samples, "Selected samples changed")
    else:
        output.mkdir(parents=True, exist_ok=False)
        artifacts.mkdir(parents=True, exist_ok=False)
        atomic_json(output / "identity.json", identity)
        atomic_json(output / "config.json", config)
        atomic_json(output / "data-audit.json", data)
        atomic_json(output / "selected_samples.json", samples)
        for relative in SOURCES:
            target = output / "sources" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
    policy = config["pilot"] if mode == "pilot" else config
    inventory = [{"run_id": f"s{s}-lambda{l:g}-seed{k}", "split": s, "lambda1": l, "seed": k, "status": "NOT_STARTED"}
                 for k in policy["seeds"] for s in policy["splits"] for l in policy["lambda1"]]
    if resume:
        inventory = read_json(output / "inventory.json")
    validate_inventory(inventory, policy)
    atomic_json(output / "inventory.json", inventory)
    experiment_status = {"status": "RUNNING", "mode": mode, "expected_runs": len(inventory), "updated_at": now()}
    atomic_json(output / "status.json", experiment_status)
    try:
        for row in inventory:
            relative = row["run_id"]
            out, art = output / relative, artifacts / relative
            row["status"] = "RUNNING"
            atomic_json(output / "inventory.json", inventory)
            summary = run_one(baseline, selected, config, row["split"], row["lambda1"], row["seed"], out, art,
                              identity, policy["max_epochs"] if mode == "pilot" else config["training_policy"]["max_epochs"],
                              policy["patience"] if mode == "pilot" else config["training_policy"]["early_stopping_patience"],
                              resume=resume and out.exists())
            row.update(status="COMPLETED", best_epoch=summary["best_epoch"], checkpoint_sha256=summary["checkpoint_sha256"])
            atomic_json(output / "inventory.json", inventory)
        experiment_status.update(status="COMPLETED", completed_runs=len(inventory), updated_at=now())
    except BaseException as exc:
        row["status"] = "INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAILED"
        atomic_json(output / "inventory.json", inventory)
        experiment_status.update(status=row["status"], error_type=type(exc).__name__, updated_at=now())
        raise
    finally:
        atomic_json(output / "status.json", experiment_status)
    return inventory


def run(config_path, output, artifacts, mode="pilot", resume=False):
    # Exclusive sibling lock protects both result and checkpoint roots, including --resume.
    # A killed process leaves its lock as evidence; inspect the process before removing it manually.
    config = read_json(config_path)
    validate_config(config, mode)
    output, artifacts = Path(output).resolve(), Path(artifacts).resolve()
    need((ROOT / "ml/results/week8-nopeek" / mode).resolve() in output.parents and
         (ROOT / "ml/artifacts/week8-nopeek" / mode).resolve() in artifacts.parents,
         "Outputs must be fresh children of separate Week8 pilot/grid roots")
    output.parent.mkdir(parents=True, exist_ok=True)
    artifacts.parent.mkdir(parents=True, exist_ok=True)
    locks = []
    try:
        for target in (output, artifacts):
            lock = target.with_name(target.name + ".lock")
            with lock.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "created_at": now()}) + "\n")
            locks.append(lock)
        return _run(config_path, output, artifacts, mode, resume)
    finally:
        for lock in locks:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "ml/configs/week8_nopeek_protocol_v1.json")
    parser.add_argument("--mode", choices=("pilot", "grid"), default="pilot")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.config, args.output, args.artifacts, args.mode, args.resume)


if __name__ == "__main__":
    main()
