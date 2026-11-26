"""Week 10 E_prot of P1 at every s, radio off (W10-D1, W10-D2): console checks of prot-usb, PPK2 cycle
segmentation of the prot image, per-session energy rows and the multi-session summary.

Rules (locked before the first E_prot session, with week10_analysis.py):
  * VERIFY (TC2): q/scale of every (sample 0..49, s 0..9) = host C path (week 9 refs); protect() with the
    PUBLIC_TEST_ONLY key 00..1f, sequence n + 1, = contracts/i2_ref; the HEAD-only s1 FP32 output = host shim.
  * cycles: CTRL rising edge -> end of HEAD (P0, CONV) or of PROT (P1); D1 only inside P1 cycles; D2/D3 never;
    exactly one D1 pulse before the self-test (the boot nonce reservation, the only Flash write); order and
    ops = the W10-D1 plan (the trace tells P1 from P0 by D1; CONV vs P0 by the plan).
  * E_prot(P1, s) = energy of the D1-only samples (gross 5 V, W9-D9 pooled + session range), net, core
    (week9_figures.core_fit of E_prot on the share of 50 us PROT blocks above 3.6 mA: block size PROT_BLOCK_SAMPLES
    chosen on week 9 B5 data on 12/11, D:/HUST/ASI_week10/prot-block-choice-20261112), t_prot marker; the
    paired delta of E_dev + E_prot (P1 - P0) per pair; E_dev of the P0 cycles (radio off); E_conv,min = E_dev
    of the HEAD-only s1 cycles; CI95 / mean < 10 % (TC5); conv_rule and prot_ratios of week10_analysis.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week10_analysis as wa  # noqa: E402
import week10_ble as wb  # noqa: E402
import week10_common as w10  # noqa: E402

w8 = wb.w8
w7 = wb.w7
FS = ep.SAMPLE_RATE_HZ
DT_MS = 1e3 / FS
CTRL, DEV, PROT, TX, WAIT = wb.CTRL, wb.DEV, wb.PROT, wb.TX, wb.WAIT
PROT_BLOCK_SAMPLES = 5               # 50 us blocks (B5 choice of 12/11: core session range 0.34 %)
PROT_SPLITS = tuple(range(10))
OPS = w10.OP_NAMES                    # 0 P0, 1 P1, 2 CONV
TABLE_III_OFF = HERE.parents[1] / "results" / "week9" / "device" / "analysis" / "table_iii_e_dev.csv"


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------------- console checks (prot-usb)


def banner_checks(banner: dict, host: wb.HostRefs) -> dict:
    return {
        "banner_variant_prot_usb": banner.get("variant") == "prot-usb",
        "banner_set_sha256": banner.get("set_sha256") == host.sample_set.set_sha256,
        "banner_plan_sha256": banner.get("plan_sha256") == w10.PROT_PLAN_SHA256,
        "device_plan_digest_equal": banner.get("plan_device_sha256") == w10.PROT_PLAN_SHA256
                                    and banner.get("plan_ok") == "1",
        "banner_cycles_p1": banner.get("cycles") == str(w10.PROT_CYCLES)
                            and banner.get("p1_cycles") == str(w10.ROUNDS * len(PROT_SPLITS)),
    }


def public_protect(host: wb.HostRefs, n: int, s: int, sequence: int) -> bytes:
    """protect() of sample n at s with the PUBLIC_TEST_ONLY key, as the prot-usb VERIFY does."""
    c, length, qb, _ = host.tensors[(n, s)]
    profile = w8.i2.Profile(w7.registry_profile().model_profile_id, w7.wire_split_id(s), c, length, w7.KEY_ID)
    return w8.i2.protect(qb, w8.i2.descriptor(profile), w7.nonce_bytes(sequence), w7.PUBLIC_TEST_KEY, profile)


def check_verify(lines_with, banner: dict, host: wb.HostRefs) -> tuple:
    vq, vprot, vconv = lines_with("VQ n="), lines_with("VPROT n="), lines_with("VCONV n=")
    end = lines_with("VERIFY END")
    mismatches, q_ok, p_ok, c_ok = [], [], [], []
    for r in vq:
        n, s = int(r["n"]), int(r["s"])
        ok = (n, s) in host.tensors and s in PROT_SPLITS
        if ok:
            c, length, qb, sb = host.tensors[(n, s)]
            ok = (r.get("id") == host.sample_set.samples[n].sample_id and int(r["C"]) == c and int(r["L"]) == length
                  and int(r["bytes"]) == c * length + 2 * c and r["q_sha256"] == sha_hex(qb)
                  and r["scale_sha256"] == sha_hex(sb))
        q_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "s": s, "what": "q/scale"})
    for r in vprot:
        n, s, seq = int(r["n"]), int(r["s"]), int(r["seq"])
        ok = s in PROT_SPLITS and 0 <= n < wb.SAMPLES and seq == n + 1 and r.get("status") == "0"
        if ok:
            out = public_protect(host, n, s, seq)
            ok = int(r["len"]) == len(out) and r["sha256"] == sha_hex(out)
        p_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "s": s, "what": "protect"})
    for r in vconv:
        n = int(r["n"])
        values = host.head_values(n, w10.CONV_SPLIT)
        ok = int(r["s"]) == w10.CONV_SPLIT and int(r["values"]) == values.size and r["sha256"] == sha_hex(values.tobytes())
        c_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "what": "conv output"})
    expected = [(s, n) for s in PROT_SPLITS for n in range(wb.SAMPLES)]
    checks = {
        **banner_checks(banner, host),
        "vq_every_sample_s0_s9_in_order": [(int(r["s"]), int(r["n"])) for r in vq] == expected,
        "q_scale_equal_host": len(q_ok) == len(expected) and all(q_ok),
        "protect_every_sample_s0_s9": [(int(r["s"]), int(r["n"])) for r in vprot] == expected,
        "protect_equal_i2_ref_public_key": len(p_ok) == len(expected) and all(p_ok),
        "conv_output_equal_host_every_sample": len(c_ok) == wb.SAMPLES and all(c_ok),
        "verify_end_set_sha256": bool(end) and end[-1].get("set_sha256") == host.sample_set.set_sha256
                                 and end[-1].get("splits") == "ALL",
    }
    return checks, {"vq": len(vq), "vprot": len(vprot), "vconv": len(vconv), "mismatches": mismatches[:20]}


def tprot_table(lines_with) -> tuple:
    """TPSUM per s (DWT descriptor + protect, IRQs locked) and TCSUM (HEAD-only s1) in ms."""
    to_ms = 1e3 / w9_cpu_hz()
    tp = {int(r["s"]): {"runs": int(r["runs"]), "prot_mean_ms": int(r["prot_mean_x100"]) / 100.0 * to_ms,
                        "prot_min_ms": int(r["prot_min"]) * to_ms, "prot_max_ms": int(r["prot_max"]) * to_ms}
          for r in lines_with("TPSUM s=")}
    tc = [{"runs": int(r["runs"]), "conv_mean_ms": int(r["conv_mean_x100"]) / 100.0 * to_ms,
           "conv_min_ms": int(r["conv_min"]) * to_ms, "conv_max_ms": int(r["conv_max"]) * to_ms}
          for r in lines_with("TCSUM s=")]
    checks = {"tprot_every_s0_s9_50_runs": sorted(tp) == list(PROT_SPLITS) and all(v["runs"] == 50 for v in tp.values()),
              "tconv_50_runs": len(tc) == 1 and tc[0]["runs"] == 50}
    return checks, {"t_prot_dwt_ms": {str(k): v for k, v in sorted(tp.items())}, "t_conv_dwt_ms": tc[0] if tc else None}


def w9_cpu_hz() -> int:
    return wb.w9.CPU_HZ


def check_session(lines_with, banner: dict, host: wb.HostRefs, first: int, count: int, prior: int | None) -> tuple:
    rows = list(host.plans.prot)[first:first + count]
    cycles = lines_with("CYCLE i=")
    end = lines_with("SESSION END")
    ok, seqs, mism = [], [], []
    for r, plan in zip(cycles, rows):
        op = OPS[plan.op]
        good = (int(r["i"]) == plan.cycle and int(r["s"]) == plan.split and int(r["n"]) == plan.sample
                and r["op"] == op and r["res"] == "OK" and int(r["nonce_writes"]) == 0)
        if good and op == "P1":
            seqs.append(int(r["seq"]))
            good = int(r["bytes"]) == host.bytes_payload(plan.split) and r["prot_sha256"] != "-"
        elif good and op == "P0":
            good = int(r["seq"]) == 0 and int(r["bytes"]) == host.bytes_payload(plan.split)
        elif good:
            good = int(r["seq"]) == 0 and int(r["bytes"]) == 0
        ok.append(good)
        if not good:
            mism.append(int(r["i"]))
    checks = {
        **banner_checks(banner, host),
        "one_cycle_line_per_plan_cycle_in_order": [int(r["i"]) for r in cycles] == [p.cycle for p in rows],
        "every_cycle_ok_plan_op_s_n_bytes_no_flash_write": len(ok) == count and all(ok),
        "p1_sequences_strictly_increasing": all(b > a for a, b in zip(seqs, seqs[1:])) and bool(seqs or not any(
            p.op == w10.OP_P1 for p in rows)),
        "session_end_ok": bool(end) and end[-1].get("ok") == str(count) and end[-1].get("failed") == "0",
    }
    if prior is not None:
        checks["p1_sequences_above_prior"] = all(q > prior for q in seqs)
    timing = {}
    for r in cycles:
        e = timing.setdefault(f'{r["op"]} s{r["s"]}', {"head_us": [], "prot_us": []})
        e["head_us"].append(int(r["head_us"]))
        e["prot_us"].append(int(r["prot_us"]))
    details = {"cycles": len(cycles), "mismatch_cycles": mism[:20], "first_p1_sequence": seqs[0] if seqs else None,
               "last_p1_sequence": seqs[-1] if seqs else None,
               "dwt_us_debug_only": {k: {"head_mean": float(np.mean(v["head_us"])), "prot_mean": float(np.mean(v["prot_us"]))}
                                     for k, v in sorted(timing.items())}}
    return checks, details


# ----------------------------------------------------------------------------- PPK2 cycles of the prot image


def high_fraction(current: np.ndarray, block: int) -> float:
    cur = np.asarray(current, float)
    if cur.size == 0:
        return float("nan")
    n = cur.size // block
    blocks = cur[:n * block].reshape(n, block).mean(axis=1) if n else cur
    return float(np.mean(blocks > wb_high_level()))


def wb_high_level() -> float:
    import week9_ppk2 as w9p
    return w9p.HIGH_LEVEL_UA


def boot_d1_pulses(trace: ep.Trace, before: int) -> int:
    """D1 pulses before the self-test: the boot nonce reservation (one NVS write) and nothing else."""
    s, _ = ep.channel_runs(trace.bits, PROT)
    return int(np.count_nonzero(s < before))


def segment_prot_cycles(trace: ep.Trace, after: int, plan_rows: list) -> list:
    """Cycles after the self-test mapped to the plan in order: CTRL rising edge -> fall of HEAD (P0, CONV) or of
    PROT (P1). Every 10 us sample goes to the phase whose marker is the only one set (W7-D11)."""
    names = {"ctrl": CTRL, "dev": DEV, "prot": PROT, "tx": TX, "wait": WAIT}
    runs = {n: ep.channel_runs(trace.bits, c) for n, c in names.items()}
    ctrl_s = runs["ctrl"][0]
    ctrl_s = ctrl_s[ctrl_s > after]
    mask = sum(1 << c for c in names.values())
    v = trace.v_supply_mv / 1000.0
    cycles = []
    for k, start in enumerate(ctrl_s):
        limit = int(ctrl_s[k + 1]) if k + 1 < ctrl_s.size else trace.n
        plan = plan_rows[k] if k < len(plan_rows) else None
        op = OPS[plan.op] if plan is not None else None
        inside = {}
        for n in names:
            s, e = runs[n]
            sel = (s >= start) & (s < limit)
            inside[n] = (s[sel], e[sel])
        errors = [] if plan is not None else ["beyond_plan"]
        needed = ("ctrl", "dev", "prot") if op == "P1" else ("ctrl", "dev")
        for n in names:
            count = inside[n][0].size
            if n in needed and count == 0:
                errors.append(f"missing_{n}")
            if n in needed and count > 1:
                errors.append(f"multiple_{n}")
            if n not in needed and count:
                errors.append(f"unexpected_{n}")
        last = "prot" if op == "P1" else "dev"
        ends = inside[last][1]
        end = int(ends[0]) if ends.size else int(max((int(e[-1]) for _, e in inside.values() if e.size), default=start))
        if end >= trace.n - 1 or not ends.size:
            errors.append("truncated_end")
        order = [int(inside[n][0][0]) for n in needed if inside[n][0].size]
        if order != sorted(order):
            errors.append("phase_order")
        seg_bits = trace.bits[start:end] & mask
        seg_i = trace.current_ua[start:end]
        row = {"cycle": len(cycles), "round": plan.round if plan else None, "sample": plan.sample if plan else None,
               "split": plan.split if plan else None, "op": op, "start_sample": int(start), "end_sample": int(end),
               "t_cycle_ms": (end - start) * DT_MS, "E_cycle_uJ": v * float(np.sum(seg_i)) * ep.DT_S}
        accounted = 0.0
        for n in ("ctrl", "dev", "prot"):
            only = seg_bits == (1 << names[n])
            row[f"t_{n}_ms"] = int(np.count_nonzero(only)) * DT_MS
            row[f"E_{n}_uJ"] = v * float(np.sum(seg_i[only])) * ep.DT_S
            accounted += row[f"E_{n}_uJ"]
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
        row["dev_high_fraction"] = wb.head_high_fraction(seg_i[seg_bits == (1 << DEV)])
        row["prot_high_fraction"] = high_fraction(seg_i[seg_bits == (1 << PROT)], PROT_BLOCK_SAMPLES) \
            if op == "P1" else float("nan")
        for n in names:
            s, _ = runs[n]
            if np.any((s >= end) & (s < limit)):
                errors.append(f"after_end_{n}")
        row["errors"] = errors
        cycles.append(row)
    return cycles


def add_net(cycles: list, i_idle_ua: float, v_supply_mv: float) -> None:
    v = v_supply_mv / 1000.0
    for row in cycles:
        for n in ("ctrl", "dev", "prot", "cycle"):
            row[f"E_{n}_net_uJ"] = row[f"E_{n}_uJ"] - v * i_idle_ua * row[f"t_{n}_ms"] / 1e3


CYCLE_COLUMNS = ["cycle", "round", "sample", "split", "op", "start_sample", "end_sample", "t_cycle_ms", "t_ctrl_ms",
                 "t_dev_ms", "t_prot_ms", "t_gap_ms", "E_cycle_uJ", "E_ctrl_uJ", "E_dev_uJ", "E_prot_uJ", "E_gap_uJ",
                 "overlap_samples", "E_phases_uJ", "diff_pct", "dev_high_fraction", "prot_high_fraction",
                 "E_cycle_net_uJ", "E_ctrl_net_uJ", "E_dev_net_uJ", "E_prot_net_uJ", "errors"]


# ----------------------------------------------------------------------------- energy rows and summary


def f(c: dict, key: str) -> float | None:
    value = c.get(key)
    return None if value in (None, "", "nan") else float(value)


def session_groups(cycles: list) -> dict:
    """Per-session lists: P1 E_prot/t_prot/fraction per s, P0 E_dev per s, CONV E_dev, paired deltas per s."""
    out = {"prot": {s: [] for s in PROT_SPLITS}, "t_prot": {s: [] for s in PROT_SPLITS},
           "prot_net": {s: [] for s in PROT_SPLITS}, "prot_fraction": {s: [] for s in PROT_SPLITS},
           "dev_p0": {s: [] for s in PROT_SPLITS}, "t_dev_p0": {s: [] for s in PROT_SPLITS},
           "dev_p1": {s: [] for s in PROT_SPLITS}, "delta": {s: [] for s in PROT_SPLITS}, "conv": [], "t_conv": [],
           "conv_fraction": [], "dev_p0_fraction": {s: [] for s in PROT_SPLITS}}
    by_pair = {}
    for c in cycles:
        s, op = (int(c["split"]) if c.get("split") not in (None, "") else None), c["op"]
        if op == "CONV":
            out["conv"].append(f(c, "E_dev_uJ"))
            out["t_conv"].append(f(c, "t_dev_ms"))
            out["conv_fraction"].append(f(c, "dev_high_fraction"))
            continue
        if op == "P1":
            out["prot"][s].append(f(c, "E_prot_uJ"))
            out["t_prot"][s].append(f(c, "t_prot_ms"))
            out["prot_fraction"][s].append(f(c, "prot_high_fraction"))
            if f(c, "E_prot_net_uJ") is not None:
                out["prot_net"][s].append(f(c, "E_prot_net_uJ"))
            out["dev_p1"][s].append(f(c, "E_dev_uJ"))
        else:
            out["dev_p0"][s].append(f(c, "E_dev_uJ"))
            out["t_dev_p0"][s].append(f(c, "t_dev_ms"))
            out["dev_p0_fraction"][s].append(f(c, "dev_high_fraction"))
        by_pair.setdefault((int(c["round"]), s), {})[op] = f(c, "E_dev_uJ") + f(c, "E_prot_uJ")
    for (_, s), pair in by_pair.items():
        if "P1" in pair and "P0" in pair:
            out["delta"][s].append(pair["P1"] - pair["P0"])
    return out


def table_iii_off(column: str = "E_dev_uJ_mean") -> dict:
    import csv
    with TABLE_III_OFF.open(encoding="utf-8", newline="") as handle:
        return {int(r["split"]): float(r[column]) for r in csv.DictReader(handle)}


# W9-D11 (pre-declared 09/11): different-day comparison of the radio-off E_dev, raw |delta| < 10 % AND core
# |delta| <= 2 % (s >= 2) / <= 8 % (s <= 1). W10-D1: the P0 cycles of the prot sessions try it early, report only.
CROSS_DAY_RAW_PCT = 10.0
CROSS_DAY_CORE_PCT = {"s>=2": 2.0, "s<=1": 8.0}


def cross_day(groups_by_session: dict) -> dict:
    """W9-D11 on the P0 cycles (CTRL + HEAD, radio off) vs week 9 Table III (pooled raw and core E_dev)."""
    import week9_figures as w9f
    off, off_core = table_iii_off(), table_iii_off("E_dev_core_uJ")
    per_s, ok = {}, True
    for s in PROT_SPLITS:
        sess = [k for k in groups_by_session if groups_by_session[k]["dev_p0"][s]]
        if not sess or s not in off:
            continue
        raw = wa.pooled({k: groups_by_session[k]["dev_p0"][s] for k in sess})
        fractions = {k: groups_by_session[k].get("dev_p0_fraction", {}).get(s) or [] for k in sess}
        cores = {k: w9f.core_fit(fractions[k], groups_by_session[k]["dev_p0"][s])["core"]
                 for k in sess if len(fractions[k]) == len(groups_by_session[k]["dev_p0"][s])}
        core = float(np.mean(list(cores.values()))) if cores else None
        raw_pct = 100.0 * (raw["mean"] - off[s]) / off[s]
        core_pct = 100.0 * (core - off_core[s]) / off_core[s] if core is not None else None
        limit = CROSS_DAY_CORE_PCT["s>=2" if s >= 2 else "s<=1"]
        raw_ok = abs(raw_pct) < CROSS_DAY_RAW_PCT
        core_ok = core_pct is not None and abs(core_pct) <= limit
        per_s[str(s)] = {"E_dev_P0_uJ": raw["mean"], "E_dev_week9_uJ": off[s], "raw_delta_pct": raw_pct,
                         "raw_pass": raw_ok, "core_per_session_uJ": cores, "core_uJ": core,
                         "core_week9_uJ": off_core[s], "core_delta_pct": core_pct, "core_limit_pct": limit,
                         "core_pass": core_ok, "pass": raw_ok and core_ok,
                         "reading": ("same" if raw_ok and core_ok else "REG0 mode share only (raw fails, core holds)"
                                     if core_ok else "real change: find the cause (core fails)")}
        ok = ok and raw_ok and core_ok
    return {"rule": "W9-D11: raw |delta| < 10 % AND core |delta| <= 2 % (s >= 2) / <= 8 % (s <= 1) vs week 9 "
                    "Table III; report only (Table III keeps the week 9 numbers)",
            "pass": ok and len(per_s) == len(PROT_SPLITS), "per_s": per_s}


def summary(groups_by_session: dict, tprot: dict | None = None) -> dict:
    """>= 2 sessions -> per s: E_prot pooled (gross, net), core per session (50 us blocks), t_prot marker (+ DWT
    if given), paired delta, E_dev P0 radio off; E_conv,min; TC5 CI95/mean < 10 %; W10-D2 conv_rule; ratios."""
    import week9_figures as w9f
    sessions = list(groups_by_session)
    per_s, prot_means = {}, {}
    for s in PROT_SPLITS:
        g = {k: groups_by_session[k] for k in sessions}
        cores = {k: w9f.core_fit(g[k]["prot_fraction"][s], g[k]["prot"][s]) for k in sessions}
        entry = {
            "E_prot_uJ": wa.pooled({k: g[k]["prot"][s] for k in sessions}),
            "E_prot_net_uJ": wa.pooled({k: g[k]["prot_net"][s] for k in sessions}),
            "E_prot_core": {"per_session": {k: c["core"] for k, c in cores.items()},
                            "r2": {k: c["r2"] for k, c in cores.items()},
                            "high_fraction_mean": {k: c["high_fraction_mean"] for k, c in cores.items()},
                            "mean": float(np.mean([c["core"] for c in cores.values()])),
                            "range_pct": wa.spread_pct(c["core"] for c in cores.values()),
                            "block_samples": PROT_BLOCK_SAMPLES},
            "t_prot_ms": wa.pooled({k: g[k]["t_prot"][s] for k in sessions}),
            "delta_P1_minus_P0_dev_plus_prot_uJ": wa.pooled({k: g[k]["delta"][s] for k in sessions}),
            "E_dev_P0_radio_off_uJ": wa.pooled({k: g[k]["dev_p0"][s] for k in sessions}),
            "t_dev_P0_ms": wa.pooled({k: g[k]["t_dev_p0"][s] for k in sessions}),
        }
        e = entry["E_prot_uJ"]
        entry["ci95_rel_pct"] = e.get("ci95_rel_pct")
        entry["ci95_rel_below_10pct"] = e.get("ci95_rel_pct") is not None and e["ci95_rel_pct"] < wa.CI_LIMIT_PCT
        if tprot and str(s) in tprot.get("t_prot_dwt_ms", {}):
            entry["t_prot_dwt_ms"] = tprot["t_prot_dwt_ms"][str(s)]
        per_s[str(s)] = entry
        prot_means[s] = entry["E_prot_uJ"]["session_means"]
    conv = wa.pooled({k: groups_by_session[k]["conv"] for k in sessions})
    conv_cores = {k: w9f.core_fit(groups_by_session[k]["conv_fraction"], groups_by_session[k]["conv"]) for k in sessions}
    rule = wa.conv_rule(prot_means, conv["session_means"])
    off = table_iii_off()
    layer_before = {s: off[s] - off[s - 1] for s in PROT_SPLITS if s >= 1 and s in off and s - 1 in off}
    e_prot = {s: per_s[str(s)]["E_prot_uJ"]["mean"] for s in PROT_SPLITS}
    e_dev = {s: per_s[str(s)]["E_dev_P0_radio_off_uJ"]["mean"] for s in PROT_SPLITS}
    return {
        "sessions": sessions, "per_s": per_s,
        "E_conv_min_uJ": conv, "E_conv_min_core": {k: c["core"] for k, c in conv_cores.items()},
        "t_conv_ms": wa.pooled({k: groups_by_session[k]["t_conv"] for k in sessions}),
        "t_conv_dwt_ms": (tprot or {}).get("t_conv_dwt_ms"),
        "tc5_ci95_below_10pct_every_s": all(per_s[str(s)]["ci95_rel_below_10pct"] for s in PROT_SPLITS),
        "w10_d2_conv_rule": rule,
        "ratios": wa.prot_ratios(e_prot, conv["mean"], layer_before, e_dev),
        "ratio_note": "over_layer_before_s uses the week 9 radio-off E_dev(s) - E_dev(s-1) (the head segment just "
                      "before s; s1: features.0 + ReLU)",
        "E_dev_P0_vs_week9_table_iii_pct": {str(s): 100.0 * (e_dev[s] - off[s]) / off[s] for s in PROT_SPLITS if s in off},
        "E_dev_vs_week9_note": "W9-D11 different-day rule, report only (Table III keeps the week 9 numbers)",
        "w9_d11_cross_day": cross_day(groups_by_session),
    }
