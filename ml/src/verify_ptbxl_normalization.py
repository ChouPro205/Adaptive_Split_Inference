"""Recompute and verify PTB-XL train-only per-lead normalization."""

from __future__ import annotations

import numpy as np

from compute_ptbxl_normalization import compute
from week1_common import config_sha256, configured_path, load_config, load_json, require, run_cli, sha256_file


def main() -> None:
    config_path, config = load_config("ptbxl_week1_config.json")
    path = configured_path(config, "normalization")
    stored = load_json(path)
    current_hash = config_sha256(config_path)
    require(stored.get("config_sha256") == current_hash, "PTB-XL normalization/config hash mismatch")
    require(stored.get("patient_manifest_sha256") == sha256_file(configured_path(config, "patient_manifest")),
            "PTB-XL normalization/patient-manifest hash mismatch")
    require(stored.get("lead_order") == config["signal"]["lead_order"], "PTB-XL normalization lead order mismatch")
    means, stds, records, values = compute(config)
    require(np.allclose(means, np.asarray(stored["mean_per_lead"]), rtol=0, atol=1e-12),
            "PTB-XL normalization means changed")
    require(np.allclose(stds, np.asarray(stored["std_per_lead"]), rtol=0, atol=1e-12),
            "PTB-XL normalization standard deviations changed")
    require(records == int(stored["num_train_records"]), "PTB-XL normalization record count mismatch")
    require(values == int(stored["num_values_per_lead"]), "PTB-XL normalization value count mismatch")
    print("PTB-XL NORMALIZATION VERIFICATION")
    print(f"Train records / values per lead: {records} / {values}")
    print(f"Lead order                    : {stored['lead_order']}")
    print(f"Config SHA-256                : {current_hash}")
    print("Stored statistics match independent recomputation")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
