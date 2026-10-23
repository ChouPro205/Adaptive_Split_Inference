#!/usr/bin/env python3
"""Week 7 result figures in IEEE style (no device I/O).

Input: a week7_ppk2.py session B directory (ppk2/ raw capture + analysis/ summary.json,
cycles.csv) and optionally the session A1 directory (idle with the week 2 Idle image).
Output (NEW --out directory), each as vector PDF (TrueType fonts, pdf.fonttype 42) + 600 dpi PNG:
  fig_cycle_waveform_P1 / _P0  one cycle, current + digital lanes D0..D4 (paper Figure 3 draft)
  fig_session_overview         whole capture, min/max envelope per bin, session stages
  fig_phase_energy             E per phase (gross, mean with CI95) for rho = P1 and P0
  fig_idle_histogram           idle current samples: firmware window vs week 2 Idle image
  fig_diff_pct                 |E_cycle - sum E_phase| / E_cycle of every cycle vs the 3 % limit
Style: 3.5 in single column / 7.16 in double column, Times New Roman 8 pt, STIX math, lines
>= 0.5 pt, readable in black and white (line styles, markers, hatches; no colour coding).

  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week7_figures.py --session <B> [--a1 <A1>] --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402

FS = ep.SAMPLE_RATE_HZ
ONE_COL, TWO_COL = 3.5, 7.16
LANES = ("ctrl", "dev", "prot", "tx", "wait")          # top to bottom, cycle order
LANE_LABEL = {"ctrl": "D4 CTRL", "dev": "D0 HEAD", "prot": "D1 PROT", "tx": "D2 TX", "wait": "D3 WAIT"}
SYMBOL = {"ctrl": r"$E_\mathrm{ctrl}$", "dev": r"$E_\mathrm{dev}$", "prot": r"$E_\mathrm{prot}$",
          "tx": r"$E_\mathrm{tx}$", "wait": r"$E_\mathrm{wait}$", "gap": r"$E_\mathrm{gap}$",
          "cycle": r"$E_\mathrm{cycle}$"}


def pyplot():
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mpl-week7"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["Times New Roman", "Times", "STIXGeneral"],
        "mathtext.fontset": "stix", "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "axes.linewidth": 0.5, "lines.linewidth": 0.75, "patch.linewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.minor.width": 0.5,
        "ytick.minor.width": 0.5, "xtick.direction": "in", "ytick.direction": "in",
        "hatch.linewidth": 0.5, "grid.linewidth": 0.5, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })
    return plt


def save(fig, out: Path, name: str, written: list) -> None:
    for ext, kw in (("pdf", {}), ("png", {"dpi": 600})):
        path = out / f"{name}.{ext}"
        if path.exists():
            raise SystemExit(f"refusing to overwrite {path}")
        fig.savefig(path, **kw)
        written.append(path.name)


def load_cycles(analysis: Path) -> list:
    with open(analysis / "cycles.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key, value in row.items():
            if key not in ("rho", "errors") and value not in ("", None):
                row[key] = float(value)
    return rows


def phase_map(summary: dict) -> dict:
    return {name: int(ch[1:]) for name, ch in summary["phase_map"].items()}


# ----------------------------------------------------------------------------- figures


def fig_cycle(plt, trace, cycle: dict, pmap: dict, out: Path, written: list, rho: str,
              before_ms=4.0, after_ms=8.0) -> None:
    a = max(0, int(cycle["start_sample"] - before_ms * FS / 1000))
    b = min(trace.n, int(cycle["end_sample"] + after_ms * FS / 1000))
    t = (np.arange(a, b) - cycle["start_sample"]) * 1e3 / FS
    fig, (ax, lanes) = plt.subplots(2, 1, figsize=(ONE_COL, 2.6), sharex=True,
                                    gridspec_kw={"height_ratios": [2.6, 1.3], "hspace": 0.08})
    ax.plot(t, trace.current_ua[a:b] / 1000.0, color="black", linewidth=0.5)
    ax.set_ylabel("Current at 5 V input (mA)")
    ax.set_ylim(bottom=0)
    edges = sorted({cycle["start_sample"], cycle["end_sample"]})
    for name in LANES:
        if name not in pmap:
            continue
        starts, ends = ep.channel_runs(trace.bits[a:b], pmap[name])
        edges += [a + int(s) for s in starts] + [a + int(e) for e in ends]
    for e in sorted(set(edges)):
        x = (e - cycle["start_sample"]) * 1e3 / FS
        for axis in (ax, lanes):
            axis.axvline(x, color="0.55", linestyle=":", linewidth=0.5, zorder=0)
    for k, name in enumerate(LANES):
        if name not in pmap:
            continue
        y0 = len(LANES) - 1 - k
        level = ((trace.bits[a:b] >> pmap[name]) & 1).astype(float)
        lanes.step(t, y0 + 0.7 * level, where="post", color="black", linewidth=0.6)
    lanes.set_yticks([len(LANES) - 1 - k + 0.35 for k in range(len(LANES))])
    lanes.set_yticklabels([LANE_LABEL[n] for n in LANES])
    lanes.tick_params(axis="y", length=0)
    lanes.set_ylim(-0.25, len(LANES))
    lanes.set_xlabel("Time from CTRL rising edge (ms)")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
        lanes.spines[side].set_visible(False)
    lanes.spines["left"].set_visible(False)
    ax.set_title(rf"$s={int(cycle.get('split', 2))}$, $\rho$ = {rho}, cycle {int(cycle['cycle'])}: "
                 rf"$E_\mathrm{{cycle}}$ = {cycle['E_cycle_uJ']:.0f} µJ, "
                 rf"$t_\mathrm{{cycle}}$ = {cycle['t_cycle_ms']:.1f} ms", loc="left", pad=3)
    fig.align_ylabels([ax, lanes])
    save(fig, out, f"fig_cycle_waveform_{rho}", written)
    plt.close(fig)


def envelope(values: np.ndarray, start: int, stop: int, bins: int):
    seg = values[start:stop]
    width = max(1, seg.size // bins)
    usable = seg[: seg.size - seg.size % width].reshape(-1, width)
    return usable.min(axis=1), usable.max(axis=1), usable.mean(axis=1), width


def fig_overview(plt, trace, summary: dict, cycles: list, out: Path, written: list) -> None:
    on = trace.info.get("dut_power_on_sample", 0)
    lo, hi, mean, width = envelope(trace.current_ua, on, trace.n, 3000)
    t = (np.arange(lo.size) * width + width / 2) / FS
    fig, (strip, ax) = plt.subplots(2, 1, figsize=(TWO_COL, 2.3), sharex=True,
                                    gridspec_kw={"height_ratios": [0.55, 2.0], "hspace": 0.04})
    floor = 1.0
    ax.fill_between(t, np.maximum(lo, floor), np.maximum(hi, floor), color="0.75", linewidth=0,
                    label=f"min-max per {width / FS * 1e3:.0f} ms bin")
    ax.plot(t, np.maximum(mean, floor), color="black", linewidth=0.5, label="mean per bin")
    ax.set_yscale("log")
    ax.set_ylim(bottom=floor)
    ax.set_xlabel("Time from DUT power on (s)")
    ax.set_ylabel(r"Current (µA)")
    ax.set_xlim(0, t[-1] if t.size else 1)
    stages = []
    st = summary.get("selftest") or {}
    if st.get("found"):
        stages.append(("self-test", st["pulses"][0]["start_sample"], st["end_sample"]))
    idle = summary.get("idle")
    if idle:
        stages.append(("idle, radio off", idle["start_sample"], idle["stop_sample"]))
    p1 = [c for c in cycles if c["rho"] == "P1"]
    p0 = [c for c in cycles if c["rho"] == "P0"]
    if idle and cycles:
        stages.append(("BLE link, connected idle", idle["stop_sample"], cycles[0]["start_sample"]))
    for label, group in ((r"$\rho$ = P1", p1), (r"$\rho$ = P0", p0)):
        if group:
            stages.append((f"{len(group)} cycles, {label}", group[0]["start_sample"],
                           group[-1]["end_sample"]))
    if cycles and trace.n - cycles[-1]["end_sample"] > 5 * FS:
        # week 6 ble_link restarts advertising once the link is released (B1/B2 2026-10-22)
        stages.append(("disconnect, advertising again", cycles[-1]["end_sample"], trace.n))
    # Stage strip: one bracket per stage, two staggered rows so neighbouring labels never collide.
    span = t[-1] if t.size else 1.0
    for k, (label, s, e) in enumerate(stages):
        x0, x1 = (s - on) / FS, (e - on) / FS
        y = 0.25 if k % 2 == 0 else 0.75
        ax.axvline(x0, color="black", linestyle="--", linewidth=0.5)
        strip.plot([x0, x0, x1, x1], [y - 0.12, y, y, y - 0.12], color="black", linewidth=0.5)
        if (x1 - x0) / span > 0.08:
            strip.text((x0 + x1) / 2, y + 0.04, label, ha="center", va="bottom", fontsize=7)
        else:   # short stage: label to the right of the bracket
            strip.text(x1 + 0.005 * span, y, label, ha="left", va="center", fontsize=7)
    strip.set_ylim(0, 1.25)
    strip.axis("off")
    ax.legend(loc="lower right", ncols=2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, out, "fig_session_overview", written)
    plt.close(fig)


def fig_phase_energy(plt, summary: dict, out: Path, written: list) -> None:
    names = ["ctrl", "dev", "prot", "tx", "wait", "gap", "cycle"]
    groups = summary.get("groups", {})
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.2))
    x = np.arange(len(names))
    style = {"P1": {"facecolor": "0.35", "hatch": None}, "P0": {"facecolor": "white", "hatch": "////"}}
    for k, rho in enumerate(("P1", "P0")):
        stats = groups.get(rho, {}).get("stats", {})
        means, errs, xs = [], [], []
        for i, name in enumerate(names):
            d = stats.get(f"E_{name}_uJ")
            if not d or d.get("mean", 0) <= 0:
                continue
            xs.append(x[i] + (k - 0.5) * 0.38)
            means.append(d["mean"])
            errs.append(d.get("ci95_half", 0.0))
        if xs:
            ax.bar(xs, means, width=0.36, yerr=errs, capsize=1.5, edgecolor="black",
                   error_kw={"elinewidth": 0.5, "capthick": 0.5}, label=rf"$\rho$ = {rho} "
                   rf"($n$ = {groups[rho]['n']})", **style[rho])
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([SYMBOL[n] for n in names])
    ax.set_ylabel(r"Energy per cycle, gross (µJ)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, out, "fig_phase_energy", written)
    plt.close(fig)


def idle_samples(directory: Path, start: int, stop: int) -> np.ndarray:
    trace = ep.load_raw_capture(directory)
    return trace.current_ua[start:stop]


def fig_idle(plt, fw_idle: np.ndarray, a1_idle: np.ndarray | None, out: Path, written: list) -> None:
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.0))
    data = [fw_idle] + ([a1_idle] if a1_idle is not None else [])
    lo = float(np.percentile(np.concatenate(data), 0.1))
    hi = float(np.percentile(np.concatenate(data), 99.9))
    bins = np.linspace(max(0.0, lo), max(hi, lo + 1.0), 100)
    curves = [(fw_idle, "-", r"week 7 energy image, boot idle"),
              (a1_idle, "--", r"week 2 Idle image")]
    for values, ls, label in curves:
        if values is None:
            continue
        ax.hist(np.clip(values, bins[0], bins[-1]), bins=bins, density=True, histtype="step",
                color="black", linestyle=ls, linewidth=0.75,
                label=f"{label}: mean {np.mean(values):.2f} µA, {values.size / FS:.0f} s")
        ax.axvline(float(np.mean(values)), color="black", linestyle=ls, linewidth=0.5)
    # Samples outside the 0.1-99.9th percentiles are clipped into the end bins (say so in captions).
    ax.set_xlabel(r"Current $I_\mathrm{idle}$ (µA)")
    ax.set_ylabel("Probability density (1/µA)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=1)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, out, "fig_idle_histogram", written)
    plt.close(fig)


def fig_diff(plt, cycles: list, out: Path, written: list) -> None:
    fig, ax = plt.subplots(figsize=(ONE_COL, 1.9))
    for rho, marker, face in (("P1", "o", "black"), ("P0", "s", "white")):
        rows = [c for c in cycles if c["rho"] == rho]
        if rows:
            ax.scatter([c["cycle"] for c in rows], [max(c["diff_pct"], 1e-4) for c in rows], s=6,
                       marker=marker, facecolors=face, edgecolors="black", linewidths=0.5,
                       label=rf"$\rho$ = {rho}")
    ax.axhline(ep.DIFF_LIMIT_PCT, color="black", linestyle="--", linewidth=0.75,
               label="acceptance limit 3 %")
    ax.set_yscale("log")
    smallest = min(max(c["diff_pct"], 1e-4) for c in cycles)
    ax.set_ylim(smallest / 3, ep.DIFF_LIMIT_PCT * 3)
    ax.set_xlabel("Cycle index")
    ax.set_ylabel(r"$|E_\mathrm{cycle}-\Sigma E_\mathrm{phase}|\,/\,E_\mathrm{cycle}$ (%)")
    ax.legend(loc="center right", ncols=1)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, out, "fig_diff_pct", written)
    plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", type=Path, required=True, help="week7_ppk2.py session B dir")
    parser.add_argument("--a1", type=Path, help="week7_ppk2.py idle (A1) dir")
    parser.add_argument("--out", type=Path, required=True, help="new directory")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"refusing to reuse {args.out}")
    summary = json.loads((args.session / "analysis" / "summary.json").read_text(encoding="utf-8"))
    cycles = load_cycles(args.session / "analysis")
    valid = [c for c in cycles if not c["errors"]]
    if not valid:
        raise SystemExit("no valid cycle to plot")
    plt = pyplot()
    trace = ep.load_raw_capture(args.session / "ppk2")
    pmap = phase_map(summary)
    args.out.mkdir(parents=True)
    written = []
    for rho in ("P1", "P0"):
        group = sorted((c for c in valid if c["rho"] == rho), key=lambda c: c["E_cycle_uJ"])
        if group:
            median = dict(group[len(group) // 2])
            median["split"] = (json.loads((args.session / "session.json").read_text(
                encoding="utf-8")).get("split", 2))
            fig_cycle(plt, trace, median, pmap, args.out, written, rho)
    fig_overview(plt, trace, summary, cycles, args.out, written)
    fig_phase_energy(plt, summary, args.out, written)
    idle = summary.get("idle")
    fw_idle = trace.current_ua[idle["start_sample"]:idle["stop_sample"]] if idle else None
    a1_idle = None
    if args.a1:
        check = json.loads((args.a1 / "check_idle.json").read_text(encoding="utf-8"))
        a1_idle = idle_samples(args.a1 / "ppk2", check["window"]["start_sample"],
                               check["window"]["stop_sample"])
    if fw_idle is not None:
        fig_idle(plt, fw_idle, a1_idle, args.out, written)
    fig_diff(plt, cycles, args.out, written)
    print(f"{len(written)} files -> {args.out}: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
