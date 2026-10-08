"""Week 5 review reference: per-sample/channel symmetric INT8, stored FP16 scale."""
from __future__ import annotations

import numpy as np

VERSION = "ncl-int8-fp16-v1-review"
FP16_MIN_NORMAL = np.float32(np.finfo(np.float16).smallest_normal)
FP16_MAX = np.float32(np.finfo(np.float16).max)


def _ncl(value: np.ndarray) -> None:
    if not isinstance(value, np.ndarray) or value.ndim != 3 or min(value.shape) < 1:
        raise ValueError("Expected nonempty NCL ndarray [N,C,L]")


def quantize_per_channel(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return C-contiguous INT8 [N,C,L] and little-endian FP16 [N,C]."""
    _ncl(z)
    if z.dtype != np.float32:
        raise ValueError("Activation dtype must be float32")
    if not np.isfinite(z).all():
        raise ValueError("Activation contains NaN/Inf")
    maxima = np.max(np.abs(z), axis=2)  # FP32, independent for every N,C
    raw_scale = maxima / np.float32(127)
    if np.any(raw_scale > FP16_MAX):
        raise ValueError("Scale exceeds finite FP16 range")
    scale = np.where(maxima == 0, np.float32(1),
                     np.maximum(raw_scale, FP16_MIN_NORMAL)).astype("<f2")
    effective = scale.astype(np.float32)[..., None]
    q = np.clip(np.rint(z / effective), -127, 127).astype(np.int8)
    return np.ascontiguousarray(q), np.ascontiguousarray(scale)


def dequantize_per_channel(q: np.ndarray, scale_fp16: np.ndarray) -> np.ndarray:
    """Use the stored scale only; never estimate a scale from the activation."""
    _ncl(q)
    if q.dtype != np.int8:
        raise ValueError("Quantized dtype must be int8")
    if (not isinstance(scale_fp16, np.ndarray) or scale_fp16.dtype.kind != "f"
            or scale_fp16.dtype.itemsize != 2 or scale_fp16.shape != q.shape[:2]):
        raise ValueError("Scale must be FP16 [N,C], matching q")
    effective = scale_fp16.astype(np.float32)
    if not np.isfinite(effective).all() or np.any(effective < FP16_MIN_NORMAL):
        raise ValueError("Scale must be finite, positive, normal FP16")
    if np.any(q == -128):
        raise ValueError("Symmetric quantization forbids -128")
    return np.ascontiguousarray(q.astype(np.float32) * effective[..., None])


def to_ncl(z: np.ndarray, s: int) -> np.ndarray:
    """NC s9/s10 -> NCL with L=1; preserve original channel order/meaning."""
    if type(s) is not int or not 0 <= s <= 10:
        raise ValueError("Invalid authoritative split s")
    if z.ndim != (2 if s >= 9 else 3):
        raise ValueError("Rank differs from frozen split mapping")
    return z[..., None] if s >= 9 else z


def from_ncl(z: np.ndarray, s: int) -> np.ndarray:
    _ncl(z)
    if type(s) is not int or not 0 <= s <= 10:
        raise ValueError("Invalid authoritative split s")
    if s >= 9 and z.shape[2] != 1:
        raise ValueError("NC adapter requires L=1")
    return np.ascontiguousarray(z[..., 0] if s >= 9 else z)
