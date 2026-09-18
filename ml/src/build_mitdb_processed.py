"""Build normalized MIT-BIH arrays and a hash-bound processed manifest."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from mitdb_common import iter_valid_beats, load_manifest, load_signal_and_annotations, validate_raw_files
from week1_common import (
    BINARY_HASH_POLICY,
    TEXT_HASH_POLICY,
    artifact_sha256,
    config_sha256,
    configured_path,
    load_config,
    load_json,
    patient_sets,
    require,
    run_cli,
    verify_no_patient_leakage,
)


def main() -> None:
    config_path, config = load_config("mitdb_week1_config.json")
    raw_dir, _ = validate_raw_files(config)
    rows = load_manifest(config)
    verify_no_patient_leakage(patient_sets(rows))
    manifest_path = configured_path(config, "patient_manifest")
    norm_path = configured_path(config, "normalization")
    norm = load_json(norm_path)
    current_config_hash = config_sha256(config_path)
    current_manifest_hash = artifact_sha256(manifest_path)
    require(norm.get("config_sha256") == current_config_hash, "Normalization config hash mismatch")
    require(norm.get("patient_manifest_sha256") == current_manifest_hash,
            "Normalization patient-manifest hash mismatch")
    mean = float(norm["mean"])
    std = float(norm["std"])
    require(np.isfinite([mean, std]).all() and std > 0, "Invalid normalization values")
    output_dir = configured_path(config, "processed_dir")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    summaries: dict[str, dict[str, int]] = {}
    expected = config["processed_dataset"]
    for split in ("train", "val", "test"):
        split_rows = [row for row in rows if row["eligibility"] == "eligible" and row["split"] == split]
        require(split_rows, f"No eligible records in {split} split")
        x_values: list[np.ndarray] = []
        y_values: list[int] = []
        metadata: list[dict[str, object]] = []
        for row in split_rows:
            record_id = row["record_id"]
            _, signal, annotations, lead_index = load_signal_and_annotations(raw_dir, record_id, config)
            for beat, r_peak, symbol, aami_class, class_index in iter_valid_beats(signal, annotations, config):
                x_values.append(((beat - mean) / std).astype(np.float32))
                y_values.append(class_index)
                metadata.append({
                    "patient_id": row["patient_id"],
                    "record_id": record_id,
                    "r_peak_sample": r_peak,
                    "original_symbol": symbol,
                    "aami_class": aami_class,
                    "class_index": class_index,
                    "lead_name": config["lead"]["preferred"],
                    "lead_index": lead_index,
                })
        X = np.asarray(x_values, dtype=np.float32)
        y = np.asarray(y_values, dtype=np.int64)
        frame = pd.DataFrame(metadata)
        split_expected = expected[split]
        expected_shape = (int(split_expected["samples"]), int(expected["sample_length"]))
        require(X.shape == expected_shape, f"{split}: expected X shape {expected_shape}, got {X.shape}")
        require(y.shape == (expected_shape[0],), f"{split}: unexpected y shape {y.shape}")
        require(len(frame) == len(X), f"{split}: metadata length mismatch")
        require(X.dtype.name == expected["x_dtype"], f"{split}: unexpected X dtype {X.dtype}")
        require(y.dtype.name == expected["y_dtype"], f"{split}: unexpected y dtype {y.dtype}")
        require(bool(np.isfinite(X).all()), f"{split}: X contains non-finite values")
        require(set(np.unique(y)).issubset(set(config["classes"].values())), f"{split}: invalid labels")
        require(frame["patient_id"].nunique() == int(split_expected["patients"]),
                f"{split}: unexpected patient count")
        require(frame["record_id"].nunique() == int(split_expected["records"]),
                f"{split}: unexpected record count")
        paths = {
            f"{split}_X.npy": output_dir / f"{split}_X.npy",
            f"{split}_y.npy": output_dir / f"{split}_y.npy",
            f"{split}_metadata.csv": output_dir / f"{split}_metadata.csv",
        }
        np.save(paths[f"{split}_X.npy"], X)
        np.save(paths[f"{split}_y.npy"], y)
        frame.to_csv(paths[f"{split}_metadata.csv"], index=False)
        for name, path in paths.items():
            artifacts[name] = artifact_sha256(path)
        summaries[split] = {
            "samples": len(X),
            "patients": int(frame["patient_id"].nunique()),
            "records": int(frame["record_id"].nunique()),
        }
        print(f"{split:5s}: X={X.shape} {X.dtype}; y={y.shape} {y.dtype}; "
              f"patients={summaries[split]['patients']}; records={summaries[split]['records']}")
    processed_manifest = {
        "schema_version": 1,
        "dataset_version": config["dataset"]["version"],
        "config_sha256": current_config_hash,
        "patient_manifest_sha256": current_manifest_hash,
        "normalization_sha256": artifact_sha256(norm_path),
        "physionet_checksum_manifest_sha256": config["integrity"]["physionet_checksum_manifest_sha256"],
        "repository_text_hash_policy": TEXT_HASH_POLICY,
        "binary_hash_policy": BINARY_HASH_POLICY,
        "splits": summaries,
        "artifacts": artifacts,
    }
    output_manifest = output_dir / "processed_manifest.json"
    with output_manifest.open("w", encoding="utf-8") as handle:
        json.dump(processed_manifest, handle, indent=2)
        handle.write("\n")
    print(f"Config SHA-256: {current_config_hash}")
    print(f"Processed manifest: {output_manifest}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
