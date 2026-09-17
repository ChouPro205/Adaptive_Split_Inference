from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = (
    ROOT
    / "data"
    / "processed"
    / "mitdb"
)

EXPECTED = {
    "train": {
        "samples": 81094,
        "patients": 34,
        "records": 35,
    },
    "val": {
        "samples": 15388,
        "patients": 7,
        "records": 7,
    },
    "test": {
        "samples": 8544,
        "patients": 4,
        "records": 4,
    },
}


results = {}


for split in ["train", "val", "test"]:

    print("\n" + "=" * 60)
    print(split.upper())
    print("=" * 60)

    X_path = DATA_DIR / f"{split}_X.npy"
    y_path = DATA_DIR / f"{split}_y.npy"
    metadata_path = (
        DATA_DIR
        / f"{split}_metadata.csv"
    )

    # ------------------------------------------
    # Files must exist
    # ------------------------------------------

    assert X_path.exists()
    assert y_path.exists()
    assert metadata_path.exists()

    # ------------------------------------------
    # Reload FROM DISK
    # ------------------------------------------

    X = np.load(X_path)
    y = np.load(y_path)

    metadata = pd.read_csv(
        metadata_path,
        dtype={
            "patient_id": str,
            "record_id": str,
        }
    )

    # ------------------------------------------
    # Shapes / dtypes
    # ------------------------------------------

    assert X.shape == (
        EXPECTED[split]["samples"],
        360,
    )

    assert y.shape == (
        EXPECTED[split]["samples"],
    )

    assert len(metadata) == len(X)

    assert X.dtype == np.float32
    assert y.dtype == np.int64

    # ------------------------------------------
    # Numerical integrity
    # ------------------------------------------

    assert np.isfinite(X).all()

    # ------------------------------------------
    # Label integrity
    # ------------------------------------------

    metadata_y = (
        metadata["class_index"]
        .to_numpy(dtype=np.int64)
    )

    assert np.array_equal(
        y,
        metadata_y,
    )

    assert set(np.unique(y)).issubset(
        {0, 1, 2, 3, 4}
    )

    # ------------------------------------------
    # Metadata integrity
    # ------------------------------------------

    patients = set(
        metadata["patient_id"]
    )

    records = set(
        metadata["record_id"]
    )

    assert (
        len(patients)
        == EXPECTED[split]["patients"]
    )

    assert (
        len(records)
        == EXPECTED[split]["records"]
    )

    # ------------------------------------------
    # Report
    # ------------------------------------------

    results[split] = {
        "patients": patients,
        "records": records,
        "mean": float(X.mean(
            dtype=np.float64
        )),
        "std": float(X.std(
            dtype=np.float64
        )),
    }

    print("X shape      :", X.shape)
    print("y shape      :", y.shape)
    print("X dtype      :", X.dtype)
    print("y dtype      :", y.dtype)
    print("Patients     :", len(patients))
    print("Records      :", len(records))
    print("Finite       :", np.isfinite(X).all())
    print(
        "Labels match :",
        np.array_equal(y, metadata_y)
    )

    print(
        "Mean         :",
        results[split]["mean"]
    )

    print(
        "Std          :",
        results[split]["std"]
    )


# --------------------------------------------------
# Patient leakage
# --------------------------------------------------

print("\n" + "=" * 60)
print("PATIENT LEAKAGE CHECK")
print("=" * 60)

train_patients = results["train"][
    "patients"
]

val_patients = results["val"][
    "patients"
]

test_patients = results["test"][
    "patients"
]


train_val = (
    train_patients
    & val_patients
)

train_test = (
    train_patients
    & test_patients
)

val_test = (
    val_patients
    & test_patients
)


print(
    "train ∩ val :",
    train_val
)

print(
    "train ∩ test:",
    train_test
)

print(
    "val ∩ test  :",
    val_test
)


assert not train_val
assert not train_test
assert not val_test


# --------------------------------------------------
# Normalization check
# --------------------------------------------------

print("\n" + "=" * 60)
print("NORMALIZATION CHECK")
print("=" * 60)

train_mean = results["train"]["mean"]
train_std = results["train"]["std"]

mean_ok = abs(train_mean) < 1e-5
std_ok = abs(train_std - 1.0) < 1e-5

print(
    "Train mean ~ 0:",
    mean_ok
)

print(
    "Train std ~ 1 :",
    std_ok
)

assert mean_ok
assert std_ok


print("\nSTATUS: PASS")