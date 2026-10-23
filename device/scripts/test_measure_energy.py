#!/usr/bin/env python3
"""Tests of energy_phases.py and measure_energy.py without hardware (week 7 TC2/TC3).

1. Week 2 reproduction on results/week2/raw (skipped if the raw CSVs are not on this machine):
   idle mean 25.416651984 uA, std 3.706868927 uA, 6 000 001 samples, trapezoid charge
   1.524999098 mC, D0-D3 LOW; Active capture D0->D3 rotation, 500 ms per marker.
2. Raw-word conversion equals ppk2-api 0.9.2 PPK2_API.get_samples() bit for bit (range switches,
   spike filter, logic bits), sample-counter continuity check.
3. Synthetic cycles with a known answer: adjacent phases, missing PROT (rho = P0), D1 pulses
   outside cycles (NVS writes), truncated start/end, overlapping phases, TX retry, gap energy.
4. Student-t quantiles; analyze CLI end to end on a synthetic raw capture; measure_energy.py
   capture against a fake PPK2 (file layout, DUT-on offset, refusal to overwrite).
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_measure_energy.py
"""
from __future__ import annotations

import json
import random
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import measure_energy as me  # noqa: E402

WEEK2 = ROOT / "results" / "week2" / "raw"
IDLE_CSV = WEEK2 / "2026-09-22_idle_vbus5v_60s.csv"
ACTIVE_CSV = WEEK2 / "2026-09-22_active_marker_vbus5v_60s.csv"
MAP = dict(ep.DEFAULT_MAP)
TMP = Path(tempfile.mkdtemp(prefix="week7_energy_"))


def word(adc: int, rng: int, counter: int, bits: int) -> int:
    return (adc & 0x3FFF) | (rng & 7) << 14 | (counter & 0x3F) << 18 | (bits & 0xFF) << 24


class Builder:
    """Synthetic trace: append segments of (samples, current_uA, bitmask)."""

    def __init__(self, v_mv=5000.0):
        self.i, self.b, self.v = [], [], v_mv

    def add(self, n, current, channels=()):
        mask = 0
        for name in channels:
            mask |= 1 << MAP[name]
        self.i.append(np.full(n, float(current)))
        self.b.append(np.full(n, mask, dtype=np.uint8))
        return self

    def cycle(self, prot=True, gap=0, gap_current=0.0, tx_runs=1):
        self.add(20, 3000, ["ctrl"]).add(2000, 7000, ["dev"])
        if prot:
            self.add(150, 6500, ["prot"])
        for r in range(tx_runs):
            if r:
                self.add(50, 30)
            self.add(800, 5000, ["tx"])
        if gap:
            self.add(gap, gap_current)
        return self.add(3000, 900, ["wait"])

    def trace(self):
        return ep.Trace(np.concatenate(self.i), np.concatenate(self.b), self.v, "synthetic")


def expected_cycle_uj(prot=True, gap=0, gap_current=0.0):
    v, dt = 5.0, ep.DT_S
    parts = {"ctrl": 20 * 3000, "dev": 2000 * 7000, "prot": (150 * 6500 if prot else 0),
             "tx": 800 * 5000, "wait": 3000 * 900}
    phases = {k: v * x * dt for k, x in parts.items()}
    return phases, v * (sum(parts.values()) + gap * gap_current) * dt


class Week2Reproduction(unittest.TestCase):
    @unittest.skipUnless(IDLE_CSV.exists(), "week 2 idle CSV not on this machine")
    def test_idle_numbers(self):
        trace = ep.load_power_profiler_csv(IDLE_CSV)
        stats = ep.window_stats(trace, 0, trace.n)
        self.assertEqual(stats["sample_count"], 6_000_001)
        self.assertAlmostEqual(stats["mean_uA"], 25.416651984, places=8)
        self.assertAlmostEqual(stats["sample_std_uA"], 3.706868927, places=8)
        self.assertAlmostEqual(stats["charge_trapz_mC"], 1.524999098, places=8)
        self.assertAlmostEqual(stats["charge_rect_mC"], 1.525, places=5)
        self.assertEqual(round(stats["mean_uA"], 3), 25.417)
        self.assertFalse(any(stats["high_samples"][f"D{c}"] for c in range(4)))

    @unittest.skipUnless(ACTIVE_CSV.exists(), "week 2 active CSV not on this machine")
    def test_active_rotation(self):
        trace = ep.load_power_profiler_csv(ACTIVE_CSV)
        check = ep.rotation_check(trace, (0, 1, 2, 3), 500.0, 5.0)
        self.assertTrue(check["pass"], check)
        self.assertGreater(check["pulses"], 100)


class RawConversion(unittest.TestCase):
    def make_api(self, metadata: str):
        import ppk2_api.ppk2_api as api
        with mock.patch("serial.Serial"):
            ppk2 = api.PPK2_API("COM_TEST")
        self.assertTrue(ppk2._parse_metadata(metadata))
        ppk2.current_vdd = 5000
        return ppk2

    def test_equals_ppk2_api(self):
        metadata = ("Calibrated: 0\nR0: 1003.3\nR1: 101.4\nR2: 10.02\nR3: 0.97\nR4: 0.051\n"
                    "GS0: 0.00012\nGS1: 0.0012\nGS2: 0.011\nGS3: 0.1\nGS4: 2.1\n"
                    "GI0: 1.002\nGI1: 1.001\nGI2: 0.999\nGI3: 1.003\nGI4: 0.998\n"
                    "O0: 112.5\nO1: 72.1\nO2: 64.3\nO3: 61.8\nO4: 60.2\n"
                    "S0: 0.0000002\nS1: 0.000001\nS2: 0.00001\nS3: 0.0001\nS4: 0.001\n"
                    "I0: -0.00000004\nI1: -0.0000003\nI2: 0.000003\nI3: 0.00003\nI4: 0.0005\n"
                    "UG0: 1.01\nUG1: 0.99\nUG2: 1.0\nUG3: 1.02\nUG4: 0.98\nHW: 9999\nIA: 56\nEND\n")
        ppk2 = self.make_api(metadata)
        rng = random.Random(7)
        words, r = [], 1
        for k in range(20000):
            if rng.random() < 0.02:
                r = rng.choice([0, 1, 2, 3, 4, 4, 5])   # range 5 is clamped to 4 by both
            words.append(word(rng.randrange(0, 1 << 14), r, k, rng.randrange(256)))
        buf = struct.pack(f"<{len(words)}I", *words)
        # Feed in odd-sized pieces to exercise the API's remainder handling.
        ref_i, ref_bits, pos = [], [], 0
        while pos < len(buf):
            step = rng.randrange(1, 4000)
            samples, bits = ppk2.get_samples(buf[pos:pos + step])
            ref_i += samples
            ref_bits += bits
            pos += step
        modifiers = ep.default_modifiers()
        for key in modifiers:
            modifiers[key].update(ppk2.modifiers[key])
        current, bits, ranges, counter = ep.convert_words(np.array(words, dtype=np.uint32),
                                                          modifiers, 5000.0)
        self.assertEqual(len(ref_i), current.size)
        self.assertTrue(np.array_equal(np.array(ref_i), current), "current not bit-exact")
        self.assertEqual(ref_bits, bits.tolist())
        self.assertEqual(ep.counter_check(counter)["discontinuities"], 0)

    def test_counter_check(self):
        counter = (np.arange(1000) % 64).astype(np.uint8)
        self.assertEqual(ep.counter_check(counter),
                         {"available": True, "discontinuities": 0, "lost_samples_min": 0,
                          "first_discontinuity_sample": None, "step_histogram_top": {1: 999}})
        dropped = np.delete(counter, [100, 101, 102, 500])
        check = ep.counter_check(dropped)
        self.assertEqual(check["discontinuities"], 2)
        self.assertEqual(check["lost_samples_min"], 4)
        self.assertEqual(check["first_discontinuity_sample"], 100)
        self.assertFalse(ep.counter_check(np.zeros(100, dtype=np.uint8))["available"])


class Statistics(unittest.TestCase):
    def test_student_t(self):
        for df, value in ((1, 12.706204736), (4, 2.776445105), (10, 2.228138852),
                          (49, 2.009575237), (99, 1.984216952)):
            self.assertAlmostEqual(ep.student_t_quantile(0.975, df), value, places=6)

    def test_describe(self):
        d = ep.describe([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(d["mean"], 2.5)
        self.assertAlmostEqual(d["std"], 1.2909944487)
        self.assertAlmostEqual(d["ci95_half"], 3.182446305 * 1.2909944487 / 2, places=6)


class Cycles(unittest.TestCase):
    def check_cycle(self, row, prot=True, gap=0, gap_current=0.0):
        phases, total = expected_cycle_uj(prot, gap, gap_current)
        for name, value in phases.items():
            self.assertAlmostEqual(row[f"E_{name}_uJ"], value, places=6, msg=name)
        self.assertAlmostEqual(row["E_cycle_uJ"], total, places=6)
        self.assertAlmostEqual(row["t_dev_ms"], 20.0)

    def test_adjacent_phases(self):
        b = Builder().add(500, 25)
        for _ in range(3):
            b.cycle().add(1000, 30)
        cycles, anomalies = ep.segment_cycles(b.trace(), MAP)
        self.assertEqual(len(cycles), 3)
        for row in cycles:
            self.assertEqual(row["errors"], [])
            self.assertEqual(row["rho"], "P1")
            self.assertAlmostEqual(row["diff_pct"], 0.0, places=9)
            self.check_cycle(row)
        self.assertFalse(any(anomalies["out_of_cycle_pulses"].values()))

    def test_missing_prot_is_p0(self):
        b = Builder().add(500, 25).cycle(prot=False).add(1000, 30).cycle(prot=True).add(100, 30)
        cycles, _ = ep.segment_cycles(b.trace(), MAP)
        self.assertEqual([c["rho"] for c in cycles], ["P0", "P1"])
        self.assertEqual(cycles[0]["errors"], [])
        self.assertEqual(cycles[0]["E_prot_uJ"], 0.0)
        self.check_cycle(cycles[0], prot=False)

    def test_d1_outside_cycles(self):
        b = Builder().add(300, 25).add(400, 4000, ["prot"]).add(300, 25)   # boot NVS write
        b.cycle().add(200, 30).add(400, 4000, ["prot"]).add(200, 30).cycle().add(50, 30)
        cycles, anomalies = ep.segment_cycles(b.trace(), MAP)
        self.assertEqual(len(cycles), 2)
        self.assertEqual(anomalies["out_of_cycle_pulses"]["prot"], 1)   # the one between cycles
        for row in cycles:
            self.assertEqual(row["errors"], [])
            self.check_cycle(row)

    def test_truncated_start_and_end(self):
        b = Builder().add(700, 900, ["wait"]).add(300, 25).cycle().add(100, 30)
        b.add(20, 3000, ["ctrl"]).add(500, 7000, ["dev"])          # capture stops in HEAD
        cycles, anomalies = ep.segment_cycles(b.trace(), MAP)
        self.assertEqual(anomalies["marker_high_at_capture_start"], ["wait"])
        self.assertEqual(len(cycles), 2)
        self.assertEqual(cycles[0]["errors"], [])
        self.assertIn("truncated_end", cycles[1]["errors"])
        self.assertIn("missing_tx", cycles[1]["errors"])

    def test_overlap(self):
        b = Builder().add(100, 25).add(20, 3000, ["ctrl"]).add(1000, 7000, ["dev"])
        b.add(10, 7000, ["dev", "prot"]).add(140, 6500, ["prot"]).add(800, 5000, ["tx"])
        b.add(3000, 900, ["wait"]).add(100, 30)
        cycles, _ = ep.segment_cycles(b.trace(), MAP)
        self.assertIn("phase_overlap", cycles[0]["errors"])
        self.assertEqual(cycles[0]["overlap_samples"], 10)
        self.assertAlmostEqual(cycles[0]["E_overlap_uJ"], 5.0 * 10 * 7000 * ep.DT_S)

    def test_retry(self):
        b = Builder().add(100, 25).cycle(tx_runs=2).add(100, 30)
        cycles, _ = ep.segment_cycles(b.trace(), MAP)
        self.assertIn("retry_tx", cycles[0]["errors"])
        # Retry after a WAIT timeout: TX, WAIT, TX, WAIT before the next CTRL.
        b = Builder().add(100, 25).cycle().add(800, 5000, ["tx"]).add(3000, 900, ["wait"])
        cycles, anomalies = ep.segment_cycles(b.add(100, 30).trace(), MAP)
        self.assertIn("retry_tx", cycles[0]["errors"])
        self.assertEqual(anomalies["out_of_cycle_pulses"]["tx"], 1)

    def test_gap_energy(self):
        b = Builder().add(100, 25).cycle(gap=300, gap_current=1000.0).add(100, 30)
        cycles, _ = ep.segment_cycles(b.trace(), MAP)
        row = cycles[0]
        self.assertEqual(row["errors"], [])
        self.check_cycle(row, gap=300, gap_current=1000.0)
        self.assertAlmostEqual(row["E_gap_uJ"], 5.0 * 300 * 1000.0 * ep.DT_S)
        self.assertAlmostEqual(row["diff_pct"], 100 * row["E_gap_uJ"] / row["E_cycle_uJ"])
        self.assertAlmostEqual(row["t_gap_ms"], 3.0)

    def test_order_error(self):
        b = Builder().add(100, 25).add(20, 3000, ["ctrl"]).add(800, 5000, ["tx"])
        b.add(2000, 7000, ["dev"]).add(3000, 900, ["wait"]).add(100, 30)
        cycles, _ = ep.segment_cycles(b.trace(), MAP)
        self.assertIn("phase_order", cycles[0]["errors"])


def synthetic_session(n_p1=3, n_p0=2) -> tuple[list[int], int]:
    """Raw words of a week 7 session: NVS D1 pulse, self-test, idle, cycles (range 2)."""
    words, k = [], 0

    def seg(n, adc, names=()):
        nonlocal k
        mask = 0
        for name in names:
            mask |= 1 << MAP[name]
        for _ in range(n):
            words.append(word(adc, 2, k, mask))
            k += 1

    seg(2000, 40)
    seg(300, 500, ["prot"])                       # boot reservation write
    seg(1000, 40)
    for name in ep.SELFTEST_ORDER:
        seg(20000, 300, [name])
    seg(3_000_000 // 10, 25)                       # 3 s idle (test uses a short window)
    seg(5000, 60)
    for i in range(n_p1 + n_p0):
        seg(20, 600, ["ctrl"])
        seg(2000, 1500, ["dev"])
        if i < n_p1:
            seg(150, 1400, ["prot"])
        seg(800, 1200, ["tx"])
        seg(3, 200)                                # thread hand-over between TX and WAIT
        seg(3000, 250, ["wait"])
        seg(4000, 60)
    return words, k


class AnalyzeCli(unittest.TestCase):
    def test_end_to_end(self):
        words, _ = synthetic_session()
        cap = TMP / "cap"
        cap.mkdir()
        raw = struct.pack(f"<{len(words)}I", *words)
        (cap / "raw.bin").write_bytes(raw)
        meta = {"raw_file": "raw.bin", "raw_sha256": ep.sha256_file(cap / "raw.bin"),
                "v_supply_mV": 5000, "modifiers": ep.default_modifiers(), "dut_power_on_byte": 0}
        (cap / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
        out = TMP / "analysis"
        code = ep.main(["analyze", "--raw", str(cap), "--expect-cycles", "5", "--expect-p1", "3",
                        "--expect-p0", "2", "--idle-seconds", "2.5", "--out", str(out)])
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0, json.dumps(summary["checks"]))
        self.assertTrue(summary["selftest"]["pass"])
        self.assertTrue(summary["idle"]["all_markers_low"])
        self.assertEqual(summary["anomalies"]["out_of_cycle_pulses"]["prot"], 0)
        self.assertLess(summary["diff_pct"]["max"], 3.0)
        self.assertTrue((out / "cycles.csv").exists() and (out / "cycle_waveform.png").exists())
        lines = (out / "cycles.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 6)
        with self.assertRaises(SystemExit):     # never overwrite an analysis
            ep.main(["analyze", "--raw", str(cap), "--expect-cycles", "5", "--out", str(out)])
        tampered = TMP / "cap_bad"
        shutil.copytree(cap, tampered)
        (tampered / "raw.bin").write_bytes(raw[:-4])
        self.assertEqual(ep.main(["analyze", "--raw", str(tampered), "--expect-cycles", "5",
                                  "--out", str(TMP / "bad_out")]), 2)

    def test_wrong_cycle_count_fails(self):
        words, _ = synthetic_session(2, 0)
        cap = TMP / "cap2"
        cap.mkdir()
        (cap / "raw.bin").write_bytes(struct.pack(f"<{len(words)}I", *words))
        meta = {"raw_file": "raw.bin", "raw_sha256": ep.sha256_file(cap / "raw.bin"),
                "v_supply_mV": 5000, "modifiers": ep.default_modifiers()}
        (cap / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(ep.main(["analyze", "--raw", str(cap), "--expect-cycles", "50",
                                  "--idle-seconds", "2.5", "--no-plot",
                                  "--out", str(TMP / "a2")]), 1)


class FakeSerial:
    """Produces PPK2 words at 100 kS/s while 'measuring' (time-based, ~real time)."""

    def __init__(self):
        self.written = []
        self.measuring = False
        self.dut_on = False
        self.counter = 0
        self.last = time.perf_counter()
        self.pending = b""
        self.lock = threading.Lock()
        self.meta_reply = b""

    def write(self, data):
        self.written.append(bytes(data))
        cmd = data[0]
        with self.lock:
            if cmd == 0x19:
                self.meta_reply = b"Calibrated: 0\nR0: 1000.0\nHW: 1\nIA: 2\nEND\n"
            elif cmd == 0x06:
                self.measuring, self.last = True, time.perf_counter()
            elif cmd == 0x07:
                self.measuring = False
            elif cmd == 0x0C:
                self.dut_on = data[1] == 1

    def _produce(self):
        now = time.perf_counter()
        if self.measuring:
            n = int((now - self.last) * 100_000)
            if n:
                adc = 200 if self.dut_on else 5
                self.pending += b"".join(struct.pack("<I", word(adc, 2, self.counter + i, 0))
                                         for i in range(n))
                self.counter += n
                self.last += n / 100_000
        else:
            self.last = now

    @property
    def in_waiting(self):
        with self.lock:
            if self.meta_reply:
                return len(self.meta_reply)
            self._produce()
            return len(self.pending)

    def read(self, n):
        with self.lock:
            if self.meta_reply:
                data, self.meta_reply = self.meta_reply[:n], self.meta_reply[n:]
                return data
            data, self.pending = self.pending[:n], self.pending[n:]
            return data

    def reset_input_buffer(self):
        with self.lock:
            self.pending = b""

    def close(self):
        pass


class Capture(unittest.TestCase):
    def test_fake_ppk2(self):
        import ppk2_api.ppk2_api as api
        fake = FakeSerial()

        def opener(_port):
            with mock.patch("serial.Serial", return_value=fake):
                return api.PPK2_API("COM_FAKE"), api

        out = TMP / "capture"
        meta = me.capture("COM_FAKE", 5000, 1.0, out, "fake", 26.0, "unit test", pre_power_s=0.2,
                          opener=opener)
        self.assertEqual(meta["v_supply_mV"], 5000)
        self.assertEqual(meta["trailing_bytes"], 0)
        self.assertIsNone(meta["reader_error"])
        self.assertGreater(meta["dut_power_on_byte"], 0)
        self.assertEqual(meta["modifiers"]["R"]["0"], 1000.0)
        commands = [w[0] for w in fake.written]
        self.assertEqual(commands[0], 0x19)                       # metadata first (TC2)
        self.assertLess(commands.index(0x06), commands.index(0x0C, commands.index(0x06)))
        self.assertIn(bytes([0x0D, 3 + (5000 - 800 + 32) // 256, (5000 - 800 + 32) % 256]),
                      fake.written)                              # 5000 mV regulator command
        trace = ep.load_raw_capture(out)
        self.assertEqual(trace.info["counter"]["discontinuities"], 0)
        on = trace.info["dut_power_on_sample"]
        self.assertLess(np.mean(trace.current_ua[:max(on - 100, 1)]),
                        np.mean(trace.current_ua[on + 1000:]))
        with self.assertRaises(SystemExit):
            me.capture("COM_FAKE", 5000, 0.1, out, "", None, "", opener=opener)
        self.assertEqual(meta["counter"]["discontinuities"], 0)
        self.assertEqual(meta["stale_bytes_dropped_at_open"], 0)

    def test_stale_stream_and_probe(self):
        """A PPK2 left measuring by an aborted run: stop it, drop the words, read metadata."""
        import ppk2_api.ppk2_api as api
        fake = FakeSerial()
        fake.measuring = True
        time.sleep(0.05)

        def opener(_port):
            with mock.patch("serial.Serial", return_value=fake):
                return api.PPK2_API("COM_FAKE"), api

        info = me.probe("COM_FAKE", 0.3, opener=opener)
        self.assertGreater(info["stale_bytes_dropped"], 0)
        self.assertEqual([w[0] for w in fake.written][:2], [0x07, 0x19])
        self.assertTrue(info["metadata_ok"])
        self.assertEqual(info["counter"]["discontinuities"], 0)
        self.assertAlmostEqual(info["samples_per_s"], 100_000, delta=5_000)
        self.assertNotIn(bytes([0x0C, 0x01]), fake.written)      # probe never powers the DUT


class Week7Driver(unittest.TestCase):
    def test_selftest_skips_power_on_glitch(self):
        b = Builder().add(500, 30).add(3, 900, ["ctrl"]).add(500, 30)
        for name in ep.SELFTEST_ORDER:
            b.add(20000, 400, [name])
        b.add(1000, 25)
        check = ep.selftest_check(b.trace(), MAP)
        self.assertTrue(check["pass"], check)
        self.assertEqual(check["ctrl_pulses_before_selftest"], 1)

    def test_slice_and_rotation_cut_at_power_off(self):
        b = Builder().add(100, 0)
        for k in range(8):
            b.add(50000, 900, [("dev", "prot", "tx", "wait")[k % 4]])
        b.add(20000, 900, ["dev"]).add(20000, 0)        # pulse cut by the DUT power OFF
        trace = b.trace()
        self.assertFalse(ep.rotation_check(trace, (0, 1, 2, 3))["pass"])
        cut = ep.slice_trace(trace, 100, trace.n - 20000)
        self.assertTrue(ep.rotation_check(cut, (0, 1, 2, 3))["pass"])

    def test_data_loss_checks(self):
        trace = Builder().add(10, 1).trace()
        trace.info = {"counter": {"available": True, "discontinuities": 2},
                      "capture": {"dut_on_rate_deviation_pct": 0.01, "reader_error": None}}
        self.assertEqual(ep.data_loss_checks(trace), {"no_data_loss": False, "sample_rate_ok": True})
        self.assertEqual(ep.data_loss_checks(trace, ignore_counter=True), {"sample_rate_ok": True})

    def test_interval_match(self):
        import week7_ppk2 as drv
        # B1 2026-10-22: the first TX takes 74 ms longer (connection events), so start spacing and
        # arrival spacing differ by 74 ms while the TX ends still line up with the arrivals.
        tx = [102.0, 28.0, 29.0, 40.0, 28.0]
        cycles = [{"start_sample": 100_000 + k * 106_000, "rho": "P1", "t_ctrl_ms": 0.2,
                   "t_dev_ms": 37.8, "t_prot_ms": 1.3, "t_tx_ms": tx[k]} for k in range(5)]
        records = [{"t_rx_ms": 5000 + k * 1060 + 39.3 + tx[k] + (7 if k == 3 else 0), "rho": "P1"}
                   for k in range(5)]
        match = drv.match_intervals(cycles, records)
        self.assertTrue(match["pass"])
        self.assertGreater(match["start_spacing_max_abs_delta_ms"], 70)
        records[3]["t_rx_ms"] += 40
        self.assertFalse(drv.match_intervals(cycles, records)["pass"])
        records[3]["t_rx_ms"] -= 40
        records[4]["rho"] = "P0"
        self.assertFalse(drv.match_intervals(cycles, records)["pass"])
        self.assertFalse(drv.match_intervals(cycles[:4], records)["pass"])


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
