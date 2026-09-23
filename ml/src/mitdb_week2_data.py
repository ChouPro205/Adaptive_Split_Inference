"""Read and validate frozen Week 1 MIT-BIH arrays without re-splitting or fitting."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mitdb_common import load_manifest
from week1_common import (artifact_sha256, config_sha256, configured_path,
                          load_config, load_json, require, verify_no_patient_leakage)


SPLITS = ("train", "val", "test")


def load_week1_splits(config_name: str = "mitdb_week1_config.json") -> tuple[dict, dict, dict]:
    """Return config, provenance identifiers, and the three fixed split arrays."""
    config_path, config = load_config(config_name)
    require(config["classes"] == {"N": 0, "S": 1, "V": 2, "F": 3, "Q": 4},
            "Unexpected Week 1 AAMI class mapping")
    require(config["lead"]["preferred"] == "MLII" and config["segmentation"]["window_size"] == 360,
            "Unexpected Week 1 ECG input contract")
    require(config["normalization"]["fit_split"] == "train", "Normalization was not train-only")
    manifest_path = configured_path(config, "patient_manifest")
    normalization_path = configured_path(config, "normalization")
    processed_dir = configured_path(config, "processed_dir")
    processed_path = processed_dir / "processed_manifest.json"
    processed = load_json(processed_path)
    normalization = load_json(normalization_path)
    identifiers = {"week1_config_sha256": config_sha256(config_path),
                   "patient_manifest_sha256": artifact_sha256(manifest_path),
                   "normalization_sha256": artifact_sha256(normalization_path),
                   "processed_manifest_sha256": artifact_sha256(processed_path),
                   "processed_artifacts": processed["artifacts"]}
    for key in ("config_sha256", "patient_manifest_sha256", "normalization_sha256"):
        require(processed.get(key) == identifiers[{"config_sha256": "week1_config_sha256",
                                                   "patient_manifest_sha256": "patient_manifest_sha256",
                                                   "normalization_sha256": "normalization_sha256"}[key]],
                f"Week 1 processed manifest {key} mismatch")
    require(normalization.get("config_sha256") == identifiers["week1_config_sha256"]
            and normalization.get("patient_manifest_sha256") == identifiers["patient_manifest_sha256"]
            and normalization.get("fit_split") == "train", "Week 1 normalization binding mismatch")
    rows = load_manifest(config)
    assigned = {split: {r["record_id"]: r["patient_id"] for r in rows
                        if r["eligibility"] == "eligible" and r["split"] == split} for split in SPLITS}
    arrays = {}
    patients = {}
    for split in SPLITS:
        files = {suffix: processed_dir / f"{split}_{suffix}" for suffix in ("X.npy", "y.npy", "metadata.csv")}
        for suffix, path in files.items():
            require(processed["artifacts"].get(path.name) == artifact_sha256(path),
                    f"Week 1 artifact hash mismatch: {path.name}")
        x = np.load(files["X.npy"], allow_pickle=False)
        y = np.load(files["y.npy"], allow_pickle=False)
        meta = pd.read_csv(files["metadata.csv"], dtype={"patient_id": str, "record_id": str})
        expected = config["processed_dataset"][split]
        require(x.shape == (expected["samples"], config["processed_dataset"]["sample_length"])
                and y.shape == (expected["samples"],), f"{split}: unexpected array shape")
        require(x.dtype == np.float32 and y.dtype == np.int64, f"{split}: unexpected array dtype")
        require(bool(np.isfinite(x).all()), f"{split}: non-finite ECG values")
        require(set(np.unique(y)).issubset(set(config["classes"].values())), f"{split}: invalid label")
        require(len(meta) == len(y) and np.array_equal(y, meta["class_index"].to_numpy(dtype=np.int64)),
                f"{split}: labels disagree with Week 1 metadata")
        require(set(meta["record_id"]) == set(assigned[split]), f"{split}: record IDs differ from manifest")
        require(all(assigned[split][record] == patient for record, patient in
                    zip(meta["record_id"], meta["patient_id"])),
                f"{split}: patient IDs differ from manifest")
        patients[split] = set(meta["patient_id"])
        require(len(patients[split]) == expected["patients"] and
                len(set(meta["record_id"])) == expected["records"],
                f"{split}: patient/record counts differ from Week 1 config")
        arrays[split] = (x, y)
    verify_no_patient_leakage(patients)
    return config, identifiers, arrays
