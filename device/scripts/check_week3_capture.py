"""Check USB CDC FP32 tensors against the authenticated Week 3 v2 golden."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from generate_week3_inputs import TRUSTED_MANIFEST, check_inventory, sha256

MILESTONES = ("M1", "R1", "M2", "R2", "P2")
COUNTS = {"M1": 5760, "R1": 5760, "M2": 5760, "R2": 5760, "P2": 2880}
READY = "READY WEEK3 mitdb-week3-fp32-20260925-v2 P2 1x16x180"
COMMAND = "COMMAND TRACE n or RUN n (0..19)"
THRESHOLD = 1e-3
CSV_FIELDS = ["sample_index", "sample_id", *(f"{name}_max_abs_error" for name in MILESTONES), "P2_pass"]


def read_capture(path: Path, full_trace: bool) -> tuple[dict[tuple[int, str], np.ndarray], list[dict[str, int]]]:
    """Require the complete, ordered firmware frame for every command."""
    lines = path.read_text(encoding="ascii").splitlines()
    position = 0

    def take(expected: str) -> None:
        nonlocal position
        actual = lines[position] if position < len(lines) else "<EOF>"
        if actual != expected:
            raise ValueError(f"Capture line {position + 1}: expected {expected!r}, got {actual!r}")
        position += 1

    # A USB reset may print Zephyr startup lines before the application banner.
    while position < len(lines) and not lines[position].startswith("READY WEEK3 "):
        if lines[position].startswith(("BEGIN ", "TENSOR ", "END ", "DONE ", "STACK ")):
            raise ValueError("Data appeared before the Week 3 READY banner")
        position += 1
    take(READY)
    take(COMMAND)
    tensors: dict[tuple[int, str], np.ndarray] = {}
    stack_usage = []
    for sample in range(20):
        command = "TRACE" if full_trace or sample == 0 else "RUN"
        take(f"BEGIN {sample} {command}")
        names = MILESTONES if command == "TRACE" else ("P2",)
        for name in names:
            count = COUNTS[name]
            take(f"TENSOR {sample} {name} {count}")
            words = []
            while position < len(lines) and lines[position] != f"END {name}":
                parts = lines[position].split()
                if len(parts) != 16 or any(re.fullmatch(r"[0-9a-f]{8}", part) is None for part in parts):
                    raise ValueError(f"Invalid FP32 row at capture line {position + 1} for {sample}/{name}")
                words.extend(int(part, 16) for part in parts)
                if len(words) > count:
                    raise ValueError(f"Too many FP32 elements for {sample}/{name}")
                position += 1
            take(f"END {name}")
            if len(words) != count:
                raise ValueError(f"{sample}/{name}: expected {count} FP32 elements, got {len(words)}")
            tensor = np.asarray(words, dtype="<u4").view("<f4").reshape(1, 16, 180 if name == "P2" else 360)
            if not np.isfinite(tensor).all():
                raise ValueError(f"Non-finite FP32 value in {sample}/{name}")
            tensors[(sample, name)] = tensor
        line = lines[position] if position < len(lines) else "<EOF>"
        match = re.fullmatch(r"STACK main_peak_bytes=(\d+) main_size_bytes=(\d+)", line)
        if match is None:
            raise ValueError(f"Missing or invalid STACK for sample {sample}: {line!r}")
        peak, size = map(int, match.groups())
        if size <= 0 or peak > size:
            raise ValueError(f"Invalid stack bounds for sample {sample}: {line!r}")
        stack_usage.append({"sample_index": sample, "main_peak_bytes": peak, "main_size_bytes": size})
        position += 1
        take(f"DONE {sample}")
    if position != len(lines):
        raise ValueError(f"Unexpected data after DONE 19 at line {position + 1}: {lines[position]!r}")
    expected_count = 100 if full_trace else 24
    if len(tensors) != expected_count:
        raise ValueError(f"Tensor completeness failed: {len(tensors)}/{expected_count}")
    return tensors, stack_usage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--mode", choices=("legacy", "20x5"), default="legacy")
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--port", help="Port used by the collector, for session provenance")
    args = parser.parse_args()
    if args.mode == "20x5" and (args.report_output is None or args.csv_output is None):
        parser.error("--mode 20x5 requires --report-output and --csv-output")
    if args.mode == "legacy" and args.csv_output is not None:
        parser.error("--csv-output is only valid with --mode 20x5")

    repo = args.repo_root.resolve()
    capture = args.capture.resolve()
    package = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    check_inventory(package)
    with (package / "samples.csv").open(encoding="utf-8", newline="") as stream:
        samples = list(csv.DictReader(stream))
    if (len(samples) != 20 or [row["sample_index"] for row in samples] != [str(i) for i in range(20)]
            or len({row["sample_id"] for row in samples}) != 20):
        raise ValueError("Invalid v2 sample_index/sample_id mapping")
    for row in samples:
        if row["sample_id"] != f"MIT-BIH:{row['record_id']}:{row['r_peak_sample']}:{row['lead_name']}":
            raise ValueError(f"Invalid sample identity at index {row['sample_index']}")
    full_trace = args.mode == "20x5"
    tensors, stack_usage = read_capture(capture, full_trace)
    golden = {}
    for name in MILESTONES:
        array = np.load(package / "golden" / f"{name}.npy", allow_pickle=False)
        shape = (20, 16, 180 if name == "P2" else 360)
        if array.shape != shape or array.dtype.str != "<f4" or not array.flags.c_contiguous or not np.isfinite(array).all():
            raise ValueError(f"Golden {name} must be finite C-contiguous FP32 with shape {shape}")
        golden[name] = array

    results = []
    csv_rows = []
    max_by_milestone = {name: 0.0 for name in MILESTONES}
    for sample, row in enumerate(samples):
        names = MILESTONES if full_trace or sample == 0 else ("P2",)
        errors = {}
        for name in names:
            actual = tensors[(sample, name)].reshape(16, -1).astype(np.float64)
            reference = golden[name][sample].astype(np.float64)
            errors[name] = float(np.max(np.abs(actual - reference)))
            max_by_milestone[name] = max(max_by_milestone[name], errors[name])
        passed = errors["P2"] < THRESHOLD
        results.append({"sample_index": sample, "sample_id": row["sample_id"],
                        "max_abs_error": errors, "P2_pass": passed})
        if full_trace:
            csv_rows.append({"sample_index": sample, "sample_id": row["sample_id"],
                             **{f"{name}_max_abs_error": errors[name] for name in MILESTONES},
                             "P2_pass": "PASS" if passed else "FAIL"})
        print(f"{sample:02d} {row['sample_id']}: " + " ".join(f"{name}={errors[name]:.9g}" for name in names)
              + (" P2 PASS" if passed else " P2 FAIL"))

    passed = all(row["P2_pass"] for row in results)
    report = {
        "handoff_id": package.name,
        "manifest_sha256": TRUSTED_MANIFEST,
        "capture_sha256": sha256(capture),
        "capture_session": {
            "capture_path": str(capture),
            "capture_size_bytes": capture.stat().st_size,
            "capture_last_write_utc": datetime.fromtimestamp(capture.stat().st_mtime, timezone.utc).isoformat(),
            "validated_utc": datetime.now(timezone.utc).isoformat(),
            "port": args.port,
            "ready_banner": READY,
            "collector_commands": "TRACE 0..19" if full_trace else "TRACE 0; RUN 1..19",
            "capture_format": "USB CDC ASCII hexadecimal FP32 bits",
        },
        "validation_mode": args.mode,
        "tensor_check": {"status": "PASS", "required": 100 if full_trace else 24,
                         "observed": len(tensors), "ordered_begin_done_pairs": 20,
                         "shape_N1": {name: [1, 16, 180 if name == "P2" else 360] for name in MILESTONES}},
        "samples": results,
        "max_abs_error_by_milestone": max_by_milestone,
        "main_stack": {"max_peak_bytes": max(row["main_peak_bytes"] for row in stack_usage),
                       "per_sample": stack_usage},
        "P2_threshold_strict": THRESHOLD,
        "mcu_20_of_20": "PASS" if passed else "FAIL",
    }
    if not full_trace:
        # Keep the historical report fields for callers of the original mode.
        report["samples"] = [
            {"sample_index": row["sample_index"], "sample_id": row["sample_id"],
             "p2_max_abs_error": row["max_abs_error"]["P2"], "pass": row["P2_pass"]}
            for row in results
        ]
        report["sample0_intermediate_max_abs_error"] = {
            name: results[0]["max_abs_error"][name] for name in MILESTONES[:-1]
        }
        report["threshold_strict"] = THRESHOLD
    report_path = args.report_output.resolve() if args.report_output else repo / "device/reports/week3_mcu_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if full_trace:
        csv_path = args.csv_output.resolve()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(csv_rows)
    print(f"TENSORS: {len(tensors)}/{100 if full_trace else 24}; MCU_20_OF_20: {report['mcu_20_of_20']}")
    print(f"CAPTURE_SHA256: {report['capture_sha256']}; report={report_path}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
