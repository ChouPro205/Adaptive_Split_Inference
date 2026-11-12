#!/usr/bin/env python3
"""Week 10 PPK2 bench driver: part A E_wait under KV260 queue load (W10-D3, TC3 + TC6), part B every s with
the radio on (W10-D4, TC7).

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
  session-alls   part B (W10-D4, TC7): the week 10 ble image (550 plan cycles, s0..s10, rho0, radio on) with
                 the KV260 (every tail loaded, no background load) -> analysis/ (week10_ble segmentation: s10 has
                 no TX/WAIT), trace checks as session-ewait, cycle order = plan
  import-alls    the KV260 request log (with split) + Read-PHY log + KV260 offline predictions s0..s9 -> edge/;
                 one request per s <= 9 cycle in plan order, labels/logits = offline at every s, PHY 2M, one
                 connection; writes alls_rows.csv + energy_alls.json of the session
  recheck-alls   the checks again with the current tools (new file)
  summary-alls   >= 2 PASS sessions -> per-s table (week10_analysis.alls_table: pooled + session range + core),
                 W10-D5 formula against week 9 Table III, E_tx linearity alarm
  session-prot   part C (W10-D1, TC3-TC5): the week 10 prot image (radio off, 1050 plan cycles: P1/P0 pairs at
                 s0..s9 + HEAD-only s1) -> analysis/ (week10_prot segmentation), trace checks (one boot D1 pulse,
                 D1 only in P1 cycles, order = plan), energy_prot.json of the session
  recheck-prot   the checks again with the current tools (new file)
  summary-prot   >= 2 PASS sessions (+ verify-prot DWT) -> energy_prot.json + e_prot_by_split.csv: E_prot per s
                 (gross, net, core 50 us blocks, t_prot), paired delta, E_conv,min, W10-D2 rule, ratios
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


# ----------------------------------------------------------------------------- part B: every s, radio on (W10-D4)

ALLS_SCHEMA = "week10-ppk2-alls/1"
ALLS_SECONDS = 900.0
TABLE_III_OFF = HERE.parents[1] / "results" / "week9" / "device" / "analysis" / "table_iii_e_dev.csv"
ALLS_ROW_FIELDS = ["cycle", "round", "sample", "split", "bytes_payload", "E_dev_uJ", "E_dev_net_uJ", "t_dev_ms",
                   "dev_high_fraction", "E_tx_uJ", "t_tx_ms", "E_wait_uJ", "t_wait_ms", "E_tot_uJ", "E_cycle_uJ",
                   "t_cycle_ms", "t_edge_ms", "label", "label_offline"]


def alls_image_info(image: Path, receipt: Path | None) -> dict:
    """A build_week10.ps1 folder (static check PASS, variant ble, clean tree, the W10-D4 plan) + its
    flash_week10.ps1 receipt."""
    check = w7p.load_json(Path(image) / "week10_build_check.json")
    source = w7p.load_json(Path(image) / "source.json")
    info = {"image": str(image), "build_id": check.get("build_id"), "variant": check.get("variant"),
            "kernel": check.get("kernel"), "check_status": check.get("status"), "dirty": source.get("dirty"),
            "commit": source.get("commit"), "bin_sha256": check.get("bin_sha256"),
            "set_sha256": check.get("set_sha256"), "plan_sha256": check.get("plan_sha256"), "kconfig": check.get("kconfig")}
    if check.get("status") != "PASS" or check.get("variant") != "ble" or source.get("dirty"):
        raise SystemExit(f"{image}: static check not PASS, not the ble variant, or dirty tree")
    if check.get("plan_sha256") != w10.BLE_PLAN_SHA256:
        raise SystemExit(f"{image}: plan {check.get('plan_sha256')} != W10-D4 {w10.BLE_PLAN_SHA256}")
    if receipt is not None:
        r = w7p.load_json(receipt)
        info["receipt"] = {"path": str(receipt), "exit_code": r.get("exit_code"), "build_id": r.get("build_id"),
                           "timestamp": r.get("timestamp"), "zip_sha256": r.get("zip_sha256")}
        if r.get("exit_code") != 0 or r.get("build_id") != info["build_id"]:
            raise SystemExit(f"{receipt}: DFU failed or receipt build differs from {image}")
    return info


def analyze_alls(trace: ep.Trace, out: Path, plan_rows: list, ignore_counter: bool) -> dict:
    """Self-test, 29 s idle window (radio off), the 550 plan cycles (week10_ble.segment_ble_cycles), net
    energies; writes analysis/cycles.csv + summary.json."""
    import week10_ble as wb
    phase_map = dict(ep.DEFAULT_MAP)
    analysis = ep.new_output_dir(out / "analysis")
    selftest = ep.selftest_check(trace, phase_map, 200.0)
    after = selftest["end_sample"] if selftest.get("found") else 0
    idle = None
    if selftest.get("found"):
        a = after + int(0.5 * FS)
        idle = ep.window_stats(trace, a, a + int(29.0 * FS), channels=sorted(phase_map.values()))
        idle["all_markers_low"] = not any(idle["high_samples"].values())
    cycles = wb.segment_ble_cycles(trace, after + 1, plan_rows)
    i_idle = idle["mean_uA"] if idle else None
    if i_idle is not None:
        wb.add_net(cycles, i_idle, trace.v_supply_mv)
    valid = [c for c in cycles if not c["errors"]]
    diffs = [c["diff_pct"] for c in valid]
    stray = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in range(8) if c not in phase_map.values()}
    checks = {
        "selftest_D0_D4": bool(selftest.get("pass")),
        "cycle_count_550": len(cycles) == len(plan_rows),
        "all_cycles_valid": len(valid) == len(cycles) and bool(cycles),
        "diff_below_3pct_all": bool(diffs) and max(diffs) < ep.DIFF_LIMIT_PCT and len(diffs) == len(cycles),
        "unused_channels_low": not any(stray.values()),
        **ep.data_loss_checks(trace, ignore_counter),
        "idle_markers_low": bool(idle and idle["all_markers_low"]),
    }
    summary = {
        "schema": "week10-alls-analysis/1", "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
        "producer": "week10_ppk2.py analyze_alls (week10_ble.segment_ble_cycles, chunked loader)",
        "trace": {"source": trace.source, "samples": trace.n, "duration_s": trace.n * ep.DT_S,
                  "v_supply_mV": trace.v_supply_mv, **trace.info},
        "phase_map": {k: f"D{v}" for k, v in phase_map.items()}, "selftest": selftest, "idle": idle,
        "I_idle_uA": i_idle, "cycles_found": len(cycles), "cycles_valid": len(valid), "diff_pct": ep.describe(diffs),
        "unused_channel_high_samples": stray, "errors": {c["cycle"]: c["errors"] for c in cycles if c["errors"]},
    }
    with open(analysis / "cycles.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, wb.CYCLE_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for c in cycles:
            writer.writerow({**c, "errors": ";".join(c["errors"])})
    (analysis / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


def match_alls(cycles: list, records: list) -> dict:
    """Each s <= 9 trace cycle is one answered request (week8_ppk2.match_cycles anchors): trace TX end
    (= WAIT start) vs edge t_rx_ms and trace WAIT end vs edge t_tx_done_ms, median-centred; equal counts
    and split order; every cycle within INTERVAL_MATCH_MS at one anchor at least and every offset below
    half the smallest spacing of these cycles."""
    edge = [c for c in cycles if not c["device_only"]]
    if not edge or len(edge) != len(records):
        return {"pass": False, "reason": f"{len(edge)} s<=9 trace cycles vs {len(records)} edge requests"}
    wait_end = np.array([int(c["end_sample"]) for c in edge]) * DT_MS
    tx_end = wait_end - np.array([float(c["t_wait_ms"]) for c in edge])
    try:
        off_a = np.array([r["t_rx_ms"] for r in records], dtype=float) - tx_end
        off_b = np.array([r["t_tx_done_ms"] for r in records], dtype=float) - wait_end
    except (KeyError, TypeError):
        return {"pass": False, "reason": "t_rx_ms / t_tx_done_ms missing in the KV260 request log"}
    off_a, off_b = np.abs(off_a - np.median(off_a)), np.abs(off_b - np.median(off_b))
    best = np.minimum(off_a, off_b)
    spacing = float(np.diff(wait_end).min()) if wait_end.size > 1 else float("inf")
    split_equal = [int(c["split"]) for c in edge] == [r.get("split") for r in records]
    limit = w7p.INTERVAL_MATCH_MS
    return {"pass": bool(split_equal and best.max() < limit and max(off_a.max(), off_b.max()) < spacing / 2),
            "split_order_equal": split_equal, "limit_ms": limit, "min_cycle_spacing_ms": spacing,
            "max_abs_offset_ms": {"tx_end_vs_rx": float(off_a.max()), "wait_end_vs_reply": float(off_b.max()),
                                  "best_anchor": float(best.max())}}


def alls_rows(cycles: list, records: list, host, edge_ref: dict) -> list:
    """Rows of the per-s table (week10_analysis.alls_table): every valid cycle; s <= 9 joined to its request."""
    it = iter(records)
    rows = []
    for c in cycles:
        s = int(c["split"])
        rec = None if c["device_only"] else next(it, None)
        f = lambda k: float(c[k])  # noqa: E731
        row = {"cycle": int(c["cycle"]), "round": int(c["round"]), "sample": int(c["sample"]), "split": s,
               "bytes_payload": host.bytes_payload(s), "E_dev_uJ": f("E_dev_uJ"),
               "E_dev_net_uJ": float(c["E_dev_net_uJ"]) if c.get("E_dev_net_uJ") not in (None, "") else None,
               "t_dev_ms": f("t_dev_ms"), "dev_high_fraction": f("dev_high_fraction"),
               "E_cycle_uJ": f("E_cycle_uJ"), "t_cycle_ms": f("t_cycle_ms")}
        if c["device_only"]:
            row.update(E_tx_uJ=None, t_tx_ms=None, E_wait_uJ=None, t_wait_ms=None, t_edge_ms=None,
                       E_tot_uJ=f("E_dev_uJ"), label=host.s10[int(c["sample"])][1], label_offline=None)
        else:
            timed = rec is not None and isinstance(rec.get("t_rx_ms"), (int, float)) \
                and isinstance(rec.get("t_tx_done_ms"), (int, float))
            row.update(E_tx_uJ=f("E_tx_uJ"), t_tx_ms=f("t_tx_ms"), E_wait_uJ=f("E_wait_uJ"), t_wait_ms=f("t_wait_ms"),
                       E_tot_uJ=f("E_dev_uJ") + f("E_tx_uJ") + f("E_wait_uJ"),
                       t_edge_ms=rec["t_tx_done_ms"] - rec["t_rx_ms"] if timed else None,
                       label=rec.get("label") if rec else None,
                       label_offline=edge_ref["labels"][(int(c["sample"]), s)][1])
        rows.append(row)
    return rows


def alls_trace_checks(out: Path, record: dict, meta: dict) -> tuple:
    summary = w7p.load_json(out / "analysis" / "summary.json")
    cycles = w7p.cycle_rows(out / "analysis")
    for c in cycles:
        c["device_only"] = c["device_only"] == "True"
    trace = w9p.load_raw_chunked(out / "ppk2")
    post = w9p.post_session_events(trace, cycles, summary.get("I_idle_uA"))
    a = summary["checks"]
    i_idle = summary.get("I_idle_uA")
    plan = [(r.split, r.sample) for r in w10.ble_plan()]
    checks = {
        "lab_on_ac_power": bool((record.get("ac_power") or {}).get("ok")),
        "capture_pass": meta.get("status") == "PASS",
        "idle_within_10pct_of_week2": i_idle is not None
                                      and abs(i_idle - w9p.WEEK2_IDLE_UA) / w9p.WEEK2_IDLE_UA * 100.0 <= IDLE_TOLERANCE_PCT,
        "selftest_D0_D4": a.get("selftest_D0_D4", False),
        "unused_channels_low": a.get("unused_channels_low", False),
        "no_data_loss": a.get("no_data_loss", record.get("ignore_counter", False)) and a.get("sample_rate_ok", False),
        "cycle_count_550": a.get("cycle_count_550", False),
        "trace_order_equals_plan": [(int(c["split"]), int(c["sample"])) for c in cycles] == plan,
        "all_cycles_valid": a.get("all_cycles_valid", False),
        "idle_markers_low": a.get("idle_markers_low", False),
        "diff_below_3pct_all": a.get("diff_below_3pct_all", False),
        "post_window_at_least_20s": post.get("found", False) and post["duration_s"] >= 20.0,
        "post_mean_at_idle": post.get("deviation_from_idle_pct", float("inf")) <= IDLE_TOLERANCE_PCT,
        "post_radio_off": post.get("found", False) and post["radio_off"],
    }
    details = {"I_idle_uA": i_idle, "post_session": post, "diff_pct": summary.get("diff_pct"),
               "P_conn": gap_power(trace, cycles, i_idle), "v_supply_mV": trace.v_supply_mv}
    return checks, details, cycles


def evaluate_alls(out: Path, record: dict, meta: dict, kind: str) -> int:
    import week10_ble as wb
    checks, details, cycles = alls_trace_checks(out, record, meta)
    if not (out / "edge" / "summary.json").exists():
        details["kv260_log"] = "PENDING: week10_ppk2.py import-alls"
        return w7p.finish(out, kind, checks, details)
    edge = w7p.load_json(out / "edge" / "summary.json")
    host = wb.HostRefs(Path(record["samples"]), Path(record["plan_dir"]), out / "host_shim")
    edge_ref = wb.load_edge_reference(sorted((out / "edge").glob("edge_reference_*")), host)
    records = wa.read_jsonl(out / "edge" / "peer.jsonl")
    result = wb.evaluate_requests(records, edge["counters"], list(host.plans.ble), edge_ref)
    connections = {r.get("connection") for r in records if r.get("connection") is not None}
    match = match_alls(cycles, records)
    phy_check = edge.get("phy_check") or {"pass": False, "rule": "no Read-PHY check"}
    checks.update({f"kv260_{k}": v for k, v in result["checks"].items()})
    checks.update({
        "one_trace_cycle_per_request": match["pass"],
        "single_connection": len(connections) == 1 if connections else edge.get("connections") == 1,
        "phy_2m_read_back": bool(phy_check.get("pass")),
    })
    details.update(kv260_log=edge.get("source_log"), interval_match=match, phy_check=phy_check,
                   kv260_per_s=result["per_s"], t_edge_ms_by_s=result["t_edge_ms_by_s"])
    status = "PASS" if all(checks.values()) else "FAIL"
    if match["pass"]:
        rows = alls_rows(cycles, records, host, edge_ref)
        stamp = "" if kind == "alls" else f"_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        with open(out / f"alls_rows{stamp}.csv", "x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, ALLS_ROW_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        w7p.write_new_json(out / f"energy_alls{stamp}.json", {
            "schema": "week10-energy-alls-session/1", "decision": "W10-D4", "status": status, "session": str(out),
            "image": record.get("image"), "temp_room_C": record.get("temp_room_C"), "I_idle_uA": details["I_idle_uA"],
            "P_conn": details["P_conn"], "single_session_table": wa.alls_table({"s": rows}),
            "note": "single-session numbers; the W10-D4 result is summary-alls over >= 2 sessions"})
    return w7p.finish(out, kind, checks, details)


def cmd_session_alls(args) -> int:
    plans = w10.load_plans(args.plan)
    sample_set = w9p.w9.w8.load_set(args.samples)
    image = alls_image_info(args.image, args.receipt)
    power = ac_power()
    if not power["ok"] and not args.ac_confirmed:
        raise SystemExit(f"laptop not on AC (Win32_Battery {power}); plug the charger (lab rule 09/11)")
    out = w7p.new_out(args.out)
    record = {
        "schema": ALLS_SCHEMA, "kind": "session-alls", "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(), "temp_room_C": args.temp_c,
        "v_supply_mV": 5000, "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "ac_power": power if power["ok"] else {**power, "ok": True, "manual_confirmation": True},
        "image": image, "samples": str(args.samples), "set_sha256": sample_set.set_sha256,
        "plan_dir": str(plans.directory), "plan_sha256": plans.ble_sha256, "cycles": len(plans.ble),
        "seconds": args.seconds,
        "peer": "KV260 (W10-D4): connects by itself, Set PHY 2M + Read PHY with t_ms, every tail s0..s9 loaded "
                "before the session, no background load; request log imported afterwards (import-alls)",
        "ignore_counter": bool(args.ignore_counter), "note": args.note,
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS + ("week10_ble.py",) if (HERE / n).exists()},
    }
    w7p.write_new_json(out / "session.json", record)
    print("KV260 service must be up with every tail s0..s9 loaded; do not touch the bench or the laptop")
    meta = w7p.run_capture(args, out, "W10-D4-alls-session", args.seconds)
    analyze_alls(w9p.load_raw_chunked(out / "ppk2"), out, list(plans.ble), args.ignore_counter)
    return evaluate_alls(out, record, meta, "session")


def cmd_import_alls(args) -> int:
    import week10_ble as wb
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != ALLS_SCHEMA:
        raise SystemExit(f"{out} is not a week 10 session-alls directory")
    host = wb.HostRefs(Path(record["samples"]), Path(record["plan_dir"]), out / "host_shim")
    wb.load_edge_reference(args.edge_reference, host)          # refuse a bad reference before copying
    edge = out / "edge"
    edge.mkdir(exist_ok=False)
    raw = edge / "kv260_requests_raw.jsonl"
    shutil.copyfile(args.kv260_log, raw)
    for i, path in enumerate(args.edge_reference):
        shutil.copyfile(path, edge / f"edge_reference_{i}{Path(path).suffix}")
    lines = raw.read_text(encoding="utf-8").splitlines()
    records, counters = wb.normalize_kv260_log(lines, host)
    with open(edge / "peer.jsonl", "x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r) + "\n")
    shutil.copyfile(args.phy_log, edge / ("kv260_phy" + Path(args.phy_log).suffix))
    phy = w9p.phy_records(args.phy_log)
    t_rx = [r["t_rx_ms"] for r in records if isinstance(r.get("t_rx_ms"), (int, float))]
    t_end = [r.get("t_tx_done_ms", r.get("t_rx_ms")) for r in records
             if isinstance(r.get("t_tx_done_ms", r.get("t_rx_ms")), (int, float))]
    phy_check = w9p.phy_session_check(phy, min(t_rx) if len(t_rx) == len(records) and t_rx else None,
                                      max(t_end) if t_end else None)
    connections = sum(1 for x in lines if x.strip() and json.loads(x).get("ev") in ("connected", "connection"))
    w7p.write_new_json(edge / "summary.json", {
        "schema": "week10-kv260-alls-import/1", "source_log": str(args.kv260_log),
        "source_log_sha256": w7p.sha256(raw), "phy_log": str(args.phy_log), "phy_log_sha256": w7p.sha256(args.phy_log),
        "phy_records": phy, "phy_check": phy_check, "connections": connections or None,
        "edge_reference": {str(p): w7p.sha256(p) for p in args.edge_reference},
        "imported_utc": datetime.now(timezone.utc).isoformat(), "counters": counters})
    print(f"KV260 log: {len(records)} requests {counters}; PHY records {len(phy)}")
    return evaluate_alls(out, record, w7p.load_json(out / "ppk2" / "capture.json"), "alls")


def cmd_recheck_alls(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != ALLS_SCHEMA:
        raise SystemExit(f"{out} is not a week 10 session-alls directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return evaluate_alls(out, record, w7p.load_json(out / "ppk2" / "capture.json"), f"alls_recheck-{stamp}")


def read_alls_rows(path: Path) -> list:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [{k: (None if v in ("", "None") else v) for k, v in r.items()} for r in csv.DictReader(handle)]


def table_iii_off() -> dict:
    """Week 9 radio-off numbers per s (Table III): core E_dev and marker t_dev."""
    with TABLE_III_OFF.open(encoding="utf-8", newline="") as handle:
        return {int(r["split"]): {"core_uJ": float(r["E_dev_core_uJ"]), "t_dev_ms": float(r["t_dev_marker_ms"]),
                                  "E_dev_uJ": float(r["E_dev_uJ_mean"])} for r in csv.DictReader(handle)}


def cmd_summary_alls(args) -> int:
    if len(args.session) < 2:
        raise SystemExit("W10-D4 needs >= 2 valid sessions")
    rows, sources, pconn = {}, {}, {}
    for folder in map(Path, args.session):
        check = w7p.load_json(folder / "check_alls.json")
        energy = w7p.load_json(folder / "energy_alls.json")
        if check.get("status") != "PASS" or energy.get("status") != "PASS":
            raise SystemExit(f"{folder}: import-alls check is not PASS; only valid sessions enter the summary")
        tag = folder.name
        rows[tag] = read_alls_rows(folder / "alls_rows.csv")
        pconn[tag] = (energy["P_conn"]["P_conn_gross_mW"] or {}).get("mean")
        sources[tag] = {"check_sha256": w7p.sha256(folder / "check_alls.json"),
                        "rows_sha256": w7p.sha256(folder / "alls_rows.csv")}
    out = w7p.new_out(args.out)
    table = wa.alls_table(rows)
    off = table_iii_off()
    core_on = {int(s): e["E_dev_core"]["mean"] for s, e in table.items() if e["E_dev_core"]["mean"] is not None}
    t_dev_on = {int(s): e["t_dev_ms"]["mean"] for s, e in table.items() if "t_dev_ms" in e}
    formula = wa.dev_on_formula(core_on, {s: v["core_uJ"] for s, v in off.items()}, t_dev_on)
    etx = {int(s): e["E_tx_uJ"]["mean"] for s, e in table.items() if "E_tx_uJ" in e}
    bytes_by_s = {int(r["split"]): int(r["bytes_payload"]) for rs in rows.values() for r in rs}
    linear = wa.etx_linearity(bytes_by_s, etx)
    w7p.write_new_json(out / "alls_summary.json", {
        "schema": "week10-alls-summary/1", "decision": "W10-D4, W10-D5", "sessions": sources,
        "P_conn_gross_mW_sessions": pconn, "per_s": table, "w10_d5_dev_on_formula": formula,
        "etx_linearity": linear, "radio_off_week9": {str(k): v for k, v in off.items()}})
    keys = ("E_dev_uJ", "t_dev_ms", "E_tx_uJ", "t_tx_ms", "E_wait_uJ", "t_wait_ms", "E_cycle_uJ", "t_cycle_ms",
            "t_edge_ms")
    with open(out / "table_iii_radio_on.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["split", "bytes_payload", *[f"{k}_mean" for k in keys], *[f"{k}_ci95_half" for k in keys],
                         "E_dev_uJ_session_range_pct", "E_dev_core_uJ", "E_dev_core_range_pct", "E_dev_off_week9_uJ",
                         "ci95_rel_below_10pct"])
        for s, e in sorted(table.items(), key=lambda kv: int(kv[0])):
            writer.writerow([s, bytes_by_s.get(int(s)), *[(e.get(k) or {}).get("mean") for k in keys],
                             *[(e.get(k) or {}).get("ci95_half") for k in keys],
                             (e.get("E_dev_uJ") or {}).get("session_range_pct"), e["E_dev_core"]["mean"],
                             e["E_dev_core"]["range_pct"], off.get(int(s), {}).get("E_dev_uJ"), e["ci95_rel_below_limit"]])
    print(f"W10-D5 formula: {'PASS' if formula['pass'] else 'FAIL'}; E_tx linear R2 {linear['fit'].get('r2')} "
          f"(alarm {linear['alarm_nonlinear']}); P_conn {pconn}")
    return 0


# ----------------------------------------------------------------------------- part C: E_prot, radio off (W10-D1)

PROT_SCHEMA = "week10-ppk2-prot/1"
PROT_SECONDS = 1260.0


def prot_image_info(image: Path, receipt: Path | None) -> dict:
    """A build_week10.ps1 folder (static check PASS, variant prot, clean tree, the W10-D1 plan) + its
    flash_week10.ps1 receipt."""
    check = w7p.load_json(Path(image) / "week10_build_check.json")
    source = w7p.load_json(Path(image) / "source.json")
    info = {"image": str(image), "build_id": check.get("build_id"), "variant": check.get("variant"),
            "kernel": check.get("kernel"), "check_status": check.get("status"), "dirty": source.get("dirty"),
            "commit": source.get("commit"), "bin_sha256": check.get("bin_sha256"),
            "set_sha256": check.get("set_sha256"), "plan_sha256": check.get("plan_sha256"), "kconfig": check.get("kconfig")}
    if check.get("status") != "PASS" or check.get("variant") != "prot" or source.get("dirty"):
        raise SystemExit(f"{image}: static check not PASS, not the prot variant, or dirty tree")
    if check.get("plan_sha256") != w10.PROT_PLAN_SHA256:
        raise SystemExit(f"{image}: plan {check.get('plan_sha256')} != W10-D1 {w10.PROT_PLAN_SHA256}")
    if receipt is not None:
        r = w7p.load_json(receipt)
        info["receipt"] = {"path": str(receipt), "exit_code": r.get("exit_code"), "build_id": r.get("build_id"),
                           "timestamp": r.get("timestamp"), "zip_sha256": r.get("zip_sha256")}
        if r.get("exit_code") != 0 or r.get("build_id") != info["build_id"]:
            raise SystemExit(f"{receipt}: DFU failed or receipt build differs from {image}")
    return info


def analyze_prot(trace: ep.Trace, out: Path, plan_rows: list, ignore_counter: bool) -> dict:
    """Self-test, boot D1 pulses, 29 s idle window, the 1050 plan cycles (week10_prot.segment_prot_cycles), net
    energies; writes analysis/cycles.csv + summary.json."""
    import week10_prot as wpr
    phase_map = dict(ep.DEFAULT_MAP)
    analysis = ep.new_output_dir(out / "analysis")
    selftest = ep.selftest_check(trace, phase_map, 200.0)
    after = selftest["end_sample"] if selftest.get("found") else 0
    before = min(int(r["start_sample"]) for r in selftest["pulses"]) if selftest.get("found") else after
    idle = None
    if selftest.get("found"):
        a = after + int(0.5 * FS)
        idle = ep.window_stats(trace, a, a + int(29.0 * FS), channels=sorted(phase_map.values()))
        idle["all_markers_low"] = not any(idle["high_samples"].values())
    cycles = wpr.segment_prot_cycles(trace, after + 1, plan_rows)
    i_idle = idle["mean_uA"] if idle else None
    if i_idle is not None:
        wpr.add_net(cycles, i_idle, trace.v_supply_mv)
    valid = [c for c in cycles if not c["errors"]]
    diffs = [c["diff_pct"] for c in valid]
    stray = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in range(8) if c not in phase_map.values()}
    boot_d1 = wpr.boot_d1_pulses(trace, before) if selftest.get("found") else None
    checks = {
        "selftest_D0_D4": bool(selftest.get("pass")),
        "boot_nonce_reservation_one_d1_pulse": boot_d1 == 1,
        "cycle_count_1050": len(cycles) == len(plan_rows),
        "all_cycles_valid": len(valid) == len(cycles) and bool(cycles),
        "diff_below_3pct_all": bool(diffs) and max(diffs) < ep.DIFF_LIMIT_PCT and len(diffs) == len(cycles),
        "unused_channels_low": not any(stray.values()),
        **ep.data_loss_checks(trace, ignore_counter),
        "idle_markers_low": bool(idle and idle["all_markers_low"]),
    }
    summary = {
        "schema": "week10-prot-analysis/1", "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
        "producer": "week10_ppk2.py analyze_prot (week10_prot.segment_prot_cycles, chunked loader)",
        "trace": {"source": trace.source, "samples": trace.n, "duration_s": trace.n * ep.DT_S,
                  "v_supply_mV": trace.v_supply_mv, **trace.info},
        "phase_map": {k: f"D{v}" for k, v in phase_map.items()}, "selftest": selftest, "boot_d1_pulses": boot_d1,
        "idle": idle, "I_idle_uA": i_idle, "cycles_found": len(cycles), "cycles_valid": len(valid),
        "diff_pct": ep.describe(diffs), "unused_channel_high_samples": stray,
        "prot_block_samples": wpr.PROT_BLOCK_SAMPLES,
        "errors": {c["cycle"]: c["errors"] for c in cycles if c["errors"]},
    }
    with open(analysis / "cycles.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, wpr.CYCLE_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for c in cycles:
            writer.writerow({**c, "errors": ";".join(c["errors"])})
    (analysis / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


def evaluate_prot(out: Path, record: dict, meta: dict, kind: str) -> int:
    """TC3/TC4 checks of an E_prot session and its energy_prot.json (single-session groups)."""
    import week10_prot as wpr
    summary = w7p.load_json(out / "analysis" / "summary.json")
    cycles = w7p.cycle_rows(out / "analysis")
    trace = w9p.load_raw_chunked(out / "ppk2")
    i_idle = summary.get("I_idle_uA")
    a = summary["checks"]
    plan = [(r.split, OP_NAME[r.op]) for r in w10.prot_plan()]
    d1_outside = sum(1 for c in cycles if c["op"] != "P1" and float(c["t_prot_ms"] or 0) > 0)
    checks = {
        "lab_on_ac_power": bool((record.get("ac_power") or {}).get("ok")),
        "capture_pass": meta.get("status") == "PASS",
        "idle_within_10pct_of_week2": i_idle is not None
                                      and abs(i_idle - w9p.WEEK2_IDLE_UA) / w9p.WEEK2_IDLE_UA * 100.0 <= IDLE_TOLERANCE_PCT,
        "selftest_D0_D4": a.get("selftest_D0_D4", False),
        "boot_nonce_reservation_one_d1_pulse": a.get("boot_nonce_reservation_one_d1_pulse", False),
        "unused_channels_low": a.get("unused_channels_low", False),
        "no_data_loss": a.get("no_data_loss", record.get("ignore_counter", False)) and a.get("sample_rate_ok", False),
        "cycle_count_1050": a.get("cycle_count_1050", False),
        "trace_order_equals_plan": [(int(c["split"]), c["op"]) for c in cycles] == plan,
        "all_cycles_valid": a.get("all_cycles_valid", False),
        "d1_only_in_p1_cycles": d1_outside == 0,
        "idle_markers_low": a.get("idle_markers_low", False),
        "diff_below_3pct_all": a.get("diff_below_3pct_all", False),
    }
    post = w9p.post_session_events(trace, cycles, i_idle)
    checks["post_window_at_least_20s"] = post.get("found", False) and post["duration_s"] >= 20.0
    checks["post_mean_at_idle"] = post.get("deviation_from_idle_pct", float("inf")) <= IDLE_TOLERANCE_PCT
    details = {"I_idle_uA": i_idle, "post_session": post, "diff_pct": summary.get("diff_pct"),
               "boot_d1_pulses": summary.get("boot_d1_pulses"), "v_supply_mV": trace.v_supply_mv,
               "nonce": "one block reserved at boot (one D1 pulse before the self-test); 500 P1 cycles < 1023 "
                        "sequences left, so no Flash write in any cycle (D1 only inside P1 cycles); sequences "
                        "strictly increasing above the prior block by the allocator (prot-usb dry run shows them); "
                        "read NONCE afterwards with week10_lab.py nonce"}
    status = "PASS" if all(checks.values()) else "FAIL"
    if checks["all_cycles_valid"] and checks["trace_order_equals_plan"]:
        groups = wpr.session_groups(cycles)
        stamp = "" if kind == "session" else f"_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        w7p.write_new_json(out / f"energy_prot{stamp}.json", {
            "schema": "week10-energy-prot-session/1", "decision": "W10-D1, W10-D2", "status": status,
            "session": str(out), "image": record.get("image"), "temp_room_C": record.get("temp_room_C"),
            "I_idle_uA": i_idle, "prot_block_samples": wpr.PROT_BLOCK_SAMPLES,
            "groups": {k: ({str(s): v for s, v in g.items()} if isinstance(g, dict) else g) for k, g in groups.items()},
            "note": "single-session values; the W10-D1/D2 result is summary-prot over >= 2 sessions"})
    return w7p.finish(out, kind, checks, details)


OP_NAME = {0: "P0", 1: "P1", 2: "CONV"}


def cmd_session_prot(args) -> int:
    plans = w10.load_plans(args.plan)
    sample_set = w9p.w9.w8.load_set(args.samples)
    image = prot_image_info(args.image, args.receipt)
    power = ac_power()
    if not power["ok"] and not args.ac_confirmed:
        raise SystemExit(f"laptop not on AC (Win32_Battery {power}); plug the charger (lab rule 09/11)")
    out = w7p.new_out(args.out)
    record = {
        "schema": PROT_SCHEMA, "kind": "session-prot", "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(), "temp_room_C": args.temp_c,
        "v_supply_mV": 5000, "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "ac_power": power if power["ok"] else {**power, "ok": True, "manual_confirmation": True},
        "image": image, "samples": str(args.samples), "set_sha256": sample_set.set_sha256,
        "plan_dir": str(plans.directory), "plan_sha256": plans.prot_sha256, "cycles": len(plans.prot),
        "prior_reserved_through": args.prior_reserved_through, "seconds": args.seconds,
        "ignore_counter": bool(args.ignore_counter), "note": args.note,
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS + ("week10_prot.py", "week10_ble.py") if (HERE / n).exists()},
    }
    w7p.write_new_json(out / "session.json", record)
    print("radio-off E_prot session (~21 min): no KV260 needed; do not touch the bench or the laptop")
    meta = w7p.run_capture(args, out, "W10-D1-prot-session", args.seconds)
    analyze_prot(w9p.load_raw_chunked(out / "ppk2"), out, list(plans.prot), args.ignore_counter)
    return evaluate_prot(out, record, meta, "session")


def cmd_recheck_prot(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != PROT_SCHEMA:
        raise SystemExit(f"{out} is not a week 10 session-prot directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return evaluate_prot(out, record, w7p.load_json(out / "ppk2" / "capture.json"), f"prot_recheck-{stamp}")


def cmd_summary_prot(args) -> int:
    import week10_prot as wpr
    if len(args.session) < 2:
        raise SystemExit("W10-D1 needs >= 2 valid sessions")
    groups, sources = {}, {}
    for folder in map(Path, args.session):
        check = w7p.load_json(folder / "check_session.json")
        energy = w7p.load_json(folder / "energy_prot.json")
        if check.get("status") != "PASS" or energy.get("status") != "PASS":
            raise SystemExit(f"{folder}: session check is not PASS; only valid sessions enter the summary")
        g = energy["groups"]
        groups[folder.name] = {k: ({int(s): v for s, v in val.items()} if isinstance(val, dict) else val)
                               for k, val in g.items()}
        sources[folder.name] = {"check_sha256": w7p.sha256(folder / "check_session.json"),
                                "energy_sha256": w7p.sha256(folder / "energy_prot.json")}
    tprot = None
    if args.tprot:
        tprot = w7p.load_json(args.tprot).get("details")
        if w7p.load_json(args.tprot).get("status") != "PASS":
            raise SystemExit(f"{args.tprot}: verify-prot check is not PASS")
    out = w7p.new_out(args.out)
    result = wpr.summary(groups, tprot)
    w7p.write_new_json(out / "energy_prot.json", {"schema": "week10-energy-prot/1", "decision": "W10-D1, W10-D2",
                                                  "sources": sources, "tprot_check": str(args.tprot) if args.tprot else None,
                                                  **result})
    with open(out / "e_prot_by_split.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["split", "n", "E_prot_uJ_mean", "E_prot_uJ_ci95_half", "ci95_rel_pct", "E_prot_session_range_pct",
                         "E_prot_net_uJ_mean", "E_prot_core_uJ", "E_prot_core_range_pct", "t_prot_ms_mean", "t_prot_dwt_ms",
                         "delta_P1_minus_P0_uJ_mean", "E_dev_P0_uJ_mean", "over_conv_min", "pct_of_E_dev", "conv_rule_pass"])
        for s in range(10):
            e = result["per_s"][str(s)]
            r = result["ratios"][str(s)]
            writer.writerow([s, e["E_prot_uJ"].get("n"), e["E_prot_uJ"].get("mean"), e["E_prot_uJ"].get("ci95_half"),
                             e["ci95_rel_pct"], e["E_prot_uJ"].get("session_range_pct"), e["E_prot_net_uJ"].get("mean"),
                             e["E_prot_core"]["mean"], e["E_prot_core"]["range_pct"], e["t_prot_ms"].get("mean"),
                             (e.get("t_prot_dwt_ms") or {}).get("prot_mean_ms"),
                             e["delta_P1_minus_P0_dev_plus_prot_uJ"].get("mean"), e["E_dev_P0_radio_off_uJ"].get("mean"),
                             r["over_conv_min"], r["pct_of_E_dev"], result["w10_d2_conv_rule"]["per_s"][str(s)]["pass"]])
    rule = result["w10_d2_conv_rule"]
    print(f"E_conv,min {result['E_conv_min_uJ'].get('mean'):.2f} uJ; W10-D2 'P1 < 1 conv layer': "
          f"{'PASS' if rule['pass'] else 'FAIL'}; TC5 CI95 < 10 % every s: {result['tc5_ci95_below_10pct_every_s']}")
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

    p = sub.add_parser("session-alls")
    p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--seconds", type=float, default=ALLS_SECONDS,
                   help="DUT power ON: ~31 s boot/idle + link + 35 s + 550 cycles (~12 min) + >= 60 s after")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week10.ps1 folder (ble, clean)")
    p.add_argument("--receipt", type=Path, required=True, help="DFU receipt JSON of flash_week10.ps1")
    p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    p.add_argument("--plan", type=Path, required=True, help="generate_week10_plan.py directory")
    p.add_argument("--ac-confirmed", action="store_true",
                   help="only if the Win32_Battery query itself fails and the charger is visibly plugged in")
    p.add_argument("--note", default="", help="e.g. KV260 distance, service commit")
    p.add_argument("--ignore-counter", action="store_true")
    p.set_defaults(func=cmd_session_alls)

    p = sub.add_parser("import-alls")
    p.add_argument("--out", type=Path, required=True, help="the session-alls directory")
    p.add_argument("--kv260-log", type=Path, required=True, help="KV260 request log (JSON lines, with split)")
    p.add_argument("--phy-log", type=Path, required=True, help="KV260 Read PHY log (t_ms)")
    p.add_argument("--edge-reference", type=Path, action="append", required=True,
                   help="KV260 offline predictions of s0..s9 (one file with a split field, or one per s)")
    p.set_defaults(func=cmd_import_alls)

    p = sub.add_parser("recheck-alls")
    p.add_argument("--out", type=Path, required=True, help="existing session-alls directory")
    p.set_defaults(func=cmd_recheck_alls)

    p = sub.add_parser("summary-alls")
    p.add_argument("--session", action="append", default=[], help="PASS session-alls directory (>= 2)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.set_defaults(func=cmd_summary_alls)

    p = sub.add_parser("session-prot")
    p.add_argument("--port", required=True, help="PPK2 data port (see: probe)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--seconds", type=float, default=PROT_SECONDS,
                   help="DUT power ON: ~31 s boot/idle + 1050 cycles (~18 min) + >= 60 s after")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week10.ps1 folder (prot, clean)")
    p.add_argument("--receipt", type=Path, required=True, help="DFU receipt JSON of flash_week10.ps1")
    p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    p.add_argument("--plan", type=Path, required=True, help="generate_week10_plan.py directory")
    p.add_argument("--prior-reserved-through", type=int, required=True,
                   help="largest NONCE reserved_through seen before this boot (W10-D8: 60657663 first)")
    p.add_argument("--ac-confirmed", action="store_true",
                   help="only if the Win32_Battery query itself fails and the charger is visibly plugged in")
    p.add_argument("--note", default="")
    p.add_argument("--ignore-counter", action="store_true")
    p.set_defaults(func=cmd_session_prot)

    p = sub.add_parser("recheck-prot")
    p.add_argument("--out", type=Path, required=True, help="existing session-prot directory")
    p.set_defaults(func=cmd_recheck_prot)

    p = sub.add_parser("summary-prot")
    p.add_argument("--session", action="append", default=[], help="PASS session-prot directory (>= 2)")
    p.add_argument("--tprot", type=Path, help="check_verify-prot JSON of week10_lab.py verify-prot (DWT t_prot)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.set_defaults(func=cmd_summary_prot)

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
