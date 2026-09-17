"""Fit PTB-XL per-lead global Z-score statistics on official train folds."""

from __future__ import annotations

import json
import math

import numpy as np
import wfdb

from ptbxl_common import canonical_records
from week1_common import config_sha256, configured_path, load_config, require, run_cli, sha256_file


def compute(config: dict) -> tuple[np.ndarray, np.ndarray, int, int]:
    raw_dir = configured_path(config, "raw_dir")
    records = canonical_records(
        configured_path(config, "database_csv"),
        configured_path(config, "scp_statements_csv"),
        config,
    )
    fit_split = config["normalization"]["fit_split"]
    train = [record for record in records if record["split"] == fit_split]
    require(train, f"No PTB-XL records in normalization split {fit_split}")
    leads = int(config["signal"]["lead_count"])
    sample_count = int(config["signal"]["sample_count"])
    total_sum = np.zeros(leads, dtype=np.float64)
    total_sum_sq = np.zeros(leads, dtype=np.float64)
    values_per_lead = 0
    for index, record in enumerate(train, start=1):
        waveform = wfdb.rdrecord(str(raw_dir / str(record["waveform_path"]))).p_signal
        require(waveform.shape == (sample_count, leads),
                f"Unexpected PTB-XL waveform shape for {record['waveform_path']}: {waveform.shape}")
        require(bool(np.isfinite(waveform).all()), f"Non-finite PTB-XL waveform: {record['waveform_path']}")
        values = waveform.astype(np.float64, copy=False)
        total_sum += values.sum(axis=0)
        total_sum_sq += np.square(values).sum(axis=0)
        values_per_lead += values.shape[0]
        if index % 2500 == 0:
            print(f"Train waveforms processed: {index}/{len(train)}")
    means = total_sum / values_per_lead
    variances = total_sum_sq / values_per_lead - np.square(means)
    require(bool(np.isfinite(variances).all()) and bool((variances > 0).all()),
            f"Invalid PTB-XL per-lead variances: {variances.tolist()}")
    return means, np.sqrt(variances), len(train), values_per_lead


def main() -> None:
    config_path, config = load_config("ptbxl_week1_config.json")
    means, stds, record_count, values_per_lead = compute(config)
    output = configured_path(config, "normalization")
    payload = {
        "schema_version": 1,
        "dataset": config["dataset"]["name"],
        "dataset_version": config["dataset"]["version"],
        "sampling_rate_hz": config["signal"]["sampling_rate_hz"],
        "lead_order": config["signal"]["lead_order"],
        "method": config["normalization"]["method"],
        "fit_split": config["normalization"]["fit_split"],
        "input_unit": config["normalization"]["input_unit"],
        "num_train_records": record_count,
        "num_values_per_lead": values_per_lead,
        "mean_per_lead": means.tolist(),
        "std_per_lead": stds.tolist(),
        "config_sha256": config_sha256(config_path),
        "patient_manifest_sha256": sha256_file(configured_path(config, "patient_manifest")),
        "physionet_checksum_manifest_sha256": config["integrity"]["physionet_checksum_manifest_sha256"],
    }
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print("PTB-XL NORMALIZATION")
    print(f"Train records        : {record_count}")
    print(f"Values per lead      : {values_per_lead}")
    print(f"Lead order           : {config['signal']['lead_order']}")
    print(f"Mean per lead        : {means.tolist()}")
    print(f"Std per lead         : {stds.tolist()}")
    print(f"Config SHA-256       : {payload['config_sha256']}")
    print(f"Saved                : {output}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
