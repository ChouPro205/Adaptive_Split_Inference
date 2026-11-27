"""Host tests of week11_etx_tc5 (TC5) on synthetic current traces: event grid, data-event count, burst energy, OLS."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import week11_etx_tc5 as tc5  # noqa: E402

FS = 100_000


def ms(x):
    return int(round(x * FS / 1000))


def trace(n_ms, pieces, base_ua=100.0):
    """pieces: (start ms, length ms, current uA) relative to the TX start at sample 0."""
    i = np.full(ms(n_ms), base_ua)
    for s, length, ua in pieces:
        i[ms(s):ms(s + length)] = ua
    return SimpleNamespace(current_ua=i)


def run(tr, tx_ms, end_ms):
    row = {"start_sample": "0", "end_sample": str(ms(end_ms))}
    return tc5.analyze_cycle(tr, row, np.array([0]), np.array([ms(tx_ms)]), 5.0)


class EventModel(unittest.TestCase):
    def test_single_event_after_marker(self):
        # s0-like: CPU queues for 1.3 ms, the only data event comes at 3 ms, empty events, response ends the cycle.
        pieces = [(0, 1.5, 4000), (3, 3.0, 5500), (18, 0.9, 3500), (33, 0.9, 3500), (48, 0.9, 3500), (63, 1.7, 4800)]
        r = run(trace(64.7, pieces), 1.3, 64.7)
        self.assertEqual(r["n_ev"], 1)
        self.assertAlmostEqual(r["phase_ms"], 3.0, places=1)
        self.assertAlmostEqual(r["t_burst_ms"], 6.0, places=2)
        expect = 5.0 * (1.5 * 4000 + 1.5 * 100 + 3.0 * 5500) * 1e-3
        self.assertAlmostEqual(r["E_burst_uJ"], expect, places=1)
        self.assertGreater(r["E_after_marker_uJ"], 0.5 * r["E_burst_uJ"])

    def test_multi_event_with_anchor_inside_cpu_run(self):
        # s5-like: the CPU run 0-10 ms holds the anchor at 6 ms; full events at 21 and 36 ms, a short one at 51 ms.
        pieces = [(0, 10, 4300), (21, 13, 6100), (36, 13, 6100), (51, 4, 5500), (66, 0.9, 3500), (81, 0.9, 3500),
                  (96, 1.7, 4800)]
        r = run(trace(97.7, pieces), 40, 97.7)
        self.assertEqual(r["n_ev"], 4)
        self.assertEqual(r["event_lengths_ms"][0], None)
        self.assertAlmostEqual(r["t_burst_ms"], 55.0, places=2)
        self.assertAlmostEqual(r["t_events_ms"], 30.0, places=2)

    def test_burst_stops_at_first_empty_event(self):
        # A long run after an empty anchor is not part of the burst (e.g. a later link-layer exchange).
        pieces = [(0, 1.5, 4000), (3, 3.0, 5500), (18, 0.9, 3500), (33, 3.0, 5500), (48, 0.9, 3500), (63, 1.7, 4800)]
        r = run(trace(64.7, pieces), 1.3, 64.7)
        self.assertEqual(r["n_ev"], 1)

    def test_no_data_event_is_an_error(self):
        pieces = [(0, 1.5, 4000), (18, 0.9, 3500), (33, 0.9, 3500), (48, 1.7, 4800)]
        r = run(trace(49.7, pieces), 1.3, 49.7)
        self.assertIn("error", r)

    def test_ols(self):
        rng = np.random.default_rng(1)
        x = rng.uniform(0, 6000, 50)
        n = rng.integers(1, 6, 50).astype(float)
        y = 50 + 90 * n + 0.2 * x
        f = tc5.ols(np.column_stack([n, x]), y, ["n_ev", "B"])
        self.assertAlmostEqual(f["coef"]["const"]["value"], 50, places=6)
        self.assertAlmostEqual(f["coef"]["n_ev"]["value"], 90, places=6)
        self.assertAlmostEqual(f["coef"]["B"]["value"], 0.2, places=9)
        self.assertAlmostEqual(f["r2"], 1.0, places=9)

    def test_circular_phase_wraps(self):
        self.assertAlmostEqual(tc5.circ_median_phase([14.9, 0.1 + 15, 14.95 + 30]), 14.98, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
