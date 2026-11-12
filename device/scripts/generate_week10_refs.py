#!/usr/bin/env python3
"""Week 10 host references for the KV260 (W10-D4): reference_s0.npz .. reference_s9.npz.

Samples: set_index 0..49 of the W8-D3 set (the same 50 samples as W9-D3/W9-D6), in set order.
For every (sample, s) the dongle path is reproduced on the host exactly as in week 9:
device/week9/host_test/dev_shim.c + device/week7/head_fast.c + device/week5/quantization.c (gcc,
-ffp-contract=off -fno-fast-math) -> q/scale, then C dequantization (week 5) -> frozen PyTorch tail
wrappers(model, s)[1] of the week 3 package (checkpoint 9b8be076...) -> logits, label = argmax.
s10 (device-only) is not sent to the edge, so it has no file.

Gates (status PASS only if all hold):
  - the W8-D3 set authenticates (anchors), the shim inputs/IDs/set SHA equal the set;
  - shape and payload bytes of every s equal results/week5/device/tensor_sizes.csv;
  - q/scale SHA-256 of every (sample, s) equal the week 9 refs.csv (W9-D6, what VERIFY ALL checked on the dongle);
  - at s=2: q, scale and logits are bit-identical to W8-D3 reference_s2.npz (week 8 G2 references);
  - all logits finite.
Reported, not gated: agreement of the host label with prediction_int8_fp16 / prediction_fp32 of
ml/results/week5/predictions.csv (that path uses the PyTorch head + Python quantizer), and whether the
PyTorch head + Python quantizer reproduce the C q/scale bytes.

Writes into a new --output directory (all deterministic except manifest.json):
  reference_s{s}.npz  same keys and dtypes as reference_s2.npz of week 8:
                      sample_id, test_index, label_ref (int8), x (50,1,360) f32,
                      q (50,C,L) int8, scale_f16 (50,C) f16, logits (50,5) f32
  sample_order.csv    set_index, sample_id, test_index, true_label (the order of every file)
  refs.csv            one row per (sample, s): shape, bytes, q/scale SHA-256, labels, logits
  manifest.json       sources, checks, label agreement, SHA-256 of every output
  SHA256SUMS.txt      sha256sum -c format, LF
Host evidence only: not MCU, radio or KV260 evidence.
Run: ml\\.venv\\Scripts\\python.exe -B device\\scripts\\generate_week10_refs.py
         --samples <W8-D3 dir> --week9-refs <week 9 refs dir> --output <new dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from week5_common import (ROOT, PACKAGE, Quantizer, need, sha,  # noqa: E402
                          quantize_per_channel, to_ncl, from_ncl)
import week9_common as w9  # noqa: E402
import generate_week9_refs as g9  # noqa: E402

w8 = w9.w8
sys.path.insert(0, str(ROOT / "ml/scripts"))
_spec = importlib.util.spec_from_file_location("frozen_week5_loader", ROOT / "ml/scripts/week5_common.py")
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)

SPLITS = range(10)                   # s0..s9 go to the edge; s10 is device-only
ROUNDS = w9.ROUNDS                   # 50
CHECKPOINT_SHA = "9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90"
PREDICTIONS = ROOT / "ml/results/week5/predictions.csv"
NPZ_KEYS = ("sample_id", "test_index", "label_ref", "x", "q", "scale_f16", "logits")
REFS_FIELDS = ["set_index", "sample_id", "test_index", "true_label", "split", "channels", "length",
               "bytes_q", "bytes_scale", "bytes_payload", "q_sha256", "scale_sha256", "label_host",
               "pred_csv_int8_fp16", "pred_csv_fp32", "torch_path_q_equal", "torch_path_scale_equal",
               "logit_0", "logit_1", "logit_2", "logit_3", "logit_4"]


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sources = [p.relative_to(ROOT).as_posix() for p in (Path(__file__).resolve(), HERE / "generate_week9_refs.py",
                                                         HERE / "week9_common.py", g9.SHIM)]
    return {"head": run("rev-parse", "HEAD"), "status_of_generator_sources": run("status", "--short", "--", *sources)}


def load_predictions() -> dict:
    """(split, sample_id) -> (prediction_int8_fp16, prediction_fp32) of the week 5 official run."""
    table = {}
    with PREDICTIONS.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            key = (int(r["split_point_s"]), r["sample_id"])
            need(key not in table, f"Duplicate prediction row {key}")
            table[key] = (int(r["prediction_int8_fp16"]), int(r["prediction_fp32"]))
    return table


def generate(samples: Path, week9_refs: Path, output: Path) -> dict:
    need(not output.exists(), "Use a new output directory")
    for path, digest in g9.ANCHORS.items():
        need(sha(path) == digest, f"R3 input {path} differs from the week 4/5 anchor")
    sample_set = w8.load_set(samples)            # authenticates the W8-D3 set
    sizes = w9.tensor_sizes()
    refs9 = w9.load_refs(week9_refs, sample_set)   # authenticated week 9 references (W9-D6)
    with np.load(samples / "reference_s2.npz", allow_pickle=False) as npz:
        w8_npz = {k: npz[k] for k in NPZ_KEYS}
    need(sha(ROOT / PACKAGE / "model/checkpoint.pt") == CHECKPOINT_SHA, "Checkpoint differs from week 5")
    model, _ = ml.baseline(ROOT / PACKAGE)
    predictions = load_predictions()

    work = Path(tempfile.mkdtemp(prefix="week10_refs_"))
    lib = g9.build_shim(work, samples)
    quant = Quantizer(work, os.environ.get("CC") or "gcc")
    x_all = np.ascontiguousarray(w8_npz["x"][:ROUNDS], dtype=np.float32)          # (50,1,360)
    ids = [sample_set.samples[n].sample_id for n in range(ROUNDS)]
    test_index = [sample_set.samples[n].test_index for n in range(ROUNDS)]
    true_label = [sample_set.samples[n].true_label for n in range(ROUNDS)]

    rows, files, checks_by_split = [], {}, {}
    size_ok, refs9_ok, finite_ok = [], [], []
    with torch.inference_mode():
        for s in SPLITS:
            head, tail = ml.wrappers(model, s)
            arrays = {"q": [], "scale_f16": [], "logits": []}
            labels = []
            for n in range(ROUNDS):
                c, length, qb, sb = g9.head_quant(lib, n, s)
                q = np.frombuffer(qb, np.int8).reshape(1, c, length).copy()
                scale = np.frombuffer(sb, "<f2").reshape(1, c).copy()
                restored = quant.dequantize(q, scale)
                logits = tail(torch.from_numpy(from_ncl(restored, s))).numpy().astype(np.float32)
                finite_ok.append(bool(np.isfinite(logits).all()))
                zt = np.ascontiguousarray(to_ncl(head(torch.from_numpy(x_all[n:n + 1].copy())).numpy(), s))
                qt, st = quantize_per_channel(zt)
                label = int(logits.argmax(axis=1)[0])
                pred_q, pred_f = predictions[(s, ids[n])]
                size_ok.append((c, length, len(qb) + len(sb)) == sizes[s])
                ref9 = refs9.get((n, s))
                refs9_ok.append(ref9 is not None and ref9.sample_id == ids[n]
                                and (ref9.q_sha256, ref9.scale_sha256) == (sha_bytes(qb), sha_bytes(sb)))
                rows.append({
                    "set_index": n, "sample_id": ids[n], "test_index": test_index[n], "true_label": true_label[n],
                    "split": s, "channels": c, "length": length, "bytes_q": len(qb), "bytes_scale": len(sb),
                    "bytes_payload": len(qb) + len(sb), "q_sha256": sha_bytes(qb), "scale_sha256": sha_bytes(sb),
                    "label_host": label, "pred_csv_int8_fp16": pred_q, "pred_csv_fp32": pred_f,
                    "torch_path_q_equal": int(qt.tobytes() == q.tobytes()),
                    "torch_path_scale_equal": int(np.asarray(st, "<f2").tobytes() == scale.tobytes()),
                    **{f"logit_{k}": repr(float(v)) for k, v in enumerate(logits[0])}})
                arrays["q"].append(q[0])
                arrays["scale_f16"].append(scale[0])
                arrays["logits"].append(logits[0])
                labels.append(label)
            stacked = {k: np.stack(v) for k, v in arrays.items()}
            name = f"reference_s{s}.npz"
            if not output.exists():
                output.mkdir(parents=True)
            with (output / name).open("wb") as handle:
                np.savez(handle, sample_id=np.array(ids), test_index=np.array(test_index, np.int32),
                         label_ref=np.array(labels, np.int8), x=x_all, q=stacked["q"],
                         scale_f16=stacked["scale_f16"], logits=stacked["logits"])
            split_rows = [r for r in rows if r["split"] == s]
            checks_by_split[str(s)] = {
                "q_shape": list(stacked["q"].shape),
                "bytes_payload": split_rows[0]["bytes_payload"],
                "label_counts_NSVFQ": [labels.count(k) for k in range(5)],
                "label_host_eq_pred_csv_int8_fp16": sum(r["label_host"] == r["pred_csv_int8_fp16"] for r in split_rows),
                "label_host_eq_pred_csv_fp32": sum(r["label_host"] == r["pred_csv_fp32"] for r in split_rows),
                "label_host_eq_true_label": sum(r["label_host"] == r["true_label"] for r in split_rows),
                "torch_path_q_equal": sum(r["torch_path_q_equal"] for r in split_rows),
                "torch_path_scale_equal": sum(r["torch_path_scale_equal"] for r in split_rows),
            }
            files[name] = stacked

    s2 = files["reference_s2.npz"]
    with np.load(output / "reference_s2.npz", allow_pickle=False) as npz:
        reread_keys = tuple(npz.files)
    checks = {
        "shim_ids_equal_set": all(lib.shim_sample_id(n).decode() == ids[n] for n in range(ROUNDS)),
        "shim_set_sha256": lib.shim_set_sha256().decode() == sample_set.set_sha256,
        "x_equal_w8d3_npz_rows_0_49": x_all.tobytes() == np.ascontiguousarray(w8_npz["x"][:ROUNDS], np.float32).tobytes(),
        "rows_500": len(rows) == ROUNDS * len(SPLITS),
        "shape_bytes_equal_tensor_sizes": len(size_ok) == len(rows) and all(size_ok),
        "q_scale_equal_week9_refs": len(refs9_ok) == len(rows) and all(refs9_ok),
        "s2_q_equal_w8d3": s2["q"].tobytes() == w8_npz["q"][:ROUNDS].tobytes(),
        "s2_scale_equal_w8d3": s2["scale_f16"].tobytes() == np.ascontiguousarray(w8_npz["scale_f16"][:ROUNDS], "<f2").tobytes(),
        "s2_logits_bit_equal_w8d3": s2["logits"].tobytes() == np.ascontiguousarray(w8_npz["logits"][:ROUNDS], np.float32).tobytes(),
        "s2_label_equal_w8d3": [int(v) for v in np.argmax(s2["logits"], axis=1)] == [int(v) for v in w8_npz["label_ref"][:ROUNDS]],
        "logits_finite": all(finite_ok),
        "npz_keys_equal_week8": set(reread_keys) == set(NPZ_KEYS),
    }

    with (output / "sample_order.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["set_index", "sample_id", "test_index", "true_label"])
        writer.writerows([n, ids[n], test_index[n], true_label[n]] for n in range(ROUNDS))
    with (output / "refs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REFS_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    outputs = [f"reference_s{s}.npz" for s in SPLITS] + ["sample_order.csv", "refs.csv"]
    status = "PASS" if all(checks.values()) else "FAIL"
    manifest = {
        "schema": "week10-refs/1",
        "status": status,
        "decision": "W10-D4 (KV260 offline references for the every-s session)",
        "samples_dir": str(samples),
        "set_sha256": sample_set.set_sha256,
        "samples": f"W8-D3 set_index 0..{ROUNDS - 1} (same as W9-D3), set order in every file",
        "splits": list(SPLITS),
        "label_ref_definition": "argmax of the host logits of this file (dongle C head + week 5 quantizer -> C dequantization -> frozen PyTorch tail); "
                                "the binding label in the session is the KV260 offline prediction",
        "pipeline": "device/week9/host_test/dev_shim.c + device/week7/head_fast.c + device/week5/quantization.c "
                    "(gcc -O2 -ffp-contract=off -fno-fast-math) -> week5 C dequantization -> wrappers(model, s)[1], CPU FP32",
        "model": {"package": PACKAGE.as_posix() if hasattr(PACKAGE, "as_posix") else str(PACKAGE),
                  "checkpoint_sha256": CHECKPOINT_SHA,
                  "kv260_xmodel_model_sha256_expected": "68c5f86b5ca60479176aa7a5da0e9fef5b79ac436b43468e8ba0ae5353deeaa9 (old xmodel set, week 9 SV2)"},
        "checks": checks,
        "per_split": checks_by_split,
        "outputs_sha256": {name: sha(output / name) for name in outputs},
        "sources_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in
                           (Path(__file__).resolve(), HERE / "generate_week9_refs.py", HERE / "week9_common.py",
                            PREDICTIONS, *g9.SOURCES)},
        "inputs_sha256": {"w8d3/reference_s2.npz": sha(samples / "reference_s2.npz"),
                          "week9/refs.csv": sha(week9_refs / "refs.csv")},
        "r3_binding": "head_parameters.h + week4_graph.h anchors (same as build_week7..9); week5_common.authenticate() not used: it reads results/week4/week4_mcu_validation.json, moved by the results/ reorganisation (PR #37)",
        "environment": ml.versions(),
        "git": git_state(),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sums = [f"{sha(output / name)}  {name}" for name in [*outputs, "manifest.json"]]
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory (samples-20261023-c)")
    parser.add_argument("--week9-refs", type=Path, required=True, help="week 9 refs directory (refs.csv, W9-D6)")
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    args = parser.parse_args()
    manifest = generate(args.samples.resolve(), args.week9_refs.resolve(), args.output.resolve())
    for name, ok in manifest["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    for s, info in manifest["per_split"].items():
        print(f"s{s}: q{info['q_shape']} payload {info['bytes_payload']} B, labels NSVFQ {info['label_counts_NSVFQ']}, "
              f"=int8csv {info['label_host_eq_pred_csv_int8_fp16']}/50, =fp32csv {info['label_host_eq_pred_csv_fp32']}/50, "
              f"torch q/scale {info['torch_path_q_equal']}/{info['torch_path_scale_equal']}")
    print(f"RESULT: {manifest['status']}")
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
