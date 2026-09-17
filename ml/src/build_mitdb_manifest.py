from pathlib import Path
import csv
import random

import wfdb


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data" / "raw" / "mitdb"
MANIFEST_DIR = ROOT / "manifests"

MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = MANIFEST_DIR / "mitdb_patient_split.csv"


SEED = 30

TRAIN_RATIO = 0.75
VAL_RATIO = 0.15
TEST_RATIO = 0.10


# --------------------------------------------------
# Patient identity rule
# --------------------------------------------------
#
# MIT-BIH has 48 records from 47 subjects.
# Records 201 and 202 belong to the same subject.
#
# All other records are treated as separate patients.
# --------------------------------------------------

def get_patient_id(record_id):

    if record_id in {"201", "202"}:
        return "P201_202"

    return f"P{record_id}"


# --------------------------------------------------
# Inspect all records
# --------------------------------------------------

headers = sorted(DATA_DIR.glob("*.hea"))

rows = []

eligible_patient_to_records = {}


for header_path in headers:

    record_id = header_path.stem
    record_path = DATA_DIR / record_id

    header = wfdb.rdheader(str(record_path))

    patient_id = get_patient_id(record_id)

    has_mlii = "MLII" in header.sig_name

    if has_mlii:

        lead_index = header.sig_name.index("MLII")

        eligibility = "eligible"
        exclusion_reason = ""

        eligible_patient_to_records.setdefault(
            patient_id,
            []
        ).append(record_id)

    else:

        lead_index = ""

        eligibility = "excluded"
        exclusion_reason = "missing_mlii"

    rows.append(
        {
            "record_id": record_id,
            "patient_id": patient_id,
            "has_mlii": has_mlii,
            "mlii_index": lead_index,
            "eligibility": eligibility,
            "exclusion_reason": exclusion_reason,
            "split": "",
        }
    )


# --------------------------------------------------
# Patient-wise deterministic split
# --------------------------------------------------

patient_ids = sorted(
    eligible_patient_to_records.keys()
)

print("Eligible patients:", len(patient_ids))


rng = random.Random(SEED)

rng.shuffle(patient_ids)


num_patients = len(patient_ids)

n_train = round(
    num_patients * TRAIN_RATIO
)

n_val = round(
    num_patients * VAL_RATIO
)

n_test = (
    num_patients
    - n_train
    - n_val
)


train_patients = set(
    patient_ids[:n_train]
)

val_patients = set(
    patient_ids[
        n_train:
        n_train + n_val
    ]
)

test_patients = set(
    patient_ids[
        n_train + n_val:
    ]
)


# --------------------------------------------------
# Leakage checks
# --------------------------------------------------

assert train_patients.isdisjoint(
    val_patients
)

assert train_patients.isdisjoint(
    test_patients
)

assert val_patients.isdisjoint(
    test_patients
)

assert (
    len(train_patients)
    + len(val_patients)
    + len(test_patients)
    == num_patients
)


# --------------------------------------------------
# Assign split to each record
# --------------------------------------------------

for row in rows:

    if row["eligibility"] != "eligible":
        continue

    patient_id = row["patient_id"]

    if patient_id in train_patients:
        row["split"] = "train"

    elif patient_id in val_patients:
        row["split"] = "val"

    elif patient_id in test_patients:
        row["split"] = "test"

    else:
        raise RuntimeError(
            f"No split assigned to patient {patient_id}"
        )


# --------------------------------------------------
# Write manifest
# --------------------------------------------------

fieldnames = [
    "record_id",
    "patient_id",
    "has_mlii",
    "mlii_index",
    "eligibility",
    "exclusion_reason",
    "split",
]


with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames
    )

    writer.writeheader()
    writer.writerows(rows)


# --------------------------------------------------
# Report
# --------------------------------------------------

print("\nPATIENT SPLIT")
print("----------------")

print(
    "Train patients:",
    len(train_patients)
)

print(
    "Val patients  :",
    len(val_patients)
)

print(
    "Test patients :",
    len(test_patients)
)


print("\nTRAIN")
print(sorted(train_patients))

print("\nVAL")
print(sorted(val_patients))

print("\nTEST")
print(sorted(test_patients))


print("\nSPECIAL RECORDS")
print("----------------")

for row in rows:

    if row["record_id"] in {
        "102",
        "104",
        "114",
        "201",
        "202",
    }:

        print(row)


print("\nMANIFEST")
print("----------------")

print("Saved to:")
print(OUTPUT_FILE)


print("\nLEAKAGE CHECK")
print("----------------")

print(
    "train ∩ val :",
    train_patients & val_patients
)

print(
    "train ∩ test:",
    train_patients & test_patients
)

print(
    "val ∩ test  :",
    val_patients & test_patients
)


print("\nSTATUS: PASS")