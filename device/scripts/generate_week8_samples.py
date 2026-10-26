#!/usr/bin/env python3
"""Week 8 sample set (W8-D3) and host references (W8-D4) for G2 at s=2.

Selection from the frozen week 5 official test set (8544 samples, the loader verifies every
artifact hash), W8-D3 as amended by Châu 23/10 so the reference labels cover all 5 classes (the
model predicts none of the 16 true S/F/Q samples as S/F/Q): every true S, F and Q sample (16),
every sample predicted F (1) or Q (8) at s=2, 11 predicted S, 30 true V and 34 true N, the last
three drawn with a fixed seed in that order; the set is kept in test-set order. The 6 samples
whose predictions.csv labels at s=2 differ between FP32 and INT8/FP16 are never drawn and are
reported separately (excluded.csv).

For every sample the dongle path is reproduced on the host: device/week7/head_fast.c (gcc, same
numerics flags; bit-identical to week 4, TC7) -> device/week5/quantization.c -> q/scale ->
C dequantization -> frozen PyTorch tail -> logits. Gates: the argmax equals
prediction_int8_fp16 of ml/results/week5/predictions.csv at s=2 (the W8-D4 reference label);
the PyTorch head + Python quantizer path is compared and reported (q/scale bytes, logits).

Writes into a new --output directory:
  week8_inputs.h      100 exact normalized FP32 inputs + IDs + reference labels (firmware)
  samples.csv         per sample: identity, labels, q/scale SHA-256, reference logits
  excluded.csv        the 6 FP32 != INT8 samples, same columns (not in the firmware set)
  reference_s2.npz    x, q, FP16 scales, logits, labels (laptop tail / KV260 offline checks)
  manifest.json       sources, seed, selection, checks, SHA-256 of every output
The output is deterministic (manifest.json aside: it records time and git state).
Host evidence only: not MCU, radio or KV260 evidence.
Run: ml\\.venv\\Scripts\\python.exe -B device\\scripts\\generate_week8_samples.py --output <new dir>
"""
from __future__ import annotations

import argparse
import csv
import ctypes as ct
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from week5_common import (ROOT, PACKAGE, Quantizer, authenticate, need, sha, write_json,  # noqa: E402
                          quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl)

sys.path.insert(0, str(ROOT / "ml/scripts"))
_spec = importlib.util.spec_from_file_location("frozen_week5_loader", ROOT / "ml/scripts/week5_common.py")
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)

SPLIT = 2
SEED = 20261027                      # first day of week 8
TAKE_ALL = (1, 3, 4)                 # true S, F, Q: taken whole
PRED_TAKE_ALL = (3, 4)               # predicted F, Q at s=2: taken whole
PRED_DRAW = {1: 11}                  # predicted S at s=2: drawn
DRAW = {2: 30, 0: 34}                # true V, N: drawn (after PRED_DRAW)
SET_SIZE = 100
CLASSES = "NSVFQ"
CHECKPOINT_SHA = "9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90"
PREDICTIONS = ROOT / "ml/results/week5/predictions.csv"
WEEK7 = ROOT / "device/week7"
SRC = ROOT / "device/src"
GENERATED = ROOT / "device/generated"
R3_FIRMWARE = ROOT / "ml/results/week4-r3/firmware"
SHIM = ROOT / "device/week8/host_test/head_shim.c"
# Same anchors as build_week7.ps1 / build_week8.ps1 (results/week4 + week5 acceptance).
ANCHORS = {
    R3_FIRMWARE / "head_parameters.h": "3f811758ca6fc6a8fdefa74ff50ccb48031c006e9a12b617604dad033657487b",
    GENERATED / "week4_graph.h": "b91b5cd664cae32f03e49b91669bb337fbea950c575d2b0a0da8959818d37b6c",
}
HEAD_SOURCES = [SHIM, WEEK7 / "head_fast.c", WEEK7 / "head_fast.h", SRC / "week4_head.c",
                SRC / "week4_head.h", ROOT / "device/week5/quantization.c",
                ROOT / "device/week5/quantization.h", *ANCHORS]
FIELDS = ["set_index", "test_index", "selected_by", "sample_id", "patient_id", "record_id", "true_label",
          "true_class", "prediction_fp32", "label_ref_int8_fp16", "label_host", "q_sha256",
          "scale_sha256", "torch_path_q_equal", "torch_path_scale_equal",
          "head_c_vs_torch_max_abs", "logit_0", "logit_1", "logit_2", "logit_3", "logit_4"]


def build_head(directory: Path) -> ct.CDLL:
    for path, digest in ANCHORS.items():
        need(path.is_file() and sha(path) == digest, f"R3 anchor differs: {path} (build_week4_head.ps1)")
    cc = os.environ.get("CC") or shutil.which("gcc")
    need(cc is not None, "gcc not found (set CC)")
    out = directory / ("week8_head_shim.dll" if os.name == "nt" else "week8_head_shim.so")
    subprocess.run([cc, "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
                    "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
                    "-I", str(WEEK7), "-I", str(SRC), "-I", str(GENERATED), "-I", str(R3_FIRMWARE),
                    "-o", str(out), str(SHIM), str(WEEK7 / "head_fast.c")], check=True)
    lib = ct.CDLL(str(out))
    lib.shim_head.argtypes = [ct.c_uint, ct.POINTER(ct.c_float), ct.POINTER(ct.c_uint32), ct.c_uint]
    lib.shim_head.restype = ct.c_int
    return lib


def run_head(lib: ct.CDLL, x: np.ndarray) -> np.ndarray:
    x = np.ascontiguousarray(x, dtype=np.float32).reshape(360)
    out = np.empty(ml.SHAPES[SPLIT], np.float32)
    n = lib.shim_head(SPLIT, x.ctypes.data_as(ct.POINTER(ct.c_float)),
                      out.ctypes.data_as(ct.POINTER(ct.c_uint32)), out.size)
    need(n == out.size, f"C head returned {n} elements")
    return out


def select(labels: np.ndarray, predicted: np.ndarray, mismatch: set) -> tuple[dict, list]:
    """test index -> selected_by, and the excluded indices."""
    rng = np.random.default_rng(SEED)
    chosen = {i: f"true_{CLASSES[labels[i]]}" for i in range(len(labels)) if labels[i] in TAKE_ALL}
    need(not mismatch.intersection(chosen), "A true S/F/Q sample is FP32 != INT8 at s=2: W8-D3 needs a decision")
    for i in range(len(labels)):
        if predicted[i] in PRED_TAKE_ALL and i not in chosen:
            need(i not in mismatch, "A predicted F/Q sample is FP32 != INT8 at s=2: W8-D3 needs a decision")
            chosen[i] = f"pred_{CLASSES[predicted[i]]}"
    for draws, key, prefix in ((PRED_DRAW, predicted, "pred"), (DRAW, labels, "draw")):
        for label, count in draws.items():
            pool = np.array([i for i in range(len(labels))
                             if key[i] == label and i not in mismatch and i not in chosen])
            for i in rng.choice(pool, size=count, replace=False):
                chosen[int(i)] = f"{prefix}_{CLASSES[label]}"
    need(len(chosen) == SET_SIZE, "Selection size differs")
    return dict(sorted(chosen.items())), sorted(mismatch)


def header(rows: list, x: np.ndarray, set_sha: str) -> str:
    lines = ["/* GENERATED by device/scripts/generate_week8_samples.py - do not edit.",
             f" * W8-D3: {SET_SIZE} frozen week 5 test inputs (exact normalized FP32, test-set order),",
             f" * reference labels W8-D4 = prediction_int8_fp16 at s={SPLIT}. Seed {SEED}. */",
             "#ifndef WEEK8_INPUTS_H", "#define WEEK8_INPUTS_H", "#include <stdint.h>",
             f"#define WEEK8_SAMPLE_COUNT {SET_SIZE}U", f"#define WEEK8_SPLIT {SPLIT}U",
             f'#define WEEK8_SET_SHA256 "{set_sha}"',
             "static const char *const week8_sample_ids[WEEK8_SAMPLE_COUNT] = {"]
    lines += [f"    {json.dumps(r['sample_id'])}," for r in rows]
    lines += ["};", "static const uint8_t week8_reference_labels[WEEK8_SAMPLE_COUNT] = {"]
    labels = [str(r["label_ref_int8_fp16"]) for r in rows]
    lines += ["    " + ", ".join(labels[i:i + 20]) + "," for i in range(0, len(labels), 20)]
    lines += ["};", "static const float week8_inputs[WEEK8_SAMPLE_COUNT][360] = {"]
    for sample in x[:, 0]:
        lines.append("    {")
        for start in range(0, 360, 6):
            lines.append("        " + ", ".join(float(v).hex() + "f" for v in sample[start:start + 6]) + ",")
        lines.append("    },")
    lines += ["};", "#endif"]
    return "\n".join(lines) + "\n"


def set_digest(ids: list, x: np.ndarray) -> str:
    """SHA-256 of the ordered IDs (UTF-8, one per line) followed by the FP32 LE input bytes."""
    digest = hashlib.sha256("".join(i + "\n" for i in ids).encode("utf-8"))
    digest.update(np.ascontiguousarray(x, dtype="<f4").tobytes())
    return digest.hexdigest()


def write_csv(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sources = [p.relative_to(ROOT).as_posix() for p in (Path(__file__).resolve(), SHIM)]
    return {"head": run("rev-parse", "HEAD"), "status_of_generator_sources": run("status", "--short", "--", *sources)}


def generate(output: Path) -> dict:
    need(not output.exists(), "Use a new output directory")
    _, proof, _ = authenticate()
    model, _ = ml.baseline(ROOT / PACKAGE)
    need(sha(ROOT / PACKAGE / "model/checkpoint.pt") == CHECKPOINT_SHA, "Checkpoint differs from week 5")
    checkpoint = torch.load(ROOT / PACKAGE / "model/checkpoint.pt", map_location="cpu", weights_only=True)
    x_all, labels, meta, dataset = ml.load_test(checkpoint)
    need(len(labels) == 8544, "Frozen test set count differs")
    with PREDICTIONS.open(encoding="utf-8", newline="") as handle:
        reference = [r for r in csv.DictReader(handle) if int(r["split_point_s"]) == SPLIT]
    need(len(reference) == 8544, "predictions.csv rows at s=2 differ")
    for i, r in enumerate(reference):
        need((r["sample_id"], int(r["true_label"])) == (meta.sample_id.iloc[i], int(labels[i])),
             f"predictions.csv order/label differs at {i}")
    mismatch = {i for i, r in enumerate(reference) if r["prediction_fp32"] != r["prediction_int8_fp16"]}
    need(len(mismatch) == 6, f"Expected 6 FP32 != INT8 samples at s=2, found {len(mismatch)}")
    predicted_all = np.array([int(r["prediction_int8_fp16"]) for r in reference])
    selected_by, excluded = select(labels, predicted_all, mismatch)
    chosen = list(selected_by)

    output.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="week8_samples_"))
    lib = build_head(work)
    quant = Quantizer(work, os.environ.get("CC") or "gcc")
    head, tail = ml.wrappers(model, SPLIT)

    def evaluate(indices: list) -> tuple[list, dict]:
        rows = []
        arrays = {"x": [], "q": [], "scale_f16": [], "logits": []}
        with torch.inference_mode():
            for k, i in enumerate(indices):
                x = x_all[i:i + 1]
                z = run_head(lib, x)
                q, scale = quant.quantize(z)
                stored = np.frombuffer(scale.tobytes(), "<f2").reshape(scale.shape).copy()
                restored = quant.dequantize(q, stored)
                need(restored.tobytes() == dequantize_per_channel(q, stored).tobytes(), "C dequantization differs")
                logits = tail(torch.from_numpy(from_ncl(restored, SPLIT))).numpy().astype(np.float32)
                need(np.isfinite(logits).all(), "Nonfinite tail output")
                zt = np.ascontiguousarray(to_ncl(head(torch.from_numpy(x.copy())).numpy(), SPLIT))
                qt, st = quantize_per_channel(zt)
                r = reference[i]
                rows.append({
                    "set_index": k, "test_index": i, "selected_by": selected_by.get(i, "excluded"),
                    "sample_id": r["sample_id"],
                    "patient_id": meta.patient_id.iloc[i], "record_id": meta.record_id.iloc[i],
                    "true_label": int(labels[i]), "true_class": CLASSES[int(labels[i])],
                    "prediction_fp32": int(r["prediction_fp32"]),
                    "label_ref_int8_fp16": int(r["prediction_int8_fp16"]),
                    "label_host": int(logits.argmax(axis=1)[0]),
                    "q_sha256": hashlib.sha256(q.tobytes()).hexdigest(),
                    "scale_sha256": hashlib.sha256(scale.tobytes()).hexdigest(),
                    "torch_path_q_equal": int(q.tobytes() == qt.tobytes()),
                    "torch_path_scale_equal": int(scale.tobytes() == st.tobytes()),
                    "head_c_vs_torch_max_abs": float(np.max(np.abs(z.astype(np.float64) - zt.astype(np.float64)))),
                    **{f"logit_{c}": repr(float(v)) for c, v in enumerate(logits[0])}})
                arrays["x"].append(x[0])
                arrays["q"].append(q[0])
                arrays["scale_f16"].append(stored[0])
                arrays["logits"].append(logits[0])
        return rows, {k: np.stack(v) for k, v in arrays.items()}

    rows, arrays = evaluate(chosen)
    excluded_rows, _ = evaluate(excluded)
    ids = [r["sample_id"] for r in rows]
    set_sha = set_digest(ids, arrays["x"])
    (output / "week8_inputs.h").write_text(header(rows, arrays["x"], set_sha), encoding="utf-8", newline="\n")
    write_csv(output / "samples.csv", rows)
    write_csv(output / "excluded.csv", excluded_rows)
    with (output / "reference_s2.npz").open("wb") as handle:
        np.savez(handle, sample_id=np.array(ids), test_index=np.array(chosen, np.int32),
                 label_ref=np.array([r["label_ref_int8_fp16"] for r in rows], np.int8),
                 x=arrays["x"], q=arrays["q"], scale_f16=arrays["scale_f16"], logits=arrays["logits"])

    def counts(subset):
        return {c: sum(1 for r in subset if r["true_class"] == c) for c in CLASSES}

    def label_counts(subset):
        return {c: sum(1 for r in subset if r["label_ref_int8_fp16"] == n) for n, c in enumerate(CLASSES)}

    sources = {name: sum(1 for r in rows if r["selected_by"] == name)
               for name in dict.fromkeys(r["selected_by"] for r in rows)}
    checks = {
        "set_size_100_unique": len(set(ids)) == SET_SIZE,
        "all_true_S_F_Q_included": counts(rows)["S"] == 13 and counts(rows)["F"] == 1 and counts(rows)["Q"] == 2,
        "all_predicted_F_Q_included": label_counts(rows)["F"] == int(np.sum(predicted_all == 3))
                                      and label_counts(rows)["Q"] == int(np.sum(predicted_all == 4)),
        "selection_sources": sources == {"true_S": 13, "true_F": 1, "true_Q": 2, "pred_F": 1, "pred_Q": 8,
                                         "pred_S": 11, "draw_V": 30, "draw_N": 34},
        "reference_labels_cover_5_classes": all(label_counts(rows)[c] > 0 for c in CLASSES),
        "no_fp32_int8_mismatch_in_set": not mismatch.intersection(chosen),
        "host_label_equals_reference_100": all(r["label_host"] == r["label_ref_int8_fp16"] for r in rows),
        "excluded_host_label_equals_reference": all(r["label_host"] == r["label_ref_int8_fp16"] for r in excluded_rows),
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "purpose": "Week 8 G2 sample set (W8-D3) and host references (W8-D4); host evidence only",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "git": git_state(),
        "split_point_s": SPLIT, "seed": SEED, "rng": "numpy.random.default_rng(seed).choice without replacement: predicted S, then true V, then true N",
        "selection_rule": "W8-D3 amended 23/10: all true S/F/Q + all predicted F/Q + 11 predicted S + 30 true V + 34 true N; draws never take the 6 FP32 != INT8 samples; test-set order",
        "set_sha256_definition": "SHA-256 of ordered sample IDs (UTF-8, '\\n' after each) then the inputs as FP32 LE [100,1,360]",
        "set_sha256": set_sha,
        "selection_sources": sources,
        "true_class_counts": counts(rows), "reference_label_counts": label_counts(rows),
        "reference_label_equals_true_label": sum(r["label_ref_int8_fp16"] == r["true_label"] for r in rows),
        "excluded": [{k: r[k] for k in ("test_index", "sample_id", "true_class", "prediction_fp32",
                                        "label_ref_int8_fp16", "label_host")} for r in excluded_rows],
        "torch_path_comparison": {
            "q_equal": sum(r["torch_path_q_equal"] for r in rows),
            "scale_equal": sum(r["torch_path_scale_equal"] for r in rows),
            "head_c_vs_torch_max_abs": max(r["head_c_vs_torch_max_abs"] for r in rows),
            "note": "references are the C head path (what the dongle computes); the PyTorch/Python path is the SV3 week 5 pipeline"},
        "checks": checks,
        "pipeline": "device/week7/head_fast.c (host gcc -O2 -ffp-contract=off -fno-fast-math) -> device/week5/quantization.c "
                    "-> C dequantization -> frozen PyTorch tail wrappers(model, 2)[1], CPU FP32, one thread",
        "sources_sha256": {
            **{p.relative_to(ROOT).as_posix(): sha(p) for p in (Path(__file__).resolve(), *HEAD_SOURCES, PREDICTIONS)},
            "checkpoint": CHECKPOINT_SHA,
            "dataset_artifacts": dataset["identifiers"]["processed_artifacts"]},
        "r3_handoff": proof if isinstance(proof, (dict, str)) else str(proof),
        "environment": ml.versions(),
        "outputs_sha256": {name: sha(output / name) for name in
                           ("week8_inputs.h", "samples.csv", "excluded.csv", "reference_s2.npz")},
    }
    write_json(output / "manifest.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = generate(args.output.resolve())
    print(json.dumps({k: report[k] for k in ("status", "set_sha256", "selection_sources", "true_class_counts", "reference_label_counts",
                                             "torch_path_comparison", "checks")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
