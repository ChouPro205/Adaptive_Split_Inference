"""Independently verify PTB-XL train-only per-lead normalization."""

from __future__ import annotations

import numpy as np
import wfdb

from ptbxl_common import canonical_records, summarize_records
from week1_common import (
    config_sha256,
    configured_path,
    load_config,
    load_json,
    require,
    run_cli,
    sha256_file,
)


def main() -> None:
    config_path, config = load_config("ptbxl_week1_config.json")
    normalization = config["normalization"]
    path = configured_path(config, "normalization")
    stored = load_json(path)
    current_hash = config_sha256(config_path)
    manifest_path = configured_path(config, "patient_manifest")
    require(stored.get("config_sha256") == current_hash,
            "PTB-XL normalization/config hash mismatch")
    require(stored.get("patient_manifest_sha256") == sha256_file(manifest_path),
            "PTB-XL normalization/patient-manifest hash mismatch")
    require(stored.get("dataset_version") == config["dataset"]["version"],
            "PTB-XL normalization dataset-version mismatch")
    require(stored.get("sampling_rate_hz") == config["signal"]["sampling_rate_hz"],
            "PTB-XL normalization sampling-rate mismatch")
    require(stored.get("lead_order") == config["signal"]["lead_order"],
            "PTB-XL normalization lead-order mismatch")
    require(stored.get("method") == normalization["method"],
            "PTB-XL normalization method mismatch")
    require(stored.get("fit_split") == normalization["fit_split"],
            "PTB-XL normalization fit-split mismatch")
    require(stored.get("input_unit") == normalization["input_unit"],
            "PTB-XL normalization input-unit mismatch")
    require(stored.get("physionet_checksum_manifest_sha256") ==
            config["integrity"]["physionet_checksum_manifest_sha256"],
            "PTB-XL normalization checksum-manifest binding mismatch")

    leads = int(config["signal"]["lead_count"])
    sample_count = int(config["signal"]["sample_count"])
    means = np.asarray(stored.get("mean_per_lead"), dtype=np.float64)
    stds = np.asarray(stored.get("std_per_lead"), dtype=np.float64)
    require(means.shape == (leads,) and stds.shape == (leads,),
            "PTB-XL normalization statistic shape mismatch")
    require(bool(np.isfinite(means).all()) and bool(np.isfinite(stds).all()) and bool((stds > 0).all()),
            "PTB-XL normalization statistics are non-finite or non-positive")

    output_dtype = np.dtype(normalization["output_dtype"])
    require(output_dtype == np.dtype(np.float32),
            f"Week 1 PTB-XL normalized representation must be float32, got {output_dtype}")
    raw_dir = configured_path(config, "raw_dir")
    records = canonical_records(
        configured_path(config, "database_csv"),
        configured_path(config, "scp_statements_csv"),
        config,
    )
    require(len(records) == int(config["integrity"]["expected_record_count"]),
            "PTB-XL normalization verification found an incomplete database")
    require(summarize_records(records) == config["expected_split"],
            "PTB-XL normalization verification found unexpected split counts")
    fit_split = normalization["fit_split"]
    train = [record for record in records if record["split"] == fit_split]
    require(len(train) == int(config["expected_split"][fit_split]["records"]),
            "PTB-XL normalization train-record count mismatch")

    normalized_sum = np.zeros(leads, dtype=np.float64)
    normalized_sum_sq = np.zeros(leads, dtype=np.float64)
    values_per_lead = 0
    for index, record in enumerate(train, start=1):
        waveform = wfdb.rdrecord(str(raw_dir / str(record["waveform_path"]))).p_signal
        require(waveform.shape == (sample_count, leads),
                f"Unexpected PTB-XL waveform shape for {record['waveform_path']}: {waveform.shape}")
        require(bool(np.isfinite(waveform).all()),
                f"Non-finite PTB-XL waveform: {record['waveform_path']}")
        normalized64 = (waveform.astype(np.float64, copy=False) - means) / stds
        require(bool(np.isfinite(normalized64).all()),
                f"Non-finite normalized PTB-XL values: {record['waveform_path']}")
        normalized = normalized64.astype(output_dtype)
        require(normalized.dtype == np.float32,
                f"Normalized PTB-XL dtype is not float32: {normalized.dtype}")
        require(bool(np.isfinite(normalized).all()),
                f"Non-finite float32 PTB-XL values: {record['waveform_path']}")
        values64 = normalized.astype(np.float64, copy=False)
        normalized_sum += values64.sum(axis=0)
        normalized_sum_sq += np.square(values64).sum(axis=0)
        values_per_lead += normalized.shape[0]
        if index % 2500 == 0:
            print(f"Normalized train waveforms checked: {index}/{len(train)}")

    require(values_per_lead > 0, "No PTB-XL train values were normalized")
    require(values_per_lead == int(stored["num_values_per_lead"]),
            "PTB-XL normalization value-count mismatch")
    require(len(train) == int(stored["num_train_records"]),
            "PTB-XL normalization stored train-record count mismatch")
    normalized_means = normalized_sum / values_per_lead
    variances = normalized_sum_sq / values_per_lead - np.square(normalized_means)
    require(bool(np.isfinite(variances).all()) and bool((variances >= 0).all()),
            "PTB-XL normalized variances are invalid")
    normalized_stds = np.sqrt(variances)
    mean_tolerance = float(normalization["verification_mean_abs_tolerance"])
    std_tolerance = float(normalization["verification_std_abs_tolerance"])
    require(bool((np.abs(normalized_means) <= mean_tolerance).all()),
            f"PTB-XL normalized train means exceed tolerance {mean_tolerance}: "
            f"{normalized_means.tolist()}")
    require(bool((np.abs(normalized_stds - 1.0) <= std_tolerance).all()),
            f"PTB-XL normalized train standard deviations exceed tolerance {std_tolerance}: "
            f"{normalized_stds.tolist()}")

    print("PTB-XL NORMALIZATION VERIFICATION")
    print(f"Train records / values per lead: {len(train)} / {values_per_lead}")
    print(f"Lead order                    : {stored['lead_order']}")
    print(f"Normalized dtype              : {output_dtype.name}")
    print(f"Normalized mean per lead      : {normalized_means.tolist()}")
    print(f"Normalized std per lead       : {normalized_stds.tolist()}")
    print(f"Mean/std absolute tolerances  : {mean_tolerance} / {std_tolerance}")
    print(f"Config SHA-256                : {current_hash}")
    print("Stored train-only statistics pass independent normalized-data verification")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
