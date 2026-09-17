"""Download the pinned PTB-XL v1.0.3 100 Hz subset and metadata."""

from __future__ import annotations

import argparse
import csv

from week1_common import (
    configured_path,
    download_file,
    load_config,
    parse_physionet_checksums,
    require,
    run_cli,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="ptbxl_week1_config.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    _, config = load_config(args.config)
    raw_dir = configured_path(config, "raw_dir")
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_url = config["dataset"]["source_url"].rstrip("/") + "/"
    checksum_name = configured_path(config, "physionet_checksums").name
    bootstrap = [
        ("SHA256SUMS.txt", checksum_name),
        ("LICENSE.txt", "LICENSE.txt"),
        ("ptbxl_database.csv", "ptbxl_database.csv"),
        ("scp_statements.csv", "scp_statements.csv"),
    ]
    counts = {"downloaded": 0, "kept": 0}
    print(f"PTB-XL version : {config['dataset']['version']}")
    print(f"Sampling rate  : {config['signal']['sampling_rate_hz']} Hz")
    print(f"Source         : {base_url}")
    print(f"Destination    : {raw_dir}")
    for remote_name, local_name in bootstrap:
        status = download_file(base_url + remote_name, raw_dir / local_name, args.overwrite)
        counts[status] += 1
        print(f"{status}: {local_name}")

    parse_physionet_checksums(
        raw_dir / checksum_name,
        config["integrity"]["physionet_checksum_manifest_sha256"],
    )
    database_path = raw_dir / "ptbxl_database.csv"
    with database_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == int(config["integrity"]["expected_record_count"]),
            f"Expected {config['integrity']['expected_record_count']} metadata rows, found {len(rows)}")
    column = config["signal"]["filename_column"]
    stems = [row[column].strip().replace("\\", "/") for row in rows]
    require(all(stems), f"Empty waveform path in {column}")
    relative_paths = [f"{stem}.{extension}" for stem in stems
                      for extension in config["integrity"]["required_extensions"]]
    for index, relative in enumerate(relative_paths, start=1):
        status = download_file(base_url + relative, raw_dir / relative, args.overwrite)
        counts[status] += 1
        if status == "downloaded" or index % 1000 == 0 or index == len(relative_paths):
            print(f"[{index}/{len(relative_paths)}] {status}: {relative}")
    print(f"Downloaded: {counts['downloaded']}; retained: {counts['kept']}")
    print("Download complete. Run build_ptbxl_manifest.py and verify_ptbxl.py.")


if __name__ == "__main__":
    run_cli(main)
