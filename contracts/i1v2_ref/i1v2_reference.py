"""I1 v2 host reference: framing, validation order and response codec.

Framing/validation only. The I2/1 transform is ../i2_ref/i2_reference.py; this
module calls it for the receiver pipeline. Host reference, not firmware/Edge code.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "i2_ref"))
import i2_reference as i2  # noqa: E402

MAGIC = b"I1PK"
VERSION = 2
FIXED_HEADER = 32
CRC_BYTES = 4
MSG_REQUEST, MSG_RESPONSE, MSG_ERROR = 0x01, 0x02, 0x03
FLAG_I2_TRANSFORMED = 0x0002
DTYPE_INT8, LAYOUT_NCL, SCHEME_PER_CHANNEL = 0x02, 0x01, 0x02
RESULT_NONE, RESULT_SCORE_VECTOR = 0x00, 0x02
RESULT_DTYPE_NONE, RESULT_DTYPE_FLOAT32 = 0x00, 0x02
DESCRIPTOR_BYTES = 28
NONCE_BYTES = 12
REQUEST_PREFIX_BYTES = 32  # model_profile_id 4 + tensor prefix 12 + dims 12 + quant_count 4
CLASS_ORDER = ("N", "S", "V", "F", "Q")
RESULT_COUNT = len(CLASS_ORDER)

STATUS = {
    "OK": 0x0000,
    "UNSUPPORTED_VERSION": 0x0001,
    "INVALID_MESSAGE_TYPE": 0x0002,
    "INVALID_LENGTH": 0x0003,
    "INVALID_TENSOR_METADATA": 0x0004,
    "CRC_MISMATCH": 0x0005,
    "UNSUPPORTED_SPLIT": 0x0006,
    "UNSUPPORTED_DTYPE": 0x0007,
    "EDGE_BUSY": 0x0008,
    "INFERENCE_FAILED": 0x0009,
    "TIMEOUT": 0x000A,
    "UNSUPPORTED_LAYOUT": 0x000B,
    "UNSUPPORTED_QUANTIZATION": 0x000C,
    "DUPLICATE_CONFLICT": 0x000D,
    "PAYLOAD_TOO_LARGE": 0x000E,
    "UNSUPPORTED_FLAGS": 0x000F,
    "INVALID_REQUEST_ID": 0x0010,
    "UNKNOWN_MODEL_PROFILE": 0x0011,
    "KEY_UNAVAILABLE": 0x0012,
    "INVALID_I2_DESCRIPTOR": 0x0013,
    "INVALID_NONCE": 0x0014,
}
STATUS_NAME = {value: name for name, value in STATUS.items()}

# I2/1 API error -> I1 v2 status (section 7.3 of the spec). NONCE_REUSE is a
# sender-side stop and never reaches the wire.
I2_TO_I1 = {
    "INVALID_ARGUMENT": "INFERENCE_FAILED",
    "INVALID_NONCE": "INVALID_NONCE",
    "KEY_UNAVAILABLE": "KEY_UNAVAILABLE",
    "INVALID_PROFILE": "INFERENCE_FAILED",
    "INVALID_METADATA": "INVALID_I2_DESCRIPTOR",
    "UNSUPPORTED_VERSION": "INVALID_I2_DESCRIPTOR",
    "UNSUPPORTED_ALGORITHM": "INVALID_I2_DESCRIPTOR",
    "SIZE_LIMIT": "PAYLOAD_TOO_LARGE",
    "LENGTH_MISMATCH": "INVALID_I2_DESCRIPTOR",
    "PROFILE_MISMATCH": "INVALID_I2_DESCRIPTOR",
    "KEY_SCOPE_MISMATCH": "KEY_UNAVAILABLE",
    "BUFFER_TOO_SMALL": "INFERENCE_FAILED",
}

_HEADER = struct.Struct("<4sBBHHHIIIIHH")
_TENSOR_PREFIX = struct.Struct("<IHBBBBbBI")  # model_profile_id + I1 v1 tensor prefix
_TENSOR_FIELDS = struct.Struct("<HBBBBbBI")
_DESCRIPTOR = struct.Struct("<BBBBIHHHHIII")
_RESPONSE_META = struct.Struct("<HBBI")


class Drop(Exception):
    """Envelope cannot be trusted: no response, request_id not usable."""


class Reject(Exception):
    def __init__(self, name: str, request_id: int) -> None:
        super().__init__(name)
        self.name = name
        self.status = STATUS[name]
        self.request_id = request_id


@dataclass(frozen=True)
class Split:
    split_id: int
    split_point: int
    channels: int
    length: int
    edge_tail: bool


@dataclass(frozen=True)
class Profile:
    model_profile_id: int
    key_id: int
    sender_ids: frozenset
    splits: dict
    max_payload: int
    max_channels: int
    max_packet: int


def load_profile(path: Path) -> Profile:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    limits = registry["buffer_limits"]["device"]
    splits = {}
    for row in registry["splits"]:
        n, c, l = row["i2_shape_NCL"]
        assert n == 1 and row["channel_axis"] == 1 and row["dtype"] == "INT8"
        splits[row["wire_split_id"]] = Split(row["wire_split_id"], row["split_point_s"], c, l,
                                             bool(row["edge_tail_executable"]))
    return Profile(registry["model_profile_id"], registry["key_id"],
                   frozenset(registry["sender_scope"]["sender_ids"]), splits,
                   limits["payload_bytes"], limits["channels"],
                   registry["packet_planning"]["protected_budget_bytes"])


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def frame(message_type: int, flags: int, request_id: int, metadata: bytes, nonce: bytes,
          payload: bytes, *, version: int = VERSION, reserved_0: int = 0, reserved_1: int = 0) -> bytes:
    """Serialize a frame with consistent lengths and CRC (also used to build negative cases)."""
    header_length = FIXED_HEADER + len(metadata) + len(nonce)
    total_length = header_length + len(payload) + CRC_BYTES
    header = _HEADER.pack(MAGIC, version, message_type, flags, header_length, reserved_0,
                          total_length, request_id, len(metadata), len(payload), len(nonce), reserved_1)
    covered = header + metadata + nonce + payload
    return covered + struct.pack("<I", crc32(covered))


def recrc(packet: bytes) -> bytes:
    body = bytes(packet[:-CRC_BYTES])
    return body + struct.pack("<I", crc32(body))


def tensor_metadata(split_id: int, channels: int, length: int, scales: list) -> bytes:
    if len(scales) != channels:
        raise ValueError("one scale per channel")
    return (_TENSOR_FIELDS.pack(split_id, DTYPE_INT8, LAYOUT_NCL, 3, SCHEME_PER_CHANNEL, 1, 0,
                                channels * length)
            + struct.pack("<4I", 1, channels, length, channels)
            + struct.pack(f"<{channels}f", *scales)
            + struct.pack(f"<{channels}i", *([0] * channels)))


def encode_request(request_id: int, model_profile_id: int, split_id: int, channels: int, length: int,
                   scales: list, payload: bytes, descriptor: bytes | None = None,
                   nonce: bytes | None = None) -> bytes:
    """Plain request when descriptor/nonce are None; I2/1 request otherwise (payload = transformed bytes)."""
    if (descriptor is None) != (nonce is None):
        raise ValueError("descriptor and nonce go together")
    if len(payload) != channels * length:
        raise ValueError("payload must be C*L bytes")
    metadata = struct.pack("<I", model_profile_id) + tensor_metadata(split_id, channels, length, scales)
    flags = 0
    if descriptor is not None:
        if len(descriptor) != DESCRIPTOR_BYTES or len(nonce) != NONCE_BYTES:
            raise ValueError("descriptor 28 B, nonce 12 B")
        metadata += descriptor
        flags = FLAG_I2_TRANSFORMED
    return frame(MSG_REQUEST, flags, request_id, metadata, nonce or b"", payload)


def encode_response(request_id: int, logits: list) -> bytes:
    if len(logits) != RESULT_COUNT or not all(math.isfinite(v) for v in logits):
        raise ValueError("five finite logits")
    payload = struct.pack(f"<{RESULT_COUNT}f", *logits)
    metadata = _RESPONSE_META.pack(STATUS["OK"], RESULT_SCORE_VECTOR, RESULT_DTYPE_FLOAT32, RESULT_COUNT)
    return frame(MSG_RESPONSE, 0, request_id, metadata, b"", payload)


def encode_error(request_id: int, status: int) -> bytes:
    if status == STATUS["OK"] or status not in STATUS_NAME:
        raise ValueError("error status must be a known non-OK code")
    metadata = _RESPONSE_META.pack(status, RESULT_NONE, RESULT_DTYPE_NONE, 0)
    return frame(MSG_ERROR, 0, request_id, metadata, b"", b"")


@dataclass(frozen=True)
class Header:
    version: int
    message_type: int
    flags: int
    header_length: int
    reserved_0: int
    total_length: int
    request_id: int
    metadata_length: int
    payload_length: int
    nonce_length: int
    reserved_1: int


def parse_envelope(packet: bytes, max_packet: int) -> Header:
    """Stage A (section 7.1): any failure is a silent drop."""
    if len(packet) < FIXED_HEADER:
        raise Drop("SHORT")
    fields = _HEADER.unpack_from(packet, 0)
    if fields[0] != MAGIC:
        raise Drop("MAGIC")
    h = Header(*fields[1:])
    if h.total_length != len(packet):
        raise Drop("FRAME_LENGTH")
    if h.total_length > max_packet:
        raise Drop("TOO_LARGE")
    if h.header_length != FIXED_HEADER + h.metadata_length + h.nonce_length:
        raise Drop("HEADER_LENGTH")
    if h.total_length != h.header_length + h.payload_length + CRC_BYTES:
        raise Drop("TOTAL_LENGTH")
    if struct.unpack_from("<I", packet, h.total_length - CRC_BYTES)[0] != crc32(packet[:-CRC_BYTES]):
        raise Drop("CRC")
    return h


def scale_is_fp16_normal(bits: int) -> bool:
    """Wire scale must be a positive normal FP16 value expanded exactly to FP32."""
    value = struct.unpack("<f", struct.pack("<I", bits))[0]
    if not math.isfinite(value) or not 2.0 ** -14 <= value <= 65504.0:
        return False
    return struct.unpack("<e", struct.pack("<e", value))[0] == value


@dataclass(frozen=True)
class Request:
    request_id: int
    flags: int
    model_profile_id: int
    split: Split
    scales: tuple
    descriptor: bytes
    nonce: bytes
    payload: bytes

    @property
    def transformed(self) -> bool:
        return self.flags == FLAG_I2_TRANSFORMED


def parse_request(packet: bytes, profile: Profile) -> Request:
    """Stages A-D of section 7 in the normative order. Raises Drop or Reject."""
    h = parse_envelope(packet, profile.max_packet)
    rid = h.request_id

    def reject(name: str):
        raise Reject(name, rid)

    if h.version != VERSION:
        reject("UNSUPPORTED_VERSION")
    if h.message_type != MSG_REQUEST:
        reject("INVALID_MESSAGE_TYPE")
    if rid == 0:
        reject("INVALID_REQUEST_ID")
    # Edge duplicate-cache lookup happens here (stateful, binding section 8).
    if h.reserved_0 or h.reserved_1:
        reject("INVALID_LENGTH")
    if h.flags not in (0, FLAG_I2_TRANSFORMED):
        reject("UNSUPPORTED_FLAGS")
    transformed = h.flags == FLAG_I2_TRANSFORMED
    if h.nonce_length != (NONCE_BYTES if transformed else 0):
        reject("INVALID_NONCE")
    if h.payload_length > profile.max_payload:
        reject("PAYLOAD_TOO_LARGE")
    metadata = packet[FIXED_HEADER:FIXED_HEADER + h.metadata_length]
    if len(metadata) < 16:
        reject("INVALID_LENGTH")
    model, split_id, dtype, layout, ndim, scheme, axis, reserved, count = _TENSOR_PREFIX.unpack_from(metadata, 0)
    if model != profile.model_profile_id:
        reject("UNKNOWN_MODEL_PROFILE")
    split = profile.splits.get(split_id)
    if split is None:
        reject("UNSUPPORTED_SPLIT")
    if dtype != DTYPE_INT8:
        reject("UNSUPPORTED_DTYPE")
    if layout != LAYOUT_NCL:
        reject("UNSUPPORTED_LAYOUT")
    if ndim != 3 or reserved != 0:
        reject("INVALID_TENSOR_METADATA")
    if scheme != SCHEME_PER_CHANNEL or axis != 1:
        reject("UNSUPPORTED_QUANTIZATION")
    if len(metadata) < REQUEST_PREFIX_BYTES:
        reject("INVALID_LENGTH")
    n, c, l, quant_count = struct.unpack_from("<4I", metadata, 16)
    if (n, c, l) != (1, split.channels, split.length) or count != c * l:
        reject("INVALID_TENSOR_METADATA")
    if h.payload_length != count:
        reject("INVALID_LENGTH")
    if quant_count != c:
        reject("UNSUPPORTED_QUANTIZATION")
    if h.metadata_length != REQUEST_PREFIX_BYTES + 8 * c + (DESCRIPTOR_BYTES if transformed else 0):
        reject("INVALID_LENGTH")
    scale_bits = struct.unpack_from(f"<{c}I", metadata, REQUEST_PREFIX_BYTES)
    zero_points = struct.unpack_from(f"<{c}i", metadata, REQUEST_PREFIX_BYTES + 4 * c)
    if not all(scale_is_fp16_normal(bits) for bits in scale_bits) or any(zero_points):
        reject("UNSUPPORTED_QUANTIZATION")
    descriptor = nonce = b""
    if transformed:
        descriptor = bytes(metadata[REQUEST_PREFIX_BYTES + 8 * c:])
        (version, algorithm, d_dtype, d_layout, d_model, d_split, d_n, d_c, d_reserved,
         d_l, key_id, d_length) = _DESCRIPTOR.unpack(descriptor)
        if (version, algorithm, d_dtype, d_layout, d_n, d_reserved) != (1, 1, DTYPE_INT8, LAYOUT_NCL, 1, 0):
            reject("INVALID_I2_DESCRIPTOR")
        if (d_model, d_split, d_c, d_l, d_length) != (model, split_id, c, l, count):
            reject("INVALID_I2_DESCRIPTOR")
        if key_id != profile.key_id:
            reject("KEY_UNAVAILABLE")
        nonce = bytes(packet[FIXED_HEADER + h.metadata_length:h.header_length])
        sender_id, sequence = struct.unpack("<IQ", nonce)
        if sender_id not in profile.sender_ids or sequence == 0:
            reject("INVALID_NONCE")
    scales = tuple(struct.unpack("<f", struct.pack("<I", bits))[0] for bits in scale_bits)
    return Request(rid, h.flags, model, split, scales, descriptor, nonce,
                   bytes(packet[h.header_length:h.header_length + h.payload_length]))


def recover_q(request: Request, keys: dict) -> bytes:
    """Stage E/F: unprotect first (if I2), then reject q=-128. Raises Reject."""
    q = request.payload
    if request.transformed:
        key_id = struct.unpack_from("<I", request.descriptor, 20)[0]
        key = keys.get(key_id)
        if key is None:
            raise Reject("KEY_UNAVAILABLE", request.request_id)
        split = request.split
        active = i2.Profile(request.model_profile_id, split.split_id, split.channels, split.length,
                            key_id, min(i2.MAX_PAYLOAD_BYTES, split.channels * split.length))
        try:
            q = i2.unprotect(q, request.descriptor, request.nonce, key, active)
        except i2.I2Error as error:
            raise Reject(I2_TO_I1[error.code], request.request_id) from None
    if 0x80 in q:
        raise Reject("UNSUPPORTED_QUANTIZATION", request.request_id)
    return q


def dequantize(request: Request, q: bytes) -> list:
    """NCL float32 values of the original channels; Edge reshapes to NC when the model needs it."""
    length = request.split.length
    values = []
    for index, byte in enumerate(q):
        signed = byte - 256 if byte >= 128 else byte
        product = signed * request.scales[index // length]
        values.append(struct.unpack("<f", struct.pack("<f", product))[0])
    return values


def receive_request(packet: bytes, profile: Profile, keys: dict, tail=None) -> bytes | None:
    """Receiver pipeline. Returns response bytes, or None for a silent drop.

    tail(split, values) -> 5 logits runs the frozen model tail; s10 (no Edge
    tail) answers with the dequantized logits unchanged (identity).
    """
    try:
        request = parse_request(packet, profile)
    except Drop:
        return None
    except Reject as error:
        return encode_error(error.request_id, error.status)
    try:
        values = dequantize(request, recover_q(request, keys))
    except Reject as error:
        return encode_error(error.request_id, error.status)
    if not request.split.edge_tail:
        logits = values
    elif tail is None:
        return encode_error(request.request_id, STATUS["INFERENCE_FAILED"])
    else:
        logits = tail(request.split, values)
    if len(logits) != RESULT_COUNT or not all(math.isfinite(v) for v in logits):
        return encode_error(request.request_id, STATUS["INFERENCE_FAILED"])
    return encode_response(request.request_id, logits)


def parse_response(packet: bytes, expected_request_id: int, max_packet: int) -> tuple:
    """Device side. Returns ('OK', logits) or ('ERROR', status); raises Drop otherwise."""
    h = parse_envelope(packet, max_packet)
    if h.version != VERSION or h.message_type not in (MSG_RESPONSE, MSG_ERROR):
        raise Drop("TYPE")
    if h.request_id == 0 or h.request_id != expected_request_id:
        raise Drop("REQUEST_ID")
    if h.reserved_0 or h.reserved_1 or h.flags or h.nonce_length or h.metadata_length != _RESPONSE_META.size:
        raise Drop("RESPONSE_HEADER")
    status, result_type, result_dtype, count = _RESPONSE_META.unpack_from(packet, FIXED_HEADER)
    if h.message_type == MSG_RESPONSE:
        if (status, result_type, result_dtype, count, h.payload_length) != (
                STATUS["OK"], RESULT_SCORE_VECTOR, RESULT_DTYPE_FLOAT32, RESULT_COUNT, 4 * RESULT_COUNT):
            raise Drop("RESULT")
        logits = list(struct.unpack_from(f"<{RESULT_COUNT}f", packet, h.header_length))
        if not all(math.isfinite(v) for v in logits):
            raise Drop("NON_FINITE")
        return "OK", logits
    if status == STATUS["OK"] or status not in STATUS_NAME or (result_type, result_dtype, count,
                                                              h.payload_length) != (0, 0, 0, 0):
        raise Drop("ERROR_RESULT")
    return "ERROR", status


def predicted_class(logits: list) -> int:
    """Argmax on raw logits (no softmax); ties pick the smallest index."""
    best = 0
    for index in range(1, len(logits)):
        if logits[index] > logits[best]:
            best = index
    return best
