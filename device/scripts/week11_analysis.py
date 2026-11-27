"""Week 11 analysis rules of the week 12 link-state sessions (W11-D7..D14), fixed and committed BEFORE the lab.

Pure functions (no device, no capture) used by week11_ppk2.py and the week 11/12 reports; host tests in
test_week11_analysis_host.py. Energy is gross at the 5 V input (W9-D9) unless a name says net or marg.

Markers of the `link` image (week11/link_cycle.h, W7-D2 pins): D4 CTRL starts every op; D1 LINK = STATE or
RECONNECT procedure; D2 TX; D3 WAIT; D0 HEAD = S0C encodes. A STATE the central did not grant ends with
REFUSED_PULSES CTRL pulses of 1 ms right after the fall of D1. Ten 5 ms CTRL pulses before the self-test = the
plan bytes failed their SHA-256: no session.

W11-D7 segmentation. Ops are read in plan order: op k starts at its CTRL rising edge and ends at the rising edge
  of op k + 1 (the last op, an IDLE, at its CTRL fall + a ms). After a STATE, the CTRL pulses that start within
  REFUSED_WINDOW_MS of the D1 fall are its refusal signature, never ops: exactly REFUSED_PULSES of width
  REFUSED_PULSE_MS +- REFUSED_PULSE_TOL_MS = refused, none = granted, anything else = error. Each 10 us sample
  goes to the phase whose marker is the only one set (W7-D11); expected phases: STATE ctrl+link, IDLE ctrl,
  ECHO ctrl+tx+wait (in this order), S0C ctrl+dev, RECONNECT ctrl+link; a missing, repeated, unexpected or
  overlapping phase is an op error; ECHO WAIT >= ECHO_TIMEOUT_MS - TIMEOUT_TOL_MS = timeout (no answer or a
  wrong one), RECONNECT D1 >= RECONNECT_TIMEOUT_MS - TIMEOUT_TOL_MS = timeout. |E_op - sum(phases)| / E_op <
  DIFF_LIMIT_PCT on the active part of the op (CTRL rise to the fall of its last phase; the IDLE has no active
  part, the gap after it is the measurement).
W11-D8 block validity. A block (one link state) is valid when its STATE is granted without error, both of its
  IDLE windows pass the interval check and at most BLOCK_MAX_ERROR_PCT of its other ops have errors. Ops of an
  invalid block never enter a table. A refused block is reported as "state not available with this central"
  (e.g. no LE Coded on the KV260 adapter), it does not fail the session; the base block (and the reconnect
  block, base state) must be valid. Interval check (physical proof of k and L, the `link` image has no
  console): in the IDLE window the median spacing of radio events (current > EVENT_THRESHOLD_UA, merged within
  EVENT_MERGE_MS) equals k * (L + 1) within max(INTERVAL_TOL_MS, INTERVAL_TOL_PCT %) (SDC skips L events
  when it has nothing to send). PHY, data length and TX power have no marker: they come from the KV260 btmon /
  link-event log at import (W11-D14).
W11-D9 P_conn(state) = mean power of the IDLE window [CTRL fall + IDLE_SKIP_MS, next CTRL - IDLE_GUARD_MS],
  two windows per block (start, end) and session; drift = |end - start| / mean, alarm above DRIFT_ALARM_PCT.
  Net = gross - P_idle,off (week 2 idle current x 5 V); P_conn is the "keep the link" price per unit time.
W11-D10 ECHO (amended 2026-11-27 after TC5, before any week-12 data): E_tx (D2), t_tx, E_wait (D3), t_wait,
  E_op (CTRL..D3 fall) gross; marg = gross - P_conn(state of this block and session) x t, the price of sending
  on top of keeping the link. TC5 (raw week 10) showed that D2 falls when the last packet is queued in the
  controller, so the last data connection event (~100 uJ at 2M) lies in D3: D2 alone is not the cost of
  sending. Burst (week11_etx_tc5.burst, the TC5 rules): from the D2 rise to the D3 fall, anchor grid at the
  state's interval k, data events = consecutive anchors from the first one (inside the CPU run at TX start or a
  run longer than the block's data threshold = max(tc5.DATA_MIN_MS, median empty-event length of the block's
  IDLE windows + DATA_MARGIN_MS)); n_ev_tx = their number, E_burst / t_burst from the D2 rise to the end of
  the last data event; a burst the rules cannot find is a burst_error (the op stays valid, its burst values are
  missing and counted). Tables need >= MIN_VALID_REPEATS valid ops of each (state, B, flags) per session,
  otherwise the cell is missing. Per state, ack mode only: (i) PRIMARY E_tx,full = E_burst = alpha + beta * B
  on the means of the 7 teacher sizes 64..4096 B (TEACHER_SIZES, criterion R^2 >= ETX_R2_MIN) and on every
  valid ack op of the 12 sizes; (ii) the break-even rule's beta' = slope of E_op,marg vs B (all of the op above
  keeping the link: the last event and the constant 72-byte ack are inside, the ack cancels in the slope), on
  the 7 teacher sizes and on every valid ack op; n_ev_tx vs B; (iii) secondary, for comparison with week 10:
  the same fits on E_tx (D2) and E_tx,marg. E_wait in ack mode is reported against B (slope). L > 0: latency
  enabled vs disabled during WAIT, difference of means of t_wait and E_wait with a Welch CI95. Base block:
  E_rx(B) = mean E_wait full - mean E_wait ack (same session, same B; both receive the 72-byte ack or the
  frame), fitted against B; the burst of a full-mode op may run into the echoed frame and is not used.
W11-D11 S0C: per W8-D3 sample of a session, the encode cost = (E_D0(x100) - E_D0(x1)) / 99 (call overhead and
  marker edges cancel), the same for t; marg = - P_conn(base) x t; core (REG0 level, W9-D9..D12) by core_fit on
  the x100 ops; the repeat-1 numbers are reported as the cost of one call.
W11-D12 RECONNECT: t_link and E_link of D1 (device disconnect -> reconnected, MTU, subscribed, base state again);
  marg = E_link - P_conn(base) x t_link = what a disconnect-reconnect costs above keeping the link that long.
W11-D13 pooled number = mean of all valid values of the valid sessions with the session means and their range
  (W9-D9, W11-D4); E_tx and P_conn are reported gross (REG0 barely moves them), S0C gross + core.
W11-D14 KV260 logs (import): one echo record per ECHO entry of the plan, in order (length, ack/full mode,
  request_id +1 per ECHO, trace TX end vs t_rx_ms median-centred < 30 ms) and, for every block not refused, the
  last conn_update / phy_update / data_len seen by the central before the block's first IDLE = the state;
  connections = 1 + RECONNECTs. t_edge = t_tx_done - t_rx per echo.
Estimate (not a rule): session duration from the plan and an airtime model (estimate_session), for the capture
length and the 45-minute budget of W11-D3.
"""
from __future__ import annotations

import math

import numpy as np

import energy_phases as ep
import week10_analysis as wa
import week11_common as w11
import week11_etx_tc5 as tc5

FS = ep.SAMPLE_RATE_HZ
DT_MS = 1e3 / FS
CTRL, DEV, LINK, TX, WAIT = (ep.DEFAULT_MAP[k] for k in ("ctrl", "dev", "prot", "tx", "wait"))
PHASE_CH = {"ctrl": CTRL, "dev": DEV, "link": LINK, "tx": TX, "wait": WAIT}
EXPECTED = {w11.OP_STATE: ("ctrl", "link"), w11.OP_IDLE: ("ctrl",), w11.OP_ECHO: ("ctrl", "tx", "wait"),
            w11.OP_S0C: ("ctrl", "dev"), w11.OP_RECONNECT: ("ctrl", "link")}

# ----------------------------------------------------------------------------- constants (locked)
REFUSED_PULSES = 5                 # link_cycle.c REFUSED_PULSES
REFUSED_WINDOW_MS = 20.0           # the five pulses end ~10 ms after the D1 fall
REFUSED_PULSE_MS, REFUSED_PULSE_TOL_MS = 1.0, 0.3
PLAN_FAIL_PULSES, PLAN_FAIL_PULSE_MS = 10, 5.0
ECHO_TIMEOUT_MS = 5000.0           # CONFIG_WEEK11_ECHO_TIMEOUT_MS
RECONNECT_TIMEOUT_MS = 30000.0     # CONFIG_WEEK11_RECONNECT_TIMEOUT_MS
STATE_TIMEOUT_MS = 8000.0          # CONFIG_WEEK11_STATE_TIMEOUT_MS
TIMEOUT_TOL_MS = 20.0
DIFF_LIMIT_PCT = ep.DIFF_LIMIT_PCT
IDLE_SKIP_MS = 1000.0
IDLE_GUARD_MS = 10.0
EVENT_THRESHOLD_UA = 1000.0
EVENT_MERGE_MS = 2.0
INTERVAL_TOL_MS, INTERVAL_TOL_PCT = 0.5, 3.0
DRIFT_ALARM_PCT = 5.0
BLOCK_MAX_ERROR_PCT = 2.0
MIN_VALID_REPEATS = 5
TEACHER_SIZES = (64, 128, 256, 512, 1024, 2048, 4096)
ETX_R2_MIN = 0.98
EMPTY_EVENT_MIN_MS = 0.5           # IDLE runs shorter than this are the HFXO pre-runs, not events (TC5)
DATA_MARGIN_MS = 0.3               # data threshold above the block's median empty-event length (W11-D10)
S0C_REPEAT_LOW, S0C_REPEAT_HIGH = w11.S0C_REPEATS
P_IDLE_OFF_MW = wa.P_IDLE_OFF_MW


# ----------------------------------------------------------------------------- trace helpers


def radio_events(current: np.ndarray, threshold_ua: float = EVENT_THRESHOLD_UA,
                 merge_ms: float = EVENT_MERGE_MS) -> np.ndarray:
    """Start samples (relative) of radio events: runs above threshold merged when closer than merge_ms."""
    above = np.flatnonzero(np.asarray(current) > threshold_ua)
    if above.size == 0:
        return above
    merge = int(round(merge_ms / DT_MS))
    return above[np.concatenate(([True], np.diff(above) > merge))]


def expected_spacing_ms(state: w11.LinkState) -> float:
    return state.interval_ms * (state.latency + 1)


def interval_check(trace: ep.Trace, lo: int, hi: int, state: w11.LinkState) -> dict:
    starts = radio_events(trace.current_ua[lo:hi])
    spacing = np.diff(starts) * DT_MS
    expect = expected_spacing_ms(state)
    median = float(np.median(spacing)) if spacing.size else None
    tol = max(INTERVAL_TOL_MS, INTERVAL_TOL_PCT / 100.0 * expect)
    return {"events": int(starts.size), "median_spacing_ms": median, "expected_ms": expect, "tol_ms": tol,
            "pass": median is not None and spacing.size >= 10 and abs(median - expect) <= tol}


def _runs(trace: ep.Trace) -> dict:
    return {n: ep.channel_runs(trace.bits, c) for n, c in PHASE_CH.items()}


def _inside(runs: dict, lo: int, hi: int) -> dict:
    out = {}
    for n, (s, e) in runs.items():
        sel = (s >= lo) & (s < hi)
        out[n] = (s[sel], e[sel])
    return out


def plan_fail_signature(trace: ep.Trace, before: int) -> bool:
    """Ten ~5 ms CTRL pulses before the self-test: the image refused its plan."""
    s, e = ep.channel_runs(trace.bits, CTRL)
    sel = s < before
    widths = (e[sel] - s[sel]) * DT_MS
    return int(np.count_nonzero(np.abs(widths - PLAN_FAIL_PULSE_MS) < 1.0)) >= PLAN_FAIL_PULSES


# ----------------------------------------------------------------------------- W11-D7 segmentation


def segment_ops(trace: ep.Trace, after: int, plan_rows: list) -> list:
    """One row per plan entry, in plan order (see module doc). Rows beyond the CTRL edges found are
    'missing' (errors), CTRL edges beyond the plan are reported by the caller (extra_ctrl)."""
    runs = _runs(trace)
    ctrl_s, ctrl_e = runs["ctrl"]
    keep = ctrl_s > after
    ctrl_s, ctrl_e = ctrl_s[keep], ctrl_e[keep]
    v = trace.v_supply_mv / 1000.0
    mask = sum(1 << c for c in PHASE_CH.values())
    rows, j = [], 0
    for k, plan in enumerate(plan_rows):
        st = w11.STATES[plan.state]
        row = {"index": plan.index, "block": plan.block, "state": plan.state, "state_name": st.name,
               "op": w11.OP_NAMES[plan.op], "a": plan.a, "b": plan.b, "errors": [], "refused": False,
               "refused_pulses": 0}
        if j >= ctrl_s.size:
            row["errors"].append("missing")
            rows.append(row)
            continue
        start, c_end = int(ctrl_s[j]), int(ctrl_e[j])
        j += 1
        # refusal signature after a STATE: CTRL pulses right after the D1 fall
        if plan.op == w11.OP_STATE:
            ls, le = runs["link"]
            nxt = int(ctrl_s[j]) if j < ctrl_s.size else trace.n
            first = np.flatnonzero((ls >= start) & (ls < nxt))
            if first.size:
                d1_end = int(le[first[0]])
                widths = []
                while j < ctrl_s.size and ctrl_s[j] - d1_end <= REFUSED_WINDOW_MS / DT_MS:
                    widths.append((ctrl_e[j] - ctrl_s[j]) * DT_MS)
                    j += 1
                row["refused_pulses"] = len(widths)
                good = all(abs(w - REFUSED_PULSE_MS) <= REFUSED_PULSE_TOL_MS for w in widths)
                if len(widths) == REFUSED_PULSES and good:
                    row["refused"] = True
                elif widths:
                    row["errors"].append("bad_refusal_signature")
        if j < ctrl_s.size:
            stop = int(ctrl_s[j])
        elif plan.op == w11.OP_IDLE:
            stop = min(trace.n, c_end + int(round(plan.a / DT_MS)))
        else:
            stop = trace.n
            row["errors"].append("truncated_end")
        inside = _inside(runs, start, stop)
        need = EXPECTED[plan.op]
        for n in PHASE_CH:
            count = inside[n][0].size
            if n in need and count == 0:
                row["errors"].append(f"missing_{n}")
            elif n in need and count > 1 and not (n == "ctrl" and row["refused"]):
                row["errors"].append(f"multiple_{n}")
            elif n not in need and count:
                row["errors"].append(f"unexpected_{n}")
        order = [int(inside[n][0][0]) for n in need if inside[n][0].size]
        if order != sorted(order):
            row["errors"].append("phase_order")
        last = need[-1]
        active_end = int(inside[last][1][0]) if inside[last][1].size else c_end
        if plan.op == w11.OP_IDLE:
            active_end = c_end
        seg_bits = trace.bits[start:active_end] & mask
        seg_i = trace.current_ua[start:active_end]
        row.update(start_sample=start, ctrl_end_sample=c_end, active_end_sample=active_end, stop_sample=stop,
                   t_op_ms=(active_end - start) * DT_MS, E_op_uJ=v * float(np.sum(seg_i)) * ep.DT_S,
                   t_window_ms=(stop - start) * DT_MS)
        accounted = 0.0
        for n, c in PHASE_CH.items():
            only = seg_bits == (1 << c)
            row[f"t_{n}_ms"] = int(np.count_nonzero(only)) * DT_MS
            row[f"E_{n}_uJ"] = v * float(np.sum(seg_i[only])) * ep.DT_S
            accounted += row[f"E_{n}_uJ"]
        multi = (seg_bits != 0) & ((seg_bits & (seg_bits - 1)) != 0)
        row["overlap_samples"] = int(np.count_nonzero(multi))
        if row["overlap_samples"]:
            row["errors"].append("phase_overlap")
        gap = seg_bits == 0
        row["t_gap_ms"] = int(np.count_nonzero(gap)) * DT_MS
        row["E_gap_uJ"] = v * float(np.sum(seg_i[gap])) * ep.DT_S
        row["diff_pct"] = (100.0 * abs(row["E_op_uJ"] - accounted - row["E_gap_uJ"]) / row["E_op_uJ"]
                           if row["E_op_uJ"] > 0 else 0.0)
        row["gap_share_pct"] = 100.0 * row["E_gap_uJ"] / row["E_op_uJ"] if row["E_op_uJ"] > 0 else 0.0
        if plan.op != w11.OP_IDLE and row["gap_share_pct"] >= DIFF_LIMIT_PCT:
            row["errors"].append("gap_over_limit")
        # timeouts
        if plan.op == w11.OP_ECHO and row["t_wait_ms"] >= ECHO_TIMEOUT_MS - TIMEOUT_TOL_MS:
            row["errors"].append("wait_timeout")
        if plan.op == w11.OP_RECONNECT and row["t_link_ms"] >= RECONNECT_TIMEOUT_MS - TIMEOUT_TOL_MS:
            row["errors"].append("reconnect_timeout")
        if plan.op == w11.OP_STATE and row["t_link_ms"] >= STATE_TIMEOUT_MS - TIMEOUT_TOL_MS and not row["refused"]:
            row["errors"].append("state_timeout_without_signature")
        # TX marker of the ECHO: the burst (W11-D10) is found after all blocks' IDLE windows are known
        if plan.op == w11.OP_ECHO and inside["tx"][0].size == 1:
            row["tx_start_sample"], row["tx_end_sample"] = int(inside["tx"][0][0]), int(inside["tx"][1][0])
        # IDLE window
        if plan.op == w11.OP_IDLE:
            lo = c_end + int(round(IDLE_SKIP_MS / DT_MS))
            hi = stop - int(round(IDLE_GUARD_MS / DT_MS))
            if hi - lo < FS:
                row["errors"].append("idle_window_short")
            else:
                cur = trace.current_ua[lo:hi]
                row["P_idle_gross_mW"] = v * float(np.mean(cur)) / 1e3
                row["P_idle_net_mW"] = row["P_idle_gross_mW"] - P_IDLE_OFF_MW
                row["idle_window_s"] = (hi - lo) / FS
                row["interval"] = interval_check(trace, lo, hi, st)
                lengths = [(y - x) * DT_MS for x, y in tc5.runs_above(cur)]
                lengths = [x for x in lengths if x >= EMPTY_EVENT_MIN_MS]
                row["empty_event_ms"] = float(np.median(lengths)) if lengths else None
                if any(np.count_nonzero((trace.bits[lo:hi] >> c) & 1) for c in PHASE_CH.values()):
                    row["errors"].append("marker_in_idle_window")
        if plan.op == w11.OP_S0C and inside["dev"][0].size == 1:
            import week10_ble as wb
            row["dev_high_fraction"] = wb.head_high_fraction(seg_i[seg_bits == (1 << DEV)])
        rows.append(row)
    rows_extra = int(ctrl_s.size - j)
    if rows:
        rows[-1]["extra_ctrl_after_plan"] = rows_extra
    add_bursts(trace, rows)
    return rows


def data_threshold_ms(rows: list, block: int) -> float:
    """W11-D10: max(tc5.DATA_MIN_MS, median empty-event length of the block's IDLE windows + DATA_MARGIN_MS)."""
    e = [r["empty_event_ms"] for r in rows if r["block"] == block and r["op"] == "IDLE" and r.get("empty_event_ms")]
    return max(tc5.DATA_MIN_MS, float(np.median(e)) + DATA_MARGIN_MS) if e else tc5.DATA_MIN_MS


def add_bursts(trace: ep.Trace, rows: list) -> None:
    """W11-D10 burst of every ECHO with one TX marker and a WAIT: n_ev_tx, E_burst_uJ, t_burst_ms (or burst_error)."""
    v = trace.v_supply_mv / 1000.0
    for row in rows:
        if row["op"] != "ECHO" or "tx_start_sample" not in row or not row.get("t_wait_ms"):
            continue
        a, b = row["tx_start_sample"], row["active_end_sample"]
        thr = data_threshold_ms(rows, row["block"])
        res = tc5.burst(trace.current_ua[a:b], row["tx_end_sample"] - a, v, w11.STATES[row["state"]].interval_ms, thr)
        row["data_threshold_ms"] = thr
        if "error" in res:
            row["burst_error"] = res["error"]
            continue
        row.update(n_ev_tx=res["n_ev"], E_burst_uJ=res["E_burst_uJ"], t_burst_ms=res["t_burst_ms"],
                   E_after_tx_uJ=res["E_after_marker_uJ"])


# ----------------------------------------------------------------------------- W11-D8 blocks


def block_table(rows: list) -> dict:
    """Validity of every block (see module doc)."""
    out = {}
    for b in sorted({r["block"] for r in rows}):
        g = [r for r in rows if r["block"] == b]
        st = [r for r in g if r["op"] == "STATE"]
        idle = [r for r in g if r["op"] == "IDLE"]
        others = [r for r in g if r["op"] not in ("STATE", "IDLE")]
        state_ok = len(st) >= 1 and not st[0]["errors"] and not st[0]["refused"]
        idle_ok = len(idle) >= 1 and all(not r["errors"] and r.get("interval", {}).get("pass") for r in idle)
        bad = sum(1 for r in others if r["errors"])
        err_pct = 100.0 * bad / len(others) if others else 0.0
        p = [r["P_idle_gross_mW"] for r in idle if "P_idle_gross_mW" in r]
        drift = 100.0 * abs(p[-1] - p[0]) / float(np.mean(p)) if len(p) >= 2 else None
        out[b] = {"block": b, "state": g[0]["state"], "state_name": g[0]["state_name"],
                  "refused": bool(st and st[0]["refused"]), "state_errors": st[0]["errors"] if st else ["missing"],
                  "t_state_ms": st[0].get("t_link_ms") if st else None,
                  "idle_interval": [r.get("interval") for r in idle], "op_error_pct": err_pct,
                  "P_conn_gross_mW": float(np.mean(p)) if p else None, "P_conn_windows_mW": p,
                  "P_conn_drift_pct": drift, "drift_alarm": drift is not None and drift > DRIFT_ALARM_PCT,
                  "valid": bool(state_ok and idle_ok and err_pct <= BLOCK_MAX_ERROR_PCT)}
    return out


def valid_rows(rows: list, blocks: dict) -> list:
    """Ops of valid blocks without errors, with P_conn of the block and the marginal energies."""
    out = []
    for r in rows:
        blk = blocks[r["block"]]
        if not blk["valid"] or r["errors"]:
            continue
        p = blk["P_conn_gross_mW"]
        r = dict(r, P_conn_block_mW=p)
        for n in ("tx", "wait", "link", "dev"):
            r[f"E_{n}_marg_uJ"] = r[f"E_{n}_uJ"] - p * r[f"t_{n}_ms"]
        r["E_echo_uJ"] = r["E_ctrl_uJ"] + r["E_tx_uJ"] + r["E_wait_uJ"]
        if r["op"] == "ECHO":
            r["E_op_marg_uJ"] = r["E_op_uJ"] - p * r["t_op_ms"]
            if r.get("E_burst_uJ") is not None:
                r["E_burst_marg_uJ"] = r["E_burst_uJ"] - p * r["t_burst_ms"]
        out.append(r)
    return out


# ----------------------------------------------------------------------------- session tables


def _by_session(rows_by_session: dict, pred, key: str) -> dict:
    return {s: [float(r[key]) for r in rs if pred(r) and r.get(key) is not None] for s, rs in rows_by_session.items()}


def welch(a, b) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size < 2 or b.size < 2:
        return {"n_a": int(a.size), "n_b": int(b.size), "diff": None}
    va, vb = a.var(ddof=1) / a.size, b.var(ddof=1) / b.size
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / ((va ** 2) / (a.size - 1) + (vb ** 2) / (b.size - 1)) if va + vb > 0 else a.size + b.size - 2
    t = ep.student_t_quantile(0.975, max(1, int(df)))
    d = float(a.mean() - b.mean())
    return {"n_a": int(a.size), "n_b": int(b.size), "diff": d, "ci95": [d - t * se, d + t * se], "df": df}


def echo_cells(rows_by_session: dict) -> dict:
    """(state, B, flags) cells: pooled E_tx, t_tx, E_wait, t_wait, E_echo, marg; cell usable when every
    session has >= MIN_VALID_REPEATS valid ops."""
    cells = {}
    keys = sorted({(r["state"], r["a"], r["b"]) for rs in rows_by_session.values() for r in rs if r["op"] == "ECHO"})
    for st, size, flags in keys:
        pred = lambda r, st=st, size=size, flags=flags: r["op"] == "ECHO" and r["state"] == st and r["a"] == size and r["b"] == flags  # noqa: E731
        counts = {s: sum(1 for r in rs if pred(r)) for s, rs in rows_by_session.items()}
        cell = {"state": st, "state_name": w11.STATES[st].name, "B": size, "flags": flags,
                "ack": bool(flags & w11.ECHO_ACK), "latency_off": bool(flags & w11.ECHO_LATENCY_OFF),
                "valid_per_session": counts, "usable": all(c >= MIN_VALID_REPEATS for c in counts.values())}
        for key in ("E_tx_uJ", "t_tx_ms", "E_wait_uJ", "t_wait_ms", "E_echo_uJ", "E_tx_marg_uJ", "E_wait_marg_uJ",
                    "n_ev_tx", "E_burst_uJ", "t_burst_ms", "E_burst_marg_uJ", "E_after_tx_uJ", "E_op_uJ", "t_op_ms",
                    "E_op_marg_uJ"):
            cell[key] = wa.pooled(_by_session(rows_by_session, pred, key))
        cell["burst_errors"] = sum(1 for rs in rows_by_session.values() for r in rs if pred(r) and r.get("burst_error"))
        cells[f"{st}/{size}/{flags}"] = cell
    return cells


def etx_fits(cells: dict, rows_by_session: dict) -> dict:
    """Per state, ack mode (W11-D10): PRIMARY E_tx,full = E_burst vs B on the 7 teacher sizes (means of usable ack
    cells, criterion R^2 >= ETX_R2_MIN) and on every valid ack op; the break-even beta' = slope of E_op,marg vs B;
    n_ev_tx vs B; secondary the D2 fits (E_tx, E_tx,marg) as in week 10; E_wait vs B slope."""
    out = {}
    for st in sorted({c["state"] for c in cells.values()}):
        ack = [c for c in cells.values() if c["state"] == st and c["ack"] and c["usable"]]
        # one value per size: pool both latency variants (TX runs with latency enabled in both)
        sizes = sorted({c["B"] for c in ack})
        ops = [r for rs in rows_by_session.values() for r in rs
               if r["op"] == "ECHO" and r["state"] == st and r["b"] & w11.ECHO_ACK and r["a"] in sizes]

        def means_of(key):
            m = {}
            for size in sizes:
                vals = [r[key] for r in ops if r["a"] == size and r.get(key) is not None]
                if vals:
                    m[size] = float(np.mean(vals))
            return m

        def fits(key):
            m = means_of(key)
            teach = [s for s in TEACHER_SIZES if s in m]
            have = [r for r in ops if r.get(key) is not None]
            return m, teach, wa.ols(teach, [m[s] for s in teach]), wa.ols([r["a"] for r in have], [r[key] for r in have])

        burst_m, burst_teach, burst7, burst_all = fits("E_burst_uJ")
        _, op_teach, op7, op_all = fits("E_op_marg_uJ")
        tx_m, tx_teach, tx7, tx_all = fits("E_tx_uJ")
        _, _, txm7, txm_all = fits("E_tx_marg_uJ")
        _, _, bm7, bm_all = fits("E_burst_marg_uJ")
        _, _, _, nev_all = fits("n_ev_tx")
        out[str(st)] = {
            "state_name": w11.STATES[st].name, "sizes": sizes,
            "teacher_fit": burst7, "teacher_sizes_present": burst_teach, "teacher_quantity": "E_burst_uJ (E_tx,full)",
            "teacher_r2_pass": (len(burst_teach) == len(TEACHER_SIZES) and burst7.get("r2") is not None
                                and burst7["r2"] >= ETX_R2_MIN),
            "all_ops_fit": burst_all,
            "teacher_fit_burst_marg": bm7, "all_ops_fit_burst_marg": bm_all,
            "breakeven_beta_teacher_fit": op7, "breakeven_beta_all_ops_fit": op_all,
            "breakeven_quantity": "E_op_marg_uJ (ack mode)", "breakeven_sizes_present": op_teach,
            "n_ev_vs_B": nev_all,
            "burst_errors": sum(1 for r in ops if r.get("burst_error")),
            "marker_teacher_fit": tx7, "marker_teacher_sizes_present": tx_teach,
            "marker_teacher_r2_pass": (len(tx_teach) == len(TEACHER_SIZES) and tx7.get("r2") is not None
                                       and tx7["r2"] >= ETX_R2_MIN),
            "marker_all_ops_fit": tx_all, "marker_teacher_fit_marg": txm7, "marker_all_ops_fit_marg": txm_all,
            "E_wait_vs_B_ack": wa.ols([r["a"] for r in ops], [r["E_wait_uJ"] for r in ops]),
            "t_tx_vs_B": wa.ols([r["a"] for r in ops], [r["t_tx_ms"] for r in ops]),
            "means_E_burst_uJ": {str(k): v for k, v in burst_m.items()},
            "means_E_tx_uJ": {str(k): v for k, v in tx_m.items()},
        }
    return out


def latency_compare(rows_by_session: dict) -> dict:
    """L > 0 states: latency enabled (flags 1) vs disabled during WAIT (flags 3), all sizes pooled."""
    out = {}
    for st in w11.STATES:
        if st.latency == 0:
            continue
        rs = [r for v in rows_by_session.values() for r in v if r["op"] == "ECHO" and r["state"] == st.index]
        on = [r for r in rs if r["b"] == w11.ECHO_ACK]
        off = [r for r in rs if r["b"] == w11.ECHO_ACK | w11.ECHO_LATENCY_OFF]
        if not on and not off:
            continue
        out[st.name] = {key: {"enabled": ep.describe(r[key] for r in on), "disabled": ep.describe(r[key] for r in off),
                              "enabled_minus_disabled": welch([r[key] for r in on], [r[key] for r in off])}
                        for key in ("t_wait_ms", "E_wait_uJ", "E_echo_uJ")}
    return out


def rx_table(rows_by_session: dict) -> dict:
    """Base block: E_rx(B) = mean E_wait full - mean E_wait ack per session and B, fitted against B."""
    per, xs, ys = {}, [], []
    for s, rs in rows_by_session.items():
        base = [r for r in rs if r["op"] == "ECHO" and r["state"] == w11.BASE and not r["b"] & w11.ECHO_LATENCY_OFF]
        for size in sorted({r["a"] for r in base}):
            full = [r["E_wait_uJ"] for r in base if r["a"] == size and r["b"] == 0]
            ack = [r["E_wait_uJ"] for r in base if r["a"] == size and r["b"] == w11.ECHO_ACK]
            tf = [r["t_wait_ms"] for r in base if r["a"] == size and r["b"] == 0]
            ta = [r["t_wait_ms"] for r in base if r["a"] == size and r["b"] == w11.ECHO_ACK]
            if full and ack:
                d = float(np.mean(full) - np.mean(ack))
                per.setdefault(str(size), {})[s] = {"E_rx_uJ": d, "t_rx_extra_ms": float(np.mean(tf) - np.mean(ta)),
                                                    "n_full": len(full), "n_ack": len(ack)}
                xs.append(size)
                ys.append(d)
    return {"per_B": per, "fit": wa.ols(xs, ys), "rule": "E_rx(B) = E_wait(full) - E_wait(ack), base block"}


def s0c_table(rows_by_session: dict) -> dict:
    """W11-D11: per-encode cost from the paired x100 / x1 ops of each sample."""
    per_session, core = {}, {}
    for s, rs in rows_by_session.items():
        ops = [r for r in rs if r["op"] == "S0C"]
        enc, t_enc, enc_marg, one, t_one = [], [], [], [], []
        for n in sorted({r["a"] for r in ops}):
            lo = [r for r in ops if r["a"] == n and r["b"] == S0C_REPEAT_LOW]
            hi = [r for r in ops if r["a"] == n and r["b"] == S0C_REPEAT_HIGH]
            if len(lo) != 1 or len(hi) != 1:
                continue
            k = S0C_REPEAT_HIGH - S0C_REPEAT_LOW
            e = (hi[0]["E_dev_uJ"] - lo[0]["E_dev_uJ"]) / k
            t = (hi[0]["t_dev_ms"] - lo[0]["t_dev_ms"]) / k
            enc.append(e)
            t_enc.append(t)
            enc_marg.append(e - hi[0]["P_conn_block_mW"] * t)
            one.append(lo[0]["E_dev_uJ"])
            t_one.append(lo[0]["t_dev_ms"])
        hi_ops = [r for r in ops if r["b"] == S0C_REPEAT_HIGH and r.get("dev_high_fraction") is not None]
        if len(hi_ops) >= 3:
            import week9_figures as w9f
            fit = w9f.core_fit([r["dev_high_fraction"] for r in hi_ops], [r["E_dev_uJ"] for r in hi_ops])
            core[s] = {"x100_core_uJ": fit["core"], "per_encode_core_uJ": fit["core"] / S0C_REPEAT_HIGH, "fit": fit}
        per_session[s] = {"E_encode_uJ": enc, "t_encode_ms": t_enc, "E_encode_marg_uJ": enc_marg,
                          "E_call_x1_uJ": one, "t_call_x1_ms": t_one}
    keys = ("E_encode_uJ", "t_encode_ms", "E_encode_marg_uJ", "E_call_x1_uJ", "t_call_x1_ms")
    return {**{k: wa.pooled({s: v[k] for s, v in per_session.items()}) for k in keys},
            "samples_paired": {s: len(v["E_encode_uJ"]) for s, v in per_session.items()},
            "core": core, "core_range_pct": wa.spread_pct(c["per_encode_core_uJ"] for c in core.values()),
            "rule": "per encode = (E_D0(x100) - E_D0(x1)) / 99 per sample; marg = - P_conn(base) x t"}


def reconnect_table(rows_by_session: dict) -> dict:
    keys = ("t_link_ms", "E_link_uJ", "E_link_marg_uJ")
    pred = lambda r: r["op"] == "RECONNECT"  # noqa: E731
    return {k: wa.pooled(_by_session(rows_by_session, pred, k)) for k in keys}


def pconn_table(blocks_by_session: dict) -> dict:
    """W11-D9 per state over valid blocks: every IDLE window of every session pooled."""
    out = {}
    for st in w11.STATES:
        vals = {s: [p for b in bl.values() if b["state"] == st.index and b["valid"] for p in b["P_conn_windows_mW"]]
                for s, bl in blocks_by_session.items()}
        status = {s: [("valid" if b["valid"] else "refused" if b["refused"] else "invalid")
                      for b in bl.values() if b["state"] == st.index] for s, bl in blocks_by_session.items()}
        gross = wa.pooled(vals)
        out[st.name] = {"state": st.index, "phy": w11.PHY_NAMES[st.phy], "interval_ms": st.interval_ms,
                        "latency": st.latency, "tx_octets": st.tx_octets, "tx_power_dbm": st.tx_power_dbm,
                        "block_status": status, "P_conn_gross_mW": gross,
                        "P_conn_net_mW": (gross["mean"] - P_IDLE_OFF_MW) if gross.get("mean") is not None else None}
    return out


def summary(rows_by_session: dict, blocks_by_session: dict) -> dict:
    """Every W11-D9..D13 table from the valid rows of >= 1 sessions (the result needs >= 2 PASS sessions)."""
    cells = echo_cells(rows_by_session)
    return {"P_conn": pconn_table(blocks_by_session), "echo_cells": cells,
            "E_tx_fits": etx_fits(cells, rows_by_session), "latency": latency_compare(rows_by_session),
            "E_rx_base": rx_table(rows_by_session), "s0c": s0c_table(rows_by_session),
            "reconnect": reconnect_table(rows_by_session),
            "states_missing": sorted({b["state_name"] for bl in blocks_by_session.values() for b in bl.values()
                                      if not b["valid"]}),
            "rules": {"min_valid_repeats": MIN_VALID_REPEATS, "teacher_sizes": TEACHER_SIZES, "etx_r2_min": ETX_R2_MIN,
                      "idle_skip_ms": IDLE_SKIP_MS, "interval_tol": [INTERVAL_TOL_MS, INTERVAL_TOL_PCT],
                      "block_max_error_pct": BLOCK_MAX_ERROR_PCT, "drift_alarm_pct": DRIFT_ALARM_PCT}}


# ----------------------------------------------------------------------------- KV260 log (W11-D14)


def normalize_echo_records(lines: list) -> list:
    """Echo records of the KV260 service log (JSONL). Accepted keys: request_id, length (or frame_length,
    total_length), mode ('ack'/'full' or 1/0), t_rx_ms, t_tx_done_ms (or t_reply_ms). Records whose event
    is not an echo frame are skipped."""
    import json
    out = []
    for line in lines:
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("ev", e.get("event")) not in ("echo", "echo_rx", "echo_frame"):
            continue
        mode = e.get("mode")
        mode = {"ack": 1, "full": 0, 1: 1, 0: 0}.get(mode, mode)
        out.append({"request_id": int(e["request_id"]),
                    "length": int(e.get("length", e.get("frame_length", e.get("total_length")))),
                    "mode": mode, "t_rx_ms": e.get("t_rx_ms"), "t_tx_done_ms": e.get("t_tx_done_ms", e.get("t_reply_ms")),
                    "connection": e.get("connection")})
    return out


def check_echo_records(records: list, seg_rows: list) -> dict:
    """Every ECHO entry of the plan is one KV260 record, in order: length = plan, mode = plan, request_id
    consecutive (+1 per ECHO, link_cycle.c next_request_id); trace TX end vs t_rx_ms median-centred within
    week7 INTERVAL_MATCH_MS. Gives t_edge_ms = t_tx_done_ms - t_rx_ms per echo row."""
    import week7_ppk2 as w7p
    echo = [r for r in seg_rows if r["op"] == "ECHO"]
    if len(echo) != len(records):
        return {"pass": False, "reason": f"{len(echo)} ECHO entries vs {len(records)} KV260 echo records"}
    lengths = [r["a"] for r in echo] == [x["length"] for x in records]
    modes = [int(bool(r["b"] & w11.ECHO_ACK)) for r in echo] == [x["mode"] for x in records]
    ids = [x["request_id"] for x in records]
    consecutive = all(b == (a + 1 if a + 1 not in (0, 0xFFFFFFFF) else 1) for a, b in zip(ids, ids[1:]))
    timed = [(r, x) for r, x in zip(echo, records) if "active_end_sample" in r and isinstance(x.get("t_rx_ms"), (int, float))]
    off = np.array([x["t_rx_ms"] - (r["active_end_sample"] * DT_MS - r["t_wait_ms"]) for r, x in timed], float)
    centred = np.abs(off - np.median(off)) if off.size else off
    time_ok = bool(off.size == len(echo) and centred.max() < w7p.INTERVAL_MATCH_MS)
    for r, x in zip(echo, records):
        if isinstance(x.get("t_rx_ms"), (int, float)) and isinstance(x.get("t_tx_done_ms"), (int, float)):
            r["t_edge_ms"] = x["t_tx_done_ms"] - x["t_rx_ms"]
    return {"pass": bool(lengths and modes and consecutive and time_ok), "lengths_equal_plan": lengths,
            "modes_equal_plan": modes, "request_ids_consecutive": consecutive, "time_match": time_ok,
            "max_abs_offset_ms": float(centred.max()) if centred.size else None, "limit_ms": w7p.INTERVAL_MATCH_MS}


def check_link_events(events: list, seg_rows: list, blocks: dict, t_offset_ms: float) -> dict:
    """Granted parameters seen by the central (btmon / service log, JSONL with t_ms on the KV260 clock):
    for every block not refused, the last event of each kind before its first IDLE matches the state.
    kinds: conn_update (interval_1250us, latency, timeout_10ms), phy_update (tx_phy, rx_phy as 1/2/3 =
    1M/2M/Coded), data_len (max_tx_octets or max_rx_octets of the dongle's direction). t_offset_ms = KV260
    clock - trace clock (from check_echo_records)."""
    per = {}
    for b, blk in blocks.items():
        if blk["refused"]:
            continue
        st = w11.STATES[blk["state"]]
        idle = [r for r in seg_rows if r["block"] == b and r["op"] == "IDLE" and "ctrl_end_sample" in r]
        if not idle:
            continue
        t_cut = idle[0]["ctrl_end_sample"] * DT_MS + t_offset_ms
        last = {}
        for e in events:
            if e.get("t_ms") is not None and e["t_ms"] <= t_cut:
                last[e.get("ev")] = e
        cu, ph, dl = last.get("conn_update"), last.get("phy_update"), last.get("data_len")
        ok = {"conn_update": bool(cu) and cu.get("interval_1250us") == st.interval_1250us
              and cu.get("latency") == st.latency and cu.get("timeout_10ms") == st.timeout_10ms,
              "phy_update": (bool(ph) and ph.get("tx_phy") == st.phy and ph.get("rx_phy") == st.phy)
              or (ph is None and st.phy == w11.PHY_1M),
              "data_len": bool(dl) and dl.get("max_rx_octets", dl.get("max_tx_octets")) == st.tx_octets}
        per[str(b)] = {"state_name": st.name, **ok, "pass": all(ok.values())}
    return {"pass": bool(per) and all(v["pass"] for v in per.values()), "per_block": per}


# ----------------------------------------------------------------------------- estimate (not a rule)

FRAG_PAYLOAD = 247 - 3 - 8           # ATT MTU 247 - ATT header - frag header
CODED_S8_FIXED_US, CODED_S8_US_PER_BYTE = 376.0, 64.0
T_IFS_US = 150.0
EST_CENTRAL_PDU_CAP = 6              # PDUs per event the central allows (week 10: ~5 at 2M/15 ms, 11.6 us/B)
EST_TURNAROUND_EVENTS = 2.0          # ack answer: KV260 processing + next event
EST_STATE_MS = 1500.0                # procedures in D1 (several connection-update instants)
EST_RECONNECT_MS = 9000.0            # disconnect + advertise + BlueZ reconnect + MTU/CCC + base params (5 s timer)
EST_ECHO_BUILD_MS = 2.0              # frame + SHA-256 of the ack inside CTRL (4096 B)


def _pdu_us(phy: int, octets: int) -> float:
    """Air time of one LL data PDU: 1M 8 us/byte, 2M 4 us/byte (preamble, AA, header, CRC), Coded S8 fixed
    part + 64 us/byte."""
    if phy == w11.PHY_CODED_S8:
        return CODED_S8_FIXED_US + (octets + 5) * CODED_S8_US_PER_BYTE
    per = 8.0 if phy == w11.PHY_1M else 4.0
    fixed = 10 if phy == w11.PHY_1M else 11
    return (fixed + octets) * per


def transfer_ms(state: w11.LinkState, frame: int, cap: int) -> float:
    """Time to move one frame: fragments of FRAG_PAYLOAD, each one ATT notify of <= 251 LL octets cut into
    ceil(251 / tx_octets) PDUs; PDUs per event = min(cap, what fits in 90 % of the interval)."""
    notifies = math.ceil(frame / FRAG_PAYLOAD)
    last = frame - (notifies - 1) * FRAG_PAYLOAD
    octets = [min(251, n + 3 + 8 + 4) for n in [FRAG_PAYLOAD] * (notifies - 1) + [last]]
    pdus = sum(math.ceil(o / state.tx_octets) for o in octets)
    pair = _pdu_us(state.phy, state.tx_octets) + T_IFS_US + _pdu_us(state.phy, 0) + T_IFS_US
    fit = max(1, int(0.9 * state.interval_ms * 1000.0 // pair))
    per_event = max(1, min(cap, fit))
    return math.ceil(pdus / per_event) * state.interval_ms


def estimate_op_ms(row, cap: int) -> float:
    st = w11.STATES[row.state]
    gap = 250.0
    if row.op == w11.OP_STATE:
        return EST_STATE_MS + 2000.0
    if row.op == w11.OP_IDLE:
        return float(row.a)
    if row.op == w11.OP_S0C:
        return 0.2 + row.b * 0.15 + gap          # ~0.15 ms per encode (host estimate, MCU unknown)
    if row.op == w11.OP_RECONNECT:
        return EST_RECONNECT_MS + gap
    latency_events = 1 if row.b & w11.ECHO_LATENCY_OFF else st.latency + 1
    wait = EST_TURNAROUND_EVENTS * st.interval_ms * latency_events
    if not row.b & w11.ECHO_ACK:
        wait += transfer_ms(st, row.a, cap)
    else:
        wait += transfer_ms(st, w11.ACK_LENGTH, cap)
    return EST_ECHO_BUILD_MS + transfer_ms(st, row.a, cap) + wait + gap


BOOT_S = 1.0 + 30.0 + 5.0 + 5.0 + 30.0  # self-test, idle radio off, connect (~5 s), settle, connected idle
POST_S = 60.0


def estimate_session(rows: list) -> dict:
    """Seconds of one session under the fast (central allows EST_CENTRAL_PDU_CAP PDUs per event) and slow
    (one PDU per event) airtime models; per block and per op kind."""
    out = {}
    for name, cap in (("fast", EST_CENTRAL_PDU_CAP), ("slow", 1)):
        per_block, per_op = {}, {}
        for r in rows:
            ms = estimate_op_ms(r, cap)
            key = w11.STATES[r.state].name if r.block < len(w11.STATES) else "reconnect"
            per_block[key] = per_block.get(key, 0.0) + ms / 1e3
            per_op[w11.OP_NAMES[r.op]] = per_op.get(w11.OP_NAMES[r.op], 0.0) + ms / 1e3
        plan_s = sum(per_block.values())
        out[name] = {"plan_s": plan_s, "boot_s": BOOT_S, "post_s": POST_S, "total_s": BOOT_S + plan_s + POST_S,
                     "per_block_s": per_block, "per_op_s": per_op}
    return out
