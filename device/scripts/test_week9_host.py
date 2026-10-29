#!/usr/bin/env python3
"""Host tests of the week 9 firmware modules and laptop tools (no dongle).

1. Plan (W9-D4): week9_common.plan_splits() (splitmix64 known-answer, every round a permutation,
   50 cycles per split) equals plan.csv, the generated week9_plan.h compiled into
   device/week9/host_test/dev_shim.c, and WEEK9_PLAN_SHA256.
2. q/scale (W9-D6): dev_shim.c + week7/head_fast.c + week5/quantization.c (gcc on PATH or CC, -O2
   -ffp-contract=off -fno-fast-math, the steps of dev_cycle.c dev_head()) on the 50 samples at every
   s equal refs.csv; refs.csv shapes/bytes equal tensor_sizes.csv and s=2 equals the W8-D3 samples.csv.
3. check_week9.py verify/session PASS on host-made captures and FAIL on a changed q hash, a missing VQ
   line, a wrong device plan digest, a DWT mean outside the rule, a reordered cycle, a failed cycle and
   wrong payload bytes. With --week8-build, check_week9_build.py FAILS on a week 8 radio image.
4. week9_ppk2.analyze_dev PASSES a synthetic dev-image trace (550 cycles in plan order, HEAD widths =
   DWT) with E_dev per split as integrated, and FAILS on a missing cycle, two swapped cycles, a D2
   pulse, a 6 mA sample between cycles and an idle current 57 % above week 2. With --week8-b5, the
   chunked raw loader equals energy_phases.load_raw_capture bit for bit on a 3 M-sample prefix
   (chunk edges inside range switches), and the week 8 B5 session FAILS the week 9 checks.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week9_host.py --samples <W8-D3 dir>
     --plan <plan dir> --refs <refs dir> [--week8-build <week 8 build report dir>]
     [--week8-b5 <week 8 B5 session dir>]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_week9  # noqa: E402
import generate_week9_refs as gen_refs  # noqa: E402
import week9_common as w9  # noqa: E402

w8 = w9.w8
TMP = Path(tempfile.mkdtemp(prefix="week9_host_"))
SAMPLES: Path | None = None
PLAN: Path | None = None
REFS: Path | None = None
WEEK8_BUILD: Path | None = None
WEEK8_B5: Path | None = None


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = gen_refs.build_shim(TMP, SAMPLES, PLAN)
        cls.plan = w9.load_plan(PLAN)

    def test_splitmix64_known_answer(self):
        # Reference outputs of splitmix64 seeded with 0 (Vigna's splitmix64.c).
        state, out = 0, []
        for _ in range(3):
            state, x = w9._splitmix64(state)
            out.append(x)
        self.assertEqual(out, [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F])

    def test_plan_properties(self):
        splits = w9.plan_splits()
        self.assertEqual(len(splits), w9.CYCLES)
        for k in range(w9.ROUNDS):
            self.assertEqual(sorted(splits[11 * k:11 * k + 11]), list(range(11)), k)
        self.assertEqual([splits.count(s) for s in range(11)], [50] * 11)
        self.assertNotEqual(splits[:11], list(range(11)))
        self.assertNotEqual(w9.plan_splits(seed=w9.PLAN_SEED + 1), splits)
        self.assertEqual(w9.plan_sha256(splits), w9.PLAN_SHA256)

    def test_plan_csv_and_c_header_equal_generator(self):
        splits = w9.plan_splits()
        self.assertEqual(list(self.plan.rows), w9.plan_rows(splits))
        self.assertEqual(self.lib.shim_plan_cycles(), w9.CYCLES)
        self.assertEqual(self.lib.shim_plan_rounds(), w9.ROUNDS)
        self.assertEqual(self.lib.shim_plan_seed(), w9.PLAN_SEED)
        self.assertEqual(self.lib.shim_plan_sha256().decode(), w9.PLAN_SHA256)
        c_splits = list(ctypes.string_at(self.lib.shim_plan_splits(), w9.CYCLES))
        self.assertEqual(c_splits, splits)

    def test_load_plan_rejects_changed_csv(self):
        bad = TMP / "plan_bad"
        bad.mkdir()
        for name in ("manifest.json", "week9_plan.h"):
            (bad / name).write_bytes((PLAN / name).read_bytes())
        text = (PLAN / "plan.csv").read_text(encoding="utf-8").replace("\n0,0,0,3\n", "\n0,0,0,4\n", 1)
        (bad / "plan.csv").write_text(text, encoding="utf-8", newline="\n")
        with self.assertRaises(ValueError):
            w9.load_plan(bad)


class References(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = w8.load_set(SAMPLES)
        cls.refs = w9.load_refs(REFS, cls.set)
        (TMP / "refs").mkdir()
        cls.lib = gen_refs.build_shim(TMP / "refs", SAMPLES)

    def test_shim_550_equal_refs(self):
        for n in range(w9.ROUNDS):
            for s in range(w9.SPLITS):
                c, length, q, scale = gen_refs.head_quant(self.lib, n, s)
                r = self.refs[(n, s)]
                self.assertEqual((c, length, len(q) + len(scale)), (r.channels, r.length, r.bytes_payload))
                self.assertEqual((w9.sha256_hex(q), w9.sha256_hex(scale)), (r.q_sha256, r.scale_sha256), (n, s))

    def test_payload_bytes_per_split(self):
        want = {0: 362, 1: 5792, 2: 2912, 3: 5824, 4: 2944, 5: 4416, 6: 2256, 7: 3008, 8: 1536, 9: 96, 10: 15}
        self.assertEqual({s: self.refs[(0, s)].bytes_payload for s in range(11)}, want)

    def test_s2_equal_week8(self):
        for n in range(w9.ROUNDS):
            sample = self.set.samples[n]
            self.assertEqual((self.refs[(n, 2)].q_sha256, self.refs[(n, 2)].scale_sha256),
                             (sample.q_sha256, sample.scale_sha256))


def verify_capture(refs: dict, set_sha: str, plan_digest: str = w9.PLAN_SHA256, td_scale: float = 1.0) -> list:
    """The lines a dev-usb image prints for STATUS, VERIFY ALL and TDEV ALL, from the host references
    (TD head = week 7 BENCH FAST x td_scale)."""
    lines = [f"READY WEEK9 build=host variant=dev-usb kernel=FAST rounds=50 splits=11 cycles=550 samples=50 "
             f"set_sha256={set_sha} plan_sha256={w9.PLAN_SHA256} plan_device_sha256={plan_digest} "
             f"plan_ok={int(plan_digest == w9.PLAN_SHA256)}"]
    for s in range(w9.SPLITS):
        for n in range(w9.ROUNDS):
            r = refs[(n, s)]
            lines.append(f"VQ n={n} id={r.sample_id} s={s} C={r.channels} L={r.length} bytes={r.bytes_payload} "
                         f"q_sha256={r.q_sha256} scale_sha256={r.scale_sha256}")
    lines.append(f"VERIFY END kernel=FAST samples=50 splits=ALL set_sha256={set_sha}")
    bench = w9.bench_fast_ms()
    for s in range(w9.SPLITS):
        head = round(bench[s] * td_scale * w9.CPU_HZ / 1000.0)
        for n in range(w9.ROUNDS):
            lines.append(f"TD s={s} n={n} head_cyc={head} quant_cyc=900 total_cyc={head + 920}")
        lines.append(f"TDSUM s={s} runs=50 warmup=20 irq=locked cpu_hz=64000000 head_min={head} head_max={head} "
                     f"head_mean_x100={head * 100} quant_mean_x100=90000 total_min={head + 920} "
                     f"total_max={head + 920} total_mean_x100={(head + 920) * 100}")
    lines.append("TDEV END kernel=FAST splits=ALL")
    return [(i, t) for i, t in enumerate(lines)]


def session_capture(refs: dict, first: int = 0, count: int = w9.CYCLES, rows=None) -> list:
    rows = rows if rows is not None else w9.plan_rows(w9.plan_splits())[first:first + count]
    lines = [f"SESSION BEGIN first={first} count={count} gap_ms=0 plan_sha256={w9.PLAN_SHA256}"]
    for i, k, n, s in rows:
        r = refs[(n, s)]
        lines.append(f"CYCLE i={i} round={k} n={n} id={r.sample_id} s={s} bytes={r.bytes_payload} ctrl_cyc=12800 "
                     f"head_cyc={1000 + 64000 * s} quant_cyc=900 head_us={(1000 + 64000 * s) // 64} res=OK")
    lines.append(f"SESSION END first={first} count={count} ok={count} failed=0")
    return [(i, t) for i, t in enumerate(lines)]


class Checkers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = w8.load_set(SAMPLES)
        cls.refs = w9.load_refs(REFS, cls.set)

    def failed_verify(self, capture) -> list:
        return [k for k, ok in check_week9.check_verify(capture, self.set, self.refs)["checks"].items() if not ok]

    def failed_session(self, capture, first=0, count=w9.CYCLES) -> list:
        return [k for k, ok in check_week9.check_session(capture, self.refs, first, count)["checks"].items() if not ok]

    def test_verify_passes_host_capture(self):
        result = check_week9.check_verify(verify_capture(self.refs, self.set.set_sha256), self.set, self.refs)
        self.assertTrue(all(result["checks"].values()), result["checks"])
        self.assertEqual(len(result["t_dev_table"]), 11)

    def test_verify_rejects_changes(self):
        good = verify_capture(self.refs, self.set.set_sha256)
        q = self.refs[(5, 7)].q_sha256
        self.assertIn("q_scale_id_shape_bytes_equal_host_reference",
                      self.failed_verify([(i, t.replace(q, "0" * 64)) for i, t in good]))
        missing = [(i, t) for i, t in good if not t.startswith("VQ n=7 id=") or " s=3 " not in t]
        self.assertIn("vq_550_split_major_order", self.failed_verify(missing))
        self.assertIn("device_plan_digest_equal",
                      self.failed_verify(verify_capture(self.refs, self.set.set_sha256, "a" * 64)))
        self.assertEqual(self.failed_verify(verify_capture(self.refs, self.set.set_sha256, td_scale=1.03)),
                         ["tdev_head_within_rule_of_week7_bench_fast"])
        self.assertEqual(self.failed_verify(verify_capture(self.refs, self.set.set_sha256, td_scale=1.015)), [])

    def test_session_passes_plan(self):
        self.assertEqual(self.failed_session(session_capture(self.refs)), [])
        self.assertEqual(self.failed_session(session_capture(self.refs, 33, 22), 33, 22), [])

    def test_session_rejects_changes(self):
        rows = w9.plan_rows(w9.plan_splits())
        swapped = list(rows)
        swapped[3], swapped[4] = (3, 0, 0, swapped[4][3]), (4, 0, 0, swapped[3][3])
        self.assertIn("cycles_equal_plan_order", self.failed_session(session_capture(self.refs, rows=swapped)))
        good = session_capture(self.refs)
        failed = [(i, t.replace("res=OK", "res=HEAD") if i == 10 else t) for i, t in good]
        self.assertIn("all_cycles_ok", self.failed_session(failed))
        line = good[1][1]
        wrong = [(i, t.replace(" bytes=", " bytes=1", 1) if i == 1 else t) for i, t in good]
        self.assertNotEqual(wrong[1][1], line)
        self.assertIn("bytes_equal_tensor_sizes", self.failed_session(wrong))
        self.assertIn("cycles_equal_plan_order", self.failed_session(good[:-2] + good[-1:]))


FS = 100_000
SCALE = 0.05     # synthetic HEAD widths = DWT x SCALE (keeps the trace ~2 M samples)


def synthetic_trace(rows, dwt, idle_ua=25.0, tweak=None):
    """A dev-image trace: self-test D0..D4 200 ms, 2 s idle, the given (cycle, round, n, s) rows as
    CTRL 200 us + HEAD (DWT x SCALE) + 6 ms gap, 5 s idle. tweak(pieces) may edit the pieces."""
    import energy_phases as ep
    rng = np.random.default_rng(7)
    pieces = [[1000, 25.0, 0]] + [[20000, 300.0, 1 << ch] for ch in range(5)] + [[200000, idle_ua, 0]]
    for _, _, n, s in rows:
        pieces += [[20, 3200.0, 1 << 4], [round(dwt[(n, s)] * SCALE * 100), 3300.0, 1], [600, idle_ua, 0]]
    pieces.append([500000, idle_ua, 0])
    if tweak:
        tweak(pieces)
    current = np.concatenate([np.full(n, i) for n, i, _ in pieces]).astype(np.float64)
    bits = np.concatenate([np.full(n, b, dtype=np.uint8) for n, _, b in pieces])
    current += rng.normal(0.0, 1.0, current.size) * np.where(current > 1000, 40.0, 0.5)
    info = {"dut_power_on_sample": 0, "counter": {"available": True, "discontinuities": 0},
            "capture": {"dut_on_rate_deviation_pct": 0.0, "reader_error": None}}
    return ep.Trace(current, bits, 5000.0, "synthetic", None, info)


class Ppk2Analysis(unittest.TestCase):
    """week9_ppk2.analyze_dev on synthetic dev-image traces (HEAD widths from the B2 TDEV shape)."""

    @classmethod
    def setUpClass(cls):
        import week9_ppk2
        cls.mod = week9_ppk2
        cls.set = w8.load_set(SAMPLES)
        refs = w9.load_refs(REFS, cls.set)
        cls.bytes = {s: refs[(0, s)].bytes_payload for s in range(11)}
        head = [0.5487, 11.69, 37.10, 71.16, 126.17, 176.70, 246.24, 302.23, 373.46, 377.55, 377.40]
        cls.dwt = {(n, s): head[s] * (1 + 0.001 * (n % 5)) for n in range(50) for s in range(11)}
        cls.dwt_scaled = {k: v * SCALE for k, v in cls.dwt.items()}
        cls.rows = w9.plan_rows(w9.plan_splits())

    def run_analysis(self, rows=None, **kw):
        trace = synthetic_trace(rows if rows is not None else self.rows, self.dwt, **kw)
        return self.mod.analyze_dev(trace, self.dwt_scaled, self.bytes, idle_seconds=1.0)

    def failed(self, result) -> set:
        checks = {**result["summary"]["checks"], **result["energy_dev"]["checks"]}
        return {k for k, ok in checks.items() if not ok}

    def test_passes_and_energy_per_split(self):
        result = self.run_analysis()
        self.assertEqual(self.failed(result), set())
        energy = result["energy_dev"]["splits"]
        for row in energy:
            s = row["split"]
            want = 5.0 * 3300e-6 * float(np.mean([self.dwt_scaled[(n, s)] for n in range(50)])) * 1e3
            self.assertEqual(row["n"], 50)
            self.assertEqual(row["bytes_payload"], self.bytes[s])
            self.assertAlmostEqual(row["E_dev_uJ"]["mean"], want, delta=max(0.1, 0.01 * want))
            self.assertLess(row["E_dev_net_uJ"]["mean"], row["E_dev_uJ"]["mean"])
        self.assertAlmostEqual(result["summary"]["I_idle_uA"], 25.0, delta=0.1)
        cycles = result["cycles"]
        self.assertEqual([(c["round"], c["sample"], c["split"]) for c in cycles], [r[1:] for r in self.rows])

    def test_rejects_missing_cycle(self):
        failed = self.failed(self.run_analysis(self.rows[:100] + self.rows[101:]))
        self.assertTrue({"TC4_cycle_count_550", "TC4_head_width_matches_plan", "TC5_n_50_per_split"} <= failed)

    def test_rejects_swapped_cycles(self):
        rows = list(self.rows)
        rows[0], rows[1] = rows[1], rows[0]          # s=3 and s=0 of round 0 run in the other order
        self.assertIn("TC4_head_width_matches_plan", self.failed(self.run_analysis(rows)))

    def test_rejects_d2_pulse_spike_and_idle(self):
        def d2(pieces):
            pieces.insert(7 + 3 * 40 + 2, [50, 25.0, 1 << 2])      # a D2 pulse after cycle 40's HEAD
        failed = self.failed(self.run_analysis(tweak=d2))
        self.assertIn("TC4_D1_D3_low_after_selftest", failed)
        self.assertIn("TC4_all_cycles_valid", failed)

        self.assertIn("TC3_idle_within_10pct_week2", self.failed(self.run_analysis(idle_ua=40.0)))

    def test_radio_off_rule(self):
        """Revised TC4: one short burst (the 512 s RTC OVERFLOW wake-up) passes; a 1 ms burst, or more
        short bursts than floor(T / 512 s) + 1 (here 1: the trace is ~17 s), fail."""
        def burst(cycles, width):
            def tweak(pieces):
                for k in sorted(cycles, reverse=True):
                    at = 7 + 3 * k + 2
                    idle = pieces[at][1]
                    pieces[at:at + 1] = [[250, idle, 0], [width, 6000.0, 0], [350 - width, idle, 0]]
            return tweak
        result = self.run_analysis(tweak=burst([200], 7))
        self.assertEqual(self.failed(result), set())
        events = result["summary"]["gaps"]["events_above_3mA"]
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["duration_ms"], 0.07)
        self.assertIn("TC4_radio_off_between_cycles", self.failed(self.run_analysis(tweak=burst([200], 100))))
        self.assertIn("TC4_radio_off_between_cycles", self.failed(self.run_analysis(tweak=burst([200, 300], 7))))


class Ppk2RealCapture(unittest.TestCase):
    """--week8-b5: the chunked loader equals energy_phases.load_raw_capture bit for bit on a prefix of
    the week 8 B5 raw capture, and analyze_dev FAILS on that session (it has D1..D3 and 200 cycles)."""

    @classmethod
    def setUpClass(cls):
        if WEEK8_B5 is None:
            raise unittest.SkipTest("--week8-b5 not given")
        import week9_ppk2
        cls.mod = week9_ppk2

    def test_chunked_loader_equals_energy_phases(self):
        import energy_phases as ep
        prefix = TMP / "b5_prefix"
        prefix.mkdir()
        meta = json.loads((WEEK8_B5 / "ppk2" / "capture.json").read_text(encoding="utf-8"))
        data = (WEEK8_B5 / "ppk2" / meta["raw_file"]).read_bytes()[:4 * 3_000_001]   # + 1 word: a chunk edge
        (prefix / meta["raw_file"]).write_bytes(data)
        meta["raw_sha256"] = w9.sha256_hex(data)
        (prefix / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
        whole = ep.load_raw_capture(prefix)
        chunked = self.mod.load_raw_chunked(prefix, chunk_samples=250_000)
        self.assertGreater(sum(whole.info["range_counts"][1:]), 10_000)   # range switches cross chunk edges
        self.assertTrue(np.array_equal(whole.current_ua, chunked.current_ua))
        self.assertTrue(np.array_equal(whole.bits, chunked.bits))
        self.assertEqual(whole.info, chunked.info)

    def test_week8_session_fails_week9_checks(self):
        trace = self.mod.load_raw_chunked(WEEK8_B5 / "ppk2")
        dwt = {(n, s): 37.1 for n in range(50) for s in range(11)}
        result = self.mod.analyze_dev(trace, dwt, {s: 1 for s in range(11)})
        checks = result["summary"]["checks"]
        self.assertTrue(checks["selftest_D0_D4"])
        for name in ("TC4_cycle_count_550", "TC4_D1_D3_low_after_selftest", "TC4_all_cycles_valid",
                     "TC4_head_width_matches_plan", "TC4_radio_off_between_cycles"):
            self.assertFalse(checks[name], name)
        self.assertEqual(result["summary"]["cycles_found"], 200)
        self.assertEqual(result["energy_dev"]["status"], "FAIL")


class Kv260Pipeline(unittest.TestCase):
    """--week8-b5: part B tooling (session-kv260 analysis + import-kv260) on the week 8 B5 session: the
    chunked analysis gives the published phase means, the laptop edge's log in the KV260 form imports
    and PASSES every check with a 2M Read-PHY record, and FAILS phy_2m_read_back with a 1M one."""

    @classmethod
    def setUpClass(cls):
        if WEEK8_B5 is None:
            raise unittest.SkipTest("--week8-b5 not given")
        import shutil
        import week9_ppk2
        cls.mod = week9_ppk2
        cls.published = json.loads((WEEK8_B5 / "analysis" / "summary.json").read_text(encoding="utf-8"))
        cls.base = TMP / "kv260_base"
        (cls.base / "ppk2").mkdir(parents=True)
        for name in ("raw.bin", "capture.json"):
            shutil.copyfile(WEEK8_B5 / "ppk2" / name, cls.base / "ppk2" / name)
        cls.mod.analyze_energy_image(cls.mod.load_raw_chunked(cls.base / "ppk2"), cls.base, 100, False)
        cls.log = TMP / "kv260_requests.jsonl"
        with open(cls.log, "w", encoding="utf-8") as handle:
            for line in (WEEK8_B5 / "edge" / "peer.jsonl").read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if event.get("ev") == "request":
                    handle.write(json.dumps({**event, "connection": 0}) + "\n")

    def session(self, name: str, phy: str) -> tuple:
        import shutil
        out = TMP / name
        shutil.copytree(self.base, out)
        (out / "session.json").write_text(json.dumps({
            "schema": "week9-ppk2-kv260/1", "samples": str(SAMPLES), "prior_reserved_through": 60643328,
            "image": {"build_id": "week8 B5 (test)"}, "ignore_counter": False}), encoding="utf-8")
        phy_log = TMP / f"{name}_phy.jsonl"
        phy_log.write_text(json.dumps({"event": "read_phy", "tx_phy": phy, "rx_phy": phy}) + "\n", encoding="utf-8")
        code = self.mod.cmd_import_kv260(argparse.Namespace(out=out, kv260_log=self.log, edge_reference=None,
                                                            phy_log=phy_log))
        return code, json.loads((out / "check_kv260.json").read_text(encoding="utf-8"))

    def test_analysis_equals_published(self):
        mine = json.loads((self.base / "analysis" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(mine["checks"], {**mine["checks"], **{k: True for k in mine["checks"]}})
        for rho in ("P1", "P0"):
            for key in ("E_dev_uJ", "E_prot_uJ", "E_tx_uJ", "E_wait_uJ", "E_cycle_uJ", "t_tx_ms"):
                self.assertAlmostEqual(mine["groups"][rho]["stats"][key]["mean"],
                                       self.published["groups"][rho]["stats"][key]["mean"], places=9)

    def test_import_passes_with_2m(self):
        code, report = self.session("kv260_2m", "2M")
        self.assertEqual(code, 0, {k: v for k, v in report["checks"].items() if not v})
        energy = json.loads((TMP / "kv260_2m" / "energy_kv260_s2.json").read_text(encoding="utf-8"))
        delta = energy["paired_delta_p1_minus_p0"]
        self.assertEqual(delta["E_prot_uJ"]["n"], 100)
        self.assertAlmostEqual(delta["E_prot_uJ"]["mean"], energy["per_rho"]["P1"]["E_prot_uJ"]["mean"], places=6)

    def test_import_fails_with_1m(self):
        code, report = self.session("kv260_1m", "1M")
        self.assertEqual(code, 1)
        self.assertEqual([k for k, v in report["checks"].items() if not v], ["phy_2m_read_back"])


class BuildChecker(unittest.TestCase):
    def test_week8_radio_image_fails(self):
        if WEEK8_BUILD is None:
            raise unittest.SkipTest("--week8-build not given")
        out = TMP / "week8_as_week9.json"
        code = subprocess.run([sys.executable, "-B", str(HERE / "check_week9_build.py"), "--build",
                               str(WEEK8_BUILD / "build"), "--variant", "dev", "--build-id", "x",
                               "--set-sha256", w8.SET_SHA256, "--plan-sha256", w9.PLAN_SHA256,
                               "--output", str(out)], capture_output=True).returncode
        self.assertEqual(code, 1)
        checks = json.loads(out.read_text(encoding="utf-8"))["checks"]
        for name in ("no_bt", "no_nvs", "no_radio_nonce_i2_code_linked", "variant_selected",
                     "plan_sha256_in_image", "week9_modules_compiled"):
            self.assertFalse(checks[name], name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--plan", type=Path, required=True, help="generate_week9_plan.py directory")
    parser.add_argument("--refs", type=Path, required=True, help="generate_week9_refs.py directory")
    parser.add_argument("--week8-build", type=Path, help="a build_week8.ps1 report directory (negative test)")
    parser.add_argument("--week8-b5", type=Path, help="a week8_ppk2.py session directory (loader + negative test)")
    args, rest = parser.parse_known_args()
    SAMPLES, PLAN, REFS = args.samples.resolve(), args.plan.resolve(), args.refs.resolve()
    WEEK8_BUILD = args.week8_build.resolve() if args.week8_build else None
    WEEK8_B5 = args.week8_b5.resolve() if args.week8_b5 else None
    result = unittest.main(argv=[sys.argv[0], *rest], verbosity=2, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
