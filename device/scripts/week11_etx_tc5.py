r"""TC5 week 11: connection events that carry the payload in the week-10 B1/B2 sessions, and an E_tx model.

Reads, never writes, the week-10 raw captures (raw.bin SHA-256 checked by week9_ppk2.load_raw_chunked) and each
session's analysis/cycles.csv + alls_rows.csv. For every cycle with s <= 9:
  * TX window = the D2 run of the cycle (as week10_ble.segment_ble_cycles).
  * Runs of current > 1 mA from TX start to the cycle end, gaps < 0.15 ms merged.
  * Anchor grid of the connection (interval 15 ms): phase = circular median of (start mod 15 ms) over the runs
    >= 0.7 ms that are not the CPU run at TX start nor the response run that ends the cycle.
  * Data events = the consecutive anchors from the first anchor after TX start: an anchor is a data event if it
    falls inside the CPU run at TX start (the payload is being queued then) or its run lasts > DATA_MIN_MS; the
    first anchor whose run is shorter (an empty event, ~0.85-1.0 ms) ends the burst. n_ev = their number.
  * E_burst = energy from TX start to the end of the last data-event run (gross 5 V), t_burst its duration.
    E_after = E_burst - E_tx(marker) = air time that the marker leaves to the WAIT phase.
Fits (OLS, per-split means of both sessions and per cycle): E_tx(marker) = a + b B (week-10 reference);
E_burst = a + b B; E_burst = c0 + e_ev n_ev + beta' B; n_ev versus B. Decomposition of E_burst: the CPU run at TX
start (E_cpu, it also holds the first anchor of a multi-event payload), the data-event runs after it (E_events,
t_events) and the rest (current below 1 mA between runs); fits of each against B and E_events against t_events.

Usage: python -B device/scripts/week11_etx_tc5.py --out <new dir> [--sessions <week-10 B session dir> ...]
Default sessions: D:\HUST\ASI_week10\B1-20261119-1537 and B2-20261119-1557 (raw data outside Git).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import energy_phases as ep  # noqa: E402
import week9_ppk2 as w9p  # noqa: E402

SESSIONS = [Path(r"D:\HUST\ASI_week10\B1-20261119-1537"), Path(r"D:\HUST\ASI_week10\B2-20261119-1557")]
FS = 100_000
DT_MS = 1e3 / FS
INTERVAL_MS = 15.0
THRESH_UA = 1000.0
MERGE_MS = 0.15
GRID_MIN_MS = 0.7
DATA_MIN_MS = 1.2
TX = ep.DEFAULT_MAP["tx"]


def runs_above(i: np.ndarray) -> list:
    d = np.diff(np.concatenate(([0], (i > THRESH_UA).astype(np.int8), [0])))
    s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    out = []
    gap = int(round(MERGE_MS / DT_MS))
    for x, y in zip(s, e):
        if out and x - out[-1][1] < gap:
            out[-1][1] = int(y)
        else:
            out.append([int(x), int(y)])
    return out


def circ_median_phase(starts_ms: list, interval_ms: float = INTERVAL_MS) -> float | None:
    if not starts_ms:
        return None
    ang = np.asarray(starts_ms) % interval_ms / interval_ms * 2 * np.pi
    ref = np.angle(np.mean(np.exp(1j * ang)))
    dev = np.angle(np.exp(1j * (ang - ref)))
    return float((ref + np.median(dev)) % (2 * np.pi) / (2 * np.pi) * interval_ms)


def burst(i: np.ndarray, tx_len: int, v: float, interval_ms: float = INTERVAL_MS,
          data_min_ms: float = DATA_MIN_MS) -> dict:
    """The data-event burst of one transmission. i: current (uA) from the TX marker rise to the end of the op
    (the response run, if any, ends it); tx_len: samples of the TX marker; v: supply in V. Rules in the module doc.
    Returns {"error": ...} when no anchor grid or no data event can be found."""
    runs = runs_above(i)
    if not runs:
        return {"error": "no_runs"}
    cpu = runs[0] if runs[0][0] <= int(0.1 / DT_MS) else None
    resp = runs[-1] if runs[-1][1] >= i.size - int(0.5 / DT_MS) else None
    grid = [r for r in runs if r is not cpu and r is not resp and (r[1] - r[0]) * DT_MS >= GRID_MIN_MS]
    phase = circ_median_phase([r[0] * DT_MS for r in grid], interval_ms)
    if phase is None:
        return {"error": "no_grid"}
    end_ms = (resp[0] if resp else i.size) * DT_MS
    anchors = []
    t = phase
    while t < end_ms - 0.5:
        anchors.append(t)
        t += interval_ms
    data, last_end = 0, None
    lengths = []
    for t in anchors:
        k = int(round(t / DT_MS))
        tol = int(0.4 / DT_MS)
        hit = next((r for r in runs if r[0] - tol <= k < r[1]), None)
        if hit is None:
            break
        if hit is cpu:
            data += 1
            last_end = hit[1]
            lengths.append(None)
            continue
        if hit is resp:
            break
        length = (hit[1] - max(hit[0], k - tol)) * DT_MS
        if length > data_min_ms:
            data += 1
            last_end = hit[1]
            lengths.append(length)
        else:
            break
    if data == 0 or last_end is None:
        return {"error": "no_data_event", "phase_ms": phase}
    e_burst = v * float(np.sum(i[:last_end])) * ep.DT_S
    ev_runs = [r for r in runs if r is not cpu and r[1] <= last_end and (r[1] - r[0]) * DT_MS > data_min_ms]
    e_cpu = v * float(np.sum(i[cpu[0]:cpu[1]])) * ep.DT_S if cpu else 0.0
    e_ev = sum(v * float(np.sum(i[x:y])) * ep.DT_S for x, y in ev_runs)
    t_ev = sum((y - x) * DT_MS for x, y in ev_runs)
    e_marker = v * float(np.sum(i[:tx_len])) * ep.DT_S
    return {"n_ev": data, "t_burst_ms": last_end * DT_MS, "E_burst_uJ": e_burst, "E_tx_marker_uJ": e_marker,
            "E_after_marker_uJ": e_burst - e_marker,
            "E_cpu_run_uJ": e_cpu, "E_events_uJ": e_ev, "t_events_ms": t_ev, "E_rest_uJ": e_burst - e_cpu - e_ev,
            "t_tx_marker_ms": tx_len * DT_MS, "phase_ms": phase,
            "first_anchor_ms": anchors[0] if anchors else None, "cpu_run_ms": (cpu[1] - cpu[0]) * DT_MS if cpu else None,
            "event_lengths_ms": [None if x is None else round(x, 2) for x in lengths], "grid_runs": len(grid)}


def analyze_cycle(tr, row, tx_s, tx_e, v):
    a, b = int(row["start_sample"]), int(row["end_sample"])
    sel = (tx_s >= a) & (tx_s < b)
    if sel.sum() != 1:
        return {"error": f"tx_runs={int(sel.sum())}"}
    ts, te = int(tx_s[sel][0]), int(tx_e[sel][0])
    return burst(tr.current_ua[ts:b], te - ts, v)


def ols(X: np.ndarray, y: np.ndarray, names: list) -> dict:
    X = np.column_stack([np.ones(len(y)), X]) if X.ndim == 1 else np.column_stack([np.ones(len(y)), *X.T])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    n, p = X.shape
    s2 = float(res @ res) / (n - p) if n > p else float("nan")
    cov = s2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    r2 = 1 - float(res @ res) / float(((y - y.mean()) ** 2).sum())
    return {"n": int(n), "r2": r2, "residual_sd": float(np.sqrt(s2)),
            "coef": {nm: {"value": float(b_), "se": float(s_)} for nm, b_, s_ in zip(["const", *names], beta, se)},
            "residuals": [float(x) for x in res]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sessions", type=Path, nargs="*", default=SESSIONS)
    args = ap.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; use a new directory")
    rows_out = []
    for sess in args.sessions:
        tr = w9p.load_raw_chunked(sess / "ppk2")
        v = tr.v_supply_mv / 1000.0
        tx_s, tx_e = ep.channel_runs(tr.bits, TX)
        cyc = list(csv.DictReader(open(sess / "analysis" / "cycles.csv", encoding="utf-8")))
        alls = {r["cycle"]: r for r in csv.DictReader(open(sess / "alls_rows.csv", encoding="utf-8"))}
        for r in cyc:
            if r["split"] == "10" or r["errors"]:
                continue
            res = analyze_cycle(tr, r, tx_s, tx_e, v)
            rows_out.append({"session": sess.name, "cycle": int(r["cycle"]), "split": int(r["split"]),
                             "bytes_payload": int(alls[r["cycle"]]["bytes_payload"]),
                             "E_tx_uJ_cycles_csv": float(r["E_tx_uJ"]), "t_wait_ms": float(r["t_wait_ms"]),
                             "E_wait_uJ_cycles_csv": float(r["E_wait_uJ"]), **res})
        del tr
    args.out.mkdir(parents=True)
    ok = [r for r in rows_out if "error" not in r]
    errs = [r for r in rows_out if "error" in r]
    keys = ["session", "cycle", "split", "bytes_payload", "n_ev", "t_tx_marker_ms", "t_burst_ms", "E_tx_uJ_cycles_csv",
            "E_tx_marker_uJ", "E_burst_uJ", "E_after_marker_uJ", "E_cpu_run_uJ", "E_events_uJ", "t_events_ms", "E_rest_uJ", "t_wait_ms", "E_wait_uJ_cycles_csv", "phase_ms",
            "first_anchor_ms", "cpu_run_ms", "grid_runs", "event_lengths_ms", "error"]
    with open(args.out / "cycles_etx.csv", "x", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, keys, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows_out:
            w.writerow({**r, "event_lengths_ms": json.dumps(r.get("event_lengths_ms"))})
    per_s = {}
    for s in sorted({r["split"] for r in ok}):
        g = [r for r in ok if r["split"] == s]
        n_ev = np.array([r["n_ev"] for r in g])
        per_s[s] = {"bytes": g[0]["bytes_payload"], "cycles": len(g),
                    "n_ev_values": {int(k): int(c) for k, c in zip(*np.unique(n_ev, return_counts=True))},
                    **{f"{k}_mean": float(np.mean([r[k] for r in g])) for k in
                       ("n_ev", "E_tx_uJ_cycles_csv", "E_tx_marker_uJ", "E_burst_uJ", "E_after_marker_uJ",
                        "t_tx_marker_ms", "t_burst_ms", "cpu_run_ms", "E_cpu_run_uJ", "E_events_uJ", "t_events_ms", "E_rest_uJ")}}
    B = np.array([per_s[s]["bytes"] for s in per_s], float)
    m = lambda k: np.array([per_s[s][k] for s in per_s], float)  # noqa: E731
    Bc = np.array([r["bytes_payload"] for r in ok], float)
    nc = np.array([r["n_ev"] for r in ok], float)
    fits = {
        "means_Etx_marker_vs_B": ols(B, m("E_tx_uJ_cycles_csv_mean"), ["B"]),
        "means_Eburst_vs_B": ols(B, m("E_burst_uJ_mean"), ["B"]),
        "means_Eburst_vs_nev_B": ols(np.column_stack([m("n_ev_mean"), B]), m("E_burst_uJ_mean"), ["n_ev", "B"]),
        "means_Eburst_vs_nev": ols(m("n_ev_mean"), m("E_burst_uJ_mean"), ["n_ev"]),
        "cycles_Eburst_vs_nev_B": ols(np.column_stack([nc, Bc]), np.array([r["E_burst_uJ"] for r in ok]), ["n_ev", "B"]),
        "cycles_Eburst_vs_B": ols(Bc, np.array([r["E_burst_uJ"] for r in ok]), ["B"]),
        "means_nev_vs_B": ols(B, m("n_ev_mean"), ["B"]),
        "means_Ecpu_vs_B": ols(B, m("E_cpu_run_uJ_mean"), ["B"]),
        "means_Eevents_vs_B": ols(B, m("E_events_uJ_mean"), ["B"]),
        "means_tevents_vs_B": ols(B, m("t_events_ms_mean"), ["B"]),
        "means_Eevents_vs_tevents": ols(m("t_events_ms_mean"), m("E_events_uJ_mean"), ["t_events_ms"]),
        "means_Erest_vs_B": ols(B, m("E_rest_uJ_mean"), ["B"]),
    }
    for f in fits.values():
        if f["n"] > 20:
            f.pop("residuals")
    summary = {"schema": "sv1-week11-tc5-etx/1", "sessions": [str(s) for s in args.sessions],
               "params": {"interval_ms": INTERVAL_MS, "threshold_uA": THRESH_UA, "merge_ms": MERGE_MS,
                          "grid_min_ms": GRID_MIN_MS, "data_min_ms": DATA_MIN_MS},
               "cycles_analyzed": len(ok), "cycles_error": [{k: r.get(k) for k in ("session", "cycle", "split", "error")} for r in errs],
               "per_split": per_s, "fits": fits}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("cycles_analyzed", "cycles_error")}, indent=1))
    for s, p in per_s.items():
        print(s, p["bytes"], p["n_ev_values"], {k: round(v, 1) for k, v in p.items() if k.endswith("_mean")})
    for k, f in fits.items():
        print(k, "R2 %.4f sd %.1f" % (f["r2"], f["residual_sd"]), {n: (round(c["value"], 3), round(c["se"], 3)) for n, c in f["coef"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
