"""Shared definitions of the week 11 link tools (plan generator, echo/ack frames, analysis rules, tests).

Week 11 prepares the week 12 BLE lab (W11-D1..D5 of 19/11, CHỐT 25/11). One PPK2 session of the `link` image
is a list of link-state blocks (W11-D3: OFAT around the base state 2M / 15 ms / L 0 / 251 B / 0 dBm, two
Coded S8 blocks at 30 ms); every block is

  STATE     the dongle asks for the block's state (connection parameters, PHY, data length, TX power) and
            waits until the central has granted it (D1 high during the procedures), then a settle time
  IDLE      connected idle, nothing queued: P_conn of the state (start and end of the block)
  ECHO      one I1 v2 envelope of B bytes on stream 0x02 (D2 TX); the KV260 answers with the 72-byte
            ECHO-ACK v1 (length + SHA-256 of what it received) or, in the base block only, the whole frame
            (binding v1 §9); D3 WAIT until the answer is verified. B = I1 frame length (total_length),
            W11-D2 sizes. L > 0 blocks run every size twice: SDC peripheral latency enabled throughout, and
            disabled during WAIT (sdc_hci_cmd_vs_peripheral_latency_mode_set, enabled again after WAIT)

and the base block also carries the S0c encoder cycles (D0 = s0c_encode of a W8-D3 input, 1x and 100x per
pulse) and the reconnect cycles (D1 from the device's disconnect until the link is ready again in the base
state: reconnect + MTU + subscription + base parameters). Block order is a random permutation per session
(seed SESSION_SEED_BASE + session), the base block always first so the session starts like week 10; the
order of the ops inside a block is a permutation too (same stream). The 6-byte plan entries and the state
table are compiled into the firmware (week11_link_plan.h) and authenticated by SHA-256 on the dongle.
"""
from __future__ import annotations

import csv
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import week10_common as w10  # noqa: E402

w9 = w10.w9
ROOT = w10.ROOT

# ----------------------------------------------------------------------------- link states (W11-D3)
PHY_1M, PHY_2M, PHY_CODED_S8 = 1, 2, 3          # plan codes; Zephyr BT_GAP_LE_PHY_{1M,2M,CODED} = 1, 2, 4
PHY_NAMES = {PHY_1M: "1M", PHY_2M: "2M", PHY_CODED_S8: "CodedS8"}
TIMEOUT_10MS = 400                              # supervision timeout 4 s (W7-D7) in every state


@dataclass(frozen=True)
class LinkState:
    index: int
    name: str
    phy: int
    interval_1250us: int
    latency: int
    tx_octets: int
    tx_power_dbm: int
    timeout_10ms: int = TIMEOUT_10MS

    @property
    def interval_ms(self) -> float:
        return self.interval_1250us * 1.25


# Index 0 = base (= week 10 bench state). OFAT: interval, latency at 15 ms, PHY, data length, TX power; Coded at
# 30 ms (a 251 B S8 packet ~17.6 ms does not fit 15 ms) with 251 and 27 B; 1M at 30 ms as Coded's reference.
STATES = (
    LinkState(0, "base", PHY_2M, 12, 0, 251, 0),
    LinkState(1, "k7.5", PHY_2M, 6, 0, 251, 0),
    LinkState(2, "k30", PHY_2M, 24, 0, 251, 0),
    LinkState(3, "k50", PHY_2M, 40, 0, 251, 0),
    LinkState(4, "k100", PHY_2M, 80, 0, 251, 0),
    LinkState(5, "L2", PHY_2M, 12, 2, 251, 0),
    LinkState(6, "L4", PHY_2M, 12, 4, 251, 0),
    LinkState(7, "L9", PHY_2M, 12, 9, 251, 0),
    LinkState(8, "1M", PHY_1M, 12, 0, 251, 0),
    LinkState(9, "len27", PHY_2M, 12, 0, 27, 0),
    LinkState(10, "tx-8", PHY_2M, 12, 0, 251, -8),
    LinkState(11, "coded-k30", PHY_CODED_S8, 24, 0, 251, 0),
    LinkState(12, "coded-k30-len27", PHY_CODED_S8, 24, 0, 27, 0),
    LinkState(13, "1M-k30", PHY_1M, 24, 0, 251, 0),
)
BASE = 0

# ----------------------------------------------------------------------------- ops
OP_STATE, OP_IDLE, OP_ECHO, OP_S0C, OP_RECONNECT = 0, 1, 2, 3, 4
OP_NAMES = {OP_STATE: "STATE", OP_IDLE: "IDLE", OP_ECHO: "ECHO", OP_S0C: "S0C", OP_RECONNECT: "RECONNECT"}
ECHO_ACK = 0x01          # b bit 0: the KV260 answers with ECHO-ACK v1 (else the whole frame, binding §9)
ECHO_LATENCY_OFF = 0x02  # b bit 1: peripheral latency disabled during WAIT (L > 0 blocks)

# W11-D2: the 7 levels of the teacher's table + S1 fixed 20/46 B (104/130), S0c (~112), S0 Rice 157 B (233),
# s0 raw (436 = 68 + 8 + 360). All are I1 v2 frame lengths.
ECHO_SIZES = (64, 104, 112, 128, 130, 233, 256, 436, 512, 1024, 2048, 4096)
ECHO_REPEATS = 6                     # per size and echo variant, per block and session (2 sessions -> 12)
ECHO_FULL_REPEATS = 3                # whole-frame echo in the base block (cross-check with weeks 9-10)
IDLE_MS = 15000                      # P_conn windows at the start and the end of each block
S0C_SAMPLES = 25                     # W8-D3 samples 0..24, each at both repeat counts
S0C_REPEATS = (1, 100)
RECONNECTS = 8
SESSIONS = 2
SESSION_SEED_BASE = 20261126         # session s uses seed 20261126 + s
FRAME_MIN, FRAME_MAX = 36, 6380      # binding v1 frame limits


@dataclass(frozen=True)
class Entry:
    index: int
    block: int        # position of the block in the session
    state: int        # LinkState.index
    op: int
    a: int            # IDLE: ms; ECHO: frame length; S0C: sample; else 0
    b: int            # ECHO: flags; S0C: repeats; else 0


def block_ops(state: LinkState, rng_state: int) -> tuple[list, int]:
    """The ops of one block after its STATE and first IDLE, shuffled with the session stream; plus the state."""
    ops = []
    variants = [ECHO_ACK] if state.latency == 0 else [ECHO_ACK, ECHO_ACK | ECHO_LATENCY_OFF]
    for size in ECHO_SIZES:
        for flags in variants:
            ops += [(OP_ECHO, size, flags)] * ECHO_REPEATS
    if state.index == BASE:
        for size in ECHO_SIZES:
            ops += [(OP_ECHO, size, 0)] * ECHO_FULL_REPEATS
        for n in range(S0C_SAMPLES):
            for r in S0C_REPEATS:
                ops.append((OP_S0C, n, r))
    return _shuffle(ops, rng_state)


def _shuffle(items: list, state: int) -> tuple[list, int]:
    """Fisher-Yates of week10_common.shuffle on a running splitmix64 state (rejection sampling)."""
    perm = list(items)
    for j in range(len(perm) - 1, 0, -1):
        m = j + 1
        limit = (1 << 64) - ((1 << 64) % m)
        while True:
            state, x = w9._splitmix64(state)
            if x < limit:
                break
        r = x % m
        perm[j], perm[r] = perm[r], perm[j]
    return perm, state


def session_plan(session: int) -> list:
    """Base block first, then the other blocks in a random order; the reconnect cycles end the session (base
    state), each followed by a base STATE so the next one starts from the same state."""
    if not 0 <= session < SESSIONS:
        raise ValueError("session out of range")
    state = (SESSION_SEED_BASE + session) & w9._MASK64
    others, state = _shuffle([s.index for s in STATES if s.index != BASE], state)
    rows = []

    def add(block, st, op, a=0, b=0):
        rows.append(Entry(len(rows), block, st, op, a, b))

    for block, index in enumerate([BASE] + others):
        st = STATES[index]
        add(block, index, OP_STATE)
        add(block, index, OP_IDLE, IDLE_MS)
        ops, state = block_ops(st, state)
        for op, a, b in ops:
            add(block, index, op, a, b)
        add(block, index, OP_IDLE, IDLE_MS)
    block = len(STATES)
    add(block, BASE, OP_STATE)
    for _ in range(RECONNECTS):
        add(block, BASE, OP_RECONNECT)
    add(block, BASE, OP_IDLE, IDLE_MS)
    return rows


# ----------------------------------------------------------------------------- serialization / digest
STATE_FMT = "<BBHHHBb"   # index, phy, interval, latency, timeout, tx_octets, tx_power_dbm = 10 bytes
ENTRY_FMT = "<BBHH"      # op, state, a, b = 6 bytes


def state_bytes(states=STATES) -> bytes:
    return b"".join(struct.pack(STATE_FMT, s.index, s.phy, s.interval_1250us, s.latency, s.timeout_10ms,
                                s.tx_octets, s.tx_power_dbm) for s in states)


def plan_bytes(rows, states=STATES) -> bytes:
    """Digest input: the state table (10 bytes per state), then (op, state, a, b uint16 LE) per entry."""
    return state_bytes(states) + b"".join(struct.pack(ENTRY_FMT, r.op, r.state, r.a, r.b) for r in rows)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


FIELDS = ["index", "block", "state", "state_name", "op", "a", "b"]


def write_csv(path: Path, rows) -> None:
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(FIELDS)
        for r in rows:
            writer.writerow([r.index, r.block, r.state, STATES[r.state].name, OP_NAMES[r.op], r.a, r.b])


def read_csv(path: Path) -> list:
    ops = {v: k for k, v in OP_NAMES.items()}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [Entry(int(r["index"]), int(r["block"]), int(r["state"]), ops[r["op"]], int(r["a"]), int(r["b"]))
                for r in csv.DictReader(handle)]


# ----------------------------------------------------------------------------- echo / ack frames
MAGIC = b"I1PK"
ACK_LENGTH = 72                      # 32 header + 4 length + 32 SHA-256 + 4 CRC


def crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def _envelope(message_type: int, request_id: int, payload: bytes, reserved_0: int = 0) -> bytes:
    total = 32 + len(payload) + 4
    header = struct.pack("<4sBBHHHIIIIHH", MAGIC, 2, message_type, 0, 32, reserved_0, total, request_id, 0,
                         len(payload), 0, 0)
    frame = header + payload
    return frame + struct.pack("<I", crc32(frame))


def echo_payload_byte(i: int, request_id: int) -> int:
    return (i ^ (i >> 8) ^ request_id) & 0xFF


ECHO_MODE_FULL, ECHO_MODE_ACK = 0, 1   # reserved_0 (uint16 LE at offset 10) of the echo frame


def echo_frame(length: int, request_id: int, ack: bool = True) -> bytes:
    """The device's echo frame: I1 v2 envelope (type 0x01, no metadata/nonce) of total_length = length; the answer
    it asks for is in reserved_0 (offset 10): 1 = ECHO-ACK v1, 0 = the whole frame back. Stage A of I1 v2 does not
    read reserved_0, so binding v1 §9 peers still accept the frame."""
    if not FRAME_MIN <= length <= FRAME_MAX or not 0 < request_id < 0xFFFFFFFF:
        raise ValueError("echo frame length or request_id out of range")
    payload = bytes(echo_payload_byte(i, request_id) for i in range(length - 36))
    return _envelope(0x01, request_id, payload, ECHO_MODE_ACK if ack else ECHO_MODE_FULL)


def echo_wants_ack(frame: bytes) -> bool:
    """What the KV260 echo service reads to choose its answer."""
    return struct.unpack_from("<H", frame, 10)[0] == ECHO_MODE_ACK


def ack_frame(received: bytes) -> bytes:
    """ECHO-ACK v1, what the KV260 sends back on stream 0x02 in ack mode: an I1 v2 envelope of 72 bytes,
    message_type 0x02, the request_id of the received frame (offset 16), payload = uint32 LE length of the
    received frame + SHA-256 of the received frame, CRC-32 as in I1 v2."""
    if len(received) < 32 or received[:4] != MAGIC:
        raise ValueError("not an I1 envelope")
    request_id = struct.unpack_from("<I", received, 16)[0]
    return _envelope(0x02, request_id, struct.pack("<I", len(received)) + hashlib.sha256(received).digest())


def check_ack(ack: bytes, sent: bytes) -> bool:
    return len(ack) == ACK_LENGTH and ack == ack_frame(sent)
