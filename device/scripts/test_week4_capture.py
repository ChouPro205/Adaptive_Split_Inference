"""Reject corrupted variants of a real capture; never generate passing MCU data."""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from check_week4_capture import check


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    lines = args.capture.read_text(encoding="ascii").splitlines()
    timing_header = next((i for i, line in enumerate(lines) if line.startswith("TIMING ")), None)
    bench_sample = int(lines[timing_header].split()[1]) if timing_header is not None else None
    mixed_order = timing_header is not None
    start = next(i for i, line in enumerate(lines) if line.startswith("BEGIN "))
    first_done = next(i for i, line in enumerate(lines) if line.startswith("DONE "))
    first_tensor = next(i for i, line in enumerate(lines) if line.startswith("TENSOR "))
    first_data = first_tensor + 1
    end = next(i for i, line in enumerate(lines) if line.startswith("END "))
    # Preserve the complete valid capture for one-error mutations, so a test
    # cannot pass merely because the remaining 219 commands are absent.
    first = lines

    def replace(index: int, value: str) -> list[str]:
        changed = first.copy()
        changed[index] = value
        return changed

    fixtures = {
        "empty": [],
        "truncated_header": first[:first_tensor + 1],
        "missing_done": first[:first_done] + first[first_done + 1:],
        "wrong_sample_id": replace(start, first[start].replace("MIT-BIH", "WRONG")),
        "wrong_split": replace(first_tensor, first[first_tensor].replace(" 0 FP32 ", " 1 FP32 ")),
        "wrong_shape": replace(first_tensor, first[first_tensor].replace(" 360 360", " 359 360")),
        "malformed_hex": replace(first_data, "zzzzzzzz " + " ".join(first[first_data].split()[1:])),
        "nan": replace(first_data, "7fc00000 " + " ".join(first[first_data].split()[1:])),
        "extra_element": first[:end] + ["00000000"] + first[end:],
        "duplicate_tensor": first[:first_done] + first[first_tensor:end + 1] + first[first_done:],
        "duplicate_command": first[:first_done + 1] + first[start:first_done + 1] + first[first_done + 1:],
        "reset_banner": first[:first_done + 1] + first[:start] + first[first_done + 1:],
        "identity_one_bit": replace(first_data, f"{int(first[first_data].split()[0], 16) ^ 1:08x} " + " ".join(first[first_data].split()[1:])),
    }
    if timing_header is not None:
        cycle_index = next(i for i, line in enumerate(lines) if line.startswith("CYCLES "))
        cycles = lines[cycle_index].split()
        fixtures.update({
            "timing_zero_identity_baseline": replace(cycle_index, " ".join(cycles[:4] + ["0"])),
            "timing_missing_iteration": lines[:cycle_index] + lines[cycle_index + 1:],
            "timing_duplicate_iteration": lines[:cycle_index] + [lines[cycle_index]] + lines[cycle_index:],
            "timing_bad_cpu_clock": replace(timing_header, lines[timing_header].replace("cpu_hz=64000000", "cpu_hz=32768")),
            "timing_short_warmup": replace(timing_header, lines[timing_header].replace("warmup=20", "warmup=19")),
        })
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="negative-checker-tests-", dir=args.work_dir) as directory:
        scratch = Path(directory)
        # The source must itself pass the intended full-matrix contract.
        check(args.repo_root.resolve(), args.capture.resolve(), scratch / "real-source.json", bench_sample, mixed_order)
        for name, fixture in fixtures.items():
            capture = scratch / f"{name}.txt"
            report = scratch / f"{name}.json"
            capture.write_text("\n".join(fixture) + "\n", encoding="ascii")
            try:
                check(args.repo_root.resolve(), capture, report, bench_sample, mixed_order)
            except (ValueError, KeyError, IndexError):
                if report.exists():
                    raise ValueError("Rejected capture must not create a PASS report")
                print(f"NEGATIVE_CHECKER: PASS reject={name}")
            else:
                raise ValueError(f"Corrupt capture accepted: {name}")
    print(f"NEGATIVE_CHECKER: {len(fixtures)}/{len(fixtures)} PASS; source is real capture; no passing MCU data fabricated")


if __name__ == "__main__":
    main()
