"""Create Week 4 offline artifacts in a NEW output directory; never overwrite."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import matplotlib
import numpy as np
import torch

from week3_common import compiler_verify, header, need, read_json, sha, text, write_json
from week3_sv2_common import CONTRACT, INPUT_SHA, MODEL_VERSION, PREPROCESSING, SAMPLES_SHA, SOURCE, versions
from week4_common import (CHECKPOINT, OUTPUT, SCRIPTS, SOURCE_HASH_POLICY, W3_PATH, W3_SHA, csv_profile,
                          figure, frozen, graph_parameters, inventory, profile, source_sha)


def export(repo, output, compiler="gcc"):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    need(not output.exists(), "Week 4 output already exists; choose a new output directory")
    package, w3, model, inputs, identities = frozen(repo)
    value = profile(model, inputs)
    graph, parameters = graph_parameters(model, inputs)
    output.mkdir(parents=True)
    write_json(output / "tensor_profile.json", value)  # Week 4 extension of canonical registry
    text(output / "tensor_profile.csv", csv_profile(value))
    write_json(output / "model_graph.json", graph)
    for path, a in parameters.items():
        (output / path).parent.mkdir(parents=True, exist_ok=True)
        np.save(output / path, a, allow_pickle=False)
    text(output / "firmware/head_parameters.h", header(graph, parameters))
    compiled = compiler_verify(output, graph, parameters, compiler)
    write_json(output / "firmware/host_c_verification.json", compiled)
    figure(value, output)
    external = []
    for row in w3["files"]:
        item = {"path": f"{W3_PATH}/{row['path']}", "sha256": row["sha256"], "file_size_bytes": row["size_bytes"]}
        if row["path"].endswith(".npy"):
            a = np.load(package / row["path"], allow_pickle=False)
            item.update(dtype=a.dtype.str, shape=list(a.shape), logical_tensor_bytes=a.nbytes,
                        layout="NCL" if a.ndim == 3 else "NC", sample_order_sha256=SAMPLES_SHA)
        external.append(item)
    source_paths = [f"ml/scripts/{name}" for name in SCRIPTS] + [
        "ml/scripts/week3_common.py", "ml/scripts/week3_sv2_common.py",
        "ml/configs/week3_sv2_interface_review.json", "ml/configs/week3_model_freeze.json",
        "ml/configs/mitdb_week1_config.json", "ml/configs/mitdb_normalization.json",
        "ml/manifests/mitdb_patient_split.csv", "contracts/sv3_sv2_week3_fp32.md",
        "contracts/sv3_sv1_week3_model_handoff.md", "ml/src/mitdb_baseline_model.py",
        "ml/configs/week4_requirement_references.json"]
    requirements = read_json(repo / "ml/configs/week4_requirement_references.json")
    manifest = {"schema_version": 2, "scope": "SV3_WEEK4_OFFLINE",
                "source_hash_policy": SOURCE_HASH_POLICY,
                "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                "source_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip(),
                "source_files": [{"path": n, "sha256": source_sha(repo / n)} for n in source_paths],
                "project_requirements": requirements, "model_revision": MODEL_VERSION,
                "model_source_commit": SOURCE, "checkpoint_path": f"{W3_PATH}/model/checkpoint.pt",
                "checkpoint_sha256": CHECKPOINT, "week3_manifest_path": f"{W3_PATH}/manifest.json",
                "week3_manifest_sha256": W3_SHA, "split_convention_version": CONTRACT,
                "sample_set": {"count": 20, "samples_path": f"{W3_PATH}/samples.csv", "samples_sha256": SAMPLES_SHA,
                               "ordered_sample_ids": [r["sample_id"] for r in identities], "input_path": f"{W3_PATH}/golden/z_s0.npy", "input_sha256": INPUT_SHA},
                "preprocessing": PREPROCESSING, "class_order": ["N", "S", "V", "F", "Q"],
                "dependency_versions": {**versions(), "matplotlib": matplotlib.__version__},
                "generation_command": "& ml/.venv/Scripts/python.exe -B ml/scripts/profile_week4.py --repo-root . --output-dir <NEW_DIRECTORY> --compiler " + compiler,
                "comparison": "All 11 existing Week 3 goldens reused, FP32 bitwise; N=1 per inference",
                "int8": "Estimated theoretical payload only = numel; no INT8 artifact or quantization",
                "external_status": "SV2 independent acceptance pending; does not block SV3 Week 4",
                "no_training": True, "no_week5": True, "no_device_timing": True,
                "files": inventory(output), "reused_files": external}
    write_json(output / "manifest.json", manifest)
    return sha(output / "manifest.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path(OUTPUT))
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    digest = export(args.repo_root, args.output_dir, args.compiler)
    print(f"WEEK4_EXPORT_PASS: {args.output_dir}")
    print(f"MANIFEST_SHA256: {digest}")
