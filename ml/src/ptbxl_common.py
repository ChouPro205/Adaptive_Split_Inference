"""PTB-XL metadata parsing shared by Week 1 scripts."""

from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

from week1_common import ValidationError, read_csv_rows, require


def patient_id(value: str) -> str:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid PTB-XL patient_id: {value!r}") from exc
    require(numeric.is_integer(), f"Non-integral PTB-XL patient_id: {value!r}")
    return str(int(numeric))


def parse_scp_codes(value: str, vocabulary: set[str]) -> dict[str, float]:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise ValidationError(f"Invalid scp_codes value: {value!r}") from exc
    require(isinstance(parsed, dict) and parsed, "scp_codes must be a non-empty dictionary")
    result: dict[str, float] = {}
    for code, likelihood in parsed.items():
        require(isinstance(code, str) and code in vocabulary, f"Unknown SCP code: {code!r}")
        require(isinstance(likelihood, (int, float)), f"Non-numeric likelihood for SCP code {code}")
        result[code] = float(likelihood)
    return result


def load_scp_vocabulary(path: Path) -> set[str]:
    rows = read_csv_rows(path)
    first_column = next(iter(rows[0]))
    vocabulary = {row[first_column].strip() for row in rows if row[first_column].strip()}
    require(vocabulary, f"No SCP vocabulary entries found in {path}")
    return vocabulary


def split_for_fold(fold: int, split_config: dict) -> str:
    for split in ("train", "val", "test"):
        if fold in split_config[f"{split}_folds"]:
            return split
    raise ValidationError(f"Fold {fold} is not assigned to train/val/test")


def canonical_records(database_path: Path, scp_path: Path, config: dict) -> list[dict[str, object]]:
    rows = read_csv_rows(database_path)
    vocabulary = load_scp_vocabulary(scp_path)
    filename_column = config["signal"]["filename_column"]
    source_column = config["labels"]["source_column"]
    fold_column = config["split"]["source_column"]
    required_columns = {"ecg_id", "patient_id", filename_column, source_column, fold_column}
    require(required_columns.issubset(rows[0]),
            f"PTB-XL database is missing columns: {sorted(required_columns - set(rows[0]))}")
    records: list[dict[str, object]] = []
    seen_ecg: set[int] = set()
    patient_folds: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        try:
            ecg_id = int(row["ecg_id"])
            fold = int(row[fold_column])
        except ValueError as exc:
            raise ValidationError(f"Invalid ecg_id or fold in row: {row.get('ecg_id')}") from exc
        require(ecg_id not in seen_ecg, f"Duplicate ecg_id: {ecg_id}")
        seen_ecg.add(ecg_id)
        pid = patient_id(row["patient_id"])
        relative_stem = row[filename_column].strip().replace("\\", "/")
        require(relative_stem and not Path(relative_stem).is_absolute(),
                f"Invalid waveform path for ecg_id {ecg_id}: {relative_stem!r}")
        labels = parse_scp_codes(row[source_column], vocabulary)
        split = split_for_fold(fold, config["split"])
        patient_folds[pid].add(fold)
        records.append({
            "ecg_id": ecg_id,
            "patient_id": pid,
            "strat_fold": fold,
            "split": split,
            "waveform_path": relative_stem,
            "scp_codes": json.dumps(labels, sort_keys=True, separators=(",", ":")),
            "label_count": len(labels),
        })
    leaking = sorted(pid for pid, folds in patient_folds.items() if len(folds) != 1)
    require(not leaking, f"Patients assigned to multiple PTB-XL folds: {leaking[:10]}")
    return records


def summarize_records(records: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    record_counts = Counter(str(record["split"]) for record in records)
    patient_sets = {split: set() for split in ("train", "val", "test")}
    for record in records:
        patient_sets[str(record["split"])].add(str(record["patient_id"]))
    return {
        split: {"records": record_counts[split], "patients": len(patient_sets[split])}
        for split in ("train", "val", "test")
    }
