"""Destructive-safe negative tests for Week 1 integrity gates."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mitdb_common import expected_records
from ptbxl_common import canonical_records
from week1_common import (
    artifact_sha256,
    confined_dataset_path,
    config_sha256,
    configured_path,
    configured_relative_path,
    load_config,
    require,
    run_cli,
)


ROOT = Path(__file__).resolve().parents[1]
MIT_VERIFIER = Path(__file__).resolve().with_name("verify_mitdb_integrity.py")
PTB_VERIFIER = Path(__file__).resolve().with_name("verify_ptbxl.py")
PTB_DOWNLOADER = Path(__file__).resolve().with_name("download_ptbxl.py")


def link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


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
            link_or_copy(source, target)


def make_ptb_view(destination: Path, config: dict) -> str:
    raw = configured_path(config, "raw_dir")
    destination.mkdir(parents=True, exist_ok=True)
    relatives = [configured_relative_path(config, "physionet_checksums")]
    relatives.extend(configured_relative_path(config, key)
                     for key in config["integrity"]["required_metadata_path_keys"])
    records = canonical_records(
        configured_path(config, "database_csv"),
        configured_path(config, "scp_statements_csv"),
        config,
    )
    require(len(records) == int(config["integrity"]["expected_record_count"]),
            "Cannot construct PTB-XL negative-test view from incomplete source data")
    extensions = list(config["integrity"]["required_extensions"])
    relatives.extend(f"{record['waveform_path']}.{extension}"
                     for record in records for extension in extensions)
    for relative in relatives:
        source = confined_dataset_path(raw, relative, "PTB-XL negative-test source")
        target = confined_dataset_path(destination, relative, "PTB-XL negative-test target")
        require(source.is_file(), f"PTB-XL negative-test source file is missing: {source}")
        link_or_copy(source, target)
    return str(records[0]["waveform_path"])


def restore_ptb_file(raw: Path, view: Path, relative: str) -> None:
    target = confined_dataset_path(view, relative, "PTB-XL negative-test restore target")
    if target.exists():
        target.unlink()
    source = confined_dataset_path(raw, relative, "PTB-XL negative-test restore source")
    link_or_copy(source, target)


def make_corrupt_ptb_metadata_view(destination: Path, config: dict) -> None:
    raw = configured_path(config, "raw_dir")
    destination.mkdir(parents=True, exist_ok=True)
    keys = ["physionet_checksums", *config["integrity"]["required_metadata_path_keys"]]
    for key in keys:
        relative = configured_relative_path(config, key)
        source = confined_dataset_path(raw, relative, "PTB-XL metadata negative-test source")
        target = confined_dataset_path(destination, relative, "PTB-XL metadata negative-test target")
        if key == "database_csv":
            shutil.copy2(source, target)
            with target.open("ab") as handle:
                handle.write(b"negative-test-metadata-corruption")
        else:
            link_or_copy(source, target)


def make_ptb_manifest_mutations(
    directory: Path, config: dict,
) -> list[tuple[str, Path, str]]:
    source = configured_path(config, "patient_manifest")
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None, "PTB-XL manifest has no header")
        rows = list(reader)
        fields = list(reader.fieldnames)
    expected_count = int(config["integrity"]["expected_record_count"])
    require(len(rows) == expected_count,
            "PTB-XL source manifest is incomplete before negative-test mutation")
    require(len(rows) >= 2, "PTB-XL manifest is too small for ID mutation")

    def write(name: str, mutated_rows: list[dict[str, str]]) -> Path:
        destination = directory / f"ptbxl_manifest_{name}.csv"
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(mutated_rows)
        return destination

    duplicated_id = rows[0]["ecg_id"]
    missing_id = rows[-1]["ecg_id"]
    duplicate_missing_rows = [dict(row) for row in rows]
    duplicate_missing_rows[-1] = dict(rows[0])

    foreign_id = "999999999"
    require(all(row["ecg_id"] != foreign_id for row in rows),
            f"Chosen foreign PTB-XL ecg_id unexpectedly exists: {foreign_id}")
    foreign_missing_rows = [dict(row) for row in rows]
    foreign_missing_rows[-1]["ecg_id"] = foreign_id

    return [
        ("header_only", write("header_only", []), "CSV contains no data rows"),
        ("missing_row", write("missing_row", rows[:-1]),
         f"PTB-XL manifest row count mismatch: {expected_count - 1} vs {expected_count}"),
        ("extra_row", write("extra_row", [*rows, dict(rows[-1])]),
         f"PTB-XL manifest row count mismatch: {expected_count + 1} vs {expected_count}"),
        (f"duplicate_{duplicated_id}_missing_{missing_id}",
         write("duplicate_missing_id", duplicate_missing_rows),
         "Duplicate ecg_id values in PTB-XL manifest"),
        (f"foreign_{foreign_id}_missing_{missing_id}",
         write("foreign_missing_id", foreign_missing_rows),
         "PTB-XL manifest ecg_id set mismatch"),
    ]


def verify_line_ending_hash_stability(directory: Path) -> list[str]:
    checks: list[str] = []
    for config_name in ("environment.json", "mitdb_week1_config.json", "ptbxl_week1_config.json"):
        source, _ = load_config(config_name)
        converted = directory / f"crlf_{config_name}"
        text = source.read_text(encoding="utf-8")
        converted.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("utf-8"))
        require(config_sha256(source) == config_sha256(converted),
                f"Config hash changes with line endings: {config_name}")
        checks.append(f"config_eol_{config_name}")
    _, ptb_config = load_config("ptbxl_week1_config.json")
    manifest = configured_path(ptb_config, "patient_manifest")
    converted_manifest = directory / "crlf_ptbxl_patient_split.csv"
    text = manifest.read_text(encoding="utf-8")
    converted_manifest.write_bytes(
        text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("utf-8")
    )
    require(artifact_sha256(manifest) == artifact_sha256(converted_manifest),
            "PTB-XL manifest artifact hash changes with line endings")
    checks.append("artifact_eol_ptbxl_patient_manifest")
    return checks


def expect_failure(command: list[str], name: str,
                   expected_error: str | None = None) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT.parent, text=True, capture_output=True, check=False)
    combined = result.stdout + result.stderr
    require(result.returncode != 0, f"Negative test unexpectedly returned zero: {name}")
    require("STATUS: PASS" not in combined, f"Negative test printed PASS: {name}")
    if expected_error is not None:
        require(expected_error in combined,
                f"Negative test failed for the wrong reason: {name}; "
                f"expected error containing {expected_error!r}")
    error_line = next((line for line in combined.splitlines() if "ERROR:" in line), "non-zero without ERROR line")
    return {"name": name, "exit_code": result.returncode, "evidence": error_line.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimization-modes", choices=("both", "normal"), default="both")
    args = parser.parse_args()
    _, mit_config = load_config("mitdb_week1_config.json")
    _, ptb_config = load_config("ptbxl_week1_config.json")
    modes = [([], "python")]
    if args.optimization_modes == "both":
        modes.append((["-O"], "python-O"))
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="sv3_week1_negative_") as temporary:
        temp = Path(temporary)
        hash_checks = verify_line_ending_hash_stability(temp)
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

        corrupt_metadata = temp / "ptbxl_corrupt_cached_metadata"
        make_corrupt_ptb_metadata_view(corrupt_metadata, ptb_config)
        for flags, label in modes:
            results.append(expect_failure(
                [sys.executable, *flags, str(PTB_DOWNLOADER), "--raw-dir", str(corrupt_metadata)],
                f"ptbxl_corrupt_cached_metadata_{label}",
            ))

        manifest_mutations = make_ptb_manifest_mutations(temp, ptb_config)
        for mutation_name, corrupt_manifest, expected_error in manifest_mutations:
            for flags, label in modes:
                results.append(expect_failure(
                    [sys.executable, *flags, str(PTB_VERIFIER),
                     "--manifest", str(corrupt_manifest)],
                    f"ptbxl_manifest_{mutation_name}_{label}",
                    expected_error=expected_error,
                ))

        ptb_view = temp / "ptbxl_view"
        first_stem = make_ptb_view(ptb_view, ptb_config)
        ptb_raw = configured_path(ptb_config, "raw_dir")
        ptb_cases = {
            "missing_header": [f"{first_stem}.hea"],
            "missing_data": [f"{first_stem}.dat"],
            "missing_record": [f"{first_stem}.hea", f"{first_stem}.dat"],
        }
        for case_name, omitted in ptb_cases.items():
            for relative in omitted:
                confined_dataset_path(ptb_view, relative, "PTB-XL omitted test file").unlink()
            for flags, label in modes:
                results.append(expect_failure(
                    [sys.executable, *flags, str(PTB_VERIFIER), "--raw-dir", str(ptb_view)],
                    f"ptbxl_{case_name}_{label}",
                ))
            for relative in omitted:
                restore_ptb_file(ptb_raw, ptb_view, relative)

        corrupt_relative = f"{first_stem}.dat"
        corrupt_target = confined_dataset_path(ptb_view, corrupt_relative, "PTB-XL corrupt test file")
        corrupt_target.unlink()
        shutil.copy2(confined_dataset_path(ptb_raw, corrupt_relative), corrupt_target)
        with corrupt_target.open("ab") as handle:
            handle.write(b"negative-test-corruption")
        for flags, label in modes:
            results.append(expect_failure(
                [sys.executable, *flags, str(PTB_VERIFIER), "--raw-dir", str(ptb_view)],
                f"ptbxl_wrong_checksum_{label}",
            ))
        restore_ptb_file(ptb_raw, ptb_view, corrupt_relative)
    print("WEEK 1 NEGATIVE TESTS")
    for check in hash_checks:
        print(f"PASS line-ending-stable hash: {check}")
    for result in results:
        print(f"PASS expected failure: {result['name']} (exit={result['exit_code']})")
        print(f"  {result['evidence']}")
    print(f"Cases passed: {len(results)}/{len(results)}")
    print("Real raw datasets were not modified.")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
