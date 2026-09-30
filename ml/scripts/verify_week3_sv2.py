"""Authenticate and independently recompute every Week 3 FP32 tail reference."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import numpy as np

from week3_common import check_decision, need, read_json, same_bits, sha
from week3_sv2_common import (CHECKPOINT, CONTRACT, INPUT_SHA, MODEL_NAME, MODEL_VERSION, OPSET,
    P2_SHA, PREPROCESSING, SHAPES, SOURCE, SV1_MANIFEST, TARGET, TOLERANCE,
    authenticate, load_frozen, numerics, references, samples, split_map, versions)

SCRIPTS = ("export_week3_sv2.py", "verify_week3_sv2.py", "test_week3_sv2.py", "week3_sv2_common.py", "week3_common.py")


def verify(package, expected_manifest_sha256):
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
    for s in range(11):
        delivered = np.load(package / f"golden/z_s{s}.npy",allow_pickle=False)
        need(delivered.shape==(20,*SHAPES[s][1:]), f"Golden shape mismatch: s={s}")
        need(same_bits(delivered,activations[s]), f"Recomputed golden bits differ: s={s}")
    need(same_bits(np.load(package / "golden/reference_logits.npy",allow_pickle=False),full), "Reference logits bits differ")
    evidence = numerics(package,model,full,identities)
    evidence["direct_head_tail_worst"] = {str(s):max(v) for s,v in direct_errors.items()}
    need(manifest["onnx_models"]==evidence["onnx_models"], "ONNX inventory/graph metadata differs")
    need(read_json(package / "evidence/numerical_verification.json")==evidence, "Numerical evidence differs from recomputation")
    return {"status":"SV2_FP32_REFERENCE_CHECKS_PASS", "handoff_id":package.name,
            "manifest_sha256":expected_manifest_sha256, "comparisons":evidence["comparisons"],
            "per_split":evidence["per_split"], "global_worst":evidence["global_worst"],
            "s10_identity_samples":len(evidence["s10_identity_rows"]), "downstream":TARGET}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",type=Path,required=True)
    parser.add_argument("--expected-manifest-sha256",required=True)
    args = parser.parse_args()
    import json
    print(json.dumps(verify(args.package,args.expected_manifest_sha256),indent=2))
