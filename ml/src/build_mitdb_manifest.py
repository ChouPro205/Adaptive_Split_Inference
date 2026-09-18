"""Build the deterministic MIT-BIH patient-wise split manifest."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

import wfdb

from mitdb_common import get_patient_id, validate_raw_files
from week1_common import config_sha256, configured_path, load_config, require, run_cli, verify_no_patient_leakage


FIELDS = ["record_id", "patient_id", "has_mlii", "mlii_index", "eligibility", "exclusion_reason", "split"]


def build(config_path: Path, config: dict, output_override: str | None = None) -> dict:
    raw_dir, records = validate_raw_files(config)
    lead = config["lead"]["preferred"]
    rows: list[dict[str, object]] = []
    patient_records: dict[str, list[str]] = {}
    for record_id in records:
        header = wfdb.rdheader(str(raw_dir / record_id))
        patient = get_patient_id(record_id, config)
        has_lead = lead in header.sig_name
        if has_lead:
            patient_records.setdefault(patient, []).append(record_id)
        rows.append({
            "record_id": record_id,
            "patient_id": patient,
            "has_mlii": has_lead,
            "mlii_index": header.sig_name.index(lead) if has_lead else "",
            "eligibility": "eligible" if has_lead else "excluded",
            "exclusion_reason": "" if has_lead else "missing_mlii",
            "split": "",
        })
    patients = sorted(patient_records)
    require(patients, "No eligible MIT-BIH patients found")
    split_config = config["split"]
    ratios = [float(split_config[f"{name}_ratio"]) for name in ("train", "val", "test")]
    require(abs(sum(ratios) - 1.0) < 1e-12, f"Split ratios do not sum to 1: {ratios}")
    random.Random(int(split_config["seed"])).shuffle(patients)
    n_train = round(len(patients) * ratios[0])
    n_val = round(len(patients) * ratios[1])
    sets = {
        "train": set(patients[:n_train]),
        "val": set(patients[n_train:n_train + n_val]),
        "test": set(patients[n_train + n_val:]),
    }
    verify_no_patient_leakage(sets)
    require(sum(len(value) for value in sets.values()) == len(patients), "Patient split is incomplete")
    for row in rows:
        if row["eligibility"] != "eligible":
            continue
        matches = [split for split, values in sets.items() if row["patient_id"] in values]
        require(len(matches) == 1, f"Patient {row['patient_id']} has {len(matches)} split assignments")
        row["split"] = matches[0]
    output = Path(output_override).resolve() if output_override else configured_path(config, "patient_manifest")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    record_counts = {split: sum(row["split"] == split for row in rows) for split in sets}
    return {"patients": {split: len(value) for split, value in sets.items()},
            "records": record_counts, "output": output, "config_sha256": config_sha256(config_path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mitdb_week1_config.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    config_path, config = load_config(args.config)
    result = build(config_path, config, args.output)
    print("MIT-BIH PATIENT MANIFEST")
    for split in ("train", "val", "test"):
        print(f"{split:5s}: {result['patients'][split]} patients / {result['records'][split]} records")
    print(f"Config SHA-256: {result['config_sha256']}")
    print(f"Saved         : {result['output']}")
    print("Patient leakage: none")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
