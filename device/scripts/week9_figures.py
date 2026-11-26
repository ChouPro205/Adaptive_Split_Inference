#!/usr/bin/env python3
"""Week 9 result tables and IEEE figures (no device I/O).

Two steps, each writing a NEW directory:

  tables   reads the PPK2 sessions of the week 9 lab root (folder names fixed below) and writes
           per-cycle tables, the pooled E_dev(s) table (Table III draft), the KV260 s = 2 phase table
           (B5), the REG0 two-level analysis and one CSV per figure (the plotted numbers):
             cycles_dev_<tag>.csv      every cycle of a dev session (recomputed with week9_ppk2.analyze_dev,
                                       incl. dev_high_fraction, which the 29/10 cycles.csv lacked)
             cycles_kv260_<tag>.csv    every cycle of a KV260 session + dev/prot high fraction
             gaps_kv260_<tag>.csv      every connected-idle gap between two cycles (P_conn)
             table_iii_e_dev.csv       per s: pooled E_dev (3 board sessions), session means, range,
                                       core E_dev, high fraction, net, t_dev, DWT, quantization share, bytes
             table_kv260_s2.csv        per session and rho: every phase (gross, net) mean and CI95
             week9_analysis.json       everything above + method, decisions, inputs (SHA-256)
             fig_*.csv                 data of each figure
  figures  reads a tables directory and writes figures/ (vector PDF, TrueType fonts + 600 dpi PNG)

Core E ("lõi", B4 29/10, decided for the paper at B6, 09/11): the compute current on the 5 V VBUS bench has two
levels (~2.6 / ~4.4-4.8 mA) from the REG0 DC/DC at light load; the share of 1 ms HEAD blocks above 3.6 mA (high
fraction) drifts between sessions and explains most of the E_dev variance. Per s and session, a least-squares line
E = a + b * high_fraction over the cycles gives the core a = E with no high-level block.

  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week9_figures.py tables --lab D:\\HUST\\ASI_week9 \\
      --week8-b5 D:\\HUST\\ASI_week8\\B5-official-20261026-1328 --out <new dir>
  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week9_figures.py figures --tables <that dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week7_figures as w7f  # noqa: E402
import week9_common as w9  # noqa: E402
import week9_ppk2 as w9p  # noqa: E402

FS = ep.SAMPLE_RATE_HZ
DT_MS = 1e3 / FS
HIGH_UA = w9p.HIGH_LEVEL_UA
DEV_SESSIONS = {"B4-1": "B4-s1-20261029-1302", "B4-2": "B4-s2-20261029-1320", "B4-3": "B4-s3-20261029-1340"}
REG_SESSIONS = {"REG0-LDO": "B4-reg0ldo-20261029-1405", "REG1-LDO": "B4-reg1ldo-20261029-1423"}
KV_SESSIONS = {"B5-1": "B5-20261109-1419", "B5-4": "B5-20261109-1509-p4"}
# supplementary: trace check FAIL only no_data_loss (48 samples lost between two cycles), not pooled
KV_SUPPL = {"B5-2": "B5-20261109-1438-p2"}
KV_BTSNOOP = {"B5-1": "phien1/b5_p1.btsnoop", "B5-2": "phien2/b5_p2.btsnoop",
              "B5-4": "phien4/b5_p4.btsnoop"}     # under --kv260-logs
VERIFY = "verify-20261029-1223"
WAVE_SPLITS = (0, 2, 10)
GAP_GUARD_MS = 10.0          # connected-idle window = [cycle end + 10 ms, next cycle start - 10 ms)
OVERVIEW_BIN_MS = 50.0
HEAD_TRIM_MS = (10.0, 5.0)   # histogram of 1 ms HEAD blocks: drop the first 10 ms and last 5 ms of each HEAD
# Pre-declared 09/11 (before any week 13 data) for the week 13 D0/D4 cross-day comparison:
CORE_RULE_PCT = {"s>=2": 2.0, "s<=1": 8.0}


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
            w.writerow([f"{v:.6g}" if isinstance(v, float) else v for v in row])


def read_csv(path: Path) -> list:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = float(v) if v not in ("", None) and k not in ("tag", "rho", "errors", "kind", "label",
                                                                     "stage", "config") else v
            except ValueError:
                pass
    return rows


def core_fit(fraction, energy) -> dict:
    """E = a + b * high_fraction by least squares; a = core E (no high-level block)."""
    f, e = np.asarray(fraction, float), np.asarray(energy, float)
    out = {"n": int(e.size), "mean": float(e.mean()), "high_fraction_mean": float(f.mean())}
    if e.size < 3 or float(np.std(f)) == 0.0:
        out.update(core=float(e.mean()), slope=None, r2=None, core_se=None)
        return out
    b, a = np.polyfit(f, e, 1)
    resid = e - (a + b * f)
    r2 = 1.0 - float(np.sum(resid ** 2)) / float(np.sum((e - e.mean()) ** 2)) if np.ptp(e) else None
    s2 = float(np.sum(resid ** 2)) / (e.size - 2)
    sxx = float(np.sum((f - f.mean()) ** 2))
    se_a = math.sqrt(s2 * (1.0 / e.size + f.mean() ** 2 / sxx))
    out.update(core=float(a), slope=float(b), r2=r2, core_se=se_a)
    return out


def spread_pct(values) -> float | None:
    v = [x for x in values if x is not None]
    return 100.0 * (max(v) - min(v)) / float(np.mean(v)) if len(v) > 1 and np.mean(v) else None


def head_blocks(current: np.ndarray) -> np.ndarray:
    """1 ms block means of one HEAD (D0-only samples)."""
    n = current.size // 100
    return current[:n * 100].reshape(n, 100).mean(axis=1) if n else current[:0]


def tdsum(verify_dir: Path) -> dict:
    """split -> (head ms, quantization ms, total ms) of the dev-usb TDEV ALL run (DWT, IRQs locked)."""
    out = {}
    for line in (verify_dir / "cdc.log").read_text(encoding="utf-8", errors="replace").splitlines():
        _, _, msg = line.partition("\t")
        if msg.startswith("TDSUM "):
            f = dict(x.split("=", 1) for x in msg.split()[1:] if "=" in x)
            hz = float(f["cpu_hz"]) / 1e3
            out[int(f["s"])] = tuple(int(f[k]) / 100.0 / hz for k in ("head_mean_x100", "quant_mean_x100",
                                                                       "total_mean_x100"))
    if sorted(out) != list(range(w9.SPLITS)):
        raise SystemExit(f"{verify_dir}: TDSUM lines do not cover s = 0..10")
    return out


def btsnoop_link(path: Path) -> dict:
    """LE connection parameters and PHY updates from a btmon -w file (monitor 2001 or H4 1002)."""
    data = Path(path).read_bytes()
    if data[:8] != b"btsnoop\0":
        raise SystemExit(f"{path}: not a btsnoop file")
    _, link = struct.unpack(">II", data[8:16])
    pos, events = 16, []
    while pos + 24 <= len(data):
        _, incl, flags, _, ts = struct.unpack(">IIIIq", data[pos:pos + 24])
        pkt = data[pos + 24:pos + 24 + incl]
        pos += 24 + incl
        if link == 2001:
            if flags & 0xFFFF != 3:          # monitor opcode 3 = HCI event
                continue
            ev = pkt
        elif link == 1002:
            if not pkt or pkt[0] != 0x04:
                continue
            ev = pkt[1:]
        else:
            raise SystemExit(f"{path}: datalink {link} not handled")
        if len(ev) < 3 or ev[0] != 0x3E:
            continue
        p, sub = ev[2:], ev[2]
        t_s = ts / 1e6
        if sub in (0x01, 0x0A, 0x29) and p[1] == 0:
            off = 12 if sub == 0x01 else 24
            itv, lat, to = struct.unpack("<HHH", p[off:off + 6])
            events.append({"t_s": t_s, "event": "connection_complete", "interval_ms": itv * 1.25,
                           "latency": lat, "timeout_ms": to * 10})
        elif sub == 0x03 and p[1] == 0:
            itv, lat, to = struct.unpack("<HHH", p[4:10])
            events.append({"t_s": t_s, "event": "connection_update", "interval_ms": itv * 1.25,
                           "latency": lat, "timeout_ms": to * 10})
        elif sub == 0x0C and p[1] == 0:
            names = {1: "1M", 2: "2M", 3: "Coded"}
            events.append({"t_s": t_s, "event": "phy_update", "tx_phy": names.get(p[4], p[4]),
                           "rx_phy": names.get(p[5], p[5])})
    params = [e for e in events if "interval_ms" in e]
    return {"source": str(path), "sha256": sha256(path), "datalink": link, "events": events,
            "final_interval_ms": params[-1]["interval_ms"] if params else None,
            "final_latency": params[-1]["latency"] if params else None,
            "final_timeout_ms": params[-1]["timeout_ms"] if params else None,
            "phy_updates": [e for e in events if e["event"] == "phy_update"]}


# ----------------------------------------------------------------------------- dev sessions


def analyze_dev_session(folder: Path) -> tuple:
    """week9_ppk2.analyze_dev on a session-dev directory -> (result, sliced trace)."""
    record = load_json(folder / "session.json")
    sample_set = w9.w8.load_set(Path(record["samples"]))
    refs = w9.load_refs(Path(record["refs"]), sample_set)
    dwt = w9p.dwt_reference(Path(record["dwt_verify"]))
    trace = w9p.load_raw_chunked(folder / "ppk2")
    result = w9p.analyze_dev(trace, dwt, {s: refs[(0, s)].bytes_payload for s in range(w9.SPLITS)},
                             ignore_counter=record.get("ignore_counter", False))
    on = int(trace.info.get("dut_power_on_sample", 0))
    off = int(trace.info.get("dut_power_off_sample", trace.n))
    return result, ep.slice_trace(trace, on, off), record


DEV_COLUMNS = ("cycle", "round", "sample", "split", "bytes_payload", "start_sample", "end_sample", "t_dev_ms",
               "dwt_ms", "E_dev_uJ", "E_dev_net_uJ", "E_cycle_uJ", "mean_dev_uA", "dev_high_fraction")


def head_histogram(trace, cycles, splits_min=2) -> np.ndarray:
    lo, hi = int(HEAD_TRIM_MS[0] * FS / 1e3), int(HEAD_TRIM_MS[1] * FS / 1e3)
    blocks = []
    for c in cycles:
        if c.get("split", 0) < splits_min or c["errors"]:
            continue
        seg = trace.current_ua[c["start_sample"]:c["end_sample"]]
        bits = trace.bits[c["start_sample"]:c["end_sample"]]
        head = seg[bits == (1 << w9p.DEV)]
        if head.size > lo + hi + 100:
            blocks.append(head_blocks(head[lo:head.size - hi]))
    return np.concatenate(blocks) if blocks else np.zeros(0)


# ----------------------------------------------------------------------------- KV260 sessions


def analyze_kv_session(folder: Path) -> dict:
    trace = w9p.load_raw_chunked(folder / "ppk2")
    summary = load_json(folder / "analysis" / "summary.json")
    cycles = read_csv(folder / "analysis" / "cycles.csv")
    v = trace.v_supply_mv / 1000.0
    for c in cycles:
        a, b = int(c["start_sample"]), int(c["end_sample"])
        seg, bits = trace.current_ua[a:b], trace.bits[a:b]
        head = seg[bits == (1 << 0)]
        blk = head_blocks(head)
        c["dev_high_fraction"] = float(np.mean(blk > HIGH_UA)) if blk.size else float("nan")
        prot = seg[bits == (1 << 1)]
        c["prot_high_fraction"] = float(np.mean(prot > HIGH_UA)) if prot.size else float("nan")
    guard = int(GAP_GUARD_MS * FS / 1e3)
    gaps = []
    for k, (c0, c1) in enumerate(zip(cycles, cycles[1:])):
        lo, hi = int(c0["end_sample"]) + guard, int(c1["start_sample"]) - guard
        if hi - lo < FS // 10:
            continue
        seg = trace.current_ua[lo:hi]
        markers = int(np.count_nonzero(trace.bits[lo:hi] & 0x1F))
        gaps.append({"gap": k, "start_sample": lo, "duration_ms": (hi - lo) * DT_MS, "mean_uA": float(seg.mean()),
                     "P_gross_mW": v * float(seg.mean()) / 1e3, "markers_high_samples": markers})
    i_idle = summary["I_idle_uA"]
    for g in gaps:
        g["P_net_mW"] = v * (g["mean_uA"] - i_idle) / 1e3
    return {"cycles": cycles, "gaps": gaps, "summary": summary, "trace": trace, "v": v, "I_idle_uA": i_idle}


PHASES = ("ctrl", "dev", "prot", "tx", "wait", "gap", "cycle")


# ----------------------------------------------------------------------------- tables step


def cmd_tables(args) -> int:
    lab, out = Path(args.lab), Path(args.out)
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    out.mkdir(parents=True)
    inputs, analysis = {}, {"schema": "week9-analysis/1", "created_utc": datetime.now(timezone.utc).isoformat(),
                            "tool_sha256": {n: sha256(HERE / n) for n in ("week9_figures.py", "week9_ppk2.py",
                                                                         "energy_phases.py", "week7_figures.py")}}
    timing = tdsum(lab / VERIFY)
    inputs[f"{VERIFY}/cdc.log"] = sha256(lab / VERIFY / "cdc.log")

    # --- board dev sessions (B4) + regulator experiments
    dev, regs, hist = {}, {}, {}
    for tag, name in {**DEV_SESSIONS, **REG_SESSIONS}.items():
        folder = lab / name
        cap = load_json(folder / "ppk2" / "capture.json")
        inputs[f"{name}/ppk2/raw.bin"] = cap["raw_sha256"]
        result, trace, record = analyze_dev_session(folder)
        s = result["summary"]
        status_ok = s["checks"]
        cycles = [c for c in result["cycles"] if not c["errors"]]
        write_csv(out / f"cycles_dev_{tag}.csv", list(DEV_COLUMNS),
                  [[c.get(k, "") for k in DEV_COLUMNS] for c in result["cycles"]])
        hist[tag] = head_histogram(trace, result["cycles"])
        info = {"folder": name, "temp_room_C": record.get("temp_room_C"), "I_idle_uA": s["I_idle_uA"],
                "idle_vs_week2_pct": s["idle_vs_week2_pct"], "cycles_valid": len(cycles),
                "regulator": (record.get("image") or {}).get("regulator", "board"),
                "high_fraction_by_fifth": s["dev_high_fraction_by_fifth"],
                "checks_failed_now": [k for k, v in status_ok.items() if not v]}
        (dev if tag in DEV_SESSIONS else regs)[tag] = {"info": info, "cycles": cycles}
        if tag == "B4-1":
            figure_data_from_dev_trace(out, trace, result)
        del trace

    # Table III: pooled E_dev(s) over the three board sessions
    rows, table = [], []
    for split in range(w9.SPLITS):
        per = {}
        for tag, d in dev.items():
            g = [c for c in d["cycles"] if c["split"] == split]
            fit = core_fit([c["dev_high_fraction"] for c in g], [c["E_dev_uJ"] for c in g])
            per[tag] = {"E_dev_uJ": ep.describe(c["E_dev_uJ"] for c in g),
                        "E_dev_net_uJ": ep.describe(c["E_dev_net_uJ"] for c in g),
                        "t_dev_ms": ep.describe(c["t_dev_ms"] for c in g), "core": fit}
        pooled_cycles = [c for d in dev.values() for c in d["cycles"] if c["split"] == split]
        e = ep.describe(c["E_dev_uJ"] for c in pooled_cycles)
        net = ep.describe(c["E_dev_net_uJ"] for c in pooled_cycles)
        t = ep.describe(c["t_dev_ms"] for c in pooled_cycles)
        means = [per[k]["E_dev_uJ"]["mean"] for k in dev]
        cores = [per[k]["core"]["core"] for k in dev]
        head_ms, quant_ms, total_ms = timing[split]
        reg = {tag: ep.describe(c["E_dev_uJ"] for c in d["cycles"] if c["split"] == split) for tag, d in regs.items()}
        entry = {"split": split, "bytes_payload": pooled_cycles[0]["bytes_payload"], "n": e["n"],
                 "E_dev_uJ": e, "E_dev_net_uJ": net, "t_dev_ms": t,
                 "t_dev_dwt_ms": total_ms, "head_dwt_ms": head_ms, "quant_dwt_ms": quant_ms,
                 "quant_share_pct": 100.0 * quant_ms / total_ms,
                 "session_means_uJ": dict(zip(dev, means)), "session_range_pct": spread_pct(means),
                 "session_min_uJ": min(means), "session_max_uJ": max(means),
                 "core_uJ_by_session": dict(zip(dev, cores)), "core_uJ": float(np.mean(cores)),
                 "core_range_pct": spread_pct(cores),
                 "high_fraction_pct_by_session": {k: 100 * per[k]["core"]["high_fraction_mean"] for k in dev},
                 "core_r2_by_session": {k: per[k]["core"]["r2"] for k in dev},
                 "per_session": per, "regulator_experiment_E_dev_uJ": {k: v.get("mean") for k, v in reg.items()}}
        table.append(entry)
        rows.append([split, entry["bytes_payload"], e["n"], total_ms, t["mean"], entry["quant_share_pct"],
                     e["mean"], e["std"], e["ci95_half"], net["mean"], *means, entry["session_range_pct"],
                     entry["session_min_uJ"], entry["session_max_uJ"], *cores, entry["core_uJ"],
                     entry["core_range_pct"], *entry["high_fraction_pct_by_session"].values(),
                     *[reg[k].get("mean") for k in regs]])
    write_csv(out / "table_iii_e_dev.csv",
              ["split", "bytes_payload", "n", "t_dev_dwt_ms", "t_dev_marker_ms", "quant_share_pct",
               "E_dev_uJ_mean", "E_dev_uJ_std", "E_dev_uJ_ci95_half", "E_dev_net_uJ_mean",
               *[f"E_dev_uJ_{k}" for k in dev], "E_dev_session_range_pct", "E_dev_session_min_uJ",
               "E_dev_session_max_uJ", *[f"E_dev_core_uJ_{k}" for k in dev], "E_dev_core_uJ",
               "E_dev_core_range_pct", *[f"high_fraction_pct_{k}" for k in dev],
               *[f"E_dev_uJ_{k}" for k in regs]], rows)
    analysis["e_dev"] = {"sessions": {k: d["info"] for k, d in dev.items()},
                         "regulator_sessions": {k: d["info"] for k, d in regs.items()}, "splits": table}

    # fig (a), (b), (f), (g) data
    write_csv(out / "fig_e_dev_vs_split.csv",
              ["split", "bytes_payload", "E_dev_uJ_mean", "E_dev_session_min_uJ", "E_dev_session_max_uJ",
               "E_dev_ci95_half", "E_dev_core_uJ"],
              [[r["split"], r["bytes_payload"], r["E_dev_uJ"]["mean"], r["session_min_uJ"], r["session_max_uJ"],
                r["E_dev_uJ"]["ci95_half"], r["core_uJ"]] for r in table])
    write_csv(out / "fig_t_dev_marker_vs_dwt.csv", ["split", "tag", "t_dev_marker_ms", "t_dev_dwt_ms", "delta_pct"],
              [[r["split"], k, r["per_session"][k]["t_dev_ms"]["mean"], r["t_dev_dwt_ms"],
                100 * (r["per_session"][k]["t_dev_ms"]["mean"] - r["t_dev_dwt_ms"]) / r["t_dev_dwt_ms"]]
               for r in table for k in dev])
    write_csv(out / "fig_session_repeatability.csv", ["split", "tag", "raw_dev_pct", "core_dev_pct"],
              [[r["split"], k, 100 * (r["session_means_uJ"][k] - r["E_dev_uJ"]["mean"]) / r["E_dev_uJ"]["mean"],
                100 * (r["core_uJ_by_session"][k] - r["core_uJ"]) / r["core_uJ"]] for r in table for k in dev])
    write_csv(out / "fig_quant_share.csv", ["split", "head_ms", "quant_ms", "total_ms", "quant_share_pct"],
              [[s, *timing[s], 100 * timing[s][1] / timing[s][2]] for s in range(w9.SPLITS)])
    edges = np.arange(1500.0, 8001.0, 100.0)
    write_csv(out / "fig_reg0_histogram.csv", ["bin_low_uA", "bin_high_uA", *[f"share_{k}" for k in hist]],
              [[edges[i], edges[i + 1], *[float(np.histogram(h, edges)[0][i]) / max(1, h.size) for h in hist.values()]]
               for i in range(edges.size - 1)])

    # --- KV260 s = 2 sessions (B5)
    kv, kv_rows, gap_out = {}, [], {}
    logs = Path(args.kv260_logs) if args.kv260_logs else None
    extra = {"B5-week8-laptop": Path(args.week8_b5)} if args.week8_b5 else {}
    for tag, folder in {**{k: lab / v for k, v in {**KV_SESSIONS, **KV_SUPPL}.items()}, **extra}.items():
        cap = load_json(folder / "ppk2" / "capture.json")
        inputs[f"{folder.name}/ppk2/raw.bin"] = cap["raw_sha256"]
        r = analyze_kv_session(folder)
        del r["trace"]
        cols = ["cycle", "rho", "start_sample", "end_sample"] + [f"t_{p}_ms" for p in PHASES] + \
               [f"E_{p}_uJ" for p in PHASES] + ["E_dev_net_uJ", "E_prot_net_uJ", "E_tx_net_uJ", "E_wait_net_uJ",
                                                "E_cycle_net_uJ", "dev_high_fraction", "prot_high_fraction"]
        write_csv(out / f"cycles_kv260_{tag}.csv", cols, [[c.get(k, "") for k in cols] for c in r["cycles"]])
        write_csv(out / f"gaps_kv260_{tag}.csv", ["gap", "start_sample", "duration_ms", "mean_uA", "P_gross_mW",
                                                  "P_net_mW", "markers_high_samples"],
                  [[g[k] for k in ("gap", "start_sample", "duration_ms", "mean_uA", "P_gross_mW", "P_net_mW",
                                   "markers_high_samples")] for g in r["gaps"]])
        entry = {"folder": str(folder), "I_idle_uA": r["I_idle_uA"],
                 "conn_interval_trace_ms": (r["summary"].get("conn_interval_diagnostic") or {}).get("median_spacing_ms"),
                 "P_conn_gross_mW": ep.describe(g["P_gross_mW"] for g in r["gaps"]),
                 "P_conn_net_mW": ep.describe(g["P_net_mW"] for g in r["gaps"]),
                 "gap_ms": ep.describe(g["duration_ms"] for g in r["gaps"]),
                 "gaps_with_marker_samples": sum(1 for g in r["gaps"] if g["markers_high_samples"]), "rho": {}}
        for rho in ("P1", "P0"):
            g = [c for c in r["cycles"] if c["rho"] == rho and not c.get("errors")]
            stats = {f"{q}_{p}_{u}": ep.describe(float(c[f"{q}_{p}_{u}"]) for c in g)
                     for p in PHASES for q, u in (("E", "uJ"), ("t", "ms"))}
            stats.update({f"E_{p}_net_uJ": ep.describe(float(c[f"E_{p}_net_uJ"]) for c in g)
                          for p in ("dev", "prot", "tx", "wait", "cycle")})
            entry["rho"][rho] = {"stats": stats,
                                 "core_E_dev": core_fit([c["dev_high_fraction"] for c in g], [c["E_dev_uJ"] for c in g]),
                                 "core_E_prot": core_fit([c["prot_high_fraction"] for c in g],
                                                         [c["E_prot_uJ"] for c in g]) if rho == "P1" else None}
            for key, d in stats.items():
                kv_rows.append([tag, rho, key, d["n"], d.get("mean"), d.get("ci95_half"), d.get("ci95_rel_pct")])
        ek = folder / "energy_kv260_s2.json"
        if ek.exists():
            entry["paired_delta_p1_minus_p0"] = load_json(ek)["paired_delta_p1_minus_p0"]
            entry["status"] = load_json(ek)["status"]
        if logs and tag in KV_BTSNOOP and (logs / KV_BTSNOOP[tag]).exists():
            entry["btmon"] = btsnoop_link(logs / KV_BTSNOOP[tag])
        kv[tag] = entry
        gap_out[tag] = r["cycles"]
    write_csv(out / "table_kv260_s2.csv", ["tag", "rho", "quantity", "n", "mean", "ci95_half", "ci95_rel_pct"], kv_rows)

    # pooled KV260 s = 2 over the two PASS sessions (W9-D9/D10): mean of all cycles, session range, core
    pooled, prow = {}, []
    for rho in ("P1", "P0"):
        cyc = [c for t in KV_SESSIONS for c in gap_out[t] if c["rho"] == rho and not c.get("errors")]
        pooled[rho] = {}
        for p in ("dev", "prot", "tx", "wait", "cycle"):
            key = f"E_{p}_uJ"
            means = [kv[t]["rho"][rho]["stats"][key]["mean"] for t in KV_SESSIONS]
            d = ep.describe(float(c[key]) for c in cyc)
            core = None
            if p in ("dev", "prot") and not (p == "prot" and rho == "P0"):
                core = float(np.mean([kv[t]["rho"][rho][f"core_E_{p}"]["core"] for t in KV_SESSIONS]))
            pooled[rho][key] = {"pooled": d, "session_means": dict(zip(KV_SESSIONS, means)),
                                "session_range_pct": spread_pct(means), "core_mean": core}
            prow.append([rho, key, d["n"], d["mean"], d.get("ci95_half"), *means, spread_pct(means), core])
    pc = [kv[t]["P_conn_gross_mW"]["mean"] for t in KV_SESSIONS]
    pn = [kv[t]["P_conn_net_mW"]["mean"] for t in KV_SESSIONS]
    pooled["P_conn_gross_mW"] = {"mean": float(np.mean(pc)), "session_means": dict(zip(KV_SESSIONS, pc)),
                                 "session_range_pct": spread_pct(pc)}
    pooled["P_conn_net_mW"] = {"mean": float(np.mean(pn)), "session_means": dict(zip(KV_SESSIONS, pn)),
                               "session_range_pct": spread_pct(pn)}
    prow.append(["-", "P_conn_gross_mW", "", float(np.mean(pc)), "", *pc, spread_pct(pc), ""])
    prow.append(["-", "P_conn_net_mW", "", float(np.mean(pn)), "", *pn, spread_pct(pn), ""])
    write_csv(out / "table_kv260_s2_pooled.csv", ["rho", "quantity", "n", "pooled_mean", "pooled_ci95_half",
                                                   *[f"mean_{t}" for t in KV_SESSIONS], "session_range_pct",
                                                   "core_mean"], prow)
    analysis["kv260_s2_pooled"] = pooled

    # figure data: KV260 phases, E_dev(s2) vs high fraction (radio off B4, radio on B5)
    write_csv(out / "fig_kv260_phases.csv", ["tag", "rho", "phase", "E_uJ_mean", "E_uJ_ci95_half"],
              [[t, rho, p, kv[t]["rho"][rho]["stats"][f"E_{p}_uJ"]["mean"],
                kv[t]["rho"][rho]["stats"][f"E_{p}_uJ"].get("ci95_half")]
               for t in KV_SESSIONS for rho in ("P1", "P0") for p in ("dev", "prot", "tx", "wait")])
    scatter = [[t, "radio off (dev image)", c["dev_high_fraction"], c["E_dev_uJ"]]
               for t, d in dev.items() for c in d["cycles"] if c["split"] == 2]
    scatter += [[t, f"radio on, {c['rho']}", c["dev_high_fraction"], float(c["E_dev_uJ"])]
                for t in KV_SESSIONS for c in gap_out[t] if not c.get("errors")]
    write_csv(out / "fig_reg0_scatter_s2.csv", ["tag", "kind", "dev_high_fraction", "E_dev_uJ"], scatter)

    # radio-on vs radio-off E_dev at s = 2 (W9-D1)
    s2 = table[2]
    analysis["kv260_s2"] = kv
    analysis["w9_d1_s2_radio"] = {
        "radio_off_raw_pooled_uJ": s2["E_dev_uJ"]["mean"], "radio_off_core_uJ": s2["core_uJ"],
        "radio_on_raw_uJ": {t: {rho: kv[t]["rho"][rho]["stats"]["E_dev_uJ"]["mean"] for rho in ("P1", "P0")}
                            for t in kv},
        "radio_on_core_uJ": {t: {rho: kv[t]["rho"][rho]["core_E_dev"]["core"] for rho in ("P1", "P0")} for t in kv},
        "t_dev_radio_off_dwt_ms": s2["t_dev_dwt_ms"],
        "t_dev_radio_on_ms": {t: kv[t]["rho"]["P0"]["stats"]["t_dev_ms"]["mean"] for t in kv}}
    analysis["decisions_r4"] = DECISIONS_R4
    analysis["core_rule_week13_pct"] = CORE_RULE_PCT
    analysis["inputs_sha256"] = inputs
    (out / "week9_analysis.json").write_text(json.dumps(analysis, indent=2, default=float) + "\n", encoding="utf-8")
    print_summary(analysis)
    return 0


DECISIONS_R4 = [
    "W9-D9 Table III / LUT / simulation value = pooled gross mean of the valid sessions (what the device draws on "
    "the VBUS -> REG0 path on average); uncertainty = range of the session means, cycle-level CI95 also reported",
    "W9-D10 core E (intercept at high fraction 0) and the mean high fraction are reported next to every pooled "
    "E_dev / E_prot as the reproducibility measure and the lower envelope (REG0 always in its low mode)",
    "W9-D11 week 13 D0/D4 cross-day rule, pre-declared before the data: raw |delta| < 10 % per s (plan) AND core "
    "|delta| <= 2 % (s >= 2) / <= 8 % (s <= 1); raw fails + core passes = REG0 mode share (documented), core "
    "fails = real change, investigate before D5",
    "W9-D12 E7 simulation: base = pooled mean, sensitivity with the session min and max",
]


def figure_data_from_dev_trace(out: Path, trace, result) -> None:
    """fig (c) one CTRL->HEAD cycle at s0, s2, s10 (round 0); fig (d) whole session; fig (e) idle samples."""
    rows = []
    for split in WAVE_SPLITS:
        c = next(c for c in result["cycles"] if c.get("split") == split and c.get("round") == 0)
        a = c["start_sample"] - int(1e-3 * FS)
        b = c["end_sample"] + int(2e-3 * FS)
        step = 1 if b - a < 20000 else 10           # s10: 377 ms -> every 10th sample (0.1 ms)
        for k in range(a, b, step):
            rows.append([split, (k - c["start_sample"]) * DT_MS, float(trace.current_ua[k]),
                         int(trace.bits[k] >> w9p.CTRL & 1), int(trace.bits[k] >> w9p.DEV & 1)])
    write_csv(out / "fig_cycle_waveforms.csv", ["split", "t_ms", "current_uA", "D4_ctrl", "D0_head"], rows)
    s = result["summary"]
    n = int(OVERVIEW_BIN_MS * FS / 1e3)
    m = trace.n // n
    blk = trace.current_ua[:m * n].reshape(m, n)
    write_csv(out / "fig_session_overview.csv", ["t_s", "min_uA", "mean_uA", "max_uA"],
              [[i * OVERVIEW_BIN_MS / 1e3, float(lo), float(me), float(hi)]
               for i, (lo, me, hi) in enumerate(zip(blk.min(1), blk.mean(1), blk.max(1)))])
    st, idle = s["selftest"], s["idle"]
    stages = [["self-test", st["start_sample"] / FS if "start_sample" in st else 0.0, st["end_sample"] / FS],
              ["idle window", idle["start_sample"] / FS, idle["stop_sample"] / FS],
              ["550 cycles", result["cycles"][0]["start_sample"] / FS, result["cycles"][-1]["end_sample"] / FS]]
    write_csv(out / "fig_session_overview_stages.csv", ["stage", "start_s", "end_s"], stages)
    i = trace.current_ua[idle["start_sample"]:idle["stop_sample"]]
    edges = np.arange(0.0, 200.5, 1.0)
    h = np.histogram(i, edges)[0]
    write_csv(out / "fig_idle_histogram.csv", ["bin_low_uA", "bin_high_uA", "share"],
              [[edges[k], edges[k + 1], float(h[k]) / i.size] for k in range(h.size)])
    (out / "fig_idle_histogram_meta.json").write_text(json.dumps({
        "session": "B4-1", "mean_uA": float(i.mean()), "samples": int(i.size), "above_200uA_share":
        float(np.mean(i > 200.0)), "week2_mean_uA": w9p.WEEK2_IDLE_UA}, indent=2) + "\n", encoding="utf-8")


def print_summary(a: dict) -> None:
    print("split  E_dev pooled  range%  core  core-range%  high% (B4-1..3)")
    for r in a["e_dev"]["splits"]:
        hf = " ".join(f"{v:.1f}" for v in r["high_fraction_pct_by_session"].values())
        print(f"s{r['split']:<3d} {r['E_dev_uJ']['mean']:10.1f} {r['session_range_pct']:6.2f} {r['core_uJ']:9.1f} "
              f"{r['core_range_pct']:6.2f}  {hf}")
    for t, e in a["kv260_s2"].items():
        print(t, "P_conn gross", round(e["P_conn_gross_mW"]["mean"], 4), "mW net", round(e["P_conn_net_mW"]["mean"], 4),
              "interval", e["conn_interval_trace_ms"], "btmon", (e.get("btmon") or {}).get("final_interval_ms"))
        for rho, d in e["rho"].items():
            st = d["stats"]
            line = " ".join(f"{p} {st[f'E_{p}_uJ']['mean']:.1f}" for p in ("dev", "prot", "tx", "wait", "cycle"))
            ce = d["core_E_dev"]
            cp = d["core_E_prot"]
            print(f"  {rho}: {line} | core dev {ce['core']:.1f} (hf {100 * ce['high_fraction_mean']:.1f} %, R2 {ce['r2']})"
                  + (f" core prot {cp['core']:.2f} (R2 {cp['r2']})" if cp else ""))


# ----------------------------------------------------------------------------- figures step


def cmd_figures(args) -> int:
    src = Path(args.tables)
    out = src / "figures"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    out.mkdir()
    plt = w7f.pyplot()
    written = []
    a = load_json(src / "week9_analysis.json")

    # (a) E_dev(s): pooled mean, session range, core; payload bytes on a second axis
    rows = read_csv(src / "fig_e_dev_vs_split.csv")
    s = np.array([r["split"] for r in rows])
    mean = np.array([r["E_dev_uJ_mean"] for r in rows])
    lo = mean - np.array([r["E_dev_session_min_uJ"] for r in rows])
    hi = np.array([r["E_dev_session_max_uJ"] for r in rows]) - mean
    fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 2.3))
    ax.errorbar(s, mean, yerr=[lo, hi], fmt="o-", ms=3, mfc="black", color="black", capsize=2,
                label=r"$E_\mathrm{dev}$ pooled (bar: session range)")
    ax.plot(s, [r["E_dev_core_uJ"] for r in rows], "s--", ms=3, mfc="white", color="black",
            label=r"core $E_\mathrm{dev}$ (high fraction 0)")
    ax.set_yscale("log")
    ax.set_xlabel("Split point $s$")
    ax.set_ylabel(r"$E_\mathrm{dev}$ ($\mu$J, 5 V gross)")
    ax.set_xticks(range(11))
    ax2 = ax.twinx()
    ax2.plot(s, [r["bytes_payload"] for r in rows], "^:", ms=3, mfc="white", color="0.35", label="payload bytes")
    ax2.set_yscale("log")
    ax2.set_ylabel("Payload (B)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower center", bbox_to_anchor=(0.55, 0.02))
    w7f.save(fig, out, "fig_e_dev_vs_split", written)
    plt.close(fig)

    # (b) t_dev marker vs DWT
    rows = read_csv(src / "fig_t_dev_marker_vs_dwt.csv")
    fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 1.9))
    for (tag, mk), off in zip((("B4-1", "o"), ("B4-2", "s"), ("B4-3", "^")), (-0.2, 0.0, 0.2)):
        g = [r for r in rows if r["tag"] == tag]
        ax.plot([r["split"] + off for r in g], [r["delta_pct"] for r in g], mk, ms=3, mfc="white", color="black",
                label=tag)
    for y in (-1.0, 1.0):
        ax.axhline(y, ls="--", color="black", lw=0.5)
    ax.axhline(0.0, color="0.6", lw=0.5)
    ax.set_xticks(range(11))
    ax.set_xlabel("Split point $s$")
    ax.set_ylabel(r"$t_\mathrm{dev}$ marker $-$ DWT (%)")
    ax.legend(ncol=3, loc="upper right")
    w7f.save(fig, out, "fig_t_dev_marker_vs_dwt", written)
    plt.close(fig)

    # (c) one cycle CTRL -> HEAD at s0, s2, s10
    rows = read_csv(src / "fig_cycle_waveforms.csv")
    fig, axes = plt.subplots(1, 3, figsize=(w7f.TWO_COL, 1.9), gridspec_kw={"width_ratios": [1, 1.4, 2.2]})
    for ax, split in zip(axes, WAVE_SPLITS):
        g = [r for r in rows if r["split"] == split]
        t = np.array([r["t_ms"] for r in g])
        ax.plot(t, np.array([r["current_uA"] for r in g]) / 1e3, color="black", lw=0.4)
        top = max(r["current_uA"] for r in g) / 1e3
        ax.fill_between(t, top * 1.08, top * 1.08 + top * 0.06 * np.array([r["D4_ctrl"] for r in g]),
                        color="0.4", lw=0, step="post")
        ax.fill_between(t, top * 1.18, top * 1.18 + top * 0.06 * np.array([r["D0_head"] for r in g]),
                        color="0.75", lw=0, step="post")
        ax.set_title(f"$s={split}$")
        ax.set_xlabel("Time from CTRL (ms)")
        ax.set_ylim(0, top * 1.3)
        if split == WAVE_SPLITS[0]:
            ctrl_end = max(r["t_ms"] for r in g if r["D4_ctrl"])
            head_end = max(r["t_ms"] for r in g if r["D0_head"])
            ax.text(ctrl_end, top * 1.11, "  D4 CTRL", ha="left", va="center", fontsize=6)
            ax.text(head_end, top * 1.21, "  D0 HEAD", ha="left", va="center", fontsize=6)
    axes[0].set_ylabel("Current (mA)")
    w7f.save(fig, out, "fig_cycle_waveforms", written)
    plt.close(fig)

    # (d) whole session (B4-1)
    rows = read_csv(src / "fig_session_overview.csv")
    stages = read_csv(src / "fig_session_overview_stages.csv")
    fig, ax = plt.subplots(figsize=(w7f.TWO_COL, 1.9))
    t = np.array([r["t_s"] for r in rows])
    ax.fill_between(t, np.maximum([r["min_uA"] for r in rows], 1.0), [r["max_uA"] for r in rows], color="0.7",
                    lw=0, label="min-max per 50 ms")
    ax.plot(t, np.maximum([r["mean_uA"] for r in rows], 1.0), color="black", lw=0.4, label="mean per 50 ms")
    ax.set_yscale("log")
    boot = {"stage": "self-test + idle", "start_s": stages[0]["start_s"], "end_s": stages[1]["end_s"]}
    after = {"stage": "after session", "start_s": stages[2]["end_s"], "end_s": t[-1]}
    for st in (boot, stages[2], after):
        y = 2e4
        ax.annotate("", xy=(st["start_s"], y), xytext=(st["end_s"], y),
                    arrowprops={"arrowstyle": "<->", "lw": 0.5})
        ax.text((st["start_s"] + st["end_s"]) / 2, y * 1.5, st["stage"], ha="center", fontsize=6)
    ax.set_ylim(5, 1e5)
    ax.set_xlabel("Time after power-on (s)")
    ax.set_ylabel(r"Current ($\mu$A)")
    ax.legend(loc="lower right", ncol=2)
    w7f.save(fig, out, "fig_session_overview", written)
    plt.close(fig)

    # (e) idle histogram vs week 2
    rows = read_csv(src / "fig_idle_histogram.csv")
    meta = load_json(src / "fig_idle_histogram_meta.json")
    fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 1.9))
    ax.step([r["bin_low_uA"] for r in rows], [100 * r["share"] for r in rows], where="post", color="black")
    ax.axvline(meta["mean_uA"], color="black", ls="-", lw=0.75, label=f"week 9 mean {meta['mean_uA']:.2f} $\\mu$A")
    ax.axvline(meta["week2_mean_uA"], color="black", ls="--", lw=0.75,
               label=f"week 2 mean {meta['week2_mean_uA']:.2f} $\\mu$A")
    ax.set_xlim(15, 45)
    ax.set_xlabel(r"Idle current sample ($\mu$A)")
    ax.set_ylabel("Share of samples (%)")
    ax.legend()
    w7f.save(fig, out, "fig_idle_histogram", written)
    plt.close(fig)

    # (f) session repeatability: raw vs core
    rows = read_csv(src / "fig_session_repeatability.csv")
    fig, axes = plt.subplots(1, 2, figsize=(w7f.TWO_COL, 1.9), sharey=True)
    for ax, key, title in zip(axes, ("raw_dev_pct", "core_dev_pct"), ("raw session mean", "core (high fraction 0)")):
        for (tag, mk), off in zip((("B4-1", "o"), ("B4-2", "s"), ("B4-3", "^")), (-0.2, 0.0, 0.2)):
            g = [r for r in rows if r["tag"] == tag]
            ax.plot([r["split"] + off for r in g], [r[key] for r in g], mk, ms=3, mfc="white", color="black",
                    label=tag)
        ax.axhline(0, color="0.6", lw=0.5)
        ax.set_title(title)
        ax.set_xticks(range(11))
        ax.set_xlabel("Split point $s$")
    axes[0].set_ylabel("Deviation from pooled (%)")
    axes[1].legend(ncol=3, loc="lower right")
    w7f.save(fig, out, "fig_session_repeatability", written)
    plt.close(fig)

    # (g) quantization share of the HEAD phase (DWT)
    rows = read_csv(src / "fig_quant_share.csv")
    fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 1.9))
    s = [r["split"] for r in rows]
    ax.bar(s, [r["head_ms"] for r in rows], color="white", edgecolor="black", hatch="///", label="head(s)")
    ax.bar(s, [r["quant_ms"] for r in rows], bottom=[r["head_ms"] for r in rows], color="0.6", edgecolor="black",
           label="INT8/FP16 quantization")
    for r in rows:
        ax.text(r["split"], r["total_ms"] * 1.15, f"{r['quant_share_pct']:.0f}%", ha="center", fontsize=5.5)
    ax.set_yscale("log")
    ax.set_ylim(0.1, 2e4)
    ax.set_xticks(range(11))
    ax.set_xlabel("Split point $s$")
    ax.set_ylabel(r"$t_\mathrm{dev}$ (ms, DWT)")
    ax.legend(loc="upper left", ncol=2)
    w7f.save(fig, out, "fig_quant_share", written)
    plt.close(fig)

    # (h) REG0 two levels: 1 ms HEAD block histogram per regulator setting; E_dev(s2) vs high fraction
    rows = read_csv(src / "fig_reg0_histogram.csv")
    sc = read_csv(src / "fig_reg0_scatter_s2.csv")
    fig, axes = plt.subplots(1, 2, figsize=(w7f.TWO_COL, 2.0))
    ax = axes[0]
    x = [r["bin_low_uA"] / 1e3 for r in rows]
    for key, ls, label in (("share_B4-1", "-", "board: REG0 + REG1 DC/DC"), ("share_REG0-LDO", "--", "REG0 LDO"),
                           ("share_REG1-LDO", ":", "REG1 LDO")):
        ax.step(x, [100 * r[key] for r in rows], where="post", ls=ls, color="black", label=label)
    ax.axvline(HIGH_UA / 1e3, color="0.5", lw=0.5)
    ax.set_yscale("log")
    ax.set_ylim(0.01, 300)
    ax.set_xlabel("HEAD current, 1 ms block mean (mA)")
    ax.set_ylabel("Share of blocks (%)")
    ax.legend(loc="upper right")
    ax = axes[1]
    styles = {"radio off (dev image)": ("o", "white"), "radio on, P1": ("^", "black"), "radio on, P0": ("v", "0.6")}
    for kind, (mk, face) in styles.items():
        g = [r for r in sc if r["kind"] == kind]
        f, e = np.array([r["dev_high_fraction"] for r in g]), np.array([r["E_dev_uJ"] for r in g])
        ax.plot(100 * f, e, mk, ms=2.2, mfc=face, color="black", mew=0.4, label=kind)
        b, a0 = np.polyfit(f, e, 1)
        xx = np.array([0.0, max(f)])
        ax.plot(100 * xx, a0 + b * xx, color="black", lw=0.5, ls="--" if "off" in kind else "-")
    ax.set_xlabel("High-level fraction of HEAD (%)")
    ax.set_ylabel(r"$E_\mathrm{dev}$, $s=2$ ($\mu$J)")
    ax.legend(loc="upper left")
    w7f.save(fig, out, "fig_reg0_two_level", written)
    plt.close(fig)

    # (i) KV260 s = 2: energy per phase and rho, two sessions
    rows = read_csv(src / "fig_kv260_phases.csv")
    fig, ax = plt.subplots(figsize=(w7f.ONE_COL, 2.0))
    phases = ("dev", "prot", "tx", "wait")
    bars = (("B5-1", "P1", "white", "///"), ("B5-1", "P0", "white", ""), ("B5-4", "P1", "0.7", "///"),
            ("B5-4", "P0", "0.7", ""))
    width = 0.2
    for k, (tag, rho, face, hatch) in enumerate(bars):
        g = {r["phase"]: r for r in rows if r["tag"] == tag and r["rho"] == rho}
        xs = np.arange(len(phases)) + (k - 1.5) * width
        ax.bar(xs, [g[p]["E_uJ_mean"] for p in phases], width, yerr=[g[p]["E_uJ_ci95_half"] or 0 for p in phases],
               color=face, edgecolor="black", hatch=hatch, capsize=1.5, error_kw={"lw": 0.5},
               label=f"{tag} {rho}")
    ax.set_xticks(range(len(phases)))
    ax.set_xticklabels([w7f.SYMBOL[p] for p in phases])
    ax.set_ylabel(r"Energy per cycle ($\mu$J)")
    ax.set_ylim(0, 950)
    ax.legend(ncol=2, loc="upper center")
    w7f.save(fig, out, "fig_kv260_phases", written)
    plt.close(fig)

    (out / "figures.json").write_text(json.dumps({"written": written, "tables": str(src),
                                                  "tool_sha256": sha256(HERE / "week9_figures.py")}, indent=2) + "\n",
                                      encoding="utf-8")
    print(f"{len(written)} files -> {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    t = sub.add_parser("tables")
    t.add_argument("--lab", required=True, type=Path, help="week 9 lab root (D:/HUST/ASI_week9)")
    t.add_argument("--week8-b5", type=Path, help="week 8 B5 session (laptop peer) for comparison")
    t.add_argument("--kv260-logs", type=Path, help="folder with Trung's B5 logs (btsnoop) of 09/11")
    t.add_argument("--out", required=True, type=Path)
    t.set_defaults(func=cmd_tables)
    f = sub.add_parser("figures")
    f.add_argument("--tables", required=True, type=Path)
    f.set_defaults(func=cmd_figures)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
