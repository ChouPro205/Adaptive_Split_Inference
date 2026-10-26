#!/usr/bin/env python3
"""Week 8 laptop tail (W8-D7 fallback peer, TC3): dequantize + frozen PyTorch tail at s=2.

Started by week8_edge.py with ml\\.venv (torch); speaks JSON lines on stdin/stdout:
  out (once)  {"ready": true, "selftest_bit_exact": 100, ...} after the self-test below
  in          {"id": k, "C": 16, "L": 180, "q": "<hex C*L int8>", "scale_f16": "<hex 2*C bytes LE>"}
  out         {"id": k, "logits_bits": ["3f800000", ...5], "tail_us": t}  or  {"id": k, "error": "..."}
The model is the frozen week 5 checkpoint (SHA-256 checked), CPU FP32, one thread, deterministic
(week3_sv2_common.configure); q is dequantized with the stored FP16 scales only
(ml/src/quantization.dequantize_per_channel). Self-test: the 100 W8-D3 reference q/scales must give
logits bit-identical to reference_s2.npz (generate_week8_samples.py, C dequantization path).
The worker never looks a sample up: logits come from the received q and scales only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from week5_common import ROOT, PACKAGE, dequantize_per_channel, from_ncl, sha  # noqa: E402

sys.path.insert(0, str(ROOT / "ml/scripts"))
_spec = importlib.util.spec_from_file_location("frozen_week5_loader", ROOT / "ml/scripts/week5_common.py")
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)

SPLIT = 2
CHECKPOINT_SHA = "9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90"
REFERENCE_SHA = "e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5"


def bits(logits: np.ndarray) -> list:
    return [f"{v:08x}" for v in np.ascontiguousarray(logits, dtype="<f4").view("<u4").tolist()]


class Tail:
    def __init__(self):
        if sha(ROOT / PACKAGE / "model/checkpoint.pt") != CHECKPOINT_SHA:
            raise SystemExit("checkpoint differs from week 5")
        model, _ = ml.baseline(ROOT / PACKAGE)
        _, self.tail = ml.wrappers(model, SPLIT)

    def __call__(self, q: np.ndarray, scale_f16: np.ndarray) -> np.ndarray:
        restored = dequantize_per_channel(q, scale_f16)
        with torch.inference_mode():
            out = self.tail(torch.from_numpy(from_ncl(restored, SPLIT))).numpy().astype(np.float32)
        if out.shape != (1, 5) or not np.isfinite(out).all():
            raise ValueError("tail output is not five finite logits")
        return out[0]


def selftest(tail: Tail, samples: Path) -> int:
    path = samples / "reference_s2.npz"
    if sha(path) != REFERENCE_SHA:
        raise SystemExit("reference_s2.npz differs from the W8-D3 anchor")
    with np.load(path, allow_pickle=False) as npz:
        q, scale, logits = npz["q"], npz["scale_f16"], npz["logits"]
    equal = sum(tail(q[n:n + 1], scale[n:n + 1]).tobytes() == logits[n].astype("<f4").tobytes()
                for n in range(len(q)))
    return int(equal)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    args = parser.parse_args()
    tail = Tail()
    equal = selftest(tail, args.samples)
    out = sys.stdout
    out.write(json.dumps({"ready": equal == 100, "selftest_bit_exact": equal, "split": SPLIT,
                          "checkpoint_sha256": CHECKPOINT_SHA, "environment": ml.versions(),
                          "torch_threads": torch.get_num_threads()}) + "\n")
    out.flush()
    if equal != 100:
        return 1
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        reply = {"id": request.get("id")}
        try:
            c, length = int(request["C"]), int(request["L"])
            q = np.frombuffer(bytes.fromhex(request["q"]), np.int8).reshape(1, c, length)
            scale = np.frombuffer(bytes.fromhex(request["scale_f16"]), "<f2").reshape(1, c)
            t0 = time.perf_counter_ns()
            logits = tail(q, scale)
            reply.update(logits_bits=bits(logits), tail_us=(time.perf_counter_ns() - t0) // 1000)
        except Exception as error:  # noqa: BLE001  (reported to the edge, which does not answer)
            reply["error"] = repr(error)
        out.write(json.dumps(reply) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
