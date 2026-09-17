from pathlib import Path
import csv
import json

import numpy as np
import wfdb


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data" / "raw" / "mitdb"
MANIFEST_FILE = ROOT / "manifests" / "mitdb_patient_split.csv"

OUTPUT_DIR = ROOT / "configs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "mitdb_normalization.json"


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
# Read manifest
# --------------------------------------------------

train_records = []

with MANIFEST_FILE.open(
    "r",
    encoding="utf-8"
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        if (
            row["eligibility"] == "eligible"
            and row["split"] == "train"
        ):
            train_records.append(row["record_id"])


print("Train records:", len(train_records))
print(train_records)


# --------------------------------------------------
# Streaming statistics
#
# We accumulate:
#   sum(x)
#   sum(x^2)
#   number of values
#
# This avoids storing every training beat in RAM.
# --------------------------------------------------

total_sum = 0.0
total_sum_sq = 0.0
total_values = 0

total_beats = 0
boundary_dropped = 0


for record_id in train_records:

    record_path = DATA_DIR / record_id

    header = wfdb.rdheader(str(record_path))

    if "MLII" not in header.sig_name:
        raise RuntimeError(
            f"Train record {record_id} has no MLII"
        )

    lead_idx = header.sig_name.index("MLII")

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

        # Only accepted AAMI heartbeat annotations
        if symbol not in AAMI_MAP:
            continue

        start = r_peak - HALF_WINDOW
        end = start + WINDOW_SIZE

        if start < 0 or end > len(signal):
            boundary_dropped += 1
            continue

        beat = signal[start:end].astype(
            np.float64
        )

        if len(beat) != WINDOW_SIZE:
            raise RuntimeError(
                f"{record_id}: invalid beat length"
            )

        total_sum += beat.sum()
        total_sum_sq += np.square(beat).sum()

        total_values += beat.size
        total_beats += 1


# --------------------------------------------------
# Compute population mean/std
# --------------------------------------------------

mean = total_sum / total_values

variance = (
    total_sum_sq / total_values
    - mean ** 2
)

std = np.sqrt(variance)


# --------------------------------------------------
# Sanity checks
# --------------------------------------------------

assert total_values == total_beats * WINDOW_SIZE

if std <= 0:
    raise RuntimeError(
        "Invalid normalization std"
    )


# --------------------------------------------------
# Save
# --------------------------------------------------

stats = {
    "dataset": "MIT-BIH",
    "lead": "MLII",
    "window_size": WINDOW_SIZE,
    "fit_split": "train",
    "num_train_records": len(train_records),
    "num_train_beats": total_beats,
    "num_values": total_values,
    "boundary_dropped": boundary_dropped,
    "mean": float(mean),
    "std": float(std),
}


with OUTPUT_FILE.open(
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        stats,
        f,
        indent=2
    )


# --------------------------------------------------
# Report
# --------------------------------------------------

print("\nNORMALIZATION STATISTICS")
print("------------------------")

print("Train records   :", len(train_records))
print("Train beats     :", total_beats)
print("Total values    :", total_values)
print("Boundary dropped:", boundary_dropped)

print("\nMean:", mean)
print("Std :", std)

print("\nSaved to:")
print(OUTPUT_FILE)

print("\nSTATUS: PASS")