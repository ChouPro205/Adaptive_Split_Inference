"""Short real-data offline NoPeek smoke; never evaluate or select on test."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))

import numpy as np
import torch
from torch.nn import functional as F

from distance_correlation import distance_correlation
from nopeek import nopeek_loss
from nopeek_data import load_train_val
from train_mitdb_baseline import classification_metrics, set_determinism
from week1_common import artifact_sha256
from week3_common import load_model, need, sha, write_json
from week3_sv2_common import wrappers, SHAPES

SOURCES = ("ml/src/distance_correlation.py", "ml/src/nopeek.py", "ml/src/nopeek_data.py",
           "ml/scripts/run_week7_nopeek.py", "ml/scripts/test_week7_nopeek.py",
           "ml/configs/week7_nopeek_smoke.json", "ml/configs/week8_nopeek_sweep.json",
           "ml/src/mitdb_baseline_model.py", "ml/src/train_mitdb_baseline.py",
           "ml/src/week1_common.py", "ml/src/mitdb_common.py",
           "ml/scripts/week3_common.py", "ml/scripts/week3_sv2_common.py")


def state_digest(model):
    digest = hashlib.sha256()
    for key, value in model.state_dict().items():
        digest.update(key.encode())
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def wiring_checks(model, x, y, split, seed, lr):
    """Exact CE equivalence and isolated privacy gradient on the real head."""
    plain, candidate = copy.deepcopy(model), copy.deepcopy(model)
    head, tail = wrappers(candidate, split)
    plain.train()
    candidate.train()
    opt_plain = torch.optim.SGD(plain.parameters(), lr=lr)
    opt_candidate = torch.optim.SGD(candidate.parameters(), lr=lr)
    torch.manual_seed(seed)
    a = F.cross_entropy(plain(x), y)
    a.backward()
    torch.manual_seed(seed)
    z = head(x)
    b, _ = nopeek_loss(tail(z), y, x, z, 0)
    b.backward()
    need(torch.equal(a, b), "lambda=0 CE loss differs")
    for p, q in zip(plain.parameters(), candidate.parameters()):
        need(torch.equal(p.grad, q.grad), "lambda=0 gradients differ")
    opt_plain.step()
    opt_candidate.step()
    need(state_digest(plain) == state_digest(candidate), "lambda=0 optimizer update differs")
    head.eval()
    candidate.zero_grad(set_to_none=True)
    privacy = distance_correlation(x, head(x))
    grads = torch.autograd.grad(privacy, tuple(head.parameters()))
    need(all(bool(torch.isfinite(g).all()) for g in grads), "Nonfinite privacy gradient")
    grad_norm = float(torch.sqrt(sum((g * g).sum() for g in grads)))
    need(grad_norm > 0, "Privacy loss does not reach head")
    return {"split": split, "lambda0_loss_gradients_and_SGD_update_bit_exact": True,
            "isolated_dcor_head_gradient_l2": grad_norm, "batch_samples": len(x)}


def run(config_path, output, artifacts):
    config_path, output, artifacts = config_path.resolve(), output.resolve(), artifacts.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    need(config["device"] == "cpu", "Week7 evidence uses deterministic CPU only")
    need(config["splits"] == [2, 5, 8] and config["lambda1"] == [0, 0.5], "Smoke scope is fixed, not the Week8 grid")
    need(type(config["batch_size"]) is int and config["batch_size"] >= 3 and
         type(config["steps"]) is int and 1 <= config["steps"] <= 10 and
         type(config["validation_samples"]) is int and config["validation_samples"] >= config["batch_size"],
         "Invalid short smoke sizes")
    need(not output.exists() and not artifacts.exists(), "Refuse to overwrite experiment evidence/artifacts")
    need((ROOT / "ml/results/week7-nopeek").resolve() in output.resolve().parents and
         (ROOT / "ml/artifacts/week7").resolve() in artifacts.resolve().parents,
         "Outputs must be fresh children of Week7 experiment directories")
    set_determinism(config["seed"], config["threads"])
    torch.backends.mkldnn.enabled = False
    checkpoint_path = ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt"
    baseline, checkpoint = load_model(checkpoint_path, ROOT / "ml/src/mitdb_baseline_model.py")
    data_config, identifiers, arrays, metadata = load_train_val(checkpoint)
    size = config["batch_size"] * config["steps"]
    need(size <= len(arrays["train"][0]) and config["validation_samples"] <= len(arrays["val"][0]), "Subset larger than split")
    indices = {"train": np.random.default_rng(config["seed"]).permutation(len(arrays["train"][0]))[:size],
               "val": np.random.default_rng(config["seed"] + 1).permutation(len(arrays["val"][0]))[:config["validation_samples"]]}
    need(len(indices["val"]) % config["batch_size"] == 0, "Val subset must have complete dCor batches")
    selected = {s: (torch.from_numpy(arrays[s][0][idx].copy()), torch.from_numpy(arrays[s][1][idx].copy()))
                for s, idx in indices.items()}
    # Refuse reusing any existing directory, including after a failed run.
    output.mkdir(parents=True, exist_ok=False)
    artifacts.mkdir(parents=True, exist_ok=False)
    selection = {s: [{"row_index": int(i), "sample_id": metadata[s].iloc[i].sample_id,
                      "patient_id": metadata[s].iloc[i].patient_id, "class_index": int(arrays[s][1][i])}
                     for i in idx] for s, idx in indices.items()}
    write_json(output / "selected_samples.json", selection)
    initial_digest, checkpoint_hash = state_digest(baseline), sha(checkpoint_path)
    checks, records, runs = [], [], []
    for split in config["splits"]:
        checks.append(wiring_checks(baseline, selected["train"][0][:config["batch_size"]],
                                    selected["train"][1][:config["batch_size"]], split,
                                    config["seed"], config["learning_rate"]))
        for lambda1 in config["lambda1"]:
            set_determinism(config["seed"], config["threads"])
            model = copy.deepcopy(baseline)
            head, tail = wrappers(model, split)
            optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"])
            run_id = f"s{split}-lambda{lambda1}"
            def batches(phase):
                model.train(phase == "train")
                xs, ys = selected[phase]
                truth, predicted = [], []
                for step, start in enumerate(range(0, len(xs), config["batch_size"])):
                    x, y = xs[start:start+config["batch_size"]], ys[start:start+config["batch_size"]]
                    with torch.set_grad_enabled(phase == "train"):
                        z = head(x)
                        need(tuple(z.shape[1:]) == SHAPES[split][1:], "Authoritative split shape differs")
                        logits = tail(z)
                        loss, parts = nopeek_loss(logits, y, x, z, lambda1)
                        need(all(bool(torch.isfinite(v)) for v in parts.values()), "Nonfinite loss")
                        if phase == "train":
                            optimizer.zero_grad(set_to_none=True)
                            loss.backward()
                            need(all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in model.parameters()), "Invalid gradient")
                            optimizer.step()
                    truth.extend(y.tolist())
                    predicted.extend(logits.detach().argmax(1).tolist())
                    records.append({"run_id": run_id, "phase": phase, "step": step,
                                    "samples": len(y), "ce": float(parts["ce"].detach()),
                                    "dcor": float(parts["dcor"].detach()), "total": float(loss.detach()),
                                    "accuracy": float((logits.detach().argmax(1) == y).float().mean())})
                return classification_metrics(np.array(truth), np.array(predicted), data_config["classes"])
            before = state_digest(model)
            train_metrics = batches("train")
            val_metrics = batches("val")
            after = state_digest(model)
            need(before == initial_digest and after != before, "Experiment initialization/update differs")
            target = artifacts / f"{run_id}.pt"
            torch.save({"state_dict": model.state_dict(), "split": split, "lambda1": lambda1,
                        "baseline_checkpoint_sha256": checkpoint_hash, "deployment_model_profile_id": None,
                        "status": "EXPERIMENT_ONLY_NOT_APPROVED"}, target)
            runs.append({"run_id": run_id, "split": split, "lambda1": lambda1,
                         "train": train_metrics, "val": val_metrics, "initial_state_sha256": before,
                         "final_state_sha256": after, "artifact": str(target.relative_to(ROOT)),
                         "artifact_sha256": sha(target), "artifact_size_bytes": target.stat().st_size})
    need(state_digest(baseline) == initial_digest and sha(checkpoint_path) == checkpoint_hash, "Baseline changed")
    write_json(output / "batch_metrics.json", records)
    result = {"status": "PASS_OFFLINE_SMOKE_ONLY", "config": config, "wiring_checks": checks, "runs": runs,
              "test_opened_or_evaluated": False, "model_selection_performed": False,
              "dataset_identifiers": identifiers, "baseline_checkpoint_sha256": checkpoint_hash,
              "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_sha256": {p: artifact_sha256(ROOT / p) for p in SOURCES},
              "config_sha256": artifact_sha256(config_path),
              "environment": {"python": sys.version, "torch": torch.__version__, "numpy": np.__version__,
                              "platform": platform.platform(), "device": "cpu", "threads": config["threads"], "mkldnn": False},
              "limitations": "128 train and 512 validation samples; no generalization, privacy, accuracy-gate or hardware acceptance claim"}
    write_json(output / "summary.json", result)
    print(json.dumps({"status": result["status"], "wiring_checks": checks,
                      "runs": [{k: r[k] for k in ("run_id", "train", "val")} for r in runs]}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "ml/configs/week7_nopeek_smoke.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output, args.artifacts)
