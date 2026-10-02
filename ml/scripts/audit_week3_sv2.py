"""Historical 2026-09-30 audit, before the team confirmed split mapping.

Current workflow: export_week3_sv2.py and verify_week3_sv2.py. This historical
script intentionally retains the old evidence commit and unresolved status.

An operation output is not an approved project split. This script exports no
tail and does not claim an SV2 release or VART/KV260 compatibility.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import torch

from verify_week3 import verify
from week3_common import load_model, need, read_json, sha, write_json

MAIN_EVIDENCE = "144413b3c827d5a7a0163e9eab880670fdf91d8b"
TRUSTED_MANIFEST = "0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469"


def blob(repo, relative):
    return subprocess.check_output(["git", "show", f"{MAIN_EVIDENCE}:{relative}"], cwd=repo)


def audit(repo, output, compiler):
    repo, output = repo.resolve(), output.resolve()
    need(not output.exists(), "Audit output already exists; choose a new location")
    package = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    before = {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*") if p.is_file()}
    verified = verify(package, repo, compiler=compiler, expected_manifest_sha256=TRUSTED_MANIFEST)
    model, _ = load_model(package / "model/checkpoint.pt",
                          package / "model/source/ml/src/mitdb_baseline_model.py")
    inputs = np.load(package / "inputs.npy", allow_pickle=False)
    with (package / "samples.csv").open(encoding="utf-8", newline="") as stream:
        samples = list(csv.DictReader(stream))
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.mkldnn.enabled = False
    operations = [(name, module) for name, module in model.named_modules()
                  if name and not list(module.children())]
    observed, handles, logits, p2 = [], [], [], []

    def hook(name):
        def capture(module, args, result):
            observed.append({"source_op": name, "type": type(module).__name__,
                             "input_shape_N1": list(args[0].shape),
                             "output_shape_N1": list(result.shape),
                             "dtype": str(result.dtype),
                             "layout": "NCL" if result.ndim == 3 else "NC",
                             "split_id": None, "split_status": "NOT_ASSIGNED"})
            if name == "features.4":
                p2.append(result.detach().numpy().copy())
        return capture

    for name, module in operations:
        handles.append(module.register_forward_hook(hook(name)))
    try:
        with torch.inference_mode():
            for i in range(20):
                logits.append(model(torch.from_numpy(inputs[i:i+1])).numpy().copy())
    finally:
        for handle in handles:
            handle.remove()
    graph = observed[:len(operations)]
    need(len(observed) == 20 * len(operations), "Unexpected graph execution count")
    need(all(observed[i*len(operations):(i+1)*len(operations)] == graph for i in range(20)),
         "Graph differs between samples")
    for index, entry in enumerate(graph):
        entry["remaining_operations"] = [name for name, _ in operations[index+1:]]
        entry["final_logits_shape_N1"] = [1, 5]
    reference = np.concatenate(logits)
    need(reference.shape == (20, 5) and np.isfinite(reference).all(), "Invalid reference logits")
    actual_p2 = np.concatenate(p2)
    need(actual_p2.tobytes() == np.load(package / "golden/P2.npy", allow_pickle=False).tobytes(),
         "P2 differs from immutable handoff")

    # Read the checked-in capture parser at a pinned evidence commit. Call only
    # its parsing functions, not main(), which would rewrite the SV1 report.
    evidence_paths = ["device/scripts/check_week3_capture.py", "device/scripts/generate_week3_inputs.py",
                      "device/reports/week3_mcu_validation.json", "device/reports/week3_build.md",
                      "results/week3/logs/week3_capture_verified.txt"]
    with tempfile.TemporaryDirectory(prefix="week3_sv1_capture_audit_") as temporary:
        root = Path(temporary)
        for relative in evidence_paths:
            (root / Path(relative).name).write_bytes(blob(repo, relative))
        sys.path.insert(0, str(root))
        try:
            spec = importlib.util.spec_from_file_location("sv1_capture_audit", root / "check_week3_capture.py")
            parser = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(parser)
            capture = root / "week3_capture_verified.txt"
            recorded = read_json(root / "week3_mcu_validation.json")
            # Git stores this text capture with LF, while SV1 hashed the original
            # Windows CRLF file. Prove the exact documented bytes after changing
            # only line endings; preserve and record the Git blob hash separately.
            capture_bytes = capture.read_bytes()
            need(b"\r" not in capture_bytes, "Unexpected Git capture line endings")
            restored_capture_sha = hashlib.sha256(capture_bytes.replace(b"\n", b"\r\n")).hexdigest()
            need(restored_capture_sha == recorded["capture_sha256"], "Recorded CRLF capture hash mismatch")
            need(recorded["manifest_sha256"] == TRUSTED_MANIFEST, "SV1 used another manifest")
            tensors = parser.parse_capture(capture)
            stack = parser.parse_stack_usage(capture)
            need(set(tensors) == ({(i, "P2") for i in range(20)} |
                                 {(0, k) for k in ("M1", "R1", "M2", "R2", "P2")}),
                 "Unexpected captured tensor set")
            golden = np.load(package / "golden/P2.npy", allow_pickle=False)
            errors = []
            for i, row in enumerate(samples):
                error = float(np.max(np.abs(tensors[(i, "P2")].astype(np.float64) - golden[i].astype(np.float64))))
                result = {"sample_index": i, "sample_id": row["sample_id"],
                          "p2_max_abs_error": error, "pass": error < 1e-3}
                need(result == recorded["samples"][i], "Recomputed MCU result differs from record")
                need(result["pass"], "MCU P2 numerical failure")
                errors.append(result)
            intermediate = {}
            for name in ("M1", "R1", "M2", "R2"):
                target = np.load(package / "golden" / f"{name}.npy", allow_pickle=False)[0]
                intermediate[name] = float(np.max(np.abs(tensors[(0, name)].astype(np.float64) - target.astype(np.float64))))
            need(intermediate == recorded["sample0_intermediate_max_abs_error"], "Intermediate record differs")
            evidence_hashes = {relative: sha(root / Path(relative).name) for relative in evidence_paths}
        finally:
            sys.path.remove(str(root))
    after = {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*") if p.is_file()}
    need(before == after, "Immutable v2 package changed")
    output.mkdir(parents=True)
    np.save(output / "reference_logits.npy", reference, allow_pickle=False)
    report = {"status": "AUDIT_ONLY_NOT_SV2_HANDOFF", "valid_splits": None,
              "split_registry_status": "BLOCKED_MISSING_EXISTING_SPLIT_MAPPING",
              "frozen_package_verification": verified, "source_evidence_commit": MAIN_EVIDENCE,
              "actual_graph_endpoints_not_approved_splits": graph,
              "samples": samples, "reference_logits_shape": list(reference.shape),
              "reference_logits_sha256": sha(output / "reference_logits.npy"),
              "p2_matches_frozen_golden_bitwise": True, "sv1_v2_unchanged": True,
              "sv1_evidence_hashes": evidence_hashes,
              "sv1_capture_hash_policy": "Git blob LF; LF-to-CRLF restoration matches original SV1 raw SHA-256",
              "sv1_original_crlf_capture_sha256": restored_capture_sha,
              "sv1_independent_package_checks": "RECORDED_PASS_IN_PINNED_BUILD_REPORT",
              "sv1_mcu_p2_samples": errors,
              "sv1_mcu_p2_worst_error": max(r["p2_max_abs_error"] for r in errors),
              "sv1_mcu_p2_status": "20_OF_20_PASS_RECHECKED_FROM_CAPTURE",
              "sv1_sample0_intermediate_errors": intermediate,
              "sv1_main_stack_peak_bytes": max(r["main_peak_bytes"] for r in stack),
              "sv1_remaining_evidence_gap": "Intermediate M1/R1/M2/R2 for samples 1..19 not captured",
              "pytorch_tail_status": "NOT_RUN_PENDING_SPLIT_MAPPING",
              "onnx_status": "NOT_EXPORTED_PENDING_SPLIT_MAPPING",
              "overall_week3": "NOT_DONE"}
    write_json(output / "audit.json", report)
    print(f"AUDIT_PASS: {len(graph)} real operation endpoints; no split IDs assigned")
    print(f"SV1_P2: 20/20 PASS; worst error {report['sv1_mcu_p2_worst_error']}")
    print(f"SV2_EXPORT_BLOCKED: {output / 'audit.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    audit(args.repo_root, args.output, args.compiler)
