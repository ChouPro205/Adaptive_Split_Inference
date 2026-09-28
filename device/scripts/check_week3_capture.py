"""Validate full USB CDC FP32 tensors against v2 golden by sample_id."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

from generate_week3_inputs import TRUSTED_MANIFEST, check_inventory, sha256

COUNTS = {"M1": 5760, "R1": 5760, "M2": 5760, "R2": 5760, "P2": 2880}


def parse_capture(path: Path) -> dict[tuple[int, str], np.ndarray]:
    tensors = {}
    lines = iter(path.read_text(encoding="ascii").splitlines())
    for line in lines:
        if not line.startswith("TENSOR "):
            continue
        match = re.fullmatch(r"TENSOR (\d+) (M1|R1|M2|R2|P2) (\d+)", line)
        if match is None:
            raise ValueError(f"Malformed TENSOR header: {line}")
        sample, milestone, count = int(match[1]), match[2], int(match[3])
        if sample not in range(20) or count != COUNTS[milestone] or (sample, milestone) in tensors:
            raise ValueError(f"Invalid or duplicate tensor: {line}")
        words = []
        for data_line in lines:
            if data_line == f"END {milestone}":
                break
            parts = data_line.split()
            if not all(re.fullmatch(r"[0-9a-f]{8}", part) for part in parts):
                raise ValueError(f"Invalid FP32 bit pattern in {milestone} sample {sample}")
            words.extend(int(part, 16) for part in parts)
        else:
            raise ValueError(f"Missing END {milestone} for sample {sample}")
        if len(words) != count:
            raise ValueError(f"{milestone} sample {sample}: expected {count} elements, got {len(words)}")
        tensor = np.asarray(words, dtype="<u4").view("<f4")
        if not np.isfinite(tensor).all():
            raise ValueError(f"Non-finite tensor: {milestone} sample {sample}")
        tensors[(sample, milestone)] = tensor.reshape(16, 180 if milestone == "P2" else 360)
    return tensors


def parse_stack_usage(path: Path) -> list[dict[str, int]]:
    """Check command framing and extract Zephyr main-thread high-water marks."""
    measurements = []
    active = None
    stack = None
    for line in path.read_text(encoding="ascii").splitlines():
        begin = re.fullmatch(r"BEGIN (\d+) (TRACE|RUN)", line)
        if begin:
            sample = int(begin[1])
            if active is not None or sample != len(measurements) or begin[2] != ("TRACE" if sample == 0 else "RUN"):
                raise ValueError(f"Unexpected BEGIN: {line}")
            active, stack = sample, None
            continue
        if line.startswith("STACK "):
            match = re.fullmatch(r"STACK main_peak_bytes=(\d+) main_size_bytes=(\d+)", line)
            if match is None or active is None or stack is not None:
                raise ValueError(f"Invalid stack measurement: {line}")
            peak, size = int(match[1]), int(match[2])
            if size <= 0 or peak > size:
                raise ValueError(f"Invalid stack bounds: {line}")
            stack = {"sample_index": active, "main_peak_bytes": peak, "main_size_bytes": size}
            continue
        if line.startswith("DONE "):
            if active is None or line != f"DONE {active}" or stack is None:
                raise ValueError(f"Unexpected DONE or missing STACK: {line}")
            measurements.append(stack)
            active, stack = None, None
    if active is not None or len(measurements) != 20:
        raise ValueError(f"Incomplete command/stack sequence: {len(measurements)}/20")
    return measurements


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    package = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    check_inventory(package)
    with (package / "samples.csv").open(encoding="utf-8", newline="") as stream:
        samples = list(csv.DictReader(stream))
    if len(samples) != 20 or [int(row["sample_index"]) for row in samples] != list(range(20)):
        raise ValueError("Invalid v2 sample index mapping")
    tensors = parse_capture(args.capture.resolve())
    stack_usage = parse_stack_usage(args.capture.resolve())
    required = {(sample, "P2") for sample in range(20)} | {(0, name) for name in COUNTS}
    if set(tensors) != required:
        raise ValueError(f"Missing={sorted(required-set(tensors))}; extra={sorted(set(tensors)-required)}")
    results = []
    for sample, row in enumerate(samples):
        golden = np.load(package / "golden/P2.npy", allow_pickle=False)[sample]
        error = float(np.max(np.abs(tensors[(sample, "P2")].astype(np.float64) - golden.astype(np.float64))))
        results.append({"sample_index": sample, "sample_id": row["sample_id"], "p2_max_abs_error": error,
                        "pass": error < 1e-3})
        print(f"{row['sample_id']}: P2 max_abs_error={error:.9g} {'PASS' if error < 1e-3 else 'FAIL'}")
    intermediate = {}
    for name in ("M1", "R1", "M2", "R2"):
        golden = np.load(package / "golden" / f"{name}.npy", allow_pickle=False)[0]
        intermediate[name] = float(np.max(np.abs(tensors[(0, name)].astype(np.float64) - golden.astype(np.float64))))
        print(f"sample 0 {name}: max_abs_error={intermediate[name]:.9g}")
    passed = all(row["pass"] for row in results)
    max_stack_peak = max(row["main_peak_bytes"] for row in stack_usage)
    print(f"MAIN_STACK_PEAK: {max_stack_peak}/{stack_usage[0]['main_size_bytes']} bytes")
    report = {"handoff_id": package.name, "manifest_sha256": TRUSTED_MANIFEST,
              "capture_sha256": sha256(args.capture.resolve()), "samples": results,
              "sample0_intermediate_max_abs_error": intermediate,
              "main_stack": {"max_peak_bytes": max_stack_peak, "per_sample": stack_usage},
              "threshold_strict": 1e-3, "mcu_20_of_20": "PASS" if passed else "FAIL"}
    report_path = repo / "device/reports/week3_mcu_validation.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MCU_20_OF_20: {report['mcu_20_of_20']}; report={report_path}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
