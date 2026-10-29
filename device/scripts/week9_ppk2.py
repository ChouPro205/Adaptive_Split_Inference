#!/usr/bin/env python3
"""Week 9 PPK2 bench driver: part A E_dev(s) for every s with the dev image (W9-D1..D4, B4), part B
the week 8 energy image with the KV260 at s = 2 (W9-D8, B5).

The dongle is powered by the PPK2 Source Meter (5000 mV) through the VBUS breakout, never by the
laptop USB (decision PPK2 VBUS). Capture is measure_energy.py and the week 7 helpers (week7_ppk2.py),
unmodified. energy_phases.py is used for its loaders, self-test and statistics only: its cycle
segmentation needs TX/WAIT markers, while a week 9 cycle is CTRL (D4) -> HEAD (D0) only.

  probe        PPK2 answers? (week7_ppk2.py probe)
  session-dev  dev image: capture (boot, self-test D0..D4, 30 s idle, 550 cycles, sleep) -> analysis/
               (cycles.csv, summary.json), energy_dev.json, check_session.json. Checks:
               TC3  I_idle of the 29 s window after the self-test within 10 % of week 2 (25.417 uA)
               TC4  self-test PASS, no lost sample, exactly 550 valid cycles (one CTRL then one HEAD),
                    every cycle's HEAD width equal to the DWT time of its planned (sample, split)
                    (dev-usb TDEV of week9_lab.py verify) so cycle i is plan row i, D1..D3 LOW from the
                    self-test to power off, radio off between cycles (see the revised rule below),
                    phases vs whole cycle < 3 %
               TC5  per s: E_dev gross/net, t_dev, bytes_payload; CI95/mean < 10 %; mean marker t_dev
                    vs mean DWT within 1 % (or 1 sample = 10 us)
               TC4 radio-off rule revised 29/10 (B4): > 3 mA events between cycles each <= 0.5 ms and at most
                    floor(T / 512 s) + 1 of them (the RTC OVERFLOW wake-up of the kernel timer)
  recheck      the session checks again on an existing directory -> check_session_recheck.json
  note         end-of-session notes (temperature, photos) (week7_ppk2.py note)
  compare      TC6: two session-dev directories (same bench, same day) -> per s mean differences
Part B (W9-D8, TC7): the week 8 energy image at s = 2 with the KV260 as central:
  session-kv260  capture (the KV260 service scans and connects by itself) -> the energy_phases
               analysis steps on a chunked trace (analysis/), trace checks: self-test, 200 cycles in the
               W8-D1 paired order, < 3 %, back to idle and off-air after the session (W8-D2)
  import-kv260 the KV260 request log (week 8 form) + Read-PHY log -> edge/, labels vs the KV260 offline
               run (W8-D8), one cycle per request at two anchors (week 8 B5), one connection, nonce
               above --prior-reserved-through, PHY 2M read back; energy_kv260_s2.json: phases per rho
               and paired P1 - P0 deltas with CI95
  recheck-kv260  the part B checks again with the current checker (new file)
Each session writes a NEW --out directory. Exit 0 = PASS. Run with device/host/.venv; close nRF
Connect Power Profiler first (it holds the PPK2 port).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week6_common as wc  # noqa: E402
import week7_ppk2 as w7p  # noqa: E402
import week9_common as w9  # noqa: E402

FS = ep.SAMPLE_RATE_HZ
DT_MS = 1e3 / FS
CTRL, DEV = ep.DEFAULT_MAP["ctrl"], ep.DEFAULT_MAP["dev"]        # D4, D0
OTHER_MARKERS = (ep.DEFAULT_MAP["prot"], ep.DEFAULT_MAP["tx"], ep.DEFAULT_MAP["wait"])   # D1..D3
WEEK2_IDLE_UA = w7p.WEEK2_IDLE_UA
IDLE_TOLERANCE_PCT = 10.0            # TC3
RADIO_SPIKE_UA = 3000.0              # TC4: radio TX/RX draws several mA; the sleeping CPU stays < 0.5 mA
# TC4 as revised 29/10 after B4 sessions 1-2: Zephyr's nrf_rtc_timer wakes the CPU on the 24-bit RTC
# OVERFLOW interrupt every 2^24 / 32768 Hz = 512 s (two < 0.1 ms bursts); a radio would repeat.
RTC_OVERFLOW_S = 512.0
EVENT_MAX_MS, EVENT_MERGE_MS = 0.5, 1.0
HIGH_LEVEL_UA = 3600.0               # diagnostic: 1 ms HEAD blocks above it = the ~4.4 mA level (B4: REG mode)
GAP_GUARD_MS = 2.0                   # CPU wake-up before CTRL / going to sleep after HEAD (~3 mA, us long)
CI_LIMIT_PCT = 10.0                  # TC5
MEAN_TOLERANCE_PCT, MEAN_FLOOR_US = 1.0, 10.0           # TC5: marker vs DWT, per s
CYCLE_TOLERANCE_PCT, CYCLE_FLOOR_US = 0.5, 30.0         # TC4: one cycle vs its planned (n, s)
POST_OFFSET_S = 2.0
CHUNK_SAMPLES = 4_000_000
SESSION_GAP_MS = 1000                # CONFIG_WEEK9_CYCLE_GAP_MS of the dev image
TOOLS = ("week9_ppk2.py", "week9_common.py", "week8_common.py", "week7_common.py", "week7_ppk2.py",
         "measure_energy.py", "energy_phases.py", "check_week9.py", "week6_common.py")


# ----------------------------------------------------------------------------- loading


class SpikeFilter:
    """energy_phases._spike_filter with its state kept between calls, so a capture converted chunk
    by chunk equals the whole-array conversion bit for bit (test_week9_host.py checks it)."""

    alpha, alpha5, samples_after = 0.18, 0.06, 3

    def __init__(self):
        self.rolling = self.rolling4 = None
        self.prev_range = None
        self.consecutive = 0
        self.after_spike = 0

    def run(self, adc: np.ndarray, ranges: np.ndarray) -> np.ndarray:
        out = adc.copy()
        values, range_list = adc.tolist(), ranges.tolist()
        alpha, alpha5 = self.alpha, self.alpha5
        rolling, rolling4 = self.rolling, self.rolling4
        prev_range, consecutive, after_spike = self.prev_range, self.consecutive, self.after_spike
        for k, value in enumerate(values):
            current_range = range_list[k]
            prev_rolling, prev_rolling4 = rolling, rolling4
            rolling = value if rolling is None else alpha * value + (1 - alpha) * rolling
            rolling4 = value if rolling4 is None else alpha5 * value + (1 - alpha5) * rolling4
            if prev_range is None:
                prev_range = current_range
            if prev_range != current_range or after_spike > 0:
                if prev_range != current_range:
                    consecutive = 0
                    after_spike = self.samples_after
                else:
                    consecutive += 1
                if current_range == 4:
                    if consecutive < 2:
                        rolling, rolling4 = prev_rolling, prev_rolling4
                    out[k] = rolling4
                else:
                    out[k] = rolling
                after_spike -= 1
            prev_range = current_range
        self.rolling, self.rolling4 = rolling, rolling4
        self.prev_range, self.consecutive, self.after_spike = prev_range, consecutive, after_spike
        return out


def _adc(words: np.ndarray, modifiers: dict, vdd_mv: float) -> tuple:
    """energy_phases.convert_words up to the spike filter (same arithmetic and order)."""
    ranges = np.minimum((words >> ep.RANGE_SHIFT) & ep.RANGE_MASK, 4).astype(np.int64)
    adc_value = ((words & ep.ADC_MASK) * 4).astype(np.float64)
    adc = np.empty(words.size, dtype=np.float64)
    for r in range(5):
        key = str(r)
        sel = ranges == r
        if not np.any(sel):
            continue
        rwg = (adc_value[sel] - modifiers["O"][key]) * (ep.ADC_MULT / modifiers["R"][key])
        adc[sel] = modifiers["UG"][key] * (
            rwg * (modifiers["GS"][key] * rwg + modifiers["GI"][key])
            + (modifiers["S"][key] * (vdd_mv / 1000) + modifiers["I"][key]))
    return adc, ranges


def load_raw_chunked(directory: Path, chunk_samples: int = CHUNK_SAMPLES) -> ep.Trace:
    """energy_phases.load_raw_capture (spike filter on) in chunks: the same Trace, a fraction of the
    memory (a 720 s session is ~72 M samples; the whole-array filter needs ~6 GB)."""
    directory = Path(directory)
    meta = json.loads((directory / "capture.json").read_text(encoding="utf-8"))
    raw_path = directory / meta["raw_file"]
    if ep.sha256_file(raw_path) != meta["raw_sha256"]:
        raise ep.InputError("raw.bin SHA-256 differs from capture.json")
    size = raw_path.stat().st_size
    usable = size - size % 4
    words_all = np.memmap(raw_path, dtype="<u4", mode="r", shape=(usable // 4,)) if usable else np.zeros(0, "<u4")
    modifiers = ep.default_modifiers()
    for key, table in meta["modifiers"].items():
        if key in modifiers and isinstance(table, dict):
            modifiers[key].update({k: float(v) for k, v in table.items()})
    vdd = float(meta["v_supply_mV"])
    n = words_all.size
    current = np.empty(n, dtype=np.float64)
    bits = np.empty(n, dtype=np.uint8)
    counter = np.empty(n, dtype=np.uint8)
    range_counts = np.zeros(5, dtype=np.int64)
    spike = SpikeFilter()
    for a in range(0, n, chunk_samples):
        words = np.asarray(words_all[a:a + chunk_samples], dtype=np.uint32)
        adc, ranges = _adc(words, modifiers, vdd)
        current[a:a + words.size] = spike.run(adc, ranges) * 10 ** 6
        bits[a:a + words.size] = ((words >> ep.LOGIC_SHIFT) & 0xFF).astype(np.uint8)
        counter[a:a + words.size] = ((words >> ep.COUNTER_SHIFT) & ep.COUNTER_MASK).astype(np.uint8)
        range_counts += np.bincount(ranges, minlength=5)[:5]
    del words_all
    info = {"format": "measure_energy-raw", "raw_sha256": meta["raw_sha256"],
            "trailing_bytes": size - usable, "counter": ep.counter_check(counter),
            "spike_filter": True, "range_counts": range_counts.tolist(),
            "capture": {k: meta.get(k) for k in ("started_utc", "seconds_requested",
                                                   "dut_power_on_byte", "temp_room_C", "label",
                                                   "status", "dut_on_rate_deviation_pct",
                                                   "reader_error")}}
    if meta.get("dut_power_on_byte") is not None:
        info["dut_power_on_sample"] = int(meta["dut_power_on_byte"]) // 4
    if meta.get("dut_power_off_byte") is not None:
        info["dut_power_off_sample"] = int(meta["dut_power_off_byte"]) // 4
    return ep.Trace(current, bits, vdd, f"raw:{directory}", None, info)


# ----------------------------------------------------------------------------- references


def dwt_reference(verify_dir: Path) -> dict:
    """(sample, split) -> head + quantization ms (dev-usb TDEV ALL, IRQs locked) of a PASS
    week9_lab.py verify directory: the D0 phase the dev image runs without USB."""
    verify_dir = Path(verify_dir)
    report = w7p.load_json(verify_dir / "check_verify.json")
    if report.get("status") != "PASS" or report.get("plan_sha256") != w9.PLAN_SHA256:
        raise SystemExit(f"{verify_dir}: check_verify.json is not a PASS of plan {w9.PLAN_SHA256}")
    out = {}
    for _, text in wc.read_capture(verify_dir / "cdc.log"):
        if text.startswith("TD s=") and "total_cyc=" in text:
            r = wc.kv(text)
            out[(int(r["n"]), int(r["s"]))] = int(r["total_cyc"]) * 1e3 / w9.CPU_HZ
    if sorted(out) != [(n, s) for n in range(w9.ROUNDS) for s in range(w9.SPLITS)]:
        raise SystemExit(f"{verify_dir}: TD lines do not cover 50 samples x 11 splits")
    return out


def expected_session_s(dwt: dict, gap_ms: float = SESSION_GAP_MS, ctrl_us: float = 200.0) -> float:
    """Boot to the end of the last cycle: 0.1 s + self-test 5 x 0.2 s + idle 30 s + cycles."""
    return 0.1 + 1.0 + 30.0 + sum(dwt.values()) / 1e3 + w9.CYCLES * (gap_ms + ctrl_us / 1e3) / 1e3


def image_info(image: Path, receipt: Path | None) -> dict:
    """A build_week9.ps1 folder (static check PASS, variant dev, clean tree, the W9-D4 plan) + its
    flash_week9.ps1 receipt."""
    check = w7p.load_json(Path(image) / "week9_build_check.json")
    source = w7p.load_json(Path(image) / "source.json")
    info = {"image": str(image), "build_id": check.get("build_id"), "variant": check.get("variant"),
            "kernel": check.get("kernel"), "check_status": check.get("status"), "dirty": source.get("dirty"),
            "bin_sha256": check.get("bin_sha256"), "set_sha256": check.get("set_sha256"),
            "plan_sha256": check.get("plan_sha256"), "kconfig": check.get("kconfig"),
            "regulator": check.get("regulator", "board"), "regulator_modes": check.get("regulator_modes")}
    if check.get("status") != "PASS" or check.get("variant") != "dev" or source.get("dirty"):
        raise SystemExit(f"{image}: static check not PASS, not the dev variant, or dirty tree")
    if check.get("plan_sha256") != w9.PLAN_SHA256:
        raise SystemExit(f"{image}: plan {check.get('plan_sha256')} != W9-D4 {w9.PLAN_SHA256}")
    if receipt is not None:
        r = w7p.load_json(receipt)
        info["receipt"] = {"path": str(receipt), "exit_code": r.get("exit_code"), "build_id": r.get("build_id"),
                           "timestamp": r.get("timestamp"), "zip_sha256": r.get("zip_sha256")}
        if r.get("exit_code") != 0 or r.get("build_id") != info["build_id"]:
            raise SystemExit(f"{receipt}: DFU failed or receipt build differs from {image}")
    return info


# ----------------------------------------------------------------------------- analysis


def segment_dev_cycles(trace: ep.Trace, after: int) -> tuple:
    """Cycles after the self-test: each starts at a CTRL rising edge and ends when its HEAD pulse
    falls. Every 10 us sample goes to the phase whose marker is the only one set (W7-D11)."""
    runs = {c: ep.channel_runs(trace.bits, c) for c in (CTRL, DEV, *OTHER_MARKERS)}
    ctrl_s, ctrl_e = runs[CTRL]
    keep = ctrl_s > after
    ctrl_s, ctrl_e = ctrl_s[keep], ctrl_e[keep]
    dev_s, dev_e = runs[DEV]
    v = trace.v_supply_mv / 1000.0
    mask = (1 << CTRL) | (1 << DEV) | sum(1 << c for c in OTHER_MARKERS)
    cycles = []
    for k, start in enumerate(ctrl_s):
        limit = int(ctrl_s[k + 1]) if k + 1 < ctrl_s.size else trace.n
        sel = (dev_s >= start) & (dev_s < limit)
        d_s, d_e = dev_s[sel], dev_e[sel]
        errors = []
        if d_s.size == 0:
            errors.append("missing_dev")
        if d_s.size > 1:
            errors.append("multiple_dev")
        end = int(d_e[0]) if d_s.size else int(ctrl_e[k])
        if d_s.size and d_s[0] < ctrl_e[k]:
            errors.append("phase_order")
        if end >= trace.n or (d_s.size and d_e[0] > limit):
            errors.append("truncated_end")
        for c in OTHER_MARKERS:
            s, _ = runs[c]
            if np.any((s >= start) & (s < limit)):
                errors.append(f"marker_D{c}")
        seg_bits = trace.bits[start:end] & mask
        seg_i = trace.current_ua[start:end]
        row = {"cycle": len(cycles), "start_sample": int(start), "end_sample": int(end),
               "t_cycle_ms": (end - start) * DT_MS, "E_cycle_uJ": v * float(np.sum(seg_i)) * ep.DT_S}
        accounted = 0.0
        for name, channel in (("ctrl", CTRL), ("dev", DEV)):
            only = seg_bits == (1 << channel)
            row[f"t_{name}_ms"] = int(np.count_nonzero(only)) * DT_MS
            row[f"E_{name}_uJ"] = v * float(np.sum(seg_i[only])) * ep.DT_S
            accounted += row[f"E_{name}_uJ"]
        gap = seg_bits == 0
        multi = (seg_bits != 0) & ((seg_bits & (seg_bits - 1)) != 0)
        row["t_gap_ms"] = int(np.count_nonzero(gap)) * DT_MS
        row["E_gap_uJ"] = v * float(np.sum(seg_i[gap])) * ep.DT_S
        row["overlap_samples"] = int(np.count_nonzero(multi))
        if row["overlap_samples"]:
            errors.append("phase_overlap")
        row["E_phases_uJ"] = accounted
        row["diff_pct"] = (100.0 * abs(row["E_cycle_uJ"] - accounted) / row["E_cycle_uJ"]
                           if row["E_cycle_uJ"] > 0 else float("nan"))
        row["mean_dev_uA"] = row["E_dev_uJ"] / v / (row["t_dev_ms"] / 1e3) if row["t_dev_ms"] else float("nan")
        head = seg_i[seg_bits == (1 << DEV)]
        blocks = head[:head.size // 100 * 100].reshape(-1, 100).mean(axis=1) if head.size >= 100 else head
        row["dev_high_fraction"] = float(np.mean(blocks > HIGH_LEVEL_UA)) if blocks.size else float("nan")
        row["errors"] = errors
        cycles.append(row)
    return cycles


def gap_windows(cycles: list, guard: int) -> list:
    """[HEAD end + guard, next CTRL start - guard) between consecutive cycles."""
    out = []
    for a, b in zip(cycles, cycles[1:]):
        lo, hi = a["end_sample"] + guard, b["start_sample"] - guard
        if hi > lo:
            out.append((lo, hi))
    return out


def gap_events(trace: ep.Trace, gaps: list) -> list:
    """Runs of samples above RADIO_SPIKE_UA inside the gap windows, merged when closer than
    EVENT_MERGE_MS: start time (s after DUT ON), duration (first to last sample above) and peak."""
    merge = int(EVENT_MERGE_MS * FS / 1e3)
    events = []
    for lo, hi in gaps:
        above = np.flatnonzero(trace.current_ua[lo:hi] > RADIO_SPIKE_UA)
        if above.size == 0:
            continue
        cuts = np.flatnonzero(np.diff(above) > merge) + 1
        for run in np.split(above, cuts):
            a, b = lo + int(run[0]), lo + int(run[-1]) + 1
            events.append({"t_s": a / FS, "duration_ms": (b - a) * DT_MS,
                           "samples_above": int(run.size), "max_uA": float(np.max(trace.current_ua[a:b]))})
    return events


def analyze_dev(trace: ep.Trace, dwt: dict, bytes_by_split: dict, idle_offset_s: float = 0.5,
                idle_seconds: float = 29.0, ignore_counter: bool = False) -> dict:
    """Self-test, idle window, the 550 cycles mapped to the plan, and energy_dev per split."""
    on = int(trace.info.get("dut_power_on_sample", 0))
    off = int(trace.info.get("dut_power_off_sample", trace.n))
    trace = ep.slice_trace(trace, on, off)     # a pulse cut by DUT power off touches the end
    selftest = ep.selftest_check(trace, ep.DEFAULT_MAP, 200.0)
    after = selftest["end_sample"] if selftest.get("found") else 0
    idle = None
    if selftest.get("found"):
        a = after + int(idle_offset_s * FS)
        b = a + int(idle_seconds * FS)
        if b <= trace.n:
            idle = ep.window_stats(trace, a, b, channels=range(5))
            idle["all_markers_low"] = not any(idle["high_samples"].values())
    i_idle = idle["mean_uA"] if idle else None
    cycles = segment_dev_cycles(trace, after)
    v = trace.v_supply_mv / 1000.0
    plan = w9.plan_rows(w9.plan_splits())
    mapped = len(cycles) == len(plan)
    order_bad = []
    for c, (i, k, n, s) in zip(cycles, plan if mapped else []):
        c.update(round=k, sample=n, split=s, bytes_payload=bytes_by_split[s], dwt_ms=dwt[(n, s)])
        delta_us = (c["t_dev_ms"] - c["dwt_ms"]) * 1e3
        c["t_dev_vs_dwt_us"] = delta_us
        if abs(delta_us) > max(CYCLE_FLOOR_US, CYCLE_TOLERANCE_PCT / 100.0 * c["dwt_ms"] * 1e3):
            order_bad.append(i)
        if i_idle is not None:
            for name in ("ctrl", "dev", "cycle"):
                c[f"E_{name}_net_uJ"] = c[f"E_{name}_uJ"] - v * i_idle * c[f"t_{name}_ms"] / 1e3
    valid = [c for c in cycles if not c["errors"]]
    guard = int(GAP_GUARD_MS * FS / 1e3)
    gaps = gap_windows(cycles, guard)
    gap_max = max((float(np.max(trace.current_ua[lo:hi])) for lo, hi in gaps), default=None)
    gap_spikes = sum(int(np.count_nonzero(trace.current_ua[lo:hi] > RADIO_SPIKE_UA)) for lo, hi in gaps)
    gap_with_spike = sum(1 for lo, hi in gaps if np.any(trace.current_ua[lo:hi] > RADIO_SPIKE_UA))
    events = gap_events(trace, gaps)
    max_events = int(trace.n * ep.DT_S // RTC_OVERFLOW_S) + 1
    radio_off = bool(gaps) and len(events) <= max_events and all(
        e["duration_ms"] <= EVENT_MAX_MS for e in events)
    other_high = {f"D{c}": int(np.count_nonzero((trace.bits[after:] >> c) & 1)) for c in OTHER_MARKERS}
    unused = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in (5, 6, 7)}
    post = None
    if cycles:
        a = cycles[-1]["end_sample"] + int(POST_OFFSET_S * FS)
        if trace.n - a >= 2 * FS:
            p = ep.window_stats(trace, a, trace.n, channels=range(5))
            post = {k: p[k] for k in ("duration_s", "mean_uA", "sample_std_uA", "max_uA", "high_samples")}
            post["samples_above_3mA"] = int(np.count_nonzero(trace.current_ua[a:] > RADIO_SPIKE_UA))
    diffs = [c["diff_pct"] for c in valid]
    loss = ep.data_loss_checks(trace, ignore_counter)
    checks = {
        "selftest_D0_D4": bool(selftest.get("pass")),
        "unused_channels_D5_D7_low": not any(unused.values()),
        **loss,
        "TC3_idle_window_found": idle is not None,
        "TC3_idle_within_10pct_week2": i_idle is not None
                                       and abs(i_idle - WEEK2_IDLE_UA) / WEEK2_IDLE_UA * 100 <= IDLE_TOLERANCE_PCT,
        "TC3_idle_markers_low": bool(idle and idle["all_markers_low"]),
        "TC4_cycle_count_550": len(cycles) == w9.CYCLES,
        "TC4_all_cycles_valid": bool(cycles) and len(valid) == len(cycles),
        "TC4_head_width_matches_plan": mapped and not order_bad,
        "TC4_D1_D3_low_after_selftest": not any(other_high.values()),
        "TC4_radio_off_between_cycles": radio_off,
        "TC4_diff_below_3pct_all": bool(diffs) and len(diffs) == len(cycles) and max(diffs) < ep.DIFF_LIMIT_PCT,
    }
    summary = {
        "schema": "week9-dev-analysis/1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "trace": {"source": trace.source, "samples": trace.n, "duration_s": trace.n * ep.DT_S,
                  "v_supply_mV": trace.v_supply_mv, **trace.info},
        "phase_map": {"ctrl": f"D{CTRL}", "dev": f"D{DEV}"},
        "method": "cycle = CTRL rising edge to HEAD falling edge; per-sample phase assignment, rectangle sum "
                  "E = V*sum(i)*dt (W7-D11); gross = primary, net = gross - V*I_idle*t (W7-D5)",
        "selftest": selftest, "idle": idle, "I_idle_uA": i_idle,
        "idle_vs_week2_pct": (100 * (i_idle - WEEK2_IDLE_UA) / WEEK2_IDLE_UA) if i_idle else None,
        "cycles_found": len(cycles), "cycles_valid": len(valid),
        "errors": {c["cycle"]: c["errors"] for c in cycles if c["errors"]},
        "head_width_rule": f"|t_dev marker - DWT(n, s)| <= max({CYCLE_FLOOR_US} us, {CYCLE_TOLERANCE_PCT} %)",
        "head_width_mismatch_cycles": order_bad[:50],
        "D1_D3_high_samples_after_selftest": other_high, "D5_D7_high_samples": unused,
        "gaps": {"count": len(gaps), "guard_ms": GAP_GUARD_MS, "max_uA": gap_max,
                 "samples_above_3mA": gap_spikes, "gaps_with_samples_above_3mA": gap_with_spike,
                 "events_above_3mA": events, "max_events": max_events,
                 "radio_off_rule": f"every > 3 mA event <= {EVENT_MAX_MS} ms and at most floor(T / "
                                   f"{RTC_OVERFLOW_S:.0f} s) + 1 events (Zephyr RTC OVERFLOW wake-up, "
                                   "nrf_rtc_timer.c; a radio repeats every 15-100 ms for ms each)"},
        "dev_high_fraction_by_fifth": [float(np.nanmean([c["dev_high_fraction"] for c in cycles[a:a + len(cycles) // 5]]))
                                       for a in range(0, 5 * (len(cycles) // 5), max(1, len(cycles) // 5))],
        "post_session": post,
        "diff_pct": ep.describe(diffs),
        "spacing_ms": ep.describe(np.diff([c["start_sample"] for c in cycles]) * DT_MS) if len(cycles) > 1 else None,
    }
    return {"summary": summary, "cycles": cycles, "energy_dev": energy_dev_table(cycles if mapped else [],
                                                                                 dwt, i_idle, trace.v_supply_mv)}


def energy_dev_table(cycles: list, dwt: dict, i_idle: float | None, v_supply_mv: float) -> dict:
    """TC5: per split, statistics of the valid cycles of that split (W9-D2)."""
    rows, ci_ok, dwt_ok, n_ok = [], [], [], []
    for s in range(w9.SPLITS):
        group = [c for c in cycles if c.get("split") == s and not c["errors"]]
        e = ep.describe(c["E_dev_uJ"] for c in group)
        t = ep.describe(c["t_dev_ms"] for c in group)
        ref = [dwt[(c["sample"], s)] for c in group]
        dwt_mean = float(np.mean(ref)) if ref else None
        delta_ms = (t["mean"] - dwt_mean) if group else None
        within = (delta_ms is not None and (abs(delta_ms) * 1e3 <= MEAN_FLOOR_US
                                            or abs(delta_ms) / dwt_mean * 100 <= MEAN_TOLERANCE_PCT))
        row = {"split": s, "n": len(group), "bytes_payload": group[0]["bytes_payload"] if group else None,
               "E_dev_uJ": e, "t_dev_ms": t,
               "E_dev_net_uJ": ep.describe(c["E_dev_net_uJ"] for c in group if "E_dev_net_uJ" in c),
               "E_ctrl_uJ": ep.describe(c["E_ctrl_uJ"] for c in group),
               "E_cycle_uJ": ep.describe(c["E_cycle_uJ"] for c in group),
               "mean_dev_uA": ep.describe(c["mean_dev_uA"] for c in group),
               "dev_high_fraction": ep.describe(c["dev_high_fraction"] for c in group),
               "dwt_t_dev_ms": dwt_mean, "t_dev_marker_minus_dwt_us": delta_ms * 1e3 if delta_ms is not None else None,
               "t_dev_marker_vs_dwt_pct": 100 * delta_ms / dwt_mean if delta_ms is not None else None,
               "t_dev_within_rule": within}
        rows.append(row)
        n_ok.append(len(group) == w9.ROUNDS)
        ci_ok.append(e.get("ci95_rel_pct") is not None and e["ci95_rel_pct"] < CI_LIMIT_PCT)
        dwt_ok.append(within)
    checks = {"TC5_n_50_per_split": all(n_ok) and bool(cycles),
              "TC5_ci95_below_10pct_all_splits": all(ci_ok) and bool(cycles),
              "TC5_t_dev_marker_vs_dwt_within_1pct": all(dwt_ok) and bool(cycles)}
    return {"schema": "week9-energy-dev/1", "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "definition": "E_dev_uJ = energy at the 5 V input while only D0 (HEAD: head(s) + INT8/FP16 quantization) "
                          "is HIGH, radio off (W9-D1, W9-D2); gross primary, net = gross - V*I_idle*t_dev (W7-D5); "
                          "CI95 = Student-t, n-1 dof; bytes_payload = int8 + FP16 scale bytes",
            "v_supply_mV": v_supply_mv, "I_idle_uA": i_idle,
            "rules": {"ci95_rel_pct_below": CI_LIMIT_PCT,
                      "t_dev_marker_vs_dwt": f"<= {MEAN_TOLERANCE_PCT} % or <= {MEAN_FLOOR_US} us"},
            "plan_sha256": w9.PLAN_SHA256, "set_sha256": w9.w8.SET_SHA256, "splits": rows}


CYCLE_COLUMNS = ["cycle", "round", "sample", "split", "bytes_payload", "start_sample", "end_sample", "t_cycle_ms",
                 "t_ctrl_ms", "t_dev_ms", "t_gap_ms", "dwt_ms", "t_dev_vs_dwt_us", "E_cycle_uJ", "E_ctrl_uJ",
                 "E_dev_uJ", "E_gap_uJ", "E_phases_uJ", "diff_pct", "mean_dev_uA", "E_cycle_net_uJ",
                 "E_ctrl_net_uJ", "E_dev_net_uJ", "dev_high_fraction", "overlap_samples", "errors"]


def write_outputs(out: Path, result: dict) -> None:
    analysis = ep.new_output_dir(out / "analysis")
    with open(analysis / "cycles.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CYCLE_COLUMNS)
        for row in result["cycles"]:
            writer.writerow([";".join(row["errors"]) if col == "errors" else
                             (f"{row[col]:.6f}" if isinstance(row.get(col), float) else row.get(col, ""))
                             for col in CYCLE_COLUMNS])
    (analysis / "summary.json").write_text(json.dumps(result["summary"], indent=2) + "\n", encoding="utf-8")


def finish(out: Path, kind: str, checks: dict, details: dict) -> int:
    status = "PASS" if checks and all(checks.values()) else "FAIL"
    w7p.write_new_json(out / f"check_{kind}.json", {"schema": f"week9-ppk2-{kind}/1", "status": status,
                                                   "checks": checks, **details})
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT {kind}: {status} -> {out}")
    return 0 if status == "PASS" else 1


def evaluate(out: Path, record: dict, meta: dict, kind: str, energy_name: str) -> int:
    """Analysis + checks of a session directory (capture, references named in session.json)."""
    sample_set = w9.w8.load_set(Path(record["samples"]))
    refs = w9.load_refs(Path(record["refs"]), sample_set)
    dwt = dwt_reference(Path(record["dwt_verify"]))
    bytes_by_split = {s: refs[(0, s)].bytes_payload for s in range(w9.SPLITS)}
    trace = load_raw_chunked(out / "ppk2")
    result = analyze_dev(trace, dwt, bytes_by_split, ignore_counter=record.get("ignore_counter", False))
    if kind == "session":
        write_outputs(out, result)
    summary, energy = result["summary"], result["energy_dev"]
    energy.update(session=str(out), image=record.get("image"), temp_room_C=record.get("temp_room_C"),
                  capture_raw_sha256=meta.get("raw_sha256"), dwt_verify=record["dwt_verify"],
                  tool_sha256={n: w7p.sha256(HERE / n) for n in TOOLS if (HERE / n).exists()})
    w7p.write_new_json(out / energy_name, energy)
    checks = {"capture_pass": meta.get("status") == "PASS", **summary["checks"], **energy["checks"]}
    s = summary
    if not s["selftest"].get("found") and s["cycles_found"] == 0:
        print("NOTE: no self-test found. Ten 5 ms CTRL pulses = the image refused its plan (digest "
              "mismatch): rebuild with build_week9.ps1 and the W9-D4 plan.")
    if s["I_idle_uA"] is not None:
        print(f"I_idle {s['I_idle_uA']:.3f} uA ({s['idle_vs_week2_pct']:+.2f} % vs week 2); gaps max "
              f"{s['gaps']['max_uA']} uA, >3 mA samples {s['gaps']['samples_above_3mA']}")
    for row in energy["splits"]:
        e = row["E_dev_uJ"]
        if e.get("n"):
            print(f"s={row['split']:2d} n={row['n']} E_dev {e['mean']:.2f} uJ (CI95 {e.get('ci95_rel_pct', 0):.3f} %) "
                  f"t_dev {row['t_dev_ms']['mean']:.4f} ms vs DWT {row['dwt_t_dev_ms']:.4f} "
                  f"({row['t_dev_marker_minus_dwt_us']:+.1f} us) bytes {row['bytes_payload']}")
    details = {"analysis_status": s["status"], "energy_dev_status": energy["status"],
               "I_idle_uA": s["I_idle_uA"], "idle_vs_week2_pct": s["idle_vs_week2_pct"],
               "cycles_found": s["cycles_found"], "errors": s["errors"],
               "head_width_mismatch_cycles": s["head_width_mismatch_cycles"],
               "D1_D3_high_samples_after_selftest": s["D1_D3_high_samples_after_selftest"],
               "gaps": s["gaps"], "post_session": s["post_session"], "diff_pct": s["diff_pct"],
               "capture": {k: meta.get(k) for k in ("samples", "dut_on_rate_deviation_pct", "raw_sha256",
                                                    "host_max_gap_between_reads_s", "status")},
               "checker_sha256": {n: w7p.sha256(HERE / n) for n in ("week9_ppk2.py", "energy_phases.py")}}
    return finish(out, kind, checks, details)


# ----------------------------------------------------------------------------- commands


def cmd_session_dev(args) -> int:
    sample_set = w9.w8.load_set(args.samples)       # authenticate everything before powering the DUT
    w9.load_refs(args.refs, sample_set)
    dwt = dwt_reference(args.dwt_verify)
    image = image_info(args.image, args.receipt)
    need = expected_session_s(dwt)
    if args.seconds < need + 20.0:
        raise SystemExit(f"--seconds {args.seconds} < expected session {need:.0f} s + 20 s")
    out = w7p.new_out(args.out)
    record = {
        "schema": "week9-ppk2-session/1", "kind": "session-dev", "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(), "temp_room_C": args.temp_c,
        "v_supply_mV": 5000, "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "image": image, "samples": str(args.samples), "refs": str(args.refs), "dwt_verify": str(args.dwt_verify),
        "plan_sha256": w9.PLAN_SHA256, "expected_session_s": need, "seconds": args.seconds,
        "ignore_counter": bool(args.ignore_counter), "note": args.note,
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS if (HERE / n).exists()},
        "photos": "add with: week9_ppk2.py note --out <this dir> --photo <file> --temp-end-c <t>",
    }
    w7p.write_new_json(out / "session.json", record)
    print(f"session ~{need:.0f} s of {args.seconds:.0f} s DUT ON; do not touch the bench")
    meta = w7p.run_capture(args, out, "B4-week9-dev-session", args.seconds)
    return evaluate(out, record, meta, "session", "energy_dev.json")


def cmd_recheck(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != "week9-ppk2-session/1":
        raise SystemExit(f"{out} is not a week 9 session-dev directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return evaluate(out, record, w7p.load_json(out / "ppk2" / "capture.json"), "session_recheck",
                    f"energy_dev_recheck-{stamp}.json")


def cmd_compare(args) -> int:
    """TC6: per split, mean E_dev / t_dev of session b vs session a (report; < 10 % is week 13)."""
    a, b = (w7p.load_json(Path(d) / "energy_dev.json") for d in (args.a, args.b))
    rows = []
    for ra, rb in zip(a["splits"], b["splits"]):
        row = {"split": ra["split"]}
        for key in ("E_dev_uJ", "E_dev_net_uJ", "t_dev_ms", "E_cycle_uJ"):
            ma, mb = ra[key].get("mean"), rb[key].get("mean")
            row[key] = {"a": ma, "b": mb, "delta_pct": 100 * (mb - ma) / ma if ma and mb is not None else None}
        rows.append(row)
    deltas = [abs(r["E_dev_uJ"]["delta_pct"]) for r in rows if r["E_dev_uJ"]["delta_pct"] is not None]
    report = {"schema": "week9-compare/1", "a": str(args.a), "b": str(args.b),
              "status": {"a": a.get("status"), "b": b.get("status")},
              "temp_room_C": {"a": a.get("temp_room_C"), "b": b.get("temp_room_C")},
              "I_idle_uA": {"a": a.get("I_idle_uA"), "b": b.get("I_idle_uA")},
              "max_abs_E_dev_delta_pct": max(deltas) if deltas else None, "splits": rows,
              "scope": "TC6 week 9: reported only; the < 10 % day-to-day criterion is week 13"}
    w7p.write_new_json(Path(args.output), report)
    for r in rows:
        print(f"s={r['split']:2d} E_dev {r['E_dev_uJ']['a']} -> {r['E_dev_uJ']['b']} ({r['E_dev_uJ']['delta_pct']})")
    print(f"max |delta E_dev| = {report['max_abs_E_dev_delta_pct']} % -> {args.output}")
    return 0


# ----------------------------------------------------------------------------- part B: KV260, s = 2 (W9-D8)

KV260_PAIRS = 100                    # CONFIG_WEEK8_PAIRS of the week 8 energy image
PHY_2M = {"2", "2M", "LE2M", "LE_2M", "LE 2M", "PHY_2M", "0X02"}
PHY_KEYS = (("tx_phy", "rx_phy"), ("phy_tx", "phy_rx"), ("tx", "rx"))
PHASE_KEYS = ("ctrl", "dev", "prot", "tx", "wait", "gap", "cycle")


def analyze_energy_image(trace: ep.Trace, out: Path, pairs: int, ignore_counter: bool) -> dict:
    """energy_phases.py analyze (the week 7/8 steps: self-test, 29 s idle window, cycles, net, groups)
    on a trace loaded in chunks; writes analysis/cycles.csv + summary.json like it (no plot)."""
    phase_map = dict(ep.DEFAULT_MAP)
    analysis = ep.new_output_dir(out / "analysis")
    selftest = ep.selftest_check(trace, phase_map, 200.0)
    after = selftest["end_sample"] if selftest.get("found") else 0
    idle = None
    if selftest.get("found"):
        a = after + int(0.5 * FS)
        idle = ep.window_stats(trace, a, a + int(29.0 * FS), channels=sorted(phase_map.values()))
        idle["all_markers_low"] = not any(idle["high_samples"].values())
    cycles, anomalies = ep.segment_cycles(trace, phase_map, after_sample=after + 1)
    i_idle = idle["mean_uA"] if idle else None
    if i_idle is not None:
        ep.add_net(cycles, i_idle, trace.v_supply_mv)
    valid = [c for c in cycles if not c["errors"]]
    diffs = [c["diff_pct"] for c in valid]
    stray = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in range(8) if c not in phase_map.values()}
    checks = {
        "selftest_D0_D4": bool(selftest.get("pass")),
        "cycle_count": len(cycles) == 2 * pairs,
        "all_cycles_valid": len(valid) == len(cycles) and bool(cycles),
        "diff_below_3pct_all": bool(diffs) and max(diffs) < ep.DIFF_LIMIT_PCT and len(diffs) == len(cycles),
        "unused_channels_low": not any(stray.values()),
        **ep.data_loss_checks(trace, ignore_counter),
        "p1_cycles": sum(c["rho"] == "P1" for c in valid) == pairs,
        "p0_cycles": sum(c["rho"] == "P0" for c in valid) == pairs,
        "idle_markers_low": bool(idle and idle["all_markers_low"]),
    }
    gaps = [(c["end_sample"], cycles[i + 1]["start_sample"]) for i, c in enumerate(cycles[:-1])]
    summary = {
        "schema": "week7-energy-analysis/1", "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks, "producer": "week9_ppk2.py analyze_energy_image (energy_phases steps, chunked loader)",
        "trace": {"source": trace.source, "samples": trace.n, "duration_s": trace.n * ep.DT_S,
                  "v_supply_mV": trace.v_supply_mv, **trace.info},
        "phase_map": {k: f"D{v}" for k, v in phase_map.items()},
        "selftest": selftest, "idle": idle, "I_idle_uA": i_idle,
        "cycles_found": len(cycles), "cycles_valid": len(valid), "diff_pct": ep.describe(diffs),
        "anomalies": anomalies, "unused_channel_high_samples": stray,
        "errors": {i: c["errors"] for i, c in enumerate(cycles) if c["errors"]},
        "conn_interval_diagnostic": (ep.estimate_conn_interval_ms(trace, *max(gaps, key=lambda g: g[1] - g[0]))
                                     if gaps else None),
        "groups": ep.summarize_cycles(cycles), "tools": ep.tool_hashes(),
    }
    ep.write_cycles_csv(analysis / "cycles.csv", cycles)
    (analysis / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def post_session_events(trace: ep.Trace, cycles: list, i_idle: float | None) -> dict:
    """W8-D2 (TC6 of week 8) with the revised radio rule: from 2 s after the last cycle to DUT power
    off, the mean is back at the idle current and > 3 mA events are only RTC-overflow-like bursts."""
    if not cycles:
        return {"found": False}
    start = int(cycles[-1]["end_sample"]) + int(POST_OFFSET_S * FS)
    stop = int(trace.info.get("dut_power_off_sample", trace.n))
    if stop - start < 2 * FS:
        return {"found": False, "duration_s": (stop - start) / FS}
    stats = ep.window_stats(trace, start, stop, channels=range(5))
    events = gap_events(trace, [(start, stop)])
    out = {"found": True, "duration_s": stats["duration_s"], "mean_uA": stats["mean_uA"],
           "max_uA": stats["max_uA"], "high_samples": stats["high_samples"], "events_above_3mA": events,
           "radio_off": len(events) <= 1 and all(e["duration_ms"] <= EVENT_MAX_MS for e in events),
           "I_idle_uA": i_idle}
    if i_idle:
        out["deviation_from_idle_pct"] = abs(stats["mean_uA"] - i_idle) / i_idle * 100.0
    return out


def phy_records(path: Path) -> list:
    """Read-PHY results of the KV260 log: JSON lines with (tx_phy, rx_phy) or the like, or text lines
    'TX PHY: LE 2M ... RX PHY: LE 2M'. Returns [(line, tx, rx)] with the PHY names upper-cased."""
    import re
    out = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        tx = rx = None
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if isinstance(event, dict):
            for a, b in PHY_KEYS:
                if a in event and b in event:
                    tx, rx = str(event[a]).upper(), str(event[b]).upper()
                    break
        else:
            m_tx = re.search(r"TX[ _]?PHY\W+([A-Z0-9 _]+?)(?:[,;)]|\s{2}|RX|$)", line, re.I)
            m_rx = re.search(r"RX[ _]?PHY\W+([A-Z0-9 _]+?)(?:[,;)]|\s{2}|$)", line, re.I)
            if m_tx and m_rx:
                tx, rx = m_tx.group(1).strip().upper(), m_rx.group(1).strip().upper()
        if tx is not None:
            out.append((number, tx, rx))
    return out


def paired_deltas(cycles: list) -> dict:
    """W8-D1 pairs (cycles 2k, 2k + 1, one P1 and one P0, same sample): P1 - P0 per phase."""
    out = {}
    pairs = [(cycles[2 * k], cycles[2 * k + 1]) for k in range(len(cycles) // 2)]
    for name in PHASE_KEYS:
        for prefix, unit in (("E", "uJ"), ("t", "ms")):
            key = f"{prefix}_{name}_{unit}"
            if not cycles or key not in cycles[0]:
                continue
            values = []
            for a, b in pairs:
                p1, p0 = (a, b) if a["rho"] == "P1" else (b, a)
                if p1["rho"] == "P1" and p0["rho"] == "P0" and p1.get(key) not in ("", None):
                    values.append(float(p1[key]) - float(p0[key]))
            out[key] = ep.describe(values)
    return out


def kv260_records(out: Path) -> tuple:
    edge = out / "edge"
    records = [json.loads(line) for line in (edge / "peer.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    return records, w7p.load_json(edge / "summary.json")


def evaluate_kv260(out: Path, record: dict, meta: dict, kind: str) -> int:
    """Part B checks: the trace (capture, self-test, 200 paired cycles, < 3 %, back to idle and
    off-air after the session) and, once the KV260 log is imported, the labels, the cycle <-> request
    match at two anchors (week 8 B5), one connection, the nonce, PHY 2M; phase table + paired deltas."""
    import week8_ppk2 as w8p
    summary = w7p.load_json(out / "analysis" / "summary.json")
    cycles = w7p.cycle_rows(out / "analysis")
    trace = load_raw_chunked(out / "ppk2")
    post = post_session_events(trace, cycles, summary.get("I_idle_uA"))
    a = summary["checks"]
    plan_rho = ["P1" if (k + slot) % 2 == 0 else "P0" for k in range(KV260_PAIRS) for slot in range(2)]
    checks = {
        "capture_pass": meta.get("status") == "PASS",
        "selftest_D0_D4": a.get("selftest_D0_D4", False),
        "unused_channels_low": a.get("unused_channels_low", False),
        "no_data_loss": a.get("no_data_loss", record.get("ignore_counter", False)) and a.get("sample_rate_ok", False),
        "cycle_count_200": a.get("cycle_count", False),
        "p1_100_p0_100": a.get("p1_cycles", False) and a.get("p0_cycles", False),
        "trace_rho_order_paired": [c.get("rho") for c in cycles] == plan_rho,
        "all_cycles_valid": a.get("all_cycles_valid", False),
        "idle_markers_low": a.get("idle_markers_low", False),
        "diff_below_3pct_all": a.get("diff_below_3pct_all", False),
        "post_window_at_least_20s": post.get("found", False) and post["duration_s"] >= 20.0,
        "post_mean_at_idle": post.get("deviation_from_idle_pct", float("inf")) <= IDLE_TOLERANCE_PCT,
        "post_radio_off": post.get("found", False) and post["radio_off"],
    }
    details = {"I_idle_uA": summary.get("I_idle_uA"), "post_session": post,
               "conn_interval_estimate_ms": (summary.get("conn_interval_diagnostic") or {}).get("median_spacing_ms"),
               "diff_pct": summary.get("diff_pct"), "kv260_log": "PENDING: week9_ppk2.py import-kv260"}
    energy = None
    if (out / "edge" / "summary.json").exists():
        records, edge = kv260_records(out)
        match = w8p.match_cycles(cycles, records)
        p1_seq = [r["sequence"] for r in records if r.get("rho") == "P1" and r.get("sequence") is not None]
        connections = {r.get("connection") for r in records if "connection" in r}
        phy = edge.get("phy_records") or []
        checks.update({
            "kv260_log_pass_labels_100_per_rho": edge.get("status") == "PASS",
            "kv260_answered_all": (edge.get("counters") or {}).get("response_sent") == 2 * KV260_PAIRS,
            "one_cycle_per_request": match["pass"],
            "nonce_above_prior_and_increasing": bool(p1_seq) and p1_seq[0] > record["prior_reserved_through"]
                                                and all(b > a for a, b in zip(p1_seq, p1_seq[1:])),
            "single_connection": len(connections) == 1 if connections else edge.get("connections") == 1,
            "phy_2m_read_back": bool(phy) and all(tx in PHY_2M and rx in PHY_2M for _, tx, rx in phy),
        })
        details.update(kv260_log=edge.get("source_log"), labels_equal_reference=edge.get("labels_equal_reference"),
                       interval_match=match, first_p1_sequence=p1_seq[0] if p1_seq else None,
                       last_p1_sequence=p1_seq[-1] if p1_seq else None, connections=sorted(map(str, connections)),
                       phy_records=phy)
        energy = {"schema": "week9-energy-kv260-s2/1", "decision": "W9-D8", "split": 2, "session": str(out),
                  "image": record.get("image"), "temp_room_C": record.get("temp_room_C"),
                  "v_supply_mV": trace.v_supply_mv, "I_idle_uA": summary.get("I_idle_uA"),
                  "per_rho": {rho: g["stats"] for rho, g in summary.get("groups", {}).items()},
                  "paired_delta_p1_minus_p0": paired_deltas(cycles),
                  "definition": "gross energy at the 5 V input per marker phase (W7-D11), net = gross - V*I_idle*t "
                                "(W7-D5); paired delta = P1 - P0 of the two cycles of each W8-D1 pair (same sample)"}
    status = "PASS" if all(checks.values()) else "FAIL"
    if energy is not None:
        energy["status"] = status
        w7p.write_new_json(out / ("energy_kv260_s2.json" if kind == "kv260" else
                                  f"energy_kv260_s2_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"), energy)
        for rho, stats in energy["per_rho"].items():
            print(f"{rho}: " + ", ".join(f"{k} {stats[k]['mean']:.1f}" for k in
                                         ("E_dev_uJ", "E_prot_uJ", "E_tx_uJ", "E_wait_uJ", "E_cycle_uJ") if k in stats))
    if post.get("found"):
        print(f"post-session {post['duration_s']:.1f} s: mean {post['mean_uA']:.3f} uA vs idle "
              f"{post.get('I_idle_uA')} uA, events {len(post['events_above_3mA'])}")
    return finish(out, kind, checks, details)


def cmd_session_kv260(args) -> int:
    import week8_ppk2 as w8p
    sample_set = w9.w8.load_set(args.samples)
    image = w8p.image_info(args.image, args.receipt, False)      # PASS, energy, clean, 100 pairs
    out = w7p.new_out(args.out)
    record = {
        "schema": "week9-ppk2-kv260/1", "kind": "session-kv260", "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(), "temp_room_C": args.temp_c,
        "v_supply_mV": 5000, "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "image": image, "samples": str(args.samples), "set_sha256": sample_set.set_sha256,
        "prior_reserved_through": args.prior_reserved_through, "pairs": KV260_PAIRS, "seconds": args.seconds,
        "peer": "KV260 (W9-D8): scans and connects by itself, Set PHY 2M + Read PHY per connection; its "
                "request log is imported afterwards (import-kv260)",
        "ignore_counter": bool(args.ignore_counter), "note": args.note,
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS + ("week8_ppk2.py", "week8_lab.py", "week8_edge.py")
                        if (HERE / n).exists()},
    }
    w7p.write_new_json(out / "session.json", record)
    print("KV260 service must already be scanning for ASI-SV1 (it connects when the dongle advertises, "
          "~31 s after power-on); do not touch the bench")
    meta = w7p.run_capture(args, out, "B5-week9-kv260-session", args.seconds)
    analyze_energy_image(load_raw_chunked(out / "ppk2"), out, KV260_PAIRS, args.ignore_counter)
    return evaluate_kv260(out, record, meta, "session")


def cmd_import_kv260(args) -> int:
    import shutil
    import week8_edge as edge_mod
    import week8_lab as w8lab
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != "week9-ppk2-kv260/1":
        raise SystemExit(f"{out} is not a week 9 session-kv260 directory")
    sample_set = w9.w8.load_set(Path(record["samples"]))
    edge_ref = w9.w8.load_edge_reference(args.edge_reference, sample_set) if args.edge_reference else None
    edge = out / "edge"
    edge.mkdir(exist_ok=False)
    raw = edge / "kv260_requests_raw.jsonl"
    shutil.copyfile(args.kv260_log, raw)
    lines = raw.read_text(encoding="utf-8").splitlines()
    records, counters = w8lab.normalize_peer_log(lines, sample_set)
    for r, line in zip(records, [json.loads(x) for x in lines if x.strip() and json.loads(x).get("ev") == "request"]):
        if "connection" in line:
            r["connection"] = line["connection"]
    with open(edge / "peer.jsonl", "x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r) + "\n")
    result = edge_mod.evaluate(records, counters, sample_set, 0, KV260_PAIRS, None,
                               edge_ref.labels if edge_ref else None)
    phy = []
    if args.phy_log:
        shutil.copyfile(args.phy_log, edge / ("kv260_phy" + Path(args.phy_log).suffix))
        phy = phy_records(args.phy_log)
    connections = sum(1 for x in lines if x.strip() and json.loads(x).get("ev") in ("connected", "connection"))
    w7p.write_new_json(edge / "summary.json", {
        "schema": "week9-kv260-import/1", "source_log": str(args.kv260_log),
        "source_log_sha256": w7p.sha256(raw), "phy_log": str(args.phy_log) if args.phy_log else None,
        "phy_log_sha256": w7p.sha256(args.phy_log) if args.phy_log else None, "phy_records": phy,
        "connections": connections or None, "imported_utc": datetime.now(timezone.utc).isoformat(),
        "counters": counters, "set_sha256": sample_set.set_sha256, "field_spec": w8lab.PEER_LOG_FIELDS,
        "label_reference": {"path": edge_ref.path, "sha256": edge_ref.sha256} if edge_ref else "W8-D4", **result})
    print(f"KV260 log: {len(records)} requests {counters}; labels {result['labels_equal_reference']}; "
          f"PHY records {len(phy)}")
    return evaluate_kv260(out, record, w7p.load_json(out / "ppk2" / "capture.json"), "kv260")


def cmd_recheck_kv260(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != "week9-ppk2-kv260/1":
        raise SystemExit(f"{out} is not a week 9 session-kv260 directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return evaluate_kv260(out, record, w7p.load_json(out / "ppk2" / "capture.json"), f"kv260_recheck-{stamp}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--port")
    p.add_argument("--stream-s", type=float, default=2.0)
    p.set_defaults(func=w7p.cmd_probe)

    p = sub.add_parser("session-dev")
    p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--seconds", type=float, default=750.0, help="DUT power ON time (session ~716 s + idle after)")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week9.ps1 folder (dev)")
    p.add_argument("--receipt", type=Path, required=True, help="DFU receipt JSON of flash_week9.ps1")
    p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    p.add_argument("--refs", type=Path, required=True, help="generate_week9_refs.py directory")
    p.add_argument("--dwt-verify", type=Path, required=True, help="PASS week9_lab.py verify directory (TDEV)")
    p.add_argument("--note", default="", help="e.g. bench, wiring, session number of the day")
    p.add_argument("--ignore-counter", action="store_true",
                   help="only after A1 showed bits 18-23 are not a sample counter")
    p.set_defaults(func=cmd_session_dev)

    p = sub.add_parser("recheck")
    p.add_argument("--out", type=Path, required=True, help="existing session-dev directory")
    p.set_defaults(func=cmd_recheck)

    p = sub.add_parser("note")
    p.add_argument("--out", type=Path, required=True, help="existing session directory")
    p.add_argument("--temp-end-c", type=float)
    p.add_argument("--photo", type=Path, action="append", default=[])
    p.add_argument("--text", default="")
    p.set_defaults(func=w7p.cmd_note)

    p = sub.add_parser("compare")
    p.add_argument("--a", type=Path, required=True, help="first session-dev directory")
    p.add_argument("--b", type=Path, required=True, help="second session-dev directory")
    p.add_argument("--output", type=Path, required=True, help="new JSON file")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("session-kv260")
    p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--seconds", type=float, default=420.0,
                   help="DUT power ON time: ~31 s boot/idle + link + 35 s + 200 cycles (~250 s) + >= 60 s after")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week8.ps1 folder (energy, clean)")
    p.add_argument("--receipt", type=Path, required=True, help="DFU receipt JSON of flash_week8.ps1")
    p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    p.add_argument("--prior-reserved-through", type=int, required=True,
                   help="largest NONCE reserved_through seen before this boot")
    p.add_argument("--note", default="", help="e.g. KV260 distance, service commit")
    p.add_argument("--ignore-counter", action="store_true")
    p.set_defaults(func=cmd_session_kv260)

    p = sub.add_parser("import-kv260")
    p.add_argument("--out", type=Path, required=True, help="the session-kv260 directory")
    p.add_argument("--kv260-log", type=Path, required=True, help="KV260 request log (JSON lines, week 8 form)")
    p.add_argument("--edge-reference", type=Path, help="KV260 offline predictions.jsonl of the 100 samples (W8-D8)")
    p.add_argument("--phy-log", type=Path, help="KV260 Read PHY log of the session's connection")
    p.set_defaults(func=cmd_import_kv260)

    p = sub.add_parser("recheck-kv260")
    p.add_argument("--out", type=Path, required=True, help="existing session-kv260 directory")
    p.set_defaults(func=cmd_recheck_kv260)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
