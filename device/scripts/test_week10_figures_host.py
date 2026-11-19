#!/usr/bin/env python3
"""Host test of the week 10 reporting chain on synthetic PASS sessions (no device, no PPK2):
summary-ewait / summary-alls / summary-prot of week10_ppk2.py -> week10_figures.py tables + figures ->
publish_week10_results.py (only when the lab root D:/HUST/ASI_week10 with the plan, refs and clean builds exists).
Checks that the numbers put into the synthetic rows come back in table_iii_week10.csv and week10_analysis.json
(E_wait line, W10-D5 formula, E_tx line, W10-D2 rule, W9-D11 cross-day) and that every figure is written.

  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week10_figures_host.py
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import publish_week10_results as pub  # noqa: E402
import test_week10_host as t10  # noqa: E402
import week10_analysis as wa  # noqa: E402
import week10_figures as wf  # noqa: E402
import week10_ppk2 as wp  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="week10_figures_"))
LAB = Path("D:/HUST/ASI_week10")
B_MW, P_CONN = 1.55, 1.58
ETX_A, ETX_B = 150.0, 0.155          # uJ, uJ/B


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_rows(path: Path, fields: list, rows: list) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def ewait_session(tag: str, seed: int) -> Path:
    folder = TMP / tag
    write_json(folder / "check_ewait.json", {"status": "PASS"})
    write_json(folder / "energy_ewait.json", {"status": "PASS", "queue_seed": seed,
                                              "t_svc_background_ms": {"mean": 46.0},
                                              "P_conn": {"P_conn_gross_mW": {"mean": P_CONN}}})
    write_rows(folder / "ewait_rows.csv", wp.ROW_FIELDS, t10.synthetic_session(seed, B_MW))
    return folder


def alls_session(tag: str, seed: int, off: dict, shape: dict) -> Path:
    """50 cycles per s: core E_dev,on = week 9 core + 0.7 mW * t_dev exactly, plus a REG0 high-fraction term."""
    rng = np.random.default_rng(seed)
    folder = TMP / tag
    rows = []
    for k in range(50):
        for s in range(11):
            hf = float(rng.uniform(0.1, 0.6))
            t_dev = off[s]["t_dev_ms"]
            e_dev = off[s]["core_uJ"] + wa.DEV_ON_EXTRA_MW * t_dev + 0.3 * off[s]["core_uJ"] * hf
            row = {"cycle": len(rows), "round": k, "sample": k, "split": s, "bytes_payload": shape[s][2],
                   "E_dev_uJ": e_dev, "E_dev_net_uJ": e_dev - 0.127 * t_dev, "t_dev_ms": t_dev, "dev_high_fraction": hf,
                   "label": 0, "label_offline": 0}
            if s == 10:
                row.update(E_tx_uJ=None, t_tx_ms=None, E_wait_uJ=None, t_wait_ms=None, t_edge_ms=None,
                           E_tot_uJ=e_dev, E_cycle_uJ=e_dev + 2.0, t_cycle_ms=t_dev + 0.3)
            else:
                e_tx = ETX_A + ETX_B * shape[s][2] + rng.normal(0, 3.0)
                t_tx = 20.0 + shape[s][2] / 50.0
                e_wait, t_wait = 95.0 + B_MW * 60.0, 60.0
                row.update(E_tx_uJ=e_tx, t_tx_ms=t_tx, E_wait_uJ=e_wait, t_wait_ms=t_wait, t_edge_ms=30.0,
                           E_tot_uJ=e_dev + e_tx + e_wait, E_cycle_uJ=e_dev + e_tx + e_wait + 2.0,
                           t_cycle_ms=t_dev + t_tx + t_wait + 0.3)
            rows.append(row)
    write_json(folder / "check_alls.json", {"status": "PASS"})
    write_json(folder / "energy_alls.json", {"status": "PASS", "P_conn": {"P_conn_gross_mW": {"mean": P_CONN}}})
    write_rows(folder / "alls_rows.csv", wp.ALLS_ROW_FIELDS, rows)
    return folder


def prot_session(tag: str, seed: int, off: dict, prot_scale: float) -> Path:
    """Groups as week10_prot.session_groups writes them: E_prot 0.47 nJ/B-ish, P0 E_dev on the week 9 line."""
    rng = np.random.default_rng(seed)
    g = {k: {str(s): [] for s in range(10)} for k in ("prot", "t_prot", "prot_net", "prot_fraction", "dev_p0",
                                                      "t_dev_p0", "dev_p1", "delta", "dev_p0_fraction")}
    g.update(conv=[], t_conv=[], conv_fraction=[])
    for _ in range(50):
        for s in range(10):
            e_prot = prot_scale * (2.0 + 0.002 * (s + 1) * 1000) + rng.normal(0, 0.1)
            hf = float(rng.uniform(0.1, 0.6))
            core, raw = off[s]["core_uJ"], off[s]["E_dev_uJ"]
            slope = (raw - core) / 0.35                     # mean fraction 0.35 -> pooled mean = week 9 raw
            e_dev = core + slope * hf
            g["prot"][str(s)].append(e_prot)
            g["t_prot"][str(s)].append(0.5 + 0.1 * s)
            g["prot_net"][str(s)].append(e_prot - 0.05)
            g["prot_fraction"][str(s)].append(float(rng.uniform(0.0, 0.2)))
            g["dev_p0"][str(s)].append(e_dev)
            g["t_dev_p0"][str(s)].append(off[s]["t_dev_ms"])
            g["dev_p0_fraction"][str(s)].append(hf)
            g["dev_p1"][str(s)].append(e_dev)
            g["delta"][str(s)].append(e_prot)
        g["conv"].append(70.0 + rng.normal(0, 1.0))
        g["t_conv"].append(3.54)
        g["conv_fraction"].append(float(rng.uniform(0.2, 0.5)))
    folder = TMP / tag
    write_json(folder / "check_session.json", {"status": "PASS"})
    write_json(folder / "energy_prot.json", {"status": "PASS", "groups": g})
    return folder


class Chain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        off, shape = wf.week9_off(), wf.shapes()
        cls.ew = [ewait_session("A1", 11), ewait_session("A2", 12)]
        cls.al = [alls_session("B1", 21, off, shape), alls_session("B2", 22, off, shape)]
        cls.pr = [prot_session("P1", 31, off, 1.0), prot_session("P2", 32, off, 1.02)]
        cls.sum = {k: TMP / f"summary-{k}" for k in ("ewait", "alls", "prot")}
        for kind, sessions in (("ewait", cls.ew), ("alls", cls.al), ("prot", cls.pr)):
            argv = [f"summary-{kind}", "--out", str(cls.sum[kind])]
            for s in sessions:
                argv += ["--session", str(s)]
            assert wp.main(argv) == 0
        cls.tables = TMP / "tables"
        argv = ["tables", "--ewait-summary", str(cls.sum["ewait"]), "--alls-summary", str(cls.sum["alls"]),
                "--prot-summary", str(cls.sum["prot"]), "--out", str(cls.tables)]
        for s in cls.ew:
            argv += ["--ewait-session", str(s)]
        assert wf.main(argv) == 0
        assert wf.main(["figures", "--tables", str(cls.tables)]) == 0
        cls.analysis = json.loads((cls.tables / "week10_analysis.json").read_text(encoding="utf-8"))

    def test_ewait_line_recovered(self):
        e = self.analysis["w10_d3_ewait"]
        self.assertAlmostEqual(e["E_wait_line"]["slope"], B_MW, delta=0.03)
        self.assertEqual(e["rule_ewait_model"], "line a + b * t_wait")
        self.assertEqual(e["sessions"], ["A1", "A2"])

    def test_table_iii(self):
        rows = {int(r["split"]): r for r in wf.read_csv(self.tables / "table_iii_week10.csv")}
        self.assertEqual(sorted(rows), list(range(11)))
        self.assertIsNone(rows[10]["E_tx_uJ_mean"])
        self.assertIsNone(rows[10]["E_prot_P1_uJ"])
        self.assertEqual(int(rows[3]["bytes_payload"]), 5824)
        self.assertAlmostEqual(rows[2]["E_tx_uJ_mean"], ETX_A + ETX_B * 2912, delta=3.0)
        self.assertIsNotNone(rows[4]["E_prot_P1_uJ"])

    def test_rules(self):
        self.assertTrue(self.analysis["w10_d5_dev_on_formula"]["pass"])
        fit = self.analysis["etx_linearity"]["fit"]
        self.assertAlmostEqual(fit["slope"], ETX_B, delta=0.005)
        self.assertFalse(self.analysis["etx_linearity"]["alarm_nonlinear"])
        prot = self.analysis["w10_d1_d2_prot"]
        self.assertTrue(prot["w10_d2_conv_rule"]["pass"])
        cross = prot["w9_d11_cross_day"]
        self.assertEqual(len(cross["per_s"]), 10)
        for s, v in cross["per_s"].items():
            self.assertLess(abs(v["raw_delta_pct"]), 3.0, s)
            self.assertLess(abs(v["core_delta_pct"]), 3.0, s)

    def test_figures(self):
        written = json.loads((self.tables / "figures" / "figures.json").read_text(encoding="utf-8"))["written"]
        for name in ("fig_ewait_vs_twait", "fig_twait_vs_q", "fig_cycle_by_split_radio_on", "fig_etx_vs_payload",
                     "fig_dev_on_vs_off", "fig_e_prot_vs_conv"):
            self.assertIn(f"{name}.pdf", written)
            self.assertIn(f"{name}.png", written)

    def test_partial_tables(self):
        out = TMP / "tables-prot-only"
        self.assertEqual(wf.main(["tables", "--prot-summary", str(self.sum["prot"]), "--out", str(out)]), 0)
        self.assertEqual(wf.main(["figures", "--tables", str(out)]), 0)
        a = json.loads((out / "week10_analysis.json").read_text(encoding="utf-8"))
        self.assertTrue(a["w10_d3_ewait"].startswith("MISSING"))

    def test_wrong_session_rows_refused(self):
        bad = TMP / "A9"
        shutil.copytree(self.ew[1], bad)
        with open(bad / "ewait_rows.csv", "a", encoding="utf-8") as handle:
            handle.write("\n")
        argv = ["tables", "--ewait-summary", str(self.sum["ewait"]), "--ewait-session", str(self.ew[0]),
                "--ewait-session", str(bad), "--out", str(TMP / "tables-bad")]
        with self.assertRaises(SystemExit):
            wf.main(argv)

    @unittest.skipUnless((LAB / "plan-20261112").is_dir(), "lab root not on this machine")
    def test_publish(self):
        out = TMP / "published"
        argv = ["--lab", str(LAB), "--out", str(out), "--analysis", str(self.tables)]
        for kind, sessions in (("ewait", self.ew), ("alls", self.al), ("prot", self.pr)):
            argv += [x for s in sessions for x in ("--session", f"{kind}={s}")]
        argv += [x for s in self.sum.values() for x in ("--summary", str(s))]
        self.assertEqual(pub.main(argv), 0)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        paths = {f["path"] for f in manifest["files"]}
        self.assertIn("figures/fig_e_prot_vs_conv.pdf", paths)
        self.assertIn("analysis/table_iii_week10.csv", paths)
        self.assertIn("sessions/ewait_A1/ewait_rows.csv", paths)
        self.assertIn("build_check/prot_week10_build_check.json", paths)
        failing = TMP / "P9"
        shutil.copytree(self.pr[0], failing)
        write_json(failing / "check_session.json", {"status": "FAIL"})
        with self.assertRaises(SystemExit):
            pub.main(["--lab", str(LAB), "--out", str(TMP / "published-2"), "--session", f"prot={failing}"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
