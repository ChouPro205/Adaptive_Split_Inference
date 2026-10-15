"""I1 BLE binding v1 host reference: fragment header, sender and bounded reassembly.

Models contracts/i1_ble_binding_v1.md. Host reference only; no radio, no GATT stack.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

BINDING_VERSION = 1
STREAM_I1 = 0x01
STREAM_DIAG_ECHO = 0x02
FRAGMENT_HEADER = struct.Struct("<BBHHH")  # version, stream, transfer_id, offset, total_length
ATT_NOTIFY_WRITE_OVERHEAD = 3
MIN_ATT_MTU = 23
MIN_FRAME = 36  # I1 fixed header + CRC
MAX_FRAME = 6380  # profile ceiling of I1 v2, binding configuration
I1_MAGIC = b"I1PK"

# Bench defaults (binding section 7); configurable, not measured performance.
RESPONSE_TIMEOUT_BASE_MS = 8000
PER_FRAGMENT_BUDGET_MS = 30
MAX_RETRIES = 2
RETRY_BACKOFF_MS = (250, 500)
RECONNECT_WAIT_MS = 10000
REASSEMBLY_TIMEOUT_MS = 2000
TX_CREDITS = 4
TX_CREDIT_TIMEOUT_MS = 2000
EDGE_INFERENCE_DEADLINE_MS = 4000
DUPLICATE_CACHE_TTL_MS = 60000
DUPLICATE_CACHE_ENTRIES = 16
HORIZON_MARGIN_MS = 5000
INFERENCE_RESPONSE_BYTES = 64


def response_timeout_ms(response_bytes: int, att_mtu: int) -> int:
    """Per attempt; starts when the last request fragment has been handed to the stack."""
    return RESPONSE_TIMEOUT_BASE_MS + fragment_count(response_bytes, att_mtu) * PER_FRAGMENT_BUDGET_MS


def retry_horizon_ms(response_bytes: int, att_mtu: int, retries: int = MAX_RETRIES,
                     backoff_ms: tuple = RETRY_BACKOFF_MS) -> int:
    """Longest time between the first transmission and the last possible retry of one request_id."""
    if len(backoff_ms) != retries:
        raise ValueError("one backoff value per retry")
    return ((1 + retries) * response_timeout_ms(response_bytes, att_mtu) + sum(backoff_ms)
            + retries * RECONNECT_WAIT_MS)


def fragment_data_bytes(att_mtu: int) -> int:
    if att_mtu < MIN_ATT_MTU:
        raise ValueError("ATT_MTU below the Bluetooth minimum of 23")
    return att_mtu - ATT_NOTIFY_WRITE_OVERHEAD - FRAGMENT_HEADER.size


def fragment_count(frame_length: int, att_mtu: int) -> int:
    chunk = fragment_data_bytes(att_mtu)
    return (frame_length + chunk - 1) // chunk


def fragment(frame: bytes, stream: int, transfer_id: int, att_mtu: int) -> list:
    if stream not in (STREAM_I1, STREAM_DIAG_ECHO) or not 1 <= transfer_id <= 0xFFFF:
        raise ValueError("invalid stream or transfer_id")
    if not MIN_FRAME <= len(frame) <= MAX_FRAME:
        raise ValueError("frame length outside binding limits")
    chunk = fragment_data_bytes(att_mtu)
    return [FRAGMENT_HEADER.pack(BINDING_VERSION, stream, transfer_id, offset, len(frame))
            + frame[offset:offset + chunk] for offset in range(0, len(frame), chunk)]


class TransferIds:
    """Per connection and direction: 1, 2, ..., 65535, 1, ... (never 0)."""

    def __init__(self) -> None:
        self.last = 0

    def next(self) -> int:
        self.last = self.last % 0xFFFF + 1
        return self.last


@dataclass
class Reassembler:
    """One in-progress transfer per direction; frames are delivered whole or not at all."""

    streams: frozenset = frozenset({STREAM_I1, STREAM_DIAG_ECHO})
    max_frame: int = MAX_FRAME
    timeout_ms: int = REASSEMBLY_TIMEOUT_MS
    counters: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._reset()
        self.last_completed = None

    def _reset(self) -> None:
        self.key = None  # (stream, transfer_id)
        self.total = 0
        self.buffer = bytearray()
        self.header_checked = False
        self.last_ms = 0

    def _count(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    def _abort(self, reason: str) -> None:
        self._count(reason)
        self._count("aborted_transfers")
        self._reset()

    def disconnect(self) -> None:
        if self.key is not None:
            self._abort("disconnect")
        self.last_completed = None

    def tick(self, now_ms: int) -> None:
        if self.key is not None and now_ms - self.last_ms > self.timeout_ms:
            self._abort("reassembly_timeout")

    def feed(self, data: bytes, now_ms: int):
        """Returns (stream, frame) when a transfer completes, else None."""
        self.tick(now_ms)
        if len(data) <= FRAGMENT_HEADER.size:
            self._count("malformed_fragment")
            return None
        version, stream, transfer_id, offset, total = FRAGMENT_HEADER.unpack_from(data, 0)
        chunk = bytes(data[FRAGMENT_HEADER.size:])
        if (version != BINDING_VERSION or stream not in self.streams or transfer_id == 0
                or not MIN_FRAME <= total <= self.max_frame or offset + len(chunk) > total):
            self._count("malformed_fragment")
            if self.key == (stream, transfer_id):
                self._abort("inconsistent_fragment")
            return None
        key = (stream, transfer_id)
        if self.key is None:
            if key == self.last_completed:
                self._count("duplicate_fragment")
                return None
            if offset != 0:
                self._count("orphan_fragment")
                return None
            self._start(key, total, now_ms)
        elif key != self.key:
            if offset != 0:
                self._count("orphan_fragment")
                return None
            self._abort("superseded_transfer")  # sender gave up and started a new transfer
            self._start(key, total, now_ms)
        elif total != self.total:
            self._abort("inconsistent_fragment")
            return None
        received = len(self.buffer)
        if offset < received:
            if offset + len(chunk) <= received and self.buffer[offset:offset + len(chunk)] == chunk:
                self._count("duplicate_fragment")
                self.last_ms = now_ms
            else:
                self._abort("overlap_conflict")
            return None
        if offset > received:
            self._abort("gap")
            return None
        self.buffer += chunk
        self.last_ms = now_ms
        if not self.header_checked and len(self.buffer) >= 16:
            if self.buffer[:4] != I1_MAGIC or struct.unpack_from("<I", self.buffer, 12)[0] != self.total:
                self._abort("frame_header_mismatch")
                return None
            self.header_checked = True
        if len(self.buffer) < self.total:
            return None
        frame = bytes(self.buffer)
        self.last_completed = self.key
        self._reset()
        self._count("frames_delivered")
        return stream, frame

    def _start(self, key: tuple, total: int, now_ms: int) -> None:
        self.key, self.total, self.last_ms = key, total, now_ms
        self.buffer = bytearray()
        self.header_checked = False
