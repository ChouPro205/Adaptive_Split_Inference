"""Reproducibly download the pinned MIT-BIH v1.0.0 Week 1 files."""

from __future__ import annotations

import argparse

from week1_common import (
    configured_path,
    download_file,
    load_config,
    load_expected_records,
    run_cli,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mitdb_week1_config.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    _, config = load_config(args.config)
    raw_dir = configured_path(config, "raw_dir")
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_url = config["dataset"]["source_url"].rstrip("/") + "/"
    records = load_expected_records(
        configured_path(config, "expected_records"),
        int(config["integrity"]["expected_record_count"]),
    )
    checksum_name = configured_path(config, "physionet_checksums").name
    relative_paths = [checksum_name]
    relative_paths.extend(
        f"{record}.{extension}"
        for record in records
        for extension in config["integrity"]["required_extensions"]
    )
    counts = {"downloaded": 0, "kept": 0}
    print(f"MIT-BIH version : {config['dataset']['version']}")
    print(f"Source          : {base_url}")
    print(f"Destination     : {raw_dir}")
    for index, relative in enumerate(relative_paths, start=1):
        status = download_file(base_url + relative, raw_dir / relative, args.overwrite)
        counts[status] += 1
        if status == "downloaded" or index % 25 == 0 or index == len(relative_paths):
            print(f"[{index}/{len(relative_paths)}] {status}: {relative}")
    print(f"Downloaded: {counts['downloaded']}; retained: {counts['kept']}")
    print("Download complete. Run verify_mitdb_integrity.py before preprocessing.")


if __name__ == "__main__":
    run_cli(main)
