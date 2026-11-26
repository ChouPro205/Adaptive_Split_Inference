#!/usr/bin/env python3
"""Week 10 result tables and IEEE figures (no device I/O).

Reads the summary directories written by week10_ppk2.py (summary-ewait, summary-alls, summary-prot) and the
PASS session-ewait directories they were built from; session folder names are arguments (they are only known
after the lab). Any of the three parts may be left out (a part not measured yet is reported as missing).
Two steps, each writing a NEW directory:

  tables   table_iii_week10.csv   per s 0..10: tensor C x L, payload bytes, E_dev radio on (pooled, session
                                  range, core), E_dev radio off (week 9 Table III), E_prot P1 (s <= 9, not in
                                  the action set), E_tx, E_wait, E_dev + E_tx + E_wait, E_cycle, t_dev, t_tx,
                                  t_wait, T = t_cycle, t_edge (KV260 log); all gross 5 V (W9-D9)
           fig_*.csv              the numbers of each figure
           week10_analysis.json   the decisions' outcomes (W10-D1..D5), inputs with SHA-256
  figures  reads a tables directory and writes figures/ (vector PDF with TrueType fonts + 600 dpi PNG,
           IEEE one/two-column widths, black and white readable; week7_figures.pyplot rcParams)

  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week10_figures.py tables \\
      --ewait-summary <dir> --ewait-session <A1> --ewait-session <A2> \\
      --alls-summary <dir> --prot-summary <dir> --out <new dir>
  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week10_figures.py figures --tables <that dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week7_figures as w7f  # noqa: E402
import week10_analysis as wa  # noqa: E402

ROOT = HERE.parents[1]
WEEK9_REFS = ROOT / "results" / "week9" / "device" / "refs" / "refs.csv"
WEEK9_TABLE_III = ROOT / "results" / "week9" / "device" / "analysis" / "table_iii_e_dev.csv"
SPLITS = tuple(range(11))
DEADLINE_MS = 500.0          # D of the G5 protocol (chốt 05/11), drawn on the latency panel only
LEVEL_MARK = {0: ("o", "white"), 15: ("s", "0.6"), 30: ("^", "black")}


# ----------------------------------------------------------------------------- helpers


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_csv(path: Path, header: list, rows: list) -> None:
    with open(path, "x", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else f"{v:.6g}" if isinstance(v, float) else v for v in row])


def read_csv(path: Path) -> list:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if v in ("", "None", None):
                r[k] = None
                continue
            try:
                r[k] = float(v)
            except ValueError:
                pass
    return rows


def stat(entry: dict | None, key: str = "mean"):
    return (entry or {}).get(key)


def shapes() -> dict:
    """(channels, length, payload bytes) of each split, from the week 9 references (W9-D3)."""
    out = {}
    with WEEK9_REFS.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            out.setdefault(int(r["split"]), (int(r["channels"]), int(r["length"]), int(r["bytes_payload"])))
    return out


def week9_off() -> dict:
    with WEEK9_TABLE_III.open(encoding="utf-8", newline="") as handle:
        return {int(r["split"]): {"E_dev_uJ": float(r["E_dev_uJ_mean"]), "core_uJ": float(r["E_dev_core_uJ"]),
                                  "t_dev_ms": float(r["t_dev_marker_ms"])} for r in csv.DictReader(handle)}


def summary_input(folder: Path, name: str, inputs: dict) -> dict:
    path = Path(folder) / name
    inputs[str(path)] = sha256(path)
    return load_json(path)


# ----------------------------------------------------------------------------- tables


def ewait_part(args, out: Path, inputs: dict) -> dict:
    """W10-D3: per-cycle scatter of the PASS sessions (rows SHA = the summary's), by-q table, bins."""
    summ = summary_input(args.ewait_summary, "ewait_summary.json", inputs)
    sources = summ["sessions"]
    if sorted(Path(s).name for s in args.ewait_session) != sorted(sources):
        raise SystemExit(f"--ewait-session {[Path(s).name for s in args.ewait_session]} != summary sessions "
                         f"{sorted(sources)}")
    scatter = []
    for folder in map(Path, args.ewait_session):
        rows_path = folder / "ewait_rows.csv"
        if sha256(rows_path) != sources[folder.name]["rows_sha256"]:
            raise SystemExit(f"{rows_path}: SHA-256 differs from the one summary-ewait used")
        inputs[str(rows_path)] = sources[folder.name]["rows_sha256"]
        for r in read_csv(rows_path):
            scatter.append([folder.name, int(r["cycle"]), r["rho"], r["lambda"], r["level_use"], int(r["q"]),
                            r["active"], r["t_wait_ms"], r["E_wait_uJ"], r["edge_queue_wait_ms"], r["edge_service_ms"]])
    write_csv(out / "fig_ewait_cycles.csv", ["tag", "cycle", "rho", "lambda", "level_use", "q", "active",
                                              "t_wait_ms", "E_wait_uJ", "edge_queue_wait_ms", "edge_service_ms"],
              scatter)
    write_csv(out / "fig_ewait_by_q.csv", ["q", "n", "t_wait_ms_mean", "t_wait_ms_ci95_half", "E_wait_uJ_mean",
                                           "E_wait_uJ_ci95_half", "active_fraction"],
              [[int(q), e["n"], stat(e["t_wait_ms"]), stat(e["t_wait_ms"], "ci95_half"), stat(e["E_wait_uJ"]),
                stat(e["E_wait_uJ"], "ci95_half"), e["active_fraction"]] for q, e in summ["by_q"].items()])
    write_csv(out / "fig_ewait_levels.csv",
              ["lambda_jobs_per_s", "quantity", "n", "pooled_mean", "ci95_half", "session_range_pct"],
              [[lam, key, s.get("n"), s.get("mean"), s.get("ci95_half"), s.get("session_range_pct")]
               for lam, entry in summ["levels"].items() for key, s in entry.items()])
    e, q = summ["pooled_E_wait_vs_t_wait"], summ["pooled_t_wait_vs_q"]
    return {
        "sessions": sorted(sources), "queue_seeds": summ.get("queue_seeds"),
        "E_wait_line": {k: e.get(k) for k in ("intercept", "slope", "slope_ci95", "intercept_ci95", "r2", "n")},
        "t_wait_vs_q": {k: q.get(k) for k in ("intercept", "slope", "slope_ci95", "r2", "n")},
        "t_svc_background_ms": summ["t_svc_background_ms"], "slope_over_t_svc": summ["slope_over_t_svc"],
        "P_conn_gross_mW_sessions": summ["P_conn_gross_mW_sessions"],
        "P_conn_gross_mW_week9": summ["P_conn_gross_mW_week9"], "b_over_P_conn_dev": summ["b_over_P_conn_dev"],
        "b_over_P_idle_off": summ["b_over_P_idle_off"], "rule_ewait_model": summ["rule_ewait_model"],
        "rule_queue_model": summ["rule_queue_model"], "long_over_empty_E_wait": summ["long_over_empty_E_wait"],
        "empty_q0_idle": summ["empty_q0_idle"],
        "levels": {lam: {k: {x: v.get(x) for x in ("n", "mean", "ci95_half", "session_range_pct")}
                         for k, v in entry.items()} for lam, entry in summ["levels"].items()},
    }


def cmd_tables(args) -> int:
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    out.mkdir(parents=True)
    inputs = {str(WEEK9_REFS): sha256(WEEK9_REFS), str(WEEK9_TABLE_III): sha256(WEEK9_TABLE_III)}
    shape, off = shapes(), week9_off()
    analysis = {"schema": "week10-analysis/1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "energy": "gross at the 5 V VBUS input unless named net or core (W9-D9, W9-D10)"}

    if args.ewait_summary:
        analysis["w10_d3_ewait"] = ewait_part(args, out, inputs)
    else:
        analysis["w10_d3_ewait"] = "MISSING (no summary-ewait given)"

    alls = summary_input(args.alls_summary, "alls_summary.json", inputs) if args.alls_summary else None
    prot = summary_input(args.prot_summary, "energy_prot.json", inputs) if args.prot_summary else None
    per_s = (alls or {}).get("per_s", {})
    pprot = (prot or {}).get("per_s", {})

    keys = ("E_dev_uJ", "E_tx_uJ", "E_wait_uJ", "E_cycle_uJ", "t_dev_ms", "t_tx_ms", "t_wait_ms", "t_cycle_ms",
            "t_edge_ms")
    rows = []
    for s in SPLITS:
        e = per_s.get(str(s), {})
        p = pprot.get(str(s), {})
        c, length, nbytes = shape[s]
        parts = [stat(e.get(k)) for k in ("E_dev_uJ", "E_tx_uJ", "E_wait_uJ")]
        e_sum = None if parts[0] is None else parts[0] + sum(x for x in parts[1:] if x is not None)
        rows.append([s, c, length, nbytes,
                     *[stat(e.get(k)) for k in keys], *[stat(e.get(k), "ci95_half") for k in keys],
                     stat(e.get("E_dev_uJ"), "session_range_pct"), (e.get("E_dev_core") or {}).get("mean"),
                     (e.get("E_dev_core") or {}).get("range_pct"), off.get(s, {}).get("E_dev_uJ"),
                     off.get(s, {}).get("core_uJ"), e_sum,
                     stat(p.get("E_prot_uJ")) if s <= 9 else None,
                     stat(p.get("E_prot_uJ"), "session_range_pct") if s <= 9 else None,
                     (p.get("E_prot_core") or {}).get("mean") if s <= 9 else None,
                     stat(p.get("t_prot_ms")) if s <= 9 else None])
    header = ["split", "channels", "length", "bytes_payload", *[f"{k}_mean" for k in keys],
              *[f"{k}_ci95_half" for k in keys], "E_dev_session_range_pct", "E_dev_core_uJ", "E_dev_core_range_pct",
              "E_dev_off_week9_uJ", "E_dev_off_week9_core_uJ", "E_dev_tx_wait_sum_uJ", "E_prot_P1_uJ",
              "E_prot_P1_session_range_pct", "E_prot_P1_core_uJ", "t_prot_P1_ms"]
    write_csv(out / "table_iii_week10.csv", header, rows)

    if alls:
        formula = alls["w10_d5_dev_on_formula"]
        write_csv(out / "fig_dev_on_vs_off.csv",
                  ["split", "core_on_uJ", "core_off_uJ", "t_dev_ms", "predicted_uJ", "deviation_pct", "counts"],
                  [[int(s), v["core_on_uJ"], off[int(s)]["core_uJ"], stat(per_s[s].get("t_dev_ms")), v["predicted_uJ"],
                    v["deviation_pct"], v["counts_for_rule"]] for s, v in formula["per_s"].items()])
        lin = alls["etx_linearity"]
        write_csv(out / "fig_etx_vs_payload.csv",
                  ["split", "bytes_payload", "E_tx_uJ_mean", "E_tx_uJ_ci95_half", "t_tx_ms_mean", "residual_uJ"],
                  [[s, shape[s][2], stat(per_s[str(s)].get("E_tx_uJ")), stat(per_s[str(s)].get("E_tx_uJ"), "ci95_half"),
                    stat(per_s[str(s)].get("t_tx_ms")), lin["residual_uJ"].get(str(s))]
                   for s in SPLITS if str(s) in per_s and per_s[str(s)].get("E_tx_uJ")])
        analysis["w10_d4_alls"] = {
            "sessions": sorted(alls["sessions"]), "P_conn_gross_mW_sessions": alls["P_conn_gross_mW_sessions"],
            "ci95_rel_below_10pct_every_s": all(per_s[str(s)]["ci95_rel_below_limit"] for s in SPLITS if str(s) in per_s),
            "splits_measured": sorted(int(s) for s in per_s),
            "E_tot_le_deadline_note": "T = t_cycle (CTRL rise -> WAIT fall), no queue load (W10-D4)"}
        analysis["w10_d5_dev_on_formula"] = formula
        analysis["etx_linearity"] = {"fit": {k: lin["fit"].get(k) for k in ("intercept", "slope", "slope_ci95", "r2", "n")},
                                     "alarm_nonlinear": lin["alarm_nonlinear"], "r2_min": lin["r2_min"]}
    else:
        analysis["w10_d4_alls"] = "MISSING (no summary-alls given)"

    if prot:
        conv = prot["E_conv_min_uJ"]
        rule = prot["w10_d2_conv_rule"]
        write_csv(out / "fig_e_prot.csv",
                  ["split", "E_prot_uJ_mean", "E_prot_uJ_ci95_half", "E_prot_session_min_uJ", "E_prot_session_max_uJ",
                   "E_prot_core_uJ", "t_prot_ms_mean", "over_conv_min", "pct_of_E_dev", "rule_pass"],
                  [[s, stat(pprot[str(s)]["E_prot_uJ"]), stat(pprot[str(s)]["E_prot_uJ"], "ci95_half"),
                    min(pprot[str(s)]["E_prot_uJ"]["session_means"].values()),
                    max(pprot[str(s)]["E_prot_uJ"]["session_means"].values()), pprot[str(s)]["E_prot_core"]["mean"],
                    stat(pprot[str(s)]["t_prot_ms"]), prot["ratios"][str(s)]["over_conv_min"],
                    prot["ratios"][str(s)]["pct_of_E_dev"], rule["per_s"][str(s)]["pass"]] for s in range(10)])
        write_csv(out / "fig_e_conv_min.csv", ["E_conv_min_uJ_mean", "session_min_uJ", "session_max_uJ", "t_conv_ms"],
                  [[conv["mean"], min(conv["session_means"].values()), max(conv["session_means"].values()),
                    stat(prot["t_conv_ms"])]])
        analysis["w10_d1_d2_prot"] = {
            "sessions": prot["sessions"], "E_conv_min_uJ": {k: conv.get(k) for k in ("mean", "ci95_half", "session_means")},
            "w10_d2_conv_rule": rule, "tc5_ci95_below_10pct_every_s": prot["tc5_ci95_below_10pct_every_s"],
            "ratios": prot["ratios"], "w9_d11_cross_day": prot.get("w9_d11_cross_day"),
            "E_dev_P0_vs_week9_table_iii_pct": prot.get("E_dev_P0_vs_week9_table_iii_pct")}
    else:
        analysis["w10_d1_d2_prot"] = "MISSING (no summary-prot given)"

    analysis["inputs_sha256"] = inputs
    analysis["tool_sha256"] = {n: sha256(HERE / n) for n in ("week10_figures.py", "week10_analysis.py",
                                                             "week10_ppk2.py", "week10_prot.py")}
    (out / "week10_analysis.json").write_text(json.dumps(analysis, indent=2, default=float) + "\n", encoding="utf-8")
    print_summary(analysis)
    return 0


def print_summary(a: dict) -> None:
    e = a["w10_d3_ewait"]
    if isinstance(e, dict):
        line, q = e["E_wait_line"], e["t_wait_vs_q"]
        print(f"W10-D3 E_wait = {line['intercept']:.1f} uJ + {line['slope']:.3f} mW * t_wait (R2 {line['r2']:.3f}); "
              f"P_conn {e['P_conn_gross_mW_sessions']:.3f} mW -> {e['rule_ewait_model']}")
        print(f"       t_wait = {q['intercept']:.1f} ms + {q['slope']:.1f} ms/job * q; t_svc {e['t_svc_background_ms']:.1f}"
              f" ms -> {e['rule_queue_model']}")
    else:
        print(f"W10-D3 {e}")
    f = a.get("w10_d5_dev_on_formula")
    print(f"W10-D5 {'PASS' if f and f['pass'] else 'FAIL' if f else 'MISSING'}"
          + (": " + ", ".join(f"s{s} {v['deviation_pct']:+.2f} %" for s, v in f["per_s"].items()) if f else ""))
    p = a["w10_d1_d2_prot"]
    if isinstance(p, dict):
        print(f"W10-D2 P1 < 1 conv layer: {'PASS' if p['w10_d2_conv_rule']['pass'] else 'FAIL'} "
              f"(E_conv,min {p['E_conv_min_uJ']['mean']:.2f} uJ; worst ratio "
              f"{max(v['ratio'] for v in p['w10_d2_conv_rule']['per_s'].values()):.2f})")
    else:
        print(f"W10-D1/D2 {p}")


# ----------------------------------------------------------------------------- figures


def cmd_figures(args) -> int:
    src = Path(args.tables)
    out = src / "figures"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    out.mkdir()
    plt = w7f.pyplot()
    written = []
    a = load_json(src / "week10_analysis.json")

    if (src / "fig_ewait_cycles.csv").exists():
        e = a["w10_d3_ewait"]
        cyc = read_csv(src / "fig_ewait_cycles.csv")
        # (a) E_wait vs t_wait, every cycle, marker = load level; fitted line and the P_conn slope
        fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 2.2))
        for lam, (mk, face) in LEVEL_MARK.items():
            g = [r for r in cyc if r["lambda"] is not None and int(r["lambda"]) == lam]
            ax.plot([r["t_wait_ms"] for r in g], [r["E_wait_uJ"] for r in g], mk, ms=2.2, mfc=face, color="black",
                    mew=0.4, label=rf"$\lambda={lam}$ job/s")
        line = e["E_wait_line"]
        xx = np.array([0.0, max(r["t_wait_ms"] for r in cyc) * 1.03])
        ax.plot(xx, line["intercept"] + line["slope"] * xx, color="black", lw=0.75,
                label=rf"fit $b={line['slope']:.2f}$ mW, $R^2={line['r2']:.3f}$")
        if e.get("P_conn_gross_mW_sessions"):
            ax.plot(xx, line["intercept"] + e["P_conn_gross_mW_sessions"] * xx, color="black", lw=0.75, ls="--",
                    label=rf"slope $P_\mathrm{{conn}}={e['P_conn_gross_mW_sessions']:.2f}$ mW")
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.set_xlabel(r"$t_\mathrm{wait}$ (ms, marker D3)")
        ax.set_ylabel(r"$E_\mathrm{wait}$ ($\mu$J, 5 V gross)")
        ax.legend(loc="upper left")
        w7f.save(fig, out, "fig_ewait_vs_twait", written)
        plt.close(fig)

        # (b) t_wait vs q at the request: mean +- CI95 per q, fitted line, q * t_svc model
        byq = [r for r in read_csv(src / "fig_ewait_by_q.csv") if r["n"] and r["n"] >= 2]
        fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 2.0))
        ax.errorbar([r["q"] for r in byq], [r["t_wait_ms_mean"] for r in byq],
                    yerr=[r["t_wait_ms_ci95_half"] or 0 for r in byq], fmt="o", ms=3, mfc="white", color="black",
                    capsize=2, label=r"mean $\pm$ CI95")
        for r in byq:
            ax.text(r["q"], r["t_wait_ms_mean"] + (r["t_wait_ms_ci95_half"] or 0) + 8, f"{int(r['n'])}",
                    ha="center", fontsize=5.5)
        q = e["t_wait_vs_q"]
        qq = np.array([0.0, max(r["q"] for r in byq)])
        ax.plot(qq, q["intercept"] + q["slope"] * qq, color="black", lw=0.75,
                label=rf"fit {q['slope']:.1f} ms/job")
        if e.get("t_svc_background_ms"):
            ax.plot(qq, q["intercept"] + e["t_svc_background_ms"] * qq, color="black", lw=0.75, ls="--",
                    label=rf"$\hat q\, t_\mathrm{{svc}}$, $t_\mathrm{{svc}}={e['t_svc_background_ms']:.1f}$ ms")
        ax.axhline(DEADLINE_MS, color="0.5", lw=0.5, ls=":")
        ax.text(0.99, DEADLINE_MS, r"$D$", transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=6,
                color="0.3")
        ax.set_ylim(top=max(DEADLINE_MS, max(r["t_wait_ms_mean"] for r in byq)) * 1.08)
        ax.set_xlabel(r"Jobs waiting at the request $q$")
        ax.set_ylabel(r"$t_\mathrm{wait}$ (ms)")
        ax.legend(loc="upper left")
        w7f.save(fig, out, "fig_twait_vs_q", written)
        plt.close(fig)

    if (src / "table_iii_week10.csv").exists():
        rows = [r for r in read_csv(src / "table_iii_week10.csv") if r["E_dev_uJ_mean"] is not None]
        if rows:
            # (c) energy and latency per s with the radio on (rho0): stacked dev / tx / wait
            s = np.array([int(r["split"]) for r in rows])
            fig, axes = plt.subplots(1, 2, figsize=(w7f.TWO_COL, 2.1))
            for ax, keys, ylabel in ((axes[0], ("E_dev_uJ", "E_tx_uJ", "E_wait_uJ"), r"Energy per cycle ($\mu$J)"),
                                     (axes[1], ("t_dev_ms", "t_tx_ms", "t_wait_ms"), "Time per cycle (ms)")):
                bottom = np.zeros(len(rows))
                for key, face, hatch, label in zip(keys, ("white", "0.75", "0.35"), ("///", "", ""),
                                                   ("device head", "transmit", "wait for result")):
                    v = np.array([r[f"{key}_mean"] or 0.0 for r in rows])
                    ax.bar(s, v, 0.7, bottom=bottom, color=face, edgecolor="black", hatch=hatch, label=label)
                    bottom += v
                ax.set_xticks(SPLITS)
                ax.set_xlabel("Split point $s$")
                ax.set_ylabel(ylabel)
            axes[0].plot([int(r["split"]) for r in rows if r["E_dev_off_week9_uJ"]],
                         [r["E_dev_off_week9_uJ"] for r in rows if r["E_dev_off_week9_uJ"]], "_", ms=7, mew=1.0,
                         color="black", label=r"$E_\mathrm{dev}$ radio off (wk 9)")
            axes[1].axhline(DEADLINE_MS, color="black", lw=0.5, ls="--", label=r"$D=500$ ms")
            axes[0].legend(loc="upper left")
            axes[1].legend(loc="upper left")
            w7f.save(fig, out, "fig_cycle_by_split_radio_on", written)
            plt.close(fig)

    if (src / "fig_etx_vs_payload.csv").exists():
        # (d) E_tx vs payload bytes (s0..s9) with the OLS line (week 11 alpha_k + beta_k B preview)
        rows = read_csv(src / "fig_etx_vs_payload.csv")
        lin = a["etx_linearity"]["fit"]
        fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 2.0))
        ax.errorbar([r["bytes_payload"] for r in rows], [r["E_tx_uJ_mean"] for r in rows],
                    yerr=[r["E_tx_uJ_ci95_half"] or 0 for r in rows], fmt="o", ms=3, mfc="white", color="black",
                    capsize=2, label=r"mean $\pm$ CI95")
        groups = []                       # splits with (nearly) the same payload share one label
        for r in sorted(rows, key=lambda r: r["bytes_payload"]):
            if groups and r["bytes_payload"] - groups[-1][-1]["bytes_payload"] < 200:
                groups[-1].append(r)
            else:
                groups.append([r])
        for g in groups:
            label = ", ".join(f"$s{int(r['split'])}$" for r in g)
            ax.annotate(label, (np.mean([r["bytes_payload"] for r in g]), np.mean([r["E_tx_uJ_mean"] for r in g])),
                        xytext=(4, -9), textcoords="offset points", fontsize=5.5)
        if lin.get("slope") is not None:
            bb = np.array([0.0, max(r["bytes_payload"] for r in rows) * 1.05])
            ax.plot(bb, lin["intercept"] + lin["slope"] * bb, color="black", lw=0.75, ls="--",
                    label=rf"OLS {lin['slope'] * 1e3:.1f} nJ/B, $R^2={lin['r2']:.3f}$")
        ax.set_xlabel("Payload $B$ (bytes)")
        ax.set_ylabel(r"$E_\mathrm{tx}$ ($\mu$J)")
        ax.set_xlim(left=0)
        ax.legend(loc="upper left")
        w7f.save(fig, out, "fig_etx_vs_payload", written)
        plt.close(fig)

    if (src / "fig_dev_on_vs_off.csv").exists():
        # (e) W10-D5: core E_dev radio on vs core radio off + 0.7 mW * t_dev
        rows = read_csv(src / "fig_dev_on_vs_off.csv")
        fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 1.8))
        ax.axhspan(-wa.DEV_ON_TOL_PCT, wa.DEV_ON_TOL_PCT, color="0.88", lw=0)
        for r in rows:
            counts = r["counts"] in (True, "True", 1.0)
            ax.plot(r["split"], r["deviation_pct"], "o", ms=3, mfc="black" if counts else "white", color="black")
        ax.axhline(0, color="0.5", lw=0.5)
        ax.set_xticks(SPLITS)
        ax.set_xlabel("Split point $s$")
        ax.set_ylabel("Core on vs formula (%)")
        ax.text(0.02, 0.95, rf"band $\pm${wa.DEV_ON_TOL_PCT:.0f} %; filled: $s\geq 2$ (rule)", transform=ax.transAxes,
                va="top", fontsize=6)
        w7f.save(fig, out, "fig_dev_on_vs_off", written)
        plt.close(fig)

    if (src / "fig_e_prot.csv").exists():
        # (f) E_prot(P1, s) vs the cheapest conv layer E_conv,min (W10-D2)
        rows = read_csv(src / "fig_e_prot.csv")
        conv = read_csv(src / "fig_e_conv_min.csv")[0]
        s = np.array([int(r["split"]) for r in rows])
        mean = np.array([r["E_prot_uJ_mean"] for r in rows])
        lo = mean - np.array([r["E_prot_session_min_uJ"] for r in rows])
        hi = np.array([r["E_prot_session_max_uJ"] for r in rows]) - mean
        fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 2.0))
        ax.bar(s, mean, 0.65, color="white", edgecolor="black", hatch="///", yerr=[lo, hi], capsize=1.5,
               error_kw={"lw": 0.5}, label=r"$E_\mathrm{prot}$ P1 (bar: session range)")
        ax.axhspan(conv["session_min_uJ"], conv["session_max_uJ"], color="0.8", lw=0)
        ax.axhline(conv["E_conv_min_uJ_mean"], color="black", lw=0.75, ls="--",
                   label=r"$E_\mathrm{conv,min}$ (features.0 + ReLU)")
        for r in rows:
            ax.annotate(f"{r['over_conv_min']:.2f}", (r["split"], r["E_prot_session_max_uJ"]), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=5)
        ax.text(9.4, conv["E_conv_min_uJ_mean"], "ratio to " + r"$E_\mathrm{conv,min}$" + " above bars", ha="right",
                va="bottom", fontsize=5.5)
        ax.set_xticks(range(10))
        ax.set_ylim(0, max(conv["session_max_uJ"], max(r["E_prot_session_max_uJ"] for r in rows)) * 1.3)
        ax.set_xlabel("Split point $s$")
        ax.set_ylabel(r"Energy ($\mu$J, 5 V gross)")
        ax.legend(loc="upper left")
        w7f.save(fig, out, "fig_e_prot_vs_conv", written)
        plt.close(fig)

    (out / "figures.json").write_text(json.dumps({"written": written, "tables": str(src),
                                                  "tool_sha256": sha256(HERE / "week10_figures.py")}, indent=2) + "\n",
                                      encoding="utf-8")
    print(f"{len(written)} files -> {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    t = sub.add_parser("tables")
    t.add_argument("--ewait-summary", type=Path, help="week10_ppk2.py summary-ewait directory")
    t.add_argument("--ewait-session", type=Path, action="append", default=[],
                   help="each PASS session-ewait directory the summary used")
    t.add_argument("--alls-summary", type=Path, help="week10_ppk2.py summary-alls directory")
    t.add_argument("--prot-summary", type=Path, help="week10_ppk2.py summary-prot directory")
    t.add_argument("--out", required=True, type=Path)
    t.set_defaults(func=cmd_tables)
    f = sub.add_parser("figures")
    f.add_argument("--tables", required=True, type=Path)
    f.set_defaults(func=cmd_figures)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
