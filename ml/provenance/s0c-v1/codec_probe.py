"""Exploratory, fixed-codec probe. Run from the repo with ml/.venv/Scripts/python -B.

Read only four DS1 validation records. No fitting or selection on patient data.
Compare the frozen C5 baseline, lossless Rice on quantized S0, three lossy S0
controls (180, 46, 20 time bins) and two fixed two-channel S1 bottlenecks.
The 20- and 46-byte S1 bodies have 10 and 23 bins per channel respectively.
All decoded tails run in host FP32. No deployment or privacy claims.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "ml/scripts"), str(ROOT / "ml/src")]
from m1_metrics_v4 import validation_metrics
from mitdb_baseline_model import MitdbBaselineCNN
from mitdb_ds1ds2_m1_v3 import load_record
from quantization import dequantize_per_channel, quantize_per_channel

RECORDS = ("118", "119", "205", "223")
DATA = ROOT / "ml/manifests/mitdb-ds1ds2-m1-v3-r2"
LOCK = ROOT / "ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json"
ARCHIVE = ROOT.parent / "KyAnh/0511/SV3_M1_V4_GRID_RESULT_20261103.zip"
METHODS = ("fp32", "s0_rice", "s0_rice_180", "s0_rice_46", "s0_rice_20", "s1_20", "s1_46")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validation_only():
    with (DATA / "split.csv").open(newline="", encoding="utf-8") as f:
        ids = tuple(row["record_id"] for row in csv.DictReader(f) if row["split"] == "val")
    if ids != RECORDS:
        raise ValueError("DS1 validation record list differs")
    norm = load_json(DATA / "normalization.json")
    xs, ys, patients = [], [], []
    for record in RECORDS:
        x, y, _, _ = load_record(ROOT / "ml/data/raw/mitdb", record)
        xs.append(((x - norm["mean"]) / norm["std"]).astype("<f4"))
        ys.append(y)
        patients.extend([record] * len(y))
    x, y = np.concatenate(xs), np.concatenate(ys)
    binding = load_json(ROOT / "ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json")["binding"]["data_files"]
    for name, array in (("val_X.npy", x), ("val_y.npy", y)):
        buffer = io.BytesIO()
        np.save(buffer, array, allow_pickle=False)
        if sha(buffer.getvalue()) != binding[name]["sha256"]:
            raise ValueError(f"Development input hash mismatch: {name}")
    return torch.from_numpy(x[:, None, :]), y, np.asarray(patients)


def load_c5(archive):
    deployment = next(c for c in load_json(LOCK)["checkpoints"] if c["role"] == "deployment")
    with ZipFile(archive) as z:
        weights = z.read(deployment["path"])
    if sha(weights) != deployment["sha256"]:
        raise ValueError("Deployment checkpoint hash mismatch")
    checkpoint = torch.load(io.BytesIO(weights), map_location="cpu", weights_only=True)
    model = MitdbBaselineCNN()
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval(), deployment


def rice_body_bytes(q):
    """Exact coded length including first signed value and one k byte; one channel."""
    delta = np.diff(q[:, 0].astype(np.int32), axis=1)
    zigzag = np.where(delta < 0, -2 * delta - 1, 2 * delta)
    bit_counts = [(zigzag >> k).sum(axis=1) + (k + 1) * delta.shape[1] for k in range(8)]
    return 2 + (np.min(bit_counts, axis=0) + 7) // 8


def transport(values):
    q, scale = quantize_per_channel(values.contiguous().numpy())
    return torch.from_numpy(dequantize_per_channel(q, scale)), q


def restore_time(z, steps):
    return F.interpolate(z, size=steps, mode="linear", align_corners=False)


def s1_basis(model):
    # Two fixed directions from the locked conv1 responses to constant +1 and -1
    # inputs. This is a 1x1 projection after time pooling. At the edge its
    # transpose restores channels before interpolation and the original S1 tail.
    weights = model.features[0].weight.detach().sum(dim=(1, 2))
    bias = model.features[0].bias.detach()
    center = F.relu(bias)
    directions = torch.stack([F.relu(bias + w) - center for w in (weights, -weights)], dim=1)
    if torch.linalg.matrix_rank(directions).item() != 2:
        raise ValueError("Conv1 directions are degenerate")
    basis, _ = torch.linalg.qr(directions)
    return basis, center[None, :, None]


@torch.inference_mode()
def run(archive):
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    model, checkpoint = load_c5(archive)
    x, y, patients = validation_only()
    basis, center = s1_basis(model)
    head, tail_features = model.features[:2], model.features[2:]
    collected = {m: {"pred": [], "bytes": []} for m in METHODS}

    def record(method, logits, sizes):
        collected[method]["pred"].append(logits.argmax(1).numpy())
        collected[method]["bytes"].append(np.broadcast_to(sizes, (len(logits),)))

    for batch in x.split(64):
        record("fp32", model(batch), 0)
        for bins in (360, 180, 46, 20):
            z = batch if bins == 360 else F.adaptive_avg_pool1d(batch, bins)
            restored, q = transport(z)
            name = "s0_rice" if bins == 360 else f"s0_rice_{bins}"
            record(name, model(restore_time(restored, 360)), rice_body_bytes(q))
        activation = head(batch)
        for bins in (10, 23):
            pooled = F.adaptive_avg_pool1d(activation, bins)
            latent = basis.T @ (pooled - center)
            restored, _ = transport(latent)
            decoded = restore_time(F.relu(center + basis @ restored), 360)
            record(f"s1_{2*bins}", model.classifier(tail_features(decoded)), 2*bins)

    metrics = load_json(DATA / "metric-policy.json")
    result = {}
    for name, output in collected.items():
        prediction, sizes = np.concatenate(output["pred"]), np.concatenate(output["bytes"])
        scores = validation_metrics(y, prediction, metrics)
        # Codec bodies omit the I1 envelope. Project it using the ordinary
        # 68+8*C byte metadata/CRC overhead, one input channel or two latent channels.
        header = 0 if name == "fp32" else 68 + 8 * (2 if name.startswith("s1_") else 1)
        result[name] = {
            "macro_f1": scores["validation_macro_f1_K_fixed"], "f1_NSVFQ": scores["f1"],
            "confusion": scores["confusion_matrix"], "body_B_mean": float(sizes.mean()),
            "body_B_p95": float(np.percentile(sizes, 95)), "envelope_B": header,
            "frame_B_mean": float(sizes.mean() + header),
            "per_record_confusion": {r: np.bincount(5*y[patients == r] + prediction[patients == r],
                                                    minlength=25).reshape(5, 5).tolist() for r in RECORDS},
        }
    if abs(result["fp32"]["macro_f1"] - checkpoint["validation_macro_f1_K"]) > 1e-10:
        raise ValueError("Uncompressed CPU baseline failed the locked validation reproduction")
    return {"script_sha256": sha(Path(__file__).read_bytes()), "checkpoint_sha256": checkpoint["sha256"],
            "scope": "exploratory DS1 validation; fixed codecs, CPU FP32 tails; no fit; DS2 unopened",
            "records": list(RECORDS), "samples": len(y), "minimum_macro_f1": 0.95 * result["fp32"]["macro_f1"],
            "methods": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(args.archive)
    if args.out:
        with args.out.open("x", encoding="utf-8") as out:
            json.dump(report, out, ensure_ascii=False, indent=2)
    for m, row in report["methods"].items():
        print(f"{m:15} macro-F1={row['macro_f1']:.6f}  mean body={row['body_B_mean']:.1f} B  "
              f"frame={row['frame_B_mean']:.1f} B")
