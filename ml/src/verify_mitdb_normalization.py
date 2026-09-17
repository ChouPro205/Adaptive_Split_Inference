from pathlib import Path
import csv
import json
from collections import Counter

import numpy as np
import wfdb


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data" / "raw" / "mitdb"
MANIFEST_FILE = (
    ROOT / "manifests" / "mitdb_patient_split.csv"
)
NORMALIZATION_FILE = (
    ROOT / "configs" / "mitdb_normalization.json"
)

WINDOW_SIZE = 360
HALF_WINDOW = WINDOW_SIZE // 2


AAMI_MAP = {
    "N": "N",
    "L": "N",
    "R": "N",
    "e": "N",
    "j": "N",

    "A": "S",
    "a": "S",
    "J": "S",
    "S": "S",

    "V": "V",
    "E": "V",

    "F": "F",

    "/": "Q",
    "f": "Q",
    "Q": "Q",
}


# --------------------------------------------------
# Load the TRAIN-fitted normalization parameters
# --------------------------------------------------

with NORMALIZATION_FILE.open(
    "r",
    encoding="utf-8"
) as f:
    norm = json.load(f)

mean_train = norm["mean"]
std_train = norm["std"]

print("Using normalization statistics:")
print("mean_train =", mean_train)
print("std_train  =", std_train)


# --------------------------------------------------
# Read manifest
# --------------------------------------------------

split_records = {
    "train": [],
    "val": [],
    "test": [],
}

split_patients = {
    "train": set(),
    "val": set(),
    "test": set(),
}


with MANIFEST_FILE.open(
    "r",
    encoding="utf-8"
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        if row["eligibility"] != "eligible":
            continue

        split = row["split"]

        split_records[split].append(
            row["record_id"]
        )

        split_patients[split].add(
            row["patient_id"]
        )


# --------------------------------------------------
# Verify patient leakage again
# --------------------------------------------------

assert split_patients["train"].isdisjoint(
    split_patients["val"]
)

assert split_patients["train"].isdisjoint(
    split_patients["test"]
)

assert split_patients["val"].isdisjoint(
    split_patients["test"]
)


# --------------------------------------------------
# Process one split
# --------------------------------------------------

def evaluate_split(split_name):

    total_sum = 0.0
    total_sum_sq = 0.0
    total_values = 0

    total_beats = 0
    boundary_dropped = 0

    class_counts = Counter()

    for record_id in split_records[split_name]:

        record_path = DATA_DIR / record_id

        header = wfdb.rdheader(
            str(record_path)
        )

        if "MLII" not in header.sig_name:
            raise RuntimeError(
                f"{record_id}: MLII missing"
            )

        lead_idx = header.sig_name.index(
            "MLII"
        )

        record = wfdb.rdrecord(
            str(record_path),
            channels=[lead_idx]
        )

        signal = record.p_signal[:, 0]

        ann = wfdb.rdann(
            str(record_path),
            "atr"
        )

        for r_peak, symbol in zip(
            ann.sample,
            ann.symbol
        ):

            if symbol not in AAMI_MAP:
                continue

            start = r_peak - HALF_WINDOW
            end = start + WINDOW_SIZE

            if (
                start < 0
                or end > len(signal)
            ):
                boundary_dropped += 1
                continue

            beat = signal[start:end].astype(
                np.float64
            )

            if len(beat) != WINDOW_SIZE:
                raise RuntimeError(
                    f"{record_id}: invalid beat size"
                )

            # IMPORTANT:
            # use TRAIN statistics for every split
            beat_norm = (
                beat - mean_train
            ) / std_train

            total_sum += beat_norm.sum()
            total_sum_sq += np.square(
                beat_norm
            ).sum()

            total_values += beat_norm.size
            total_beats += 1

            aami_class = AAMI_MAP[symbol]
            class_counts[aami_class] += 1


    normalized_mean = (
        total_sum / total_values
    )

    normalized_variance = (
        total_sum_sq / total_values
        - normalized_mean ** 2
    )

    normalized_std = np.sqrt(
        normalized_variance
    )


    return {
        "records": len(
            split_records[split_name]
        ),
        "patients": len(
            split_patients[split_name]
        ),
        "beats": total_beats,
        "values": total_values,
        "boundary_dropped": boundary_dropped,
        "mean": normalized_mean,
        "std": normalized_std,
        "classes": class_counts,
    }


# --------------------------------------------------
# Evaluate all splits
# --------------------------------------------------

results = {}

for split in [
    "train",
    "val",
    "test",
]:
    results[split] = evaluate_split(
        split
    )


# --------------------------------------------------
# Report
# --------------------------------------------------

print("\n" + "=" * 65)
print("NORMALIZATION VERIFICATION")
print("=" * 65)

for split in [
    "train",
    "val",
    "test",
]:

    result = results[split]

    print(
        f"\n{split.upper()}"
    )

    print("--------------------")

    print(
        "Patients         :",
        result["patients"]
    )

    print(
        "Records          :",
        result["records"]
    )

    print(
        "Beats            :",
        result["beats"]
    )

    print(
        "Boundary dropped :",
        result["boundary_dropped"]
    )

    print(
        "Normalized mean  :",
        result["mean"]
    )

    print(
        "Normalized std   :",
        result["std"]
    )

    print(
        "Class counts     :",
        dict(result["classes"])
    )


# --------------------------------------------------
# Critical invariants
# --------------------------------------------------

print("\n" + "=" * 65)
print("INVARIANT CHECK")
print("=" * 65)


train_mean_ok = (
    abs(results["train"]["mean"])
    < 1e-8
)

train_std_ok = (
    abs(
        results["train"]["std"] - 1.0
    )
    < 1e-8
)


print(
    "Train normalized mean ~ 0:",
    train_mean_ok
)

print(
    "Train normalized std ~ 1 :",
    train_std_ok
)

print(
    "Patient leakage train/val :",
    split_patients["train"]
    & split_patients["val"]
)

print(
    "Patient leakage train/test:",
    split_patients["train"]
    & split_patients["test"]
)

print(
    "Patient leakage val/test  :",
    split_patients["val"]
    & split_patients["test"]
)


if train_mean_ok and train_std_ok:
    print("\nSTATUS: PASS")
else:
    print("\nSTATUS: FAIL")