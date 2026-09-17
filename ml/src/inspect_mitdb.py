from pathlib import Path
from collections import Counter

import wfdb


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "mitdb"

headers = sorted(DATA_DIR.glob("*.hea"))

lead_combinations = Counter()
sampling_rates = Counter()
signal_lengths = Counter()

records_no_mlii = []
records_mlii_not_ch0 = []

for header in headers:
    record_name = header.stem
    record_path = DATA_DIR / record_name

    record = wfdb.rdheader(str(record_path))

    leads = tuple(record.sig_name)

    # Tổng hợp thống kê chung
    lead_combinations[leads] += 1
    sampling_rates[record.fs] += 1
    signal_lengths[record.sig_len] += 1

    # Kiểm tra MLII có tồn tại không
    if "MLII" not in record.sig_name:
        records_no_mlii.append(
            (record_name, record.sig_name)
        )

    # Nếu có MLII nhưng không nằm ở channel 0
    else:
        mlii_index = record.sig_name.index("MLII")

        if mlii_index != 0:
            records_mlii_not_ch0.append(
                (record_name, record.sig_name, mlii_index)
            )


print("=" * 60)
print("MIT-BIH DATASET INSPECTION")
print("=" * 60)

print("\nNumber of records:")
print(f"  {len(headers)}")

print("\nSampling rates:")
for fs, count in sorted(sampling_rates.items()):
    print(f"  {fs} Hz: {count} records")

print("\nSignal lengths:")
for length, count in sorted(signal_lengths.items()):
    print(f"  {length}: {count} records")

print("\nLead combinations:")
for leads, count in lead_combinations.items():
    print(f"  {leads}: {count} records")


print("\n" + "=" * 60)
print("MLII CHECK")
print("=" * 60)

print("\nRecords WITHOUT MLII:")
if records_no_mlii:
    for record_name, leads in records_no_mlii:
        print(
            f"  NO MLII: {record_name} -> {leads}"
        )
else:
    print("  None")


print("\nRecords where MLII is NOT channel 0:")
if records_mlii_not_ch0:
    for record_name, leads, index in records_mlii_not_ch0:
        print(
            f"  MLII NOT CHANNEL 0: "
            f"{record_name} -> {leads}, "
            f"MLII index = {index}"
        )
else:
    print("  None")


print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

num_records = len(headers)
num_no_mlii = len(records_no_mlii)
num_with_mlii = num_records - num_no_mlii
num_mlii_not_ch0 = len(records_mlii_not_ch0)

print(f"Total records           : {num_records}")
print(f"Records with MLII       : {num_with_mlii}")
print(f"Records without MLII    : {num_no_mlii}")
print(f"MLII not at channel 0   : {num_mlii_not_ch0}")