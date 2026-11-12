#!/usr/bin/env python3
"""Host tests of the week 10 E_prot tools (W10-D1, W10-D2; no dongle, no PPK2). Needs gcc on PATH (or CC).

1. check_week10 verify-prot on a synthetic prot-usb VERIFY ALL + TPROT + TCONV capture written from the host
   references (q/scale = week 9 refs, protect() with the PUBLIC_TEST key = contracts/i2_ref, HEAD-only s1 output =
   host shim) PASSES, and FAILS with one changed q, protect or conv digest.
2. check_week10 session-prot on a synthetic dry run PASSES, and FAILS with a repeated nonce sequence, a sequence
   at or below the prior block, or a Flash write inside a cycle.
3. week10_prot.segment_prot_cycles + week10_ppk2.analyze_prot on a synthetic trace (boot D1 pulse, self-test, idle,
   one round of the plan): every cycle valid and mapped to the plan, one boot D1 pulse, phase energies exact; a D1
   pulse in a P0 cycle or a missing PROT in a P1 cycle are errors. week10_prot.summary over two synthetic sessions
   gives the known E_prot, paired delta and E_conv,min, and the W10-D2 rule passes/fails where it should.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week10_prot_host.py
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_week10 as chk  # noqa: E402
import energy_phases as ep  # noqa: E402
import generate_week10_plan as gen  # noqa: E402
import week10_ble as wb  # noqa: E402
import week10_common as w10  # noqa: E402
import week10_ppk2 as wp  # noqa: E402
import week10_prot as wpr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="week10_prot_host_"))
SAMPLES = Path(os.environ.get("WEEK10_SAMPLES", r"D:\HUST\ASI_week8\samples-20261023-c"))
HOST = None


def host() -> wb.HostRefs:
    global HOST
    if HOST is None:
        plan = TMP / "plan"
        gen.generate(plan)
        HOST = wb.HostRefs(SAMPLES, plan, TMP / "shim")
    return HOST


def setUpModule():
    if not (os.environ.get("CC") or shutil.which("gcc")):
        raise unittest.SkipTest("no gcc on PATH (set CC)")
    if not SAMPLES.exists():
        raise unittest.SkipTest(f"W8-D3 set not found at {SAMPLES} (set WEEK10_SAMPLES)")


def lw_of(lines):
    capture = [(i, t) for i, t in enumerate(lines)]
    return lambda tag: chk.lines_with(capture, tag)


def banner(h) -> dict:
    return {"variant": "prot-usb", "set_sha256": h.sample_set.set_sha256, "plan_sha256": w10.PROT_PLAN_SHA256,
            "plan_device_sha256": w10.PROT_PLAN_SHA256, "plan_ok": "1", "cycles": "1050", "p1_cycles": "500"}


def verify_lines(h) -> list:
    lines = []
    for s in range(10):
        for n in range(wb.SAMPLES):
            c, length, qb, sb = h.tensors[(n, s)]
            lines.append(f"VQ n={n} id={h.sample_set.samples[n].sample_id} s={s} C={c} L={length} bytes={c * length + 2 * c} "
                         f"q_sha256={wpr.sha_hex(qb)} scale_sha256={wpr.sha_hex(sb)}")
            out = wpr.public_protect(h, n, s, n + 1)
            lines.append(f"VPROT n={n} s={s} seq={n + 1} status=0 len={len(out)} sha256={wpr.sha_hex(out)} prot_cyc=1000")
    for n in range(wb.SAMPLES):
        v = h.head_values(n, 1)
        lines.append(f"VCONV n={n} s=1 values={v.size} sha256={wpr.sha_hex(v.tobytes())}")
    lines.append(f"VERIFY END kernel=FAST samples=50 splits=ALL set_sha256={h.sample_set.set_sha256}")
    for s in range(10):
        lines.append(f"TPSUM s={s} runs=50 warmup=20 irq=locked cpu_hz=64000000 prot_min=60000 prot_max=61000 "
                     f"prot_mean_x100=6050000")
    lines.append("TCSUM s=1 runs=50 warmup=20 irq=locked cpu_hz=64000000 conv_min=226000 conv_max=227000 conv_mean_x100=22650000")
    return lines


class VerifyProt(unittest.TestCase):
    def test_pass_and_fail(self):
        h = host()
        lines = verify_lines(h)
        checks, details = wpr.check_verify(lw_of(lines), banner(h), h)
        t_checks, t_details = wpr.tprot_table(lw_of(lines))
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})
        self.assertTrue(all(t_checks.values()))
        self.assertAlmostEqual(t_details["t_prot_dwt_ms"]["0"]["prot_mean_ms"], 60500 / 64000.0)
        for tag, key in (("VQ n=4 id", "q_sha256"), ("VPROT n=9 s=3", "sha256"), ("VCONV n=2 ", "sha256")):
            bad = list(lines)
            i = next(k for k, t in enumerate(bad) if t.startswith(tag))
            bad[i] = " ".join(p if not p.startswith(key + "=") else key + "=00" for p in bad[i].split(" "))
            checks, _ = wpr.check_verify(lw_of(bad), banner(h), h)
            self.assertFalse(all(checks.values()), tag)


def dry_lines(h, first, count, seq0=60700000, repeat=False, write_at=None):
    lines, seq = [], seq0
    for p in list(h.plans.prot)[first:first + count]:
        op = w10.OP_NAMES[p.op]
        sq, byts, digest = 0, 0, "-"
        if op == "P1":
            seq += 0 if (repeat and seq > seq0) else 1
            sq, byts, digest = seq, h.bytes_payload(p.split), "ab" * 32
        elif op == "P0":
            byts = h.bytes_payload(p.split)
        lines.append(f"CYCLE i={p.cycle} round={p.round} n={p.sample} id=x s={p.split} op={op} seq={sq} bytes={byts} "
                     f"ctrl_cyc=12800 head_cyc=1000 quant_cyc=10 prot_cyc=50 head_us=100 prot_us=1 "
                     f"nonce_writes={1 if write_at == p.cycle else 0} res=OK prot_sha256={digest}")
    lines.append(f"SESSION END first={first} count={count} ok={count} failed=0")
    return lines


class SessionProt(unittest.TestCase):
    def test_pass(self):
        h = host()
        checks, _ = wpr.check_session(lw_of(dry_lines(h, 0, 63)), banner(h), h, 0, 63, 60657663)
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})

    def test_fail(self):
        h = host()
        checks, _ = wpr.check_session(lw_of(dry_lines(h, 0, 63, repeat=True)), banner(h), h, 0, 63, 60657663)
        self.assertFalse(checks["p1_sequences_strictly_increasing"])
        checks, _ = wpr.check_session(lw_of(dry_lines(h, 0, 63, seq0=60657000)), banner(h), h, 0, 63, 60657663)
        self.assertFalse(checks["p1_sequences_above_prior"])
        checks, _ = wpr.check_session(lw_of(dry_lines(h, 0, 63, write_at=5)), banner(h), h, 0, 63, 60657663)
        self.assertFalse(checks["every_cycle_ok_plan_op_s_n_bytes_no_flash_write"])


def segment(trace, rows):
    st = ep.selftest_check(trace, dict(ep.DEFAULT_MAP), 200.0)
    return wpr.segment_prot_cycles(trace, st["end_sample"] + 1, rows)


def synth(plan_rows, prot_ua=2000.0, d1_in=None, drop_prot=None, conv_ms=3.5, seed=0):
    """Boot D1 pulse, self-test D0..D4 (200 ms), 30 s idle, cycles: CTRL 0.2 ms, HEAD 1 ms + s ms at 4 mA (CONV
    conv_ms), P1 PROT 0.5 ms at prot_ua; 100 ms gaps; 25 s idle after."""
    rng = np.random.default_rng(seed)
    cur, bits = [], []

    def seg(ms, ua, bit, noise=0.0):
        n = int(round(ms * 100))
        cur.append(ua + (rng.normal(0, noise, n) if noise else np.zeros(n)))
        bits.append(np.full(n, 0 if bit is None else 1 << bit, np.uint8))

    seg(50, 25.0, None)
    seg(2, 3000.0, wpr.PROT)                 # boot nonce reservation
    seg(100, 25.0, None)
    for m in (0, 1, 2, 3, 4):
        seg(200, 500.0, m)
    seg(30000, 25.4, None)
    for k, p in enumerate(plan_rows):
        op = w10.OP_NAMES[p.op]
        seg(0.2, 3000.0, wpr.CTRL)
        seg(conv_ms if op == "CONV" else 1.0 + p.split, 4000.0, wpr.DEV)
        if (op == "P1" and k != drop_prot) or k == d1_in:
            seg(0.5, prot_ua, wpr.PROT)
        seg(100, 25.4, None)
    seg(25000, 25.4, None)
    return ep.Trace(np.concatenate(cur), np.concatenate(bits), 5000.0, "synthetic", info={})


class ProtTrace(unittest.TestCase):
    rows = w10.prot_plan()[:42]

    def test_valid_and_analysis(self):
        out = TMP / "prot_analysis"
        summary = wp.analyze_prot(synth(self.rows), out, self.rows, True)
        self.assertTrue(summary["checks"]["boot_nonce_reservation_one_d1_pulse"])
        self.assertTrue(summary["checks"]["all_cycles_valid"], summary["errors"])
        self.assertTrue(summary["checks"]["diff_below_3pct_all"])
        with open(out / "analysis" / "cycles.csv", encoding="utf-8") as handle:
            cycles = list(csv.DictReader(handle))
        self.assertEqual([(int(c["split"]), c["op"]) for c in cycles], [(r.split, w10.OP_NAMES[r.op]) for r in self.rows])
        p1 = [c for c in cycles if c["op"] == "P1"]
        for c in p1:
            self.assertAlmostEqual(float(c["E_prot_uJ"]), 5.0 * 2000.0 * 0.5e-3, places=6)
            self.assertAlmostEqual(float(c["t_prot_ms"]), 0.5, places=6)

    def test_errors(self):
        k0 = next(k for k, r in enumerate(self.rows) if r.op == w10.OP_P0)
        k1 = next(k for k, r in enumerate(self.rows) if r.op == w10.OP_P1)
        cycles = segment(synth(self.rows, d1_in=k0), self.rows)
        self.assertIn("unexpected_prot", cycles[k0]["errors"])
        cycles = segment(synth(self.rows, drop_prot=k1), self.rows)
        self.assertIn("missing_prot", cycles[k1]["errors"])

    def test_summary_and_rule(self):
        rows = w10.prot_plan()[:105]
        groups = {}
        for tag, prot_ua in (("a", 2000.0), ("b", 2100.0)):
            cycles = segment(synth(rows, prot_ua=prot_ua, seed=1), rows)
            self.assertTrue(all(not c["errors"] for c in cycles), [c["errors"] for c in cycles if c["errors"]][:3])
            groups[tag] = wpr.session_groups(cycles)
        result = wpr.summary(groups)
        e = result["per_s"]["3"]["E_prot_uJ"]
        self.assertAlmostEqual(e["mean"], 5.0 * 2050.0 * 0.5e-3, places=4)
        self.assertAlmostEqual(result["per_s"]["3"]["delta_P1_minus_P0_dev_plus_prot_uJ"]["mean"], e["mean"], places=4)
        self.assertAlmostEqual(result["E_conv_min_uJ"]["mean"], 5.0 * 4000.0 * 3.5e-3, places=4)
        self.assertTrue(result["w10_d2_conv_rule"]["pass"])
        cycles = segment(synth(rows, conv_ms=0.2, seed=1), rows)
        groups["b"] = wpr.session_groups(cycles)
        self.assertFalse(wpr.summary(groups)["w10_d2_conv_rule"]["pass"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
