"""Download the pinned PTB-XL v1.0.3 100 Hz subset and metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

from ptbxl_common import canonical_records, summarize_records

from week1_common import (
    confined_dataset_path,
    configured_path,
    configured_relative_path,
    download_file,
    load_config,
    parse_physionet_checksums,
    require,
    run_cli,
    safe_dataset_relative_path,
    sha256_file,
    verify_files_against_checksums,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="ptbxl_week1_config.json")
    parser.add_argument("--raw-dir", help="Override raw directory (primarily for isolated verification)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    _, config = load_config(args.config)
    raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else configured_path(config, "raw_dir")
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_url = config["dataset"]["source_url"].rstrip("/") + "/"
    counts = {"downloaded": 0, "kept": 0}
    print(f"PTB-XL version : {config['dataset']['version']}")
    print(f"Sampling rate  : {config['signal']['sampling_rate_hz']} Hz")
    print(f"Source         : {base_url}")
    print(f"Destination    : {raw_dir}")

    checksum_relative = configured_relative_path(config, "physionet_checksums")
    checksum_destination = confined_dataset_path(raw_dir, checksum_relative, "checksum manifest path")
    checksum_remote = safe_dataset_relative_path(
        config["acquisition"]["checksum_manifest_remote_path"], "remote checksum manifest path"
    )
    status = download_file(base_url + checksum_remote, checksum_destination, args.overwrite)
    counts[status] += 1
    print(f"{status}: {checksum_relative}")
    checksums = parse_physionet_checksums(
        checksum_destination,
        config["integrity"]["physionet_checksum_manifest_sha256"],
    )

    metadata_keys = list(config["integrity"]["required_metadata_path_keys"])
    remote_metadata = config["acquisition"]["metadata_remote_paths"]
    require(set(remote_metadata) == set(metadata_keys),
            "PTB-XL metadata acquisition keys differ from integrity config")
    metadata_relatives: list[str] = []
    for key in metadata_keys:
        local_relative = configured_relative_path(config, key)
        remote_relative = safe_dataset_relative_path(remote_metadata[key], f"remote path for {key}")
        destination = confined_dataset_path(raw_dir, local_relative, f"local path for {key}")
        status = download_file(base_url + remote_relative, destination, args.overwrite)
        counts[status] += 1
        metadata_relatives.append(local_relative)
        print(f"{status}: {local_relative}")

    metadata_count, _ = verify_files_against_checksums(
        raw_dir, metadata_relatives, checksums
    )
    print(f"Metadata checksummed before parsing: {metadata_count}")

    database_path = confined_dataset_path(
        raw_dir, configured_relative_path(config, "database_csv"), "PTB-XL database path"
    )
    scp_path = confined_dataset_path(
        raw_dir, configured_relative_path(config, "scp_statements_csv"), "SCP vocabulary path"
    )
    records = canonical_records(database_path, scp_path, config)
    require(len(records) == int(config["integrity"]["expected_record_count"]),
            f"Expected {config['integrity']['expected_record_count']} metadata rows, found {len(records)}")
    patients = {str(record["patient_id"]) for record in records}
    require(len(patients) == int(config["integrity"]["expected_patient_count"]),
            f"Unexpected PTB-XL patient count: {len(patients)}")
    require(summarize_records(records) == config["expected_split"],
            "PTB-XL split counts differ from config")
    stems = [str(record["waveform_path"]) for record in records]
    extensions = [safe_dataset_relative_path(extension, "waveform extension")
                  for extension in config["integrity"]["required_extensions"]]
    require(all("/" not in extension for extension in extensions), "Waveform extensions must be single components")
    relative_paths = [f"{stem}.{extension}" for stem in stems
                      for extension in extensions]
    for index, relative in enumerate(relative_paths, start=1):
        safe_relative = safe_dataset_relative_path(relative, "waveform file path")
        require(safe_relative in checksums,
                f"Official checksum missing for required waveform: {safe_relative}")
        destination = confined_dataset_path(raw_dir, safe_relative, "waveform destination")
        status = download_file(base_url + safe_relative, destination, args.overwrite)
        counts[status] += 1
        actual_hash = sha256_file(destination)
        require(actual_hash == checksums[safe_relative],
                f"Checksum mismatch for {safe_relative}: expected {checksums[safe_relative]}, got {actual_hash}")
        if status == "downloaded" or index % 1000 == 0 or index == len(relative_paths):
            print(f"[{index}/{len(relative_paths)}] {status} and verified: {safe_relative}")
    print(f"Downloaded: {counts['downloaded']}; retained: {counts['kept']}")
    print(f"Verified cached/downloaded waveforms: {len(relative_paths)}")
    print("Download and checksum verification complete. Run build_ptbxl_manifest.py and verify_ptbxl.py.")


if __name__ == "__main__":
    run_cli(main)
