#!/usr/bin/env python3
"""Host tests of the week 10 laptop tools (no dongle, no PPK2, no KV260).

1. Plans: the regenerated ewait_load_blocks.csv equals the CSV sent to SV2 on 10/11 (SHA-256 38937e54...);
   week10_common.permutations() equals week9_common.plan_splits() (same splitmix64 stream); the prot
   plan (W10-D1) and ble plan (W10-D4) hold the counts, pairing and order of the decisions;
   generate_week10_plan.py output PASSES load_plans() and a changed byte FAILS it; with gcc on PATH (or
   CC) both generated headers compile and their entries equal the CSVs.
2. Analysis rules (W10-D1..D5, week10_analysis): OLS known answer; the queue state rebuilt from a
   jobs.jsonl written by SV2's real queue_sim.Dispatcher (edge/server/week9/queue_sim.py, fake backend)
   equals queue_sim's own queue length at every foreground enqueue; request matching, block assignment,
   level skip; ewait_summary recovers a known E_wait = a + b t_wait and t_wait = c + d q and picks the
   line / table and q_hat * t_svc / measured slope by the locked rules; conv_rule, dev_on_formula and
   etx_linearity pass and fail where they should.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week10_host.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_week10_plan as gen  # noqa: E402
import week10_analysis as wa  # noqa: E402
import week10_common as w10  # noqa: E402

w9 = w10.w9
TMP = Path(tempfile.mkdtemp(prefix="week10_host_"))
QUEUE_SIM = w10.ROOT / "edge" / "server" / "week9" / "queue_sim.py"


class Plans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = TMP / "plan"
        cls.manifest = gen.generate(cls.out)

    def test_generator_pass(self):
        self.assertEqual(self.manifest["status"], "PASS", self.manifest["checks"])

    def test_load_csv_is_the_one_sent_to_sv2(self):
        self.assertEqual(w10.sha256_hex(w10.load_csv_text().encode()), w10.LOAD_CSV_SHA256)
        self.assertEqual(w10.w8.w7.sha256_file(self.out / w10.LOAD_CSV_NAME), w10.LOAD_CSV_SHA256)
        self.assertEqual(sum(d for d, _ in w10.load_blocks()), 460)

    def test_permutations_equal_week9_stream(self):
        for seed in (w9.PLAN_SEED, w10.BLE_SEED, w10.PROT_SEED):
            flat = [s for perm in w10.permutations(seed, 11) for s in perm]
            self.assertEqual(flat, w9.plan_splits(seed))

    def test_prot_plan(self):
        rows = w10.prot_plan()
        self.assertEqual(len(rows), 1050)
        self.assertTrue(gen.pairs_ok(rows))
        conv = [r for r in rows if r.op == w10.OP_CONV]
        self.assertEqual(len(conv), 50)
        self.assertTrue(all(r.split == 1 for r in conv))
        positions = {r.cycle - 21 * r.round for r in conv}
        self.assertGreater(len(positions), 5, "the HEAD-only cycle must move inside the round")
        broken = list(rows)
        broken[0], broken[1] = broken[1], broken[0]
        self.assertFalse(gen.pairs_ok(broken))

    def test_ble_plan(self):
        rows = w10.ble_plan()
        self.assertEqual([r.split for r in rows], w9.plan_splits(w10.BLE_SEED))
        self.assertEqual(len(w10.ble_plan_bytes(rows)), 5 * 550)

    def test_load_plans_authenticates(self):
        plans = w10.load_plans(self.out)
        self.assertEqual(plans.prot_sha256, self.manifest["prot"]["plan_sha256"])
        bad = TMP / "plan_bad"
        shutil.copytree(self.out, bad)
        text = (bad / w10.LOAD_CSV_NAME).read_text(encoding="utf-8").replace("20,30", "20,31", 1)
        (bad / w10.LOAD_CSV_NAME).write_text(text, encoding="utf-8", newline="\n")
        with self.assertRaises(ValueError):
            w10.load_plans(bad)

    def test_headers_compile(self):
        cc = os.environ.get("CC") or shutil.which("gcc")
        if not cc:
            self.skipTest("no gcc on PATH (set CC)")
        main = TMP / "hdr.c"
        main.write_text(
            '#include <stdio.h>\n#include "week10_prot_plan.h"\n#include "week10_ble_plan.h"\n'
            "int main(void){unsigned i;for(i=0;i<WEEK10_PROT_PLAN_CYCLES;i++)"
            'printf("P %u %u\\n",week10_prot_plan[i][0],week10_prot_plan[i][1]);'
            "for(i=0;i<WEEK10_BLE_PLAN_CYCLES;i++)printf(\"B %u %u %u %u\\n\",week10_ble_plan[i].split,"
            "week10_ble_plan[i].rho,week10_ble_plan[i].k,week10_ble_plan[i].payload_bytes);"
            'printf("%s %s\\n",WEEK10_PROT_PLAN_SHA256,WEEK10_BLE_PLAN_SHA256);return 0;}\n', encoding="utf-8")
        exe = TMP / "hdr.exe"
        subprocess.run([cc, "-std=c11", "-Wall", "-Werror", "-I", str(self.out), str(main), "-o", str(exe)], check=True)
        lines = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.splitlines()
        prot = [tuple(map(int, l.split()[1:])) for l in lines if l.startswith("P ")]
        ble = [tuple(map(int, l.split()[1:])) for l in lines if l.startswith("B ")]
        self.assertEqual(prot, [(r.split, r.op) for r in w10.prot_plan()])
        self.assertEqual(ble, [(r.split, r.rho, r.k, r.payload_bytes) for r in w10.ble_plan()])
        self.assertEqual(lines[-1].split(), [self.manifest["prot"]["plan_sha256"], self.manifest["ble"]["plan_sha256"]])


class Stats(unittest.TestCase):
    def test_ols_known_answer(self):
        x = np.arange(10.0)
        fit = wa.ols(x, 3.0 + 2.0 * x)
        self.assertAlmostEqual(fit["slope"], 2.0)
        self.assertAlmostEqual(fit["intercept"], 3.0)
        self.assertAlmostEqual(fit["r2"], 1.0)
        rng = np.random.default_rng(1)
        y = 5.0 + 0.5 * x + rng.normal(0, 0.1, x.size)
        fit = wa.ols(x, y)
        lo, hi = fit["slope_ci95"]
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertIsNone(wa.ols([1, 1, 1], [1, 2, 3])["slope"])

    def test_block_of(self):
        table = w10.block_table(w10.load_blocks())
        self.assertEqual(wa.block_of(0.0, table)[:2], (0, 0.0))
        idx, lam, off = wa.block_of(41.0, table)
        self.assertEqual((idx, lam), (1, 30.0))
        self.assertAlmostEqual(off, 1.0)
        self.assertEqual(wa.block_of(460.0, table), (None, None, None))


class FineClock:
    """time for queue_sim with a ns-resolution monotonic clock: Windows time.monotonic_ns ticks every
    ~15.6 ms, the KV260 (Linux CLOCK_MONOTONIC) every ns."""
    def __getattr__(self, name):
        return getattr(time, name)

    @staticmethod
    def monotonic_ns():
        return time.perf_counter_ns()


def load_queue_sim():
    spec = importlib.util.spec_from_file_location("sv2_queue_sim", QUEUE_SIM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.time = FineClock()
    return module


class FakeBackend:
    def __init__(self, service_s: float):
        self.service_s = service_s

    def infer(self, values):
        time.sleep(self.service_s)
        return {"tail_ms": self.service_s * 1e3}

    def close(self):
        pass


class QueueLog(unittest.TestCase):
    """SV2's Dispatcher (real code, fake 8 ms backend), 120 background jobs/s for ~1.5 s, 12 foreground
    requests: the rebuilt q equals the queue length queue_sim logs at each foreground enqueue."""

    @classmethod
    def setUpClass(cls):
        qs = load_queue_sim()
        cls.dir = TMP / "queue"
        cls.dir.mkdir()
        dispatch = qs.Dispatcher(FakeBackend(0.008), cls.dir, max_background=8)
        stop = threading.Event()

        def background():
            rng = random.Random(7)
            while not stop.is_set():
                time.sleep(rng.expovariate(120.0))
                dispatch.submit([0], background=True)
        thread = threading.Thread(target=background, daemon=True)
        thread.start()
        cls.t_rx_ms = []
        for _ in range(12):
            time.sleep(0.11)
            cls.t_rx_ms.append(time.perf_counter_ns() / 1e6)
            dispatch.infer([1])
        stop.set()
        thread.join(2)
        dispatch.close()
        cls.jobs = wa.queue_jobs(wa.read_jsonl(cls.dir / "jobs.jsonl"))
        cls.fg = wa.foreground_rows(cls.jobs)

    def test_q_is_logged_and_rebuild_consistent(self):
        self.assertEqual(len(self.fg), 12)
        pairs = [(r["q_rebuilt"], r["q_logged_minus_self"]) for r in self.fg]
        self.assertTrue(all(r["q"] == r["q_logged_minus_self"] for r in self.fg))
        self.assertTrue(all(abs(a - b) <= wa.QUEUE_REBUILD_MAX_DIFF for a, b in pairs), pairs)
        self.assertGreaterEqual(sum(a == b for a, b in pairs), 11, pairs)
        self.assertTrue(any(r["q"] > 0 for r in self.fg), "the load must queue at least once")

    def test_match_requests(self):
        self.assertTrue(wa.match_requests(self.t_rx_ms, self.fg)["pass"])
        self.assertFalse(wa.match_requests(self.t_rx_ms[:-1], self.fg)["pass"])
        shifted = [t + 200.0 for t in self.t_rx_ms]
        self.assertFalse(wa.match_requests(shifted, self.fg)["pass"])

    def test_background_service(self):
        stats = wa.background_service_ms(self.jobs)
        self.assertGreater(stats["n"], 10)
        self.assertGreater(stats["mean"], 7.0)


def synthetic_session(seed: int, b_mw: float, t_svc: float = 46.0, d_scale: float = 1.0) -> list:
    """Rows in ewait_rows form: q from the block level, t_wait = 120 + d q + noise, E = 95 + b t_wait."""
    rng = np.random.default_rng(seed)
    table = w10.block_table(w10.load_blocks())
    rows = []
    for i in range(200):
        t = 36.0 + i * 1.45
        index, lam, off = wa.block_of(t, table)
        q = int(min(8, rng.poisson({0.0: 0.05, 15.0: 1.5, 30.0: 7.0}[lam])))
        t_wait = 120.0 + d_scale * t_svc * q + rng.normal(0, 3.0)
        e = 95.0 + b_mw * t_wait + rng.normal(0, 2.0)
        rows.append({"cycle": i, "rho": "P1" if i % 2 == 0 else "P0", "t_wait_ms": t_wait, "E_wait_uJ": e,
                     "E_wait_net_uJ": e, "q": q, "q_rebuilt": q, "active": q > 0, "q_logged_minus_self": q,
                     "block": index,
                     "lambda": lam, "seconds_into_block": off, "level_use": off >= wa.LEVEL_SKIP_S,
                     "edge_queue_wait_ms": t_svc * q, "edge_service_ms": 75.0,
                     "t_wait_minus_edge_ms": t_wait - t_svc * q - 75.0, "t_rx_ms": t * 1e3})
    return rows


class EwaitRules(unittest.TestCase):
    def test_line_and_q_model_recovered(self):
        rows = {"A": synthetic_session(1, 1.55), "B": synthetic_session(2, 1.55)}
        tsvc = {"A": {"mean": 46.0}, "B": {"mean": 46.0}}
        res = wa.ewait_summary(rows, tsvc, {"A": 1.58, "B": 1.59})
        e, q = res["pooled_E_wait_vs_t_wait"], res["pooled_t_wait_vs_q"]
        self.assertAlmostEqual(e["slope"], 1.55, delta=0.02)
        self.assertAlmostEqual(e["intercept"], 95.0, delta=5.0)
        self.assertAlmostEqual(q["slope"], 46.0, delta=1.0)
        self.assertEqual(res["rule_ewait_model"], "line a + b * t_wait")
        self.assertEqual(res["rule_queue_model"], "q_hat * t_svc")
        self.assertGreater(res["b_over_P_idle_off"], 10.0)
        self.assertGreater(res["long_over_empty_E_wait"], 1.5)
        self.assertTrue(all(b["n"] > 0 for b in res["bin_table"]))

    def test_rules_switch(self):
        rows = {"A": synthetic_session(3, 1.0, d_scale=1.5), "B": synthetic_session(4, 1.0, d_scale=1.5)}
        tsvc = {"A": {"mean": 46.0}, "B": {"mean": 46.0}}
        res = wa.ewait_summary(rows, tsvc, {"A": 1.58, "B": 1.58})
        self.assertTrue(res["rule_ewait_model"].startswith("table"))
        self.assertEqual(res["rule_queue_model"], "measured slope d")

    def test_session_checks(self):
        rows = synthetic_session(5, 1.55)
        fg = [{"cancelled": False, "error": None} for _ in rows]
        checks = wa.ewait_session_checks(rows, fg, {"failure": None})
        self.assertTrue(all(checks.values()), checks)
        quiet = [dict(r, q=0) for r in rows]
        self.assertFalse(wa.ewait_session_checks(quiet, fg, {"failure": None})["load_effective_lambda30_median_q"])
        late = [dict(r, t_wait_minus_edge_ms=-10.0) for r in rows]
        self.assertFalse(wa.ewait_session_checks(late, fg, {"failure": None})["causality_t_wait_ge_edge"])
        self.assertFalse(wa.ewait_session_checks(rows, fg, {"failure": "x"})["queue_no_failure"])
        off2 = [dict(r, q_rebuilt=r["q"] + 2) if i == 0 else r for i, r in enumerate(rows)]
        self.assertFalse(wa.ewait_session_checks(off2, fg, {"failure": None})["rebuilt_q_consistent_with_logged"])
        unlogged = [dict(r, q_logged_minus_self=None) for r in rows]
        self.assertFalse(wa.ewait_session_checks(unlogged, fg, {"failure": None})["queue_length_logged_at_every_request"])


class OtherRules(unittest.TestCase):
    def test_conv_rule(self):
        prot = {s: {"A": 10.0 + s, "B": 11.0 + s} for s in range(10)}
        self.assertTrue(wa.conv_rule(prot, {"A": 60.0, "B": 62.0})["pass"])
        prot[3]["B"] = 61.0          # max session mean at s3 above the smallest conv session mean
        res = wa.conv_rule(prot, {"A": 60.0, "B": 62.0})
        self.assertFalse(res["pass"])
        self.assertFalse(res["per_s"]["3"]["pass"])
        self.assertFalse(wa.conv_rule({0: {"A": 1.0}}, {"A": 60.0})["pass"], "needs all ten splits")

    def test_dev_on_formula(self):
        off = {0: 6.0, 2: 483.3, 4: 1659.6}
        t = {0: 0.55, 2: 37.1, 4: 126.2}
        on = {s: off[s] + 0.7 * t[s] for s in off}
        self.assertTrue(wa.dev_on_formula(on, off, t)["pass"])
        on[4] *= 1.03
        self.assertFalse(wa.dev_on_formula(on, off, t)["pass"])
        on = {0: 99.0, 2: off[2] + 0.7 * t[2]}
        self.assertTrue(wa.dev_on_formula(on, off, t)["pass"], "s0 does not count for the rule")

    def test_etx_linearity(self):
        b = {0: 362, 1: 5792, 2: 2912, 3: 5824, 4: 2944, 5: 4416, 6: 2256, 7: 3008, 8: 1536, 9: 96}
        e = {s: 150.0 + 0.155 * v for s, v in b.items()}
        self.assertFalse(wa.etx_linearity(b, e)["alarm_nonlinear"])
        e = {s: 150.0 + (900.0 if v > 3000 else 0.0) for s, v in b.items()}
        self.assertTrue(wa.etx_linearity(b, e)["alarm_nonlinear"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
