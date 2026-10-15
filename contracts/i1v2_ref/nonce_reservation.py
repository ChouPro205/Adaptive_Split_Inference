"""Host model of the I2/1 nonce high-water reservation (contracts/i2_nonce_provisioning_v1.md).

Defines the persisted record bytes and the allocation state machine so both can be
tested with crash/write-failure injection. It is not the NVS driver and proves
nothing about Flash behaviour on the nRF52840.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "i2_ref"))
from i2_reference import chacha20_block  # noqa: E402

NVS_ID_PROVISION = 0x4901
NVS_ID_NONCE_STATE = 0x4902
STATE_MAGIC = b"I2NS"
PROVISION_MAGIC = b"I2KY"
RECORD_VERSION = 1
RESERVE_BLOCK = 1024
UINT64_MAX = (1 << 64) - 1
_STATE = struct.Struct("<4sB3sIIQ8s")  # + crc32
_PROVISION = struct.Struct("<4sB3sII32s")  # + crc32


class NonceStop(Exception):
    """I2 transmission must stop (state missing/corrupt/mismatched, write failure, exhaustion)."""


def key_check(key: bytes) -> bytes:
    """8-byte key check value: ChaCha20 block 0 with the all-zero nonce (sender_id 0 is never valid)."""
    return chacha20_block(key, 0, bytes(12))[:8]


def encode_state(key_id: int, sender_id: int, reserved_through: int, kcv: bytes) -> bytes:
    body = _STATE.pack(STATE_MAGIC, RECORD_VERSION, bytes(3), key_id, sender_id, reserved_through, kcv)
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def decode_state(record: bytes | None) -> tuple:
    if record is None or len(record) != _STATE.size + 4:
        raise NonceStop("STATE_MISSING")
    body = record[:-4]
    if struct.unpack("<I", record[-4:])[0] != zlib.crc32(body) & 0xFFFFFFFF:
        raise NonceStop("STATE_CRC")
    magic, version, reserved, key_id, sender_id, reserved_through, kcv = _STATE.unpack(body)
    if magic != STATE_MAGIC or version != RECORD_VERSION or reserved != bytes(3):
        raise NonceStop("STATE_FORMAT")
    return key_id, sender_id, reserved_through, kcv


def encode_provision(key_id: int, sender_id: int, key: bytes) -> bytes:
    body = _PROVISION.pack(PROVISION_MAGIC, RECORD_VERSION, bytes(3), key_id, sender_id, key)
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def decode_provision(record: bytes | None) -> tuple:
    if record is None:
        raise NonceStop("UNPROVISIONED")
    body = record[:-4]
    if len(record) != _PROVISION.size + 4 or struct.unpack("<I", record[-4:])[0] != zlib.crc32(body) & 0xFFFFFFFF:
        raise NonceStop("PROVISION_CORRUPT")
    magic, version, reserved, key_id, sender_id, key = _PROVISION.unpack(body)
    if magic != PROVISION_MAGIC or version != RECORD_VERSION or reserved != bytes(3):
        raise NonceStop("PROVISION_CORRUPT")
    return key_id, sender_id, key


class PowerLoss(Exception):
    """Simulated reset: RAM state is lost, committed records survive."""


class Store:
    """Atomic per-ID records, like NVS: a write either lands completely or not at all."""

    def __init__(self) -> None:
        self.records = {}
        self.fail_next_write = False
        self.crash_before_write = False
        self.crash_after_write = False

    def read(self, record_id: int):
        return self.records.get(record_id)

    def write(self, record_id: int, data: bytes) -> None:
        if self.crash_before_write:
            self.crash_before_write = False
            raise PowerLoss("before commit")
        if self.fail_next_write:
            self.fail_next_write = False
            raise OSError("flash write failed")
        self.records[record_id] = bytes(data)
        if self.crash_after_write:
            self.crash_after_write = False
            raise PowerLoss("after commit")


def provision(store: Store, key_id: int, sender_id: int, key: bytes, allowed: dict) -> None:
    """Bench provisioning: state first (reserved_through=0), then key record; both read back."""
    if allowed.get(key_id) is None or sender_id not in allowed[key_id] or len(key) != 32:
        raise NonceStop("NOT_IN_REGISTRY")
    state = encode_state(key_id, sender_id, 0, key_check(key))
    record = encode_provision(key_id, sender_id, key)
    store.write(NVS_ID_NONCE_STATE, state)
    store.write(NVS_ID_PROVISION, record)
    if store.read(NVS_ID_NONCE_STATE) != state or store.read(NVS_ID_PROVISION) != record:
        raise NonceStop("READBACK")


class Allocator:
    """Boot-time load plus lazy block reservation; one owner thread holds it under a mutex."""

    def __init__(self, store: Store, allowed: dict, block: int = RESERVE_BLOCK) -> None:
        self.store, self.block, self.fault = store, block, None
        key_id, sender_id, key = decode_provision(store.read(NVS_ID_PROVISION))
        s_key_id, s_sender, reserved_through, kcv = decode_state(store.read(NVS_ID_NONCE_STATE))
        if (s_key_id, s_sender) != (key_id, sender_id) or kcv != key_check(key):
            raise NonceStop("STATE_KEY_MISMATCH")
        if allowed.get(key_id) is None or sender_id not in allowed[key_id]:
            raise NonceStop("NOT_IN_REGISTRY")
        self.key_id, self.sender_id, self.key, self.kcv = key_id, sender_id, key, kcv
        self.persisted = reserved_through
        self.next = reserved_through + 1  # everything <= reserved_through may have been used
        self.limit = reserved_through     # nothing reserved in this boot yet

    def _reserve(self) -> None:
        if self.persisted > UINT64_MAX - self.block:
            self.fault = "EXHAUSTED"
            raise NonceStop(self.fault)
        new_limit = self.persisted + self.block
        record = encode_state(self.key_id, self.sender_id, new_limit, self.kcv)
        try:
            self.store.write(NVS_ID_NONCE_STATE, record)
        except OSError:
            self.fault = "WRITE_FAILED"
            raise NonceStop(self.fault) from None
        if self.store.read(NVS_ID_NONCE_STATE) != record:
            self.fault = "READBACK"
            raise NonceStop(self.fault)
        self.persisted = self.limit = new_limit

    def allocate(self) -> int:
        if self.fault is not None:
            raise NonceStop(self.fault)
        if self.next > self.limit:
            self._reserve()
        sequence = self.next
        self.next += 1
        return sequence

    def nonce(self, sequence: int) -> bytes:
        return struct.pack("<IQ", self.sender_id, sequence)
