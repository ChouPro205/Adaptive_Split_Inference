"""One final FP32 test after validation-only candidate lock; never tune here."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
import numpy as np
import pandas as pd
import torch
from nopeek import nopeek_loss
from mitdb_week2_data import load_week1_splits
from train_mitdb_baseline import classification_metrics, set_determinism
from week1_common import configured_path
from week3_common import load_model, need, read_json, safe_path, sha
from week3_sv2_common import wrappers
from run_week8_nopeek import CLASSES, SOURCES, atomic_json, config_digest, finite_tensors, now, state_digest


def validate_lock(lock):
    need(lock["status"] == "CANDIDATES_LOCKED_VALIDATION_ONLY" and
         lock["expected_runs"] == lock["completed_runs"] == 54, "Complete validation-only candidate lock required")
    need(lock["seeds"] == [20261021, 20261022, 20261023], "Locked seeds differ")
    need(lock["deployment_status"] == "EXPERIMENT_ONLY_NOT_APPROVED" and
         lock["test_status"] == "NOT_READ_BY_CANDIDATE_SELECTION", "Invalid lock scope")
    candidates = lock["candidates"]
    need(len(candidates) == 3 and {c["split"] for c in candidates} == {2, 5, 8}, "Three locked split candidates required")
    for candidate in candidates:
        need(candidate["lambda1"] in (0, .1, .5, 1, 2, 5), "Invalid selected lambda")
        need(len(candidate["seeds"]) == 3 and sorted(s["seed"] for s in candidate["seeds"]) == lock["seeds"],
             "All three seed checkpoints required; do not select the best seed")


def evaluate(model, split, lambda1, arrays, batch_size, device):
    head, tail = wrappers(model.eval(), split)
    need(not any(m.training for m in model.modules()), "Test requires eval mode")
    before = state_digest(model)
    logits_all, ce, dcor, n = [], 0., 0., 0
    x_all, y_all = arrays
    need(len(x_all) == len(y_all) and len(y_all) % batch_size == 0, "Complete test batches required")
    with torch.inference_mode():
        for start in range(0, len(y_all), batch_size):
            x = torch.from_numpy(x_all[start:start+batch_size].copy()).to(device)
            y = torch.from_numpy(y_all[start:start+batch_size].copy()).to(device)
            z = head(x)
            logits = tail(z)
            _, parts = nopeek_loss(logits, y, x, z, lambda1)
            need(finite_tensors([logits, *parts.values()]), "Nonfinite final test output")
            ce += float(parts["ce"]) * len(y)
            dcor += float(parts["dcor"]) * len(y)
            n += len(y)
            logits_all.append(logits.cpu())
    need(state_digest(model) == before, "Final test modified model state")
    logits = torch.cat(logits_all)
    predicted = logits.argmax(1).numpy()
    metrics = classification_metrics(y_all, predicted, CLASSES)
    metrics.update(ce=ce/n, dcor=dcor/n, samples=n, batch_size=batch_size,
                   dcor_samples=n, dcor_aggregation="sample_weighted_batch_Rn",
                   state_sha256=before, mode="eval; inference_mode; no optimizer")
    return metrics, logits


def run(lock_path, output, artifacts):
    lock_path, output, artifacts = (Path(p).resolve() for p in (lock_path, output, artifacts))
    lock = read_json(lock_path)
    validate_lock(lock)  # Must precede every dataset/checkpoint read.
    need(not output.exists() and not artifacts.exists(), "Refuse to overwrite final test evidence")
    need((ROOT / "ml/results/week8-nopeek/final-test").resolve() in output.parents and
         (ROOT / "ml/artifacts/week8-nopeek/final-test").resolve() in artifacts.parents,
         "Final test outputs must use separate fresh roots")
    experiment = safe_path(ROOT, lock["experiment"]["path"])
    identity, config = read_json(experiment / "identity.json"), read_json(experiment / "config.json")
    need(config_digest(config) == identity["config_sha256"] == lock["config"]["sha256"], "Config differs from candidate lock")
    need(sha(experiment / "identity.json") == lock["experiment"]["identity_sha256"] and
         sha(experiment / "inventory.json") == lock["experiment"]["inventory_sha256"], "Grid evidence changed after lock")
    need(read_json(experiment / "status.json")["status"] == "COMPLETED", "Grid must be complete before final test")
    need(identity["dataset"] == lock["data"]["dataset_bindings"], "Locked dataset differs")
    for relative, digest in identity["source_sha256"].items():
        need(sha(safe_path(ROOT, relative)) == digest, "Training runtime changed after lock: " + relative)
    for candidate in lock["candidates"]:
        for seed in candidate["seeds"]:
            need(seed.get("checkpoint_path_base", "repo_root") == "repo_root", "Test requires repo-relative checkpoint paths")
            need(sha(safe_path(ROOT, seed["checkpoint_path"])) == seed["checkpoint_sha256"], "Locked checkpoint hash differs")
    lock_sha = sha(lock_path)
    set_determinism(config["seeds"][0], config["threads"])
    torch.backends.mkldnn.enabled = config["mkldnn"]
    torch.backends.cudnn.allow_tf32 = False
    baseline, checkpoint = load_model(ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt", ROOT / "ml/src/mitdb_baseline_model.py")
    data_config, identifiers, arrays = load_week1_splits()
    need(identifiers == identity["dataset"] == checkpoint["provenance"]["dataset_artifacts"], "Final frozen data binding mismatch")
    x, y = arrays["test"]
    need(x.shape == (8544, 360) and y.shape == (8544,), "Expected frozen 8544-sample test")
    metadata = pd.read_csv(configured_path(data_config, "processed_dir") / "test_metadata.csv",
                           dtype={"record_id": str, "patient_id": str})
    sample_ids = [f"MIT-BIH:{r.record_id}:{r.r_peak_sample}:{r.lead_name}" for r in metadata.itertuples()]
    need(len(sample_ids) == len(set(sample_ids)) == len(y), "Invalid final test IDs")
    output.mkdir(parents=True, exist_ok=False)
    artifacts.mkdir(parents=True, exist_ok=False)
    source_paths = (*SOURCES, "ml/scripts/evaluate_week8_locked_test.py", "ml/src/mitdb_week2_data.py")
    provenance = {"candidate_lock_sha256": lock_sha, "source_sha256": {p: sha(ROOT/p) for p in source_paths},
                  "training_identity": identity, "test_data_bindings": identifiers,
                  "policy": "FINAL_TEST_AFTER_LOCK_NO_RETUNING_NO_DEPLOYMENT_APPROVAL"}
    atomic_json(output / "provenance.json", provenance)
    atomic_json(output / "sample-ids.json", sample_ids)
    status = {"status": "RUNNING", "expected_checkpoints": 9, "completed_checkpoints": 0, "updated_at": now()}
    atomic_json(output / "status.json", status)
    results = []
    try:
        for candidate in lock["candidates"]:
            for seed in candidate["seeds"]:
                path = safe_path(ROOT, seed["checkpoint_path"])
                stored = torch.load(path, map_location="cpu", weights_only=True)
                need(stored["identity"]["experiment_identity"] == identity and
                     stored["identity"]["seed"] == seed["seed"] and
                     stored["identity"]["split"] == candidate["split"] and
                     stored["identity"]["lambda1"] == candidate["lambda1"], "Selected checkpoint identity differs")
                model = copy.deepcopy(baseline).to(config["device"])
                model.load_state_dict(stored["state_dict"], strict=True)
                metrics, logits = evaluate(model, candidate["split"], candidate["lambda1"],
                                           (x[:, None, :], y), config["batch_size"], config["device"])
                raw = artifacts / (seed["run_id"] + "-test-logits.pt")
                torch.save({"logits": logits, "truth": torch.from_numpy(y.copy()), "sample_ids": sample_ids}, raw)
                result = {"split": candidate["split"], "lambda1": candidate["lambda1"], "seed": seed["seed"],
                          "run_id": seed["run_id"], "checkpoint_sha256": seed["checkpoint_sha256"],
                          "test": metrics, "raw_logits_path": raw.relative_to(ROOT).as_posix(), "raw_logits_sha256": sha(raw)}
                results.append(result)
                atomic_json(output / "results.json", results)
                status.update(completed_checkpoints=len(results), updated_at=now())
                atomic_json(output / "status.json", status)
                print(seed["run_id"], "final test accuracy", metrics["accuracy"], flush=True)
        need(sha(lock_path) == lock_sha, "Candidate lock changed during test")
        aggregate = []
        for split in (2, 5, 8):
            subset = [r for r in results if r["split"] == split]
            row = {"split": split, "lambda1": subset[0]["lambda1"], "seeds": 3, "samples_per_seed": len(y)}
            for name in ("accuracy", "ce", "dcor", "macro_f1"):
                values = [r["test"][name] for r in subset]
                row[name+"_mean"] = float(np.mean(values))
                row[name+"_std_sample"] = float(np.std(values, ddof=1))
            aggregate.append(row)
        atomic_json(output / "aggregate.json", aggregate)
        status.update(status="COMPLETED", updated_at=now())
    except BaseException as exc:
        status.update(status="INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAILED",
                      error_type=type(exc).__name__, updated_at=now())
        raise
    finally:
        atomic_json(output / "status.json", status)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    run(args.candidate_lock, args.output, args.artifacts)
