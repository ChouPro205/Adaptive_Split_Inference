"""Shared definitions of the week 8 laptop tools (lab driver, checkers) and their host tests.

The W8-D3 sample set is an output directory of generate_week8_samples.py (manifest.json,
samples.csv, reference_s2.npz, week8_inputs.h). load_set() authenticates it with the same anchors
as build_week8.ps1. The q/scale references are the host C path (week7/head_fast.c + week5
quantization, what the dongle computes); requests are built only with the contract references
(contracts/i1v2_ref, contracts/i2_ref) through week7_common. The session order and the label rule
mirror device/week8/g2_plan.h (test_week8_host.py compares both).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import week7_common as w7  # noqa: E402

ROOT = w7.ROOT
ref, i2 = w7.ref, w7.i2
SPLIT = 2
SAMPLE_COUNT = 100
CLASSES = "NSVFQ"
NO_LABEL = 255
# W8-D3 amended 23/10 (samples-20261023-c); identical in build_week8.ps1.
SET_SHA256 = "7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639"
ANCHORS = {
    "week8_inputs.h": "4091e4613e0680aebd7c656c408311534a5645bf4ab30ef3faf0d7e896d41317",
    "samples.csv": "d77e8c662d03818f94c345c2c2f6d385c431768da20899b88ac54227857b5e20",
    "reference_s2.npz": "e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5",
}


@dataclass(frozen=True)
class Sample:
    index: int
    sample_id: str
    test_index: int
    true_label: int
    label_ref: int
    q: bytes
    scale_le: bytes
    q_sha256: str
    scale_sha256: str
    logits: tuple


@dataclass(frozen=True)
class SampleSet:
    directory: Path
    set_sha256: str
    channels: int
    length: int
    samples: tuple


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_set(directory: Path) -> SampleSet:
    """The W8-D3 set, authenticated (anchors, manifest, csv <-> npz consistency); ValueError otherwise."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or manifest.get("set_sha256") != SET_SHA256:
        raise ValueError(f"{directory} is not the PASS W8-D3 set {SET_SHA256}")
    for name, digest in ANCHORS.items():
        actual = w7.sha256_file(directory / name)
        if actual != digest or manifest["outputs_sha256"].get(name) != digest:
            raise ValueError(f"{name} SHA-256 {actual} differs from the W8-D3 anchor or its manifest")
    with (directory / "samples.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with np.load(directory / "reference_s2.npz", allow_pickle=False) as npz:
        ids = [str(v) for v in npz["sample_id"]]
        test_index = npz["test_index"].tolist()
        label_ref = npz["label_ref"].tolist()
        q = np.ascontiguousarray(npz["q"], dtype=np.int8)
        scale = np.ascontiguousarray(npz["scale_f16"], dtype="<f2")
        logits = np.asarray(npz["logits"], dtype=np.float32)
    if len(rows) != SAMPLE_COUNT or q.shape[0] != SAMPLE_COUNT or q.ndim != 3:
        raise ValueError("sample count or q shape differs")
    channels, length = int(q.shape[1]), int(q.shape[2])
    samples = []
    for n, row in enumerate(rows):
        qb, sb = q[n].tobytes(), scale[n].tobytes()
        sample = Sample(n, row["sample_id"], int(row["test_index"]), int(row["true_label"]),
                        int(row["label_ref_int8_fp16"]), qb, sb, row["q_sha256"], row["scale_sha256"],
                        tuple(float(v) for v in logits[n]))
        if (int(row["set_index"]) != n or ids[n] != sample.sample_id or test_index[n] != sample.test_index
                or label_ref[n] != sample.label_ref or sha256_hex(qb) != sample.q_sha256
                or sha256_hex(sb) != sample.scale_sha256 or label(sample.logits) != sample.label_ref):
            raise ValueError(f"samples.csv and reference_s2.npz disagree at sample {n}")
        samples.append(sample)
    return SampleSet(directory, SET_SHA256, channels, length, tuple(samples))


def i2_profile(s: SampleSet) -> i2.Profile:
    return i2.Profile(w7.registry_profile().model_profile_id, w7.wire_split_id(SPLIT), s.channels,
                      s.length, w7.KEY_ID, min(i2.MAX_PAYLOAD_BYTES, s.channels * s.length))


def build_request(s: SampleSet, n: int, request_id: int, key: bytes | None,
                  sequence: int | None) -> bytes:
    """I1 v2 request of sample n as the dongle sends it: plain (key None, rho = P0) or I2/1 (P1)."""
    sample = s.samples[n]
    payload, descriptor, nonce = sample.q, None, None
    if key is not None:
        active = i2_profile(s)
        descriptor = i2.descriptor(active)
        nonce = w7.nonce_bytes(sequence)
        payload = i2.protect(sample.q, descriptor, nonce, key, active)
    return ref.encode_request(request_id, w7.registry_profile().model_profile_id, w7.wire_split_id(SPLIT),
                              s.channels, s.length, w7.scales_fp32(sample.scale_le), payload,
                              descriptor, nonce)


def frame_length(s: SampleSet, rho: str) -> int:
    """I1 v2 request length at the set's shape (week 7 check_dryrun formula)."""
    return (108 if rho == "P1" else 68) + 8 * s.channels + s.channels * s.length


def label(logits) -> int:
    """g2_label(): index of the first largest logit, NO_LABEL if one is NaN."""
    if any(math.isnan(v) for v in logits):
        return NO_LABEL
    best = 0
    for i, v in enumerate(logits):
        if v > logits[best]:
            best = i
    return best


def plan(first: int, count: int, sample_count: int = SAMPLE_COUNT) -> list:
    """[(cycle, pair, sample, rho)] of PAIRS <first> <count> / the session (W8-D1)."""
    out = []
    for k in range(count):
        pair = first + k
        for slot in range(2):
            out.append((2 * k + slot, pair, pair % sample_count, "P1" if (pair + slot) % 2 == 0 else "P0"))
    return out


def logits_from_hex(text: str) -> tuple:
    """'3f800000,...' (FP32 bits as printed by the firmware) -> five floats."""
    return tuple(struct.unpack("<f", struct.pack("<I", int(h, 16)))[0] for h in text.split(","))
