#!/usr/bin/env python3
"""Week 8 PPK2 bench driver (B5: TC6, the week 8 energy image on the bench before week 9).

The dongle is powered by the PPK2 Source Meter (5000 mV) through the VBUS breakout, never by the
laptop USB (decision PPK2 VBUS). Capture, raw conversion and phase analysis are week7_ppk2.py,
measure_energy.py and energy_phases.py, unmodified (energy_phases counts P1/P0 by the D1 pulse, so
the W8-D1 paired order needs no change there).

  probe    PPK2 answers? (week7_ppk2.py probe)
  session  week 8 energy image: the laptop edge with the real tail (week8_edge.py) starts first and
           scans, then the capture powers the dongle; energy_phases analyze (200 cycles, 100 P1 +
           100 P0); cross-checks edge <-> trace; TC6: the window from 2 s after the last cycle to
           DUT power off (>= 20 s) is back at the firmware idle current (radio-off window after the
           self-test) and the edge never connected again (W8-D2: no advertising after the session).
  recheck  session checks again on an existing directory -> check_session_recheck.json
  note     end-of-session notes (temperature, photos, distance) (week7_ppk2.py note)
Each run writes a NEW --out directory: session.json, ppk2/, edge/ (peer.jsonl, tail.log, summary.json),
edge.out, analysis/, check_session.json. Exit 0 = PASS. Run with device/host/.venv; close nRF Connect
Power Profiler first (it holds the PPK2 port). The peer is the laptop (W8-D7 fallback), so the
connection interval recorded here is the laptop's, not the KV260's (TC8 needs the week 9 peer).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week7_ppk2 as w7p  # noqa: E402

ROOT = HERE.parents[1]
FS = ep.SAMPLE_RATE_HZ
PAIRS = 100                          # CONFIG_WEEK8_PAIRS of the energy image
POST_OFFSET_S = 2.0                  # link_disconnect -> LL terminate -> adv closed, well inside 2 s
POST_MIN_S = 20.0                    # TC6
IDLE_TOLERANCE_PCT = 10.0            # same tolerance as the week 7 idle check (TC3)
RADIO_SPIKE_UA = 3000.0              # radio TX/RX draws several mA; idle spikes stayed < 0.5 mA (week 7)
EDGE_LINGER_S = 15.0                 # the edge keeps scanning after the session: a re-advertising dongle reconnects
TOOLS = ("week8_ppk2.py", "week7_ppk2.py", "measure_energy.py", "energy_phases.py", "week8_edge.py",
         "week8_tail_worker.py", "week8_common.py", "week7_common.py", "week6_lab.py", "week6_common.py")


def image_info(image: Path | None, receipt: Path | None, allow_dirty: bool) -> dict:
    """A build_week8.ps1 folder (static check PASS, variant energy) + its flash_week8.ps1 receipt.
    A dirty-tree image is refused unless --allow-dirty (recorded: behaviour evidence, not the final image)."""
    if image is None:
        raise SystemExit("--image <build_week8.ps1 folder> is required")
    check = w7p.load_json(Path(image) / "week8_build_check.json")
    source = w7p.load_json(Path(image) / "source.json")
    info = {"image": str(image), "build_id": check.get("build_id"), "variant": check.get("variant"),
            "kernel": check.get("kernel"), "check_status": check.get("status"), "dirty": source.get("dirty"),
            "bin_sha256": check.get("bin_sha256"), "set_sha256": check.get("set_sha256"),
            "pairs": (check.get("kconfig") or {}).get("CONFIG_WEEK8_PAIRS")}
    if check.get("status") != "PASS" or check.get("variant") != "energy":
        raise SystemExit(f"{image}: static check not PASS or not the energy variant")
    if source.get("dirty") and not allow_dirty:
        raise SystemExit(f"{image}: built from a dirty tree (use --allow-dirty for behaviour checks only)")
    if info["pairs"] != str(PAIRS):
        raise SystemExit(f"{image}: CONFIG_WEEK8_PAIRS={info['pairs']}, this driver expects {PAIRS}")
    if receipt is not None:
        r = w7p.load_json(receipt)
        info["receipt"] = {"path": str(receipt), "exit_code": r.get("exit_code"), "build_id": r.get("build_id"),
                           "timestamp": r.get("timestamp"), "zip_sha256": r.get("zip_sha256")}
        if r.get("exit_code") != 0 or r.get("build_id") != info["build_id"]:
            raise SystemExit(f"{receipt}: DFU failed or receipt build differs from {image}")
    return info


def session_record(out: Path, args, extra: dict) -> None:
    w7p.write_new_json(out / "session.json", {
        "schema": "week8-ppk2-session/1",
        "kind": "session",
        "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "temp_room_C": args.temp_c,
        "v_supply_mV": 5000,
        "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "peer": "laptop edge, real tail (W8-D7 fallback), not KV260",
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS if (HERE / n).exists()},
        "photos": "add with: week8_ppk2.py note --out <this dir> --photo <file>",
        **extra,
    })


def start_edge(args, out: Path):
    log = open(out / "edge.out", "w", encoding="utf-8")
    cmd = [sys.executable, "-B", "-u", str(HERE / "week8_edge.py"), "--out", str(out / "edge"),
           "--samples", str(args.samples), "--pairs", str(PAIRS), "--key-file", str(args.key_file),
           "--max-s", str(args.seconds + args.edge_extra_s), "--linger-s", str(EDGE_LINGER_S)]
    print("+", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    deadline = time.monotonic() + 120.0   # the tail worker self-test runs before the scan starts
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        if "scanning for" in (out / "edge.out").read_text(encoding="utf-8", errors="replace"):
            time.sleep(args.edge_warmup_s)
            if proc.poll() is None:
                return proc, log
            break
        time.sleep(0.5)
    log.close()
    if proc.poll() is None:
        proc.terminate()
    raise SystemExit("edge did not start scanning (tail worker? Bluetooth off? see edge.out); "
                     "DUT was NOT powered, no nonce block used")


def post_session(trace: ep.Trace, cycles: list, i_idle: float | None) -> dict:
    """TC6 window: POST_OFFSET_S after the last cycle's end to DUT power off."""
    if not cycles:
        return {"found": False}
    start = int(cycles[-1]["end_sample"]) + int(POST_OFFSET_S * FS)
    stop = int(trace.info.get("dut_power_off_sample", trace.n))
    if stop - start < 2 * FS:
        return {"found": False, "duration_s": (stop - start) / FS}
    stats = ep.window_stats(trace, start, stop)
    current = trace.current_ua[start:stop]
    spikes = current > RADIO_SPIKE_UA
    seconds = [float(np.mean(current[k:k + FS])) for k in range(0, current.size - FS + 1, FS)]
    out = {"found": True, "offset_after_last_cycle_s": POST_OFFSET_S, "duration_s": stats["duration_s"],
           "mean_uA": stats["mean_uA"], "sample_std_uA": stats["sample_std_uA"], "max_uA": stats["max_uA"],
           "high_samples": stats["high_samples"], "samples_above_3mA": int(np.count_nonzero(spikes)),
           "per_second_mean_uA": {"min": min(seconds), "max": max(seconds)} if seconds else None,
           "I_idle_uA_firmware_window": i_idle}
    if i_idle:
        out["deviation_from_idle_pct"] = abs(stats["mean_uA"] - i_idle) / i_idle * 100.0
    return out


def match_cycles(cycles: list, records: list) -> dict:
    """Each trace cycle is one answered request, matched at two anchors: (A) trace TX end vs edge
    t_rx_ms (week 7 reference) and (B) trace WAIT end vs edge t_tx_done_ms. Windows can hand a
    complete request to the edge tens of ms late; the dongle then waits as much longer, so (A) moves
    and (B) does not (B5 2026-10-26: A off by up to 47 ms in 6/199 spacings, offset vs t_wait r = 0.80).
    Pass: equal counts and rho order, every cycle within INTERVAL_MATCH_MS (around the median) at
    one anchor at least, and every offset below half the smallest cycle spacing (no neighbour fits)."""
    if not cycles or len(cycles) != len(records):
        return {"pass": False, "reason": f"{len(cycles)} trace cycles vs {len(records)} edge requests"}
    start_ms = np.array([int(c["start_sample"]) for c in cycles]) * 1e3 / FS
    tx_end_ms = start_ms + np.array([sum(float(c[k]) for k in w7p.TX_END_PHASES) for c in cycles])
    wait_end_ms = tx_end_ms + np.array([float(c["t_wait_ms"]) for c in cycles])
    off_a = np.array([r["t_rx_ms"] for r in records], dtype=float) - tx_end_ms
    off_b = np.array([r["t_tx_done_ms"] for r in records], dtype=float) - wait_end_ms
    off_a = np.abs(off_a - np.median(off_a))
    off_b = np.abs(off_b - np.median(off_b))
    best = np.minimum(off_a, off_b)
    min_spacing = float(np.diff(start_ms).min()) if start_ms.size > 1 else float("inf")
    rho_equal = [c.get("rho") for c in cycles] == [r.get("rho") for r in records]
    limit = w7p.INTERVAL_MATCH_MS
    return {"pass": bool(rho_equal and best.max() < limit and max(off_a.max(), off_b.max()) < min_spacing / 2),
            "reference": "min(|trace TX end - edge t_rx_ms|, |trace WAIT end - edge t_tx_done_ms|), median-centred",
            "rho_order_equal": rho_equal,
            "max_abs_offset_ms": {"tx_end_vs_rx": float(off_a.max()), "wait_end_vs_reply": float(off_b.max()),
                                  "best_anchor": float(best.max())},
            "cycles_over_limit": {"tx_end_vs_rx": int(np.count_nonzero(off_a >= limit)),
                                  "wait_end_vs_reply": int(np.count_nonzero(off_b >= limit))},
            "min_cycle_spacing_ms": min_spacing,
            "edge_clock_resolution_s": time.get_clock_info("monotonic").resolution,
            "limit_ms": limit}


def evaluate(out: Path, args, meta: dict, kind: str) -> int:
    edge = w7p.load_json(out / "edge" / "summary.json") if (out / "edge" / "summary.json").exists() else {}
    summary = w7p.load_json(out / "analysis" / "summary.json")
    cycles = w7p.cycle_rows(out / "analysis")
    records = w7p.stub_records(out / "edge")
    match = match_cycles(cycles, records)
    trace = ep.load_raw_capture(out / "ppk2")
    post = post_session(trace, cycles, summary.get("I_idle_uA"))
    events = [json.loads(line) for line in (out / "edge" / "peer.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()] if (out / "edge" / "peer.jsonl").exists() else []
    connections = sum(1 for e in events if e.get("ev") == "connected")
    plan_rho = ["P1" if (k + slot) % 2 == 0 else "P0" for k in range(PAIRS) for slot in range(2)]
    a = summary["checks"]
    waits = [float(c["t_wait_ms"]) for c in cycles if c.get("t_wait_ms")]
    first_seq = edge.get("first_sequence")
    checks = {
        "selftest_D0_D4": a.get("selftest_D0_D4", False),
        "unused_channels_low": a.get("unused_channels_low", False),
        "capture_pass": meta["status"] == "PASS",
        "no_data_loss": a.get("no_data_loss", args.ignore_counter) and a.get("sample_rate_ok", False),
        "edge_pass_labels_100_per_rho": edge.get("status") == "PASS",
        "edge_answered_all": (edge.get("counters") or {}).get("response_sent") == 2 * PAIRS,
        "cycle_count_200": a.get("cycle_count", False),
        "p1_100_p0_100": a.get("p1_cycles", False) and a.get("p0_cycles", False),
        "trace_rho_order_paired": [c.get("rho") for c in cycles] == plan_rho,
        "all_cycles_valid_single_tx": a.get("all_cycles_valid", False),
        "one_cycle_per_request": match["pass"],
        "wait_below_timeout": bool(waits) and max(waits) < w7p.RESPONSE_TIMEOUT_MS,
        "idle_markers_low": a.get("idle_markers_low", False),
        "diff_below_3pct_all": a.get("diff_below_3pct_all", False),
        "nonce_above_prior": first_seq is not None and first_seq > args.prior_reserved_through,
        "TC6_post_window_at_least_20s": post.get("found", False) and post["duration_s"] >= POST_MIN_S,
        "TC6_post_mean_at_idle": post.get("deviation_from_idle_pct", float("inf")) <= IDLE_TOLERANCE_PCT,
        "TC6_no_radio_activity_after_session": post.get("found", False) and post["samples_above_3mA"] == 0,
        "TC6_post_markers_low": post.get("found", False) and not any(post["high_samples"].values()),
        "TC6_single_connection": connections == 1,
    }
    conn = summary.get("conn_interval_diagnostic") or {}
    details = {
        "analysis_status": summary["status"], "edge_status": edge.get("status"),
        "labels_equal_reference": edge.get("labels_equal_reference"),
        "first_p1_sequence": first_seq, "last_p1_sequence": edge.get("last_sequence"),
        "prior_reserved_through": args.prior_reserved_through,
        "interval_match": match, "interval_match_week7_single_anchor": w7p.match_intervals(cycles, records),
        "wait_ms_max": max(waits) if waits else None,
        "I_idle_uA_firmware_window": summary.get("I_idle_uA"),
        "post_session": post, "edge_connections": connections,
        "conn_interval_estimate_ms": conn.get("median_spacing_ms"),
        "conn_interval_note": "central = laptop (Windows); the week 9 peer decides TC8",
        "diff_pct": summary.get("diff_pct"),
        "ci95_rel_pct": {rho: {k: v.get("ci95_rel_pct") for k, v in g["stats"].items()
                               if k.startswith("E_") and not k.endswith("net_uJ")}
                         for rho, g in summary.get("groups", {}).items()},
        "capture": {k: meta[k] for k in ("samples", "dut_on_rate_deviation_pct", "raw_sha256",
                                         "host_max_gap_between_reads_s", "status")},
        "scope": "B5 behaviour check of the week 8 energy image (TC6); energy numbers are not week 9 results",
        "checker_sha256": {n: w7p.sha256(HERE / n) for n in ("week8_ppk2.py", "week7_ppk2.py", "energy_phases.py")},
    }
    if not summary.get("selftest", {}).get("found") and not cycles:
        print("NOTE: no self-test found. Ten 5 ms CTRL pulses = the image refused P1 (nonce not READY): "
              "flash energy-usb, read NONCE, never PROV ERASE.")
    p = post
    if p.get("found"):
        print(f"post-session {p['duration_s']:.1f} s: mean {p['mean_uA']:.3f} uA vs idle "
              f"{p.get('I_idle_uA_firmware_window')} uA, max {p['max_uA']:.1f} uA, >3 mA samples {p['samples_above_3mA']}")
    return w7p.finish(out, kind, checks, details)


def cmd_session(args) -> int:
    out = w7p.new_out(args.out)
    image = image_info(args.image, args.receipt, args.allow_dirty)
    session_record(out, args, {"image": image, "pairs": PAIRS, "samples": str(args.samples),
                               "prior_reserved_through": args.prior_reserved_through,
                               "key": "bench key file", "distance_note": args.note})
    proc, log = start_edge(args, out)
    try:
        meta = w7p.run_capture(args, out, "B5-week8-energy-session", args.seconds)
        try:
            proc.wait(timeout=args.edge_extra_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.terminate()
        log.close()
    print((out / "edge.out").read_text(encoding="utf-8", errors="replace")[-1500:])
    argv = ["analyze", "--raw", str(out / "ppk2"), "--expect-cycles", str(2 * PAIRS),
            "--expect-p1", str(PAIRS), "--expect-p0", str(PAIRS), "--out", str(out / "analysis")]
    if args.ignore_counter:
        argv.append("--ignore-counter")
    print("+ energy_phases.py", " ".join(argv))
    ep.main(argv)
    return evaluate(out, args, meta, "session")


def cmd_recheck(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != "week8-ppk2-session/1":
        raise SystemExit(f"{out} is not a week 8 session directory")
    a = argparse.Namespace(prior_reserved_through=record["prior_reserved_through"],
                           ignore_counter="--ignore-counter" in record.get("command", []))
    return evaluate(out, a, w7p.load_json(out / "ppk2" / "capture.json"), "session_recheck")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--port")
    p.add_argument("--stream-s", type=float, default=2.0)
    p.set_defaults(func=w7p.cmd_probe)

    p = sub.add_parser("session")
    p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--seconds", type=float, default=360.0,
                   help="DUT power ON time: ~280 s session + >= 60 s after it")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week8.ps1 folder (energy)")
    p.add_argument("--receipt", type=Path, help="DFU receipt JSON of flash_week8.ps1")
    p.add_argument("--allow-dirty", action="store_true", help="dirty-tree image: behaviour evidence only")
    p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    p.add_argument("--key-file", type=Path, required=True, help="32-byte bench key (never printed)")
    p.add_argument("--prior-reserved-through", type=int, required=True,
                   help="largest NONCE reserved_through seen before this boot")
    p.add_argument("--note", default="", help="e.g. dongle-laptop distance, placement")
    p.add_argument("--ignore-counter", action="store_true",
                   help="only after A1 showed bits 18-23 are not a sample counter")
    p.add_argument("--edge-warmup-s", type=float, default=2.0)
    p.add_argument("--edge-extra-s", type=float, default=120.0)
    p.set_defaults(func=cmd_session)

    p = sub.add_parser("recheck")
    p.add_argument("--out", type=Path, required=True, help="existing week 8 session directory")
    p.set_defaults(func=cmd_recheck)

    p = sub.add_parser("note")
    p.add_argument("--out", type=Path, required=True, help="existing session directory")
    p.add_argument("--temp-end-c", type=float)
    p.add_argument("--photo", type=Path, action="append", default=[])
    p.add_argument("--text", default="")
    p.set_defaults(func=w7p.cmd_note)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
