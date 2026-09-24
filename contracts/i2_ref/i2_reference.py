"""I2/1 reference transform. This is reversible obfuscation, not encryption."""

from __future__ import annotations

import struct
from dataclasses import dataclass

VERSION = 1
ALGORITHM = 1
DTYPE_INT8 = 2
LAYOUT_NCL = 1
DESCRIPTOR_SIZE = 28
MAX_CHANNELS = 256
MAX_PAYLOAD_BYTES = 32768
_DESCRIPTOR = struct.Struct("<BBBBIHHHHIII")
_MASK32 = 0xFFFFFFFF


class I2Error(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Profile:
    model_profile_id: int
    split_id: int
    channels: int
    length: int
    key_id: int
    max_payload_bytes: int = MAX_PAYLOAD_BYTES


def descriptor(profile: Profile) -> bytes:
    """Serialize the fixed 28-byte descriptor; nonce is separate."""
    _check_profile(profile)
    return _DESCRIPTOR.pack(
        VERSION, ALGORITHM, DTYPE_INT8, LAYOUT_NCL,
        profile.model_profile_id, profile.split_id, 1, profile.channels, 0,
        profile.length, profile.key_id, profile.channels * profile.length,
    )


def _check_profile(profile: Profile) -> None:
    if not (
        1 <= profile.model_profile_id <= _MASK32
        and 1 <= profile.split_id <= 0xFFFF
        and 1 <= profile.channels <= MAX_CHANNELS
        and 1 <= profile.length <= _MASK32
        and 1 <= profile.key_id <= _MASK32
        and 1 <= profile.max_payload_bytes <= MAX_PAYLOAD_BYTES
    ):
        raise I2Error("INVALID_PROFILE")
    if profile.channels * profile.length > profile.max_payload_bytes:
        raise I2Error("SIZE_LIMIT")


def _validate(data: bytes, metadata: bytes, nonce: bytes, key: bytes,
              profile: Profile) -> int:
    if not isinstance(data, bytes) or not isinstance(metadata, bytes):
        raise I2Error("INVALID_ARGUMENT")
    if not isinstance(nonce, bytes) or len(nonce) != 12:
        raise I2Error("INVALID_NONCE")
    if not isinstance(key, bytes) or len(key) != 32:
        raise I2Error("KEY_UNAVAILABLE")
    _check_profile(profile)
    if len(metadata) != DESCRIPTOR_SIZE:
        raise I2Error("INVALID_METADATA")
    version, algorithm, dtype, layout, model, split, n, c, reserved, length, key_id, size = _DESCRIPTOR.unpack(metadata)
    if version != VERSION:
        raise I2Error("UNSUPPORTED_VERSION")
    if algorithm != ALGORITHM:
        raise I2Error("UNSUPPORTED_ALGORITHM")
    if (dtype != DTYPE_INT8 or layout != LAYOUT_NCL or n != 1 or reserved != 0
            or model == 0 or split == 0 or key_id == 0 or c == 0 or length == 0):
        raise I2Error("INVALID_METADATA")
    if c > MAX_CHANNELS or c * length > MAX_PAYLOAD_BYTES:
        raise I2Error("SIZE_LIMIT")
    if size != c * length or len(data) != size:
        raise I2Error("LENGTH_MISMATCH")
    if (model, split, c, length) != (profile.model_profile_id, profile.split_id,
                                     profile.channels, profile.length):
        raise I2Error("PROFILE_MISMATCH")
    if key_id != profile.key_id:
        raise I2Error("KEY_SCOPE_MISMATCH")
    return size


def _rotl(value: int, n: int) -> int:
    return ((value << n) | (value >> (32 - n))) & _MASK32


def _quarter(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & _MASK32
    state[d] = _rotl(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & _MASK32
    state[b] = _rotl(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b]) & _MASK32
    state[d] = _rotl(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & _MASK32
    state[b] = _rotl(state[b] ^ state[c], 7)


def chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    """RFC 8439 Section 2.3 block function, without XOR or Poly1305."""
    if len(key) != 32 or len(nonce) != 12 or not 0 <= counter <= _MASK32:
        raise I2Error("INVALID_ARGUMENT")
    initial = list(struct.unpack("<4I", b"expand 32-byte k"))
    initial += list(struct.unpack("<8I", key))
    initial += [counter, *struct.unpack("<3I", nonce)]
    state = initial.copy()
    for _ in range(10):
        _quarter(state, 0, 4, 8, 12)
        _quarter(state, 1, 5, 9, 13)
        _quarter(state, 2, 6, 10, 14)
        _quarter(state, 3, 7, 11, 15)
        _quarter(state, 0, 5, 10, 15)
        _quarter(state, 1, 6, 11, 12)
        _quarter(state, 2, 7, 8, 13)
        _quarter(state, 3, 4, 9, 14)
    return struct.pack("<16I", *((state[i] + initial[i]) & _MASK32 for i in range(16)))


def _stream(key: bytes, nonce: bytes):
    counter = 0
    while True:
        if counter > _MASK32:
            raise I2Error("SIZE_LIMIT")
        yield from chacha20_block(key, counter, nonce)
        counter += 1


def _parameters(key: bytes, nonce: bytes, channels: int):
    stream = _stream(key, nonce)
    a = [(next(stream) | 1) for _ in range(channels)]
    b = [next(stream) for _ in range(channels)]
    permutation = list(range(channels))
    for i in range(channels - 1, 0, -1):
        bound = i + 1
        limit = (1 << 32) - ((1 << 32) % bound)
        while True:
            sample = sum(next(stream) << (8 * k) for k in range(4))
            if sample < limit:
                break
        j = sample % bound
        permutation[i], permutation[j] = permutation[j], permutation[i]
    return a, b, permutation


def protect(activation_bytes: bytes, metadata: bytes, nonce: bytes,
            key: bytes, active_profile: Profile) -> bytes:
    _validate(activation_bytes, metadata, nonce, key, active_profile)
    c, length = active_profile.channels, active_profile.length
    a, b, permutation = _parameters(key, nonce, c)
    output = bytearray(len(activation_bytes))
    for out_channel, in_channel in enumerate(permutation):
        source = in_channel * length
        target = out_channel * length
        for index in range(length):
            output[target + index] = (a[in_channel] * activation_bytes[source + index] + b[in_channel]) & 0xFF
    return bytes(output)


def unprotect(protected_bytes: bytes, metadata: bytes, nonce: bytes,
              key: bytes, active_profile: Profile) -> bytes:
    _validate(protected_bytes, metadata, nonce, key, active_profile)
    c, length = active_profile.channels, active_profile.length
    a, b, permutation = _parameters(key, nonce, c)
    output = bytearray(len(protected_bytes))
    for out_channel, in_channel in enumerate(permutation):
        source = out_channel * length
        target = in_channel * length
        inverse = pow(a[in_channel], -1, 256)
        for index in range(length):
            output[target + index] = (inverse * (protected_bytes[source + index] - b[in_channel])) & 0xFF
    return bytes(output)
