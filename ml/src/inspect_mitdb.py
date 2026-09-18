"""Inspect the pinned MIT-BIH records and lead layout."""

from __future__ import annotations

from collections import Counter

import wfdb

from mitdb_common import validate_raw_files
from week1_common import config_sha256, load_config, require, run_cli


def main() -> None:
    config_path, config = load_config("mitdb_week1_config.json")
    raw_dir, records = validate_raw_files(config)
    lead = config["lead"]["preferred"]
    rates: Counter[float] = Counter()
    lengths: Counter[int] = Counter()
    combinations: Counter[tuple[str, ...]] = Counter()
    missing: list[str] = []
    nonzero: list[tuple[str, int]] = []
    for record_id in records:
        header = wfdb.rdheader(str(raw_dir / record_id))
        rates[float(header.fs)] += 1
        lengths[int(header.sig_len)] += 1
        combinations[tuple(header.sig_name)] += 1
        if lead not in header.sig_name:
            missing.append(record_id)
        elif header.sig_name.index(lead) != 0:
            nonzero.append((record_id, header.sig_name.index(lead)))
    expected_rate = float(config["segmentation"]["sampling_rate_hz"])
    require(rates == Counter({expected_rate: len(records)}), f"Unexpected sampling rates: {dict(rates)}")
    require(len(records) > 0, "No MIT-BIH records were inspected")
    require(sorted(missing) == sorted(config["lead"]["excluded_records_missing_mlii"]),
            f"Unexpected records missing {lead}: {missing}")
    print("MIT-BIH DATASET INSPECTION")
    print(f"Records             : {len(records)}")
    print(f"Sampling rates      : {dict(rates)}")
    print(f"Signal lengths      : {dict(lengths)}")
    print(f"Lead combinations   : {dict(combinations)}")
    print(f"Missing {lead:4s}        : {missing}")
    print(f"{lead} not channel 0  : {nonzero}")
    print(f"Config SHA-256      : {config_sha256(config_path)}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
