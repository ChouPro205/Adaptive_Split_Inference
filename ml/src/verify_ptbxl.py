"""Strict PTB-XL v1.0.3 Week 1 verifier for 100 Hz 12-lead data."""

from __future__ import annotations

import argparse
from pathlib import Path

import wfdb

from ptbxl_common import canonical_records, summarize_records, validate_patient_manifest
from week1_common import (
    TEXT_HASH_POLICY,
    artifact_sha256,
    confined_dataset_path,
    config_sha256,
    configured_path,
    configured_relative_path,
    load_config,
    load_json,
    parse_physionet_checksums,
    require,
    require_raw_dir,
    run_cli,
    verify_files_against_checksums,
    verify_no_patient_leakage,
)


def verify(config_path: Path, config: dict, raw_override: str | None = None,
           manifest_override: str | None = None) -> dict:
    raw_dir = Path(raw_override).resolve() if raw_override else configured_path(config, "raw_dir")
    require_raw_dir(raw_dir)
    metadata_paths: dict[str, Path] = {}
    metadata_relatives: list[str] = []
    for key in config["integrity"]["required_metadata_path_keys"]:
        relative = configured_relative_path(config, key)
        path = confined_dataset_path(raw_dir, relative, f"configured PTB-XL path {key}")
        require(path.is_file() and path.stat().st_size > 0, f"Required PTB-XL file missing or empty: {path}")
        metadata_paths[key] = path
        metadata_relatives.append(relative)
    checksum_relative = configured_relative_path(config, "physionet_checksums")
    checksum_manifest = confined_dataset_path(raw_dir, checksum_relative, "PTB-XL checksum manifest")
    require(checksum_manifest.is_file() and checksum_manifest.stat().st_size > 0,
            f"Required PTB-XL checksum manifest missing or empty: {checksum_manifest}")

    records = canonical_records(metadata_paths["database_csv"], metadata_paths["scp_statements_csv"], config)
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
    validate_patient_manifest(manifest_path, records)

    normalization = load_json(configured_path(config, "normalization"))
    require(normalization.get("config_sha256") == config_sha256(config_path),
            "PTB-XL normalization/config hash mismatch")
    require(normalization.get("patient_manifest_sha256") == artifact_sha256(manifest_path),
            "PTB-XL normalization/patient-manifest hash mismatch")
    require(normalization.get("repository_text_hash_policy") == TEXT_HASH_POLICY,
            "PTB-XL normalization repository-text hash policy mismatch")

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

    checksums = parse_physionet_checksums(
        checksum_manifest,
        config["integrity"]["physionet_checksum_manifest_sha256"],
    )
    file_count, tree_hash = verify_files_against_checksums(
        raw_dir,
        metadata_relatives + required_waveforms,
        checksums,
    )

    signal = config["signal"]
    lead_order = list(signal["lead_order"])
    for index, stem in enumerate(stems, start=1):
        header_path = confined_dataset_path(raw_dir, stem, "PTB-XL waveform stem")
        header = wfdb.rdheader(str(header_path))
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
