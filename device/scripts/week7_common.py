"""Shared definitions of the week 7 laptop tools (stub edge, checkers) and their host tests.

Golden data: the SV3 quantization20 package (20 samples x 11 splits, INT8 q + FP16 scales and
reference logits of the INT8/FP16 path; the same golden the week 5 MCU matched byte for byte).
Requests are built only with the contract references (contracts/i1v2_ref, contracts/i2_ref).
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "contracts" / "i1v2_ref"
I2REF = ROOT / "contracts" / "i2_ref"
for _p in (REF, I2REF):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import i1v2_reference as ref  # noqa: E402
import i2_reference as i2  # noqa: E402

QUANT20 = ROOT / "ml" / "artifacts" / "week5" / "quantization20"
# quant_anchor of results/week5/week5_mcu_validation.json (the golden the week 5 MCU matched).
QUANT20_MANIFEST_SHA256 = "8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd"
P1_PACKAGE = ROOT / "ml" / "artifacts" / "week6" / "mitdb-week6-p1-50-20261016-v1"
REGISTRY = ROOT / "contracts" / "sv3_week5_approved_registry_v2.json"
PUBLIC_TEST_KEY = bytes(range(32))   # PUBLIC_TEST_ONLY (I1 v2 §12), never a bench key
KEY_ID, SENDER_ID = 65537, 131073
RESPONSE_BYTES = 64
SAMPLE_COUNT = 20


@dataclass(frozen=True)
class Golden:
    sample: int
    split: int
    channels: int
    length: int
    q: bytes
    scale_le: bytes
    q_sha256: str
    scale_sha256: str
    logits: tuple


@lru_cache(maxsize=1)
def registry_profile():
    return ref.load_profile(REGISTRY)


def wire_split_id(split: int) -> int:
    for split_id, row in registry_profile().splits.items():
        if row.split_point == split:
            return split_id
    raise KeyError(f"split {split} not in the registry")


@lru_cache(maxsize=1)
def _quant20_entries() -> dict:
    manifest = json.loads((QUANT20 / "manifest.json").read_text(encoding="utf-8"))
    return {(int(e["sample_index"]), int(e["split_point_s"])): e for e in manifest["entries"]}


@lru_cache(maxsize=None)
def golden_tensor(sample: int, split: int) -> Golden:
    entry = _quant20_entries()[(sample, split)]
    _, c, l = entry["quantization_shape_NCL"]
    q = (QUANT20 / entry["int8_path"]).read_bytes()
    scale = (QUANT20 / entry["scale_path"]).read_bytes()
    if len(q) != c * l or len(scale) != 2 * c:
        raise ValueError(f"golden ({sample},{split}) size mismatch")
    return Golden(sample, split, c, l, q, scale, entry["int8_sha256"], entry["scale_sha256"],
                  tuple(float(v) for v in entry["reference_logits_int8_fp16"]))


def reference_logits(sample: int, split: int) -> tuple:
    return golden_tensor(sample, split).logits


def scales_fp32(scale_le: bytes) -> list:
    """FP16 little-endian scales expanded exactly to FP32 values (I1 v2 carries FP32 bits)."""
    return [struct.unpack("<e", scale_le[i:i + 2])[0] for i in range(0, len(scale_le), 2)]


def nonce_bytes(sequence: int) -> bytes:
    return struct.pack("<IQ", SENDER_ID, sequence)


def i2_profile(split: int) -> i2.Profile:
    golden = golden_tensor(0, split)
    return i2.Profile(registry_profile().model_profile_id, wire_split_id(split), golden.channels,
                      golden.length, KEY_ID, min(i2.MAX_PAYLOAD_BYTES, golden.channels * golden.length))


def build_request(sample: int, split: int, request_id: int, key: bytes | None,
                  sequence: int | None) -> bytes:
    """I1 v2 request of a golden tensor: plain (key None, rho = P0) or I2/1 (rho = P1)."""
    golden = golden_tensor(sample, split)
    profile = registry_profile()
    payload, descriptor, nonce = golden.q, None, None
    if key is not None:
        active = i2_profile(split)
        descriptor = i2.descriptor(active)
        nonce = nonce_bytes(sequence)
        payload = i2.protect(golden.q, descriptor, nonce, key, active)
    return ref.encode_request(request_id, profile.model_profile_id, wire_split_id(split),
                              golden.channels, golden.length, scales_fp32(golden.scale_le),
                              payload, descriptor, nonce)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StubEdge:
    """Laptop stand-in for the Edge in week 7 (decision W7-D6).

    For every reassembled request: CRC + header via the I1 v2 reference parser, expected split,
    sequence strictly increasing (P1), q recovered (unprotect with the bench key for P1) and
    matched byte for byte against the 20 golden tensors of that split, then a valid 64 B
    RESPONSE with that sample's reference logits. Anything else is counted and NOT answered,
    so the Device sees a timeout (never a fabricated success).
    """

    def __init__(self, split: int, key: bytes | None):
        self.split = split
        self.key = key
        self.last_sequence = 0
        self.by_q = {golden_tensor(n, split).q: n for n in range(SAMPLE_COUNT)}
        self.counters = {name: 0 for name in (
            "received", "crc_fail", "drop", "reject", "wrong_split", "sequence_not_increasing",
            "no_key", "unknown_q", "p1", "p0", "response_sent")}

    def handle(self, frame: bytes) -> tuple[bytes | None, dict]:
        self.counters["received"] += 1
        record = {"len": len(frame), "sha256": sha256_hex(frame)}
        if len(frame) >= 4 and struct.unpack_from("<I", frame, len(frame) - 4)[0] != ref.crc32(frame[:-4]):
            return self._fail(record, "CRC_FAIL", "crc_fail")
        try:
            request = ref.parse_request(frame, registry_profile())
        except ref.Drop as error:
            return self._fail(record, f"DROP_{error}", "drop")
        except ref.Reject as error:
            return self._fail(record, f"REJECT_{error.status}", "reject")
        record.update(request_id=request.request_id, split_id=request.split.split_id,
                      rho="P1" if request.transformed else "P0")
        if request.split.split_point != self.split:
            return self._fail(record, "WRONG_SPLIT", "wrong_split")
        q = request.payload
        if request.transformed:
            _, sequence = struct.unpack("<IQ", request.nonce)
            record["sequence"] = sequence
            if sequence <= self.last_sequence:
                return self._fail(record, "SEQUENCE_NOT_INCREASING", "sequence_not_increasing")
            self.last_sequence = sequence
            if self.key is None:
                return self._fail(record, "NO_KEY", "no_key")
            try:
                q = ref.recover_q(request, {KEY_ID: self.key})
            except ref.Reject as error:
                return self._fail(record, f"REJECT_{error.status}", "reject")
        sample = self.by_q.get(q)
        if sample is None:
            return self._fail(record, "UNKNOWN_Q", "unknown_q")
        record["sample"] = sample
        record["scales_match"] = list(request.scales) == scales_fp32(
            golden_tensor(sample, self.split).scale_le)
        if not record["scales_match"]:
            return self._fail(record, "SCALE_MISMATCH", "unknown_q")
        self.counters["p1" if request.transformed else "p0"] += 1
        response = ref.encode_response(request.request_id, list(reference_logits(sample, self.split)))
        assert len(response) == RESPONSE_BYTES
        self.counters["response_sent"] += 1
        record["result"] = "OK"
        return response, record

    def _fail(self, record: dict, result: str, counter: str):
        self.counters[counter] += 1
        record["result"] = result
        return None, record


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
