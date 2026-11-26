"""Build and check the S0c v1 golden set; compare the reference with the 2026-11-20 probe.

Place this file, s0c_v1_ref.py, codec_probe.py and check_wire.py in one folder three levels
below the repo root (for example <repo>/ml/provenance/s0c-v1/), then run from the repo root:
  ml/.venv/Scripts/python.exe -B -X utf8 <folder>/build_s0c_v1.py --archive <SV3_M1_V4_GRID_RESULT_20261103.zip> --out <new dir>
Reads DS1 data only (20 package A golden train beats, 4 DS1 validation records). DS2 is not opened.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / ".private/analysis/compression-20261120"), str(ROOT / "ml/scripts"), str(ROOT / "ml/src")]
import s0c_v1_ref as ref  # noqa: E402
from check_wire import pack  # noqa: E402
from codec_probe import load_c5, transport, validation_only  # noqa: E402
from m1_metrics_v4 import validation_metrics  # noqa: E402
from mitdb_ds1ds2_m1_v3 import load_record  # noqa: E402

DATA = ROOT / "ml/manifests/mitdb-ds1ds2-m1-v3-r2"
GOLDEN_RULE = "package A: DS1 train rows sorted by numeric record_id, then numeric r_peak_sample, then lead_name; first 20"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def golden_beats():
    with (DATA / "split.csv").open(newline="", encoding="utf-8") as f:
        train = sorted((r["record_id"] for r in csv.DictReader(f) if r["split"] == "train"), key=int)
    norm = json.loads((DATA / "normalization.json").read_text(encoding="utf-8"))
    rows, beats = [], []
    for record in train[:1]:
        x, _, meta, _ = load_record(ROOT / "ml/data/raw/mitdb", record)
        order = sorted(range(len(meta)), key=lambda i: (int(meta[i]["record_id"]), int(meta[i]["r_peak_sample"]), meta[i]["lead_name"], i))
        for i in order:
            rows.append(meta[i])
            beats.append(((x[i] - norm["mean"]) / norm["std"]).astype("<f4"))
    if len(rows) < 20:
        raise ValueError("First train record has fewer than 20 beats")
    return np.stack(beats[:20]), rows[:20]


def check_against_probe(archive):
    """Reference vs the torch path of codec_probe on every DS1 validation beat."""
    x, y, _ = validation_only()
    pooled_t = F.adaptive_avg_pool1d(x, 46)
    restored_t, q_t = transport(pooled_t)
    recon_t = F.interpolate(restored_t, size=360, mode="linear", align_corners=False)
    n = len(x)
    stats = {"beats": n, "v46_bitwise_equal": 0, "q_equal": 0, "body_equal": 0, "roundtrip_ok": 0,
             "recon_bitwise_equal": 0, "v46_max_abs_diff": 0.0, "recon_max_abs_diff": 0.0}
    sizes, recon_ref = np.empty(n), np.empty((n, 360), dtype=np.float32)
    for i in range(n):
        xi = x[i, 0].numpy()
        v = ref.reduce46(xi)
        vt = pooled_t[i, 0].numpy()
        stats["v46_bitwise_equal"] += int(np.array_equal(v.view(np.uint32), vt.view(np.uint32)))
        stats["v46_max_abs_diff"] = max(stats["v46_max_abs_diff"], float(np.max(np.abs(v - vt))))
        body, scale, q = ref.encode(xi)
        stats["q_equal"] += int(np.array_equal(q, q_t[i, 0]))
        stats["body_equal"] += int(body == pack(q_t[i, 0]))
        sizes[i] = len(body)
        v_hat, recon = ref.decode(body, scale)
        stats["roundtrip_ok"] += int(np.array_equal(ref.rice_decode(body), q))
        recon_ref[i] = recon
        rt = recon_t[i, 0].numpy()
        stats["recon_bitwise_equal"] += int(np.array_equal(recon.view(np.uint32), rt.view(np.uint32)))
        stats["recon_max_abs_diff"] = max(stats["recon_max_abs_diff"], float(np.max(np.abs(recon - rt))))
    stats["body_B_mean"] = float(sizes.mean())
    stats["body_B_p95"] = float(np.percentile(sizes, 95))
    stats["body_B_max"] = int(sizes.max())
    model, checkpoint = load_c5(Path(archive))
    metrics = json.loads((DATA / "metric-policy.json").read_text(encoding="utf-8"))
    with torch.inference_mode():
        pred = np.concatenate([model(torch.from_numpy(recon_ref[i:i + 256, None, :])).argmax(1).numpy() for i in range(0, n, 256)])
        pred_t = np.concatenate([model(recon_t[i:i + 256]).argmax(1).numpy() for i in range(0, n, 256)])
    stats["macro_f1_reference"] = validation_metrics(y, pred, metrics)["validation_macro_f1_K_fixed"]
    stats["macro_f1_probe_path"] = validation_metrics(y, pred_t, metrics)["validation_macro_f1_K_fixed"]
    stats["label_agreement_reference_vs_probe"] = int((pred == pred_t).sum())
    stats["checkpoint_sha256"] = checkpoint["sha256"]
    return stats


def main(out, archive):
    out = Path(out)
    out.mkdir(parents=False, exist_ok=False)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    x, rows = golden_beats()
    bodies, scales, qs, v46, recon = [], [], [], [], []
    for xi in x:
        body, scale, q = ref.encode(xi)
        v_hat, r = ref.decode(body, scale)
        if not np.array_equal(ref.rice_decode(body), q):
            raise ValueError("Golden roundtrip failed")
        bodies.append(body)
        scales.append(scale)
        qs.append(q)
        v46.append(v_hat)
        recon.append(r)
    arrays = {"x": x.astype("<f4"), "reduced_v46": np.stack([ref.reduce46(xi) for xi in x]).astype("<f4"),
              "q": np.stack(qs).astype("i1"), "scale_fp16": np.asarray(scales, dtype="<f2"),
              "dequantized_v46": np.stack(v46).astype("<f4"), "reconstructed_x360": np.stack(recon).astype("<f4")}
    np.savez(out / "s0c_v1_golden20.npz", **arrays)
    golden = {
        "version": ref.VERSION,
        "reference_sha256": sha((HERE / "s0c_v1_ref.py").read_bytes()),
        "golden_rule": GOLDEN_RULE,
        "check_against_package_A": "np.array_equal(x, golden/z_s0.npy[:, 0, :]) must hold for the package A golden beats",
        "array_sha256": {k: sha(np.ascontiguousarray(v).tobytes()) for k, v in arrays.items()},
        "beats": [{"index": i, "record_id": r["record_id"], "r_peak_sample": int(r["r_peak_sample"]), "original_symbol": r["original_symbol"], "aami_class": r["aami_class"],
                   "scale_fp16_le_hex": np.asarray(scales[i], dtype="<f2").tobytes().hex(), "rice_k": bodies[i][1],
                   "body_len_B": len(bodies[i]), "body_hex": bodies[i].hex(), "q": [int(t) for t in qs[i]]}
                  for i, r in enumerate(rows)],
    }
    (out / "s0c_v1_golden20.json").write_text(json.dumps(golden, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    check = check_against_probe(archive)
    (out / "s0c_v1_check_ds1val.json").write_text(json.dumps(check, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(check, indent=1))
    print("golden body lengths:", [len(b) for b in bodies])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--archive", required=True, help="SV3_M1_V4_GRID_RESULT_20261103.zip (checkpoint A is checked by SHA-256)")
    a = p.parse_args()
    main(a.out, a.archive)
