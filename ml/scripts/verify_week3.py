"""Verify package bytes, raw-derived inputs, compiled C bits and PyTorch golden."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import re
import subprocess

import numpy as np

from week3_common import (CONTRACT, SOURCE, CHECKPOINT, FIELDS, check_decision,
    compiler_verify, inventory, load_model, need, read_json, safe_path, same_bits,
    sha, source_and_data, trace, versions)


def verify(package, repo, review=False, compiler="gcc"):
    package, repo = Path(package).resolve(), Path(repo).resolve()
    manifest = read_json(package / "manifest.json")
    need(manifest["contract_version"] == CONTRACT, "Contract version mismatch")
    need(re.fullmatch(r"[a-z0-9_-]+", manifest["handoff_id"]) is not None
         and package.name == manifest["handoff_id"], "Invalid handoff_id or directory identity")
    status = "REVIEW_ONLY_M_FINAL_UNCONFIRMED" if review else "SV3_RELEASE_PACKAGE"
    need(manifest["release_status"] == status,
         "Release gate: review package has no confirmed M_final; use --review for technical checks only")
    need(manifest["source_commit"] == SOURCE and manifest["dataset_profile"] == "MIT-BIH/1.0.0"
         and manifest["precision"] == "fp32" and manifest["eval"] is True and manifest["seed"] == 30,
         "Model identity/precision/eval/seed mismatch")
    if not review:
        need(manifest.get("quantization") == "not_applicable", "FP32 quantization must be not_applicable")
        need(manifest.get("sv1_acceptance") == {"package_review": "PENDING", "mcu_validation": "PENDING",
                                               "mcu_20_of_20": "NOT_YET_TESTED"},
             "SV3 release does not establish SV1 device acceptance")
    entries = manifest["files"]
    need(isinstance(entries, list) and entries, "Missing file inventory")
    paths = [e["path"] for e in entries]
    need(len(set(paths)) == len(paths) and "manifest.json" not in paths, "Duplicate path or manifest self-hash")
    for entry in entries:
        path = safe_path(package, entry["path"])
        need(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None, "Malformed SHA-256")
        need(type(entry["size_bytes"]) is int and entry["size_bytes"] > 0, "Invalid size")
        need(path.is_file() and path.stat().st_size == entry["size_bytes"] and sha(path) == entry["sha256"],
             f"File hash/size mismatch: {entry['path']}")
        if "shape" in entry:
            need(all(type(v) is int and v > 0 for v in entry["shape"]), "Invalid tensor shape")
    need(entries == inventory(package), "Inventory differs: missing/extra file, dtype, shape, size or encoding")
    required = {"README.md", "model/checkpoint.pt", "model/train_config.json", "model/graph.json",
                "model/freeze_decision.json", "samples.csv", "inputs.npy", "firmware/head_parameters.h",
                "firmware/host_c_verification.json", "scripts/export_week3.py", "scripts/verify_week3.py",
                "scripts/week3_common.py", "weights/conv1.weight.npy", "weights/conv1.bias.npy",
                "weights/conv2.weight.npy", "weights/conv2.bias.npy"}
    need(required.issubset(paths), "Missing required package files")
    decision = read_json(package / "model/freeze_decision.json")
    boundary = check_decision(decision, review)
    need(manifest["M_final"] == boundary and manifest["model_name"] == decision["model_name"]
         and manifest["model_version"] == decision["model_version"], "Frozen decision differs")
    expected_sources = {"ml/configs/mitdb_week2_baseline.json", "ml/src/mitdb_baseline_model.py",
                        "ml/src/mitdb_week2_data.py", "ml/src/train_mitdb_baseline.py",
                        "ml/src/week1_common.py", "ml/src/mitdb_common.py"}
    need(set(manifest["model_source_files"]) == expected_sources, "Incomplete frozen source bundle")
    for relative, entry in manifest["model_source_files"].items():
        blob = subprocess.check_output(["git", "show", f"{SOURCE}:{relative}"], cwd=repo)
        path = safe_path(package, entry["path"])
        need(path.read_bytes() == blob and sha(path) == entry["sha256"], "Bundled source differs from Git")
    source_key = "ml/src/mitdb_baseline_model.py"
    model, checkpoint = load_model(package / "model/checkpoint.pt",
                                   safe_path(package, manifest["model_source_files"][source_key]["path"]))
    need(manifest["checkpoint"]["path"] == "model/checkpoint.pt"
         and manifest["checkpoint"]["sha256"] == CHECKPOINT
         and manifest["checkpoint"]["size_bytes"] == (package / "model/checkpoint.pt").stat().st_size
         and manifest["checkpoint"]["selected_epoch"] == checkpoint["epoch"], "Checkpoint metadata mismatch")
    need(manifest["train_config"]["path"] == "model/train_config.json"
         and manifest["train_config"]["sha256"] == sha(package / "model/train_config.json")
         and read_json(package / "model/train_config.json") == checkpoint["training_config"], "Train config mismatch")
    need(manifest["dependency_versions"] == versions(), "Runtime versions differ; use recorded environment")
    expected_samples, expected_inputs, upstream, identifiers = source_and_data(repo, checkpoint)
    need(manifest["upstream"] == upstream and manifest["week1_dataset_artifacts"] == identifiers,
         "Week 1 upstream provenance mismatch")
    need(manifest["selection"] == decision["sample_selection"], "Sample selection metadata mismatch")
    with (package / "samples.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        need(reader.fieldnames == list(FIELDS), "CSV schema mismatch")
        samples = list(reader)
    need(len(samples) == 20 and [r["sample_index"] for r in samples] == [str(i) for i in range(20)],
         "Exactly 20 ordered samples required")
    need(len({r["sample_id"] for r in samples}) == 20
         and len({(r["record_id"], r["r_peak_sample"], r["lead_name"]) for r in samples}) == 20,
         "Duplicate sample/source identity")
    need(samples == expected_samples, "Samples differ from deterministic Week 1 source mapping")
    inputs = np.load(package / "inputs.npy", allow_pickle=False)
    need(same_bits(inputs, expected_inputs), "Delivered inputs differ from raw-derived Week 1 samples")
    graph, parameters, golden = trace(model, inputs, boundary)
    graph["boundary_status"] = "PROPOSAL_ONLY" if review else "CONFIRMED"
    need(manifest["graph"] == "model/graph.json" and read_json(package / "model/graph.json") == graph,
         "Graph differs from actual execution: missing/wrong op, shape, parameter or milestone")
    need(manifest["boundary_status"] == graph["boundary_status"] and manifest["memory"] == graph["memory"],
         "Graph boundary/memory metadata mismatch")
    expected_tensor_paths = {"inputs.npy", *parameters, *(f"golden/{k}.npy" for k in golden)}
    need({p for p in paths if p.endswith(".npy")} == expected_tensor_paths,
         "Missing/extra parameter or golden milestone")
    for path, actual in {**parameters, **{f"golden/{k}.npy": v for k, v in golden.items()}}.items():
        delivered = np.load(package / path, allow_pickle=False)
        need(same_bits(delivered, actual), f"FP32 recomputation bits differ: {path}")
    compiled = compiler_verify(package, graph, parameters, compiler)
    saved_compiler = read_json(package / "firmware/host_c_verification.json")
    need(saved_compiler["status"] == "PASS" and saved_compiler["fp32_elements"] == compiled["fp32_elements"],
         "Saved C verification evidence differs")
    return {"handoff_id": manifest["handoff_id"], "release_eligible": not review,
            "samples": len(samples), "milestones": list(graph["milestones"]),
            "checkpoint_sha256": CHECKPOINT, "source_commit": SOURCE,
            "memory": graph["memory"], "compiled_c": compiled}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--review", action="store_true")
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    result = verify(a.package, a.repo_root, a.review, a.compiler)
    import json
    print(json.dumps(result, indent=2))
    print("REVIEW_CHECKS_PASS (NOT A RELEASE)" if a.review else "HANDOFF_CHECKS_PASS")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
