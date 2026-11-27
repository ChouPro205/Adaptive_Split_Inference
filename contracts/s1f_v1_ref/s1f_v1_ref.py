"""S1F v1: the fixed S1 compressor of the ASI project (reference implementation, 46-byte payload).

Status: S1F-V1, prepared by SV1 on 2026-11-27. Bound by the SHA-256 of this file and of
s1f_v1_constants.json. This numpy code and the constants file are normative.
Conformance on the golden set:
 - Device (encode): q, the two FP16 scales and the 46 payload bytes exactly. Steps 2-3 fix the
   float32 summation order, so a C implementation that follows them is bit-exact.
 - Edge (decode): from the golden payload and scales, the dequantized latent exactly, the tail
   input [16, 360] within max |difference| <= 1e-6 of the golden array, and the same label.
   Bit-for-bit equality is not required on the edge: a BLAS or DPU matrix product sums in another
   order (PyTorch from the same payload: <= 4.8e-7 on 1,500 DS1 validation beats).

Purpose: the cheapest fixed (not learned) compressor at split s1, used for the K gate (edge
decode + tail s1 time, H6) and as a comparison point. It is not in the action set unless the K
gate says so. S1F20 (10 bins, 20 bytes) is the same code with BINS = 10, diagnostic only.

Constants (s1f_v1_constants.json, float32, from checkpoint A = C5 seed 20261101 of package A;
no fit on patient data): c = ReLU(b1) [16] and B [16, 2] with orthonormal columns, B = QR of
[ReLU(b1 + w1) - c, ReLU(b1 - w1) - c], where b1 is the bias of the first Conv1d and w1[j] is the
sum of its weights over input channel and kernel (the conv1 response to a constant +1 / -1
input). The stored float32 values are normative; re-deriving them with another QR routine may
differ in the last bits, so implementations load the constants, never recompute them.

Device side, one beat:
 1. z: the FP32 s1 activation [16, 360] = ReLU(Conv1d #1(x)), x the normalized beat used at s0
    (the same tensor split s1 would send).
 2. Pool 360 -> 23 per channel: bin t covers samples [floor(360*t/23), ceil(360*(t+1)/23)), the
    bins of torch.nn.functional.adaptive_avg_pool1d. Value = float32 sum over the bin in index
    order, divided by the float32 bin length.
 3. Project: d[j,t] = float32(p[j,t] - c[j]); latent[k,t] = float32 sum over j = 0..15 in index
    order of float32(B[j,k] * d[j,t]) (no fused multiply-add). Shape [2, 23].
 4. Quantize per channel k (registry v2 rule, as s0): scale_k = fp16(max(max_t|latent[k,t]|/127,
    FP16 smallest normal)), or 1 when the maximum is 0; q = clip(rint(latent / float32(scale_k)),
    -127, 127) as int8.
 5. Payload: the 46 int8 bytes in NCL order, q[0, 0..22] then q[1, 0..22] (two's complement), plus
    the two FP16 scales, carried as scales[2] of the I1 frame (float32_le holding the FP16 value,
    I1 v2 section 6). The I1 split_id / envelope is fixed in contract I1 (SV1 + SV2).

Edge side:
 6. v[k,t] = float32(q[k,t]) * float32(scale_k).
 7. h[j,t] = float32(c[j] + float32(float32(B[j,0] * v[0,t]) + float32(B[j,1] * v[1,t])));
    z_hat = max(h, 0) (ReLU). Shape [16, 23].
 8. Linear interpolation 23 -> 360 per channel with half-pixel centres (PyTorch
    align_corners=False), float32: scale = float32(23) / float32(360);
    src = max(scale * (j + 0.5) - 0.5, 0); i0 = floor(src); i1 = min(i0 + 1, 22);
    w = src - i0; y[j] = (1 - w) * z_hat[i0] + w * z_hat[i1].
 9. y [16, 360] is the input of the frozen tail s1 of checkpoint A (Conv1d #2 onwards).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

C = 16
L = 360
K = 2
BINS = 23
FP16_MIN_NORMAL = np.float32(np.finfo(np.float16).smallest_normal)
FP16_MAX = np.float32(np.finfo(np.float16).max)
VERSION = "S1F-V1"


def load_constants(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """(B [16, 2], c [16]) float32 from s1f_v1_constants.json (exact float32 bit patterns)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != VERSION:
        raise ValueError("Constants version differs")
    basis = np.frombuffer(bytes.fromhex(data["basis_f32_le_hex"]), dtype="<f4").reshape(C, K).copy()
    center = np.frombuffer(bytes.fromhex(data["center_f32_le_hex"]), dtype="<f4").copy()
    if center.shape != (C,) or not (np.isfinite(basis).all() and np.isfinite(center).all()):
        raise ValueError("Invalid constants")
    return basis, center


def bins(n_out: int = BINS) -> list[tuple[int, int]]:
    """[start, end) of each output bin of adaptive_avg_pool1d (360 -> n_out)."""
    return [((i * L) // n_out, -((-(i + 1) * L) // n_out)) for i in range(n_out)]


def _activation(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z)
    if z.dtype != np.float32 or z.shape != (C, L):
        raise ValueError("s1 activation must be float32 [16, 360]")
    if not np.isfinite(z).all():
        raise ValueError("Activation contains NaN/Inf")
    return z


def pool(z: np.ndarray, n_out: int = BINS) -> np.ndarray:
    """Step 2: float32 sequential bin sums divided by the float32 bin length, per channel."""
    z = _activation(z)
    out = np.empty((C, n_out), dtype=np.float32)
    for i, (a, b) in enumerate(bins(n_out)):
        n = np.float32(b - a)
        for j in range(C):
            acc = np.float32(0)
            for t in range(a, b):
                acc = np.float32(acc + z[j, t])
            out[j, i] = np.float32(acc / n)
    return out


def project(p: np.ndarray, basis: np.ndarray, center: np.ndarray) -> np.ndarray:
    """Step 3: latent [2, T] = B^T (p - c), float32, sequential over the 16 channels, no FMA."""
    p = np.asarray(p, dtype=np.float32)
    t_len = p.shape[1]
    d = np.empty_like(p)
    for j in range(C):
        for t in range(t_len):
            d[j, t] = np.float32(p[j, t] - center[j])
    latent = np.empty((K, t_len), dtype=np.float32)
    for k in range(K):
        for t in range(t_len):
            acc = np.float32(0)
            for j in range(C):
                acc = np.float32(acc + np.float32(basis[j, k] * d[j, t]))
            latent[k, t] = acc
    return latent


def quantize(latent: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Step 4: per-channel symmetric INT8 with FP16 scales (registry v2 rule)."""
    latent = np.asarray(latent, dtype=np.float32)
    if latent.ndim != 2 or latent.shape[0] != K or not np.isfinite(latent).all():
        raise ValueError("Latent must be finite float32 [2, T]")
    q = np.empty(latent.shape, dtype=np.int8)
    scales = np.empty(K, dtype="<f2")
    for k in range(K):
        maximum = np.float32(np.max(np.abs(latent[k])))
        raw = np.float32(maximum / np.float32(127))
        if raw > FP16_MAX:
            raise ValueError("Scale exceeds finite FP16 range")
        scale = np.float16(1) if maximum == 0 else np.float16(max(raw, FP16_MIN_NORMAL))
        scales[k] = scale
        q[k] = np.clip(np.rint(latent[k] / np.float32(scale)), -127, 127).astype(np.int8)
    return q, scales


def payload_bytes(q: np.ndarray) -> bytes:
    """Step 5: NCL order, channel 0 then channel 1, int8 two's complement."""
    q = np.asarray(q)
    if q.dtype != np.int8 or q.shape[0] != K or np.any(q == -128):
        raise ValueError("q must be int8 [2, T] without -128")
    return np.ascontiguousarray(q).tobytes()


def parse_payload(data: bytes, n_bins: int = BINS) -> np.ndarray:
    if len(data) != K * n_bins:
        raise ValueError("Payload length differs")
    q = np.frombuffer(data, dtype=np.int8).reshape(K, n_bins).copy()
    if np.any(q == -128):
        raise ValueError("Symmetric quantization forbids -128")
    return q


def dequantize(q: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """Step 6."""
    scales = np.asarray(scales, dtype="<f2")
    effective = scales.astype(np.float32)
    if scales.shape != (K,) or not np.isfinite(effective).all() or np.any(effective < FP16_MIN_NORMAL):
        raise ValueError("Scales must be two finite, positive, normal FP16 values")
    out = np.empty(q.shape, dtype=np.float32)
    for k in range(K):
        out[k] = np.asarray(q[k], dtype=np.int8).astype(np.float32) * effective[k]
    return out


def restore(v: np.ndarray, basis: np.ndarray, center: np.ndarray) -> np.ndarray:
    """Step 7: z_hat [16, T] = ReLU(c + B v), float32, the two products summed first, no FMA."""
    v = np.asarray(v, dtype=np.float32)
    t_len = v.shape[1]
    out = np.empty((C, t_len), dtype=np.float32)
    for j in range(C):
        for t in range(t_len):
            m = np.float32(np.float32(basis[j, 0] * v[0, t]) + np.float32(basis[j, 1] * v[1, t]))
            h = np.float32(center[j] + m)
            out[j, t] = h if h > 0 else np.float32(0)
    return out


def interpolate360(zh: np.ndarray) -> np.ndarray:
    """Step 8: half-pixel linear interpolation T -> 360 per channel, float32."""
    zh = np.asarray(zh, dtype=np.float32)
    n_in = zh.shape[1]
    scale = np.float32(n_in) / np.float32(L)
    out = np.empty((zh.shape[0], L), dtype=np.float32)
    for j in range(L):
        src = np.float32(scale * np.float32(np.float32(j) + np.float32(0.5)) - np.float32(0.5))
        if src < 0:
            src = np.float32(0)
        i0 = int(np.floor(src))
        i1 = min(i0 + 1, n_in - 1)
        w = np.float32(src - np.float32(i0))
        for c in range(zh.shape[0]):
            out[c, j] = np.float32(np.float32(np.float32(1) - w) * zh[c, i0] + np.float32(w * zh[c, i1]))
    return out


def encode(z: np.ndarray, basis: np.ndarray, center: np.ndarray, n_bins: int = BINS):
    """Device side: s1 activation -> (payload bytes, FP16 scales [2], q [2, T], latent [2, T])."""
    latent = project(pool(z, n_bins), basis, center)
    q, scales = quantize(latent)
    return payload_bytes(q), scales, q, latent


def decode(data: bytes, scales: np.ndarray, basis: np.ndarray, center: np.ndarray, n_bins: int = BINS):
    """Edge side: (payload, scales) -> (dequantized latent [2, T], z_hat [16, T], tail input [16, 360])."""
    v = dequantize(parse_payload(data, n_bins), scales)
    zh = restore(v, basis, center)
    return v, zh, interpolate360(zh)
