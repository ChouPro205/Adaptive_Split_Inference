from pathlib import Path
from collections import Counter

import numpy as np
import wfdb


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "mitdb"

RECORD_ID = "100"

WINDOW_SIZE = 360
HALF_WINDOW = WINDOW_SIZE // 2


# --------------------------------------------------
# AAMI mapping frozen in STEP 2
# --------------------------------------------------

AAMI_MAP = {
    # N
    "N": "N",
    "L": "N",
    "R": "N",
    "e": "N",
    "j": "N",

    # S
    "A": "S",
    "a": "S",
    "J": "S",
    "S": "S",

    # V
    "V": "V",
    "E": "V",

    # F
    "F": "F",

    # Q
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
# Load record
# --------------------------------------------------

record_path = DATA_DIR / RECORD_ID

record = wfdb.rdrecord(str(record_path))
ann = wfdb.rdann(str(record_path), "atr")

print("Record:", RECORD_ID)
print("Sampling rate:", record.fs)
print("Leads:", record.sig_name)


# --------------------------------------------------
# Select MLII by NAME
# --------------------------------------------------

if "MLII" not in record.sig_name:
    raise RuntimeError(
        f"Record {RECORD_ID} does not contain MLII"
    )

lead_idx = record.sig_name.index("MLII")
signal = record.p_signal[:, lead_idx]

print("Selected lead: MLII")
print("Lead index:", lead_idx)


# --------------------------------------------------
# Segment only valid AAMI heartbeat annotations
# --------------------------------------------------

beats = []
metadata = []

raw_counts = Counter()
aami_counts = Counter()
ignored_counts = Counter()

num_dropped_boundary = 0


for r_peak, symbol in zip(ann.sample, ann.symbol):

    raw_counts[symbol] += 1

    # Ignore annotation symbols outside AAMI mapping
    if symbol not in AAMI_MAP:
        ignored_counts[symbol] += 1
        continue

    aami_class = AAMI_MAP[symbol]
    class_index = CLASS_TO_INDEX[aami_class]

    start = r_peak - HALF_WINDOW
    end = start + WINDOW_SIZE

    # Boundary rule
    if start < 0 or end > len(signal):
        num_dropped_boundary += 1
        continue

    beat = signal[start:end]

    if len(beat) != WINDOW_SIZE:
        raise RuntimeError(
            f"Invalid beat length: {len(beat)}"
        )

    beats.append(beat)

    aami_counts[aami_class] += 1

    metadata.append(
        {
            "record_id": RECORD_ID,
            "r_peak_sample": int(r_peak),
            "original_symbol": symbol,
            "aami_class": aami_class,
            "class_index": class_index,
            "lead_name": "MLII",
            "lead_index": lead_idx,
        }
    )


beats = np.asarray(beats, dtype=np.float32)


# --------------------------------------------------
# Report
# --------------------------------------------------

print("\nRAW ANNOTATION COUNTS")
print("---------------------")

for symbol, count in raw_counts.most_common():
    print(f"{symbol!r}: {count}")


print("\nIGNORED ANNOTATIONS")
print("-------------------")

if ignored_counts:
    for symbol, count in ignored_counts.most_common():
        print(f"{symbol!r}: {count}")
else:
    print("None")


print("\nAAMI COUNTS AFTER SEGMENTATION")
print("------------------------------")

for cls in ["N", "S", "V", "F", "Q"]:
    print(f"{cls}: {aami_counts[cls]}")


print("\nSEGMENTATION RESULT")
print("-------------------")

print("Original annotations :", len(ann.sample))
print("Ignored annotations  :", sum(ignored_counts.values()))
print("Boundary dropped     :", num_dropped_boundary)
print("Final beat samples   :", len(beats))
print("Beat array shape     :", beats.shape)
print("Beat dtype           :", beats.dtype)


print("\nFirst 5 samples:")
for item in metadata[:5]:
    print(item)