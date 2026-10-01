"""Authenticate Week 4 artifacts and independently recompute all frozen references."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
import torch

from week3_common import (compiler_verify, need, read_json, safe_path, same_bits, sha)
from week3_sv2_common import (CONTRACT, INPUT_SHA, MODEL_VERSION, PREPROCESSING,
                            SAMPLES_SHA, SOURCE, references, split_map, versions)
from week4_common import (CHECKPOINT, OUTPUT, SCRIPTS, W3_PATH, W3_SHA, csv_profile,
                          frozen, graph_parameters, inventory, profile)


def verify(root, repo, expected_manifest_sha256, compiler="gcc"):
    root, repo = Path(root).resolve(), Path(repo).resolve()
    need(isinstance(expected_manifest_sha256, str) and len(expected_manifest_sha256) == 64,
         "Independent Week 4 manifest anchor required")
    raw = (root / "manifest.json").read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected_manifest_sha256, "Week 4 manifest SHA-256 mismatch")
    manifest = read_json(root / "manifest.json")
    need(manifest["schema_version"] == 1 and manifest["scope"] == "SV3_WEEK4_OFFLINE"
         and manifest["model_revision"] == MODEL_VERSION and manifest["model_source_commit"] == SOURCE
         and manifest["checkpoint_sha256"] == CHECKPOINT
         and manifest["checkpoint_path"] == f"{W3_PATH}/model/checkpoint.pt"
         and manifest["week3_manifest_path"] == f"{W3_PATH}/manifest.json"
         and manifest["week3_manifest_sha256"] == W3_SHA
         and manifest["split_convention_version"] == CONTRACT, "Frozen Week 4 provenance differs")
    need(manifest["no_training"] is True and manifest["no_week5"] is True and manifest["no_device_timing"] is True,
         "Week 4 scope differs")
    need(manifest["preprocessing"] == PREPROCESSING and manifest["class_order"] == ["N", "S", "V", "F", "Q"],
         "Preprocessing/class mapping differs")
    need(manifest["dependency_versions"] == {**versions(), "matplotlib": matplotlib.__version__}, "Week 4 runtime versions differ")
    # Authenticate raw bytes first. Local inventory must have exactly the expected set.
    for row in manifest["files"]:
        p = safe_path(root, row["path"])
        need(p.is_file() and sha(p) == row["sha256"] and p.stat().st_size == row["file_size_bytes"],
             f"Week 4 artifact hash/size mismatch: {row['path']}")
    need(manifest["files"] == inventory(root), "Week 4 inventory differs")
    for row in manifest["source_files"]:
        need(sha(safe_path(repo, row["path"])) == row["sha256"], f"Source file changed: {row['path']}")
    need({f"ml/scripts/{n}" for n in SCRIPTS}.issubset({r["path"] for r in manifest["source_files"]}),
         "Week 4 source coverage differs")
    package, w3, model, inputs, identities = frozen(repo)
    expected_reused = []
    for row in w3["files"]:
        item = {"path": f"{W3_PATH}/{row['path']}", "sha256": row["sha256"], "file_size_bytes": row["size_bytes"]}
        if row["path"].endswith(".npy"):
            a = np.load(package / row["path"], allow_pickle=False)
            item.update(dtype=a.dtype.str, shape=list(a.shape), logical_tensor_bytes=a.nbytes,
                        layout="NCL" if a.ndim == 3 else "NC", sample_order_sha256=SAMPLES_SHA)
        expected_reused.append(item)
    need(manifest["reused_files"] == expected_reused, "Reused Week 3 inventory/order metadata differs")
    need(manifest["sample_set"] == {"count": 20, "samples_path": f"{W3_PATH}/samples.csv", "samples_sha256": SAMPLES_SHA,
                                  "ordered_sample_ids": [r["sample_id"] for r in identities],
                                  "input_path": f"{W3_PATH}/golden/z_s0.npy", "input_sha256": INPUT_SHA},
         "20-sample identity/order differs")
    before = {k: v.detach().clone() for k, v in model.state_dict().items()}
    expected_profile = profile(model, inputs)
    delivered = read_json(root / "tensor_profile.json")
    need(delivered == expected_profile, "Execution profile/boundary/analysis differs")
    need((root / "tensor_profile.csv").read_bytes() == csv_profile(expected_profile).encode("utf-8"), "Profile CSV differs")
    graph, parameters = graph_parameters(model, inputs)
    need(read_json(root / "model_graph.json") == graph, "Full-forward graph/op attributes differ")
    # Full-forward hooks and split execution are independent paths through the same frozen modules.
    observed = {o["module_path"]: o for o in graph["ops"]}
    for row in delivered["splits"]:
        shape = observed[row["head_last_op"]]["output_shape_n1"] if row["s"] else [1, 1, 360]
        need(row["shape_n1"] == shape, f"Full-forward boundary shape differs: {row['s']}")
    full, activations, _ = references(model, inputs)
    for s, expected in activations.items():
        actual = np.load(package / f"golden/z_s{s}.npy", allow_pickle=False)
        need(actual.dtype.str == "<f4" and actual.flags.c_contiguous and np.isfinite(actual).all(), f"Invalid golden: {s}")
        need(actual.shape == (20, *delivered["splits"][s]["shape_n1"][1:]), f"Golden shape differs: {s}")
        need(same_bits(actual, expected), f"Golden FP32 bits differ: {s}")
    need(same_bits(activations[0], inputs), "s=0 input boundary differs")
    saved_logits = np.load(package / "golden/reference_logits.npy", allow_pickle=False)
    need(same_bits(activations[10], full) and same_bits(full, saved_logits), "s=L/full-model logits differ")
    need(np.array_equal(full.argmax(axis=1), saved_logits.argmax(axis=1)), "Frozen predictions changed")
    for path, expected in parameters.items():
        actual = np.load(root / path, allow_pickle=False)
        need(actual.dtype.str == "<f4" and actual.flags.c_contiguous and np.isfinite(actual).all(), f"Invalid parameter: {path}")
        need(same_bits(actual, expected), f"Parameter FP32 bits differ: {path}")
    required = {"tensor_profile.json", "tensor_profile.csv", "model_graph.json", "tensor_size_vs_split.pdf",
                "tensor_size_vs_split.png", "firmware/head_parameters.h", "firmware/host_c_verification.json", *parameters}
    need({r["path"] for r in manifest["files"]} == required, "Week 4 required file set differs")
    compiled = compiler_verify(root, graph, parameters, compiler)
    need(read_json(root / "firmware/host_c_verification.json") == compiled, "Host C evidence differs")
    need(all(torch.equal(before[k], v) for k, v in model.state_dict().items()), "Frozen state changed during verification")
    need(all(p.grad is None for p in model.parameters()) and not model.training, "Unexpected gradients/training")
    return {"status": "WEEK4_CHECKS_PASS", "manifest_sha256": expected_manifest_sha256,
            "splits": 11, "golden_cases_bitwise": 220, "parameters_bitwise": graph["parameter_count"],
            "compiled_c": compiled, "analysis": delivered["analysis"],
            "reused_week3_manifest_sha256": W3_SHA, "sv2_acceptance": "PENDING_NOT_BLOCKING_WEEK4"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path(OUTPUT))
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    print(json.dumps(verify(args.output_dir, args.repo_root, args.expected_manifest_sha256, args.compiler), indent=2))
