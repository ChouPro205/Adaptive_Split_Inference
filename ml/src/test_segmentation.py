"""Smoke-test config-driven MIT-BIH beat segmentation on one record."""

from __future__ import annotations

from collections import Counter

import numpy as np

from mitdb_common import iter_valid_beats, load_signal_and_annotations, validate_raw_files
from week1_common import load_config, require, run_cli


def main() -> None:
    _, config = load_config("mitdb_week1_config.json")
    raw_dir, records = validate_raw_files(config)
    record_id = records[0]
    _, signal, annotations, lead_index = load_signal_and_annotations(raw_dir, record_id, config)
    beats = []
    counts: Counter[str] = Counter()
    for beat, _, _, aami_class, _ in iter_valid_beats(signal, annotations, config):
        beats.append(beat)
        counts[aami_class] += 1
    array = np.asarray(beats, dtype=np.float32)
    window = int(config["segmentation"]["window_size"])
    require(len(array) > 0, f"No valid beats segmented from record {record_id}")
    require(array.ndim == 2 and array.shape[1] == window,
            f"Unexpected segmentation shape: {array.shape}")
    require(np.isfinite(array).all(), "Segmented beats contain non-finite values")
    print(f"Record / lead index: {record_id} / {lead_index}")
    print(f"Beat shape         : {array.shape}")
    print(f"Beat dtype         : {array.dtype}")
    print(f"AAMI counts        : {dict(counts)}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
