"""Week 5 integration components; never allocate missing deployment wire IDs."""
import json
from pathlib import Path

import numpy as np
from p1 import Profile, I2Error, descriptor
from quantization import FP16_MIN_NORMAL


def scale_wire_fp32_le(stored_fp16):
    """I1 v1 scale field only: expand stored FP16 values into FP32 LE bytes."""
    if (not isinstance(stored_fp16, np.ndarray) or stored_fp16.dtype.kind != 'f'
            or stored_fp16.dtype.itemsize != 2 or stored_fp16.ndim != 2
            or stored_fp16.shape[0] != 1 or stored_fp16.shape[1] < 1):
        raise ValueError('Expected stored FP16 scale [1,C]')
    expanded = stored_fp16.astype('<f4')
    if not np.isfinite(expanded).all() or np.any(expanded < FP16_MIN_NORMAL):
        raise ValueError('Expected finite positive normal stored FP16 scale')
    return expanded.tobytes(order='C')


def active_profile(registry, s, expected_shape, checkpoint_sha256):
    """Resolve explicit model/wire IDs from a trusted local registry revision.

    Caller supplies the expected frozen shape; payload length is never a source
    of channel/length metadata. Test registries are permitted only by their
    callers, which must keep them separate from a deployment registry.
    """
    if type(s) is not int or not 0 <= s <= 10:
        raise I2Error('INVALID_PROFILE')
    rows = [r for r in registry['splits'] if r['split_point_s'] == s]
    if len(rows) != 1:
        raise I2Error('INVALID_PROFILE')
    row = rows[0]
    if (row.get('dtype') != 'INT8' or row.get('i2_layout') != 'NCL'
            or row.get('channel_axis') != 1 or len(expected_shape) != 3
            or expected_shape[0] != 1):
        raise I2Error('INVALID_PROFILE')
    if registry.get('checkpoint_sha256') != checkpoint_sha256:
        raise I2Error('PROFILE_MISMATCH')
    if row['i2_shape_NCL'] != list(expected_shape):
        raise I2Error('PROFILE_MISMATCH')
    values = [registry.get('model_profile_id'), row.get('wire_split_id'), registry.get('key_id')]
    if any(type(v) is not int or v < 1 for v in values):
        raise I2Error('INVALID_PROFILE')
    if len({r.get('wire_split_id') for r in registry['splits']}) != len(registry['splits']):
        raise I2Error('INVALID_PROFILE')
    maximum = row.get('max_payload_bytes')
    if type(maximum) is not int:
        raise I2Error('INVALID_PROFILE')
    profile = Profile(values[0], values[1], expected_shape[1], expected_shape[2], values[2], maximum)
    descriptor(profile)  # Apply the authoritative limits; no fallback IDs/shapes.
    return profile


def load_registry(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
