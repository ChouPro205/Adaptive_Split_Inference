"""Verify MIT-BIH train-only normalization and provenance."""

from __future__ import annotations

import math

import numpy as np

from mitdb_common import iter_valid_beats, load_manifest, load_signal_and_annotations, validate_raw_files
from week1_common import (
    config_sha256,
    configured_path,
    load_config,
    load_json,
    patient_sets,
    require,
    run_cli,
    sha256_file,
    verify_no_patient_leakage,
)


def main() -> None:
    config_path, config = load_config("mitdb_week1_config.json")
    raw_dir, _ = validate_raw_files(config)
    rows = load_manifest(config)
    sets = patient_sets(rows)
    verify_no_patient_leakage(sets)
    norm_path = configured_path(config, "normalization")
    norm = load_json(norm_path)
    require(norm.get("config_sha256") == config_sha256(config_path), "Normalization config hash mismatch")
    require(norm.get("patient_manifest_sha256") == sha256_file(configured_path(config, "patient_manifest")),
            "Normalization patient-manifest hash mismatch")
    require(norm.get("dataset_version") == config["dataset"]["version"], "Normalization dataset version mismatch")
    mean = float(norm["mean"])
    std = float(norm["std"])
    require(math.isfinite(mean) and math.isfinite(std) and std > 0, "Invalid normalization statistics")
    results: dict[str, dict[str, float | int]] = {}
    for split in ("train", "val", "test"):
        split_rows = [row for row in rows if row["eligibility"] == "eligible" and row["split"] == split]
        require(split_rows, f"No records in MIT-BIH {split} split")
        total_sum = total_sum_sq = 0.0
        values = beats = 0
        for row in split_rows:
            _, signal, annotations, _ = load_signal_and_annotations(raw_dir, row["record_id"], config)
            for beat, *_ in iter_valid_beats(signal, annotations, config):
                normalized = (beat.astype(np.float64) - mean) / std
                total_sum += float(normalized.sum())
                total_sum_sq += float(np.square(normalized).sum())
                values += normalized.size
                beats += 1
        require(beats > 0 and values > 0, f"No beats in {split} normalization verification")
        normalized_mean = total_sum / values
        variance = total_sum_sq / values - normalized_mean ** 2
        require(variance >= 0, f"Negative normalized variance for {split}: {variance}")
        results[split] = {"records": len(split_rows), "patients": len(sets[split]), "beats": beats,
                          "mean": normalized_mean, "std": math.sqrt(variance)}
    require(abs(float(results["train"]["mean"])) < 1e-8, "Train normalized mean is not approximately zero")
    require(abs(float(results["train"]["std"]) - 1.0) < 1e-8, "Train normalized std is not approximately one")
    print("MIT-BIH NORMALIZATION VERIFICATION")
    for split, result in results.items():
        print(f"{split:5s}: {result['records']} records / {result['patients']} patients / "
              f"{result['beats']} beats / mean={result['mean']:.12g} / std={result['std']:.12g}")
    print(f"Config SHA-256: {config_sha256(config_path)}")
    print("Patient leakage: none")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
