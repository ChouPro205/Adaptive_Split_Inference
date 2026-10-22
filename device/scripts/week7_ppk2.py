#!/usr/bin/env python3
"""Week 7 PPK2 bench driver: the dongle is powered by the PPK2 Source Meter (5000 mV) through the
VBUS breakout, never by the laptop USB (decision PPK2 VBUS). One command per lab step.

  probe    PPK2 answers? metadata, 100 kS/s, sample counter; DUT power stays OFF
  idle     session A1, week 2 Idle image: capture (default 125 s) -> mean of the 60 s window from
           5 s after DUT ON vs 25.417 uA within 10 % (TC3), logic LOW, no lost sample over the
           whole capture (TC2: the >= 120 s loss test)
  active   session A2, week 1 Active image: capture 15 s -> D0..D3 rotation, 500 ms each (TC1)
  session  session B, week 7 energy image: stub edge (BLE) starts first and scans, then the
           capture powers the dongle (boot recorded), energy_phases analyze, cross-checks
           stub <-> trace (TC1, TC2, TC5, TC6)
  recheck  session B checks again on an existing directory -> check_session_recheck.json
  note    end-of-session notes (temperature, photos) as a new file in a session directory
Each run writes a NEW --out directory: session.json (tools, image, receipt, temperature),
ppk2/ (measure_energy.py), check_<kind>.json; session also stub/ and analysis/. Exit 0 = PASS.
Run with device/host/.venv; close nRF Connect Power Profiler first (it holds the PPK2 port).
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
import measure_energy as me  # noqa: E402

ROOT = HERE.parents[1]
FS = ep.SAMPLE_RATE_HZ
WEEK2_IDLE_UA = 25.417               # results/week2: 60 s, Idle image, VBUS 5 V
RESPONSE_TIMEOUT_MS = 5000.0         # CONFIG_WEEK7_RESPONSE_TIMEOUT_MS
INTERVAL_MATCH_MS = 30.0             # two ticks of the stub clock (time.monotonic, ~15.6 ms on Windows)
TX_END_PHASES = ("t_ctrl_ms", "t_dev_ms", "t_prot_ms", "t_tx_ms")   # D2 falls = last notify done
TOOLS = ("week7_ppk2.py", "measure_energy.py", "energy_phases.py", "week7_stub_edge.py",
         "week7_common.py", "week6_lab.py", "week6_common.py")


def sha256(path: Path) -> str:
    return ep.sha256_file(Path(path))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))   # PowerShell writes a BOM


def write_new_json(path: Path, data) -> None:
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")


def new_out(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        raise SystemExit(f"refusing to reuse {path}; give a new --out directory")
    path.mkdir(parents=True)
    return path


def image_info(image: Path | None, receipt: Path | None, want_variant: str | None) -> dict:
    """Firmware under test: a build_week7.ps1 folder (static check PASS, clean tree) or a committed
    DFU ZIP (week 1/2 reference images), plus the DFU receipt of flash_week7.ps1 if given."""
    if image is None:
        return {"image": None}
    image = Path(image)
    info = {"image": str(image)}
    if image.is_dir():
        check = load_json(image / "week7_build_check.json")
        source = load_json(image / "source.json")
        info.update(build_id=check.get("build_id"), variant=check.get("variant"),
                    kernel=check.get("kernel"), check_status=check.get("status"),
                    dirty=source.get("dirty"), bin_sha256=check.get("bin_sha256"))
        if check.get("status") != "PASS" or source.get("dirty"):
            raise SystemExit(f"{image}: static check not PASS or dirty tree; not a measurement image")
        if want_variant and check.get("variant") != want_variant:
            raise SystemExit(f"{image}: variant {check.get('variant')!r}, this step needs {want_variant!r}")
    else:
        info.update(zip_sha256=sha256(image), zip_bytes=image.stat().st_size)
    if receipt is not None:
        r = load_json(receipt)
        info["receipt"] = {"path": str(receipt), "exit_code": r.get("exit_code"),
                           "build_id": r.get("build_id"), "timestamp": r.get("timestamp"),
                           "zip_sha256": r.get("zip_sha256")}
        if r.get("exit_code") != 0:
            raise SystemExit(f"{receipt}: DFU exit code {r.get('exit_code')}")
        if info.get("build_id") and r.get("build_id") != info["build_id"]:
            raise SystemExit(f"{receipt}: receipt build {r.get('build_id')} != image {info['build_id']}")
        if info.get("zip_sha256") and r.get("zip_sha256") not in (None, info["zip_sha256"]):
            raise SystemExit(f"{receipt}: receipt ZIP hash differs from {image}")
    return info


def session_record(out: Path, kind: str, args, extra: dict) -> None:
    write_new_json(out / "session.json", {
        "schema": "week7-ppk2-session/1",
        "kind": kind,
        "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "temp_room_C": getattr(args, "temp_c", None),
        "v_supply_mV": 5000,
        "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "tool_sha256": {n: sha256(HERE / n) for n in TOOLS if (HERE / n).exists()},
        "photos": "add with: week7_ppk2.py note --out <this dir> --photo <file>",
        **extra,
    })


def finish(out: Path, kind: str, checks: dict, details: dict) -> int:
    status = "PASS" if checks and all(checks.values()) else "FAIL"
    write_new_json(out / f"check_{kind}.json", {"schema": f"week7-ppk2-{kind}/1", "status": status,
                                               "checks": checks, **details})
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT {kind}: {status} -> {out}")
    return 0 if status == "PASS" else 1


def run_capture(args, out: Path, label: str, seconds: float) -> dict:
    meta = me.capture(args.port, 5000, seconds, out / "ppk2", label, args.temp_c, args.note or "",
                      args.pre_power_s)
    print(f"capture {meta['status']}: {meta['samples']} samples, DUT-on rate deviation "
          f"{meta['dut_on_rate_deviation_pct']:.4f} %, counter {meta['counter']}")
    return meta


def capture_checks(meta: dict, trace: ep.Trace, ignore_counter: bool) -> dict:
    out = {"capture_status_pass": meta["status"] == "PASS"}
    out.update(ep.data_loss_checks(trace, ignore_counter))
    if not ignore_counter:
        out["counter_available"] = bool(trace.info["counter"]["available"])
    return out


# ----------------------------------------------------------------------------- A1 / A2


def cmd_probe(args) -> int:
    return me.cmd_probe(args)


def cmd_idle(args) -> int:
    out = new_out(args.out)
    session_record(out, "idle", args, {"image": image_info(args.image, args.receipt, None),
                                       "expect_mean_uA": args.expect_mean_uA,
                                       "tolerance_pct": args.tolerance_pct})
    meta = run_capture(args, out, "A1-idle-week2", args.seconds)
    trace = ep.load_raw_capture(out / "ppk2")
    on = trace.info["dut_power_on_sample"]
    start = on + int(round(args.window_start_s * FS))
    stop = start + int(round(args.window_s * FS))
    if stop > trace.n:
        raise SystemExit("capture shorter than the idle window")
    stats = ep.window_stats(trace, start, stop)
    rel = abs(stats["mean_uA"] - args.expect_mean_uA) / args.expect_mean_uA * 100.0
    after_on = ep.window_stats(trace, on + FS, trace.n)
    checks = capture_checks(meta, trace, args.ignore_counter)
    checks.update({
        "capture_at_least_120_s": meta["dut_on_host_s"] >= 120.0,
        "idle_mean_within_tolerance": rel <= args.tolerance_pct,
        "logic_all_low_in_window": not any(stats["high_samples"].values()),
    })
    print(f"I_idle {stats['mean_uA']:.3f} uA (std {stats['sample_std_uA']:.3f}) vs "
          f"{args.expect_mean_uA} uA: {rel:.2f} % (limit {args.tolerance_pct} %)")
    if rel > args.tolerance_pct:
        print("STOP: idle differs > 10 % from week 2 -> check wiring, VBUS 5 V, image, temperature "
              "before any further capture (TC3)")
    return finish(out, "idle", checks, {
        "I_idle_uA": stats["mean_uA"], "deviation_pct": rel, "window": stats,
        "after_power_on_1s_to_end": {k: after_on[k] for k in ("mean_uA", "sample_std_uA",
                                                             "duration_s", "high_samples")},
        "counter": trace.info["counter"], "capture": {k: meta[k] for k in (
            "samples", "dut_on_samples", "dut_on_samples_expected", "dut_on_rate_deviation_pct",
            "host_max_gap_between_reads_s", "raw_sha256", "status")},
        "range_counts": trace.info["range_counts"]})


def cmd_active(args) -> int:
    out = new_out(args.out)
    session_record(out, "active", args, {"image": image_info(args.image, args.receipt, None)})
    meta = run_capture(args, out, "A2-active-week1", args.seconds)
    trace = ep.load_raw_capture(out / "ppk2")
    # Only DUT ON..OFF: the pulse running when the PPK2 cuts the power is truncated, not short.
    on = trace.info.get("dut_power_on_sample", 0)
    trace = ep.slice_trace(trace, on, trace.info.get("dut_power_off_sample", trace.n))
    rotation = ep.rotation_check(trace, (0, 1, 2, 3), 500.0, 5.0)
    # The week 1 image never drives P0.22: D4 may float, so it is reported, not gated.
    floating_d4 = rotation["stray_high_samples"].pop("D4", 0)
    stray_ok = not any(rotation["stray_high_samples"].values())
    checks = capture_checks(meta, trace, args.ignore_counter)
    checks.update({
        "rotation_order_D0_D3": rotation["order_errors"] == 0 and rotation["pulses"] >= 8,
        "rotation_width_500ms": rotation["width_errors"] == 0,
        "no_overlap": rotation["overlap_samples"] == 0,
        "D5_D7_low": stray_ok,
    })
    table = ep.pulse_table(trace, range(5))
    return finish(out, "active", checks, {
        "rotation": rotation, "D4_high_samples_week1_image": floating_d4,
        "pulses": {k: {"pulses": v["pulses"], "width_ms": v["width_ms"]} for k, v in table.items()},
        "counter": trace.info["counter"]})


# ----------------------------------------------------------------------------- B


def start_stub(args, out: Path):
    log = open(out / "stub.out", "w", encoding="utf-8")
    # -u: stdout goes to a file, unbuffered so the "scanning for" line is seen right away
    cmd = [sys.executable, "-B", "-u", str(HERE / "week7_stub_edge.py"), "--out", str(out / "stub"),
           "--split", str(args.split), "--expect-p1", str(args.p1), "--expect-p0", str(args.p0),
           "--max-s", str(args.seconds + args.stub_extra_s)]
    if args.key_file:
        cmd += ["--key-file", str(args.key_file)]
    print("+", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        text = (out / "stub.out").read_text(encoding="utf-8", errors="replace")
        if "scanning for" in text:
            time.sleep(args.stub_warmup_s)
            if proc.poll() is None:
                return proc, log
            break
        time.sleep(0.2)
    log.close()
    if proc.poll() is None:
        proc.terminate()
    raise SystemExit("stub edge did not start scanning (Bluetooth off? see stub.out); "
                     "DUT was NOT powered, no nonce block used")


def stub_records(stub_dir: Path) -> list:
    rows = []
    path = stub_dir / "peer.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("ev") == "request":
                rows.append(event)
    return rows


def cycle_rows(analysis: Path) -> list:
    import csv
    with open(analysis / "cycles.csv", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def match_intervals(cycles: list, records: list) -> dict:
    """End of TX on the trace (D2 falls when the last notify is done) vs the time the stub had the
    whole request: equal counts, equal rho order, and every spacing and every offset (around the
    median) within INTERVAL_MATCH_MS mean each trace cycle is one answered request. Cycle START
    spacing is not used: it differs from the arrival spacing by the change of t_tx between cycles
    (BLE connection events; B1 2026-10-22: first cycle t_tx 101.9 ms vs median 29 ms)."""
    if not cycles or len(cycles) != len(records):
        return {"pass": False, "reason": f"{len(cycles)} trace cycles vs {len(records)} stub requests"}
    start_ms = np.array([int(c["start_sample"]) for c in cycles]) * 1e3 / FS
    tx_end_ms = start_ms + np.array([sum(float(c[k]) for k in TX_END_PHASES) for c in cycles])
    rx_ms = np.array([r["t_rx_ms"] for r in records], dtype=float)
    delta = np.abs(np.diff(tx_end_ms) - np.diff(rx_ms))
    offset = rx_ms - tx_end_ms
    offset -= np.median(offset)
    start_delta = np.abs(np.diff(start_ms) - np.diff(rx_ms))
    rho_equal = [c.get("rho") for c in cycles] == [r.get("rho") for r in records]
    return {"pass": bool(rho_equal and (delta.size == 0 or float(delta.max()) < INTERVAL_MATCH_MS)
                         and float(np.abs(offset).max()) < INTERVAL_MATCH_MS),
            "reference": "trace TX end vs stub t_rx_ms",
            "rho_order_equal": rho_equal,
            "max_abs_delta_ms": float(delta.max()) if delta.size else 0.0,
            "mean_abs_delta_ms": float(delta.mean()) if delta.size else 0.0,
            "offset_range_ms": [float(offset.min()), float(offset.max())],
            "start_spacing_max_abs_delta_ms": float(start_delta.max()) if start_delta.size else 0.0,
            "stub_clock_resolution_s": time.get_clock_info("monotonic").resolution,
            "limit_ms": INTERVAL_MATCH_MS}


def dwt_comparison(summary: dict, dryrun_check: Path | None) -> list:
    """Marker phase durations (energy image, PPK2 power) vs DWT of the energy-usb dry run."""
    if dryrun_check is None:
        return []
    dwt = load_json(dryrun_check)["dwt_phases_us"]
    rows = []
    for rho in ("P1", "P0"):
        stats = summary["groups"].get(rho, {}).get("stats", {})
        pairs = {"t_ctrl_ms": [f"{rho}_ctrl_us"], "t_dev_ms": [f"{rho}_head_us"],
                 "t_prot_ms": [f"{rho}_prot_us"], "t_tx_ms": [f"{rho}_tx_us"],
                 "t_wait_ms": [f"{rho}_wait_us"]}
        for key, names in pairs.items():
            if key not in stats or not all(n in dwt for n in names):
                continue
            ref = sum(dwt[n]["mean"] for n in names) / 1000.0
            marker = stats[key]["mean"]
            rows.append({"rho": rho, "phase": key, "marker_mean_ms": marker, "dwt_mean_ms": ref,
                         "delta_ms": marker - ref,
                         "delta_pct": (100.0 * (marker - ref) / ref) if ref else None})
    return rows


def cmd_session(args) -> int:
    if args.p1 and not args.key_file:
        raise SystemExit("P1 cycles need --key-file (bench key; never printed)")
    if args.p1 and args.prior_reserved_through is None:
        raise SystemExit("give --prior-reserved-through (largest reserved_through seen before)")
    out = new_out(args.out)
    image = image_info(args.image, args.receipt, "energy")
    session_record(out, "session", args, {
        "image": image, "split": args.split, "p1": args.p1, "p0": args.p0,
        "prior_reserved_through": args.prior_reserved_through,
        "key": "bench key file" if args.key_file else None,
        "dryrun_check": str(args.dryrun_check) if args.dryrun_check else None,
        "session_a_idle": str(args.a1) if args.a1 else None})
    proc, log = start_stub(args, out)
    try:
        meta = run_capture(args, out, "B-energy-session", args.seconds)
        try:
            proc.wait(timeout=args.stub_extra_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.terminate()
        log.close()
    print((out / "stub.out").read_text(encoding="utf-8", errors="replace")[-1500:])
    argv = ["analyze", "--raw", str(out / "ppk2"), "--expect-cycles", str(args.p1 + args.p0),
            "--expect-p1", str(args.p1), "--expect-p0", str(args.p0), "--out", str(out / "analysis")]
    if args.ignore_counter:
        argv.append("--ignore-counter")
    print("+ energy_phases.py", " ".join(argv))
    ep.main(argv)
    return evaluate_session(out, args, meta, "session")


def evaluate_session(out: Path, args, meta: dict, kind: str) -> int:
    """Session B checks from the files of a session directory (capture, stub, analysis)."""
    stub_summary = load_json(out / "stub" / "summary.json") if (out / "stub" / "summary.json").exists() else {}
    summary = load_json(out / "analysis" / "summary.json")
    cycles = cycle_rows(out / "analysis")
    records = stub_records(out / "stub")
    match = match_intervals(cycles, records)
    a = summary["checks"]
    first_seq = stub_summary.get("first_sequence")
    waits = [float(c["t_wait_ms"]) for c in cycles if c.get("t_wait_ms")]
    conn = summary.get("conn_interval_diagnostic") or {}
    checks = {
        "TC1_selftest_D0_D4": a.get("selftest_D0_D4", False),
        "TC1_unused_channels_low": a.get("unused_channels_low", False),
        "TC2_capture_pass": meta["status"] == "PASS",
        "TC2_no_data_loss": a.get("no_data_loss", args.ignore_counter) and a.get("sample_rate_ok", False),
        "TC5_stub_pass": stub_summary.get("status") == "PASS",
        "TC5_stub_answered_all": (stub_summary.get("counters") or {}).get("response_sent") == args.p1 + args.p0,
        "TC5_cycle_count": a.get("cycle_count", False),
        "TC5_p1_p0_counts": a.get("p1_cycles", True) and a.get("p0_cycles", True),
        "TC5_all_cycles_valid_single_tx": a.get("all_cycles_valid", False),
        "TC5_one_cycle_per_request": match["pass"],
        "TC5_wait_below_timeout": bool(waits) and max(waits) < RESPONSE_TIMEOUT_MS,
        "TC5_idle_markers_low": a.get("idle_markers_low", False),
        "TC6_diff_below_3pct_all": a.get("diff_below_3pct_all", False),
    }
    if args.p1:
        checks["TC5_nonce_above_prior"] = first_seq is not None and first_seq > args.prior_reserved_through
    i_idle = summary.get("I_idle_uA")
    idle_ref = None
    if args.a1:
        idle_ref = load_json(Path(args.a1) / "check_idle.json").get("I_idle_uA")
    details = {
        "analysis_status": summary["status"],
        "stub_status": stub_summary.get("status"),
        "first_p1_sequence": first_seq, "last_p1_sequence": stub_summary.get("last_sequence"),
        "prior_reserved_through": args.prior_reserved_through,
        "interval_match": match,
        "wait_ms_max": max(waits) if waits else None,
        "I_idle_uA_firmware_window": i_idle,
        "I_idle_uA_session_a_week2_image": idle_ref,
        "conn_interval_estimate_ms": conn.get("median_spacing_ms"),
        "conn_interval_requested_ms": 15.0,
        "diff_pct": summary.get("diff_pct"),
        "phase_vs_dwt": dwt_comparison(summary, args.dryrun_check),
        "ci95_rel_pct": {rho: {k: v.get("ci95_rel_pct") for k, v in g["stats"].items()
                               if k.startswith("E_") and not k.endswith("net_uJ")}
                         for rho, g in summary.get("groups", {}).items()},
        "capture": {k: meta[k] for k in ("samples", "dut_on_rate_deviation_pct", "raw_sha256",
                                         "host_max_gap_between_reads_s", "status")},
    }
    if not summary.get("selftest", {}).get("found") and len(cycles) == 0:
        print("NOTE: no self-test found. Ten 5 ms CTRL pulses = the image refused P1 (nonce not "
              "READY): flash energy-usb, read NONCE, never PROV ERASE.")
    return finish(out, kind, checks, details)


def cmd_recheck(args) -> int:
    """Re-run the session B checks on an existing session directory with the current checker;
    writes check_session_recheck.json next to the original check (which stays untouched)."""
    out = Path(args.out)
    record = load_json(out / "session.json")
    if record.get("kind") != "session":
        raise SystemExit(f"{out} is not a session B directory")
    command = record.get("command", [])
    a = argparse.Namespace(
        p1=record["p1"], p0=record["p0"], prior_reserved_through=record.get("prior_reserved_through"),
        dryrun_check=Path(record["dryrun_check"]) if record.get("dryrun_check") else None,
        a1=Path(record["session_a_idle"]) if record.get("session_a_idle") else None,
        ignore_counter="--ignore-counter" in command)
    return evaluate_session(out, a, load_json(out / "ppk2" / "capture.json"), "session_recheck")


def cmd_note(args) -> int:
    out = Path(args.out)
    if not (out / "session.json").exists():
        raise SystemExit(f"{out} is not a week7_ppk2.py session directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    photos = [{"path": str(p), "sha256": sha256(p), "bytes": Path(p).stat().st_size} for p in args.photo]
    write_new_json(out / f"note-{stamp}.json", {"schema": "week7-ppk2-note/1", "utc": stamp,
                                                "temp_end_C": args.temp_end_c, "photos": photos,
                                                "text": args.text})
    print(f"note written to {out / f'note-{stamp}.json'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, seconds):
        p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
        p.add_argument("--out", type=Path, required=True, help="new directory")
        p.add_argument("--seconds", type=float, default=seconds, help="DUT power ON time")
        p.add_argument("--pre-power-s", type=float, default=0.5)
        p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
        p.add_argument("--image", type=Path, help="build folder or DFU ZIP flashed on the dongle")
        p.add_argument("--receipt", type=Path, help="DFU receipt JSON of flash_week7.ps1")
        p.add_argument("--note", default="")
        p.add_argument("--ignore-counter", action="store_true",
                       help="only after A1 showed bits 18-23 are not a sample counter")

    p = sub.add_parser("probe")
    p.add_argument("--port")
    p.add_argument("--stream-s", type=float, default=2.0)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("idle")
    common(p, 125.0)
    p.add_argument("--window-start-s", type=float, default=5.0, help="after DUT power ON")
    p.add_argument("--window-s", type=float, default=60.0)
    p.add_argument("--expect-mean-uA", dest="expect_mean_uA", type=float, default=WEEK2_IDLE_UA)
    p.add_argument("--tolerance-pct", type=float, default=10.0)
    p.set_defaults(func=cmd_idle)

    p = sub.add_parser("active")
    common(p, 15.0)
    p.set_defaults(func=cmd_active)

    p = sub.add_parser("session")
    common(p, 300.0)
    p.add_argument("--split", type=int, default=2)
    p.add_argument("--p1", type=int, default=50)
    p.add_argument("--p0", type=int, default=50)
    p.add_argument("--key-file", type=Path)
    p.add_argument("--prior-reserved-through", type=int)
    p.add_argument("--dryrun-check", type=Path, help="check_dryrun*.json with dwt_phases_us")
    p.add_argument("--a1", type=Path, help="session A1 directory (idle with the week 2 image)")
    p.add_argument("--stub-warmup-s", type=float, default=2.0)
    p.add_argument("--stub-extra-s", type=float, default=120.0)
    p.set_defaults(func=cmd_session)

    p = sub.add_parser("recheck")
    p.add_argument("--out", type=Path, required=True, help="existing session B directory")
    p.set_defaults(func=cmd_recheck)

    p = sub.add_parser("note")
    p.add_argument("--out", type=Path, required=True, help="existing session directory")
    p.add_argument("--temp-end-c", type=float)
    p.add_argument("--photo", type=Path, action="append", default=[])
    p.add_argument("--text", default="")
    p.set_defaults(func=cmd_note)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
