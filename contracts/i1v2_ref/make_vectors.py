"""Regenerate vectors.json deterministically: python -B contracts/i1v2_ref/make_vectors.py [--check]."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import i1_ble_binding as ble
import i1v2_reference as ref
from i1v2_reference import STATUS, frame

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REGISTRY = ROOT / "contracts" / "sv3_week5_approved_registry_v2.json"
OUTPUT = HERE / "vectors.json"
PUBLIC_TEST_KEY = bytes(range(32))  # Same public key as the I2/1 vectors; never operational.
PROFILE = ref.load_profile(REGISTRY)
MODEL = PROFILE.model_profile_id
SENDER = min(PROFILE.sender_ids)
S9, S10, S3 = 265, 266, 259
S10_Q = bytes([0x7F, 0x81, 0x00, 0x01, 0xFF])  # q = 127, -127, 0, 1, -1
S10_SCALES = [0.5, 0.25, 1.0, 2.0, 0.125]


def i2_parts(split_id: int, channels: int, length: int, q: bytes, sequence: int,
             sender: int = SENDER, model: int = MODEL, key_id: int = PROFILE.key_id):
    profile = ref.i2.Profile(model, split_id, channels, length, key_id, max(channels * length, 1))
    descriptor = ref.i2.descriptor(profile)
    nonce = struct.pack("<IQ", sender, sequence)
    return descriptor, nonce, ref.i2.protect(q, descriptor, nonce, PUBLIC_TEST_KEY, profile)


def pattern(channels: int, length: int) -> tuple:
    q = bytes(((c * 31 + i * 7) % 255 - 127) & 0xFF for c in range(channels) for i in range(length))
    scales = [2.0 ** -(c % 10) * (1 + (c % 4) / 4) for c in range(channels)]
    return q, scales


def plain_s10(request_id: int = 0x00000101, q: bytes = S10_Q) -> bytes:
    return ref.encode_request(request_id, MODEL, S10, 5, 1, S10_SCALES, q)


def i2_s10(request_id: int = 0x00000102, q: bytes = S10_Q, sequence: int = 1) -> bytes:
    descriptor, nonce, transformed = i2_parts(S10, 5, 1, q, sequence)
    return ref.encode_request(request_id, MODEL, S10, 5, 1, S10_SCALES, transformed, descriptor, nonce)


def patch(packet: bytes, offset: int, fmt: str, value, crc: bool = True) -> bytes:
    data = bytearray(packet)
    struct.pack_into(fmt, data, offset, value)
    return ref.recrc(bytes(data)) if crc else bytes(data)


def s10_metadata(**changes) -> bytes:
    fields = dict(model=MODEL, split=S10, dtype=2, layout=1, ndim=3, scheme=2, axis=1, reserved=0,
                  count=5, dims=(1, 5, 1), quant_count=5, scales=S10_SCALES, zero_points=[0] * 5,
                  scale_bits=None, tail=b"")
    fields.update(changes)
    scale_bytes = (struct.pack(f"<{len(fields['scale_bits'])}I", *fields["scale_bits"])
                   if fields["scale_bits"] is not None
                   else struct.pack(f"<{len(fields['scales'])}f", *fields["scales"]))
    return (struct.pack("<IHBBBBbBI", fields["model"], fields["split"], fields["dtype"], fields["layout"],
                        fields["ndim"], fields["scheme"], fields["axis"], fields["reserved"], fields["count"])
            + struct.pack("<3I", *fields["dims"]) + struct.pack("<I", fields["quant_count"])
            + scale_bytes + struct.pack(f"<{len(fields['zero_points'])}i", *fields["zero_points"])
            + fields["tail"])


def plain(metadata: bytes, payload: bytes = S10_Q, request_id: int = 0x00000201, **kwargs) -> bytes:
    return frame(ref.MSG_REQUEST, kwargs.pop("flags", 0), request_id, metadata, kwargs.pop("nonce", b""),
                 payload, **kwargs)


def i2_descriptor_patch(offset: int, fmt: str, value) -> bytes:
    """Change one descriptor field of i2_s10 and fix the CRC."""
    base = i2_s10(0x00000301)
    descriptor_at = ref.FIXED_HEADER + ref.REQUEST_PREFIX_BYTES + 8 * 5
    return patch(base, descriptor_at + offset, fmt, value)


def request_negatives() -> list:
    base = plain_s10(0x00000201)
    i2_base = i2_s10(0x00000301)
    nonce_at = ref.FIXED_HEADER + ref.REQUEST_PREFIX_BYTES + 8 * 5 + ref.DESCRIPTOR_BYTES
    flipped = bytearray(base)
    flipped[-5] ^= 0x01
    oversize_meta = s10_metadata()
    cases = [
        ("crc_mismatch", bytes(flipped), "DROP"),
        ("bad_magic", b"I1PL" + base[4:], "DROP"),
        ("truncated", base[:-1], "DROP"),
        ("total_length_mismatch", patch(base, 12, "<I", len(base) + 1), "DROP"),
        ("header_length_mismatch", patch(base, 8, "<H", 32 + 72 + 1), "DROP"),
        ("over_max_packet", plain(oversize_meta, bytes(6300)), "DROP"),
        ("version_1", patch(base, 4, "<B", 1), "UNSUPPORTED_VERSION"),
        ("version_3", patch(base, 4, "<B", 3), "UNSUPPORTED_VERSION"),
        ("message_type_response", patch(base, 5, "<B", ref.MSG_RESPONSE), "INVALID_MESSAGE_TYPE"),
        ("message_type_unknown", patch(base, 5, "<B", 0x7F), "INVALID_MESSAGE_TYPE"),
        ("request_id_zero", patch(base, 16, "<I", 0), "INVALID_REQUEST_ID"),
        ("reserved_0", patch(base, 10, "<H", 1), "INVALID_LENGTH"),
        ("reserved_1", patch(base, 30, "<H", 1), "INVALID_LENGTH"),
        ("flag_0001_reserved", patch(base, 6, "<H", 0x0001), "UNSUPPORTED_FLAGS"),
        ("flags_0003", patch(base, 6, "<H", 0x0003), "UNSUPPORTED_FLAGS"),
        ("plain_with_nonce", plain(s10_metadata(), nonce=struct.pack("<IQ", SENDER, 1)), "INVALID_NONCE"),
        ("i2_flag_without_nonce", plain(s10_metadata(tail=i2_parts(S10, 5, 1, S10_Q, 1)[0]), flags=2),
         "INVALID_NONCE"),
        ("payload_too_large", plain(s10_metadata(), bytes(5761)), "PAYLOAD_TOO_LARGE"),
        ("metadata_short", plain(struct.pack("<IHBB", MODEL, S10, 2, 1)), "INVALID_LENGTH"),
        ("unknown_model", plain(s10_metadata(model=MODEL + 1)), "UNKNOWN_MODEL_PROFILE"),
        ("model_zero", plain(s10_metadata(model=0)), "UNKNOWN_MODEL_PROFILE"),
        ("unknown_split_267", plain(s10_metadata(split=267)), "UNSUPPORTED_SPLIT"),
        ("logical_split_10_on_wire", plain(s10_metadata(split=10)), "UNSUPPORTED_SPLIT"),
        ("dtype_float32", plain(s10_metadata(dtype=1)), "UNSUPPORTED_DTYPE"),
        ("dtype_uint8", plain(s10_metadata(dtype=3)), "UNSUPPORTED_DTYPE"),
        ("layout_nlc", plain(s10_metadata(layout=2)), "UNSUPPORTED_LAYOUT"),
        ("layout_flat", plain(s10_metadata(layout=0)), "UNSUPPORTED_LAYOUT"),
        ("ndim_2", plain(s10_metadata(ndim=2)), "INVALID_TENSOR_METADATA"),
        ("reserved_tensor", plain(s10_metadata(reserved=1)), "INVALID_TENSOR_METADATA"),
        ("scheme_per_tensor", plain(s10_metadata(scheme=1)), "UNSUPPORTED_QUANTIZATION"),
        ("axis_2", plain(s10_metadata(axis=2)), "UNSUPPORTED_QUANTIZATION"),
        ("dims_c6", plain(s10_metadata(dims=(1, 6, 1))), "INVALID_TENSOR_METADATA"),
        ("dims_nc_swapped_1x1x5", plain(s10_metadata(dims=(1, 1, 5))), "INVALID_TENSOR_METADATA"),
        ("element_count_wrong", plain(s10_metadata(count=6)), "INVALID_TENSOR_METADATA"),
        ("payload_length_short", plain(s10_metadata(), S10_Q[:4]), "INVALID_LENGTH"),
        ("quant_count_wrong", plain(s10_metadata(quant_count=4)), "UNSUPPORTED_QUANTIZATION"),
        ("metadata_trailing_byte", plain(s10_metadata(tail=b"\0")), "INVALID_LENGTH"),
        ("scale_zero", plain(s10_metadata(scale_bits=[0x3F000000] * 4 + [0])), "UNSUPPORTED_QUANTIZATION"),
        ("scale_negative", plain(s10_metadata(scale_bits=[0xBF000000] * 5)), "UNSUPPORTED_QUANTIZATION"),
        ("scale_nan", plain(s10_metadata(scale_bits=[0x7FC00000] * 5)), "UNSUPPORTED_QUANTIZATION"),
        ("scale_inf", plain(s10_metadata(scale_bits=[0x7F800000] * 5)), "UNSUPPORTED_QUANTIZATION"),
        ("scale_not_fp16_0p1", plain(s10_metadata(scale_bits=[0x3DCCCCCD] * 5)), "UNSUPPORTED_QUANTIZATION"),
        ("scale_fp16_subnormal", plain(s10_metadata(scales=[2.0 ** -15] * 5)), "UNSUPPORTED_QUANTIZATION"),
        ("scale_above_65504", plain(s10_metadata(scales=[65536.0] * 5)), "UNSUPPORTED_QUANTIZATION"),
        ("zero_point_nonzero", plain(s10_metadata(zero_points=[0, 0, 1, 0, 0])), "UNSUPPORTED_QUANTIZATION"),
        ("i2_version_2", i2_descriptor_patch(0, "<B", 2), "INVALID_I2_DESCRIPTOR"),
        ("i2_algorithm_2", i2_descriptor_patch(1, "<B", 2), "INVALID_I2_DESCRIPTOR"),
        ("i2_descriptor_reserved", i2_descriptor_patch(14, "<H", 1), "INVALID_I2_DESCRIPTOR"),
        ("i2_descriptor_model_mismatch", i2_descriptor_patch(4, "<I", MODEL + 1), "INVALID_I2_DESCRIPTOR"),
        ("i2_descriptor_split_mismatch", i2_descriptor_patch(8, "<H", S9), "INVALID_I2_DESCRIPTOR"),
        ("i2_descriptor_length_mismatch", i2_descriptor_patch(24, "<I", 6), "INVALID_I2_DESCRIPTOR"),
        ("i2_key_id_unknown", i2_descriptor_patch(20, "<I", PROFILE.key_id + 1), "KEY_UNAVAILABLE"),
        ("i2_sender_unknown", patch(i2_base, nonce_at, "<I", SENDER + 1), "INVALID_NONCE"),
        ("i2_sequence_zero", patch(i2_base, nonce_at + 4, "<Q", 0), "INVALID_NONCE"),
    ]
    return [{"id": name, "packet_hex": packet.hex(), "expected": expected} for name, packet, expected in cases]


def pipeline_cases() -> list:
    """Receiver results after parsing (key state, unprotect, q check, identity tail)."""
    q_minus128 = bytes([0x80, 0x01, 0x02, 0x03, 0x04])
    return [
        {"id": "plain_q_minus128", "packet_hex": plain_s10(0x401, q_minus128).hex(), "keys": "public",
         "expected": "UNSUPPORTED_QUANTIZATION"},
        {"id": "i2_q_minus128_after_unprotect", "packet_hex": i2_s10(0x402, q_minus128, 2).hex(),
         "keys": "public", "expected": "UNSUPPORTED_QUANTIZATION"},
        {"id": "i2_key_not_loaded", "packet_hex": i2_s10(0x403).hex(), "keys": "none",
         "expected": "KEY_UNAVAILABLE"},
        {"id": "plain_s10_identity", "packet_hex": plain_s10(0x404).hex(), "keys": "none", "expected": "OK"},
        {"id": "i2_s10_identity", "packet_hex": i2_s10(0x405).hex(), "keys": "public", "expected": "OK"},
    ]


def response_cases() -> list:
    ok = ref.encode_response(0x102, [63.5, -31.75, 0.0, 2.0, -0.125])
    error = ref.encode_error(0x102, STATUS["UNSUPPORTED_QUANTIZATION"])
    meta = ref.FIXED_HEADER
    cases = [
        ("ok", ok, "OK"),
        ("error_unsupported_quantization", error, "ERROR"),
        ("wrong_request_id", patch(ok, 16, "<I", 0x103), "DROP"),
        ("version_1", patch(ok, 4, "<B", 1), "DROP"),
        ("type_request", patch(ok, 5, "<B", ref.MSG_REQUEST), "DROP"),
        ("flags_nonzero", patch(ok, 6, "<H", 2), "DROP"),
        ("status_nonzero_in_response", patch(ok, meta, "<H", 1), "DROP"),
        ("result_count_4", patch(ok, meta + 4, "<I", 4), "DROP"),
        ("result_type_class_id", patch(ok, meta + 2, "<B", 1), "DROP"),
        ("logit_nan", patch(ok, meta + 8, "<I", 0x7FC00000), "DROP"),
        ("logit_inf", patch(ok, meta + 12, "<I", 0xFF800000), "DROP"),
        ("error_status_ok", patch(error, meta, "<H", 0), "DROP"),
        ("error_status_unknown", patch(error, meta, "<H", 0x0015), "DROP"),
        ("error_with_payload", frame(ref.MSG_ERROR, 0, 0x102, error[meta:meta + 8], b"", b"\0\0\0\0"), "DROP"),
        ("crc_mismatch", ok[:-1] + bytes([ok[-1] ^ 0xFF]), "DROP"),
    ]
    return [{"id": name, "packet_hex": packet.hex(), "expected_request_id": 0x102, "expected": expected}
            for name, packet, expected in cases]


def boundary_cases() -> list:
    out = []
    row = PROFILE.splits[S3]
    q, scales = pattern(row.channels, row.length)
    descriptor, nonce, transformed = i2_parts(S3, row.channels, row.length, q, 3)
    packet = ref.encode_request(0x00000501, MODEL, S3, row.channels, row.length, scales, transformed,
                                descriptor, nonce)
    out.append({"id": "i2_s3_largest_registry_split", "profile": "registry", "packet_hex": packet.hex(),
                "q_hex": q.hex(), "sha256": hashlib.sha256(packet).hexdigest(), "length": len(packet)})
    # Design ceiling C=64, payload 5760: no registry split has this shape, so a
    # PUBLIC_TEST_ONLY profile (model 1, split 1, key 1, sender 1) is used.
    q, scales = pattern(64, 90)
    descriptor, nonce, transformed = i2_parts(1, 64, 90, q, 1, sender=1, model=1, key_id=1)
    packet = ref.encode_request(0x00000502, 1, 1, 64, 90, scales, transformed, descriptor, nonce)
    out.append({"id": "i2_ceiling_c64_payload5760", "profile": "PUBLIC_TEST_ONLY", "packet_hex": packet.hex(),
                "q_hex": q.hex(), "sha256": hashlib.sha256(packet).hexdigest(), "length": len(packet)})
    return out


def split_table() -> list:
    rows = []
    for split_id, row in sorted(PROFILE.splits.items()):
        meta_plain = ref.REQUEST_PREFIX_BYTES + 8 * row.channels
        payload = row.channels * row.length
        rows.append({"s": row.split_point, "split_id": split_id, "C": row.channels, "L": row.length,
                     "payload": payload, "metadata_plain": meta_plain,
                     "metadata_i2": meta_plain + ref.DESCRIPTOR_BYTES,
                     "total_plain": 32 + meta_plain + payload + 4,
                     "total_i2": 32 + meta_plain + ref.DESCRIPTOR_BYTES + ref.NONCE_BYTES + payload + 4,
                     "fragments_i2_mtu23": ble.fragment_count(
                         32 + meta_plain + 40 + payload + 4, 23),
                     "fragments_i2_mtu247": ble.fragment_count(
                         32 + meta_plain + 40 + payload + 4, 247)})
    return rows


def build() -> dict:
    i2_packet = i2_s10()
    return {
        "contract": "I1 v2 (protocol_version=2) + I1 BLE binding v1",
        "note": ("Protocol vectors. Tensor values and the key bytes 00..1f are PUBLIC_TEST_ONLY; "
                 "IDs come from the approved registry. Not ML activations, not operational keys."),
        "registry_sha256": hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
        "public_test_key_hex": PUBLIC_TEST_KEY.hex(),
        "golden": {
            "plain_s10": {"packet_hex": plain_s10().hex(), "q_hex": S10_Q.hex(), "scales": S10_SCALES},
            "i2_s10": {"packet_hex": i2_packet.hex(), "q_hex": S10_Q.hex(), "scales": S10_SCALES,
                       "nonce_hex": struct.pack("<IQ", SENDER, 1).hex()},
            "response_s10_identity": {"packet_hex": ref.encode_response(0x102, [63.5, -31.75, 0.0, 2.0, -0.125]).hex(),
                                      "class_index": 0},
            "response_tie": {"packet_hex": ref.encode_response(0x103, [1.0, 3.0, 3.0, -1.0, 0.0]).hex(),
                             "class_index": 1},
            "error_unsupported_quantization": {
                "packet_hex": ref.encode_error(0x102, STATUS["UNSUPPORTED_QUANTIZATION"]).hex()},
        },
        "split_table": split_table(),
        "request_negative": request_negatives(),
        "pipeline": pipeline_cases(),
        "response": response_cases(),
        "boundary": boundary_cases(),
        "ble_fragments": {
            "i2_s10_mtu23_transfer7": [f.hex() for f in ble.fragment(i2_packet, ble.STREAM_I1, 7, 23)],
            "i2_s10_mtu247_transfer7": [f.hex() for f in ble.fragment(i2_packet, ble.STREAM_I1, 7, 247)],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if vectors.json differs")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1) + "\n"
    if args.check:
        return 0 if OUTPUT.read_text(encoding="utf-8") == text else 1
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
