"""MIT-BIH Week 1 data helpers driven exclusively by the frozen config."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

import numpy as np
import wfdb

from week1_common import (
    configured_path,
    load_expected_records,
    read_csv_rows,
    require,
    require_raw_dir,
)


def expected_records(config: dict) -> list[str]:
    return load_expected_records(
        configured_path(config, "expected_records"),
        int(config["integrity"]["expected_record_count"]),
    )


def validate_raw_files(config: dict, raw_dir: Path | None = None) -> tuple[Path, list[str]]:
    directory = raw_dir.resolve() if raw_dir else configured_path(config, "raw_dir")
    require_raw_dir(directory)
    records = expected_records(config)
    actual = {path.stem for path in directory.glob("*.hea")}
    expected = set(records)
    require(actual == expected,
            f"MIT-BIH record list mismatch; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}")
    for record in records:
        for extension in config["integrity"]["required_extensions"]:
            path = directory / f"{record}.{extension}"
            require(path.is_file() and path.stat().st_size > 0,
                    f"Required MIT-BIH file missing or empty: {path}")
    return directory, records


def get_patient_id(record_id: str, config: dict) -> str:
    for group in config["patient_identity"]["shared_record_groups"]:
        if record_id in group:
            return "P" + "_".join(group)
    return f"P{record_id}"


def load_manifest(config: dict, eligible_only: bool = False) -> list[dict[str, str]]:
    rows = read_csv_rows(configured_path(config, "patient_manifest"))
    require(len(rows) == int(config["integrity"]["expected_record_count"]),
            f"MIT-BIH manifest must contain {config['integrity']['expected_record_count']} rows")
    require({row["record_id"] for row in rows} == set(expected_records(config)),
            "MIT-BIH manifest record IDs do not match the official record list")
    return [row for row in rows if row["eligibility"] == "eligible"] if eligible_only else rows


def segmentation_settings(config: dict) -> tuple[str, int, int, int, dict[str, str], dict[str, int]]:
    lead = config["lead"]["preferred"]
    segment = config["segmentation"]
    window = int(segment["window_size"])
    left = int(segment["left_samples"])
    right = int(segment["right_samples"])
    require(left + right == window, "Segmentation left/right samples do not equal window size")
    return lead, window, left, right, dict(config["aami_mapping"]), dict(config["classes"])


def load_signal_and_annotations(raw_dir: Path, record_id: str, config: dict):
    lead, _, _, _, _, _ = segmentation_settings(config)
    record_path = raw_dir / record_id
    header = wfdb.rdheader(str(record_path))
    require(float(header.fs) == float(config["segmentation"]["sampling_rate_hz"]),
            f"Unexpected sampling rate in record {record_id}: {header.fs}")
    require(lead in header.sig_name, f"{record_id}: required lead {lead} is missing")
    lead_index = header.sig_name.index(lead)
    record = wfdb.rdrecord(str(record_path), channels=[lead_index])
    annotations = wfdb.rdann(str(record_path), "atr")
    return header, record.p_signal[:, 0], annotations, lead_index


def iter_valid_beats(signal: np.ndarray, annotations, config: dict) -> Iterator[tuple[np.ndarray, int, str, str, int]]:
    _, window, left, _, mapping, classes = segmentation_settings(config)
    for r_peak, symbol in zip(annotations.sample, annotations.symbol):
        if symbol not in mapping:
            continue
        start = int(r_peak) - left
        end = start + window
        if start < 0 or end > len(signal):
            continue
        beat = signal[start:end]
        require(len(beat) == window, f"Invalid accepted beat length: {len(beat)}")
        aami_class = mapping[symbol]
        yield beat, int(r_peak), symbol, aami_class, int(classes[aami_class])
