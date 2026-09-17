"""Strict MIT-BIH v1.0.0 completeness and SHA-256 verification."""

from __future__ import annotations

import argparse
from pathlib import Path

from week1_common import (
    config_sha256,
    configured_path,
    load_config,
    load_expected_records,
    parse_physionet_checksums,
    require,
    require_raw_dir,
    run_cli,
    verify_files_against_checksums,
)


def verify(config_path: Path, config: dict, raw_override: str | None = None,
           checksum_override: str | None = None) -> dict:
    raw_dir = Path(raw_override).resolve() if raw_override else configured_path(config, "raw_dir")
    checksum_name = configured_path(config, "physionet_checksums").name
    checksum_path = Path(checksum_override).resolve() if checksum_override else raw_dir / checksum_name
    require_raw_dir(raw_dir)

    integrity = config["integrity"]
    records = load_expected_records(
        configured_path(config, "expected_records"),
        int(integrity["expected_record_count"]),
    )
    extensions = list(integrity["required_extensions"])
    require(extensions == ["hea", "dat", "atr"], "MIT-BIH required extensions must be hea/dat/atr")

    actual_headers = {path.stem for path in raw_dir.glob("*.hea")}
    expected = set(records)
    require(actual_headers == expected,
            f"MIT-BIH record list mismatch; missing={sorted(expected - actual_headers)}, "
            f"unexpected={sorted(actual_headers - expected)}")

    required = [f"{record}.{extension}" for record in records for extension in extensions]
    checksums = parse_physionet_checksums(
        checksum_path,
        integrity["physionet_checksum_manifest_sha256"],
    )
    checked_count, tree_hash = verify_files_against_checksums(raw_dir, required, checksums)
    require(checked_count == len(records) * len(extensions), "Not all MIT-BIH files were verified")
    return {
        "records": len(records),
        "files": checked_count,
        "tree_sha256": tree_hash,
        "checksum_manifest_sha256": integrity["physionet_checksum_manifest_sha256"],
        "config_sha256": config_sha256(config_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mitdb_week1_config.json")
    parser.add_argument("--raw-dir")
    parser.add_argument("--checksum-manifest")
    args = parser.parse_args()
    config_path, config = load_config(args.config)
    result = verify(config_path, config, args.raw_dir, args.checksum_manifest)
    print("MIT-BIH INTEGRITY")
    print(f"Version                   : {config['dataset']['version']}")
    print(f"Records verified          : {result['records']}")
    print(f"Files verified            : {result['files']}")
    print(f"Official manifest SHA-256 : {result['checksum_manifest_sha256']}")
    print(f"Required-file tree SHA-256: {result['tree_sha256']}")
    print(f"Config SHA-256            : {result['config_sha256']}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
