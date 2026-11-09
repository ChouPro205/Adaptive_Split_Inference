"""Shared definitions of the week 9 laptop tools (generators, lab driver, checkers) and their host tests.

Week 9 measures E_dev(s) for every s = 0..10 (W9-D1..D4): head(s) + INT8/FP16 quantization on the
dongle with the radio off, 50 samples (the first 50 of the W8-D3 set, set_index 0..49) for every s.
  plan  W9-D4: 50 rounds x 11 splits = 550 cycles; round k uses sample k, its 11 splits in a random
        permutation (splitmix64 + Fisher-Yates, seed 20261103, defined below so any tool can
        reproduce it). generate_week9_plan.py writes plan.csv + week9_plan.h (firmware); the plan
        SHA-256 is the SHA-256 of the 550 split bytes in cycle order.
  refs  W9-D6: q/scale SHA-256 of the 50 samples at every s from the host C path (week7/head_fast.c
        + week5/quantization.c via device/week9/host_test/dev_shim.c, gcc, the firmware's numerics
        flags). generate_week9_refs.py writes refs.csv.
Both directories are authenticated by the anchors below (identical in build_week9.ps1).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import week8_common as w8  # noqa: E402

ROOT = w8.ROOT
PLAN_SEED = 20261103                 # W9-D4
ROUNDS = 50                          # W9-D3: samples 0..49 of the W8-D3 set
SPLITS = 11
CYCLES = ROUNDS * SPLITS
TENSOR_SIZES = ROOT / "results" / "week5" / "device" / "tensor_sizes.csv"
BENCH_FAST = ROOT / "results" / "week7" / "device" / "t_dev_bench_by_split.csv"
CPU_HZ = 64_000_000
# Filled from the first PASS generator outputs (deterministic: a regenerated directory gives the
# same bytes); identical in build_week9.ps1.
PLAN_SHA256 = "5b1fcfe85b7057f5ea4ef52db4b6b3aa1b819a07d5af7a3c55bdb985f6eb4a9f"
PLAN_ANCHORS = {
    "plan.csv": "dc12ee727d9df7bf6548345f6c61dd6afdbde9a2a68146a89dfcb2c95dbafa8f",
    "week9_plan.h": "5652a76a367ee357b043f900b2cff18193bb1d65c2e224c03b83e7aa5c14706e",
}
REFS_ANCHORS = {
    "refs.csv": "cd739a6d8d1389796c376945ef633afc895d031c6308b97590dd0f5c18620a69",
}
_MASK64 = (1 << 64) - 1


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _splitmix64(state: int) -> tuple:
    """(new state, output) of splitmix64 (Steele, Lea, Flood 2014)."""
    state = (state + 0x9E3779B97F4A7C15) & _MASK64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return state, z ^ (z >> 31)


def plan_splits(seed: int = PLAN_SEED, rounds: int = ROUNDS) -> list:
    """Split of every cycle (cycle i = 11 * round + j): per round a Fisher-Yates shuffle of 0..10,
    j from 10 down to 1, swap with an index drawn uniformly in 0..j (rejection sampling)."""
    state, out = seed & _MASK64, []
    for _ in range(rounds):
        perm = list(range(SPLITS))
        for j in range(SPLITS - 1, 0, -1):
            m = j + 1
            limit = (1 << 64) - ((1 << 64) % m)
            while True:
                state, x = _splitmix64(state)
                if x < limit:
                    break
            r = x % m
            perm[j], perm[r] = perm[r], perm[j]
        out.extend(perm)
    return out


def plan_sha256(splits) -> str:
    return sha256_hex(bytes(splits))


def plan_rows(splits) -> list:
    """[(cycle, round, sample, split)]: round k uses W8-D3 sample k (W9-D3, W9-D4)."""
    return [(i, i // SPLITS, i // SPLITS, s) for i, s in enumerate(splits)]


def read_plan_csv(path: Path) -> list:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [(int(r["cycle"]), int(r["round"]), int(r["sample"]), int(r["split"]))
                for r in csv.DictReader(handle)]


@dataclass(frozen=True)
class Plan:
    directory: Path
    sha256: str
    rows: tuple          # (cycle, round, sample, split)


def load_plan(directory: Path) -> Plan:
    """The W9-D4 plan, authenticated (anchors, manifest, csv = generator); ValueError otherwise."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or manifest.get("plan_sha256") != PLAN_SHA256:
        raise ValueError(f"{directory} is not the PASS W9-D4 plan {PLAN_SHA256}")
    for name, digest in PLAN_ANCHORS.items():
        actual = w8.w7.sha256_file(directory / name)
        if actual != digest or manifest["outputs_sha256"].get(name) != digest:
            raise ValueError(f"{name} SHA-256 {actual} differs from the W9-D4 anchor or its manifest")
    rows = read_plan_csv(directory / "plan.csv")
    splits = plan_splits()
    if rows != plan_rows(splits) or plan_sha256(splits) != PLAN_SHA256:
        raise ValueError("plan.csv differs from plan_splits(20261103)")
    return Plan(directory, PLAN_SHA256, tuple(rows))


@dataclass(frozen=True)
class Ref:
    sample: int
    sample_id: str
    split: int
    channels: int
    length: int
    bytes_payload: int
    q_sha256: str
    scale_sha256: str


def tensor_sizes() -> dict:
    """split -> (channels, length, int8 + FP16 bytes) of results/week5/device/tensor_sizes.csv."""
    out = {}
    with TENSOR_SIZES.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            channels, count = int(r["channels"]), int(r["num_elements"])
            out[int(r["split"])] = (channels, count // channels, int(r["int8_plus_fp16_bytes"]))
    return out


REFS_FIELDS = ["set_index", "sample_id", "split", "channels", "length", "bytes_q", "bytes_scale",
               "bytes_payload", "q_sha256", "scale_sha256"]


def read_refs_csv(path: Path) -> dict:
    out = {}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            ref = Ref(int(r["set_index"]), r["sample_id"], int(r["split"]), int(r["channels"]),
                      int(r["length"]), int(r["bytes_payload"]), r["q_sha256"], r["scale_sha256"])
            out[(ref.sample, ref.split)] = ref
    return out


def load_refs(directory: Path, sample_set: w8.SampleSet) -> dict:
    """(sample, split) -> Ref, authenticated (anchors, manifest, set, sizes, s=2 = W8-D3)."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or manifest.get("set_sha256") != sample_set.set_sha256:
        raise ValueError(f"{directory} is not a PASS week 9 reference set of {sample_set.set_sha256}")
    for name, digest in REFS_ANCHORS.items():
        actual = w8.w7.sha256_file(directory / name)
        if actual != digest or manifest["outputs_sha256"].get(name) != digest:
            raise ValueError(f"{name} SHA-256 {actual} differs from the week 9 anchor or its manifest")
    refs = read_refs_csv(directory / "refs.csv")
    sizes = tensor_sizes()
    if sorted(refs) != [(n, s) for n in range(ROUNDS) for s in range(SPLITS)]:
        raise ValueError("refs.csv does not hold samples 0..49 x splits 0..10")
    for (n, s), r in refs.items():
        sample = sample_set.samples[n]
        if (r.sample_id != sample.sample_id or (r.channels, r.length, r.bytes_payload) != sizes[s]
                or (s == w8.SPLIT and (r.q_sha256, r.scale_sha256) != (sample.q_sha256, sample.scale_sha256))):
            raise ValueError(f"refs.csv differs from the W8-D3 set or tensor_sizes.csv at n={n} s={s}")
    return refs


def bench_fast_ms() -> dict:
    """split -> FAST_mean_ms of week 7 BENCH (head only, sample 0, IRQs locked; TC2 reference)."""
    with BENCH_FAST.open(encoding="utf-8", newline="") as handle:
        return {int(r["split"]): float(r["FAST_mean_ms"]) for r in csv.DictReader(handle)}
