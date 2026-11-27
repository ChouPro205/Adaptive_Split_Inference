#!/usr/bin/env python3
"""Week 12 PPK2 link-state sessions with the week 11 `link` image (W11-D1..D3, rules W11-D7..D14 in
week11_analysis.py, fixed before the lab).

Image: build_week11.ps1 -Variant link -Session k (clean tree, static check PASS), one image per plan session,
flashed with flash_week11.ps1 before its session. The KV260 echo service (H3 part 3) connects by itself, accepts
every parameter request of the dongle, answers each echo frame in the mode it asks for, reconnects after each
device disconnect, and logs every echo frame + every granted parameter (btmon or service log). Power: PPK2
Source Meter 5000 mV through the VBUS breakout (decision PPK2 VBUS). Lab rule (09/11): the laptop on AC
(Win32_Battery.BatteryStatus = 2, checked before the capture), Best performance, no other use of the laptop.

  probe     PPK2 answers? (week7_ppk2.py probe)
  session   capture -> analysis/ (W11-D7 segmentation, W11-D8 blocks), trace checks: self-test, plan not
            refused, boot idle within 10 % of week 2, every plan entry found in order, base and reconnect
            blocks valid, every other block valid or refused with its signature, < 3 % on every active op of a
            valid block, unused channels low, no lost sample, back to idle and off-air after the session
  import    KV260 echo log + link-event log -> edge/; one echo record per ECHO entry (length, mode, request_id
            consecutive, time match), granted parameters = state of every block not refused; writes
            ops_valid.csv + energy_link.json of the session
  recheck   the checks again with the current tools (new file)
  summary   >= 2 PASS sessions (plan sessions 0 and 1) -> W11-D9..D13 tables (week11_analysis.summary) into a
            new directory: summary.json, p_conn.csv, echo_cells.csv, etx_fits.csv
  estimate  session duration estimate of a plan (week11_analysis.estimate_session), no hardware
  note      end-of-session notes (temperature, photos) (week7_ppk2.py note)
Each session writes a NEW --out directory. Exit 0 = PASS. Run with device/host/.venv; close nRF Connect
Power Profiler first (it holds the PPK2 port).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week10_ppk2 as w10p  # noqa: E402
import week11_analysis as an  # noqa: E402
import week11_common as w11  # noqa: E402
import week11_link as wl  # noqa: E402
import week7_ppk2 as w7p  # noqa: E402
import week9_ppk2 as w9p  # noqa: E402

FS = ep.SAMPLE_RATE_HZ
SCHEMA = "week11-ppk2-link/1"
SESSION_SECONDS = 1800.0     # estimate 20-23 min + boot + >= 60 s after; set from the H4 dry run (+120 s)
BOOT_IDLE_S = 29.0           # window inside CONFIG_WEEK11_BOOT_IDLE_S = 30, 0.5 s after the self-test
IDLE_TOLERANCE_PCT = 10.0
TOOLS = ("week11_ppk2.py", "week11_analysis.py", "week11_etx_tc5.py", "week11_common.py", "week11_link.py", "week10_ppk2.py",
         "week10_analysis.py", "week10_common.py", "week10_ble.py", "week9_ppk2.py", "week9_common.py",
         "week9_figures.py", "week7_ppk2.py", "measure_energy.py", "energy_phases.py")
OP_COLUMNS = ["index", "block", "state", "state_name", "op", "a", "b", "refused", "refused_pulses", "start_sample",
              "ctrl_end_sample", "active_end_sample", "stop_sample", "t_op_ms", "t_window_ms", "E_op_uJ",
              "t_ctrl_ms", "E_ctrl_uJ", "t_dev_ms", "E_dev_uJ", "t_link_ms", "E_link_uJ", "t_tx_ms", "E_tx_uJ",
              "t_wait_ms", "E_wait_uJ", "t_gap_ms", "E_gap_uJ", "diff_pct", "gap_share_pct", "overlap_samples",
              "n_ev_tx", "tx_start_sample", "tx_end_sample", "data_threshold_ms", "E_burst_uJ", "t_burst_ms",
              "E_after_tx_uJ", "burst_error", "dev_high_fraction", "P_idle_gross_mW", "P_idle_net_mW", "idle_window_s",
              "empty_event_ms", "interval_median_ms", "interval_expected_ms", "interval_events", "interval_pass",
              "errors"]
VALID_COLUMNS = ["index", "block", "state", "state_name", "op", "a", "b", "t_op_ms", "E_op_uJ", "t_ctrl_ms",
                 "E_ctrl_uJ", "t_dev_ms", "E_dev_uJ", "t_link_ms", "E_link_uJ", "t_tx_ms", "E_tx_uJ", "t_wait_ms",
                 "E_wait_uJ", "E_echo_uJ", "P_conn_block_mW", "E_tx_marg_uJ", "E_wait_marg_uJ", "E_link_marg_uJ",
                 "E_dev_marg_uJ", "n_ev_tx", "E_burst_uJ", "t_burst_ms", "E_burst_marg_uJ", "E_after_tx_uJ",
                 "E_op_marg_uJ", "burst_error", "dev_high_fraction", "P_idle_gross_mW", "t_edge_ms"]


# ----------------------------------------------------------------------------- image


def image_info(image: Path, receipt: Path | None, plan_rows: list, session: int) -> dict:
    """A build_week11.ps1 folder (static check PASS, variant link, the session's plan, clean tree) + its
    flash_week11.ps1 receipt."""
    check = w7p.load_json(Path(image) / "week11_build_check.json")
    source = w7p.load_json(Path(image) / "source.json")
    digest = w11.sha256_hex(w11.plan_bytes(plan_rows))
    info = {"image": str(image), "build_id": check.get("build_id"), "variant": check.get("variant"),
            "session": check.get("session"), "check_status": check.get("status"), "dirty": source.get("dirty"),
            "commit": source.get("commit"), "bin_sha256": check.get("bin_sha256"),
            "set_sha256": check.get("set_sha256"), "plan_sha256": check.get("plan_sha256"), "kconfig": check.get("kconfig")}
    if check.get("status") != "PASS" or check.get("variant") != "link" or source.get("dirty"):
        raise SystemExit(f"{image}: static check not PASS, not the link variant, or dirty tree")
    if check.get("session") != session or check.get("plan_sha256") != digest:
        raise SystemExit(f"{image}: session {check.get('session')} plan {check.get('plan_sha256')} != "
                         f"session {session} plan {digest}")
    if receipt is not None:
        r = w7p.load_json(receipt)
        info["receipt"] = {"path": str(receipt), "exit_code": r.get("exit_code"), "build_id": r.get("build_id"),
                           "timestamp": r.get("timestamp"), "zip_sha256": r.get("zip_sha256")}
        if r.get("exit_code") != 0 or r.get("build_id") != info["build_id"]:
            raise SystemExit(f"{receipt}: DFU failed or receipt build differs from {image}")
    return info


# ----------------------------------------------------------------------------- analysis


def _flat(row: dict) -> dict:
    iv = row.get("interval") or {}
    return {**row, "interval_median_ms": iv.get("median_spacing_ms"), "interval_expected_ms": iv.get("expected_ms"),
            "interval_events": iv.get("events"), "interval_pass": iv.get("pass"), "errors": ";".join(row["errors"])}


def analyze(trace: ep.Trace, out: Path, plan_rows: list, ignore_counter: bool) -> dict:
    """Self-test, boot idle window (radio off), W11-D7 ops, W11-D8 blocks; analysis/ops.csv, blocks.json,
    summary.json."""
    phase_map = dict(ep.DEFAULT_MAP)
    analysis = ep.new_output_dir(out / "analysis")
    selftest = ep.selftest_check(trace, phase_map, 200.0)
    after = selftest["end_sample"] if selftest.get("found") else 0
    idle = None
    if selftest.get("found"):
        a = after + int(0.5 * FS)
        idle = ep.window_stats(trace, a, a + int(BOOT_IDLE_S * FS), channels=sorted(phase_map.values()))
        idle["all_markers_low"] = not any(idle["high_samples"].values())
    rows = an.segment_ops(trace, after + 1, plan_rows)
    blocks = an.block_table(rows)
    valid = an.valid_rows(rows, blocks)
    stray = {f"D{c}": int(np.count_nonzero((trace.bits >> c) & 1)) for c in range(8) if c not in phase_map.values()}
    diffs = [r["diff_pct"] for r in valid if r["op"] != "IDLE"]
    found_all = all("missing" not in r["errors"] for r in rows)
    checks = {
        "plan_not_refused": not an.plan_fail_signature(trace, after if selftest.get("found") else trace.n),
        "selftest_D0_D4": bool(selftest.get("pass")),
        "every_entry_found": found_all and rows[-1].get("extra_ctrl_after_plan", 1) == 0,
        "base_block_valid": blocks[0]["valid"],
        "reconnect_block_valid": blocks[len(w11.STATES)]["valid"],
        "every_block_valid_or_refused": all(b["valid"] or (b["refused"] and not
                                                          [e for e in b["state_errors"] if e])
                                            for b in blocks.values()),
        "diff_below_3pct_valid_ops": bool(diffs) and max(diffs) < ep.DIFF_LIMIT_PCT,
        "unused_channels_low": not any(stray.values()),
        **ep.data_loss_checks(trace, ignore_counter),
        "idle_markers_low": bool(idle and idle["all_markers_low"]),
    }
    summary = {
        "schema": "week11-link-analysis/1", "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
        "producer": "week11_ppk2.py analyze (week11_analysis.segment_ops / block_table, chunked loader)",
        "trace": {"source": trace.source, "samples": trace.n, "duration_s": trace.n * ep.DT_S,
                  "v_supply_mV": trace.v_supply_mv, **trace.info},
        "selftest": selftest, "idle": idle, "I_idle_uA": idle["mean_uA"] if idle else None,
        "entries": len(rows), "entries_valid": len(valid), "diff_pct": ep.describe(diffs),
        "blocks": {str(k): v for k, v in blocks.items()},
        "refused_states": [b["state_name"] for b in blocks.values() if b["refused"]],
        "unused_channel_high_samples": stray,
        "errors": {r["index"]: r["errors"] for r in rows if r["errors"]},
        "end_sample": int(rows[-1].get("stop_sample", 0)) if rows else 0,
    }
    with open(analysis / "ops.csv", "x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, OP_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow(_flat(r))
    (analysis / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


def trace_checks(out: Path, record: dict, meta: dict) -> tuple:
    summary = w7p.load_json(out / "analysis" / "summary.json")
    trace = w9p.load_raw_chunked(out / "ppk2")
    i_idle = summary.get("I_idle_uA")
    post = w9p.post_session_events(trace, [{"end_sample": summary["end_sample"]}], i_idle)
    post["radio_rule_w10"] = w10p.post_session_radio_rule(post, trace) if post.get("found") else {"pass": False}
    a = summary["checks"]
    checks = {
        "lab_on_ac_power": bool((record.get("ac_power") or {}).get("ok")),
        "capture_pass": meta.get("status") == "PASS",
        "idle_within_10pct_of_week2": i_idle is not None
                                      and abs(i_idle - w9p.WEEK2_IDLE_UA) / w9p.WEEK2_IDLE_UA * 100.0 <= IDLE_TOLERANCE_PCT,
        "no_data_loss": a.get("no_data_loss", record.get("ignore_counter", False)) and a.get("sample_rate_ok", False),
        **{k: a.get(k, False) for k in ("plan_not_refused", "selftest_D0_D4", "every_entry_found", "base_block_valid",
                                        "reconnect_block_valid", "every_block_valid_or_refused",
                                        "diff_below_3pct_valid_ops", "unused_channels_low", "idle_markers_low")},
        "post_window_at_least_20s": post.get("found", False) and post["duration_s"] >= 20.0,
        "post_mean_at_idle": post.get("deviation_from_idle_pct", float("inf")) <= IDLE_TOLERANCE_PCT,
        "post_radio_off": post["radio_rule_w10"]["pass"],
    }
    details = {"I_idle_uA": i_idle, "post_session": post, "diff_pct": summary.get("diff_pct"),
               "refused_states": summary.get("refused_states"), "v_supply_mV": trace.v_supply_mv,
               "blocks": {k: {x: v[x] for x in ("state_name", "valid", "refused", "P_conn_gross_mW", "P_conn_drift_pct",
                                                "drift_alarm", "op_error_pct")}
                          for k, v in summary["blocks"].items()}}
    return checks, details


def rows_from_csv(path: Path) -> list:
    """analysis/ops.csv back into the dict rows of week11_analysis (numbers, errors list, interval)."""
    ints = {"index", "block", "state", "a", "b", "refused_pulses", "start_sample", "ctrl_end_sample",
            "active_end_sample", "stop_sample", "overlap_samples", "n_ev_tx", "interval_events", "tx_start_sample",
            "tx_end_sample"}
    rows = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            row = {}
            for k, v in r.items():
                if v in ("", None):
                    continue
                if k in ("op", "state_name", "burst_error"):
                    row[k] = v
                elif k in ("refused", "interval_pass"):
                    row[k] = v == "True"
                elif k == "errors":
                    pass
                else:
                    row[k] = int(v) if k in ints else float(v)
            row["errors"] = [e for e in r["errors"].split(";") if e]
            row.setdefault("refused", False)
            if r.get("interval_median_ms") not in ("", None) or r.get("interval_pass") not in ("", None):
                row["interval"] = {"median_spacing_ms": row.get("interval_median_ms"),
                                   "expected_ms": row.get("interval_expected_ms"), "events": row.get("interval_events"),
                                   "pass": row.get("interval_pass", False)}
            for n in ("ctrl", "dev", "link", "tx", "wait"):
                row.setdefault(f"t_{n}_ms", 0.0)
                row.setdefault(f"E_{n}_uJ", 0.0)
            rows.append(row)
    return rows


def evaluate(out: Path, record: dict, meta: dict, kind: str) -> int:
    checks, details = trace_checks(out, record, meta)
    if not (out / "edge" / "summary.json").exists():
        details["kv260_log"] = "PENDING: week11_ppk2.py import"
        return w7p.finish(out, kind, checks, details)
    edge = w7p.load_json(out / "edge" / "summary.json")
    rows = rows_from_csv(out / "analysis" / "ops.csv")
    blocks = an.block_table(rows)
    records = an.normalize_echo_records((out / "edge" / "kv260_echo.jsonl").read_text(encoding="utf-8").splitlines())
    echo = an.check_echo_records(records, rows)
    events = [json.loads(x) for x in (out / "edge" / "kv260_link_events.jsonl").read_text(encoding="utf-8").splitlines()
              if x.strip()]
    trace_rows = [r for r in rows if r["op"] == "ECHO" and "active_end_sample" in r]
    offsets = [x["t_rx_ms"] - (r["active_end_sample"] * an.DT_MS - r["t_wait_ms"])
               for r, x in zip(trace_rows, records) if isinstance(x.get("t_rx_ms"), (int, float))]
    offset = float(np.median(offsets)) if offsets else 0.0
    link = an.check_link_events(events, rows, blocks, offset)
    reconnects = sum(1 for r in rows if r["op"] == "RECONNECT")
    checks.update({"kv260_one_echo_record_per_entry": echo["pass"], "kv260_granted_parameters_equal_plan": link["pass"],
                   "kv260_connections_1_plus_reconnects": edge.get("connections") == 1 + reconnects})
    details.update(echo_match=echo, link_events=link, clock_offset_ms=offset, kv260_log=edge.get("source_log"))
    status = "PASS" if all(checks.values()) else "FAIL"
    if echo["pass"]:
        valid = an.valid_rows(rows, blocks)
        stamp = "" if kind == "link" else f"_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        with open(out / f"ops_valid{stamp}.csv", "x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, VALID_COLUMNS, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(valid)
        w7p.write_new_json(out / f"energy_link{stamp}.json", {
            "schema": "week11-energy-link-session/1", "decision": "W11-D7..D14", "status": status, "session": str(out),
            "plan_session": record.get("plan_session"), "image": record.get("image"),
            "temp_room_C": record.get("temp_room_C"), "I_idle_uA": details["I_idle_uA"],
            "single_session_tables": an.summary({"s": valid}, {"s": blocks}),
            "note": "single-session numbers; the result is summary over >= 2 sessions"})
    return w7p.finish(out, kind, checks, details)


# ----------------------------------------------------------------------------- commands


def cmd_session(args) -> int:
    plans = wl.load_plan(args.plan)
    rows = plans[args.session]
    image = image_info(args.image, args.receipt, rows, args.session)
    power = w10p.ac_power()
    if not power["ok"] and not args.ac_confirmed:
        raise SystemExit(f"laptop not on AC (Win32_Battery {power}); plug the charger (lab rule 09/11)")
    out = w7p.new_out(args.out)
    est = an.estimate_session(rows)
    record = {
        "schema": SCHEMA, "kind": "session", "command": sys.argv, "started_utc": datetime.now(timezone.utc).isoformat(),
        "temp_room_C": args.temp_c, "v_supply_mV": 5000,
        "power": "PPK2 Source Meter -> USB breakout VBUS 5 V; dongle not on laptop USB",
        "ac_power": power if power["ok"] else {**power, "ok": True, "manual_confirmation": True},
        "image": image, "plan_dir": str(Path(args.plan)), "plan_session": args.session,
        "plan_sha256": w11.sha256_hex(w11.plan_bytes(rows)), "entries": len(rows), "seconds": args.seconds,
        "estimate_s": {k: v["total_s"] for k, v in est.items()},
        "peer": "KV260 echo service (H3 part 3): connects by itself, accepts every parameter request, ack/full echo, "
                "reconnects after a device disconnect; echo + link-event logs imported afterwards (import)",
        "ignore_counter": bool(args.ignore_counter), "note": args.note,
        "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS if (HERE / n).exists()},
    }
    if args.seconds < est["slow"]["total_s"]:
        raise SystemExit(f"--seconds {args.seconds} below the slow estimate {est['slow']['total_s']:.0f} s")
    w7p.write_new_json(out / "session.json", record)
    print("KV260 echo service must be up and logging (btmon too); do not touch the bench or the laptop")
    meta = w7p.run_capture(args, out, f"W11-link-session{args.session}", args.seconds)
    analyze(w9p.load_raw_chunked(out / "ppk2"), out, rows, args.ignore_counter)
    return evaluate(out, record, meta, "session")


def cmd_import(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != SCHEMA:
        raise SystemExit(f"{out} is not a week 11 link session directory")
    edge = out / "edge"
    edge.mkdir(exist_ok=False)
    shutil.copyfile(args.kv260_log, edge / "kv260_echo_raw.jsonl")
    shutil.copyfile(args.link_events, edge / "kv260_link_events.jsonl")
    lines = (edge / "kv260_echo_raw.jsonl").read_text(encoding="utf-8").splitlines()
    records = an.normalize_echo_records(lines)
    with open(edge / "kv260_echo.jsonl", "x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps({"ev": "echo", **r}) + "\n")
    connections = sum(1 for x in lines if x.strip() and json.loads(x).get("ev") in ("connected", "connection"))
    extra = {}
    for path in args.btsnoop or []:
        target = edge / Path(path).name
        shutil.copyfile(path, target)
        extra[target.name] = w7p.sha256(target)
    w7p.write_new_json(edge / "summary.json", {
        "schema": "week11-kv260-import/1", "source_log": str(args.kv260_log),
        "source_log_sha256": w7p.sha256(edge / "kv260_echo_raw.jsonl"), "link_events": str(args.link_events),
        "link_events_sha256": w7p.sha256(edge / "kv260_link_events.jsonl"), "btsnoop_sha256": extra,
        "connections": connections or None, "echo_records": len(records),
        "imported_utc": datetime.now(timezone.utc).isoformat()})
    print(f"KV260 log: {len(records)} echo records, {connections} connection events")
    return evaluate(out, record, w7p.load_json(out / "ppk2" / "capture.json"), "link")


def cmd_recheck(args) -> int:
    out = Path(args.out)
    record = w7p.load_json(out / "session.json")
    if record.get("schema") != SCHEMA:
        raise SystemExit(f"{out} is not a week 11 link session directory")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return evaluate(out, record, w7p.load_json(out / "ppk2" / "capture.json"), f"link_recheck-{stamp}")


def _valid_from_csv(path: Path) -> list:
    rows = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            row = {}
            for k, v in r.items():
                if v in ("", None):
                    row[k] = None
                elif k in ("op", "state_name", "burst_error"):
                    row[k] = v
                elif k in ("index", "block", "state", "a", "b", "n_ev_tx"):
                    row[k] = int(v)
                else:
                    row[k] = float(v)
            rows.append(row)
    return rows


def cmd_summary(args) -> int:
    if len(args.session) < 2:
        raise SystemExit("summary needs >= 2 PASS sessions")
    rows_by, blocks_by, used = {}, {}, {}
    for path in args.session:
        path = Path(path)
        results = sorted(path.glob("check_link*.json"))
        if not results or w7p.load_json(results[-1]).get("status") != "PASS":
            raise SystemExit(f"{path}: no PASS result after import")
        record = w7p.load_json(path / "session.json")
        key = f"s{record['plan_session']}-{path.name}"
        rows_by[key] = _valid_from_csv(path / "ops_valid.csv")
        blocks_by[key] = an.block_table(rows_from_csv(path / "analysis" / "ops.csv"))
        used[key] = {"dir": str(path), "result": str(results[-1]), "plan_session": record["plan_session"]}
    if len({v["plan_session"] for v in used.values()}) < 2:
        raise SystemExit("summary needs both plan sessions (0 and 1)")
    out = w7p.new_out(args.out)
    result = an.summary(rows_by, blocks_by)
    w7p.write_new_json(out / "summary.json", {"schema": "week11-link-summary/1", "sessions": used,
                                              "tool_sha256": {n: w7p.sha256(HERE / n) for n in TOOLS if (HERE / n).exists()},
                                              **result})
    with open(out / "p_conn.csv", "x", encoding="utf-8", newline="") as h:
        w = csv.writer(h, lineterminator="\n")
        w.writerow(["state", "phy", "interval_ms", "latency", "tx_octets", "tx_power_dbm", "n", "P_conn_gross_mW",
                    "ci95_half_mW", "session_range_pct", "P_conn_net_mW"])
        for name, v in result["P_conn"].items():
            g = v["P_conn_gross_mW"]
            w.writerow([name, v["phy"], v["interval_ms"], v["latency"], v["tx_octets"], v["tx_power_dbm"], g.get("n"),
                        g.get("mean"), g.get("ci95_half"), g.get("session_range_pct"), v["P_conn_net_mW"]])
    with open(out / "echo_cells.csv", "x", encoding="utf-8", newline="") as h:
        w = csv.writer(h, lineterminator="\n")
        keys = ("E_burst_uJ", "t_burst_ms", "E_burst_marg_uJ", "n_ev_tx", "E_op_uJ", "t_op_ms", "E_op_marg_uJ",
                "E_tx_uJ", "t_tx_ms", "E_wait_uJ", "t_wait_ms", "E_echo_uJ", "E_tx_marg_uJ", "E_wait_marg_uJ",
                "E_after_tx_uJ")
        w.writerow(["state", "B", "flags", "usable", "burst_errors"] +
                   [f"{k}_{s}" for k in keys for s in ("mean", "ci95_half", "range_pct")])
        for c in result["echo_cells"].values():
            w.writerow([c["state_name"], c["B"], c["flags"], c["usable"], c["burst_errors"]] +
                       [x for k in keys for x in (c[k].get("mean"), c[k].get("ci95_half"), c[k].get("session_range_pct"))])
    with open(out / "etx_fits.csv", "x", encoding="utf-8", newline="") as h:
        w = csv.writer(h, lineterminator="\n")
        # primary = E_tx,full (burst) and the break-even beta' (E_op,marg, ack); marker = D2 as in week 10 (W11-D10)
        w.writerow(["state", "alpha_full_uJ", "beta_full_uJ_per_B", "r2_teacher7_full", "teacher_r2_pass",
                    "beta_full_all_ops", "r2_full_all_ops", "alpha_op_marg_uJ", "beta_prime_uJ_per_B",
                    "r2_op_marg_teacher7", "beta_prime_all_ops", "n_ev_per_B", "burst_errors",
                    "alpha_marker_uJ", "beta_marker_uJ_per_B", "r2_marker_teacher7", "marker_teacher_r2_pass",
                    "E_wait_slope_uJ_per_B"])
        for v in result["E_tx_fits"].values():
            t, o, b, ba, k = (v["teacher_fit"], v["all_ops_fit"], v["breakeven_beta_teacher_fit"],
                              v["breakeven_beta_all_ops_fit"], v["marker_teacher_fit"])
            w.writerow([v["state_name"], t.get("intercept"), t.get("slope"), t.get("r2"), v["teacher_r2_pass"],
                        o.get("slope"), o.get("r2"), b.get("intercept"), b.get("slope"), b.get("r2"), ba.get("slope"),
                        v["n_ev_vs_B"].get("slope"), v["burst_errors"], k.get("intercept"), k.get("slope"), k.get("r2"),
                        v["marker_teacher_r2_pass"], v["E_wait_vs_B_ack"].get("slope")])
    print(f"summary -> {out}; states missing: {result['states_missing']}")
    return 0


def cmd_estimate(args) -> int:
    plans = wl.load_plan(args.plan)
    out = {f"s{k}": an.estimate_session(rows) for k, rows in plans.items()}
    for k, v in out.items():
        print(f"{k}: fast {v['fast']['total_s'] / 60:.1f} min, slow {v['slow']['total_s'] / 60:.1f} min")
    if args.output:
        w7p.write_new_json(args.output, {"schema": "week11-session-estimate/1", "estimate": out,
                                         "assumptions": {"central_pdu_cap_fast": an.EST_CENTRAL_PDU_CAP,
                                                         "turnaround_events": an.EST_TURNAROUND_EVENTS,
                                                         "state_ms": an.EST_STATE_MS,
                                                         "reconnect_ms": an.EST_RECONNECT_MS}})
    return 0


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
    p.add_argument("--seconds", type=float, default=SESSION_SECONDS)
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--temp-c", type=float, required=True, help="room temperature at start")
    p.add_argument("--image", type=Path, required=True, help="build_week11.ps1 folder (link, clean)")
    p.add_argument("--receipt", type=Path, required=True, help="DFU receipt JSON of flash_week11.ps1")
    p.add_argument("--plan", type=Path, required=True, help="generate_week11_plan.py directory")
    p.add_argument("--session", type=int, choices=[0, 1], required=True, help="plan session of the image")
    p.add_argument("--ac-confirmed", action="store_true", help="laptop on AC checked by hand (no battery reading)")
    p.add_argument("--note", default="", help="e.g. KV260 distance, service commit")
    p.add_argument("--ignore-counter", action="store_true")
    p.set_defaults(func=cmd_session)
    p = sub.add_parser("import")
    p.add_argument("--out", type=Path, required=True, help="the session directory")
    p.add_argument("--kv260-log", type=Path, required=True, help="KV260 echo service log (JSON lines)")
    p.add_argument("--link-events", type=Path, required=True,
                   help="granted parameters seen by the central (JSON lines: conn_update / phy_update / data_len, t_ms)")
    p.add_argument("--btsnoop", type=Path, action="append", help="btmon capture(s), copied with SHA-256")
    p.set_defaults(func=cmd_import)
    p = sub.add_parser("recheck")
    p.add_argument("--out", type=Path, required=True, help="existing session directory")
    p.set_defaults(func=cmd_recheck)
    p = sub.add_parser("summary")
    p.add_argument("--session", action="append", default=[], help="PASS session directory (>= 2, both plans)")
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.set_defaults(func=cmd_summary)
    p = sub.add_parser("estimate")
    p.add_argument("--plan", type=Path, required=True, help="generate_week11_plan.py directory")
    p.add_argument("--output", type=Path, help="new JSON file")
    p.set_defaults(func=cmd_estimate)
    p = sub.add_parser("note")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--temp-end-c", type=float)
    p.add_argument("--photo", action="append", default=[])
    p.add_argument("--text", default="")
    p.set_defaults(func=w7p.cmd_note)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
