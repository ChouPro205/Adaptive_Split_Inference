"""Audit all MIT-BIH annotations against the frozen Week 1 protocol."""

from __future__ import annotations

from collections import Counter

import wfdb

from mitdb_common import segmentation_settings, validate_raw_files
from week1_common import config_sha256, load_config, require, run_cli


def main() -> None:
    config_path, config = load_config("mitdb_week1_config.json")
    raw_dir, records = validate_raw_files(config)
    lead, window, left, _, mapping, _ = segmentation_settings(config)
    aami_counts: Counter[str] = Counter()
    ignored_counts: Counter[str] = Counter()
    raw_annotations = boundary_dropped = valid_beats = 0
    processed: list[str] = []
    without_lead: list[str] = []
    nonzero: list[tuple[str, int]] = []
    for record_id in records:
        record_path = raw_dir / record_id
        header = wfdb.rdheader(str(record_path))
        require(float(header.fs) == float(config["segmentation"]["sampling_rate_hz"]),
                f"Unexpected sampling rate for {record_id}: {header.fs}")
        if lead not in header.sig_name:
            without_lead.append(record_id)
            continue
        lead_index = header.sig_name.index(lead)
        if lead_index != 0:
            nonzero.append((record_id, lead_index))
        signal = wfdb.rdrecord(str(record_path), channels=[lead_index]).p_signal[:, 0]
        annotations = wfdb.rdann(str(record_path), "atr")
        processed.append(record_id)
        raw_annotations += len(annotations.sample)
        for r_peak, symbol in zip(annotations.sample, annotations.symbol):
            if symbol not in mapping:
                ignored_counts[symbol] += 1
                continue
            start = int(r_peak) - left
            end = start + window
            if start < 0 or end > len(signal):
                boundary_dropped += 1
                continue
            require(len(signal[start:end]) == window, f"{record_id}: invalid beat length")
            aami_counts[mapping[symbol]] += 1
            valid_beats += 1
    require(processed and valid_beats > 0, "Audit processed no records or valid beats")
    expected = config["expected_audit"]
    actual = {
        "processed_records": len(processed),
        "raw_annotations": raw_annotations,
        "ignored_annotations": sum(ignored_counts.values()),
        "boundary_dropped": boundary_dropped,
        "valid_beats": valid_beats,
        "class_counts": {name: aami_counts[name] for name in config["classes"]},
    }
    require(actual == expected, f"MIT-BIH audit differs from frozen results: expected {expected}, got {actual}")
    require(raw_annotations - sum(ignored_counts.values()) - boundary_dropped == valid_beats,
            "MIT-BIH annotation accounting invariant failed")
    require(sorted(without_lead) == sorted(config["lead"]["excluded_records_missing_mlii"]),
            f"Unexpected records without {lead}: {without_lead}")
    print("MIT-BIH PREPROCESSING AUDIT")
    print(f"Records found / processed: {len(records)} / {len(processed)}")
    print(f"Records without {lead}   : {without_lead}")
    print(f"{lead} not channel 0      : {nonzero}")
    print(f"Ignored annotations      : {dict(ignored_counts)}")
    print(f"AAMI counts              : {actual['class_counts']}")
    print(f"Raw / ignored / boundary : {raw_annotations} / {actual['ignored_annotations']} / {boundary_dropped}")
    print(f"Final valid beats        : {valid_beats}")
    print(f"Config SHA-256           : {config_sha256(config_path)}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
