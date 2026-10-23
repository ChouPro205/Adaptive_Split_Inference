#!/usr/bin/env python3
"""Phase-energy analysis of PPK2 traces with GPIO markers (week 7 onward; no device I/O).

Inputs: a raw capture directory written by measure_energy.py (raw.bin + capture.json) or a CSV
exported by nRF Connect Power Profiler (Timestamp(ms),Current(uA),D0..D7, the week 2 format).

Model (decision W7-D11): every 10 us sample belongs to the phase whose marker bit is the only
one set in that same sample; E_phase = v_supply * sum(i_k) * dt (rectangle sum). A cycle runs
from the rising edge of CTRL to the falling edge of its last phase marker, so
E_cycle = sum(E_phase) + E_gap (samples with no marker) + E_overlap (more than one marker).
The 3 % criterion (TC6) therefore measures the energy that no marker accounts for.

Names (decision W7-D1): E_ctrl_uJ, E_dev_uJ, E_prot_uJ, E_tx_uJ, E_wait_uJ, E_cycle_uJ, E_gap_uJ,
t_*_ms, I_idle_uA, v_supply_mV. Marker channels default to D0 dev (HEAD), D1 prot (PROTECTION),
D2 tx, D3 wait, D4 ctrl.

Subcommands:
  idle     statistics of a window (week 2 reproduction: mean, std, charge, logic all LOW)
  markers  high pulses per digital channel (marker wiring/order checks, TC1)
  analyze  self-test, idle window and cycle table of a week 7 session (TC1, TC5, TC6)
Exit code 0 = PASS, 1 = FAIL of a check, 2 = unusable input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SAMPLE_RATE_HZ = 100_000
DT_S = 1.0 / SAMPLE_RATE_HZ
PHASES = ("ctrl", "dev", "prot", "tx", "wait")
DEFAULT_MAP = {"dev": 0, "prot": 1, "tx": 2, "wait": 3, "ctrl": 4}
OPTIONAL_PHASES = {"prot"}          # rho = P0 has no protect phase
SELFTEST_ORDER = ("dev", "prot", "tx", "wait", "ctrl")   # firmware week7: D0..D4, 200 ms each
DIFF_LIMIT_PCT = 3.0

# ppk2-api 0.9.2 raw word layout (ppk2_api.py: MEAS_ADC, MEAS_RANGE, MEAS_LOGIC) plus the
# 6-bit sample counter at bits 18..23 that nRF Connect Power Profiler uses for data-loss
# detection (ppk2-api ignores it). Checked against real data in session A (step 2.5).
ADC_MASK, RANGE_SHIFT, RANGE_MASK = 0x3FFF, 14, 0x7
COUNTER_SHIFT, COUNTER_MASK = 18, 0x3F
LOGIC_SHIFT = 24
ADC_MULT = 1.8 / 163840


class InputError(Exception):
    """Trace cannot be used (format, units, missing samples)."""


@dataclass
class Trace:
    current_ua: np.ndarray            # float64, one value per sample
    bits: np.ndarray                  # uint8, digital channels D0..D7 (bit n = Dn)
    v_supply_mv: float
    source: str
    time_ms: np.ndarray | None = None  # only for CSV input (week 2 trapezoid reproduction)
    info: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return int(self.current_ua.size)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ----------------------------------------------------------------------------- loading


def load_power_profiler_csv(path: Path, chunk_rows: int = 500_000) -> Trace:
    """CSV exported by nRF Connect Power Profiler: Timestamp(ms),Current(uA),D0..D7."""
    path = Path(path)
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        header = [h.strip() for h in next(csv.reader([handle.readline()]))]
        if len(header) < 2 or header[0] != "Timestamp(ms)" or header[1] != "Current(uA)":
            raise InputError(f"unexpected CSV header {header!r} (want Timestamp(ms),Current(uA),D0..)")
        logic = [i for i, h in enumerate(header) if h in {f"D{k}" for k in range(8)}]
        times, currents, bit_chunks = [], [], []
        while True:
            lines = list(itertools.islice(handle, chunk_rows))
            if not lines:
                break
            block = np.loadtxt(lines, delimiter=",", ndmin=2)
            if block.shape[1] != len(header):
                raise InputError(f"row width {block.shape[1]} != header width {len(header)}")
            times.append(block[:, 0].copy())
            currents.append(block[:, 1].copy())
            packed = np.zeros(block.shape[0], dtype=np.uint8)
            for column in logic:
                channel = int(header[column][1:])
                values = block[:, column]
                if not np.all((values == 0.0) | (values == 1.0)):
                    raise InputError(f"{header[column]} has values other than 0/1")
                packed |= (values.astype(np.uint8) << channel)
            bit_chunks.append(packed)
    if not times:
        raise InputError("CSV has no samples")
    time_ms = np.concatenate(times)
    current = np.concatenate(currents)
    if not (np.all(np.isfinite(time_ms)) and np.all(np.isfinite(current))):
        raise InputError("NaN or infinity in CSV")
    steps = np.diff(time_ms)
    if steps.size and (np.any(steps <= 0) or abs(float(np.median(steps)) - DT_S * 1e3) > 1e-9):
        raise InputError("timestamps are not strictly increasing at 0.01 ms")
    irregular = int(np.count_nonzero(np.abs(steps - DT_S * 1e3) > 1e-6))
    return Trace(current, np.concatenate(bit_chunks), float("nan"), f"csv:{path}", time_ms,
                 {"format": "power-profiler-csv", "logic_columns": [header[c] for c in logic],
                  "irregular_steps": irregular, "sha256": sha256_file(path)})


def default_modifiers() -> dict:
    """ppk2-api 0.9.2 PPK2_API.__init__ defaults (used for keys absent from the metadata)."""
    return {
        "R": {"0": 1031.64, "1": 101.65, "2": 10.15, "3": 0.94, "4": 0.043},
        "GS": {str(i): 1 for i in range(5)}, "GI": {str(i): 1 for i in range(5)},
        "O": {str(i): 0 for i in range(5)}, "S": {str(i): 0 for i in range(5)},
        "I": {str(i): 0 for i in range(5)}, "UG": {str(i): 1 for i in range(5)},
    }


def convert_words(words: np.ndarray, modifiers: dict, vdd_mv: float,
                  spike_filter: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Raw PPK2 words -> (current_ua, logic bits, range, counter).

    Same arithmetic, operation order and spike filter as PPK2_API.get_adc_result() of
    ppk2-api 0.9.2, so the values equal what PPK2_API.get_samples() returns bit for bit
    (checked by test_measure_energy.py). The filter state starts empty like a new PPK2_API.
    """
    words = np.asarray(words, dtype=np.uint32)
    ranges = np.minimum((words >> RANGE_SHIFT) & RANGE_MASK, 4).astype(np.int64)
    adc_value = ((words & ADC_MASK) * 4).astype(np.float64)
    adc = np.empty(words.size, dtype=np.float64)
    for r in range(5):
        key = str(r)
        sel = ranges == r
        if not np.any(sel):
            continue
        rwg = (adc_value[sel] - modifiers["O"][key]) * (ADC_MULT / modifiers["R"][key])
        adc[sel] = modifiers["UG"][key] * (
            rwg * (modifiers["GS"][key] * rwg + modifiers["GI"][key])
            + (modifiers["S"][key] * (vdd_mv / 1000) + modifiers["I"][key]))
    if spike_filter:
        adc = _spike_filter(adc, ranges)
    current = adc * 10 ** 6
    bits = ((words >> LOGIC_SHIFT) & 0xFF).astype(np.uint8)
    counter = ((words >> COUNTER_SHIFT) & COUNTER_MASK).astype(np.uint8)
    return current, bits, ranges.astype(np.uint8), counter


def _spike_filter(adc: np.ndarray, ranges: np.ndarray) -> np.ndarray:
    """Sequential state machine of PPK2_API.get_adc_result (rolling averages after a range switch)."""
    alpha, alpha5, samples_after = 0.18, 0.06, 3
    out = adc.copy()
    values = adc.tolist()
    range_list = ranges.tolist()
    rolling = rolling4 = None
    prev_range = None
    consecutive = 0
    after_spike = 0
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
                after_spike = samples_after
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
    return out


def counter_check(counter: np.ndarray) -> dict:
    """Continuity of the 6-bit sample counter; 'available' is False if it never changes."""
    if counter.size < 2 or np.all(counter == counter[0]):
        return {"available": False, "discontinuities": None, "lost_samples_min": None}
    step = (counter[1:].astype(np.int16) - counter[:-1].astype(np.int16)) % 64
    bad = np.flatnonzero(step != 1)
    histogram = np.bincount(step, minlength=64)
    top = np.argsort(histogram)[::-1][:5]
    return {"available": True, "discontinuities": int(bad.size),
            "lost_samples_min": int(np.sum((step[bad] - 1) % 64)),
            "first_discontinuity_sample": int(bad[0] + 1) if bad.size else None,
            # a real counter gives {1: n-1}; many other steps mean bits 18-23 are not a counter
            "step_histogram_top": {int(s): int(histogram[s]) for s in top if histogram[s]}}


def load_raw_capture(directory: Path, spike_filter: bool = True) -> Trace:
    """measure_energy.py output: raw.bin (little-endian uint32 words) + capture.json."""
    directory = Path(directory)
    meta = json.loads((directory / "capture.json").read_text(encoding="utf-8"))
    raw_path = directory / meta["raw_file"]
    if sha256_file(raw_path) != meta["raw_sha256"]:
        raise InputError("raw.bin SHA-256 differs from capture.json")
    data = raw_path.read_bytes()
    usable = len(data) - len(data) % 4
    words = np.frombuffer(data[:usable], dtype="<u4")
    modifiers = default_modifiers()
    for key, table in meta["modifiers"].items():
        if key in modifiers and isinstance(table, dict):
            modifiers[key].update({k: float(v) for k, v in table.items()})
    current, bits, ranges, counter = convert_words(words, modifiers, float(meta["v_supply_mV"]),
                                                   spike_filter)
    info = {"format": "measure_energy-raw", "raw_sha256": meta["raw_sha256"],
            "trailing_bytes": len(data) - usable, "counter": counter_check(counter),
            "spike_filter": spike_filter, "range_counts": np.bincount(ranges, minlength=5).tolist(),
            "capture": {k: meta.get(k) for k in ("started_utc", "seconds_requested",
                                                   "dut_power_on_byte", "temp_room_C", "label",
                                                   "status", "dut_on_rate_deviation_pct",
                                                   "reader_error")}}
    if "dut_power_on_byte" in meta and meta["dut_power_on_byte"] is not None:
        info["dut_power_on_sample"] = int(meta["dut_power_on_byte"]) // 4
    if meta.get("dut_power_off_byte") is not None:
        info["dut_power_off_sample"] = int(meta["dut_power_off_byte"]) // 4
    return Trace(current, bits, float(meta["v_supply_mV"]), f"raw:{directory}", None, info)


def slice_trace(trace: Trace, start: int, stop: int) -> Trace:
    """Samples [start, stop) as a new Trace (e.g. DUT ON..OFF, so a pulse cut by the PPK2
    switching the DUT off touches the end and is treated as truncated)."""
    return Trace(trace.current_ua[start:stop], trace.bits[start:stop], trace.v_supply_mv,
                 f"{trace.source}[{start}:{stop}]",
                 None if trace.time_ms is None else trace.time_ms[start:stop], dict(trace.info))


def load_trace(raw: Path | None, csv_path: Path | None, v_supply_mv: float | None,
               spike_filter: bool = True) -> Trace:
    if (raw is None) == (csv_path is None):
        raise InputError("give exactly one of --raw / --csv")
    trace = load_raw_capture(raw, spike_filter) if raw else load_power_profiler_csv(csv_path)
    if v_supply_mv is not None:
        if raw and abs(v_supply_mv - trace.v_supply_mv) > 1e-9:
            raise InputError("--v-supply-mV disagrees with capture.json")
        trace.v_supply_mv = v_supply_mv
    if not math.isfinite(trace.v_supply_mv):
        raise InputError("supply voltage unknown: pass --v-supply-mV for CSV input")
    return trace


# ----------------------------------------------------------------------------- statistics


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction of the regularized incomplete beta (Numerical Recipes 6.4)."""
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, df: int) -> float:
    x = df / (df + t * t)
    tail = 0.5 * _betainc(df / 2.0, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def student_t_quantile(p: float, df: int) -> float:
    """Inverse CDF by bisection (no SciPy in device/host/.venv)."""
    if not 0.5 <= p < 1.0 or df < 1:
        raise ValueError("p in [0.5, 1), df >= 1")
    lo, hi = 0.0, 1.0
    while student_t_cdf(hi, df) < p:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def describe(values) -> dict:
    """n, mean, sample std, CI95 half-width (Student-t, n-1 dof), CI95/mean, min, max."""
    arr = np.asarray(list(values), dtype=np.float64)
    out = {"n": int(arr.size)}
    if arr.size == 0:
        return out
    mean = float(np.mean(arr))
    out.update(mean=mean, min=float(np.min(arr)), max=float(np.max(arr)))
    if arr.size >= 2:
        std = float(np.std(arr, ddof=1))
        half = student_t_quantile(0.975, arr.size - 1) * std / math.sqrt(arr.size)
        out.update(std=std, ci95_half=half, ci95_low=mean - half, ci95_high=mean + half,
                   ci95_rel_pct=(100.0 * half / abs(mean)) if mean else None)
    return out


# ----------------------------------------------------------------------------- markers


def channel_runs(bits: np.ndarray, channel: int) -> tuple[np.ndarray, np.ndarray]:
    """(starts, ends) of HIGH runs of one digital channel; ends are exclusive."""
    level = ((bits >> channel) & 1).astype(np.int8)
    edges = np.diff(np.concatenate(([0], level, [0])))
    return np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)


def window_stats(trace: Trace, start: int, stop: int, channels=range(8)) -> dict:
    """Mean/std/charge of samples [start, stop) and how many samples each channel was HIGH."""
    current = trace.current_ua[start:stop]
    if current.size < 2:
        raise InputError("window shorter than two samples")
    out = {"start_sample": int(start), "stop_sample": int(stop), "sample_count": int(current.size),
           "duration_s": current.size * DT_S, "mean_uA": float(np.mean(current)),
           "sample_std_uA": float(np.std(current, ddof=1)), "min_uA": float(np.min(current)),
           "max_uA": float(np.max(current)),
           "charge_rect_mC": float(np.sum(current)) * DT_S / 1000.0}
    if trace.time_ms is not None:
        t_s = trace.time_ms[start:stop] / 1000.0
        out["duration_s"] = float(t_s[-1] - t_s[0])
        out["charge_trapz_mC"] = float(np.trapezoid(current, t_s)) / 1000.0
    if math.isfinite(trace.v_supply_mv):
        out["v_supply_mV"] = trace.v_supply_mv
        out["energy_rect_uJ"] = trace.v_supply_mv / 1000.0 * float(np.sum(current)) * DT_S
    bits = trace.bits[start:stop]
    out["high_samples"] = {f"D{c}": int(np.count_nonzero((bits >> c) & 1)) for c in channels}
    return out


def pulse_table(trace: Trace, channels=range(8)) -> dict:
    out = {}
    for c in channels:
        starts, ends = channel_runs(trace.bits, c)
        widths = (ends - starts) * DT_S * 1e3
        out[f"D{c}"] = {"pulses": int(starts.size),
                        "starts": starts.tolist(), "ends": ends.tolist(),
                        "width_ms": describe(widths) if starts.size else {"n": 0}}
    return out


def rotation_check(trace: Trace, channels=(0, 1, 2, 3), width_ms=500.0, tol_ms=5.0) -> dict:
    """Week 1 Active self-test: one marker at a time, D0->D1->D2->D3->D0..., width_ms each."""
    events = []
    for c in channels:
        starts, ends = channel_runs(trace.bits, c)
        events += [(int(s), int(e), c) for s, e in zip(starts, ends)]
    events.sort()
    complete = [ev for ev in events if ev[0] > 0 and ev[1] < trace.n]  # drop truncated ends
    order_errors = sum(1 for a, b in zip(complete, complete[1:])
                       if channels.index(b[2]) != (channels.index(a[2]) + 1) % len(channels))
    width_errors = sum(1 for s, e, _ in complete if abs((e - s) * DT_S * 1e3 - width_ms) > tol_ms)
    level = np.zeros(trace.n, dtype=np.uint8)
    for c in channels:
        level += (trace.bits >> c) & 1
    overlap = int(np.count_nonzero(level > 1))
    others = [c for c in range(8) if c not in channels]
    stray = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in others}
    ok = bool(complete) and order_errors == 0 and width_errors == 0 and overlap == 0 \
        and not any(stray.values())
    return {"pulses": len(complete), "order_errors": order_errors, "width_errors": width_errors,
            "overlap_samples": overlap, "stray_high_samples": stray, "pass": ok}


def selftest_check(trace: Trace, phase_map: dict, width_ms=200.0, tol_ms=5.0,
                   max_join_ms=1.0) -> dict:
    """Firmware week 7 boot self-test: D0..D4 HIGH one after another for width_ms each.

    The self-test is the first CTRL pulse about width_ms wide (a glitch while the pins still float
    at power-on is skipped); each other marker's self-test pulse is the last of its runs that
    ends before that CTRL pulse starts (a boot NVS write may pulse D1 earlier).
    """
    ctrl_starts, ctrl_ends = channel_runs(trace.bits, phase_map["ctrl"])
    if ctrl_starts.size == 0:
        return {"found": False, "pass": False, "reason": "no CTRL pulse"}
    widths = (ctrl_ends - ctrl_starts) * DT_S * 1e3
    wide = np.flatnonzero(np.abs(widths - width_ms) <= tol_ms)
    pick = int(wide[0]) if wide.size else 0
    pulses = {"ctrl": (int(ctrl_starts[pick]), int(ctrl_ends[pick]))}
    for name in SELFTEST_ORDER[:-1]:
        starts, ends = channel_runs(trace.bits, phase_map[name])
        keep = np.flatnonzero(ends <= ctrl_starts[pick] + 1)
        if keep.size == 0:
            return {"found": False, "pass": False, "reason": f"no self-test pulse on {name}"}
        pulses[name] = (int(starts[keep[-1]]), int(ends[keep[-1]]))
    rows, ok = [], True
    for i, name in enumerate(SELFTEST_ORDER):
        s, e = pulses[name]
        width = (e - s) * DT_S * 1e3
        join = None if i == 0 else (s - pulses[SELFTEST_ORDER[i - 1]][1]) * DT_S * 1e3
        good = abs(width - width_ms) <= tol_ms and (join is None or 0.0 <= join <= max_join_ms)
        ok &= good
        rows.append({"phase": name, "channel": f"D{phase_map[name]}", "start_sample": s,
                     "end_sample": e, "width_ms": width, "gap_from_previous_ms": join, "ok": good})
    first, last = pulses[SELFTEST_ORDER[0]][0], pulses["ctrl"][1]
    level = np.zeros(last - first, dtype=np.uint8)
    for name in SELFTEST_ORDER:
        level += (trace.bits[first:last] >> phase_map[name]) & 1
    overlap = int(np.count_nonzero(level > 1))
    ok &= overlap == 0
    return {"found": True, "pass": bool(ok), "pulses": rows, "overlap_samples": overlap,
            "end_sample": last, "ctrl_pulses_before_selftest": pick}


# ----------------------------------------------------------------------------- cycles


def segment_cycles(trace: Trace, phase_map: dict, after_sample: int = 0) -> tuple[list, dict]:
    """Cycles that start with a CTRL rising edge after after_sample. Returns (cycles, anomalies)."""
    names = list(phase_map)
    runs = {name: channel_runs(trace.bits, phase_map[name]) for name in names}
    mask = 0
    for c in phase_map.values():
        mask |= 1 << c
    ctrl_starts = runs["ctrl"][0]
    ctrl_starts = ctrl_starts[ctrl_starts >= after_sample]
    anomalies = {"marker_high_at_capture_start": [n for n in names if trace.n and
                                                  (trace.bits[0] >> phase_map[n]) & 1],
                 "out_of_cycle_pulses": {n: 0 for n in names}}
    v = trace.v_supply_mv / 1000.0
    cycles = []
    for k, start in enumerate(ctrl_starts):
        limit = int(ctrl_starts[k + 1]) if k + 1 < ctrl_starts.size else trace.n
        in_window = {}
        for name in names:
            s, e = runs[name]
            sel = (s >= start) & (s < limit)
            in_window[name] = (s[sel], e[sel])
        errors = []
        # The cycle ends with its WAIT pulse; later pulses before the next CTRL are out of cycle.
        wait_ends = in_window["wait"][1]
        ends = [int(e[-1]) for s, e in in_window.values() if e.size]
        end = int(wait_ends[0]) if wait_ends.size else (max(ends) if ends else int(start))
        if end == trace.n and any((trace.bits[-1] >> phase_map[n]) & 1 for n in names):
            errors.append("truncated_end")
        # Pulses after the end of this cycle but before the next CTRL: a D1 pulse is an NVS
        # write (counted only); any other marker means a retry or a firmware fault.
        for name in names:
            s, e = in_window[name]
            extra = int(np.count_nonzero(s >= end))
            anomalies["out_of_cycle_pulses"][name] += extra
            if extra and name != "prot":
                errors.append("retry_tx" if name == "tx" else f"extra_{name}")
            in_window[name] = (s[s < end], e[s < end])
        phase_rows = {}
        for name in PHASES:
            if name not in phase_map:
                continue
            s, e = in_window[name]
            if s.size == 0 and name not in OPTIONAL_PHASES:
                errors.append(f"missing_{name}")
            if s.size > 1:
                errors.append("retry_tx" if name == "tx" else f"multiple_{name}")
            phase_rows[name] = (int(s[0]), int(e[0])) if s.size else None
        order = [phase_rows[n][0] for n in PHASES if n in phase_rows and phase_rows[n]]
        if order != sorted(order):
            errors.append("phase_order")
        seg_bits = trace.bits[start:end] & mask
        seg_i = trace.current_ua[start:end]
        row = {"cycle": len(cycles), "start_sample": int(start), "end_sample": int(end),
               "t_cycle_ms": (end - start) * DT_S * 1e3,
               "E_cycle_uJ": v * float(np.sum(seg_i)) * DT_S}
        accounted = 0.0
        for name in PHASES:
            if name not in phase_map:
                continue
            sel = seg_bits == (1 << phase_map[name])
            energy = v * float(np.sum(seg_i[sel])) * DT_S
            row[f"t_{name}_ms"] = int(np.count_nonzero(sel)) * DT_S * 1e3
            row[f"E_{name}_uJ"] = energy
            accounted += energy
        gap = seg_bits == 0
        multi = (seg_bits != 0) & ((seg_bits & (seg_bits - 1)) != 0)
        row["t_gap_ms"] = int(np.count_nonzero(gap)) * DT_S * 1e3
        row["E_gap_uJ"] = v * float(np.sum(seg_i[gap])) * DT_S
        row["overlap_samples"] = int(np.count_nonzero(multi))
        row["E_overlap_uJ"] = v * float(np.sum(seg_i[multi])) * DT_S
        if row["overlap_samples"]:
            errors.append("phase_overlap")
        row["E_phases_uJ"] = accounted
        row["diff_pct"] = (100.0 * abs(row["E_cycle_uJ"] - accounted) / row["E_cycle_uJ"]
                           if row["E_cycle_uJ"] > 0 else float("nan"))
        row["rho"] = "P1" if phase_rows.get("prot") else "P0"
        row["mean_cycle_uA"] = float(np.mean(seg_i)) if seg_i.size else float("nan")
        row["errors"] = errors
        cycles.append(row)
    return cycles, anomalies


def add_net(cycles: list, i_idle_ua: float, v_supply_mv: float) -> None:
    """Net = gross - V * I_idle * t for every phase (decision W7-D5: gross is the primary number)."""
    v = v_supply_mv / 1000.0
    for row in cycles:
        for name in PHASES + ("cycle",):
            key, t_key = f"E_{name}_uJ", f"t_{name}_ms"
            if key in row and t_key in row:
                row[f"E_{name}_net_uJ"] = row[key] - v * i_idle_ua * row[t_key] / 1e3


def estimate_conn_interval_ms(trace: Trace, start: int, stop: int,
                              threshold_ua: float = 1000.0, merge_ms: float = 2.0) -> dict:
    """Diagnostic: median spacing of radio-event current peaks in a connected-idle window."""
    current = trace.current_ua[start:stop]
    above = np.flatnonzero(current > threshold_ua)
    if above.size == 0:
        return {"events": 0, "median_spacing_ms": None}
    merge = int(merge_ms / (DT_S * 1e3))
    event_starts = above[np.concatenate(([True], np.diff(above) > merge))]
    spacing = np.diff(event_starts) * DT_S * 1e3
    return {"events": int(event_starts.size),
            "median_spacing_ms": float(np.median(spacing)) if spacing.size else None,
            "threshold_uA": threshold_ua}


def summarize_cycles(cycles: list) -> dict:
    out = {}
    for rho in ("P1", "P0"):
        group = [c for c in cycles if c["rho"] == rho and not c["errors"]]
        if not group:
            continue
        stats = {}
        for key in group[0]:
            if (key.startswith("E_") or key.startswith("t_") or key == "diff_pct"
                    or key == "mean_cycle_uA"):
                stats[key] = describe(c[key] for c in group)
        out[rho] = {"n": len(group), "stats": stats}
    return out


def parse_map(text: str) -> dict:
    """'D4:ctrl,D0:dev,D1:prot,D2:tx,D3:wait' -> {'ctrl': 4, ...}."""
    out = {}
    for item in text.split(","):
        channel, _, name = item.partition(":")
        channel = channel.strip().upper()
        name = name.strip().lower()
        if not channel.startswith("D") or not channel[1:].isdigit() or name not in PHASES:
            raise argparse.ArgumentTypeError(f"bad map entry {item!r}")
        out[name] = int(channel[1:])
    if len(set(out.values())) != len(out) or not {"ctrl", "dev", "tx", "wait"} <= set(out):
        raise argparse.ArgumentTypeError("map needs distinct channels for ctrl, dev, tx, wait")
    return out


# ----------------------------------------------------------------------------- outputs


CYCLE_COLUMNS = ["cycle", "rho", "start_sample", "end_sample", "t_cycle_ms", "t_ctrl_ms",
                 "t_dev_ms", "t_prot_ms", "t_tx_ms", "t_wait_ms", "t_gap_ms", "E_cycle_uJ",
                 "E_ctrl_uJ", "E_dev_uJ", "E_prot_uJ", "E_tx_uJ", "E_wait_uJ", "E_gap_uJ",
                 "E_overlap_uJ", "overlap_samples", "E_phases_uJ", "diff_pct", "mean_cycle_uA",
                 "E_cycle_net_uJ", "E_ctrl_net_uJ", "E_dev_net_uJ", "E_prot_net_uJ",
                 "E_tx_net_uJ", "E_wait_net_uJ", "errors"]


def write_cycles_csv(path: Path, cycles: list) -> None:
    with open(path, "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CYCLE_COLUMNS)
        for row in cycles:
            writer.writerow([";".join(row["errors"]) if col == "errors" else
                             (f"{row[col]:.6f}" if isinstance(row.get(col), float) else row.get(col, ""))
                             for col in CYCLE_COLUMNS])


HATCH = {"ctrl": "..", "dev": "//", "prot": "xx", "tx": "\\\\", "wait": "--"}
SHADE = {"ctrl": "0.85", "dev": "0.70", "prot": "0.55", "tx": "0.78", "wait": "0.92"}
LABEL = {"ctrl": "CTRL", "dev": "HEAD", "prot": "PROT", "tx": "TX", "wait": "WAIT"}


def plot_cycle(path: Path, trace: Trace, cycle: dict, phase_map: dict, margin_ms: float = 20.0) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mpl-week7"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    margin = int(margin_ms / (DT_S * 1e3))
    a = max(0, cycle["start_sample"] - margin)
    b = min(trace.n, cycle["end_sample"] + margin)
    t = (np.arange(a, b) - cycle["start_sample"]) * DT_S * 1e3
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for name in PHASES:
        if name not in phase_map:
            continue
        starts, ends = channel_runs(trace.bits[a:b], phase_map[name])
        for i, (s, e) in enumerate(zip(starts, ends)):
            ax.axvspan(t[s], t[min(e, b - a - 1)], facecolor=SHADE[name], hatch=HATCH[name],
                       edgecolor="0.4", linewidth=0.6, label=LABEL[name] if i == 0 else None)
    ax.plot(t, trace.current_ua[a:b] / 1000.0, color="black", linewidth=0.5)
    ax.set_xlabel("Time from CTRL rising edge (ms)")
    ax.set_ylabel("Current at 5 V input (mA)")
    ax.set_title(f"One cycle (#{cycle['cycle']}, {cycle['rho']}): E_cycle = "
                 f"{cycle['E_cycle_uJ']:.0f} uJ, gap {cycle['diff_pct']:.2f} %")
    ax.legend(loc="upper right", ncols=5, fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def new_output_dir(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        raise SystemExit(f"refusing to reuse existing output {path}")
    path.mkdir(parents=True)
    return path


def tool_hashes() -> dict:
    here = Path(__file__).resolve().parent
    return {name: sha256_file(here / name) for name in ("energy_phases.py", "measure_energy.py")
            if (here / name).exists()}


# ----------------------------------------------------------------------------- commands


def cmd_idle(args) -> int:
    trace = load_trace(args.raw, args.csv, args.v_supply_mV, not args.no_spike_filter)
    start = int(round(args.start_s * SAMPLE_RATE_HZ))
    stop = trace.n if args.seconds is None else start + int(round(args.seconds * SAMPLE_RATE_HZ))
    stats = window_stats(trace, start, min(stop, trace.n))
    stats["all_logic_low"] = not any(stats["high_samples"].values())
    stats["trace"] = trace.info
    print(json.dumps(stats, indent=2))
    if args.expect_mean_uA is not None:
        rel = abs(stats["mean_uA"] - args.expect_mean_uA) / args.expect_mean_uA * 100.0
        print(f"mean {stats['mean_uA']:.3f} uA vs expected {args.expect_mean_uA:.3f} uA: "
              f"{rel:.2f} % (limit {args.tolerance_pct} %)")
        return 0 if rel <= args.tolerance_pct and stats["all_logic_low"] else 1
    return 0


def cmd_markers(args) -> int:
    trace = load_trace(args.raw, args.csv, args.v_supply_mV or 5000.0, not args.no_spike_filter)
    table = pulse_table(trace)
    for name, row in table.items():
        w = row["width_ms"]
        print(f"{name}: pulses={row['pulses']}"
              + (f" width_ms mean={w['mean']:.3f} min={w['min']:.3f} max={w['max']:.3f}"
                 if row["pulses"] else ""))
    result = 0
    if args.rotation:
        channels = tuple(int(c) for c in args.rotation.split(","))
        check = rotation_check(trace, channels, args.width_ms, args.tolerance_ms)
        print("ROTATION", json.dumps(check))
        result = 0 if check["pass"] else 1
    if args.counter and trace.info.get("counter") is not None:
        print("COUNTER", json.dumps(trace.info["counter"]))
    return result


RATE_LIMIT_PCT = 0.1   # TC2: samples between DUT ON and OFF vs host time x 100 kS/s


def data_loss_checks(trace: Trace, ignore_counter: bool = False) -> dict:
    """TC2 checks of a raw capture: sample counter continuity (unless the session A test showed
    bits 18-23 are not a counter: --ignore-counter) and the capture's sample-rate deviation."""
    out = {}
    counter = trace.info.get("counter")
    if counter is not None and not ignore_counter:
        out["no_data_loss"] = counter.get("discontinuities") in (0, None)
    capture = trace.info.get("capture") or {}
    if capture.get("dut_on_rate_deviation_pct") is not None:
        out["sample_rate_ok"] = capture["dut_on_rate_deviation_pct"] <= RATE_LIMIT_PCT \
            and capture.get("reader_error") is None
    return out


def cmd_analyze(args) -> int:
    trace = load_trace(args.raw, args.csv, args.v_supply_mV, not args.no_spike_filter)
    phase_map = args.map
    out = new_output_dir(args.out)
    selftest = selftest_check(trace, phase_map, args.selftest_width_ms)
    after = selftest["end_sample"] if selftest.get("found") else 0
    idle = None
    if selftest.get("found") and args.idle_seconds > 0:
        a = after + int(args.idle_offset_s * SAMPLE_RATE_HZ)
        idle = window_stats(trace, a, a + int(args.idle_seconds * SAMPLE_RATE_HZ),
                            channels=sorted(phase_map.values()))
        idle["all_markers_low"] = not any(idle["high_samples"].values())
    cycles, anomalies = segment_cycles(trace, phase_map, after_sample=after + 1)
    i_idle = idle["mean_uA"] if idle else None
    if i_idle is not None:
        add_net(cycles, i_idle, trace.v_supply_mv)
    valid = [c for c in cycles if not c["errors"]]
    diffs = [c["diff_pct"] for c in valid]
    p1 = sum(1 for c in valid if c["rho"] == "P1")
    p0 = sum(1 for c in valid if c["rho"] == "P0")
    checks = {
        "selftest_D0_D4": bool(selftest.get("pass")),
        "cycle_count": len(cycles) == args.expect_cycles,
        "all_cycles_valid": len(valid) == len(cycles) and bool(cycles),
        "diff_below_3pct_all": bool(diffs) and max(diffs) < DIFF_LIMIT_PCT and len(diffs) == len(cycles),
    }
    unused = [c for c in range(8) if c not in phase_map.values()]
    stray = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in unused}
    checks["unused_channels_low"] = not any(stray.values())
    checks.update(data_loss_checks(trace, args.ignore_counter))
    if args.expect_p1 is not None:
        checks["p1_cycles"] = p1 == args.expect_p1
    if args.expect_p0 is not None:
        checks["p0_cycles"] = p0 == args.expect_p0
    if idle is not None:
        checks["idle_markers_low"] = idle["all_markers_low"]
    gaps = [(c["end_sample"], cycles[i + 1]["start_sample"]) for i, c in enumerate(cycles[:-1])]
    conn = (estimate_conn_interval_ms(trace, *max(gaps, key=lambda g: g[1] - g[0]))
            if gaps else None)
    summary = {
        "schema": "week7-energy-analysis/1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "trace": {"source": trace.source, "samples": trace.n, "duration_s": trace.n * DT_S,
                  "v_supply_mV": trace.v_supply_mv, **trace.info},
        "phase_map": {k: f"D{v}" for k, v in phase_map.items()},
        "method": "per-sample phase assignment, rectangle sum E = V*sum(i)*dt (W7-D11); "
                  "gross = primary, net = gross - V*I_idle*t (W7-D5)",
        "counter_ignored": bool(args.ignore_counter),
        "selftest": selftest,
        "idle": idle,
        "I_idle_uA": i_idle,
        "cycles_found": len(cycles), "cycles_valid": len(valid), "p1_cycles": p1, "p0_cycles": p0,
        "diff_pct": describe(diffs),
        "anomalies": anomalies,
        "unused_channel_high_samples": stray,
        "errors": {i: c["errors"] for i, c in enumerate(cycles) if c["errors"]},
        "conn_interval_diagnostic": conn,
        "groups": summarize_cycles(cycles),
        "tools": tool_hashes(),
    }
    write_cycles_csv(out / "cycles.csv", cycles)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if valid and not args.no_plot:
        median = sorted(valid, key=lambda c: c["E_cycle_uJ"])[len(valid) // 2]
        plot_cycle(out / "cycle_waveform.png", trace, median, phase_map)
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    d = summary["diff_pct"]
    print(f"cycles {len(cycles)} (valid {len(valid)}, P1 {p1}, P0 {p0}); diff_pct mean "
          f"{d.get('mean', float('nan')):.3f} max {d.get('max', float('nan')):.3f}; "
          f"I_idle {i_idle if i_idle is None else round(i_idle, 3)} uA")
    print(f"RESULT: {summary['status']} -> {out}")
    return 0 if summary["status"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def source(p):
        p.add_argument("--raw", type=Path, help="measure_energy.py capture directory")
        p.add_argument("--csv", type=Path, help="nRF Connect Power Profiler CSV export")
        p.add_argument("--v-supply-mV", dest="v_supply_mV", type=float,
                       help="required for CSV input (5000 on the VBUS bench)")
        p.add_argument("--no-spike-filter", action="store_true",
                       help="raw input only: skip the ppk2-api range-switch filter")

    p = sub.add_parser("idle", help="window statistics (week 2 reproduction)")
    source(p)
    p.add_argument("--start-s", type=float, default=0.0)
    p.add_argument("--seconds", type=float)
    p.add_argument("--expect-mean-uA", dest="expect_mean_uA", type=float)
    p.add_argument("--tolerance-pct", type=float, default=10.0)
    p.set_defaults(func=cmd_idle)

    p = sub.add_parser("markers", help="digital pulse table / rotation check")
    source(p)
    p.add_argument("--rotation", help="e.g. 0,1,2,3 for the week 1 Active self-test")
    p.add_argument("--width-ms", type=float, default=500.0)
    p.add_argument("--tolerance-ms", type=float, default=5.0)
    p.add_argument("--counter", action="store_true", help="print the sample-counter check")
    p.set_defaults(func=cmd_markers)

    p = sub.add_parser("analyze", help="week 7 session: self-test, idle, cycles")
    source(p)
    p.add_argument("--map", type=parse_map, default=dict(DEFAULT_MAP))
    p.add_argument("--expect-cycles", type=int, required=True)
    p.add_argument("--expect-p1", type=int)
    p.add_argument("--expect-p0", type=int)
    p.add_argument("--selftest-width-ms", type=float, default=200.0)
    p.add_argument("--idle-offset-s", type=float, default=0.5,
                   help="idle window start after the self-test CTRL pulse ends")
    p.add_argument("--idle-seconds", type=float, default=29.0)
    p.add_argument("--no-plot", action="store_true")
    p.add_argument("--ignore-counter", action="store_true",
                   help="only if session A showed bits 18-23 are not a sample counter (TC2 then "
                        "rests on the sample-rate check)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.set_defaults(func=cmd_analyze)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except InputError as error:
        print(f"INPUT ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
