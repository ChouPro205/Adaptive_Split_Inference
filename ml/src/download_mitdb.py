from pathlib import Path
import wfdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "mitdb"

OUT_DIR.mkdir(parents=True, exist_ok=True)

print("Downloading MIT-BIH Arrhythmia Database...")
print("Destination:", OUT_DIR)

wfdb.dl_database(
    "mitdb",
    str(OUT_DIR),
)

print("MIT-BIH download complete.")