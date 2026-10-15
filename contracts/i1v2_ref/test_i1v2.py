"""Run with: python -B contracts/i1v2_ref/test_i1v2.py (Python 3.11+, host gcc on PATH or CC).

Host checks of the I1 v2 spec, BLE binding v1 reference and nonce reservation
model. Not evidence of MCU, BLE radio, NVS power-loss or KV260 behaviour.
"""

from __future__ import annotations

import ctypes
import gc
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import i1_ble_binding as ble  # noqa: E402
import i1v2_reference as ref  # noqa: E402
import make_vectors  # noqa: E402
import nonce_reservation as nr  # noqa: E402

VECTORS = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))
PROFILE = ref.load_profile(HERE.parents[1] / "contracts" / "sv3_week5_approved_registry_v2.json")
KEY = bytes.fromhex(VECTORS["public_test_key_hex"])
TEST_PROFILE = ref.Profile(1, 1, frozenset({1}), {1: ref.Split(1, 0, 64, 90, True)}, 5760, 64, 6380)


class CSplit(ctypes.Structure):
    _fields_ = [("split_id", ctypes.c_uint16), ("channels", ctypes.c_uint16), ("length", ctypes.c_uint32)]


class CProfile(ctypes.Structure):
    _fields_ = [("model_profile_id", ctypes.c_uint32), ("key_id", ctypes.c_uint32),
                ("sender_id", ctypes.c_uint32), ("max_payload", ctypes.c_uint32),
                ("max_packet", ctypes.c_uint32), ("split_count", ctypes.c_uint32),
                ("splits", CSplit * 16)]


class CRequest(ctypes.Structure):
    _fields_ = [("request_id", ctypes.c_uint32), ("flags", ctypes.c_uint16), ("split_id", ctypes.c_uint16),
                ("channels", ctypes.c_uint16), ("length", ctypes.c_uint32),
                ("scales_offset", ctypes.c_uint32), ("descriptor_offset", ctypes.c_uint32),
                ("nonce_offset", ctypes.c_uint32), ("payload_offset", ctypes.c_uint32),
                ("payload_length", ctypes.c_uint32)]


class CResponse(ctypes.Structure):
    _fields_ = [("status", ctypes.c_uint16), ("logits", ctypes.c_float * 5)]


def c_profile(profile: ref.Profile) -> CProfile:
    assert len(profile.sender_ids) == 1
    out = CProfile(profile.model_profile_id, profile.key_id, next(iter(profile.sender_ids)),
                   profile.max_payload, profile.max_packet, len(profile.splits))
    for index, split in enumerate(sorted(profile.splits.values(), key=lambda s: s.split_id)):
        out.splits[index] = CSplit(split.split_id, split.channels, split.length)
    return out


def py_result(packet: bytes, profile: ref.Profile = PROFILE) -> str:
    try:
        ref.parse_request(packet, profile)
    except ref.Drop:
        return "DROP"
    except ref.Reject as error:
        return error.name
    return "OK"


class CodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / ("i1v2_codec.dll" if os.name == "nt" else "libi1v2_codec.so")
        extra = [] if os.name == "nt" else ["-fPIC"]
        subprocess.run([os.environ.get("CC", "gcc"), "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-pedantic", *extra, "-shared", "-o", str(library), str(HERE / "i1v2_codec.c")],
                       check=True)
        cls.c = ctypes.CDLL(str(library))
        cls.c.i1v2_parse_request.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(CProfile),
                                             ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(CRequest)]
        cls.c.i1v2_parse_response.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32,
                                              ctypes.c_uint32, ctypes.POINTER(CResponse)]
        cls.c.i1v2_encode_request.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32,
                                              ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32,
                                              ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                                              ctypes.c_char_p, ctypes.c_char_p]
        cls.c.i1v2_encode_response.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32,
                                               ctypes.POINTER(ctypes.c_float)]
        cls.c.i1v2_encode_error.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint16]
        for name in ("i1v2_encode_request", "i1v2_encode_response", "i1v2_encode_error"):
            getattr(cls.c, name).restype = ctypes.c_size_t
        cls.c.i1v2_crc32.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        cls.c.i1v2_crc32.restype = ctypes.c_uint32
        cls.profile = c_profile(PROFILE)
        cls.test_profile = c_profile(TEST_PROFILE)

    @classmethod
    def tearDownClass(cls) -> None:
        if os.name == "nt":
            import _ctypes
            _ctypes.FreeLibrary(cls.c._handle)
        cls.c = None
        gc.collect()
        cls.temp.cleanup()

    def c_parse(self, packet: bytes, profile=None):
        request_id = ctypes.c_uint32(0xDEADBEEF)
        view = CRequest()
        result = self.c.i1v2_parse_request(packet, len(packet), ctypes.byref(profile or self.profile),
                                           ctypes.byref(request_id), ctypes.byref(view))
        name = "DROP" if result == -1 else ref.STATUS_NAME[result]
        return name, request_id.value, view

    def c_response(self, packet: bytes, expected_request_id: int):
        view = CResponse()
        result = self.c.i1v2_parse_response(packet, len(packet), expected_request_id, 6380, ctypes.byref(view))
        return result, view

    def c_encode(self, request_id, split_id, channels, length, scales, payload, descriptor=None, nonce=None):
        bits = (ctypes.c_uint32 * channels)(*struct.unpack(f"<{channels}I", struct.pack(f"<{channels}f", *scales)))
        out = ctypes.create_string_buffer(8192)
        size = self.c.i1v2_encode_request(out, len(out), request_id, PROFILE.model_profile_id, split_id,
                                          channels, length, bits, payload, descriptor, nonce)
        return out.raw[:size]

    # ---- golden bytes -------------------------------------------------------------

    def test_vectors_file_is_reproducible(self):
        self.assertEqual(make_vectors.build(), VECTORS)

    def test_plain_s10_golden_assembled_independently(self):
        # Literal field values from the spec tables, not the reference encoder.
        metadata = (struct.pack("<I", 1296651265) + struct.pack("<HBBBBbBI", 266, 2, 1, 3, 2, 1, 0, 5)
                    + struct.pack("<3I", 1, 5, 1) + struct.pack("<I", 5)
                    + bytes.fromhex("0000003f" "0000803e" "0000803f" "00000040" "0000003e")
                    + bytes(20))
        payload = bytes.fromhex("7f810001ff")
        self.assertEqual(len(metadata), 72)
        header = struct.pack("<4sBBHHHIIIIHH", b"I1PK", 2, 1, 0, 104, 0, 113, 0x101, 72, 5, 0, 0)
        packet = header + metadata + payload
        packet += struct.pack("<I", zlib.crc32(packet))
        self.assertEqual(packet.hex(), VECTORS["golden"]["plain_s10"]["packet_hex"])
        self.assertEqual(self.c.i1v2_crc32(packet[:-4], len(packet) - 4), zlib.crc32(packet[:-4]))
        self.assertEqual(self.c.i1v2_crc32(b"123456789", 9), 0xCBF43926)

    def test_i2_s10_golden_layout(self):
        packet = bytes.fromhex(VECTORS["golden"]["i2_s10"]["packet_hex"])
        self.assertEqual(len(packet), 32 + 100 + 12 + 5 + 4)
        self.assertEqual(struct.unpack_from("<H", packet, 6)[0], 0x0002)
        self.assertEqual((struct.unpack_from("<H", packet, 8)[0], struct.unpack_from("<H", packet, 28)[0]), (144, 12))
        descriptor = packet[32 + 72:32 + 100]
        self.assertEqual(descriptor.hex(), "01010201" "0154494d" "0a01" "0100" "0500" "0000" "01000000"
                         "01000100" "05000000")
        self.assertEqual(packet[132:144].hex(), "010002000100000000000000")
        q = ref.recover_q(ref.parse_request(packet, PROFILE), {PROFILE.key_id: KEY})
        self.assertEqual(q.hex(), VECTORS["golden"]["i2_s10"]["q_hex"])
        self.assertNotEqual(packet[144:149], q)

    def test_c_and_python_encoders_match_golden(self):
        golden = VECTORS["golden"]
        q = bytes.fromhex(golden["plain_s10"]["q_hex"])
        scales = golden["plain_s10"]["scales"]
        plain = bytes.fromhex(golden["plain_s10"]["packet_hex"])
        self.assertEqual(self.c_encode(0x101, 266, 5, 1, scales, q), plain)
        self.assertEqual(ref.encode_request(0x101, PROFILE.model_profile_id, 266, 5, 1, scales, q), plain)
        packet = bytes.fromhex(golden["i2_s10"]["packet_hex"])
        descriptor, nonce, transformed = packet[104:132], packet[132:144], packet[144:149]
        self.assertEqual(self.c_encode(0x102, 266, 5, 1, scales, transformed, descriptor, nonce), packet)
        logits = [63.5, -31.75, 0.0, 2.0, -0.125]
        out = ctypes.create_string_buffer(64)
        size = self.c.i1v2_encode_response(out, 64, 0x102, (ctypes.c_float * 5)(*logits))
        self.assertEqual(out.raw[:size].hex(), golden["response_s10_identity"]["packet_hex"])
        size = self.c.i1v2_encode_error(out, 64, 0x102, 0x000C)
        self.assertEqual(out.raw[:size].hex(), golden["error_unsupported_quantization"]["packet_hex"])
        self.assertEqual(self.c.i1v2_encode_response(out, 63, 0x102, (ctypes.c_float * 5)(*logits)), 0)
        self.assertEqual(self.c.i1v2_encode_error(out, 64, 0x102, 0), 0)

    # ---- request validation ---------------------------------------------------------

    def test_golden_requests_parse_identically(self):
        for name in ("plain_s10", "i2_s10"):
            packet = bytes.fromhex(VECTORS["golden"][name]["packet_hex"])
            parsed = ref.parse_request(packet, PROFILE)
            result, request_id, view = self.c_parse(packet)
            self.assertEqual(result, "OK", name)
            self.assertEqual(request_id, parsed.request_id)
            self.assertEqual((view.split_id, view.channels, view.length, view.payload_length),
                             (266, 5, 1, 5))
            self.assertEqual(packet[view.payload_offset:view.payload_offset + 5], parsed.payload)
            self.assertEqual(view.flags, parsed.flags)
            if parsed.transformed:
                self.assertEqual(packet[view.descriptor_offset:view.descriptor_offset + 28], parsed.descriptor)
                self.assertEqual(packet[view.nonce_offset:view.nonce_offset + 12], parsed.nonce)

    def test_request_negative_vectors_on_both_parsers(self):
        seen = set()
        for case in VECTORS["request_negative"]:
            packet = bytes.fromhex(case["packet_hex"])
            with self.subTest(case=case["id"]):
                self.assertEqual(py_result(packet), case["expected"])
                c_result, request_id, _ = self.c_parse(packet)
                self.assertEqual(c_result, case["expected"])
                if case["expected"] != "DROP":
                    self.assertEqual(request_id, struct.unpack_from("<I", packet, 16)[0])
                    response = ref.receive_request(packet, PROFILE, {PROFILE.key_id: KEY})
                    # ERROR_RESPONSE v2 echoing the request_id (even 0) with the status.
                    self.assertEqual(struct.unpack_from("<BBH", response, 4), (2, ref.MSG_ERROR, 0))
                    self.assertEqual(struct.unpack_from("<I", response, 16)[0], request_id)
                    self.assertEqual(struct.unpack_from("<H", response, 32)[0], ref.STATUS[case["expected"]])
                else:
                    self.assertIsNone(ref.receive_request(packet, PROFILE, {PROFILE.key_id: KEY}))
            seen.add(case["expected"])
        expected_codes = set(ref.STATUS) - {"OK", "CRC_MISMATCH", "EDGE_BUSY", "INFERENCE_FAILED", "TIMEOUT",
                                            "DUPLICATE_CONFLICT"}
        self.assertEqual(seen - {"DROP"}, expected_codes)

    def test_pipeline_cases(self):
        for case in VECTORS["pipeline"]:
            packet = bytes.fromhex(case["packet_hex"])
            keys = {PROFILE.key_id: KEY} if case["keys"] == "public" else {}
            with self.subTest(case=case["id"]):
                self.assertEqual(self.c_parse(packet)[0], "OK")
                response = ref.receive_request(packet, PROFILE, keys)
                request_id = struct.unpack_from("<I", packet, 16)[0]
                kind, value = ref.parse_response(response, request_id, 6380)
                if case["expected"] == "OK":
                    self.assertEqual(kind, "OK")
                    self.assertEqual(value, [63.5, -31.75, 0.0, 2.0, -0.125])  # identity of q*scale
                else:
                    self.assertEqual((kind, value), ("ERROR", ref.STATUS[case["expected"]]))

    def test_boundaries_and_0x80_in_transformed_bytes(self):
        largest, ceiling = VECTORS["boundary"]
        packet = bytes.fromhex(largest["packet_hex"])
        self.assertEqual(len(packet), 6124)
        self.assertEqual(self.c_parse(packet)[0], "OK")
        parsed = ref.parse_request(packet, PROFILE)
        self.assertIn(0x80, parsed.payload)
        self.assertEqual(ref.recover_q(parsed, {PROFILE.key_id: KEY}).hex(), largest["q_hex"])
        packet = bytes.fromhex(ceiling["packet_hex"])
        self.assertEqual(len(packet), 6380)
        self.assertEqual(len(packet), PROFILE.max_packet)
        self.assertEqual(self.c_parse(packet, self.test_profile)[0], "OK")
        self.assertEqual(py_result(packet, TEST_PROFILE), "OK")
        self.assertEqual(py_result(packet), "UNKNOWN_MODEL_PROFILE")
        over = ref.frame(1, 2, 9, packet[32:32 + 572], packet[604:616], bytes(5761))
        self.assertEqual(len(over), 6381)
        self.assertEqual(py_result(over, TEST_PROFILE), "DROP")
        self.assertEqual(self.c_parse(over, self.test_profile)[0], "DROP")

    def test_split_table_matches_encoder(self):
        rows = VECTORS["split_table"]
        self.assertEqual([row["split_id"] for row in rows], list(range(256, 267)))
        for row in rows:
            q, scales = make_vectors.pattern(row["C"], row["L"])
            descriptor, nonce, transformed = make_vectors.i2_parts(row["split_id"], row["C"], row["L"], q, 1)
            self.assertEqual(len(self.c_encode(1, row["split_id"], row["C"], row["L"], scales, q)), row["total_plain"])
            self.assertEqual(len(self.c_encode(1, row["split_id"], row["C"], row["L"], scales, transformed,
                                               descriptor, nonce)), row["total_i2"])
            self.assertEqual(row["total_i2"], 104 + 8 * row["C"] + row["payload"] + 4)
            self.assertLessEqual(row["total_i2"], 6380)
        self.assertEqual(max(row["total_i2"] for row in rows), 6124)
        self.assertEqual(104 + 8 * 64 + 5760 + 4, 6380)
        self.assertEqual([(r["C"], r["L"]) for r in rows if r["s"] in (9, 10)], [(32, 1), (5, 1)])

    def test_differential_fuzz_python_vs_c(self):
        rng = random.Random(20261015)
        bases = [bytes.fromhex(VECTORS["golden"][name]["packet_hex"]) for name in ("plain_s10", "i2_s10")]
        bases.append(bytes.fromhex(VECTORS["boundary"][0]["packet_hex"]))
        for _ in range(4000):
            data = bytearray(rng.choice(bases))
            for _ in range(rng.randint(1, 3)):
                data[rng.randrange(min(len(data), 160))] = rng.randrange(256)
            packet = ref.recrc(bytes(data)) if rng.random() < 0.9 else bytes(data)
            self.assertEqual(self.c_parse(packet)[0], py_result(packet), packet[:48].hex())

    # ---- responses ------------------------------------------------------------------

    def test_response_cases_on_both_parsers(self):
        for case in VECTORS["response"]:
            packet = bytes.fromhex(case["packet_hex"])
            with self.subTest(case=case["id"]):
                try:
                    py = ref.parse_response(packet, case["expected_request_id"], 6380)[0]
                except ref.Drop:
                    py = "DROP"
                result, view = self.c_response(packet, case["expected_request_id"])
                c = "DROP" if result == -1 else ("OK" if view.status == 0 else "ERROR")
                self.assertEqual((py, c), (case["expected"], case["expected"]))

    def test_argmax_on_raw_logits_ties_pick_smallest_index(self):
        for name in ("response_s10_identity", "response_tie"):
            golden = VECTORS["golden"][name]
            packet = bytes.fromhex(golden["packet_hex"])
            kind, logits = ref.parse_response(packet, struct.unpack_from("<I", packet, 16)[0], 6380)
            self.assertEqual(ref.predicted_class(logits), golden["class_index"])
        self.assertEqual(ref.predicted_class([0.0, -0.0, 0.0, -1.0, -2.0]), 0)
        self.assertEqual(len(bytes.fromhex(VECTORS["golden"]["response_s10_identity"]["packet_hex"])), 64)
        self.assertEqual(len(bytes.fromhex(VECTORS["golden"]["error_unsupported_quantization"]["packet_hex"])), 44)

    def test_status_enum_and_i2_mapping(self):
        values = list(ref.STATUS.values())
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(sorted(values), list(range(0x15)))
        i2_errors = {"INVALID_ARGUMENT", "INVALID_NONCE", "KEY_UNAVAILABLE", "INVALID_PROFILE", "INVALID_METADATA",
                     "UNSUPPORTED_VERSION", "UNSUPPORTED_ALGORITHM", "SIZE_LIMIT", "LENGTH_MISMATCH",
                     "PROFILE_MISMATCH", "KEY_SCOPE_MISMATCH", "BUFFER_TOO_SMALL"}
        self.assertEqual(set(ref.I2_TO_I1), i2_errors)
        self.assertTrue(set(ref.I2_TO_I1.values()) <= set(ref.STATUS))


class BleBindingTests(unittest.TestCase):
    FRAME = bytes.fromhex(VECTORS["golden"]["i2_s10"]["packet_hex"])

    def frames(self):
        yield self.FRAME
        yield bytes.fromhex(VECTORS["golden"]["error_unsupported_quantization"]["packet_hex"])
        for case in VECTORS["boundary"]:
            yield bytes.fromhex(case["packet_hex"])

    def test_roundtrip_all_mtus_and_counts(self):
        for frame in self.frames():
            for mtu in (23, 24, 185, 247, 517):
                fragments = ble.fragment(frame, ble.STREAM_I1, 7, mtu)
                self.assertEqual(len(fragments), ble.fragment_count(len(frame), mtu))
                self.assertTrue(all(len(f) <= mtu - 3 for f in fragments))
                receiver = ble.Reassembler()
                results = [receiver.feed(f, i) for i, f in enumerate(fragments)]
                self.assertEqual(results[-1], (ble.STREAM_I1, frame))
                self.assertTrue(all(r is None for r in results[:-1]))
        self.assertEqual(ble.fragment_count(6380, 23), 532)
        self.assertEqual(ble.fragment_count(6380, 247), 28)
        self.assertEqual(VECTORS["ble_fragments"]["i2_s10_mtu247_transfer7"][0][:16], "0101070000009900")
        self.assertEqual(len(VECTORS["ble_fragments"]["i2_s10_mtu23_transfer7"]), 13)
        with self.assertRaises(ValueError):
            ble.fragment_data_bytes(22)
        with self.assertRaises(ValueError):
            ble.fragment(bytes(6381), ble.STREAM_I1, 1, 247)

    def test_fragment_faults(self):
        fragments = ble.fragment(self.FRAME, ble.STREAM_I1, 9, 23)
        cases = {
            "duplicate_fragment": fragments[:3] + [fragments[2]] + fragments[3:],
            "gap": fragments[:2] + fragments[3:],
            "orphan_fragment": fragments[1:],
            "overlap_conflict": fragments[:3] + [fragments[2][:-1] + bytes([fragments[2][-1] ^ 1])] + fragments[3:],
        }
        for counter, sequence in cases.items():
            receiver = ble.Reassembler()
            results = [receiver.feed(f, i) for i, f in enumerate(sequence)]
            self.assertGreaterEqual(receiver.counters.get(counter, 0), 1, counter)
            delivered = [r for r in results if r is not None]
            if counter == "duplicate_fragment":
                self.assertEqual(delivered, [(ble.STREAM_I1, self.FRAME)])
            else:
                self.assertEqual(delivered, [])
        malformed = [b"\x01\x01", ble.FRAGMENT_HEADER.pack(2, 1, 9, 0, 149) + b"I",
                     ble.FRAGMENT_HEADER.pack(1, 3, 9, 0, 149) + b"I",
                     ble.FRAGMENT_HEADER.pack(1, 1, 0, 0, 149) + b"I",
                     ble.FRAGMENT_HEADER.pack(1, 1, 9, 0, 35) + b"I",
                     ble.FRAGMENT_HEADER.pack(1, 1, 9, 0, 6381) + b"I",
                     ble.FRAGMENT_HEADER.pack(1, 1, 9, 148, 149) + b"II"]
        receiver = ble.Reassembler()
        for item in malformed:
            self.assertIsNone(receiver.feed(item, 0))
        self.assertEqual(receiver.counters["malformed_fragment"], len(malformed))

    def test_header_mismatch_timeout_disconnect_and_retry(self):
        bad = bytearray(self.FRAME)
        struct.pack_into("<I", bad, 12, len(bad) + 1)
        receiver = ble.Reassembler()
        for f in ble.fragment(bytes(bad), ble.STREAM_I1, 3, 23)[:2]:
            receiver.feed(f, 0)
        self.assertEqual(receiver.counters["frame_header_mismatch"], 1)
        fragments = ble.fragment(self.FRAME, ble.STREAM_I1, 4, 23)
        receiver = ble.Reassembler()
        receiver.feed(fragments[0], 0)
        self.assertIsNone(receiver.feed(fragments[1], ble.REASSEMBLY_TIMEOUT_MS + 1))
        self.assertEqual(receiver.counters["reassembly_timeout"], 1)
        receiver = ble.Reassembler()
        receiver.feed(fragments[0], 0)
        receiver.disconnect()
        self.assertEqual(receiver.counters["disconnect"], 1)
        # Retry after a partial attempt: new transfer_id, identical frame bytes.
        receiver = ble.Reassembler()
        for f in fragments[:5]:
            receiver.feed(f, 0)
        retry = ble.fragment(self.FRAME, ble.STREAM_I1, 5, 23)
        results = [receiver.feed(f, 1) for f in retry]
        self.assertEqual(results[-1], (ble.STREAM_I1, self.FRAME))
        self.assertEqual(receiver.counters["superseded_transfer"], 1)
        self.assertIsNone(receiver.feed(retry[-1], 2))  # late duplicate of a completed transfer
        self.assertEqual(receiver.counters["duplicate_fragment"], 1)

    def test_lossy_link_never_delivers_wrong_bytes(self):
        rng = random.Random(6)
        ids = ble.TransferIds()
        receiver = ble.Reassembler()
        frames = list(self.frames())
        delivered_ok = 0
        for round_index in range(400):
            frame = rng.choice(frames)
            transfer = ids.next()
            sequence = []
            for f in ble.fragment(frame, rng.choice((ble.STREAM_I1, ble.STREAM_DIAG_ECHO)), transfer,
                                  rng.choice((23, 64, 247))):
                roll = rng.random()
                if roll < 0.01:
                    continue
                sequence.append(f)
                if roll > 0.99:
                    sequence.append(f)
            if rng.random() < 0.05 and len(sequence) > 2:
                i = rng.randrange(len(sequence) - 1)
                sequence[i], sequence[i + 1] = sequence[i + 1], sequence[i]
            for f in sequence:
                result = receiver.feed(f, round_index * 10)
                if result is not None:
                    self.assertEqual(result[1], frame)
                    delivered_ok += 1
        self.assertGreater(delivered_ok, 100)

    def test_timer_configuration_covers_retry_horizon(self):
        self.assertEqual(ble.response_timeout_ms(64, 23), 8180)
        self.assertEqual(ble.response_timeout_ms(6380, 23), 23960)
        horizons = [ble.retry_horizon_ms(ble.INFERENCE_RESPONSE_BYTES, mtu) for mtu in range(23, 518)]
        self.assertEqual(max(horizons), ble.retry_horizon_ms(64, 23))
        self.assertEqual(max(horizons), 45290)
        self.assertGreaterEqual(ble.DUPLICATE_CACHE_TTL_MS, max(horizons) + ble.HORIZON_MARGIN_MS)
        self.assertLess(ble.EDGE_INFERENCE_DEADLINE_MS, ble.RESPONSE_TIMEOUT_BASE_MS)
        self.assertLess(ble.REASSEMBLY_TIMEOUT_MS, ble.RESPONSE_TIMEOUT_BASE_MS)
        ids = ble.TransferIds()
        ids.last = 0xFFFF
        self.assertEqual(ids.next(), 1)


class NonceReservationTests(unittest.TestCase):
    ALLOWED = {PROFILE.key_id: set(PROFILE.sender_ids)}
    SENDER = next(iter(PROFILE.sender_ids))

    def fresh(self):
        store = nr.Store()
        nr.provision(store, PROFILE.key_id, self.SENDER, KEY, self.ALLOWED)
        return store

    def test_record_layout(self):
        state = nr.encode_state(65537, 131073, 1024, nr.key_check(KEY))
        self.assertEqual(len(state), 36)
        self.assertEqual(state[:24].hex(), "49324e53" "01000000" "01000100" "01000200" "0004000000000000")
        self.assertEqual(nr.decode_state(state)[2], 1024)
        self.assertEqual(len(nr.encode_provision(65537, 131073, KEY)), 52)
        self.assertEqual(nr.key_check(KEY).hex(), "39fd2b7dd9c5196a")

    def test_sequences_start_at_one_and_reboot_skips_unused_block(self):
        store = self.fresh()
        allocator = nr.Allocator(store, self.ALLOWED)
        self.assertEqual([allocator.allocate() for _ in range(3)], [1, 2, 3])
        self.assertEqual(nr.decode_state(store.read(nr.NVS_ID_NONCE_STATE))[2], 1024)
        self.assertEqual(allocator.nonce(1).hex(), "010002000100000000000000")
        allocator = nr.Allocator(store, self.ALLOWED)
        self.assertEqual(allocator.allocate(), 1025)
        self.assertEqual(nr.decode_state(store.read(nr.NVS_ID_NONCE_STATE))[2], 2048)

    def test_random_power_loss_never_reuses_a_sequence(self):
        rng = random.Random(1)
        store = self.fresh()
        used = []
        for _ in range(300):
            allocator = nr.Allocator(store, self.ALLOWED, block=8)
            store.crash_before_write = rng.random() < 0.3
            store.crash_after_write = not store.crash_before_write and rng.random() < 0.3
            try:
                for _ in range(rng.randint(0, 20)):
                    used.append(allocator.allocate())
            except nr.PowerLoss:
                pass
            store.crash_before_write = store.crash_after_write = False
        self.assertEqual(used, sorted(set(used)))
        self.assertGreater(len(used), 500)
        self.assertLessEqual(used[-1], nr.decode_state(store.read(nr.NVS_ID_NONCE_STATE))[2])

    def test_failures_stop_and_never_reinitialise(self):
        store = self.fresh()
        allocator = nr.Allocator(store, self.ALLOWED, block=4)
        for _ in range(4):
            allocator.allocate()
        store.fail_next_write = True
        with self.assertRaisesRegex(nr.NonceStop, "WRITE_FAILED"):
            allocator.allocate()
        with self.assertRaisesRegex(nr.NonceStop, "WRITE_FAILED"):
            allocator.allocate()  # latched until reboot
        snapshot = dict(store.records)
        corrupt = bytearray(store.records[nr.NVS_ID_NONCE_STATE])
        corrupt[16] ^= 1
        store.records[nr.NVS_ID_NONCE_STATE] = bytes(corrupt)
        for _ in range(2):
            with self.assertRaisesRegex(nr.NonceStop, "STATE_CRC"):
                nr.Allocator(store, self.ALLOWED)
        self.assertEqual(store.records[nr.NVS_ID_NONCE_STATE], bytes(corrupt))  # no silent re-init
        store.records = dict(snapshot)
        del store.records[nr.NVS_ID_NONCE_STATE]
        with self.assertRaisesRegex(nr.NonceStop, "STATE_MISSING"):
            nr.Allocator(store, self.ALLOWED)
        store.records = dict(snapshot)
        store.records[nr.NVS_ID_PROVISION] = nr.encode_provision(PROFILE.key_id, self.SENDER, bytes(32))
        with self.assertRaisesRegex(nr.NonceStop, "STATE_KEY_MISMATCH"):
            nr.Allocator(store, self.ALLOWED)
        with self.assertRaisesRegex(nr.NonceStop, "UNPROVISIONED"):
            nr.Allocator(nr.Store(), self.ALLOWED)
        with self.assertRaisesRegex(nr.NonceStop, "NOT_IN_REGISTRY"):
            nr.provision(nr.Store(), PROFILE.key_id, self.SENDER + 1, KEY, self.ALLOWED)

    def test_exhaustion_stops(self):
        store = self.fresh()
        store.records[nr.NVS_ID_NONCE_STATE] = nr.encode_state(PROFILE.key_id, self.SENDER,
                                                               nr.UINT64_MAX - 1023, nr.key_check(KEY))
        allocator = nr.Allocator(store, self.ALLOWED)
        with self.assertRaisesRegex(nr.NonceStop, "EXHAUSTED"):
            allocator.allocate()


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
