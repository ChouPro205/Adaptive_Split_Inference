"""Compute frozen global Z-score statistics from MIT-BIH train beats only."""

from __future__ import annotations

import json
import math

import numpy as np

from mitdb_common import iter_valid_beats, load_manifest, load_signal_and_annotations, validate_raw_files
from week1_common import (
    config_sha256,
    configured_path,
    load_config,
    patient_sets,
    require,
    run_cli,
    sha256_file,
    verify_no_patient_leakage,
)


def main() -> None:
    config_path, config = load_config("mitdb_week1_config.json")
    raw_dir, _ = validate_raw_files(config)
    all_rows = load_manifest(config)
    verify_no_patient_leakage(patient_sets(all_rows))
    train_rows = [row for row in all_rows if row["eligibility"] == "eligible" and row["split"] == "train"]
    require(train_rows, "MIT-BIH manifest contains no eligible train records")
    total_sum = total_sum_sq = 0.0
    total_values = total_beats = boundary_dropped = 0
    mapping = config["aami_mapping"]
    left = int(config["segmentation"]["left_samples"])
    window = int(config["segmentation"]["window_size"])
    for row in train_rows:
        _, signal, annotations, _ = load_signal_and_annotations(raw_dir, row["record_id"], config)
        accepted = 0
        for beat, *_ in iter_valid_beats(signal, annotations, config):
            beat64 = beat.astype(np.float64)
            total_sum += float(beat64.sum())
            total_sum_sq += float(np.square(beat64).sum())
            total_values += beat64.size
            total_beats += 1
            accepted += 1
        eligible_annotations = sum(symbol in mapping for symbol in annotations.symbol)
        boundary_dropped += eligible_annotations - accepted
    require(total_beats > 0 and total_values > 0, "No train beats available for normalization")
    require(total_values == total_beats * window, "Normalization value-count invariant failed")
    mean = total_sum / total_values
    variance = total_sum_sq / total_values - mean ** 2
    require(math.isfinite(variance) and variance > 0, f"Invalid normalization variance: {variance}")
    std = math.sqrt(variance)
    frozen = config["normalization"]
    require(abs(mean - float(frozen["mean"])) < 1e-12, f"Computed mean changed: {mean}")
    require(abs(std - float(frozen["std"])) < 1e-12, f"Computed std changed: {std}")
    manifest_path = configured_path(config, "patient_manifest")
    stats = {
        "schema_version": 2,
        "dataset": config["dataset"]["name"],
        "dataset_version": config["dataset"]["version"],
        "lead": config["lead"]["preferred"],
        "window_size": window,
        "fit_split": frozen["fit_split"],
        "num_train_records": len(train_rows),
        "num_train_beats": total_beats,
        "num_values": total_values,
        "boundary_dropped": boundary_dropped,
        "mean": mean,
        "std": std,
        "config_sha256": config_sha256(config_path),
        "patient_manifest_sha256": sha256_file(manifest_path),
        "physionet_checksum_manifest_sha256": config["integrity"]["physionet_checksum_manifest_sha256"],
    }
    output = configured_path(config, "normalization")
    with output.open("w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2)
        handle.write("\n")
    print("MIT-BIH NORMALIZATION")
    print(f"Train records / beats: {len(train_rows)} / {total_beats}")
    print(f"Values / boundary    : {total_values} / {boundary_dropped}")
    print(f"Mean / std           : {mean} / {std}")
    print(f"Config SHA-256       : {stats['config_sha256']}")
    print(f"Saved                : {output}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
