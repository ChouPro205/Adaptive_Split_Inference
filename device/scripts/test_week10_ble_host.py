#!/usr/bin/env python3
"""Host tests of the week 10 radio-on tools (W10-D4; no dongle, no PPK2, no KV260). Needs gcc on PATH (or CC).

1. Host references (week10_ble.HostRefs): the shim's plan digest, computed with the firmware's serialization
   (device/week10/ble_plan_bytes.h + week 6 SHA-256), equals WEEK10_BLE_PLAN_SHA256; q/scale of every
   (sample, s) equal the week 9 refs (checked inside HostRefs); the plain request at s2 equals the week 8
   request builder (G2-verified) for every sample; payload bytes per s equal tensor_sizes.csv.
2. check_week10.py verify on a synthetic VERIFY ALL capture written from the host references PASSES, and FAILS
   with one changed q digest, request digest or s10 label.
3. check_week10.py session + week10_ble.evaluate_requests on a synthetic dry run (CYCLE lines, KV260 log,
   offline predictions) PASS, and FAIL with one wrong offline label or a request out of plan order.
4. week10_ble.segment_ble_cycles on a synthetic 100 kS/s trace: s2 cycles end at WAIT, s10 cycles at HEAD,
   phase energies add up; a D1 pulse, a missing TX, or TX/WAIT in an s10 cycle are errors; match_alls pairs
   cycles with requests.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week10_ble_host.py
"""
from __future__ import annotations

import json
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

w8 = wb.w8
TMP = Path(tempfile.mkdtemp(prefix="week10_ble_host_"))
SAMPLES = Path(os.environ.get("WEEK10_SAMPLES", r"D:\HUST\ASI_week8\samples-20261023-c"))
HAVE_CC = bool(os.environ.get("CC") or shutil.which("gcc"))
HOST = None


def host() -> wb.HostRefs:
    global HOST
    if HOST is None:
        plan = TMP / "plan"
        if not plan.exists():
            gen.generate(plan)
        HOST = wb.HostRefs(SAMPLES, plan, TMP / "shim")
    return HOST


def setUpModule():
    if not HAVE_CC:
        raise unittest.SkipTest("no gcc on PATH (set CC)")
    if not SAMPLES.exists():
        raise unittest.SkipTest(f"W8-D3 set not found at {SAMPLES} (set WEEK10_SAMPLES)")


def bits(values) -> str:
    return wb.bits_hex(np.asarray(values, dtype="<f4"))


def capture(lines) -> list:
    return [(i, text) for i, text in enumerate(lines)]


def banner(h) -> str:
    return (f"READY WEEK10 build=x variant=ble-usb kernel=FAST rounds=50 splits=11 cycles=550 samples=50 "
            f"set_sha256={h.sample_set.set_sha256} plan_sha256={w10.BLE_PLAN_SHA256} "
            f"plan_device_sha256={w10.BLE_PLAN_SHA256} plan_ok=1")


class HostReferences(unittest.TestCase):
    def test_plan_digest_with_firmware_serialization(self):
        h = host()
        self.assertEqual(h.plan_digest, w10.BLE_PLAN_SHA256)
        self.assertEqual(h.plan_header_sha256, w10.BLE_PLAN_SHA256)

    def test_s2_request_equals_week8_builder(self):
        h = host()
        for n in range(wb.SAMPLES):
            self.assertEqual(h.request(n, 2, n + 1), w8.build_request(h.sample_set, n, n + 1, None, None))

    def test_bytes_and_s10(self):
        h = host()
        sizes = wb.w9.tensor_sizes()
        for s in range(11):
            self.assertEqual(h.bytes_payload(s), sizes[s][2])
        self.assertEqual(len(h.s10), wb.SAMPLES)
        for n, (b, label) in h.s10.items():
            self.assertEqual(label, w8.label(w8.logits_from_hex(b)))


def verify_lines(h) -> list:
    lines = [banner(h)]
    for s in range(11):
        for n in range(wb.SAMPLES):
            c, length, qb, sb = h.tensors[(n, s)]
            lines.append(f"VQ n={n} id={h.sample_set.samples[n].sample_id} s={s} C={c} L={length} "
                         f"bytes={c * length + 2 * c} q_sha256={wb.w9.sha256_hex(qb)} scale_sha256={wb.w9.sha256_hex(sb)}")
            if s == 10:
                b, label = h.s10[n]
                lines.append(f"VLAB n={n} s=10 logits={b} label={label}")
            else:
                frame = h.request(n, s, n + 1)
                lines.append(f"VREQ n={n} s={s} rho=P0 rid={n + 1} len={len(frame)} sha256={wb.w9.sha256_hex(frame)}")
    lines.append(f"VERIFY END kernel=FAST samples=50 splits=ALL set_sha256={h.sample_set.set_sha256}")
    return lines


class CheckVerify(unittest.TestCase):
    def test_pass_and_fail(self):
        h = host()
        lines = verify_lines(h)
        checks, details = chk.check_verify(capture(lines), h)
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})
        for tag, broken in (("VQ n=3 ", "q_sha256=0"), ("VREQ n=7 ", "sha256=0"), ("VLAB n=5 ", "label=4")):
            bad = list(lines)
            i = next(k for k, t in enumerate(bad) if t.startswith(tag))
            key = broken.split("=")[0]
            parts = [p if not p.startswith(key + "=") else broken for p in bad[i].split(" ")]
            if tag.startswith("VLAB"):
                label = int(next(p for p in bad[i].split(" ") if p.startswith("label=")).split("=")[1])
                parts = [p if not p.startswith("label=") else f"label={(label + 1) % 5}" for p in bad[i].split(" ")]
            bad[i] = " ".join(parts)
            checks, _ = chk.check_verify(capture(bad), h)
            self.assertFalse(all(checks.values()), tag)


def dry_run(h, first: int, count: int, edge_label_flip: tuple | None = None):
    """CYCLE lines of the dongle, KV260 log records and offline predictions of a dry run."""
    rng = np.random.default_rng(7)
    rows = list(h.plans.ble)[first:first + count]
    lines, log, offline = [banner(h), f"SESSION BEGIN first={first} count={count} gap_ms=0 plan_sha256=x"], [], []
    for n in range(wb.SAMPLES):
        for s in wb.EDGE_SPLITS:
            logits = rng.normal(0, 3, 5).astype("<f4")
            offline.append({"set_index": n, "sample_id": h.sample_set.samples[n].sample_id, "split": s,
                            "logits": [float(x) for x in logits]})
    off = {(r["set_index"], r["split"]): r["logits"] for r in offline}
    rid = 1000
    for row in rows:
        if row.split == 10:
            b, label = h.s10[row.sample]
            lines.append(f"CYCLE i={row.cycle} round={row.round} n={row.sample} id=x s=10 rho=0 k=0 bytes=15 rid=0 len=0 "
                         f"frags=0 mtu=0 ctrl_us=200 head_us=50000 quant_us=1 enc_us=0 tx_us=0 wait_us=0 enomem=0 "
                         f"invalid=0 status=0 res=OK logits={b} label={label}")
            continue
        rid += 1
        c, length, qb, sb = h.tensors[(row.sample, row.split)]
        logits = off[(row.sample, row.split)]
        b = bits(logits)
        label = w8.label(tuple(float(x) for x in np.asarray(logits, "<f4")))
        lines.append(f"CYCLE i={row.cycle} round={row.round} n={row.sample} id=x s={row.split} rho=0 k=0 "
                     f"bytes={c * length + 2 * c} rid={rid} len={wb.frame_length_p0(c, length)} frags=3 mtu=247 "
                     f"ctrl_us=200 head_us=1000 quant_us=1 enc_us=10 tx_us=20000 wait_us=60000 enomem=0 invalid=0 "
                     f"status=0 res=OK logits={b} label={label}")
        log.append(json.dumps({"ev": "request", "request_id": rid, "rho": "P0", "split": row.split, "result": "OK",
                               "q_sha256": wb.w9.sha256_hex(qb), "scale_sha256": wb.w9.sha256_hex(sb),
                               "logits": logits, "label": label, "t_rx_ms": 1000 * row.cycle,
                               "t_tx_done_ms": 1000 * row.cycle + 45, "connection": 0}))
    ok = sum(1 for t in lines if t.startswith("CYCLE"))
    lines.append(f"SESSION END first={first} count={count} ok={ok} failed=0")
    if edge_label_flip is not None:
        for r in offline:
            if (r["set_index"], r["split"]) == edge_label_flip:
                top = int(np.argmax(r["logits"]))
                r["logits"][(top + 1) % 5] = float(np.float32(max(r["logits"]) + 5.0))
    return lines, log, offline


class CheckSession(unittest.TestCase):
    def run_case(self, first, count, flip=None, swap=False):
        h = host()
        lines, log, offline = dry_run(h, first, count, flip)
        if swap:
            log[0], log[1] = log[1], log[0]
        ref_path = TMP / f"offline_{first}_{count}_{flip}_{swap}.jsonl"
        ref_path.write_text("".join(json.dumps(r) + "\n" for r in offline), encoding="utf-8")
        edge_ref = wb.load_edge_reference([ref_path], h)
        records, counters = wb.normalize_kv260_log(log, h)
        dongle = {}
        for t in lines:
            if t.startswith("CYCLE"):
                kv = chk.wc.kv(t)
                dongle[int(kv["i"])] = (int(kv["rid"]), kv["logits"])
        result = wb.evaluate_requests(records, counters, list(h.plans.ble)[first:first + count], edge_ref, dongle)
        session = TMP / f"session_{first}_{count}_{flip}_{swap}"
        (session / "edge").mkdir(parents=True)
        (session / "edge" / "summary.json").write_text(json.dumps({"result": result, "counters": counters}), encoding="utf-8")
        checks, _ = chk.check_session(capture(lines), h, session, first, count)
        return checks

    def test_pass(self):
        checks = self.run_case(0, 55)
        self.assertTrue(all(checks.values()), {k: v for k, v in checks.items() if not v})

    def test_wrong_offline_label_fails(self):
        row = next(r for r in w10.ble_plan()[:55] if r.split != 10)
        checks = self.run_case(0, 55, flip=(row.sample, row.split))
        self.assertFalse(checks["kv260_labels_equal_kv260_offline_every_s"])

    def test_out_of_order_fails(self):
        checks = self.run_case(0, 55, swap=True)
        self.assertFalse(checks["kv260_requests_in_plan_order"])


def synth_trace(plan_rows, extra=None, drop_tx=None):
    """Self-test-free synthetic trace: per cycle CTRL 0.2 ms, HEAD 2 ms at 4 mA; s <= 9: TX 5 ms at 6 mA,
    WAIT 50 ms at 1 mA; 100 ms gaps at 0.4 mA."""
    cur, bits = [np.full(1000, 30.0)], [np.zeros(1000, np.uint8)]

    def seg(ms, ua, bit):
        n = int(ms * 100)
        cur.append(np.full(n, ua))
        bits.append(np.full(n, 0 if bit is None else 1 << bit, np.uint8))

    for k, row in enumerate(plan_rows):
        seg(0.2, 3000.0, wb.CTRL)
        seg(2.0, 4000.0, wb.DEV)
        if row.split != 10 and k != drop_tx:
            seg(5.0, 6000.0, wb.TX)
        if row.split != 10:
            seg(50.0, 1000.0, wb.WAIT)
        if extra == k:
            seg(0.5, 2000.0, wb.PROT)
        seg(100.0, 400.0, None)
    return ep.Trace(np.concatenate(cur), np.concatenate(bits), 5000.0, "synthetic")


class Segmentation(unittest.TestCase):
    rows = w10.ble_plan()[:22]

    def test_valid(self):
        cycles = wb.segment_ble_cycles(synth_trace(self.rows), 0, self.rows)
        self.assertEqual(len(cycles), 22)
        for c, row in zip(cycles, self.rows):
            self.assertEqual(c["errors"], [], (row, c["errors"]))
            self.assertEqual(c["split"], row.split)
            expected = 2.2 if row.split == 10 else 57.2
            self.assertAlmostEqual(c["t_cycle_ms"], expected, places=6)
            self.assertLess(c["diff_pct"], 1e-6)
            self.assertAlmostEqual(c["E_dev_uJ"], 5.0 * 4000.0 * 2e-3, places=6)
            self.assertEqual(c["dev_high_fraction"], 1.0)

    def test_errors(self):
        k10 = next(k for k, r in enumerate(self.rows) if r.split == 10)
        k2 = next(k for k, r in enumerate(self.rows) if r.split != 10)
        cycles = wb.segment_ble_cycles(synth_trace(self.rows, extra=k2), 0, self.rows)
        self.assertIn("after_end_prot", cycles[k2]["errors"])
        cycles = wb.segment_ble_cycles(synth_trace(self.rows, drop_tx=k2), 0, self.rows)
        self.assertIn("missing_tx", cycles[k2]["errors"])
        shifted = list(self.rows)
        shifted[k10] = next(r for r in w10.ble_plan() if r.split != 10)   # trace has no TX/WAIT there
        cycles = wb.segment_ble_cycles(synth_trace(self.rows), 0, shifted)
        self.assertIn("missing_tx", cycles[k10]["errors"])
        wrong = list(self.rows)
        wrong[k2] = next(r for r in w10.ble_plan() if r.split == 10)       # trace has TX/WAIT there
        cycles = wb.segment_ble_cycles(synth_trace(self.rows), 0, wrong)
        self.assertTrue(any(e.startswith("unexpected_") or e.startswith("after_end_") for e in cycles[k2]["errors"]))

    def test_match_alls(self):
        cycles = wb.segment_ble_cycles(synth_trace(self.rows), 0, self.rows)
        records = []
        for c in cycles:
            if c["device_only"]:
                continue
            end = c["end_sample"] * wp.DT_MS
            records.append({"split": c["split"], "t_rx_ms": end - c["t_wait_ms"] + 3.0, "t_tx_done_ms": end - 2.0})
        self.assertTrue(wp.match_alls(cycles, records)["pass"])
        records[0], records[1] = records[1], records[0]
        self.assertFalse(wp.match_alls(cycles, records)["pass"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
