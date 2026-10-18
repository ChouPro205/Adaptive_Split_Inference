#!/usr/bin/env python3
"""Host tests of the portable week 6 firmware modules (device/week6/*.c) against the references.

Compiles frag.c, exchange.c, nonce_store.c, packets.c, sha256.c together with the unmodified
contracts/i1v2_ref/i1v2_codec.c and contracts/i2_ref/i2_reference.c into a host DLL (gcc on
PATH or CC) and checks them via ctypes against contracts/i1v2_ref (Reassembler, nonce model,
vectors.json), hashlib and, when hydrated, the SV3 50-vector P1 package. Host evidence only:
not MCU, radio, NVS or power-loss evidence. Run: python -B device/scripts/test_week6_host.py
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEEK6 = ROOT / "device" / "week6"
REF = ROOT / "contracts" / "i1v2_ref"
I2REF = ROOT / "contracts" / "i2_ref"
PACKAGE = ROOT / "ml" / "artifacts" / "week6" / "mitdb-week6-p1-50-20261016-v1"
sys.path.insert(0, str(REF))
sys.path.insert(0, str(I2REF))

import i1_ble_binding as ble  # noqa: E402
import i1v2_reference as ref  # noqa: E402
import nonce_reservation as nr  # noqa: E402

VECTORS = json.loads((REF / "vectors.json").read_text(encoding="utf-8"))
PUBLIC_KEY = bytes.fromhex(VECTORS["public_test_key_hex"])
SOURCES = [WEEK6 / n for n in ("frag.c", "exchange.c", "nonce_store.c", "packets.c", "sha256.c",
                               "host_test/week6_shim.c")] + [REF / "i1v2_codec.c",
                                                             I2REF / "i2_reference.c"]
U8P = ctypes.POINTER(ctypes.c_uint8)
REASM_NAMES = ["malformed_fragment", "inconsistent_fragment", "orphan_fragment",
               "duplicate_fragment", "superseded_transfer", "overlap_conflict", "gap",
               "frame_header_mismatch", "reassembly_timeout", "disconnect", "rx_busy",
               "aborted_transfers", "frames_delivered"]
EXCH_NAMES = ["planned", "sent_first", "retries", "timeouts", "disconnect_abort", "tx_stall",
              "completed", "failed", "error_final", "edge_busy", "crc_fail", "byte_mismatch",
              "duplicate_response", "stale_response", "invalid_response", "wrong_stream"]
ACT_SEND, ACT_WAIT, ACT_FINISHED = 0, 1, 2
(S_IDLE, S_SEND, S_SENDING, S_WAITING, S_RETRY_WAIT, S_RECONNECT_WAIT, S_DONE, S_ERROR,
 S_FAILED) = range(9)
RX_DROPPED, RX_MATCH, RX_EDGE_BUSY, RX_ERROR_FINAL = range(4)
READY, UNPROVISIONED, FAULT = range(3)
F_NONE, F_FAIL_WRITE, F_CRASH_BEFORE, F_CRASH_AFTER, F_WRITE_ZERO, F_BAD_READBACK = range(6)
PROV = ["OK", "NOT_IN_REGISTRY", "STATE_IN_USE", "STATE_UNREADABLE", "WRITE_FAILED", "READBACK"]
TMP = Path(tempfile.mkdtemp(prefix="week6_host_"))


def build_library() -> ctypes.CDLL:
    cc = os.environ.get("CC") or shutil.which("gcc")
    if not cc:
        raise unittest.SkipTest("gcc not found (set CC)")
    out = TMP / ("week6_shim.dll" if os.name == "nt" else "week6_shim.so")
    cmd = [cc, "-std=c11", "-O2", "-shared", "-fPIC", "-Wall", "-Wextra", "-Wshadow", "-Werror",
           "-I", str(WEEK6), "-I", str(REF), "-I", str(I2REF), "-o", str(out)] + [str(s) for s in SOURCES]
    subprocess.run(cmd, check=True)
    lib = ctypes.CDLL(str(out))
    lib.shim_reasm_counter_name.restype = ctypes.c_char_p
    lib.shim_nonce_reason_name.restype = ctypes.c_char_p
    for name in ("shim_frag_count", "shim_exch_attempts", "shim_exch_timeout", "shim_build",
                 "shim_frame_length", "shim_nonce_writes", "shim_store_writes", "shim_next_request_id"):
        getattr(lib, name).restype = ctypes.c_uint32
    lib.shim_frag_data_bytes.restype = ctypes.c_uint16
    lib.shim_next_transfer_id.restype = ctypes.c_uint16
    lib.shim_exch_status.restype = ctypes.c_uint16
    return lib


LIB = build_library()


def buf(data: bytes):
    return (ctypes.c_uint8 * max(1, len(data))).from_buffer_copy(data or b"\0")


class C:
    """Thin wrappers over the shim."""

    @staticmethod
    def reasm_init(capacity=ble.MAX_FRAME, streams=(1, 2), timeout=ble.REASSEMBLY_TIMEOUT_MS, hold=False):
        mask = sum(1 << s for s in streams)
        LIB.shim_reasm_init(ctypes.c_uint16(capacity), ctypes.c_uint8(mask), ctypes.c_uint32(timeout),
                            int(hold))

    @staticmethod
    def reasm_feed(data: bytes, now: int):
        frame = (ctypes.c_uint8 * ble.MAX_FRAME)()
        length, stream = ctypes.c_uint16(), ctypes.c_uint8()
        done = LIB.shim_reasm_feed(buf(data), ctypes.c_uint16(len(data)), ctypes.c_uint32(now), frame,
                                   ctypes.byref(length), ctypes.byref(stream))
        return (stream.value, bytes(frame[:length.value])) if done else None

    @staticmethod
    def reasm_counters() -> dict:
        out = (ctypes.c_uint32 * 13)()
        LIB.shim_reasm_counters(out)
        return {name: out[i] for i, name in enumerate(REASM_NAMES) if out[i]}

    @staticmethod
    def exch_counters() -> dict:
        out = (ctypes.c_uint32 * 16)()
        LIB.shim_exch_counters(out)
        return {name: out[i] for i, name in enumerate(EXCH_NAMES)}

    @staticmethod
    def poll(now: int, ready: bool = True):
        wait = ctypes.c_uint32()
        action = LIB.shim_exch_poll(ctypes.c_uint32(now), int(ready), ctypes.byref(wait))
        return action, wait.value

    @staticmethod
    def frame(echo: bool, stream: int, data: bytes, sent: bytes, now: int) -> int:
        return LIB.shim_exch_frame(int(echo), ctypes.c_uint8(stream), buf(data), len(data), buf(sent),
                                   len(sent), ctypes.c_uint32(now))

    @staticmethod
    def allocate():
        seq = ctypes.c_uint64()
        return seq.value if LIB.shim_nonce_allocate(ctypes.byref(seq)) == 0 else None

    @staticmethod
    def numbers():
        out = (ctypes.c_uint64 * 3)()
        LIB.shim_nonce_numbers(out)
        return tuple(out)

    @staticmethod
    def get(record_id: int):
        out = (ctypes.c_uint8 * 64)()
        n = LIB.shim_store_get(ctypes.c_uint16(record_id), out, 64)
        return None if n < 0 else bytes(out[:n])

    @staticmethod
    def put(record_id: int, data: bytes):
        LIB.shim_store_put(ctypes.c_uint16(record_id), buf(data), len(data))

    @staticmethod
    def reason() -> str:
        return LIB.shim_nonce_reason_name(LIB.shim_nonce_reason()).decode()

    @staticmethod
    def provision(key: bytes, key_id=65537, sender=131073) -> str:
        return PROV[LIB.shim_nonce_provision(ctypes.c_uint32(key_id), ctypes.c_uint32(sender), buf(key))]

    @staticmethod
    def build(request_id, model, split_id, channels, length, q: bytes, scale_bits, key=None,
              key_id=65537, nonce=None):
        out = (ctypes.c_uint8 * 6400)()
        transformed = (ctypes.c_uint8 * 5760)()
        recovered = (ctypes.c_uint8 * 5760)()
        scales = (ctypes.c_uint32 * len(scale_bits))(*scale_bits)
        n = LIB.shim_build(out, 6400, ctypes.c_uint32(request_id), ctypes.c_uint32(model),
                           ctypes.c_uint16(split_id), ctypes.c_uint16(channels), ctypes.c_uint32(length),
                           buf(q), scales, None if key is None else buf(key), ctypes.c_uint32(key_id),
                           None if nonce is None else buf(nonce), transformed, recovered)
        size = channels * length
        return bytes(out[:n]), bytes(transformed[:size]), bytes(recovered[:size])


def sha(data: bytes) -> bytes:
    out = (ctypes.c_uint8 * 32)()
    LIB.shim_sha256(buf(data), len(data), out)
    return bytes(out)


def float_bits(values) -> list:
    return [struct.unpack("<I", struct.pack("<f", v))[0] for v in values]


class Sha256Tests(unittest.TestCase):
    def test_matches_hashlib(self):
        rng = random.Random(6)
        for length in list(range(0, 130)) + [255, 256, 1000, 5760, 6380]:
            data = bytes(rng.randrange(256) for _ in range(length))
            self.assertEqual(sha(data), hashlib.sha256(data).digest(), length)


class FragmentTests(unittest.TestCase):
    def test_data_bytes_and_counts(self):
        for mtu in (23, 24, 185, 247, 517):
            self.assertEqual(LIB.shim_frag_data_bytes(ctypes.c_uint16(mtu)), ble.fragment_data_bytes(mtu))
            for length in (36, 44, 113, 153, 6124, 6380):
                self.assertEqual(LIB.shim_frag_count(length, ctypes.c_uint16(mtu)),
                                 ble.fragment_count(length, mtu))
        self.assertEqual(LIB.shim_frag_data_bytes(ctypes.c_uint16(22)), 0)

    def test_header_matches_vector_fragments(self):
        frame = bytes.fromhex(VECTORS["golden"]["i2_s10"]["packet_hex"])
        for name, mtu in (("i2_s10_mtu23_transfer7", 23), ("i2_s10_mtu247_transfer7", 247)):
            expected = [bytes.fromhex(h) for h in VECTORS["ble_fragments"][name]]
            chunk = ble.fragment_data_bytes(mtu)
            built = []
            for offset in range(0, len(frame), chunk):
                header = (ctypes.c_uint8 * 8)()
                LIB.shim_frag_header(header, 1, 7, offset, len(frame))
                built.append(bytes(header) + frame[offset:offset + chunk])
            self.assertEqual(built, expected, name)

    def test_transfer_id_skips_zero(self):
        last = ctypes.c_uint16(65534)
        seq = [LIB.shim_next_transfer_id(ctypes.byref(last)) for _ in range(3)]
        self.assertEqual(seq, [65535, 1, 2])


class ReassemblyTests(unittest.TestCase):
    """Differential against contracts/i1v2_ref/i1_ble_binding.Reassembler."""

    @staticmethod
    def frames(rng, count):
        out = []
        for _ in range(count):
            length = rng.choice([36, 37, 44, 113, 153, 400, 3000, 6124, 6380, rng.randint(36, 6380)])
            body = bytearray(rng.randbytes(length))
            body[0:4] = b"I1PK"
            body[12:16] = struct.pack("<I", length)
            out.append(bytes(body))
        return out

    def run_trace(self, trace):
        py = ble.Reassembler()
        C.reasm_init()
        for kind, arg, now in trace:
            if kind == "feed":
                expected = py.feed(arg, now)
                got = C.reasm_feed(arg, now)
                self.assertEqual(got, expected)
            elif kind == "tick":
                py.tick(now)
                LIB.shim_reasm_tick(ctypes.c_uint32(now))
            else:
                py.disconnect()
                LIB.shim_reasm_disconnect()
        self.assertEqual(C.reasm_counters(), {k: v for k, v in py.counters.items() if v})

    def test_differential_random_faults(self):
        rng = random.Random(20261018)
        for _ in range(300):
            trace, now, tid = [], 0, 0
            for frame in self.frames(rng, rng.randint(1, 4)):
                mtu = rng.choice([23, 24, 185, 247, 517])
                tid = tid % 0xFFFF + 1
                frags = ble.fragment(frame, rng.choice([1, 2]), tid, mtu)
                ops = []
                for f in frags:
                    r = rng.random()
                    if r < 0.03:
                        continue  # lost
                    ops.append(f)
                    if r < 0.06:
                        ops.append(f)  # duplicate
                    elif r < 0.08:
                        ops.append(f[:8] + bytes([f[8] ^ 1]) + f[9:])  # conflicting duplicate
                    elif r < 0.09:
                        ops.append(f[:1] + b"\x07" + f[2:])  # unknown stream
                    elif r < 0.10:
                        ops.append(f[:6])  # runt
                if rng.random() < 0.05 and len(ops) > 2:
                    i = rng.randrange(len(ops) - 1)
                    ops[i], ops[i + 1] = ops[i + 1], ops[i]
                for f in ops:
                    now += rng.choice([1, 5, 30, 400] if rng.random() < 0.98 else [2500])
                    trace.append(("feed", f, now))
                if rng.random() < 0.05:
                    trace.append(("disconnect", None, now))
                if rng.random() < 0.05:
                    now += 2100
                    trace.append(("tick", None, now))
            self.run_trace(trace)

    def test_rule8_rx_busy_until_released(self):
        frame = bytes.fromhex(VECTORS["golden"]["plain_s10"]["packet_hex"])
        C.reasm_init(hold=True)
        self.assertIsNotNone(C.reasm_feed(ble.fragment(frame, 1, 1, 247)[0], 0))
        self.assertIsNone(C.reasm_feed(ble.fragment(frame, 1, 2, 247)[0], 1))
        self.assertEqual(C.reasm_counters().get("rx_busy"), 1)
        LIB.shim_reasm_release()
        self.assertIsNotNone(C.reasm_feed(ble.fragment(frame, 1, 3, 247)[0], 2))

    def test_stream_mask_drops_other_stream(self):
        frame = bytes.fromhex(VECTORS["golden"]["plain_s10"]["packet_hex"])
        C.reasm_init(streams=(2,))
        self.assertIsNone(C.reasm_feed(ble.fragment(frame, 1, 1, 247)[0], 0))
        self.assertEqual(C.reasm_counters(), {"malformed_fragment": 1})


class ExchangeTests(unittest.TestCase):
    ECHO = bytes.fromhex(VECTORS["golden"]["plain_s10"]["packet_hex"])  # request_id 0x101

    def setUp(self):
        LIB.shim_exch_init(8000, 30, 2, 250, 10000)

    def send(self, now, n_resp=1):
        action, _ = C.poll(now)
        self.assertEqual(action, ACT_SEND)
        LIB.shim_exch_started(ctypes.c_uint32(now))
        LIB.shim_exch_sent(ctypes.c_uint32(now), ctypes.c_uint32(n_resp))

    def test_echo_match_completes(self):
        LIB.shim_exch_begin(0x101, 0)
        self.send(0)
        self.assertEqual(C.frame(True, 2, self.ECHO, self.ECHO, 50), RX_MATCH)
        self.assertEqual(LIB.shim_exch_state(), S_DONE)
        c = C.exch_counters()
        self.assertEqual((c["planned"], c["sent_first"], c["completed"], c["retries"]), (1, 1, 1, 0))

    def test_timeouts_backoff_and_failure(self):
        LIB.shim_exch_begin(0x101, 0)
        self.send(0, n_resp=13)                     # T = 8000 + 13 * 30
        self.assertEqual(LIB.shim_exch_timeout(), 8390)
        self.assertEqual(C.poll(8389), (ACT_WAIT, 1))
        self.assertEqual(C.poll(8390), (ACT_WAIT, 250))  # timeout -> backoff 250 ms
        self.send(8640, n_resp=13)
        self.assertEqual(C.poll(8640 + 8390), (ACT_WAIT, 500))
        self.send(8640 + 8390 + 500, n_resp=13)
        action, _ = C.poll(8640 + 8390 + 500 + 8390)
        self.assertEqual(action, ACT_FINISHED)
        self.assertEqual(LIB.shim_exch_state(), S_FAILED)
        c = C.exch_counters()
        self.assertEqual((c["sent_first"], c["retries"], c["timeouts"], c["failed"]), (1, 2, 3, 1))

    def test_retry_horizon_matches_reference(self):
        """Worst case first send -> last retry equals the reference horizon minus one T."""
        LIB.shim_exch_begin(1, 0)
        now, n_resp = 0, ble.fragment_count(64, 23)
        self.send(now, n_resp)
        first = now
        for _ in range(2):
            now += LIB.shim_exch_timeout()
            LIB.shim_exch_disconnected(ctypes.c_uint32(now))   # attempt lost, link down
            action, wait = C.poll(now, ready=False)
            now += wait                                           # backoff
            action, wait = C.poll(now, ready=False)               # reconnect wait starts
            now += wait - 1
            action, _ = C.poll(now, ready=True)
            self.assertEqual(action, ACT_SEND)
            self.send(now, n_resp)
        horizon = ble.retry_horizon_ms(64, 23)
        self.assertLessEqual(now - first + LIB.shim_exch_timeout(), horizon)
        self.assertEqual(C.exch_counters()["disconnect_abort"], 2)

    def test_reconnect_wait_expiry_fails(self):
        LIB.shim_exch_begin(5, 0)
        self.assertEqual(C.poll(0, ready=False), (ACT_WAIT, 10000))
        self.assertEqual(C.poll(10000, ready=False)[0], ACT_FINISHED)
        self.assertEqual(C.exch_counters()["failed"], 1)

    def test_stall_and_disconnect_during_send(self):
        LIB.shim_exch_begin(9, 0)
        C.poll(0)
        LIB.shim_exch_started(0)
        LIB.shim_exch_disconnected(5)        # ignored while SENDING
        LIB.shim_exch_aborted(10, 1)         # credit timeout
        self.assertEqual(LIB.shim_exch_state(), S_RETRY_WAIT)
        c = C.exch_counters()
        self.assertEqual((c["tx_stall"], c["disconnect_abort"]), (1, 0))

    def test_echo_classification(self):
        LIB.shim_exch_begin(0x101, 0)
        self.send(0)
        bad_crc = self.ECHO[:-1] + bytes([self.ECHO[-1] ^ 1])
        changed = ref.recrc(self.ECHO[:100] + bytes([self.ECHO[100] ^ 1]) + self.ECHO[101:])
        other = ref.recrc(self.ECHO[:16] + struct.pack("<I", 0x999) + self.ECHO[20:])
        self.assertEqual(C.frame(True, 1, self.ECHO, self.ECHO, 1), RX_DROPPED)
        self.assertEqual(C.frame(True, 2, bad_crc, self.ECHO, 1), RX_DROPPED)
        self.assertEqual(C.frame(True, 2, changed, self.ECHO, 1), RX_DROPPED)
        self.assertEqual(C.frame(True, 2, other, self.ECHO, 1), RX_DROPPED)
        self.assertEqual(C.frame(True, 2, self.ECHO, self.ECHO, 1), RX_MATCH)
        self.assertEqual(C.frame(True, 2, self.ECHO, self.ECHO, 2), RX_DROPPED)  # after DONE
        c = C.exch_counters()
        self.assertEqual({k: c[k] for k in ("wrong_stream", "crc_fail", "byte_mismatch",
                                             "stale_response", "duplicate_response", "completed")},
                         {"wrong_stream": 1, "crc_fail": 1, "byte_mismatch": 1, "stale_response": 1,
                          "duplicate_response": 1, "completed": 1})

    def test_response_vectors_like_reference(self):
        for case in VECTORS["response"]:
            LIB.shim_exch_init(8000, 30, 2, 250, 10000)
            LIB.shim_exch_begin(case["expected_request_id"], 0)
            self.send(0)
            packet = bytes.fromhex(case["packet_hex"])
            try:
                kind, value = ref.parse_response(packet, case["expected_request_id"], 6380)
                expected = {"OK": RX_MATCH}.get(kind) if kind == "OK" else (
                    RX_EDGE_BUSY if value == ref.STATUS["EDGE_BUSY"] else RX_ERROR_FINAL)
            except ref.Drop:
                expected = RX_DROPPED
            got = C.frame(False, 1, packet, b"", 1) if len(packet) >= 36 else RX_DROPPED
            self.assertEqual(got, expected, case["id"])

    def test_edge_busy_is_retried(self):
        LIB.shim_exch_begin(0x102, 0)
        self.send(0)
        busy = ref.encode_error(0x102, ref.STATUS["EDGE_BUSY"])
        self.assertEqual(C.frame(False, 1, busy, b"", 10), RX_EDGE_BUSY)
        self.assertEqual(C.poll(10), (ACT_WAIT, 250))
        final = ref.encode_error(0x102, ref.STATUS["INFERENCE_FAILED"])
        self.send(260)
        self.assertEqual(C.frame(False, 1, final, b"", 300), RX_ERROR_FINAL)
        self.assertEqual(LIB.shim_exch_state(), S_ERROR)
        self.assertEqual(LIB.shim_exch_status(), ref.STATUS["INFERENCE_FAILED"])
        c = C.exch_counters()
        self.assertEqual((c["edge_busy"], c["retries"], c["error_final"], c["completed"]), (1, 1, 1, 0))


class NonceTests(unittest.TestCase):
    KEY = bytes(range(32))

    def setUp(self):
        LIB.shim_store_reset()

    def test_records_match_reference(self):
        kcv = (ctypes.c_uint8 * 8)()
        LIB.shim_key_check(buf(self.KEY), kcv)
        self.assertEqual(bytes(kcv).hex(), "39fd2b7dd9c5196a")
        self.assertEqual(bytes(kcv), nr.key_check(self.KEY))
        state, prov = (ctypes.c_uint8 * 36)(), (ctypes.c_uint8 * 52)()
        LIB.shim_encode_state(state, 65537, 131073, ctypes.c_uint64(5000), kcv)
        LIB.shim_encode_provision(prov, 65537, 131073, buf(self.KEY))
        self.assertEqual(bytes(state), nr.encode_state(65537, 131073, 5000, bytes(kcv)))
        self.assertEqual(bytes(prov), nr.encode_provision(65537, 131073, self.KEY))

    def test_provision_boot_allocate_like_reference(self):
        self.assertEqual(C.provision(self.KEY), "OK")
        model = nr.Store()
        nr.provision(model, 65537, 131073, self.KEY, {65537: {131073}})
        self.assertEqual(C.get(nr.NVS_ID_NONCE_STATE), model.read(nr.NVS_ID_NONCE_STATE))
        self.assertEqual(C.get(nr.NVS_ID_PROVISION), model.read(nr.NVS_ID_PROVISION))
        self.assertEqual(LIB.shim_nonce_boot(1, ctypes.c_uint64(1024)), READY)
        alloc = nr.Allocator(model, {65537: {131073}})
        for _ in range(3000):
            self.assertEqual(C.allocate(), alloc.allocate())
        self.assertEqual(C.get(nr.NVS_ID_NONCE_STATE), model.read(nr.NVS_ID_NONCE_STATE))
        LIB.shim_nonce_boot(1, ctypes.c_uint64(1024))
        self.assertEqual(C.allocate(), 3073)

    def test_random_power_loss_never_reuses(self):
        rng = random.Random(7)
        self.assertEqual(C.provision(self.KEY), "OK")
        used, boots = [], 0
        while boots < 400:
            self.assertEqual(LIB.shim_nonce_boot(1, ctypes.c_uint64(4)), READY, C.reason())
            boots += 1
            for _ in range(rng.randint(0, 12)):
                if rng.random() < 0.2:
                    LIB.shim_store_fault(rng.choice([F_CRASH_BEFORE, F_CRASH_AFTER]))
                seq = C.allocate()
                if LIB.shim_store_crashed():
                    break  # power gone: nothing returned after the crash is used
                self.assertIsNotNone(seq)
                used.append(seq)
        self.assertEqual(len(used), len(set(used)))
        self.assertEqual(used, sorted(used))
        self.assertGreater(len(used), 1000)

    def test_write_failures_latch_fault_without_writing_more(self):
        for mode, reason in ((F_FAIL_WRITE, "WRITE_FAILED"), (F_WRITE_ZERO, "WRITE_ZERO"),
                             (F_BAD_READBACK, "READBACK")):
            LIB.shim_store_reset()
            C.provision(self.KEY)
            LIB.shim_nonce_boot(1, ctypes.c_uint64(1024))
            LIB.shim_store_fault(mode)
            self.assertIsNone(C.allocate())
            self.assertEqual(C.reason(), reason)
            writes = LIB.shim_store_writes()
            self.assertIsNone(C.allocate())  # latched: no retry, no new write
            self.assertEqual(LIB.shim_store_writes(), writes)

    def test_boot_faults_never_reinitialise(self):
        C.provision(self.KEY)
        LIB.shim_nonce_boot(1, ctypes.c_uint64(1024))
        C.allocate()
        good_state = C.get(nr.NVS_ID_NONCE_STATE)
        good_prov = C.get(nr.NVS_ID_PROVISION)
        cases = [
            ("STATE_CRC", lambda: C.put(nr.NVS_ID_NONCE_STATE, good_state[:-1] + bytes([good_state[-1] ^ 1]))),
            ("STATE_MISSING", lambda: LIB.shim_store_delete(ctypes.c_uint16(nr.NVS_ID_NONCE_STATE))),
            ("STATE_MISSING", lambda: C.put(nr.NVS_ID_NONCE_STATE, good_state[:20])),
            ("STATE_FORMAT", lambda: C.put(nr.NVS_ID_NONCE_STATE, ref.recrc(b"I2NX" + good_state[4:]))),
            ("STATE_KEY_MISMATCH", lambda: C.put(nr.NVS_ID_NONCE_STATE,
                                                 nr.encode_state(65537, 131073, 1024, bytes(8)))),
            ("PROVISION_CORRUPT", lambda: C.put(nr.NVS_ID_PROVISION, good_prov[:-1] + bytes([good_prov[-1] ^ 1]))),
            ("NOT_IN_REGISTRY", lambda: (C.put(nr.NVS_ID_PROVISION, nr.encode_provision(65538, 131073, self.KEY)),
                                         C.put(nr.NVS_ID_NONCE_STATE, nr.encode_state(65538, 131073, 1024,
                                                                                      nr.key_check(self.KEY))))),
        ]
        for reason, damage in cases:
            C.put(nr.NVS_ID_NONCE_STATE, good_state)
            C.put(nr.NVS_ID_PROVISION, good_prov)
            damage()
            before = (C.get(nr.NVS_ID_NONCE_STATE), C.get(nr.NVS_ID_PROVISION))
            writes = LIB.shim_store_writes()
            self.assertEqual(LIB.shim_nonce_boot(1, ctypes.c_uint64(1024)), FAULT, reason)
            self.assertEqual(C.reason(), reason)
            self.assertIsNone(C.allocate())
            self.assertEqual((C.get(nr.NVS_ID_NONCE_STATE), C.get(nr.NVS_ID_PROVISION)), before)
            self.assertEqual(LIB.shim_store_writes(), writes)
        LIB.shim_store_delete(ctypes.c_uint16(nr.NVS_ID_PROVISION))
        self.assertEqual(LIB.shim_nonce_boot(1, ctypes.c_uint64(1024)), UNPROVISIONED)
        self.assertEqual(LIB.shim_nonce_boot(0, ctypes.c_uint64(1024)), FAULT)
        self.assertEqual(C.reason(), "MOUNT")

    def test_exhaustion_stops(self):
        kcv = nr.key_check(self.KEY)
        C.put(nr.NVS_ID_PROVISION, nr.encode_provision(65537, 131073, self.KEY))
        C.put(nr.NVS_ID_NONCE_STATE, nr.encode_state(65537, 131073, (1 << 64) - 1 - 1024, kcv))
        LIB.shim_nonce_boot(1, ctypes.c_uint64(1024))
        self.assertEqual(C.allocate(), (1 << 64) - 1024)        # last block reaches UINT64_MAX
        C.put(nr.NVS_ID_NONCE_STATE, nr.encode_state(65537, 131073, (1 << 64) - 1 - 1023, kcv))
        LIB.shim_nonce_boot(1, ctypes.c_uint64(1024))
        self.assertIsNone(C.allocate())
        self.assertEqual(C.reason(), "EXHAUSTED")

    def test_provisioning_refuses_any_possible_reuse(self):
        self.assertEqual(C.provision(self.KEY, key_id=65538), "NOT_IN_REGISTRY")
        self.assertEqual(C.provision(self.KEY), "OK")
        self.assertEqual(C.provision(bytes(32)), "OK")          # reserved_through still 0
        LIB.shim_nonce_boot(1, ctypes.c_uint64(1024))
        C.allocate()
        self.assertEqual(C.provision(self.KEY), "STATE_IN_USE")
        prov = C.get(nr.NVS_ID_PROVISION)
        LIB.shim_store_delete(ctypes.c_uint16(nr.NVS_ID_NONCE_STATE))
        self.assertEqual(C.provision(self.KEY), "STATE_UNREADABLE")  # key without state
        LIB.shim_store_reset()
        C.put(nr.NVS_ID_NONCE_STATE, b"\xff" * 36)
        self.assertEqual(C.provision(self.KEY), "STATE_UNREADABLE")
        LIB.shim_store_reset()
        LIB.shim_store_fault(F_FAIL_WRITE)
        self.assertEqual(C.provision(self.KEY), "WRITE_FAILED")
        self.assertIsNotNone(prov)


class PacketTests(unittest.TestCase):
    def test_golden_plain_and_i2_s10(self):
        g = VECTORS["golden"]
        q = bytes.fromhex(g["plain_s10"]["q_hex"])
        scales = float_bits(g["plain_s10"]["scales"])
        frame, _, _ = C.build(0x101, 1296651265, 266, 5, 1, q, scales)
        self.assertEqual(frame.hex(), g["plain_s10"]["packet_hex"])
        nonce = bytes.fromhex(g["i2_s10"]["nonce_hex"])
        frame, transformed, recovered = C.build(0x102, 1296651265, 266, 5, 1, q, scales,
                                                key=PUBLIC_KEY, nonce=nonce)
        self.assertEqual(frame.hex(), g["i2_s10"]["packet_hex"])
        self.assertEqual(transformed.hex(), "45c1dffb03")
        self.assertEqual(recovered, q)

    def test_boundary_vectors(self):
        for case in VECTORS["boundary"]:
            packet = bytes.fromhex(case["packet_hex"])
            profile = ref.load_profile(ROOT / "contracts" / "sv3_week5_approved_registry_v2.json") \
                if case["profile"] == "registry" else ref.Profile(1, 1, frozenset({1}),
                                                                 {1: ref.Split(1, 0, 64, 90, True)}, 5760, 64, 6380)
            r = ref.parse_request(packet, profile)
            key_id = struct.unpack_from("<I", r.descriptor, 20)[0]
            frame, transformed, recovered = C.build(
                r.request_id, r.model_profile_id, r.split.split_id, r.split.channels, r.split.length,
                bytes.fromhex(case["q_hex"]), float_bits(r.scales), key=PUBLIC_KEY, key_id=key_id,
                nonce=r.nonce)
            self.assertEqual(len(frame), case["length"])
            self.assertEqual(hashlib.sha256(frame).hexdigest(), case["sha256"], case["id"])
            self.assertIn(0x80, transformed)
            self.assertEqual(recovered.hex(), case["q_hex"])

    def test_frame_lengths_match_split_table(self):
        for row in VECTORS["split_table"]:
            self.assertEqual(LIB.shim_frame_length(row["C"], row["L"], 0), row["total_plain"])
            self.assertEqual(LIB.shim_frame_length(row["C"], row["L"], 1), row["total_i2"])
        self.assertEqual(LIB.shim_frame_length(64, 90, 1), 6380)

    def test_request_id_never_zero(self):
        last = ctypes.c_uint32(0xFFFFFFFF)
        self.assertEqual(LIB.shim_next_request_id(ctypes.byref(last)), 1)

    @unittest.skipUnless((PACKAGE / "vectors.json").exists(), "SV3 P1 package not hydrated")
    def test_sv3_fifty_vectors_byte_exact(self):
        package = json.loads((PACKAGE / "vectors.json").read_text(encoding="utf-8"))
        key = bytes.fromhex(package["key_hex"])
        with_0x80 = 0
        for v in package["vectors"]:
            files = {k: (PACKAGE / p).read_bytes() for k, p in v["files"].items()}
            _, channels, length = json.loads(v["shape"]) if isinstance(v["shape"], str) else v["shape"]
            scale16 = struct.unpack(f"<{channels}H", files["scale"])
            scale_bits = [struct.unpack("<I", struct.pack("<f", float(struct.unpack("<e", struct.pack("<H", b))[0])))[0]
                          for b in scale16]
            frame, transformed, recovered = C.build(
                int(v["request_id"]), int(v["model_profile_id"]), int(v["wire_split_id"]), channels, length,
                files["q"], scale_bits, key=key, key_id=int(v["key_id"]), nonce=files["nonce"])
            self.assertEqual(transformed, files["transformed"], v["vector_index"])
            self.assertEqual(recovered, files["q"], v["vector_index"])
            self.assertEqual(frame, files["request"], v["vector_index"])
            with_0x80 += 0x80 in transformed
        self.assertEqual(len(package["vectors"]), 50)
        self.assertGreaterEqual(with_0x80, 1)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
