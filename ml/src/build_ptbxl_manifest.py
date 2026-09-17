"""Build the PTB-XL patient-wise split and canonical multi-label manifest."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ptbxl_common import canonical_records, summarize_records
from week1_common import config_sha256, configured_path, load_config, require, run_cli


FIELDS = ["ecg_id", "patient_id", "strat_fold", "split", "waveform_path", "scp_codes", "label_count"]


def build(config_path: Path, config: dict, output_override: str | None = None) -> dict:
    records = canonical_records(
        configured_path(config, "database_csv"),
        configured_path(config, "scp_statements_csv"),
        config,
    )
    expected_count = int(config["integrity"]["expected_record_count"])
    require(len(records) == expected_count, f"Expected {expected_count} PTB-XL records, found {len(records)}")
    patients = {str(record["patient_id"]) for record in records}
    require(len(patients) == int(config["integrity"]["expected_patient_count"]),
            f"Unexpected PTB-XL patient count: {len(patients)}")
    summary = summarize_records(records)
    require(summary == config["expected_split"],
            f"PTB-XL split counts differ from config: expected {config['expected_split']}, got {summary}")
    output = Path(output_override).resolve() if output_override else configured_path(config, "patient_manifest")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    return {
        "records": len(records),
        "patients": len(patients),
        "summary": summary,
        "output": output,
        "config_sha256": config_sha256(config_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="ptbxl_week1_config.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    config_path, config = load_config(args.config)
    result = build(config_path, config, args.output)
    print("PTB-XL PATIENT MANIFEST")
    print(f"Records       : {result['records']}")
    print(f"Patients      : {result['patients']}")
    for split, counts in result["summary"].items():
        print(f"{split:5s}         : {counts['records']} records / {counts['patients']} patients")
    print(f"Config SHA-256: {result['config_sha256']}")
    print(f"Saved         : {result['output']}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
