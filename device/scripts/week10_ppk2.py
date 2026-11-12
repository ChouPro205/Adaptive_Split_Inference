#!/usr/bin/env python3
"""Week 10 PPK2 bench driver, part A: E_wait under KV260 queue load (W10-D3, TC3 + TC6).

Image: the clean week 8 energy image (s2, 100 P1/P0 pairs, W8-D1 order), exactly as week 9 B5. The KV260
service connects by itself (Set PHY 2M + Read PHY with t_ms) and runs queue_sim with the W10-D3 scenario
(ewait_load_blocks.csv, SHA-256 38937e54...) from the moment the link to ASI-SV1 is ready; the BLE request
is queued in the same FIFO as the background jobs. Power: PPK2 Source Meter 5000 mV through the VBUS
breakout (decision PPK2 VBUS). Lab rule (09/11): the laptop on AC (Win32_Battery.BatteryStatus = 2,
checked before the capture), Best performance, no other use of the laptop during the capture.

  probe          PPK2 answers? (week7_ppk2.py probe)
  session-ewait  capture -> the week 9 energy-image analysis (analysis/), trace checks (TC3 idle within 10 %
                 of week 2, self-test, 200 paired cycles, < 3 %, no lost sample, back to idle after)
  import-ewait   the KV260 request log + Read-PHY log + queue_sim output directory -> edge/; labels = KV260
                 offline (W8-D8), one cycle per request, one connection, nonce above the prior block, PHY 2M,
                 queue log matched to the requests, scenario = W10-D3, queue rebuilt per request
                 (week10_analysis); writes ewait_rows.csv + energy_ewait.json of the session
  recheck-ewait  the checks again with the current tools (new file)
  summary-ewait  >= 2 PASS sessions with different queue seeds -> W10-D3 tables, regressions and the model
                 rule (week10_analysis.ewait_summary) into a new JSON + CSV directory
  note           end-of-session notes (temperature, photos) (week7_ppk2.py note)
Each session writes a NEW --out directory. Exit 0 = PASS. Run with device/host/.venv; close nRF Connect
Power Profiler first (it holds the PPK2 port).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week10_analysis as wa  # noqa: E402
import week10_common as w10  # noqa: E402
import week7_ppk2 as w7p  # noqa: E402
import week9_ppk2 as w9p  # noqa: E402

FS = ep.SAMPLE_RATE_HZ
DT_MS = 1e3 / FS
PAIRS = w9p.KV260_PAIRS
IDLE_TOLERANCE_PCT = 10.0                    # TC3
GAP_GUARD_MS = 10.0                          # connected-idle window, as week9_figures (P_conn)
SCHEMA = "week10-ppk2-ewait/1"
TOOLS = ("week10_ppk2.py", "week10_analysis.py", "week10_common.py", "week9_ppk2.py", "week9_common.py",
         "week8_common.py", "week8_ppk2.py", "week8_lab.py", "week8_edge.py", "week7_ppk2.py", "measure_energy.py",
         "energy_phases.py")
ROW_FIELDS = ["cycle", "rho", "t_wait_ms", "E_wait_uJ", "E_wait_net_uJ", "q", "q_rebuilt", "active", "q_logged_minus_self",
              "block", "lambda", "seconds_into_block", "level_use", "edge_queue_wait_ms", "edge_service_ms",
              "t_wait_minus_edge_ms", "t_rx_ms"]


# ----------------------------------------------------------------------------- lab rule


def ac_power() -> dict:
    """Win32_Battery.BatteryStatus of every battery (2 = on AC). No battery = desktop: on AC."""
    cmd = ["powershell", "-NoProfile", "-Command",
           "Get-CimInstance Win32_Battery | Select-Object -ExpandProperty BatteryStatus"]
    try:
        text = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError) as error:
        return {"ok": False, "error": repr(error)}
    status = [int(x) for x in text.split() if x.strip().isdigit()]
    return {"ok": all(s == 2 for s in status), "BatteryStatus": status, "checked_utc": datetime.now(timezone.utc).isoformat()}


# ----------------------------------------------------------------------------- trace helpers


def gap_power(trace: ep.Trace, cycles: list, i_idle: float | None) -> dict:
    """P_conn of the session: mean power of every connected-idle gap between two cycles (week 9 B5)."""
    guard, v, gaps = int(GAP_GUARD_MS * FS / 1e3), trace.v_supply_mv / 1000.0, []
    for c0, c1 in zip(cycles, cycles[1:]):
        lo, hi = int(c0["end_sample"]) + guard, int(c1["start_sample"]) - guard
        if hi - lo < FS // 10:
            continue
        mean = float(trace.current_ua[lo:hi].mean())
        gaps.append({"P_gross_mW": v * mean / 1e3, "P_net_mW": v * (mean - i_idle) / 1e3 if i_idle else None})
    return {"gaps": len(gaps), "P_conn_gross_mW": ep.describe(g["P_gross_mW"] for g in gaps),
            "P_conn_net_mW": ep.describe(g["P_net_mW"] for g in gaps if g["P_net_mW"] is not None)}


def trace_checks(out: Path, record: dict, meta: dict) -> tuple:
    summary = w7p.load_json(out / "analysis" / "summary.json")
    cycles = w7p.cycle_rows(out / "analysis")
    trace = w9p.load_raw_chunked(out / "ppk2")
    post = w9p.post_session_events(trace, cycles, summary.get("I_idle_uA"))
    a = summary["checks"]
    i_idle = summary.get("I_idle_uA")
    plan_rho = ["P1" if (k + slot) % 2 == 0 else "P0" for k in range(PAIRS) for slot in range(2)]
    checks = {
        "lab_on_ac_power": bool((record.get("ac_power") or {}).get("ok")),
        "capture_pass": meta.get("status") == "PASS",
        "idle_within_10pct_of_week2": i_idle is not None
                                      and abs(i_idle - w9p.WEEK2_IDLE_UA) / w9p.WEEK2_IDLE_UA * 100.0 <= IDLE_TOLERANCE_PCT,
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
    details = {"I_idle_uA": i_idle, "post_session": post, "diff_pct": summary.get("diff_pct"),
               "P_conn": gap_power(trace, cycles, i_idle), "v_supply_mV": trace.v_supply_mv}
    return checks, details, cycles, summary


# ----------------------------------------------------------------------------- evaluation


def load_edge(out: Path) -> dict:
    edge = out / "edge"
    return {"records": wa.read_jsonl(edge / "peer.jsonl"), "summary": w7p.load_json(edge / "summary.json"),
            "jobs": wa.queue_jobs(wa.read_jsonl(edge / "queue" / "jobs.jsonl")),
            "queue_run": w7p.load_json(edge / "queue" / "queue_run.json"),
            "queue_summary": w7p.load_json(edge / "queue" / "queue_summary.json")}


def evaluate(out: Path, record: dict, meta: dict, kind: str) -> int:
    import week8_ppk2 as w8p
    checks, details, cycles, summary = trace_checks(out, record, meta)
    if not (out / "edge" / "summary.json").exists():
        details["kv260_log"] = "PENDING: week10_ppk2.py import-ewait"
        return w7p.finish(out, kind, checks, details)
    e = load_edge(out)
    records, edge, jobs = e["records"], e["summary"], e["jobs"]
    match = w8p.match_cycles(cycles, records)
    p1_seq = [r["sequence"] for r in records if r.get("rho") == "P1" and r.get("sequence") is not None]
    connections = {r.get("connection") for r in records if "connection" in r}
    phy_check = edge.get("phy_check") or {"pass": False, "rule": "no Read-PHY check"}
    fg = wa.foreground_rows(jobs)
    t_rx = [r.get("t_rx_ms") for r in records]
    req_match = wa.match_requests(t_rx, fg) if all(isinstance(t, (int, float)) for t in t_rx) else \
        {"pass": False, "reason": "t_rx_ms missing in the KV260 request log"}
    scenario = [tuple(float(x) for x in row) for row in e["queue_run"].get("scenario", [])]
    checks.update({
        "kv260_log_pass_labels_100_per_rho": edge.get("status") == "PASS",
        "kv260_answered_all": (edge.get("counters") or {}).get("response_sent") == 2 * PAIRS,
        "one_cycle_per_request": match["pass"],
        "nonce_above_prior_and_increasing": bool(p1_seq) and p1_seq[0] > record["prior_reserved_through"]
                                            and all(b > a for a, b in zip(p1_seq, p1_seq[1:])),
        "single_connection": len(connections) == 1 if connections else edge.get("connections") == 1,
        "phy_2m_read_back": bool(phy_check.get("pass")),
        "queue_scenario_is_W10_D3": scenario == [(float(d), float(lv)) for d, lv in w10.load_blocks()],
        "queue_mqtt_off": e["queue_run"].get("config", {}).get("mqtt_enabled") is False,
        "requests_matched_to_foreground_jobs": req_match["pass"],
    })
    details.update(kv260_log=edge.get("source_log"), labels_equal_reference=edge.get("labels_equal_reference"),
                   interval_match=match, request_match=req_match, phy_check=phy_check,
                   first_p1_sequence=p1_seq[0] if p1_seq else None, last_p1_sequence=p1_seq[-1] if p1_seq else None,
                   queue_seed=e["queue_run"].get("config", {}).get("seed"),
                   queue_counts=e["queue_summary"])
    rows = []
    if req_match["pass"] and match["pass"]:
        table = w10.block_table(w10.load_blocks())
        rows = wa.ewait_rows(cycles, records, fg, table, int(e["queue_run"]["start_monotonic_ns"]))
        checks.update(wa.ewait_session_checks(rows, fg, e["queue_summary"]))
    else:
        checks["ewait_rows_built"] = False
    status = "PASS" if all(checks.values()) else "FAIL"
    if rows:
        stamp = "" if kind == "ewait" else f"_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        with open(out / f"ewait_rows{stamp}.csv", "x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, ROW_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        session = {"s": rows}
        tsvc = {"s": wa.background_service_ms(jobs)}
        pconn = {"s": (details["P_conn"]["P_conn_gross_mW"] or {}).get("mean")}
        w7p.write_new_json(out / f"energy_ewait{stamp}.json", {
            "schema": "week10-energy-ewait-session/1", "decision": "W10-D3", "status": status, "session": str(out),
            "image": record.get("image"), "temp_room_C": record.get("temp_room_C"), "queue_seed": details["queue_seed"],
            "I_idle_uA": details["I_idle_uA"], "P_conn": details["P_conn"], "t_svc_background_ms": tsvc["s"],
            "single_session_summary": wa.ewait_summary(session, tsvc, pconn),
            "per_rho_phases": {rho: g["stats"] for rho, g in summary.get("groups", {}).items()},
            "note": "single-session numbers; the W10-D3 result is summary-ewait over >= 2 sessions"})
    return w7p.finish(out, kind, checks, details)


# ----------------------------------------------------------------------------- commands


def cmd_session_ewait(args) -> int:
    import week8_ppk2 as w8p
    plans = w10.load_plans(args.plan)                       # authenticates the W10-D3 scenario CSV
    sample_set = w9p.w9.w8.load_set(args.samples)
    image = w8p.image_info(args.image, args.receipt, False)  # PASS, energy, clean, 100 pairs
    power = ac_power()
    if not power["ok"] and not args.ac_confirmed:
        raise SystemExit(f"laptop not on AC (Win32_Battery {power}); plug the charger (lab rule 09/11)")
    out = w7p.new_out(args.out)
    record = {
        "schema": SCHEMA, "kind": "session-ewait", "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(), "temp_room_C": args.temp_c,
        "v_supply_mV": 5000, "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "ac_power": power if power["ok"] else {**power, "ok": True, "manual_confirmation": True},
        "image": image, "samples": str(args.samples), "set_sha256": sample_set.set_sha256,
        "plan_dir": str(plans.directory), "load_csv_sha256": w10.LOAD_CSV_SHA256,
        "prior_reserved_through": args.prior_reserved_through, "pairs": PAIRS, "seconds": args.seconds,
        "peer": "KV260 (W10-D3): connects by itself, Set PHY 2M + Read PHY, queue_sim with the W10-D3 "
                "scenario from link ready; request log + queue directory imported afterwards (import-ewait)",
        "ignore_counter": bool(args.ignore_counter), "note": args.note,
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS if (HERE / n).exists()},
    }
    w7p.write_new_json(out / "session.json", record)
    print("KV260 service + queue_sim must be ready (queue_sim starts when the link to ASI-SV1 is ready); "
          "do not touch the bench or the laptop")
    meta = w7p.run_capture(args, out, "W10-D3-ewait-session", args.seconds)
    w9p.analyze_energy_image(w9p.load_raw_chunked(out / "ppk2"), out, PAIRS, args.ignore_counter)
    return evaluate(out, record, meta, "session")


def cmd_import_ewait(args) -> int:
    import week8_edge as edge_mod
    import week8_lab as w8lab
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != SCHEMA:
        raise SystemExit(f"{out} is not a week 10 session-ewait directory")
    sample_set = w9p.w9.w8.load_set(Path(record["samples"]))
    edge_ref = w9p.w9.w8.load_edge_reference(args.edge_reference, sample_set)
    edge = out / "edge"
    edge.mkdir(exist_ok=False)
    raw = edge / "kv260_requests_raw.jsonl"
    shutil.copyfile(args.kv260_log, raw)
    shutil.copytree(args.queue_dir, edge / "queue")
    lines = raw.read_text(encoding="utf-8").splitlines()
    records, counters = w8lab.normalize_peer_log(lines, sample_set)
    requests = [json.loads(x) for x in lines if x.strip() and json.loads(x).get("ev") == "request"]
    for r, line in zip(records, requests):
        if "connection" in line:
            r["connection"] = line["connection"]
    with open(edge / "peer.jsonl", "x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r) + "\n")
    result = edge_mod.evaluate(records, counters, sample_set, 0, PAIRS, None, edge_ref.labels)
    shutil.copyfile(args.phy_log, edge / ("kv260_phy" + Path(args.phy_log).suffix))
    phy = w9p.phy_records(args.phy_log)
    t_rx = [e["t_rx_ms"] for e in requests if isinstance(e.get("t_rx_ms"), (int, float))]
    t_end = [e.get("t_tx_done_ms", e.get("t_rx_ms")) for e in requests
             if isinstance(e.get("t_tx_done_ms", e.get("t_rx_ms")), (int, float))]
    phy_check = w9p.phy_session_check(phy, min(t_rx) if len(t_rx) == len(requests) and t_rx else None,
                                      max(t_end) if t_end else None)
    connections = sum(1 for x in lines if x.strip() and json.loads(x).get("ev") in ("connected", "connection"))
    w7p.write_new_json(edge / "summary.json", {
        "schema": "week10-kv260-ewait-import/1", "source_log": str(args.kv260_log),
        "source_log_sha256": w7p.sha256(raw), "phy_log": str(args.phy_log), "phy_log_sha256": w7p.sha256(args.phy_log),
        "phy_records": phy, "phy_check": phy_check, "queue_dir": str(args.queue_dir),
        "queue_sha256": {p.name: w7p.sha256(p) for p in sorted((edge / "queue").iterdir()) if p.is_file()},
        "connections": connections or None, "imported_utc": datetime.now(timezone.utc).isoformat(),
        "counters": counters, "set_sha256": sample_set.set_sha256, "field_spec": w8lab.PEER_LOG_FIELDS,
        "label_reference": {"path": edge_ref.path, "sha256": edge_ref.sha256}, **result})
    print(f"KV260 log: {len(records)} requests {counters}; labels {result['labels_equal_reference']}; "
          f"PHY records {len(phy)}")
    return evaluate(out, record, w7p.load_json(out / "ppk2" / "capture.json"), "ewait")


def cmd_recheck_ewait(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != SCHEMA:
        raise SystemExit(f"{out} is not a week 10 session-ewait directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return evaluate(out, record, w7p.load_json(out / "ppk2" / "capture.json"), f"ewait_recheck-{stamp}")


def read_rows(path: Path) -> list:
    out = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            row = dict(r)
            for k in ("t_wait_ms", "E_wait_uJ", "lambda", "seconds_into_block", "edge_queue_wait_ms",
                      "edge_service_ms", "t_wait_minus_edge_ms"):
                row[k] = float(row[k]) if row[k] not in ("", "None") else None
            row["E_wait_net_uJ"] = float(row["E_wait_net_uJ"]) if row["E_wait_net_uJ"] not in ("", "None") else None
            row["q"], row["cycle"] = int(row["q"]), int(row["cycle"])
            row["active"], row["level_use"] = row["active"] == "True", row["level_use"] == "True"
            out.append(row)
    return out


def cmd_summary_ewait(args) -> int:
    if len(args.session) < 2:
        raise SystemExit("W10-D3 needs >= 2 valid sessions")
    rows, tsvc, pconn, seeds, sources = {}, {}, {}, {}, {}
    for folder in map(Path, args.session):
        check = w7p.load_json(folder / "check_ewait.json")
        energy = w7p.load_json(folder / "energy_ewait.json")
        if check.get("status") != "PASS" or energy.get("status") != "PASS":
            raise SystemExit(f"{folder}: import-ewait check is not PASS; only valid sessions enter the summary")
        tag = folder.name
        rows[tag] = read_rows(folder / "ewait_rows.csv")
        tsvc[tag] = energy["t_svc_background_ms"]
        pconn[tag] = (energy["P_conn"]["P_conn_gross_mW"] or {}).get("mean")
        seeds[tag] = energy.get("queue_seed")
        sources[tag] = {"check_sha256": w7p.sha256(folder / "check_ewait.json"),
                        "rows_sha256": w7p.sha256(folder / "ewait_rows.csv")}
    if len(set(seeds.values())) != len(seeds):
        raise SystemExit(f"queue seeds must differ between sessions: {seeds}")
    out = w7p.new_out(args.out)
    result = wa.ewait_summary(rows, tsvc, pconn)
    w7p.write_new_json(out / "ewait_summary.json", {"schema": "week10-ewait-summary/1", "decision": "W10-D3",
                                                    "sessions": sources, "queue_seeds": seeds, **result})
    with open(out / "ewait_levels.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["lambda_jobs_per_s", "quantity", "n", "pooled_mean", "pooled_ci95_half", "session_range_pct"])
        for lam, entry in result["levels"].items():
            for key, s in entry.items():
                writer.writerow([lam, key, s.get("n"), s.get("mean"), s.get("ci95_half"), s.get("session_range_pct")])
    with open(out / "ewait_bins.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, ["lo_ms", "hi_ms", "n", "t_wait_ms", "E_wait_uJ", "usable"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["bin_table"])
    e, q = result["pooled_E_wait_vs_t_wait"], result["pooled_t_wait_vs_q"]
    print(f"E_wait = {e.get('intercept'):.1f} uJ + {e.get('slope'):.4f} mW * t_wait (R2 {e.get('r2'):.3f}); "
          f"P_conn {result['P_conn_gross_mW_sessions']}; rule: {result['rule_ewait_model']}")
    print(f"t_wait = {q.get('intercept'):.1f} ms + {q.get('slope'):.2f} ms/job * q (R2 {q.get('r2'):.3f}); "
          f"t_svc {result['t_svc_background_ms']}; rule: {result['rule_queue_model']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--port")
    p.add_argument("--stream-s", type=float, default=2.0)
    p.set_defaults(func=w7p.cmd_probe)

    p = sub.add_parser("session-ewait")
    p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--seconds", type=float, default=480.0,
                   help="DUT power ON: ~31 s boot/idle + link + 35 s + 200 cycles under load (~290 s) + >= 60 s after")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week8.ps1 folder (energy, clean)")
    p.add_argument("--receipt", type=Path, required=True, help="DFU receipt JSON of flash_week8.ps1")
    p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    p.add_argument("--plan", type=Path, required=True, help="generate_week10_plan.py directory")
    p.add_argument("--prior-reserved-through", type=int, required=True,
                   help="largest NONCE reserved_through seen before this boot (W10-D8: 60657663 first)")
    p.add_argument("--ac-confirmed", action="store_true",
                   help="only if the Win32_Battery query itself fails and the charger is visibly plugged in")
    p.add_argument("--note", default="", help="e.g. KV260 distance, service commit, queue seed")
    p.add_argument("--ignore-counter", action="store_true")
    p.set_defaults(func=cmd_session_ewait)

    p = sub.add_parser("import-ewait")
    p.add_argument("--out", type=Path, required=True, help="the session-ewait directory")
    p.add_argument("--kv260-log", type=Path, required=True, help="KV260 request log (JSON lines, week 8/9 form)")
    p.add_argument("--phy-log", type=Path, required=True, help="KV260 Read PHY log (t_ms)")
    p.add_argument("--queue-dir", type=Path, required=True,
                   help="queue_sim output (jobs.jsonl, queue_run.json, queue_summary.json)")
    p.add_argument("--edge-reference", type=Path, required=True,
                   help="KV260 offline predictions.jsonl of the 100 samples (W8-D8)")
    p.set_defaults(func=cmd_import_ewait)

    p = sub.add_parser("recheck-ewait")
    p.add_argument("--out", type=Path, required=True, help="existing session-ewait directory")
    p.set_defaults(func=cmd_recheck_ewait)

    p = sub.add_parser("summary-ewait")
    p.add_argument("--session", action="append", default=[], help="PASS session-ewait directory (>= 2)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.set_defaults(func=cmd_summary_ewait)

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
