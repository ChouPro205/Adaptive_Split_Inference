"""S0c v1: the standard compressed S0 payload of the ASI project (reference implementation).

Status: S0C-V1, prepared by SV1 on 2026-11-25. Bound by the SHA-256 of this file.
This numpy code is normative. Device (C) and edge implementations must reproduce its
outputs on the golden set: Rice bytes, INT8 values and FP16 scale exactly, and the
reconstructed 360 FP32 samples bit for bit.

Device side, one beat:
 1. x: the FP32 normalized beat used at s0, shape [360]. x = (beat - mean) / std, with
    mean/std of ml/manifests/mitdb-ds1ds2-m1-v3-r2/normalization.json, computed in
    float64 and cast to float32 (same input as s0 and package A).
 2. Reduce 360 -> 46: bin i covers samples [floor(360*i/46), ceil(360*(i+1)/46)), the bins
    of torch.nn.functional.adaptive_avg_pool1d. Value = float32 sum over the bin in index
    order, divided by the float32 bin length.
 3. Quantize per beat, one channel, registry v2 rule: scale = fp16(max(max|v|/127,
    FP16 smallest normal)), or 1 when max|v| = 0; q = clip(rint(v / float32(scale)),
    -127, 127) as int8.
 4. Rice body: byte 0 = q[0] (int8, two's complement); byte 1 = k; then for i = 1..45
    the zigzag value z of d = q[i] - q[i-1] (z = 2d if d >= 0 else -2d - 1) as Rice(k):
    (z >> k) zero bits, one bit 1, then the k low bits of z, most significant first.
    Bits are packed most significant first; the last byte is padded with zeros.
    k in 0..7 minimizes the bit count; ties take the smallest k.
    Body length = 2 + ceil(bits / 8) bytes.
 5. Transport: the body plus the FP16 scale (2 B, little-endian), carried as the
    per-channel scale of the I1 frame exactly as for s0 (C = 1). The I1 payload type and
    envelope fields are fixed in contract I1 (SV1 + SV2), not in this file.

Edge side:
 6. Rice decode -> q (46 int8; nonzero padding or a whole spare byte is rejected);
    v = float32(q) * float32(scale).
 7. Linear interpolation 46 -> 360 with half-pixel centres (PyTorch align_corners=False),
    float32 arithmetic: scale = float32(46) / float32(360);
    src = max(scale * (j + 0.5) - 0.5, 0); i0 = floor(src); i1 = min(i0 + 1, 45);
    w = src - i0; y[j] = (1 - w) * v[i0] + w * v[i1].
 8. y is the input of the whole frozen model (checkpoint A, tail s0).
"""
from __future__ import annotations

import numpy as np

N_IN = 360
N_OUT = 46
K_MAX = 7
FP16_MIN_NORMAL = np.float32(np.finfo(np.float16).smallest_normal)
FP16_MAX = np.float32(np.finfo(np.float16).max)
VERSION = "S0C-V1"


def bins() -> list[tuple[int, int]]:
    """[start, end) of each of the 46 bins (adaptive_avg_pool1d bins)."""
    return [((i * N_IN) // N_OUT, -((-(i + 1) * N_IN) // N_OUT)) for i in range(N_OUT)]


BINS = bins()


def _beat(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x)
    if x.dtype != np.float32 or x.shape != (N_IN,):
        raise ValueError("Beat must be float32 with shape [360]")
    if not np.isfinite(x).all():
        raise ValueError("Beat contains NaN/Inf")
    return x


def reduce46(x: np.ndarray) -> np.ndarray:
    """Step 2: float32 sequential bin sums divided by the float32 bin length."""
    x = _beat(x)
    out = np.empty(N_OUT, dtype=np.float32)
    for i, (a, b) in enumerate(BINS):
        acc = np.float32(0)
        for t in range(a, b):
            acc = np.float32(acc + x[t])
        out[i] = np.float32(acc / np.float32(b - a))
    return out


def quantize(v: np.ndarray) -> tuple[np.ndarray, np.float16]:
    """Step 3: per-beat symmetric INT8 with an FP16 scale (registry v2 rule)."""
    v = np.asarray(v, dtype=np.float32)
    if v.shape != (N_OUT,) or not np.isfinite(v).all():
        raise ValueError("Reduced beat must be finite float32 [46]")
    maximum = np.float32(np.max(np.abs(v)))
    raw = np.float32(maximum / np.float32(127))
    if raw > FP16_MAX:
        raise ValueError("Scale exceeds finite FP16 range")
    scale = np.float16(1) if maximum == 0 else np.float16(max(raw, FP16_MIN_NORMAL))
    q = np.clip(np.rint(v / np.float32(scale)), -127, 127).astype(np.int8)
    return q, scale


def _zigzag(q: np.ndarray) -> list[int]:
    values = [int(t) for t in q]
    deltas = [b - a for a, b in zip(values[:-1], values[1:])]
    return [2 * d if d >= 0 else -2 * d - 1 for d in deltas]


def rice_bits(q: np.ndarray, k: int) -> int:
    return sum((z >> k) + 1 + k for z in _zigzag(q))


def rice_encode(q: np.ndarray) -> bytes:
    """Step 4: Rice body of one beat."""
    q = np.asarray(q)
    if q.dtype != np.int8 or q.shape != (N_OUT,) or np.any(q == -128):
        raise ValueError("q must be int8 [46] without -128")
    k = min(range(K_MAX + 1), key=lambda p: rice_bits(q, p))
    words = []
    for z in _zigzag(q):
        words.append("0" * (z >> k) + "1" + (format(z & ((1 << k) - 1), f"0{k}b") if k else ""))
    bits = "".join(words)
    padding = (-len(bits)) % 8
    body = bytes([int(q[0]) & 0xFF, k])
    if bits:
        body += int(bits + "0" * padding, 2).to_bytes((len(bits) + padding) // 8, "big")
    return body


def rice_decode(body: bytes) -> np.ndarray:
    """Step 6, first half: Rice body -> q (int8 [46])."""
    if len(body) < 2:
        raise ValueError("Body too short")
    first, k = body[0], body[1]
    if k > K_MAX:
        raise ValueError("Invalid Rice parameter")
    values = [first if first < 128 else first - 256]
    bits = "".join(format(b, "08b") for b in body[2:])
    index = 0
    for _ in range(N_OUT - 1):
        stop = bits.find("1", index)
        if stop < 0 or stop + 1 + k > len(bits):
            raise ValueError("Truncated Rice body")
        z = ((stop - index) << k) + (int(bits[stop + 1:stop + 1 + k], 2) if k else 0)
        values.append(values[-1] + (z // 2 if z % 2 == 0 else -(z // 2) - 1))
        index = stop + 1 + k
    if any(c != "0" for c in bits[index:]) or len(bits) - index >= 8:
        raise ValueError("Invalid padding")
    q = np.asarray(values, dtype=np.int64)
    if np.any(q < -127) or np.any(q > 127):
        raise ValueError("Decoded value out of range")
    return q.astype(np.int8)


def dequantize(q: np.ndarray, scale: np.float16) -> np.ndarray:
    effective = np.float32(scale)
    if not np.isfinite(effective) or effective < FP16_MIN_NORMAL:
        raise ValueError("Scale must be finite, positive, normal FP16")
    return np.asarray(q, dtype=np.int8).astype(np.float32) * effective


def interpolate360(v: np.ndarray) -> np.ndarray:
    """Step 7: half-pixel linear interpolation 46 -> 360 in float32."""
    v = np.asarray(v, dtype=np.float32)
    if v.shape != (N_OUT,):
        raise ValueError("Reduced beat must be [46]")
    scale = np.float32(N_OUT) / np.float32(N_IN)
    out = np.empty(N_IN, dtype=np.float32)
    for j in range(N_IN):
        src = np.float32(scale * np.float32(np.float32(j) + np.float32(0.5)) - np.float32(0.5))
        if src < 0:
            src = np.float32(0)
        i0 = int(np.floor(src))
        i1 = min(i0 + 1, N_OUT - 1)
        w = np.float32(src - np.float32(i0))
        out[j] = np.float32(np.float32(np.float32(1) - w) * v[i0] + np.float32(w * v[i1]))
    return out


def encode(x: np.ndarray) -> tuple[bytes, np.float16, np.ndarray]:
    """Device side: beat -> (Rice body, FP16 scale, q)."""
    q, scale = quantize(reduce46(x))
    return rice_encode(q), scale, q


def decode(body: bytes, scale: np.float16) -> tuple[np.ndarray, np.ndarray]:
    """Edge side: (Rice body, FP16 scale) -> (46 dequantized values, 360 reconstructed samples)."""
    v = dequantize(rice_decode(body), scale)
    return v, interpolate360(v)
