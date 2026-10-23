"""Authenticated train/val subset of the existing frozen Week 1 data contract.

Unlike the historical all-split evaluation loader, never open test arrays or
test metadata. Test patient assignments are checked from the frozen manifest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mitdb_common import load_manifest
from week1_common import (artifact_sha256, config_sha256, configured_path,
                          load_config, load_json, require, verify_no_patient_leakage)


def load_train_val(checkpoint):
    config_path, config = load_config("mitdb_week1_config.json")
    directory = configured_path(config, "processed_dir")
    processed_path = directory / "processed_manifest.json"
    patient_path = configured_path(config, "patient_manifest")
    norm_path = configured_path(config, "normalization")
    processed, norm = load_json(processed_path), load_json(norm_path)
    identifiers = {"week1_config_sha256": config_sha256(config_path),
                   "patient_manifest_sha256": artifact_sha256(patient_path),
                   "normalization_sha256": artifact_sha256(norm_path),
                   "processed_manifest_sha256": artifact_sha256(processed_path),
                   "processed_artifacts": processed["artifacts"]}
    require(identifiers == checkpoint["provenance"]["dataset_artifacts"],
            "Train/val identifiers differ from approved checkpoint")
    require(config["classes"] == {"N": 0, "S": 1, "V": 2, "F": 3, "Q": 4}
            and config["lead"]["preferred"] == "MLII"
            and config["segmentation"]["window_size"] == 360,
            "Frozen ECG input contract differs")
    for key, identifier in (("config_sha256", "week1_config_sha256"),
                            ("patient_manifest_sha256", "patient_manifest_sha256"),
                            ("normalization_sha256", "normalization_sha256")):
        require(processed[key] == identifiers[identifier], "Processed binding differs: " + key)
    require(norm["fit_split"] == config["normalization"]["fit_split"] == "train"
            and norm["config_sha256"] == identifiers["week1_config_sha256"]
            and norm["patient_manifest_sha256"] == identifiers["patient_manifest_sha256"],
            "Normalization must retain frozen train-only bindings")
    rows = load_manifest(config)
    assigned = {split: {r["record_id"]: r["patient_id"] for r in rows
                        if r["eligibility"] == "eligible" and r["split"] == split}
                for split in ("train", "val", "test")}
    verify_no_patient_leakage({s: set(records.values()) for s, records in assigned.items()})
    arrays, metadata = {}, {}
    for split in ("train", "val"):
        files = {suffix: directory / f"{split}_{suffix}" for suffix in ("X.npy", "y.npy", "metadata.csv")}
        for path in files.values():
            require(artifact_sha256(path) == identifiers["processed_artifacts"][path.name],
                    "Train/val artifact hash mismatch: " + path.name)
        x, y = (np.load(files[suffix], allow_pickle=False) for suffix in ("X.npy", "y.npy"))
        meta = pd.read_csv(files["metadata.csv"], dtype={"patient_id": str, "record_id": str})
        expected = config["processed_dataset"][split]
        require(x.shape == (expected["samples"], 360) and y.shape == (len(x),), "Invalid shape: " + split)
        require(x.dtype == np.float32 and y.dtype == np.int64 and bool(np.isfinite(x).all()),
                "Invalid dtype/values: " + split)
        require(set(np.unique(y)).issubset(set(config["classes"].values())), "Invalid labels")
        require(len(meta) == len(y) and np.array_equal(y, meta.class_index.to_numpy(dtype=np.int64)),
                "Labels differ from metadata")
        require(set(meta.record_id) == set(assigned[split]) and
                all(assigned[split][r] == p for r, p in zip(meta.record_id, meta.patient_id)),
                "Patient/record assignment differs")
        require(meta.patient_id.nunique() == expected["patients"] and meta.record_id.nunique() == expected["records"],
                "Patient/record counts differ")
        ids = [f"MIT-BIH:{r.record_id}:{r.r_peak_sample}:{r.lead_name}" for r in meta.itertuples()]
        require(len(ids) == len(set(ids)), "Duplicate sample IDs")
        meta["sample_id"] = ids
        arrays[split], metadata[split] = (x[:, None, :].copy(), y), meta
    require(not set(metadata["train"].sample_id) & set(metadata["val"].sample_id), "Overlapping sample IDs")
    return config, identifiers, arrays, metadata
