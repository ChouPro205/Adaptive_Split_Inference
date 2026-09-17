from pathlib import Path
from collections import Counter

import wfdb


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "mitdb"

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
# Counters
# --------------------------------------------------

headers = sorted(DATA_DIR.glob("*.hea"))

total_raw_annotations = 0
total_valid_beats = 0
total_boundary_dropped = 0

raw_counts = Counter()
aami_counts = Counter()
ignored_counts = Counter()

processed_records = []
records_without_mlii = []
records_mlii_not_ch0 = []

per_record_results = []


# --------------------------------------------------
# Process every MIT-BIH record
# --------------------------------------------------

for header_path in headers:

    record_id = header_path.stem
    record_path = DATA_DIR / record_id

    # Read header first so we can inspect lead layout
    header = wfdb.rdheader(str(record_path))

    if header.fs != 360:
        raise RuntimeError(
            f"Unexpected sampling rate in record {record_id}: "
            f"{header.fs}"
        )

    # --------------------------------------------------
    # Lead selection
    # --------------------------------------------------

    if "MLII" not in header.sig_name:

        records_without_mlii.append(
            (record_id, header.sig_name)
        )

        continue

    lead_idx = header.sig_name.index("MLII")

    if lead_idx != 0:
        records_mlii_not_ch0.append(
            (record_id, header.sig_name, lead_idx)
        )

    # Load only the selected MLII channel
    record = wfdb.rdrecord(
        str(record_path),
        channels=[lead_idx]
    )

    signal = record.p_signal[:, 0]

    ann = wfdb.rdann(
        str(record_path),
        "atr"
    )

    processed_records.append(record_id)

    record_aami_counts = Counter()

    record_raw_annotations = len(ann.sample)
    record_ignored = 0
    record_boundary_dropped = 0
    record_valid_beats = 0

    total_raw_annotations += record_raw_annotations

    # --------------------------------------------------
    # Annotation -> AAMI -> segmentation
    # --------------------------------------------------

    for r_peak, symbol in zip(
        ann.sample,
        ann.symbol
    ):

        raw_counts[symbol] += 1

        # Ignore non-heartbeat / unsupported symbols
        if symbol not in AAMI_MAP:

            ignored_counts[symbol] += 1
            record_ignored += 1

            continue

        aami_class = AAMI_MAP[symbol]

        start = r_peak - HALF_WINDOW
        end = start + WINDOW_SIZE

        # Boundary rule frozen in STEP 2
        if start < 0 or end > len(signal):

            total_boundary_dropped += 1
            record_boundary_dropped += 1

            continue

        beat = signal[start:end]

        # Invariant: every accepted sample must be 360 samples
        if len(beat) != WINDOW_SIZE:
            raise RuntimeError(
                f"Record {record_id}: "
                f"invalid beat length {len(beat)}"
            )

        aami_counts[aami_class] += 1
        record_aami_counts[aami_class] += 1

        total_valid_beats += 1
        record_valid_beats += 1

    per_record_results.append(
        {
            "record_id": record_id,
            "lead_index": lead_idx,
            "raw_annotations": record_raw_annotations,
            "ignored": record_ignored,
            "boundary_dropped": record_boundary_dropped,
            "valid_beats": record_valid_beats,
            "N": record_aami_counts["N"],
            "S": record_aami_counts["S"],
            "V": record_aami_counts["V"],
            "F": record_aami_counts["F"],
            "Q": record_aami_counts["Q"],
        }
    )


# --------------------------------------------------
# Global consistency check
# --------------------------------------------------

total_aami_beats = sum(aami_counts.values())

assert total_aami_beats == total_valid_beats


# --------------------------------------------------
# Report
# --------------------------------------------------

print("=" * 65)
print("MIT-BIH PREPROCESSING AUDIT")
print("=" * 65)

print(f"\nTotal records found       : {len(headers)}")
print(f"Records processed (MLII)  : {len(processed_records)}")
print(f"Records without MLII      : {len(records_without_mlii)}")


print("\nRECORDS WITHOUT MLII")
print("--------------------")

if records_without_mlii:
    for record_id, leads in records_without_mlii:
        print(f"{record_id}: {leads}")
else:
    print("None")


print("\nMLII NOT AT CHANNEL 0")
print("---------------------")

if records_mlii_not_ch0:
    for record_id, leads, index in records_mlii_not_ch0:
        print(
            f"{record_id}: {leads}, "
            f"MLII index = {index}"
        )
else:
    print("None")


print("\nIGNORED ANNOTATION SYMBOLS")
print("--------------------------")

for symbol, count in ignored_counts.most_common():
    print(f"{symbol!r}: {count}")


print("\nGLOBAL AAMI CLASS COUNTS")
print("------------------------")

for cls in ["N", "S", "V", "F", "Q"]:
    print(f"{cls}: {aami_counts[cls]}")


print("\nGLOBAL SEGMENTATION SUMMARY")
print("---------------------------")

print(
    "Raw annotations in processed records :",
    total_raw_annotations
)

print(
    "Ignored annotations                  :",
    sum(ignored_counts.values())
)

print(
    "Boundary-dropped AAMI beats          :",
    total_boundary_dropped
)

print(
    "Final valid beats                    :",
    total_valid_beats
)


print("\nCONSISTENCY CHECK")
print("-----------------")

expected_valid = (
    total_raw_annotations
    - sum(ignored_counts.values())
    - total_boundary_dropped
)

print("Expected final beats :", expected_valid)
print("Actual final beats   :", total_valid_beats)

if expected_valid == total_valid_beats:
    print("STATUS               : PASS")
else:
    print("STATUS               : FAIL")


print("\nPER-RECORD SUMMARY")
print("------------------")

for result in per_record_results:

    print(
        f"{result['record_id']}: "
        f"lead_idx={result['lead_index']}, "
        f"beats={result['valid_beats']}, "
        f"N={result['N']}, "
        f"S={result['S']}, "
        f"V={result['V']}, "
        f"F={result['F']}, "
        f"Q={result['Q']}"
    )