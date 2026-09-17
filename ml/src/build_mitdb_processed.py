from pathlib import Path
import csv
import json

import numpy as np
import pandas as pd
import wfdb


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data" / "raw" / "mitdb"
MANIFEST_FILE = ROOT / "manifests" / "mitdb_patient_split.csv"
NORMALIZATION_FILE = ROOT / "configs" / "mitdb_normalization.json"

OUTPUT_DIR = ROOT / "data" / "processed" / "mitdb"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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


CLASS_TO_INDEX = {
    "N": 0,
    "S": 1,
    "V": 2,
    "F": 3,
    "Q": 4,
}


# --------------------------------------------------
# Load TRAIN-fitted normalization stats
# --------------------------------------------------

with NORMALIZATION_FILE.open(
    "r",
    encoding="utf-8"
) as f:

    normalization = json.load(f)


mean_train = normalization["mean"]
std_train = normalization["std"]


# --------------------------------------------------
# Read manifest
# --------------------------------------------------

manifest_rows = []

with MANIFEST_FILE.open(
    "r",
    encoding="utf-8"
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        if row["eligibility"] == "eligible":
            manifest_rows.append(row)


# --------------------------------------------------
# Build each split independently
# --------------------------------------------------

for split_name in ["train", "val", "test"]:

    X = []
    y = []
    metadata = []

    split_rows = [
        row
        for row in manifest_rows
        if row["split"] == split_name
    ]

    print("\nBuilding:", split_name)

    for row in split_rows:

        record_id = row["record_id"]
        patient_id = row["patient_id"]

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
                continue

            beat = signal[start:end]

            if len(beat) != WINDOW_SIZE:
                raise RuntimeError(
                    f"{record_id}: invalid beat size"
                )

            aami_class = AAMI_MAP[symbol]
            class_index = CLASS_TO_INDEX[
                aami_class
            ]

            # Apply TRAIN-fitted statistics
            beat_norm = (
                beat - mean_train
            ) / std_train

            X.append(
                beat_norm.astype(np.float32)
            )

            y.append(
                class_index
            )

            metadata.append(
                {
                    "patient_id": patient_id,
                    "record_id": record_id,
                    "r_peak_sample": int(r_peak),
                    "original_symbol": symbol,
                    "aami_class": aami_class,
                    "class_index": class_index,
                    "lead_name": "MLII",
                    "lead_index": lead_idx,
                }
            )


    X = np.asarray(
        X,
        dtype=np.float32
    )

    y = np.asarray(
        y,
        dtype=np.int64
    )

    metadata_df = pd.DataFrame(
        metadata
    )


    # --------------------------------------------------
    # Basic invariants
    # --------------------------------------------------

    assert X.ndim == 2

    assert X.shape[1] == WINDOW_SIZE

    assert len(X) == len(y)

    assert len(X) == len(metadata_df)

    assert np.isfinite(X).all()

    assert set(np.unique(y)).issubset(
        {0, 1, 2, 3, 4}
    )


    # --------------------------------------------------
    # Save
    # --------------------------------------------------

    np.save(
        OUTPUT_DIR / f"{split_name}_X.npy",
        X
    )

    np.save(
        OUTPUT_DIR / f"{split_name}_y.npy",
        y
    )

    metadata_df.to_csv(
        OUTPUT_DIR
        / f"{split_name}_metadata.csv",
        index=False
    )


    # --------------------------------------------------
    # Report
    # --------------------------------------------------

    print(
        "X shape:",
        X.shape
    )

    print(
        "y shape:",
        y.shape
    )

    print(
        "X dtype:",
        X.dtype
    )

    print(
        "y dtype:",
        y.dtype
    )

    print(
        "Patients:",
        metadata_df[
            "patient_id"
        ].nunique()
    )

    print(
        "Records:",
        metadata_df[
            "record_id"
        ].nunique()
    )

    print(
        "Class counts:"
    )

    print(
        metadata_df[
            "aami_class"
        ].value_counts()
        .sort_index()
        .to_dict()
    )


print("\nProcessed dataset saved to:")
print(OUTPUT_DIR)

print("\nSTATUS: PASS")