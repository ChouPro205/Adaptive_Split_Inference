"""Strict PTB-XL v1.0.3 Week 1 verifier for 100 Hz 12-lead data."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import wfdb

from ptbxl_common import canonical_records, summarize_records
from week1_common import (
    config_sha256,
    configured_path,
    load_config,
    load_json,
    parse_physionet_checksums,
    read_csv_rows,
    require,
    require_raw_dir,
    run_cli,
    sha256_file,
    verify_files_against_checksums,
    verify_no_patient_leakage,
)


def verify(config_path: Path, config: dict, raw_override: str | None = None,
           manifest_override: str | None = None) -> dict:
    raw_dir = Path(raw_override).resolve() if raw_override else configured_path(config, "raw_dir")
    require_raw_dir(raw_dir)
    for filename in config["integrity"]["required_top_level_files"]:
        path = raw_dir / filename
        require(path.is_file() and path.stat().st_size > 0, f"Required PTB-XL file missing or empty: {path}")

    records = canonical_records(raw_dir / "ptbxl_database.csv", raw_dir / "scp_statements.csv", config)
    expected_records = int(config["integrity"]["expected_record_count"])
    require(len(records) == expected_records,
            f"Expected {expected_records} PTB-XL records, found {len(records)}")
    patients = {str(record["patient_id"]) for record in records}
    require(len(patients) == int(config["integrity"]["expected_patient_count"]),
            f"Unexpected patient count: {len(patients)}")
    summary = summarize_records(records)
    require(summary == config["expected_split"],
            f"Split counts differ from config: expected {config['expected_split']}, got {summary}")

    split_patients = {split: set() for split in ("train", "val", "test")}
    for record in records:
        split_patients[str(record["split"])].add(str(record["patient_id"]))
    verify_no_patient_leakage(split_patients)

    manifest_path = Path(manifest_override).resolve() if manifest_override else configured_path(config, "patient_manifest")
    manifest_rows = read_csv_rows(manifest_path)
    require(len(manifest_rows) == len(records),
            f"PTB-XL manifest row count mismatch: {len(manifest_rows)} vs {len(records)}")
    expected_by_id = {str(record["ecg_id"]): record for record in records}
    require(len(expected_by_id) == len(records), "Duplicate ecg_id in canonical PTB-XL records")
    for row in manifest_rows:
        ecg_id = row.get("ecg_id", "")
        require(ecg_id in expected_by_id, f"Unexpected ecg_id in PTB-XL manifest: {ecg_id}")
        expected = expected_by_id[ecg_id]
        for field in ("patient_id", "split", "waveform_path", "scp_codes"):
            require(row.get(field) == str(expected[field]),
                    f"PTB-XL manifest mismatch for ecg_id={ecg_id}, field={field}")
        require(int(row["strat_fold"]) == int(expected["strat_fold"]),
                f"PTB-XL fold mismatch for ecg_id={ecg_id}")
        require(int(row["label_count"]) == int(expected["label_count"]),
                f"PTB-XL label count mismatch for ecg_id={ecg_id}")

    normalization = load_json(configured_path(config, "normalization"))
    require(normalization.get("config_sha256") == config_sha256(config_path),
            "PTB-XL normalization/config hash mismatch")
    require(normalization.get("patient_manifest_sha256") == sha256_file(manifest_path),
            "PTB-XL normalization/patient-manifest hash mismatch")

    stems = [str(record["waveform_path"]) for record in records]
    required_waveforms = [f"{stem}.{extension}" for stem in stems
                          for extension in config["integrity"]["required_extensions"]]
    expected_headers = {f"{stem}.hea" for stem in stems}
    expected_data = {f"{stem}.dat" for stem in stems}
    selected_roots = {Path(stem).parts[0] for stem in stems}
    require(len(selected_roots) == 1, f"Expected one configured waveform root, got {selected_roots}")
    actual_headers = {relative.as_posix() for path in raw_dir.rglob("*.hea")
                      if path.is_file() and (relative := path.relative_to(raw_dir)).parts[0] in selected_roots}
    actual_data = {relative.as_posix() for path in raw_dir.rglob("*.dat")
                   if path.is_file() and (relative := path.relative_to(raw_dir)).parts[0] in selected_roots}
    require(actual_headers == expected_headers,
            f"PTB-XL header set mismatch: missing={len(expected_headers - actual_headers)}, "
            f"unexpected={len(actual_headers - expected_headers)}")
    require(actual_data == expected_data,
            f"PTB-XL data set mismatch: missing={len(expected_data - actual_data)}, "
            f"unexpected={len(actual_data - expected_data)}")

    signal = config["signal"]
    lead_order = list(signal["lead_order"])
    for index, stem in enumerate(stems, start=1):
        header = wfdb.rdheader(str(raw_dir / stem))
        require(float(header.fs) == float(signal["sampling_rate_hz"]),
                f"{stem}: expected {signal['sampling_rate_hz']} Hz, got {header.fs}")
        require(int(header.sig_len) == int(signal["sample_count"]),
                f"{stem}: expected {signal['sample_count']} samples, got {header.sig_len}")
        require(int(header.n_sig) == int(signal["lead_count"]),
                f"{stem}: expected {signal['lead_count']} leads, got {header.n_sig}")
        require(list(header.sig_name) == lead_order,
                f"{stem}: unexpected lead order {header.sig_name}")
        if index % 5000 == 0:
            print(f"Headers checked: {index}/{len(stems)}")

    checksum_manifest = raw_dir / configured_path(config, "physionet_checksums").name
    checksums = parse_physionet_checksums(
        checksum_manifest,
        config["integrity"]["physionet_checksum_manifest_sha256"],
    )
    required_top = [name for name in config["integrity"]["required_top_level_files"]
                    if name != checksum_manifest.name]
    file_count, tree_hash = verify_files_against_checksums(
        raw_dir,
        required_top + required_waveforms,
        checksums,
    )
    return {
        "records": len(records),
        "patients": len(patients),
        "summary": summary,
        "labels": sum(int(record["label_count"]) for record in records),
        "files": file_count,
        "tree_sha256": tree_hash,
        "config_sha256": config_sha256(config_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="ptbxl_week1_config.json")
    parser.add_argument("--raw-dir")
    parser.add_argument("--manifest")
    args = parser.parse_args()
    config_path, config = load_config(args.config)
    result = verify(config_path, config, args.raw_dir, args.manifest)
    print("PTB-XL VERIFICATION")
    print(f"Version             : {config['dataset']['version']}")
    print(f"Sampling rate       : {config['signal']['sampling_rate_hz']} Hz")
    print(f"Signal shape        : ({config['signal']['sample_count']}, {config['signal']['lead_count']})")
    print(f"Lead order          : {config['signal']['lead_order']}")
    print(f"Records / patients  : {result['records']} / {result['patients']}")
    for split, counts in result["summary"].items():
        print(f"{split:5s}                : {counts['records']} records / {counts['patients']} patients")
    print(f"SCP label assignments: {result['labels']}")
    print(f"Files checksummed    : {result['files']}")
    print(f"File tree SHA-256    : {result['tree_sha256']}")
    print(f"Config SHA-256       : {result['config_sha256']}")
    print("Patient leakage      : none")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
