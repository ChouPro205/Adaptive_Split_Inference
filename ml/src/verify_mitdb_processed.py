"""Verify MIT-BIH processed files, source metadata, hashes, and config binding."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mitdb_common import iter_valid_beats, load_manifest, load_signal_and_annotations, validate_raw_files
from week1_common import (
    config_sha256,
    configured_path,
    load_config,
    load_json,
    require,
    run_cli,
    sha256_file,
    verify_no_patient_leakage,
)


def main() -> None:
    config_path, config = load_config("mitdb_week1_config.json")
    raw_dir, _ = validate_raw_files(config)
    manifest_rows = load_manifest(config)
    eligible = [row for row in manifest_rows if row["eligibility"] == "eligible"]
    record_assignment = {row["record_id"]: (row["patient_id"], row["split"]) for row in eligible}
    output_dir = configured_path(config, "processed_dir")
    require(output_dir.is_dir(), f"Processed directory does not exist: {output_dir}")
    provenance_path = output_dir / "processed_manifest.json"
    provenance = load_json(provenance_path)
    current_config_hash = config_sha256(config_path)
    patient_manifest_path = configured_path(config, "patient_manifest")
    norm_path = configured_path(config, "normalization")
    norm = load_json(norm_path)
    require(provenance.get("config_sha256") == current_config_hash, "Processed/config hash mismatch")
    require(provenance.get("patient_manifest_sha256") == sha256_file(patient_manifest_path),
            "Processed/patient-manifest hash mismatch")
    require(provenance.get("normalization_sha256") == sha256_file(norm_path),
            "Processed/normalization hash mismatch")
    require(provenance.get("dataset_version") == config["dataset"]["version"],
            "Processed dataset version mismatch")
    require(norm.get("config_sha256") == current_config_hash, "Normalization/config hash mismatch")
    mean = float(norm["mean"])
    std = float(norm["std"])
    results: dict[str, dict[str, object]] = {}
    allowed_classes = set(config["classes"].values())
    for split in ("train", "val", "test"):
        names = [f"{split}_X.npy", f"{split}_y.npy", f"{split}_metadata.csv"]
        for name in names:
            path = output_dir / name
            require(path.is_file(), f"Processed artifact missing: {path}")
            require(provenance["artifacts"].get(name) == sha256_file(path),
                    f"Processed artifact hash mismatch: {name}")
        X = np.load(output_dir / names[0], allow_pickle=False)
        y = np.load(output_dir / names[1], allow_pickle=False)
        metadata = pd.read_csv(output_dir / names[2], dtype={"patient_id": str, "record_id": str})
        expected = config["processed_dataset"][split]
        expected_shape = (int(expected["samples"]), int(config["processed_dataset"]["sample_length"]))
        require(X.shape == expected_shape, f"{split}: X shape mismatch: {X.shape}")
        require(y.shape == (expected_shape[0],), f"{split}: y shape mismatch: {y.shape}")
        require(len(metadata) == len(X), f"{split}: metadata length mismatch")
        require(X.dtype.name == config["processed_dataset"]["x_dtype"], f"{split}: X dtype mismatch")
        require(y.dtype.name == config["processed_dataset"]["y_dtype"], f"{split}: y dtype mismatch")
        require(bool(np.isfinite(X).all()), f"{split}: non-finite X values")
        require(set(np.unique(y)).issubset(allowed_classes), f"{split}: invalid class index")
        require(np.array_equal(y, metadata["class_index"].to_numpy(dtype=np.int64)),
                f"{split}: y does not match metadata")
        patients = set(metadata["patient_id"])
        records = set(metadata["record_id"])
        require(len(patients) == int(expected["patients"]), f"{split}: patient count mismatch")
        require(len(records) == int(expected["records"]), f"{split}: record count mismatch")
        expected_records = {record for record, (_, assigned) in record_assignment.items() if assigned == split}
        require(records == expected_records, f"{split}: metadata record IDs differ from split manifest")
        cursor = 0
        for row in (item for item in eligible if item["split"] == split):
            record_id = row["record_id"]
            _, signal, annotations, lead_index = load_signal_and_annotations(raw_dir, record_id, config)
            source_beats = list(iter_valid_beats(signal, annotations, config))
            require(source_beats, f"{record_id}: no source beats during processed verification")
            stop = cursor + len(source_beats)
            subset = metadata.iloc[cursor:stop]
            require(len(subset) == len(source_beats), f"{record_id}: processed metadata truncated")
            expected_meta = [(row["patient_id"], record_id, peak, symbol, cls, index,
                              config["lead"]["preferred"], lead_index)
                             for _, peak, symbol, cls, index in source_beats]
            actual_meta = list(subset[["patient_id", "record_id", "r_peak_sample", "original_symbol",
                                       "aami_class", "class_index", "lead_name", "lead_index"]]
                               .itertuples(index=False, name=None))
            require(actual_meta == expected_meta, f"{record_id}: metadata does not match raw annotations")
            source_x = np.asarray([((beat - mean) / std).astype(np.float32)
                                   for beat, *_ in source_beats], dtype=np.float32)
            require(np.array_equal(X[cursor:stop], source_x),
                    f"{record_id}: processed samples do not match normalized raw source")
            cursor = stop
        require(cursor == len(X), f"{split}: unaccounted processed rows: {len(X) - cursor}")
        results[split] = {"patients": patients, "records": records,
                          "mean": float(X.mean(dtype=np.float64)), "std": float(X.std(dtype=np.float64)),
                          "shape": X.shape}
        print(f"{split:5s}: X={X.shape} {X.dtype}; y={y.shape} {y.dtype}; "
              f"patients={len(patients)}; records={len(records)}; "
              f"mean={results[split]['mean']:.12g}; std={results[split]['std']:.12g}")
    verify_no_patient_leakage({split: result["patients"] for split, result in results.items()})
    require(abs(float(results["train"]["mean"])) < 1e-5, "Processed train mean is not approximately zero")
    require(abs(float(results["train"]["std"]) - 1.0) < 1e-5,
            "Processed train std is not approximately one")
    print(f"Config SHA-256: {current_config_hash}")
    print("Raw annotation cross-check: all processed rows")
    print("Patient leakage: none")
    print("Artifact hashes: match processed_manifest.json")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
