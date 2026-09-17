"""Destructive-safe negative tests for Week 1 integrity gates."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mitdb_common import expected_records
from week1_common import configured_path, load_config, require, run_cli


ROOT = Path(__file__).resolve().parents[1]
MIT_VERIFIER = Path(__file__).resolve().with_name("verify_mitdb_integrity.py")
PTB_VERIFIER = Path(__file__).resolve().with_name("verify_ptbxl.py")


def make_mit_view(destination: Path, config: dict, omitted: set[str] | None = None,
                  corrupt: str | None = None) -> None:
    omitted = omitted or set()
    raw = configured_path(config, "raw_dir")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw / "SHA256SUMS.txt", destination / "SHA256SUMS.txt")
    required = [f"{record}.{extension}" for record in expected_records(config)
                for extension in config["integrity"]["required_extensions"]]
    for relative in required:
        if relative in omitted:
            continue
        source = raw / relative
        target = destination / relative
        if relative == corrupt:
            shutil.copy2(source, target)
            with target.open("ab") as handle:
                handle.write(b"negative-test-corruption")
        else:
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)


def expect_failure(command: list[str], name: str) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT.parent, text=True, capture_output=True, check=False)
    combined = result.stdout + result.stderr
    require(result.returncode != 0, f"Negative test unexpectedly returned zero: {name}")
    require("STATUS: PASS" not in combined, f"Negative test printed PASS: {name}")
    error_line = next((line for line in combined.splitlines() if "ERROR:" in line), "non-zero without ERROR line")
    return {"name": name, "exit_code": result.returncode, "evidence": error_line.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimization-modes", choices=("both", "normal"), default="both")
    args = parser.parse_args()
    _, mit_config = load_config("mitdb_week1_config.json")
    modes = [([], "python")]
    if args.optimization_modes == "both":
        modes.append((["-O"], "python-O"))
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="sv3_week1_negative_") as temporary:
        temp = Path(temporary)
        empty = temp / "empty"
        empty.mkdir()
        for flags, label in modes:
            results.append(expect_failure(
                [sys.executable, *flags, str(MIT_VERIFIER), "--raw-dir", str(empty)],
                f"mitdb_empty_directory_{label}",
            ))
            results.append(expect_failure(
                [sys.executable, *flags, str(PTB_VERIFIER), "--raw-dir", str(empty)],
                f"ptbxl_empty_directory_{label}",
            ))
        cases = {
            "missing_record": {"100.hea", "100.dat", "100.atr"},
            "missing_header": {"100.hea"},
            "missing_data": {"100.dat"},
            "missing_atr": {"100.atr"},
        }
        for case_name, omitted in cases.items():
            case_dir = temp / case_name
            make_mit_view(case_dir, mit_config, omitted=omitted)
            for flags, label in modes:
                results.append(expect_failure(
                    [sys.executable, *flags, str(MIT_VERIFIER), "--raw-dir", str(case_dir),
                     "--checksum-manifest", str(case_dir / "SHA256SUMS.txt")],
                    f"mitdb_{case_name}_{label}",
                ))
        corrupt_dir = temp / "wrong_checksum"
        make_mit_view(corrupt_dir, mit_config, corrupt="100.hea")
        for flags, label in modes:
            results.append(expect_failure(
                [sys.executable, *flags, str(MIT_VERIFIER), "--raw-dir", str(corrupt_dir),
                 "--checksum-manifest", str(corrupt_dir / "SHA256SUMS.txt")],
                f"mitdb_wrong_checksum_{label}",
            ))
    print("WEEK 1 NEGATIVE TESTS")
    for result in results:
        print(f"PASS expected failure: {result['name']} (exit={result['exit_code']})")
        print(f"  {result['evidence']}")
    print(f"Cases passed: {len(results)}/{len(results)}")
    print("Real raw datasets were not modified.")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
