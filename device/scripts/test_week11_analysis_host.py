#!/usr/bin/env python3
"""Host tests of the week 11 analysis rules (W11-D7..D14, week11_analysis + week11_ppk2.analyze) on synthetic
PPK2 traces built with known phase currents (no dongle, no PPK2, no KV260).

1. Segmentation: a trace with the boot self-test, a base block (ECHO ack + full, S0C x1/x100), a refused
   Coded block (5 x 1 ms CTRL signature), an L2 block (latency on / off during WAIT) and a reconnect block
   gives one row per plan entry, the known E_tx / E_wait / E_link / E_dev, refused = True only where the
   signature is, the interval check passes at k (L + 1) and fails when the events run at k although L = 2.
2. Rules: P_conn of an IDLE window = the analytic mean, marg = gross - P_conn x t, E_tx fit recovers the known
   beta with R^2 = 1 on the 7 teacher sizes, S0C pairing recovers the per-encode energy, E_rx = the known
   receive energy, latency on - off = the known WAIT difference, a block with a wrong interval is invalid.
3. Error paths: a missing WAIT, a bad refusal signature (3 pulses), an extra CTRL after the plan, an ECHO that
   hits the 5 s timeout.
4. KV260 log: echo records in plan order with consecutive request_id pass, a swapped length fails; granted
   parameters before each block's first IDLE pass, a wrong latency fails.
5. week11_ppk2.analyze on the synthetic trace: every analysis check PASS; ops.csv read back gives the same
   block validity. estimate_session of both real plans is between 10 and 45 minutes.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week11_analysis_host.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week11_analysis as an  # noqa: E402
import week11_common as w11  # noqa: E402

FS = ep.SAMPLE_RATE_HZ
V = 5.0
BASE_UA, EVENT_UA, EVENT_MS = 30.0, 5000.0, 0.3
CTRL_UA, TX_UA, WAIT_UA, LINK_UA, DEV_UA = 3000.0, 4000.0, 600.0, 300.0, 4500.0
TX_MS_PER_B = 0.0116
WAIT_MS = 30.0
S0C_MS = 0.15
IDLE_MS = 3000
# W11-D10 burst inside WAIT: the last data event (after the D2 fall), empty events on the k grid, the ack/frame RX
DATA_AT_MS, DATA_EV_MS, DATA_UA = 3.0, 2.5, 6000.0
EMPTY_EV_MS, EMPTY_UA = 0.9, 3500.0
RESP_MS, RESP_UA = 1.5, 4800.0
TMP = Path(tempfile.mkdtemp(prefix="week11_analysis_"))


def ms(n):
    return int(round(n * FS / 1e3))


class Builder:
    """Appends segments; marker-free stretches get radio events at the current spacing."""

    def __init__(self):
        self.cur, self.bits = [], []
        self.spacing_ms = 15.0
        self.phase = 0.0

    def seg(self, dur_ms, ua, bit=None):
        n = ms(dur_ms)
        c = np.full(n, ua, float)
        b = np.zeros(n, np.uint8) if bit is None else np.full(n, 1 << bit, np.uint8)
        self.cur.append(c)
        self.bits.append(b)

    def wait(self, dur_ms, k_ms, empties_until_ms):
        """WAIT (D3) with the data event at DATA_AT_MS, empty events every k ms up to empties_until_ms (the same
        for ack and full ops of a state, so E_rx stays the frame time), the response at the end.
        Returns the energy above WAIT_UA (uJ)."""
        n = ms(dur_ms)
        c = np.full(n, WAIT_UA, float)
        pulses = [(DATA_AT_MS, DATA_EV_MS, DATA_UA)]
        t = DATA_AT_MS + k_ms
        while t + EMPTY_EV_MS < min(dur_ms, empties_until_ms) - RESP_MS - 1.0:
            pulses.append((t, EMPTY_EV_MS, EMPTY_UA))
            t += k_ms
        pulses.append((dur_ms - RESP_MS, RESP_MS, RESP_UA))
        extra = 0.0
        for s0, length, ua in pulses:
            a, b = ms(s0), min(n, ms(s0 + length))
            c[a:b] = ua
            extra += V * (ua - WAIT_UA) * (b - a) / FS * 1e3 / 1e3
        self.cur.append(c)
        self.bits.append(np.full(n, 1 << an.WAIT, np.uint8))
        return extra

    def idle(self, dur_ms, events=True):
        n = ms(dur_ms)
        c = np.full(n, BASE_UA, float)
        if events:
            period, width = ms(self.spacing_ms), ms(EVENT_MS)
            for s in range(int(self.phase), n, period):
                c[s:s + width] = EVENT_UA
            self.phase = (int(self.phase) - n) % period
        self.cur.append(c)
        self.bits.append(np.zeros(n, np.uint8))

    def trace(self):
        return ep.Trace(np.concatenate(self.cur), np.concatenate(self.bits), 5000.0, "synthetic", None,
                        {"counter": {"available": True, "discontinuities": 0},
                         "capture": {"dut_on_rate_deviation_pct": 0.0, "reader_error": None}})


def E(ua, t_ms):
    return V * ua * t_ms / 1e3   # uJ = V x uA x ms / 1000


def plan_and_trace(*, wrong_l2_interval=False, drop_wait_at=None, bad_signature=False, extra_ctrl=False,
                   timeout_at=None):
    """Plan: base (block 0), coded-k30 refused (block 1), L2 (block 2), reconnect (block 14)."""
    rows = []

    def add(block, st, op, a=0, b=0):
        rows.append(w11.Entry(len(rows), block, st, op, a, b))

    add(0, 0, w11.OP_STATE)
    add(0, 0, w11.OP_IDLE, IDLE_MS)
    for size in an.TEACHER_SIZES + (436,):
        for _ in range(an.MIN_VALID_REPEATS):
            add(0, 0, w11.OP_ECHO, size, w11.ECHO_ACK)
    for size in (64, 1024):
        for _ in range(2):
            add(0, 0, w11.OP_ECHO, size, 0)
    for n in range(4):
        for r in w11.S0C_REPEATS:
            add(0, 0, w11.OP_S0C, n, r)
    add(0, 0, w11.OP_IDLE, IDLE_MS)
    add(1, 11, w11.OP_STATE)
    add(1, 11, w11.OP_IDLE, IDLE_MS)
    add(1, 11, w11.OP_ECHO, 256, w11.ECHO_ACK)
    add(1, 11, w11.OP_IDLE, IDLE_MS)
    add(2, 5, w11.OP_STATE)
    add(2, 5, w11.OP_IDLE, IDLE_MS)
    for flags in (w11.ECHO_ACK, w11.ECHO_ACK | w11.ECHO_LATENCY_OFF):
        for _ in range(an.MIN_VALID_REPEATS):
            add(2, 5, w11.OP_ECHO, 512, flags)
    add(2, 5, w11.OP_IDLE, IDLE_MS)
    add(14, 0, w11.OP_STATE)
    add(14, 0, w11.OP_RECONNECT)
    add(14, 0, w11.OP_RECONNECT)
    add(14, 0, w11.OP_IDLE, IDLE_MS)

    bld = Builder()
    bld.idle(500, events=False)
    for ch in (0, 1, 2, 3, 4):                       # self-test D0..D4
        bld.seg(200, 2000.0, ch)
    bld.idle(30000, events=False)                    # boot idle, radio off
    bld.idle(2000)
    expect = []
    for r in rows:
        st = w11.STATES[r.state]
        info = {"index": r.index}
        if r.op == w11.OP_STATE:
            refused = r.state == 11
            bld.spacing_ms = 15.0 if refused else st.interval_ms * (st.latency + 1)
            if r.state == 5 and wrong_l2_interval:
                bld.spacing_ms = 15.0
            bld.seg(0.2, CTRL_UA, an.CTRL)
            bld.seg(400.0, LINK_UA, an.LINK)
            if refused:
                for _ in range(3 if bad_signature else an.REFUSED_PULSES):
                    bld.idle(1.0, events=False)
                    bld.seg(1.0, CTRL_UA, an.CTRL)
            bld.idle(2000)
            info.update(t_link=400.0, refused=refused)
        elif r.op == w11.OP_IDLE:
            bld.seg(0.2, CTRL_UA, an.CTRL)
            bld.idle(r.a)
        elif r.op == w11.OP_ECHO:
            t_tx = TX_MS_PER_B * r.a
            t_wait = WAIT_MS * (st.latency + 1 if not r.b & w11.ECHO_LATENCY_OFF else 1)
            if not r.b & w11.ECHO_ACK:
                t_wait += TX_MS_PER_B * r.a
            if timeout_at == r.index:
                t_wait = an.ECHO_TIMEOUT_MS
            bld.seg(0.5, CTRL_UA, an.CTRL)
            bld.seg(t_tx, TX_UA, an.TX)
            extra = 0.0
            if drop_wait_at != r.index:
                extra = bld.wait(t_wait, st.interval_ms,
                                 WAIT_MS * (st.latency + 1 if not r.b & w11.ECHO_LATENCY_OFF else 1))
            bld.idle(250)
            info.update(t_tx=t_tx, t_wait=t_wait, wait_extra=extra,
                        burst=E(TX_UA, ms(t_tx) / FS * 1e3) + E(WAIT_UA, DATA_AT_MS) + E(DATA_UA, DATA_EV_MS))
        elif r.op == w11.OP_S0C:
            bld.seg(0.2, CTRL_UA, an.CTRL)
            bld.seg(S0C_MS * r.b + 0.05, DEV_UA, an.DEV)   # + 0.05 ms call overhead
            bld.idle(250)
            info.update(t_dev=S0C_MS * r.b + 0.05)
        elif r.op == w11.OP_RECONNECT:
            bld.seg(0.2, CTRL_UA, an.CTRL)
            bld.seg(6000.0, LINK_UA, an.LINK)
            bld.idle(250)
            info.update(t_link=6000.0)
        expect.append(info)
    if extra_ctrl:
        bld.seg(0.2, CTRL_UA, an.CTRL)
    bld.idle(30000, events=False)                    # post-session, off-air
    return rows, bld.trace(), expect


class Segmentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.trace, cls.expect = plan_and_trace()
        after = ep.selftest_check(cls.trace, dict(ep.DEFAULT_MAP), 200.0)["end_sample"]
        cls.seg = an.segment_ops(cls.trace, after + 1, cls.rows)
        cls.blocks = an.block_table(cls.seg)
        cls.valid = an.valid_rows(cls.seg, cls.blocks)

    def test_one_row_per_entry_known_energy(self):
        self.assertEqual(len(self.seg), len(self.rows))
        self.assertEqual(self.seg[-1]["extra_ctrl_after_plan"], 0)
        for r, e in zip(self.seg, self.expect):
            self.assertEqual(r["errors"], [], r)
            if "t_tx" in e:
                self.assertAlmostEqual(r["t_tx_ms"], e["t_tx"], delta=0.011)
                self.assertAlmostEqual(r["E_tx_uJ"], E(TX_UA, r["t_tx_ms"]), places=6)
                self.assertAlmostEqual(r["t_wait_ms"], e["t_wait"], delta=0.011)
                self.assertAlmostEqual(r["E_wait_uJ"], E(WAIT_UA, r["t_wait_ms"]) + e["wait_extra"], places=6)
                self.assertNotIn("burst_error", r)
                self.assertAlmostEqual(r["E_burst_uJ"], e["burst"], places=6)
                self.assertGreaterEqual(r["n_ev_tx"], 1)
                self.assertLess(r["diff_pct"], 1e-9)
            if "t_dev" in e:
                self.assertAlmostEqual(r["E_dev_uJ"], E(DEV_UA, r["t_dev_ms"]), places=6)
            if "t_link" in e:
                self.assertAlmostEqual(r["t_link_ms"], e["t_link"], delta=0.011)
                self.assertAlmostEqual(r["E_link_uJ"], E(LINK_UA, r["t_link_ms"]), places=6)
            self.assertEqual(r["refused"], e.get("refused", False))

    def test_blocks(self):
        self.assertTrue(self.blocks[0]["valid"])
        self.assertTrue(self.blocks[1]["refused"])
        self.assertFalse(self.blocks[1]["valid"])
        self.assertTrue(self.blocks[2]["valid"])
        self.assertTrue(self.blocks[14]["valid"])
        self.assertFalse(any(r["block"] == 1 for r in self.valid))
        for b in (0, 2):
            for iv in self.blocks[b]["idle_interval"]:
                self.assertTrue(iv["pass"], iv)
        self.assertAlmostEqual(self.blocks[2]["idle_interval"][0]["median_spacing_ms"], 45.0, delta=0.02)

    def test_pconn_and_marg(self):
        p = self.blocks[0]["P_conn_gross_mW"]
        analytic = V * (BASE_UA + EVENT_UA * EVENT_MS / 15.0) / 1e3
        self.assertAlmostEqual(p, analytic, delta=0.01 * analytic)
        r = next(r for r in self.valid if r["op"] == "ECHO")
        self.assertAlmostEqual(r["E_tx_marg_uJ"], r["E_tx_uJ"] - p * r["t_tx_ms"], places=9)

    def test_tables(self):
        result = an.summary({"A": self.valid, "B": self.valid}, {"A": self.blocks, "B": self.blocks})
        fit = result["E_tx_fits"]["0"]
        self.assertTrue(fit["teacher_r2_pass"])
        self.assertAlmostEqual(fit["teacher_fit"]["slope"], E(TX_UA, TX_MS_PER_B), delta=0.002)
        self.assertAlmostEqual(fit["teacher_fit"]["r2"], 1.0, places=5)
        self.assertEqual(fit["teacher_quantity"], "E_burst_uJ (E_tx,full)")
        self.assertEqual(fit["burst_errors"], 0)
        p = self.blocks[0]["P_conn_gross_mW"]
        self.assertAlmostEqual(fit["breakeven_beta_teacher_fit"]["slope"], E(TX_UA, TX_MS_PER_B) - p * TX_MS_PER_B,
                               delta=0.002)
        self.assertTrue(fit["marker_teacher_r2_pass"])
        self.assertAlmostEqual(fit["marker_teacher_fit"]["slope"], E(TX_UA, TX_MS_PER_B), delta=0.002)
        # burst intercept = marker intercept + the WAIT energy up to the end of the data event
        self.assertAlmostEqual(fit["teacher_fit"]["intercept"] - fit["marker_teacher_fit"]["intercept"],
                               E(WAIT_UA, DATA_AT_MS) + E(DATA_UA, DATA_EV_MS), delta=0.05)
        enc = result["s0c"]["E_encode_uJ"]["mean"]
        self.assertAlmostEqual(enc, E(DEV_UA, S0C_MS), delta=0.002)
        self.assertEqual(result["s0c"]["samples_paired"], {"A": 4, "B": 4})
        rx = result["E_rx_base"]["fit"]
        self.assertAlmostEqual(rx["slope"], E(WAIT_UA, TX_MS_PER_B), delta=1e-3)
        lat = result["latency"]["L2"]["t_wait_ms"]["enabled_minus_disabled"]
        self.assertAlmostEqual(lat["diff"], 2 * WAIT_MS, delta=0.02)
        self.assertIn("coded-k30", result["states_missing"])
        self.assertEqual(result["P_conn"]["coded-k30"]["block_status"]["A"], ["refused"])
        cells = result["echo_cells"]
        self.assertTrue(cells["0/1024/1"]["usable"])
        self.assertFalse(cells["0/1024/0"]["usable"])       # 2 < MIN_VALID_REPEATS
        rec = result["reconnect"]["E_link_marg_uJ"]["mean"]
        self.assertAlmostEqual(rec, E(LINK_UA, 6000.0) - self.blocks[14]["P_conn_gross_mW"] * 6000.0, delta=0.05)

    def test_kv260_echo_and_link_events(self):
        offset = 1234.5
        echo = [r for r in self.seg if r["op"] == "ECHO"]
        rid = 0xFFFFFFFD
        records = []
        for r in echo:
            tx_end = r["active_end_sample"] * an.DT_MS - r["t_wait_ms"]
            records.append({"request_id": rid, "length": r["a"], "mode": int(bool(r["b"] & 1)),
                            "t_rx_ms": tx_end + offset + 3.0, "t_tx_done_ms": tx_end + offset + 8.0})
            rid = rid + 1 if rid + 1 not in (0, 0xFFFFFFFF) else 1
        res = an.check_echo_records(records, [dict(r) for r in self.seg])
        self.assertTrue(res["pass"], res)
        swapped = [dict(x) for x in records]
        swapped[0]["length"], swapped[1]["length"] = swapped[1]["length"], swapped[0]["length"] + 1
        self.assertFalse(an.check_echo_records(swapped, [dict(r) for r in self.seg])["pass"])
        events = []
        for b, blk in self.blocks.items():
            if blk["refused"]:
                continue
            st = w11.STATES[blk["state"]]
            first_idle = next(r for r in self.seg if r["block"] == b and r["op"] == "IDLE")
            t = first_idle["ctrl_end_sample"] * an.DT_MS + offset - 500.0
            events += [{"ev": "conn_update", "t_ms": t, "interval_1250us": st.interval_1250us, "latency": st.latency,
                        "timeout_10ms": st.timeout_10ms},
                       {"ev": "phy_update", "t_ms": t, "tx_phy": st.phy, "rx_phy": st.phy},
                       {"ev": "data_len", "t_ms": t, "max_rx_octets": st.tx_octets}]
        self.assertTrue(an.check_link_events(events, self.seg, self.blocks, offset)["pass"])
        bad = [dict(e, latency=0) if e["ev"] == "conn_update" and e["latency"] == 2 else e for e in events]
        self.assertFalse(an.check_link_events(bad, self.seg, self.blocks, offset)["pass"])


class ErrorPaths(unittest.TestCase):
    def _seg(self, **kw):
        rows, trace, _ = plan_and_trace(**kw)
        after = ep.selftest_check(trace, dict(ep.DEFAULT_MAP), 200.0)["end_sample"]
        seg = an.segment_ops(trace, after + 1, rows)
        return seg, an.block_table(seg)

    def test_wrong_interval_invalidates_block(self):
        seg, blocks = self._seg(wrong_l2_interval=True)
        self.assertFalse(blocks[2]["valid"])
        self.assertTrue(blocks[0]["valid"])

    def test_missing_wait(self):
        seg, _ = self._seg(drop_wait_at=5)
        self.assertIn("missing_wait", seg[5]["errors"])
        self.assertEqual(seg[6]["errors"], [])

    def test_bad_signature(self):
        seg, blocks = self._seg(bad_signature=True)
        st = next(r for r in seg if r["block"] == 1 and r["op"] == "STATE")
        self.assertFalse(st["refused"])
        self.assertIn("bad_refusal_signature", st["errors"])

    def test_extra_ctrl(self):
        seg, _ = self._seg(extra_ctrl=True)
        self.assertEqual(seg[-1]["extra_ctrl_after_plan"], 1)

    def test_timeout(self):
        seg, _ = self._seg(timeout_at=4)
        self.assertIn("wait_timeout", seg[4]["errors"])


class PpkAnalyze(unittest.TestCase):
    def test_analyze_and_roundtrip(self):
        import week11_ppk2 as wp
        rows, trace, _ = plan_and_trace()
        out = TMP / "session"
        out.mkdir()
        saved = w11.STATES
        summary = wp.analyze(trace, out, rows, ignore_counter=False)
        self.assertEqual(summary["status"], "PASS", summary["checks"])
        self.assertEqual(summary["refused_states"], ["coded-k30"])
        back = wp.rows_from_csv(out / "analysis" / "ops.csv")
        blocks = an.block_table(back)
        self.assertEqual({k: v["valid"] for k, v in blocks.items()},
                         {int(k): v["valid"] for k, v in summary["blocks"].items()})
        self.assertIs(saved, w11.STATES)

    def test_import_and_summary(self):
        """session dir (analysis only) -> import (echo + link-event logs) -> evaluate -> summary of two
        sessions; the raw-trace checks are stubbed (they need a real capture)."""
        import json
        import week11_ppk2 as wp
        import week7_ppk2 as w7p
        rows, trace, _ = plan_and_trace()
        saved = wp.trace_checks
        wp.trace_checks = lambda out, record, meta: ({"trace_stub": True}, {"I_idle_uA": 25.4})
        try:
            dirs = []
            for k in (0, 1):
                out = TMP / f"imp{k}"
                out.mkdir()
                (out / "ppk2").mkdir()
                w7p.write_new_json(out / "ppk2" / "capture.json", {"status": "PASS"})
                w7p.write_new_json(out / "session.json", {"schema": wp.SCHEMA, "plan_session": k})
                wp.analyze(trace, out, rows, ignore_counter=False)
                seg = wp.rows_from_csv(out / "analysis" / "ops.csv")
                blocks = an.block_table(seg)
                rid, recs, evs = 7, [], []
                for r in seg:
                    if r["op"] == "ECHO":
                        t = r["active_end_sample"] * an.DT_MS - r["t_wait_ms"] + 50.0
                        recs.append({"ev": "echo", "request_id": rid, "length": r["a"], "mode": "ack" if r["b"] & 1 else "full",
                                     "t_rx_ms": t, "t_tx_done_ms": t + 4.0, "connection": 1 + sum(
                                         1 for x in seg if x["op"] == "RECONNECT" and x["index"] < r["index"])})
                        rid += 1
                for c in range(1, 2 + sum(1 for x in seg if x["op"] == "RECONNECT")):
                    recs.append({"ev": "connected", "connection": c})
                for b, blk in blocks.items():
                    if blk["refused"]:
                        continue
                    st = w11.STATES[blk["state"]]
                    idle = next(r for r in seg if r["block"] == b and r["op"] == "IDLE")
                    t = idle["ctrl_end_sample"] * an.DT_MS + 50.0 - 100.0
                    evs += [{"ev": "conn_update", "t_ms": t, "interval_1250us": st.interval_1250us,
                             "latency": st.latency, "timeout_10ms": st.timeout_10ms},
                            {"ev": "phy_update", "t_ms": t, "tx_phy": st.phy, "rx_phy": st.phy},
                            {"ev": "data_len", "t_ms": t, "max_rx_octets": st.tx_octets}]
                log, links = TMP / f"echo{k}.jsonl", TMP / f"links{k}.jsonl"
                log.write_text("".join(json.dumps(x) + "\n" for x in recs), encoding="utf-8")
                links.write_text("".join(json.dumps(x) + "\n" for x in evs), encoding="utf-8")
                code = wp.main(["import", "--out", str(out), "--kv260-log", str(log), "--link-events", str(links)])
                check = w7p.load_json(out / "check_link.json")
                self.assertEqual(code, 0, check["checks"])
                self.assertTrue((out / "ops_valid.csv").exists())
                dirs.append(out)
            summ = TMP / "summary"
            self.assertEqual(wp.main(["summary", "--session", str(dirs[0]), "--session", str(dirs[1]),
                                      "--out", str(summ)]), 0)
            res = w7p.load_json(summ / "summary.json")
            self.assertTrue(res["E_tx_fits"]["0"]["teacher_r2_pass"])
            self.assertEqual(len(res["sessions"]), 2)
            for name in ("p_conn.csv", "echo_cells.csv", "etx_fits.csv"):
                self.assertTrue((summ / name).exists())
        finally:
            wp.trace_checks = saved

    def test_estimate_real_plans(self):
        for k in range(w11.SESSIONS):
            est = an.estimate_session(w11.session_plan(k))
            for model in ("fast", "slow"):
                self.assertGreater(est[model]["total_s"], 600.0)
                self.assertLess(est[model]["total_s"], 45 * 60.0)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
