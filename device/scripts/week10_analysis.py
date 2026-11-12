"""Week 10 analysis rules (W10-D1..D6), fixed and committed BEFORE the week 10 measurement sessions.

Pure functions (no device, no capture) used by week10_ppk2.py and the week 10 report; host tests in
test_week10_host.py. Energy is gross at the 5 V input (W9-D9) unless a name says net or core.

W10-D3 E_wait under queue load (sessions: clean week 8 energy image, s2, 100 P1/P0 pairs, KV260 queue_sim
running ewait_load_blocks.csv):
  * queue state at each BLE request from the KV260 queue log (jobs.jsonl): q = queue_sim's own queue
    length logged at the foreground enqueue minus the request itself, cross-checked by rebuilding it: background
    jobs enqueued before the request and not yet started (the active job excluded, as queue_sim counts),
    active = a job in service at that instant. The request is the foreground job enqueued nearest its
    t_rx_ms (one-to-one, in order, within MATCH_TOL_MS).
  * level of a cycle = lambda of the load block holding its request time on the queue_sim clock; level
    means drop the first LEVEL_SKIP_S of every block; regressions use every cycle.
  * "empty" = q = 0 and no active job; "long" = the lambda 30 level.
  * (i)  t_wait = c + d * q over every cycle: d (ms/job, CI95) vs the mean background service time
         t_svc of the same session; the controller keeps q_hat * t_svc when QUEUE_RATIO_BAND holds
         d / t_svc, otherwise it uses the measured d.
  * (ii) E_wait = a + b * t_wait over every cycle: b (mW = uJ/ms, CI95, R^2) vs the session P_conn
         (gross, connected-idle gaps, week 9 method). The controller uses the line when R^2 >=
         EWAIT_R2_MIN and |b - P_conn| / P_conn <= EWAIT_B_TOL, otherwise the E_wait table in
         EWAIT_BIN_MS bins of t_wait (linear interpolation between bin means). Ratio b / P_idle,off
         reported (using the idle current would undercount by about that factor).
  * pooled number = mean of all valid cycles of the valid sessions, with the session means and their
    range (W9-D9); per rho means reported (E_wait does not depend on rho by construction).
W10-D4/D5 radio-on cycle of every s:
  * per s: E_dev,on (gross, net, core by core_fit of week 9, high fraction), t_dev, E_tx, t_tx, E_wait,
    t_wait, E_tot = E_cycle, T = t_cycle, t_edge from the KV260 log, P_conn per session;
  * W10-D5: E_dev,on core vs E_dev,off core (Table III) + DEV_ON_EXTRA_MW * t_dev: pass when the
    deviation is <= DEV_ON_TOL_PCT at every measured s >= 2 (s0, s1 reported; s2 calibrated the constant,
    so it is not an independent check);
  * E_tx linearity over the 10 payloads s0..s9: OLS E_tx = alpha + beta * B, alarm when R^2 < ETX_R2_MIN
    (the LUT always uses the measured E_tx of each s).
W10-D1/D2 E_prot of P1 (radio-off image `prot`):
  * E_prot(P1, s) = energy of the D1 phase; the paired delta (P1 - P0) of D0 + D1 per pair;
  * E_conv,min = energy of the HEAD-only s1 cycle (features.0 + ReLU, marker D0);
  * P1 < one conv layer at s when the LARGEST session mean of E_prot(P1, s) < the SMALLEST session
    mean of E_conv,min; the claim "P1 < 1 conv" holds when it holds at every s = 0..9; reported either
    way, with E_prot / E_conv,min, E_prot / (conv layer right before s) and E_prot / E_dev(s).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import energy_phases as ep

# ----------------------------------------------------------------------------- constants (locked)
MATCH_TOL_MS = 50.0          # foreground enqueue vs t_rx_ms on the same KV260 CLOCK_MONOTONIC
LEVEL_SKIP_S = 2.0           # W10-D3: drop the first 2 s of every block in level means
MIN_CYCLES_PER_LEVEL = 30    # per session, after the skip, so every level has a usable mean
LOAD_EFFECTIVE_MEDIAN_Q = 4  # lambda 30 level must actually queue (capacity 8, service ~46 ms)
CAUSALITY_TOL_MS = 2.0       # marker t_wait >= edge queue wait + service - tolerance
CAUSALITY_MIN_FRACTION = 0.99
QUEUE_REBUILD_MAX_DIFF = 1           # |rebuilt q - logged q| at every request
QUEUE_REBUILD_MIN_EXACT = 0.95       # fraction of requests with rebuilt q == logged q
QUEUE_RATIO_BAND = (0.8, 1.2)
EWAIT_R2_MIN = 0.9
EWAIT_B_TOL = 0.20
EWAIT_BIN_MS = 50.0
MIN_BIN_N = 5
P_CONN_WEEK9_GROSS_MW = 1.58204      # B5 KV260 15 ms, pooled (results/week9/device/analysis)
P_IDLE_OFF_MW = 25.417e-3 * 5.0      # week 2 idle current x 5 V
DEV_ON_EXTRA_MW = 0.7                # W10-D5
DEV_ON_TOL_PCT = 2.0
ETX_R2_MIN = 0.95
CI_LIMIT_PCT = 10.0                  # TC5: CI95 / mean


# ----------------------------------------------------------------------------- statistics


def ols(x, y) -> dict:
    """y = intercept + slope * x by least squares, Student-t CI95 of both, R^2."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = int(x.size)
    out = {"n": n}
    if n < 3 or float(np.ptp(x)) == 0.0:
        out.update(slope=None, intercept=None, r2=None)
        return out
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (intercept + slope * x)
    sse = float(np.sum(resid ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    s2 = sse / (n - 2)
    sxx = float(np.sum((x - x.mean()) ** 2))
    se_b = math.sqrt(s2 / sxx)
    se_a = math.sqrt(s2 * (1.0 / n + x.mean() ** 2 / sxx))
    t = ep.student_t_quantile(0.975, n - 2)
    out.update(slope=float(slope), intercept=float(intercept), slope_se=se_b, intercept_se=se_a,
               slope_ci95=[float(slope - t * se_b), float(slope + t * se_b)],
               intercept_ci95=[float(intercept - t * se_a), float(intercept + t * se_a)],
               r2=(1.0 - sse / sst) if sst > 0 else None, residual_sd=math.sqrt(s2))
    return out


def spread_pct(values) -> float | None:
    v = [float(x) for x in values if x is not None]
    return 100.0 * (max(v) - min(v)) / float(np.mean(v)) if len(v) > 1 and np.mean(v) else None


def pooled(values_by_session: dict) -> dict:
    """W9-D9: pooled mean of every value, CI95 over the pooled values, session means and range."""
    allv = [v for vs in values_by_session.values() for v in vs]
    means = {k: float(np.mean(vs)) for k, vs in values_by_session.items() if len(vs)}
    return {**ep.describe(allv), "session_means": means, "session_range_pct": spread_pct(means.values())}


# ----------------------------------------------------------------------------- KV260 queue log


def read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def queue_jobs(events: list) -> dict:
    """jobs.jsonl of queue_sim -> finished jobs per kind, drops, enqueue events (all times in ns)."""
    finished = [e for e in events if e.get("event") == "finished"]
    return {
        "background": sorted((e for e in finished if e.get("kind") == "background"), key=lambda e: e["enqueued_ns"]),
        "foreground": sorted((e for e in finished if e.get("kind") == "foreground"), key=lambda e: e["enqueued_ns"]),
        "enqueue": [e for e in events if e.get("event") == "enqueue"],
        "drops": [e for e in events if e.get("event") == "drop_capacity"],
    }


def queue_state_at(jobs: dict, t_ns: int) -> tuple:
    """(q, active) at t_ns: background jobs enqueued before t and started after t; any job in service."""
    q = sum(1 for e in jobs["background"] if e["enqueued_ns"] < t_ns < e["start_ns"])
    active = any(e["start_ns"] <= t_ns < e["end_ns"]
                 for e in jobs["background"] + jobs["foreground"] if e["enqueued_ns"] != t_ns)
    return q, active


def foreground_rows(jobs: dict) -> list:
    """Per foreground job: enqueue time; q = queue_sim's own queue length logged at the enqueue minus the
    job itself (= background jobs waiting, active excluded), or the rebuilt q when not logged; q_rebuilt
    and active from the finished events. queue_sim takes enqueued_ns/start_ns outside its lock, so the
    rebuilt q may differ by one job when two events race (QUEUE_REBUILD_* rule)."""
    by_enqueue = {e["enqueued_ns"]: e for e in jobs["enqueue"] if e.get("kind") == "foreground"}
    rows = []
    for e in jobs["foreground"]:
        q_rebuilt, active = queue_state_at(jobs, e["enqueued_ns"])
        logged = by_enqueue.get(e["enqueued_ns"], {}).get("queue_length_jobs")
        q_logged = None if logged is None else int(logged) - 1
        rows.append({"enqueued_ns": e["enqueued_ns"], "q": q_rebuilt if q_logged is None else q_logged,
                     "q_rebuilt": q_rebuilt, "active": active, "q_logged_minus_self": q_logged,
                     "queue_wait_ms": float(e["queue_wait_ms"]), "service_ms": float(e["service_ms"]),
                     "cancelled": bool(e.get("cancelled")), "error": e.get("error")})
    return rows


def match_requests(t_rx_ms: list, fg: list, tol_ms: float = MATCH_TOL_MS) -> dict:
    """Request i <-> foreground job i (both in time order), every |enqueue - t_rx| <= tol_ms."""
    if len(t_rx_ms) != len(fg):
        return {"pass": False, "reason": f"{len(t_rx_ms)} requests vs {len(fg)} foreground jobs"}
    off = np.array([f["enqueued_ns"] / 1e6 - t for f, t in zip(fg, t_rx_ms)], float)
    in_order = bool(np.all(np.diff(np.asarray(t_rx_ms, float)) > 0)) if len(t_rx_ms) > 1 else True
    return {"pass": bool(in_order and off.size and np.abs(off).max() <= tol_ms), "requests_in_time_order": in_order,
            "max_abs_offset_ms": float(np.abs(off).max()) if off.size else None,
            "median_offset_ms": float(np.median(off)) if off.size else None, "tol_ms": tol_ms}


def block_of(t_s: float, table: list) -> tuple:
    """(block index, lambda, seconds into the block) of t_s on the queue_sim clock; (None, None, None)
    outside the scenario."""
    for index, start, end, lam in table:
        if start <= t_s < end:
            return index, lam, t_s - start
    return None, None, None


# ----------------------------------------------------------------------------- W10-D3 E_wait


def ewait_rows(cycles: list, requests: list, fg: list, table: list, start_ns: int) -> list:
    """One row per cycle (cycles, requests and fg already matched one-to-one in order)."""
    rows = []
    for c, r, f in zip(cycles, requests, fg):
        t_s = (f["enqueued_ns"] - start_ns) / 1e9
        index, lam, offset = block_of(t_s, table)
        edge_ms = f["queue_wait_ms"] + f["service_ms"]
        rows.append({"cycle": int(c["cycle"]), "rho": c["rho"], "t_wait_ms": float(c["t_wait_ms"]),
                     "E_wait_uJ": float(c["E_wait_uJ"]), "E_wait_net_uJ": float(c["E_wait_net_uJ"])
                     if c.get("E_wait_net_uJ") not in (None, "") else None,
                     "q": f["q"], "q_rebuilt": f["q_rebuilt"], "active": f["active"],
                     "q_logged_minus_self": f["q_logged_minus_self"],
                     "block": index, "lambda": lam, "seconds_into_block": offset,
                     "level_use": offset is not None and offset >= LEVEL_SKIP_S,
                     "edge_queue_wait_ms": f["queue_wait_ms"], "edge_service_ms": f["service_ms"],
                     "t_wait_minus_edge_ms": float(c["t_wait_ms"]) - edge_ms, "t_rx_ms": r.get("t_rx_ms")})
    return rows


def background_service_ms(jobs: dict) -> dict:
    return ep.describe(float(e["service_ms"]) for e in jobs["background"] if not e.get("cancelled"))


def ewait_session_checks(rows: list, fg: list, queue_summary: dict) -> dict:
    levels = {lam: [r for r in rows if r["lambda"] == lam and r["level_use"]] for lam in (0.0, 15.0, 30.0)}
    long_q = [r["q"] for r in levels[30.0]]
    causal = [r["t_wait_minus_edge_ms"] >= -CAUSALITY_TOL_MS for r in rows]
    logged = [r for r in rows if r["q_logged_minus_self"] is not None]
    exact = [r["q_rebuilt"] == r["q_logged_minus_self"] for r in logged]
    return {
        "every_cycle_in_a_block": bool(rows) and all(r["block"] is not None for r in rows),
        "levels_min_cycles": all(len(v) >= MIN_CYCLES_PER_LEVEL for v in levels.values()),
        "load_effective_lambda30_median_q": bool(long_q) and float(np.median(long_q)) >= LOAD_EFFECTIVE_MEDIAN_Q,
        "foreground_not_cancelled_no_error": all(not f["cancelled"] and f["error"] is None for f in fg),
        "queue_no_failure": queue_summary.get("failure") is None,
        "causality_t_wait_ge_edge": bool(causal) and sum(causal) / len(causal) >= CAUSALITY_MIN_FRACTION,
        "queue_length_logged_at_every_request": len(logged) == len(rows) and bool(rows),
        "rebuilt_q_consistent_with_logged": bool(logged)
            and all(abs(r["q_rebuilt"] - r["q_logged_minus_self"]) <= QUEUE_REBUILD_MAX_DIFF for r in logged)
            and sum(exact) / len(exact) >= QUEUE_REBUILD_MIN_EXACT,
    }


def bin_table(rows: list, bin_ms: float = EWAIT_BIN_MS) -> list:
    """E_wait by t_wait bins: [lo, hi), n, mean t_wait, mean E_wait; bins with n < MIN_BIN_N kept, flagged."""
    out = {}
    for r in rows:
        k = int(r["t_wait_ms"] // bin_ms)
        out.setdefault(k, []).append(r)
    table = []
    for k in sorted(out):
        g = out[k]
        table.append({"lo_ms": k * bin_ms, "hi_ms": (k + 1) * bin_ms, "n": len(g),
                      "t_wait_ms": float(np.mean([r["t_wait_ms"] for r in g])),
                      "E_wait_uJ": float(np.mean([r["E_wait_uJ"] for r in g])), "usable": len(g) >= MIN_BIN_N})
    return table


def ewait_summary(rows_by_session: dict, t_svc_by_session: dict, p_conn_by_session: dict) -> dict:
    """W10-D3 tables, regressions and the model rule (see module doc). Sessions = valid sessions only."""
    allrows = [r for rs in rows_by_session.values() for r in rs]
    levels = {}
    for lam in (0.0, 15.0, 30.0):
        sel = {k: [r for r in rs if r["lambda"] == lam and r["level_use"]] for k, rs in rows_by_session.items()}
        levels[str(int(lam))] = {key: pooled({k: [r[key] for r in v] for k, v in sel.items()})
                                 for key in ("E_wait_uJ", "t_wait_ms", "q", "edge_queue_wait_ms")}
    by_q = {}
    for q in sorted({r["q"] for r in allrows}):
        g = [r for r in allrows if r["q"] == q]
        by_q[str(q)] = {"n": len(g), "E_wait_uJ": ep.describe(r["E_wait_uJ"] for r in g),
                        "t_wait_ms": ep.describe(r["t_wait_ms"] for r in g),
                        "active_fraction": float(np.mean([r["active"] for r in g]))}
    empty = [r for r in allrows if r["q"] == 0 and not r["active"]]
    per_session = {}
    for k, rs in rows_by_session.items():
        qfit = ols([r["q"] for r in rs], [r["t_wait_ms"] for r in rs])
        efit = ols([r["t_wait_ms"] for r in rs], [r["E_wait_uJ"] for r in rs])
        tsvc = t_svc_by_session.get(k, {}).get("mean")
        per_session[k] = {"t_wait_vs_q": qfit, "E_wait_vs_t_wait": efit, "t_svc_background_ms": tsvc,
                          "slope_over_t_svc": (qfit["slope"] / tsvc) if qfit.get("slope") and tsvc else None,
                          "P_conn_gross_mW": p_conn_by_session.get(k)}
    qfit = ols([r["q"] for r in allrows], [r["t_wait_ms"] for r in allrows])
    efit = ols([r["t_wait_ms"] for r in allrows], [r["E_wait_uJ"] for r in allrows])
    tsvc = [v.get("mean") for v in t_svc_by_session.values() if v.get("mean")]
    tsvc_mean = float(np.mean(tsvc)) if tsvc else None
    pconn = [v for v in p_conn_by_session.values() if v]
    pconn_mean = float(np.mean(pconn)) if pconn else None
    ratio = (qfit["slope"] / tsvc_mean) if qfit.get("slope") and tsvc_mean else None
    b = efit.get("slope")
    b_dev = abs(b - pconn_mean) / pconn_mean if b is not None and pconn_mean else None
    linear_ok = bool(efit.get("r2") is not None and efit["r2"] >= EWAIT_R2_MIN and b_dev is not None
                     and b_dev <= EWAIT_B_TOL)
    long_ = levels["30"]["E_wait_uJ"].get("mean")
    empty_mean = float(np.mean([r["E_wait_uJ"] for r in empty])) if empty else None
    return {
        "levels": levels, "by_q": by_q,
        "empty_q0_idle": {"n": len(empty), "E_wait_uJ": ep.describe(r["E_wait_uJ"] for r in empty),
                          "t_wait_ms": ep.describe(r["t_wait_ms"] for r in empty)},
        "long_over_empty_E_wait": (long_ / empty_mean) if long_ and empty_mean else None,
        "per_rho": {rho: ep.describe(r["E_wait_uJ"] for r in allrows if r["rho"] == rho) for rho in ("P1", "P0")},
        "per_session": per_session,
        "pooled_t_wait_vs_q": qfit, "pooled_E_wait_vs_t_wait": efit,
        "t_svc_background_ms": tsvc_mean, "P_conn_gross_mW_sessions": pconn_mean,
        "P_conn_gross_mW_week9": P_CONN_WEEK9_GROSS_MW,
        "rule_queue_model": ("q_hat * t_svc" if ratio is not None and QUEUE_RATIO_BAND[0] <= ratio <= QUEUE_RATIO_BAND[1]
                             else "measured slope d"),
        "slope_over_t_svc": ratio,
        "rule_ewait_model": "line a + b * t_wait" if linear_ok else f"table ({EWAIT_BIN_MS:.0f} ms bins)",
        "b_over_P_conn_dev": b_dev, "b_over_P_idle_off": (b / P_IDLE_OFF_MW) if b is not None else None,
        "bin_table": bin_table(allrows),
        "rules": {"queue_ratio_band": QUEUE_RATIO_BAND, "ewait_r2_min": EWAIT_R2_MIN, "ewait_b_tol": EWAIT_B_TOL,
                  "level_skip_s": LEVEL_SKIP_S},
    }


# ----------------------------------------------------------------------------- W10-D4/D5 every s, radio on


def dev_on_formula(core_on: dict, core_off: dict, t_dev_ms: dict, extra_mw: float = DEV_ON_EXTRA_MW) -> dict:
    """W10-D5: core E_dev,on vs core E_dev,off + extra_mw * t_dev at each measured s."""
    rows, ok = {}, True
    for s in sorted(core_on):
        if s not in core_off or s not in t_dev_ms:
            continue
        pred = core_off[s] + extra_mw * t_dev_ms[s]
        dev = 100.0 * (core_on[s] - pred) / pred
        within = abs(dev) <= DEV_ON_TOL_PCT
        rows[str(s)] = {"core_on_uJ": core_on[s], "predicted_uJ": pred, "deviation_pct": dev,
                        "within_tol": within, "counts_for_rule": s >= 2,
                        "note": "calibrated the constant" if s == 2 else ""}
        if s >= 2:
            ok = ok and within
    return {"rule": f"|core_on - (core_off + {extra_mw} mW * t_dev)| / predicted <= {DEV_ON_TOL_PCT} % at every s >= 2",
            "pass": ok and any(v["counts_for_rule"] for v in rows.values()), "per_s": rows}


def etx_linearity(bytes_by_s: dict, etx_by_s: dict) -> dict:
    ss = [s for s in sorted(etx_by_s) if s in bytes_by_s and s <= 9]
    fit = ols([bytes_by_s[s] for s in ss], [etx_by_s[s] for s in ss])
    resid = {str(s): etx_by_s[s] - (fit["intercept"] + fit["slope"] * bytes_by_s[s]) for s in ss} if fit.get("slope") is not None else {}
    return {"fit": fit, "residual_uJ": resid, "splits": ss,
            "alarm_nonlinear": fit.get("r2") is None or fit["r2"] < ETX_R2_MIN, "r2_min": ETX_R2_MIN}


ALLS_KEYS = ("E_dev_uJ", "E_dev_net_uJ", "t_dev_ms", "E_tx_uJ", "t_tx_ms", "E_wait_uJ", "t_wait_ms",
             "E_cycle_uJ", "t_cycle_ms", "t_edge_ms")


def alls_table(rows_by_session: dict) -> dict:
    """rows: {split, E_*, t_*, dev_high_fraction, ...} per valid cycle -> per s pooled stats (W9-D9) +
    core E_dev,on per session (core_fit), CI95/mean check."""
    import week9_figures as w9f
    out = {}
    splits = sorted({int(r["split"]) for rs in rows_by_session.values() for r in rs})
    for s in splits:
        sel = {k: [r for r in rs if int(r["split"]) == s] for k, rs in rows_by_session.items()}
        entry = {}
        for key in ALLS_KEYS:
            vals = {k: [float(r[key]) for r in v if r.get(key) not in (None, "")] for k, v in sel.items()}
            if any(vals.values()):
                entry[key] = pooled(vals)
        cores = {k: w9f.core_fit([r["dev_high_fraction"] for r in v], [r["E_dev_uJ"] for r in v])
                 for k, v in sel.items() if v}
        entry["E_dev_core"] = {"per_session": {k: c["core"] for k, c in cores.items()},
                               "mean": float(np.mean([c["core"] for c in cores.values()])) if cores else None,
                               "range_pct": spread_pct(c["core"] for c in cores.values())}
        e = entry.get("E_dev_uJ", {})
        entry["ci95_rel_below_limit"] = e.get("ci95_rel_pct") is not None and e["ci95_rel_pct"] < CI_LIMIT_PCT
        out[str(s)] = entry
    return out


# ----------------------------------------------------------------------------- W10-D1/D2 E_prot


def conv_rule(prot_session_means: dict, conv_session_means: dict) -> dict:
    """prot_session_means: {s: {session: mean E_prot(P1, s)}}, conv_session_means: {session: mean
    E_conv,min}. Pass at s when max over sessions of E_prot < min over sessions of E_conv,min."""
    conv_min = min(conv_session_means.values())
    per_s, ok = {}, True
    for s in sorted(prot_session_means):
        worst = max(prot_session_means[s].values())
        passed = worst < conv_min
        per_s[str(s)] = {"E_prot_max_session_uJ": worst, "E_conv_min_session_uJ": conv_min,
                         "ratio": worst / conv_min, "pass": passed}
        ok = ok and passed
    return {"rule": "max session mean E_prot(P1, s) < min session mean E_conv,min, every s = 0..9",
            "pass": ok and len(per_s) == 10, "per_s": per_s}


def prot_ratios(e_prot: dict, e_conv_min: float, e_layer_before: dict, e_dev: dict) -> dict:
    """Ratios reported with the rule: E_prot / E_conv,min, / conv layer right before s, / E_dev(s)."""
    return {str(s): {"over_conv_min": e_prot[s] / e_conv_min,
                     "over_layer_before_s": (e_prot[s] / e_layer_before[s]) if e_layer_before.get(s) else None,
                     "pct_of_E_dev": 100.0 * e_prot[s] / e_dev[s] if e_dev.get(s) else None}
            for s in sorted(e_prot)}
