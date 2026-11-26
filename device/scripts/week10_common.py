"""Shared definitions of the week 10 laptop tools (plan generator, analysis rules, PPK2 driver, tests).

Week 10 (decisions W10-D1..D9 of 10/11/2026) has three measurement kinds:
  prot   W10-D1/D2  E_prot of P1 at every s = 0..9 on a radio-off image: 50 rounds; per round a random
         order (seed 20261110) of 11 slots = 10 P1/P0 pairs (one per s, the two cycles back to back,
         P1 first in even rounds) + 1 HEAD-only s1 cycle (features.0 + ReLU, no quantization) giving
         E_conv,min; round k uses W8-D3 sample k (the W9-D3 set). 21 cycles per round, 1050 cycles.
  ewait  W10-D3     E_wait under KV260 queue load: the clean week 8 energy image (s2, 100 P1/P0 pairs)
         while the KV260 queue_sim runs the load blocks below (seed 20261111). The CSV sent to SV2 on
         10/11 (SHA-256 38937e54...) is regenerated bit for bit by load_blocks().
  ble    W10-D4     one cycle per s = 0..10 with the radio on: 50 rounds, per round a permutation of
         0..10 (seed 20261112), rho0 only, natural payload, link state k = 0 (the fixed bench state);
         every plan entry carries (split, rho, k, payload_bytes) so week 11 adds E_tx(B) / P_conn(k)
         plans without new firmware. s10 = HEAD then the label on the device (no TX, no WAIT).
Permutations are week9_common's splitmix64 + Fisher-Yates (rejection sampling), reproducible without
NumPy or a particular Python version.
"""
from __future__ import annotations

import csv
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import week9_common as w9  # noqa: E402

w8 = w9.w8
ROOT = w9.ROOT
ROUNDS = 50                          # W9-D3 samples 0..49

# ----------------------------------------------------------------------------- W10-D3 load blocks
LOAD_SEED = 20261111
LOAD_LEVELS = (0, 15, 30)            # background jobs/s
LOAD_BLOCKS_PER_LEVEL = 6
LOAD_BLOCK_S = 20
LOAD_LEAD_S = 40                     # lambda 0: dongle connected idle 30 s + settle 5 s
LOAD_TAIL_S = 60                     # lambda 0 after the last block
LOAD_CSV_NAME = "ewait_load_blocks.csv"
LOAD_CSV_SHA256 = "38937e54c2b9cb21a21dc6ac36c43f273216e9eaca56d98af99e053c4f19035e"   # sent to SV2 10/11

# ----------------------------------------------------------------------------- W10-D1 prot plan
PROT_SEED = 20261110
PROT_SPLITS = 10                     # s0..s9 (s10 is device-only, nothing protected or sent)
PROT_SLOTS = PROT_SPLITS + 1         # slot 10 = the HEAD-only s1 cycle
OP_P0, OP_P1, OP_CONV = 0, 1, 2      # P0 cycle, P1 cycle, HEAD-only s1 (E_conv,min, W10-D2)
OP_NAMES = {OP_P0: "P0", OP_P1: "P1", OP_CONV: "CONV"}
CONV_SPLIT = 1
PROT_CYCLES = ROUNDS * (2 * PROT_SPLITS + 1)

# ----------------------------------------------------------------------------- W10-D4 ble plan
BLE_SEED = 20261112
BLE_SPLITS = 11                      # s0..s10
BLE_CYCLES = ROUNDS * BLE_SPLITS
RHO0 = 0
LINK_STATE_DEFAULT = 0               # k0: 2M, default TX power, 15 ms interval (fixed bench geometry)
PAYLOAD_NATURAL = 0                  # payload_bytes 0 = the natural I1 v2 payload of the split

# Filled from the first PASS generator outputs (deterministic: a regenerated directory gives the
# same bytes).
PROT_PLAN_SHA256 = "2094c48bae73ef92d63f5ea4c54591835178f5942fdc2be3f60ab7b5fb045ca1"
BLE_PLAN_SHA256 = "27e20954494cdecdfaf45246cd00a16a5e113ef24e617b57e925a9783c415d33"
PLAN_ANCHORS = {
    "ewait_load_blocks.csv": "38937e54c2b9cb21a21dc6ac36c43f273216e9eaca56d98af99e053c4f19035e",
    "prot_plan.csv": "4c20fab2c9c689ba933f9a5b0ad18730484129f317e14237e6b02ab0147942da",
    "week10_prot_plan.h": "09a06d261741b7d6726880f7f5c6382b33a4304c8142b904c69dda1917508b52",
    "ble_plan.csv": "b7b33815c7c2bcb90b5c3dcea89611a3a140e3710289b43098ce08419aa2293b",
    "week10_ble_plan.h": "bfe3d7165735f07da748f5a5b9b1e54afce3ffdd54d84560c46c207e807c5749",
}


def shuffle(items, seed: int) -> list:
    """Fisher-Yates of week9_common.plan_splits (j from n-1 down to 1, rejection sampling)."""
    state, perm = seed & w9._MASK64, list(items)
    for j in range(len(perm) - 1, 0, -1):
        m = j + 1
        limit = (1 << 64) - ((1 << 64) % m)
        while True:
            state, x = w9._splitmix64(state)
            if x < limit:
                break
        r = x % m
        perm[j], perm[r] = perm[r], perm[j]
    return perm


def permutations(seed: int, n: int, rounds: int = ROUNDS) -> list:
    """rounds permutations of 0..n-1 drawn from one splitmix64 stream (the week 9 plan generator)."""
    state, out = seed & w9._MASK64, []
    for _ in range(rounds):
        perm = list(range(n))
        for j in range(n - 1, 0, -1):
            m = j + 1
            limit = (1 << 64) - ((1 << 64) % m)
            while True:
                state, x = w9._splitmix64(state)
                if x < limit:
                    break
            r = x % m
            perm[j], perm[r] = perm[r], perm[j]
        out.append(perm)
    return out


# ----------------------------------------------------------------------------- load blocks


def load_blocks() -> list:
    """[(duration_s, lambda)]: 40 s at 0, the 18 shuffled 20 s blocks, 60 s at 0 (W10-D3)."""
    base = [lv for lv in LOAD_LEVELS for _ in range(LOAD_BLOCKS_PER_LEVEL)]
    order = shuffle(base, LOAD_SEED)
    return [(LOAD_LEAD_S, 0)] + [(LOAD_BLOCK_S, lv) for lv in order] + [(LOAD_TAIL_S, 0)]


def load_csv_text(blocks=None) -> str:
    rows = load_blocks() if blocks is None else blocks
    return "duration_s,lambda_jobs_per_s\n" + "".join(f"{d},{lv}\n" for d, lv in rows)


def read_load_csv(path: Path) -> list:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["duration_s", "lambda_jobs_per_s"]:
            raise ValueError(f"{path}: expected duration_s,lambda_jobs_per_s")
        return [(float(r["duration_s"]), float(r["lambda_jobs_per_s"])) for r in reader]


def block_table(blocks) -> list:
    """[(index, start_s, end_s, lambda)] on the queue_sim clock (0 = start_monotonic_ns)."""
    out, t = [], 0.0
    for i, (d, lv) in enumerate(blocks):
        out.append((i, t, t + float(d), float(lv)))
        t += float(d)
    return out


# ----------------------------------------------------------------------------- prot plan


@dataclass(frozen=True)
class ProtCycle:
    cycle: int
    round: int
    sample: int
    slot: int        # 0..9 = pair at s = slot, 10 = HEAD-only s1
    split: int
    op: int          # OP_P0, OP_P1, OP_CONV


def prot_plan() -> list:
    """W10-D1: per round a permutation of the 11 slots; a pair slot gives two cycles at its split,
    P1 then P0 in even rounds, P0 then P1 in odd rounds; slot 10 gives one HEAD-only s1 cycle."""
    rows = []
    for k, perm in enumerate(permutations(PROT_SEED, PROT_SLOTS)):
        for slot in perm:
            if slot == PROT_SPLITS:
                ops = [(CONV_SPLIT, OP_CONV)]
            else:
                ops = [(slot, OP_P1), (slot, OP_P0)] if k % 2 == 0 else [(slot, OP_P0), (slot, OP_P1)]
            for split, op in ops:
                rows.append(ProtCycle(len(rows), k, k, slot, split, op))
    return rows


def prot_plan_bytes(rows) -> bytes:
    """Digest input: (split, op) per cycle, cycle order."""
    return b"".join(bytes((r.split, r.op)) for r in rows)


PROT_FIELDS = ["cycle", "round", "sample", "slot", "split", "op"]


def write_prot_csv(path: Path, rows) -> None:
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(PROT_FIELDS)
        for r in rows:
            writer.writerow([r.cycle, r.round, r.sample, r.slot, r.split, OP_NAMES[r.op]])


def read_prot_csv(path: Path) -> list:
    ops = {v: k for k, v in OP_NAMES.items()}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [ProtCycle(int(r["cycle"]), int(r["round"]), int(r["sample"]), int(r["slot"]),
                          int(r["split"]), ops[r["op"]]) for r in csv.DictReader(handle)]


# ----------------------------------------------------------------------------- ble plan


@dataclass(frozen=True)
class BleCycle:
    cycle: int
    round: int
    sample: int
    split: int
    rho: int
    k: int
    payload_bytes: int   # 0 = natural payload of the split (week 10); week 11 sets explicit sizes


def ble_plan() -> list:
    rows = []
    for k, perm in enumerate(permutations(BLE_SEED, BLE_SPLITS)):
        for s in perm:
            rows.append(BleCycle(len(rows), k, k, s, RHO0, LINK_STATE_DEFAULT, PAYLOAD_NATURAL))
    return rows


def ble_plan_bytes(rows) -> bytes:
    """Digest input: (split, rho, k, payload_bytes uint16 LE) = 5 bytes per cycle, cycle order."""
    return b"".join(struct.pack("<BBBH", r.split, r.rho, r.k, r.payload_bytes) for r in rows)


BLE_FIELDS = ["cycle", "round", "sample", "split", "rho", "k", "payload_bytes"]


def write_ble_csv(path: Path, rows) -> None:
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(BLE_FIELDS)
        for r in rows:
            writer.writerow([r.cycle, r.round, r.sample, r.split, r.rho, r.k, r.payload_bytes])


def read_ble_csv(path: Path) -> list:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [BleCycle(*(int(r[f]) for f in BLE_FIELDS)) for r in csv.DictReader(handle)]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------------- authenticated plan


@dataclass(frozen=True)
class Plans:
    directory: Path
    load_blocks: tuple
    prot: tuple
    ble: tuple
    prot_sha256: str
    ble_sha256: str


def load_plans(directory: Path) -> Plans:
    """The week 10 plan directory, authenticated (manifest PASS, anchors, files = generator)."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise ValueError(f"{directory} is not a PASS week 10 plan directory")
    anchors = PLAN_ANCHORS or {LOAD_CSV_NAME: LOAD_CSV_SHA256}
    for name, digest in anchors.items():
        actual = w8.w7.sha256_file(directory / name)
        if actual != digest or manifest["outputs_sha256"].get(name) != digest:
            raise ValueError(f"{name} SHA-256 {actual} differs from the week 10 anchor or its manifest")
    blocks = read_load_csv(directory / LOAD_CSV_NAME)
    prot = read_prot_csv(directory / "prot_plan.csv")
    ble = read_ble_csv(directory / "ble_plan.csv")
    if blocks != [(float(d), float(lv)) for d, lv in load_blocks()]:
        raise ValueError("ewait_load_blocks.csv differs from load_blocks()")
    if prot != prot_plan() or ble != ble_plan():
        raise ValueError("prot_plan.csv / ble_plan.csv differ from the generator")
    prot_sha, ble_sha = sha256_hex(prot_plan_bytes(prot)), sha256_hex(ble_plan_bytes(ble))
    if PROT_PLAN_SHA256 and (prot_sha, ble_sha) != (PROT_PLAN_SHA256, BLE_PLAN_SHA256):
        raise ValueError("plan digests differ from the week 10 anchors")
    return Plans(directory, tuple(blocks), tuple(prot), tuple(ble), prot_sha, ble_sha)
