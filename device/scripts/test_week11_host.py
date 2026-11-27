#!/usr/bin/env python3
"""Host tests of the week 11 link tools (W11-D2, W11-D3; no dongle, no PPK2, no KV260). Needs gcc on PATH (or CC).

1. Plan: generate_week11_plan.py PASSES and is deterministic (two runs, same bytes); load_plan authenticates it and
   refuses a changed CSV; the plan digest computed by the C shim with the firmware's serialization
   (device/week11/link_plan_bytes.h + week 6 SHA-256) equals the Python digest and the header's for both sessions.
2. Echo frames: the C echo frame of every W11-D2 size (and random lengths/request IDs) equals week11_common.echo_frame
   and passes stage A of the I1 v2 reference (parse_envelope), so a binding v1 §9 echo peer accepts it; the C
   ECHO-ACK v1 equals week11_common.ack_frame, passes stage A too, and echo_ack_check refuses a changed byte,
   a wrong length or the ack of another frame.
3. check_week11 verify on a synthetic capture from the S0c refs PASSES, and FAILS with one changed body or a
   missing sample; session on a synthetic dry run PASSES, and FAILS with an entry out of order, a refused STATE
   or a wrong S0C body.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week11_host.py
"""
from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_week11_plan as gen  # noqa: E402
import week11_common as w11  # noqa: E402
import week11_link as wl  # noqa: E402

sys.path.insert(0, str(w11.ROOT / "contracts" / "i1v2_ref"))
import i1v2_reference as i1ref  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="week11_host_"))
SAMPLES = Path(os.environ.get("WEEK10_SAMPLES", r"D:\HUST\ASI_week8\samples-20261023-c"))
HAVE_CC = bool(os.environ.get("CC") or shutil.which("gcc"))
SET = "7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639"
CACHE: dict = {}


def plan_dir() -> Path:
    if "plan" not in CACHE:
        CACHE["plan"] = TMP / "plan"
        manifest = gen.generate(CACHE["plan"])
        assert manifest["status"] == "PASS", manifest["checks"]
    return CACHE["plan"]


def shim(session: int):
    key = f"shim{session}"
    if key not in CACHE:
        CACHE[key] = wl.build_link_shim(TMP / "shim", plan_dir(), session)
    return CACHE[key]


def refs() -> dict:
    if "refs" not in CACHE:
        CACHE["refs"] = wl.s0c_refs(SAMPLES)
    return CACHE["refs"]


def setUpModule():
    if not HAVE_CC:
        raise unittest.SkipTest("no gcc on PATH (set CC)")


class Plan(unittest.TestCase):
    def test_deterministic_and_authenticated(self):
        other = TMP / "plan2"
        gen.generate(other)
        for name in gen.outputs():
            self.assertEqual((plan_dir() / name).read_bytes(), (other / name).read_bytes(), name)
        plans = wl.load_plan(plan_dir())
        self.assertEqual(sorted(plans), [0, 1])
        bad = TMP / "plan_bad"
        shutil.copytree(other, bad)
        csv_path = bad / "link_plan_s0.csv"
        text = csv_path.read_text(encoding="utf-8").replace("\n1,0,0,base,IDLE,15000,0\n", "\n1,0,0,base,IDLE,15001,0\n")
        csv_path.write_text(text, encoding="utf-8", newline="\n")
        with self.assertRaises(ValueError):
            wl.load_plan(bad)

    def test_c_digest_equals_python(self):
        plans = wl.load_plan(plan_dir())
        for k in range(w11.SESSIONS):
            lib = shim(k)
            digest = w11.sha256_hex(w11.plan_bytes(plans[k]))
            self.assertEqual(lib.shim_plan_session(), k)
            self.assertEqual(lib.shim_plan_entries(), len(plans[k]))
            self.assertEqual(wl.shim_digest(lib), digest)
            self.assertEqual(lib.shim_plan_sha256().decode(), digest)


class EchoFrames(unittest.TestCase):
    def test_frames_and_acks(self):
        lib = shim(0)
        rng = random.Random(20261126)
        cases = [(n, 0x01020304) for n in w11.ECHO_SIZES] + [(36, 1), (6380, 0xFFFFFFFE)]
        cases += [(rng.randint(36, 6380), rng.randint(1, 0xFFFFFFFE)) for _ in range(200)]
        for length, rid in cases:
            full = wl.c_echo_frame(lib, length, rid, ack=False)
            self.assertEqual(full, w11.echo_frame(length, rid, ack=False), (length, rid))
            self.assertFalse(w11.echo_wants_ack(full))
            i1ref.parse_envelope(full, 6380)
            frame = wl.c_echo_frame(lib, length, rid)
            self.assertEqual(frame, w11.echo_frame(length, rid), (length, rid))
            self.assertTrue(w11.echo_wants_ack(frame))
            header = i1ref.parse_envelope(frame, 6380)
            self.assertEqual((header.total_length, header.request_id), (length, rid))
            ack = wl.c_ack(lib, frame)
            self.assertEqual(ack, w11.ack_frame(frame))
            self.assertEqual(i1ref.parse_envelope(ack, 6380).request_id, rid)
            self.assertEqual(lib.shim_echo_ack_check(ack, len(ack), frame, len(frame)), 1)
        frame = w11.echo_frame(512, 77)
        ack = bytearray(w11.ack_frame(frame))
        ack[40] ^= 1
        self.assertEqual(lib.shim_echo_ack_check(bytes(ack), len(ack), frame, len(frame)), 0)
        ack = w11.ack_frame(frame)
        self.assertEqual(lib.shim_echo_ack_check(ack[:-1], len(ack) - 1, frame, len(frame)), 0)
        other = w11.ack_frame(w11.echo_frame(512, 78))
        self.assertEqual(lib.shim_echo_ack_check(other, len(other), frame, len(frame)), 0)
        self.assertEqual(wl.c_echo_frame(lib, 35, 1), b"")
        self.assertEqual(wl.c_echo_frame(lib, 512, 0), b"")


def banner(session: int, digest: str) -> str:
    return (f"READY WEEK11 build=x variant=link-usb session={session} states={len(w11.STATES)} entries=1 "
            f"samples=100 s0c=S0C-V1 set_sha256={SET} plan_sha256={digest} plan_device_sha256={digest} plan_ok=1")


class Checkers(unittest.TestCase):
    def setUp(self):
        if not SAMPLES.exists():
            self.skipTest(f"W8-D3 set not found at {SAMPLES} (set WEEK10_SAMPLES)")
        self.plans = wl.load_plan(plan_dir())
        self.digest = w11.sha256_hex(w11.plan_bytes(self.plans[0]))

    def verify_lines(self):
        r = refs()
        lines = [banner(0, self.digest)]
        for n in range(100):
            body, scale, k = r[n]
            lines.append(f"VS0C n={n} body_len={len(body) // 2} k={k} scale={scale} body={body}")
        lines.append(f"VERIFY END samples=100 s0c=S0C-V1 set_sha256={SET} plan_sha256={self.digest} "
                     f"plan_device_sha256={self.digest} plan_ok=1")
        return lines

    def test_verify(self):
        lines = self.verify_lines()
        checks, _ = wl.check_verify(list(enumerate(lines)), refs(), 0, self.digest, SET)
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})
        bad = list(lines)
        bad[5] = bad[5][:-2] + ("00" if not bad[5].endswith("00") else "11")
        checks, details = wl.check_verify(list(enumerate(bad)), refs(), 0, self.digest, SET)
        self.assertFalse(checks["vs0c_equal_python_reference"])
        self.assertEqual(details["mismatched_samples"], [4])
        checks, _ = wl.check_verify(list(enumerate(lines[:10] + lines[11:])), refs(), 0, self.digest, SET)
        self.assertFalse(checks["vs0c_one_line_per_sample"])

    def op_line(self, e, refuse=False, s0c_body=None):
        st = w11.STATES[e.state if e.op == w11.OP_STATE else w11.BASE]
        phy = wl.GAP_PHY[st.phy]
        interval = st.interval_1250us + (1 if refuse else 0)
        body, k = 0, 0
        if e.op == w11.OP_S0C:
            body_hex, _, k = refs()[e.a]
            body = s0c_body if s0c_body is not None else len(body_hex) // 2
        length = e.a if e.op == w11.OP_ECHO else 0
        res = "REFUSED" if refuse else "OK"
        return (f"OP i={e.index} op={w11.OP_NAMES[e.op]} state={e.state} a={e.a} b={e.b} res={res} ctrl_us=200 "
                f"link_ms=40 interval_1250us={interval} latency={st.latency} timeout_10ms={st.timeout_10ms} "
                f"phy_tx={phy} phy_rx={phy} tx_len={st.tx_octets} tx_dbm={st.tx_power_dbm} hci_err=0 rid=5 "
                f"len={length} frags=1 mtu=247 enomem=0 tx_us=900 wait_us=30000 invalid=0 body={body} k={k} "
                f"head_us=80")

    def session_lines(self, first, count, refuse_at=None, s0c_wrong_at=None, swap=False):
        rows = self.plans[0][first:first + count]
        lines = [banner(0, self.digest), f"SESSION BEGIN first={first} count={count} plan_sha256={self.digest}"]
        ops = [self.op_line(e, refuse=e.index == refuse_at, s0c_body=1 if e.index == s0c_wrong_at else None)
               for e in rows]
        if swap:
            ops[2], ops[3] = ops[3], ops[2]
        failed = 1 if refuse_at is not None else 0
        return lines + ops + [f"SESSION END first={first} count={count} ok={count - failed} failed={failed}"]

    def run_session(self, lines, first, count):
        checks, _ = wl.check_session(list(enumerate(lines)), self.plans[0], first, count, refs())
        checks.update(wl.banner_checks(wl.banner_of(list(enumerate(lines))), 0, self.digest, SET))
        return checks

    def test_session(self):
        count = 200   # base block: STATE, IDLE, echoes, S0C
        checks = self.run_session(self.session_lines(0, count), 0, count)
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})
        checks = self.run_session(self.session_lines(0, count, swap=True), 0, count)
        self.assertFalse(checks["op_lines_in_plan_order"])
        checks = self.run_session(self.session_lines(0, count, refuse_at=0), 0, count)
        self.assertFalse(checks["every_state_granted"])
        self.assertFalse(checks["every_op_ok"])
        s0c = next(e.index for e in self.plans[0][:count] if e.op == w11.OP_S0C)
        checks = self.run_session(self.session_lines(0, count, s0c_wrong_at=s0c), 0, count)
        self.assertFalse(checks["echo_lengths_and_s0c_match"])
        last = self.plans[0][-(w11.RECONNECTS + 2):]   # STATE, reconnects, IDLE of the last block
        first = last[0].index
        checks = self.run_session(self.session_lines(first, len(last)), first, len(last))
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
