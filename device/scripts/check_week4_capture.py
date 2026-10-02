"""Check real Week 4 CDC capture (no serial access, no simulated MCU results)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from generate_week4_inputs import PACKAGE, WEEK4_MANIFEST, load_handoff
from generate_week3_inputs import check_inventory
from check_week3_capture import read_capture as read_week3_capture

MIXED_SEQUENCE = [(19, 10), (0, 0), (7, 8), (3, 2), (19, 1), (0, 10),
                  (12, 0), (1, 9), (18, 4), (2, 7), (14, 6), (5, 3),
                  (11, 5), (0, 2), (19, 10), (0, 0)]


def check(repo: Path, capture: Path, report: Path, bench_sample: int | None = None,
          mixed_order: bool = False) -> dict:
    _, manifest, _, _, ids = load_handoff(repo)
    old_package = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    check_inventory(old_package)
    old_report = json.loads((repo / "results/week3/week3_mcu_validation_20x5.json").read_text(encoding="utf-8"))
    old_capture = repo / "results/week3/logs/week3_capture_20x5.txt"
    if hashlib.sha256(old_capture.read_bytes()).hexdigest() != old_report["capture_sha256"] or old_report["mcu_20_of_20"] != "PASS":
        raise ValueError("Accepted Week 3 MCU P2 evidence mismatch")
    old_tensors, _ = read_week3_capture(old_capture, full_trace=True)
    expected = [(n, s, "RUN") for n in range(20) for s in range(11)]
    if mixed_order:
        expected += [(n, s, "RUN") for n, s in MIXED_SEQUENCE]
    if bench_sample is not None:
        if not 0 <= bench_sample < 20:
            raise ValueError("Timing sample outside 0..19")
        expected += [(bench_sample, s, "BENCH") for s in range(11)]
    lines = capture.read_text(encoding="ascii").splitlines()
    position = 0
    rows = []
    timing = []
    stack = []
    ready_seen = False
    def take() -> str:
        nonlocal position
        if position >= len(lines):
            raise ValueError("Truncated capture: required protocol line is missing")
        line = lines[position]
        position += 1
        return line

    for command_index, (sample, split, mode) in enumerate(expected):
        while position < len(lines) and not lines[position].startswith("BEGIN "):
            line = lines[position]
            if line.startswith("READY "):
                if ready_seen:
                    raise ValueError("Repeated READY: possible reset/reconnect during capture")
                fields = line.split()
                if fields[:4] != ["READY", "WEEK4", "R3", WEEK4_MANIFEST] or fields[4:6] != ["samples=20", "splits=11"]:
                    raise ValueError("Wrong firmware release/sample/split identity")
                if bench_sample is not None and fields[6:] != ["DWT=READY"]:
                    raise ValueError("DWT is unavailable")
                ready_seen = True
            elif line and not line.startswith("COMMAND "):
                initial_boot_banner = not ready_seen and (
                    re.fullmatch(r"\*\*\* Booting nRF Connect SDK v3\.4\.0(?:-[0-9a-f]+)? \*\*\*", line) or
                    re.fullmatch(r"\*\*\* Using Zephyr OS v4\.4\.0(?:-[0-9a-f]+)? \*\*\*", line))
                if not initial_boot_banner:
                    raise ValueError(f"Unexpected line outside command: {line}")
            position += 1
        begin = f"BEGIN {sample} {ids[sample]} {split} {mode}"
        if not ready_seen or position >= len(lines) or lines[position] != begin:
            raise ValueError(f"Missing/incorrect command envelope: {begin}")
        take()
        cycles = []
        if mode == "BENCH":
            fields = take().split()
            if fields[:4] != ["TIMING", str(sample), ids[sample], str(split)]:
                raise ValueError("Timing identity mismatch")
            metadata = dict(field.split("=", 1) for field in fields[4:])
            if int(metadata["warmup"]) < 20 or int(metadata["measured"]) != 100 or int(metadata["cpu_hz"]) != 64000000 or metadata["irq"] != "locked" or metadata["baseline"] != "raw":
                raise ValueError("Invalid timing metadata")
            for index in range(100):
                fields = take().split()
                if fields[:4] != ["CYCLES", str(sample), str(split), str(index)] or len(fields) != 5:
                    raise ValueError("Missing/duplicate/misordered timing iteration")
                cycles.append(int(fields[4]))
                if not 0 < cycles[-1] <= 0xFFFFFFFF:
                    raise ValueError("Cycle count must be a measured positive uint32, including s=0")
            timing.append({"sample_index": sample, "sample_id": ids[sample], "split": split,
                           "warmup": int(metadata["warmup"]), "cpu_hz": int(metadata["cpu_hz"]),
                           "cycles": cycles, "min_cycles": min(cycles), "max_cycles": max(cycles),
                           "mean_cycles": sum(cycles) / 100,
                           "mean_ms": sum(cycles) / 100 / int(metadata["cpu_hz"]) * 1000})
        contract = manifest["splits"][split]
        shape = contract["shape_N1"]
        count = math.prod(shape)
        tensor = f"TENSOR {sample} {ids[sample]} {split} FP32 {contract['layout']} {len(shape)} " + " ".join(map(str, shape)) + f" {count}"
        if take() != tensor:
            raise ValueError(f"Tensor ID/shape/layout/count mismatch n={sample} s={split}")
        words = []
        while position < len(lines) and not lines[position].startswith("END "):
            row = lines[position].split()
            if not row or len(row) > 16 or any(re.fullmatch(r"[0-9a-fA-F]{8}", word) is None for word in row):
                raise ValueError("Malformed FP32 hex line")
            words.extend(row)
            position += 1
        if position >= len(lines) or lines[position] != f"END {sample} {split}" or len(words) != count:
            raise ValueError("Truncated/wrong tensor footer/count")
        take()
        actual = np.array([int(word, 16) for word in words], dtype=np.uint32).view(np.float32).reshape(shape)
        golden = np.load(repo / PACKAGE / contract["golden_path"], allow_pickle=False)[sample:sample + 1]
        if not np.isfinite(actual).all() or actual.shape != golden.shape:
            raise ValueError("Non-finite/invalid shape")
        error = float(np.max(np.abs(actual.astype(np.float64) - golden.astype(np.float64))))
        if not error < 1e-3:
            raise ValueError(f"MCU tolerance failed n={sample} s={split}: {error}")
        compatibility = {}
        if split == 0:
            if not np.array_equal(actual.view(np.uint32), golden.view(np.uint32)):
                raise ValueError("s=0 identity must preserve input FP32 bits")
            compatibility["identity_bitwise"] = True
        if split == 2:
            previous = old_tensors[(sample, "P2")]
            p2_error = float(np.max(np.abs(actual.astype(np.float64) - previous.astype(np.float64))))
            if not p2_error < 1e-3:
                raise ValueError("s=2 differs from accepted Week 3 MCU P2")
            compatibility["week3_mcu_p2_max_abs_error"] = p2_error
            compatibility["week3_mcu_p2_bitwise"] = bool(np.array_equal(actual.view(np.uint32), previous.view(np.uint32)))
        if position < len(lines) and lines[position].startswith("STACK "):
            metadata = dict(field.split("=", 1) for field in lines[position].split()[1:])
            peak, size = int(metadata["main_peak_bytes"]), int(metadata["main_size_bytes"])
            if not 0 <= peak <= size:
                raise ValueError("Invalid measured stack high-water")
            stack.append({"sample": sample, "split": split, "peak_bytes": peak, "size_bytes": size})
            position += 1
        if take() != f"DONE {sample} {split} {mode}":
            raise ValueError("Missing/mismatched DONE")
        rows.append({"sample_index": sample, "sample_id": ids[sample], "split": split, "mode": mode,
                     "phase": "primary" if command_index < 220 else ("timing" if mode == "BENCH" else "mixed"),
                     "shape": shape, "max_abs_error": error, "status": "PASS", **compatibility})
    if any(line for line in lines[position:]):
        raise ValueError("Unexpected commands/trailing capture data")
    result = {"scope": "REAL_MCU_CAPTURE", "status": "PASS", "manifest_sha256": WEEK4_MANIFEST,
              "capture": str(capture), "threshold_strict": 1e-3, "run_tensors": 220,
              "capture_sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
              "mixed_tensors": len(MIXED_SEQUENCE) if mixed_order else 0,
              "week3_mcu_capture_sha256": old_report["capture_sha256"],
              "mcu_validation": "PASS", "mcu_timing": "PASS" if len(timing) == 11 else "PENDING",
              "rows": rows, "timing": timing, "stack_high_water": stack}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--bench-sample", type=int)
    parser.add_argument("--mixed-order", action="store_true")
    args = parser.parse_args()
    result = check(args.repo_root.resolve(), args.capture.resolve(), args.report.resolve(), args.bench_sample,
                   args.mixed_order)
    print(f"MCU_220_OF_220: {result['status']}; timing={result['mcu_timing']}; report={args.report}")
