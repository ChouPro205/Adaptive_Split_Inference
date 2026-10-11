"""Authenticated Week 4 baseline and unchanged full-test loader."""
from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
import pandas as pd
import torch
from mitdb_week2_data import load_week1_splits
from week1_common import configured_path
from week3_common import CHECKPOINT, sha, need, write_json
from week3_sv2_common import (authenticate, load_frozen, configure, samples, wrappers,
                            SHAPES, split_map, versions)
from quantization import VERSION

ROOT = Path(__file__).resolve().parents[2]
BASE = "9bce483ddbf3be2ca471e522833352ab18331736"
R4_MAIN = "23b2b7d3fa152fcc50296a93ff592b42e00af943"
ANCHOR = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
PACKAGE = ROOT / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"


def baseline(package=PACKAGE):
    manifest = authenticate(package, ANCHOR)
    configure()
    model = load_frozen(package).float().eval()
    return model, manifest


def load_test(checkpoint):
    config, identifiers, arrays = load_week1_splits()
    need(identifiers == checkpoint["provenance"]["dataset_artifacts"],
         "Dataset identifiers differ from frozen checkpoint")
    directory = configured_path(config, "processed_dir")
    summaries = {}
    metadata = {}
    for split, (x, y) in arrays.items():
        meta = pd.read_csv(directory / f"{split}_metadata.csv", dtype={"record_id": str, "patient_id": str})
        ids = [f"MIT-BIH:{r.record_id}:{r.r_peak_sample}:{r.lead_name}" for r in meta.itertuples()]
        need(len(set(ids)) == len(ids), f"Duplicate sample_id in {split}")
        meta["sample_id"] = ids
        metadata[split] = meta
        summaries[split] = {"num_samples": len(y), "class_counts": {k: int(np.count_nonzero(y == v)) for k, v in config["classes"].items()},
                            "patient_ids": sorted(set(meta.patient_id)), "record_ids": sorted(set(meta.record_id))}
    # Existing loader verifies patient overlap, membership, labels and every artifact hash.
    report = {"dataset": config["dataset"], "label_mapping": config["classes"], "identifiers": identifiers,
              "preprocessing": {k: config[k] for k in ("lead", "segmentation", "filtering", "normalization")},
              "resample": "none; native 360 Hz", "split_manifest": "ml/manifests/mitdb_patient_split.csv",
              "patient_leakage_check": "PASS; official metadata incl. records 201/202 as one patient",
              "splits": summaries, "input_dtype": "<f4", "model_input_shape": [len(arrays['test'][1]), 1, 360],
              "patient_id_policy": "Existing public pseudonyms P<record>; not newly generated identities"}
    x, y = arrays["test"]
    return np.array(x[:, None, :], dtype=np.float32, order="C", copy=True), y, metadata["test"], report


def provenance(command):
    paths = [ROOT / "ml/src/quantization.py", ROOT / "ml/src/p1.py", *sorted((ROOT / "ml/scripts").glob("*week5*.py")),
             ROOT / "contracts/i2_ref/i2_reference.py", ROOT / "contracts/i2_protection_v1.md",
             ROOT / "ml/src/week5_interfaces.py", ROOT / "contracts/sv3_week5_ml_registry_v1.json"]
    return {"baseline_main_commit": BASE, "week4_r4_merge_commit": R4_MAIN,
            "week4_artifact_generation_commit": "89109fd352d84a5fe0815d7e045e52538de7bad8",
            "checkpoint_sha256": CHECKPOINT, "week3_manifest_sha256": ANCHOR,
            "quantization_version": VERSION, "environment": versions(), "command": command,
            "source_git_commit_at_execution": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_files_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in paths},
            "mode": "CPU FP32 eval/inference; deterministic; one thread; MKLDNN disabled"}


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def mapping():
    return [{"split_point_s": r["split_id"], "cut_name": r["head_endpoint"], "shape": r["shape_N1"],
             "layout": r["layout"], "channel_axis": 1, "channels": SHAPES[r["split_id"]][1],
             "num_elements": int(np.prod(SHAPES[r["split_id"]])), "num_scales_N1": SHAPES[r["split_id"]][1],
             "quantization_shape": list(SHAPES[r["split_id"]]) + ([1] if r["split_id"] >= 9 else []),
             "tail": f"wrappers(model, {r['split_id']})[1]", "tail_start": r["tail_start"],
             "tail_type": r["tail_type"]} for r in split_map()]
