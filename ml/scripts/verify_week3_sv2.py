"""Authenticate and independently recompute every Week 3 FP32 tail reference."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
import re
import math

import numpy as np

from week3_common import check_decision, need, read_json, same_bits, sha
from week3_sv2_common import (CHECKPOINT, CONTRACT, INPUT_SHA, MODEL_NAME, MODEL_VERSION, OPSET,
    P2_SHA, PREPROCESSING, SHAPES, SOURCE, SV1_MANIFEST, TARGET, TOLERANCE,
    SCRIPTS, authenticate, error, load_frozen, numerics, references, samples, split_map, versions)
LEGACY = "bitwise-v1"
PORTABLE = "portable-fp32-v2"
POLICIES = (LEGACY, PORTABLE)
# Only the first dense activation gets a new budget. Measured cross-build
# max_abs=1.9073486328125e-6; this absolute-only ceiling is ~5.24x that value.
DENSE9_MAX_ABS = 1e-5


def compare_activation(delivered, actual, s, policy):
    need(policy in POLICIES, "Unknown recomputation policy")
    need(type(s) is int and 0 <= s <= 10, "Invalid authoritative split")
    difference = error(actual, delivered)  # exact shape/dtype; finite; float64 subtraction
    if policy == LEGACY or s < 9:
        need(same_bits(delivered, actual), f"Recomputed golden bits differ: s={s}")
    else:
        budget = DENSE9_MAX_ABS if s == 9 else TOLERANCE
        need(difference < budget, f"Recomputed golden tolerance failure: s={s}")
    return {"same_bits": same_bits(delivered, actual), "max_abs_error": difference}


def _bounded(value):
    need(type(value) in (int, float) and math.isfinite(value) and 0 <= value < TOLERANCE,
         "Numerical evidence error outside strict FP32 bound")


def check_evidence(saved, observed):
    """Validate each report internally, then compare exact nonnumeric semantics.

    Error values are run-specific observations, not file authentication fields.
    No recursive allclose and no budget for arbitrary JSON numbers. Shapes,
    graph/op metadata, sample IDs/order, statuses and counts compare exactly.
    Both reports must retain correct per-case maxima and worst-case selection.
    """
    fields = ("pytorch_tail_max_abs_error", "onnx_max_abs_error",
              "onnx_vs_pytorch_tail_max_abs_error")

    def validate(report):
        need(set(report) == set(observed), "Numerical evidence schema differs")
        need(len(report["rows"]) == 200 and len(report["s10_identity_rows"]) == 20
             and len(report["per_split"]) == 11, "Numerical evidence case coverage differs")
        for row in report["rows"]:
            for field in fields:
                _bounded(row[field])
        for row in report["s10_identity_rows"]:
            _bounded(row["pytorch_tail_max_abs_error"])
            need(row["onnx_max_abs_error"] is None, "Identity evidence has ONNX result")
        for s, summary in enumerate(report["per_split"]):
            rows = [r for r in report["rows"] + report["s10_identity_rows"] if r["split_id"] == s]
            need(len(rows) == 20 and summary["split_id"] == s and summary["samples"] == 20,
                 "Numerical evidence split coverage differs")
            need(summary["pytorch_worst"] == max(r[fields[0]] for r in rows)
                 and summary["onnx_worst"] == (max(r[fields[1]] for r in rows) if s < 10 else None),
                 "Numerical evidence summary inconsistent")
        need(report["global_worst"] == max(report["rows"], key=lambda r: r[fields[1]]),
             "Numerical evidence global worst inconsistent")
        need(set(report["direct_head_tail_worst"]) == set(map(str, range(11))),
             "Numerical evidence direct split coverage differs")
        for value in report["direct_head_tail_worst"].values():
            _bounded(value)

    for report in (saved, observed):
        validate(report)
    for key in observed:
        if key in ("rows", "s10_identity_rows"):
            strip = lambda row: {k: v for k, v in row.items() if k not in fields}
            need([strip(r) for r in saved[key]] == [strip(r) for r in observed[key]],
                 "Numerical evidence case metadata differs")
            # Keep exact schemas, including all required metric fields.
            need([set(r) for r in saved[key]] == [set(r) for r in observed[key]],
                 "Numerical evidence row schema differs")
        elif key == "per_split":
            strip = lambda row: {k: v for k, v in row.items() if k not in ("pytorch_worst", "onnx_worst")}
            need([strip(r) for r in saved[key]] == [strip(r) for r in observed[key]],
                 "Numerical evidence summary metadata differs")
            need([set(r) for r in saved[key]] == [set(r) for r in observed[key]],
                 "Numerical evidence summary schema differs")
        elif key not in ("global_worst", "direct_head_tail_worst"):
            need(saved[key] == observed[key], f"Numerical evidence metadata differs: {key}")


def verify(package, expected_manifest_sha256, recomputation_policy=LEGACY):
    need(recomputation_policy in POLICIES, "Unknown recomputation policy")
    package = Path(package).resolve()
    manifest = authenticate(package, expected_manifest_sha256)
    need(manifest["contract_version"]==CONTRACT and manifest["handoff_id"]==package.name
         and re.fullmatch(r"[a-z0-9_-]+",package.name), "Contract/handoff identity mismatch")
    need(manifest["model_name"]==MODEL_NAME and manifest["model_version"]==MODEL_VERSION
         and manifest["checkpoint_sha256"]==CHECKPOINT and manifest["source_commit"]==SOURCE,
         "Frozen model identity mismatch")
    need(manifest["splits"]==split_map(), "Authoritative split mapping mismatch")
    need(manifest["opset"]==OPSET and manifest["opset_status"]=="CONFIRMED"
         and manifest["precision"]=="fp32" and manifest["batch_size"]==1
         and manifest["dynamic_axes"] is None and manifest["tolerance_strict"]==TOLERANCE,
         "FP32/opset/batch/tolerance mismatch")
    need(manifest["preprocessing"]==PREPROCESSING and manifest["downstream"]==TARGET,
         "Preprocessing/acceptance boundary mismatch")
    need(manifest["status"]=="SV3_FP32_REFERENCE_HANDOFF_SV2_ACCEPTANCE_PENDING", "Unsupported handoff status")
    required = {"README.md", "samples.csv", "model/checkpoint.pt", "model/mitdb_baseline_model.py",
                "model/train_config.json", "model/freeze_decision.json", "model/sv2_interface.json",
                "model/sv1_v2_manifest.json", "golden/reference_logits.npy", "evidence/numerical_verification.json",
                "requirements/requirements-week3-onnx.txt", "requirements/requirements-core.txt",
                "requirements/requirements-gpu-cu130.txt", "evidence/source_provenance.json",
                *[f"scripts/{n}" for n in SCRIPTS], *[f"models/tail_{s}.onnx" for s in range(10)],
                *[f"golden/z_s{s}.npy" for s in range(11)]}
    need({f["path"] for f in manifest["files"]} == required, "Required package file set differs")
    need(sha(package / "model/sv1_v2_manifest.json")==SV1_MANIFEST, "SV1 provenance manifest mismatch")
    need(manifest["dependency_versions"]==versions(), "Runtime versions differ; use pinned environment")
    decision = read_json(package / "model/freeze_decision.json")
    check_decision(decision, review=False)
    original = read_json(package / "model/sv1_v2_manifest.json")
    pinned = {r["path"]:r["sha256"] for r in original["files"]}
    for name in ("freeze_decision.json", "train_config.json"):
        need(sha(package / "model" / name)==pinned[f"model/{name}"], "Frozen config bytes differ")
    config = read_json(package / "model/sv2_interface.json")
    need(config["status"]=="CONFIRMED" and config["splits"]==split_map()
         and config["opset"]==OPSET and config["opset_status"]=="CONFIRMED"
         and config["model_name"]==MODEL_NAME and config["model_version"]==MODEL_VERSION
         and config["checkpoint_sha256"]==CHECKPOINT and config["downstream"]==TARGET
         and config["preprocessing"]==PREPROCESSING, "Confirmed interface config differs")
    need(sha(package / "golden/z_s0.npy")==INPUT_SHA, "Frozen input bytes differ")
    need(sha(package / "golden/z_s2.npy")==P2_SHA, "Accepted SV1 P2 bytes differ")
    identities = samples(package)
    need(manifest["samples"]==identities, "Manifest sample identities differ")
    model = load_frozen(package)
    inputs = np.load(package / "golden/z_s0.npy",allow_pickle=False)
    full, activations, direct_errors = references(model,inputs)
    recomputation = {}
    for s in range(11):
        delivered = np.load(package / f"golden/z_s{s}.npy",allow_pickle=False)
        need(delivered.shape==(20,*SHAPES[s][1:]), f"Golden shape mismatch: s={s}")
        recomputation[str(s)] = compare_activation(delivered, activations[s], s, recomputation_policy)
    original = np.load(package / "golden/reference_logits.npy",allow_pickle=False)
    if recomputation_policy == LEGACY:
        need(same_bits(original,full), "Reference logits bits differ")
    else:
        need(same_bits(original, np.load(package / "golden/z_s10.npy", allow_pickle=False)),
             "Delivered s10/reference logits identity differs")
        need(error(full, original) < TOLERANCE, "Reference logits tolerance failure")
    # Portable comparisons must be against the delivered original logits.
    evidence = numerics(package,model,full if recomputation_policy == LEGACY else original,identities)
    evidence["direct_head_tail_worst"] = {str(s):max(v) for s,v in direct_errors.items()}
    need(manifest["onnx_models"]==evidence["onnx_models"], "ONNX inventory/graph metadata differs")
    saved = read_json(package / "evidence/numerical_verification.json")
    if recomputation_policy == LEGACY:
        need(saved==evidence, "Numerical evidence differs from recomputation")
    else:
        check_evidence(saved, evidence)
    return {"status":"SV2_FP32_REFERENCE_CHECKS_PASS", "handoff_id":package.name,
            "manifest_sha256":expected_manifest_sha256, "comparisons":evidence["comparisons"],
            "per_split":evidence["per_split"], "global_worst":evidence["global_worst"],
            "s10_identity_samples":len(evidence["s10_identity_rows"]), "downstream":TARGET,
            "recomputation_policy":recomputation_policy, "legacy_contract_pass":recomputation_policy == LEGACY,
            "reference_basis":"delivered original logits" if recomputation_policy == PORTABLE else "bitwise recomputed logits",
            "recomputed_activations":recomputation,
            "dense9_strict_max_abs_error":DENSE9_MAX_ABS if recomputation_policy == PORTABLE else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",type=Path,required=True)
    parser.add_argument("--expected-manifest-sha256",required=True)
    parser.add_argument("--recomputation-policy", choices=POLICIES, default=LEGACY)
    args = parser.parse_args()
    import json
    print(json.dumps(verify(args.package,args.expected_manifest_sha256,args.recomputation_policy),indent=2))
