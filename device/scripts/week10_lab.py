#!/usr/bin/env python3
"""Week 10 lab driver (dongle with the ble-usb image on laptop USB): USB CDC commands + capture, then
check_week10.py. TC2, radio-on part (W10-D4).

  verify        STATUS, VERIFY ALL (50 samples x 11 splits: q/scale SHA-256, the plain request of every
                s <= 9, the s10 logits/label), STACK. No link needed.
  session       dry run against the KV260: wait until the KV260 has connected and subscribed (LINK ready=1),
                CONNPARAM 12 12 (15 ms, k = 0), then SESSION <gap_ms> <first> <count> (default: the whole
                W10-D4 plan with the energy session's 1000 ms gap, about 12 min), every cycle printed.
  import-kv260  the KV260 request log of that run (+ its offline predictions per s, + the queue_sim output
                directory if the service ran with the queue) -> edge/, then check_week10.py session.
Each run writes a NEW --out directory: cdc.log (week 6 format), session.json, check_<kind>.json.
USB CDC helpers are week6_lab's, unmodified. Laptop power: correctness and CPU-time evidence, never
energy numbers. Run with device/host/.venv (gcc on PATH for the host references). Exit 0 = PASS.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week10_ble as wb  # noqa: E402
import week10_common as w10  # noqa: E402
import week6_common as wc  # noqa: E402
import week6_lab as w6  # noqa: E402

TOOLS = ("week10_lab.py", "week10_ble.py", "week10_common.py", "check_week10.py", "week10_analysis.py",
         "week9_common.py", "week8_common.py", "week8_lab.py", "week7_common.py", "week6_lab.py", "week6_common.py")


def session_record(out: Path, kind: str, extra: dict) -> None:
    wc.write_new_json(out / "session.json", {
        "schema": "week10-lab-session/1",
        "kind": kind,
        "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": {n: wc.sha256_file(HERE / n) for n in TOOLS},
        "scope": "dongle on laptop USB power: correctness and CPU-time evidence, never energy numbers",
        **extra,
    })


def open_cdc(port, out: Path) -> tuple:
    cdc = w6.Cdc(port, out / "cdc.log")
    cdc.open()
    _, banner = cdc.wait(r"^READY WEEK10 ", 0, 20)
    return cdc, wc.kv(banner)


def require_image(banner: dict, sample_set) -> None:
    if banner.get("variant") != "ble-usb":
        raise SystemExit(f"dongle runs variant {banner.get('variant')!r}, this step needs 'ble-usb'")
    if banner.get("set_sha256") != sample_set.set_sha256:
        raise SystemExit(f"image set {banner.get('set_sha256')} != W8-D3 set {sample_set.set_sha256}")
    if banner.get("plan_sha256") != w10.BLE_PLAN_SHA256 or banner.get("plan_ok") != "1":
        raise SystemExit(f"image plan {banner.get('plan_sha256')} (ok={banner.get('plan_ok')}) "
                         f"!= W10-D4 plan {w10.BLE_PLAN_SHA256}")


def checker(kind: str, out: Path, record: dict) -> int:
    cmd = [sys.executable, "-B", str(HERE / "check_week10.py"), kind, "--session", str(out),
           "--samples", record["samples"], "--plan", record["plan"],
           "--output", str(out / f"check_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")]
    if kind == "session":
        cmd += ["--first", str(record["first"]), "--count", str(record["count"])]
    print("+", " ".join(cmd))
    return subprocess.run(cmd).returncode


def prepare(args, kind: str, extra: dict) -> tuple:
    sample_set = wb.w8.load_set(args.samples)    # authenticate before touching the dongle
    w10.load_plans(args.plan)
    out = w6.new_out(args.out)
    record = {"samples": str(args.samples), "plan": str(args.plan), "set_sha256": sample_set.set_sha256,
              "plan_sha256": w10.BLE_PLAN_SHA256, **extra}
    session_record(out, kind, record)
    cdc, banner = open_cdc(args.port, out)
    return out, cdc, banner, sample_set, record


def cmd_verify(args) -> int:
    out, cdc, banner, sample_set, record = prepare(args, "verify", {})
    try:
        require_image(banner, sample_set)
        cdc.wait(r"^READY WEEK10 ", cdc.send("STATUS"), 10)
        cdc.wait(r"^VERIFY END", cdc.send("VERIFY ALL"), 900)
        start = cdc.send("STACK")
        cdc.wait(r"^STACK main ", start, 10)
    finally:
        cdc.close()
    return checker("verify", out, record)


def wait_link(cdc, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        _, text = cdc.wait(r"^LINK connected=", cdc.send("STATUS"), 10)
        info = wc.kv(text)
        if info.get("ready") == "1":
            return info
        if time.monotonic() > deadline:
            raise SystemExit(f"no ready link after {timeout_s} s (KV260 service connected to ASI-SV1 and "
                             "subscribed to TX notifications?)")
        time.sleep(2.0)


def cmd_session(args) -> int:
    if not 0 <= args.first < w10.BLE_CYCLES or not 1 <= args.count <= w10.BLE_CYCLES - args.first:
        raise SystemExit("--first/--count outside the 550-cycle plan")
    out, cdc, banner, sample_set, record = prepare(args, "session", {
        "gap_ms": args.gap_ms, "first": args.first, "count": args.count, "conn_interval_1250us": args.conn_interval,
        "peer": f"external: {args.peer_name}"})
    try:
        require_image(banner, sample_set)
        wait_link(cdc, args.connect_timeout_s)
        if args.conn_interval:
            cdc.send(f"CONNPARAM {args.conn_interval} {args.conn_interval}")
            time.sleep(3.0)
        cdc.wait(r"^LINK connected=", cdc.send("STATUS"), 10)
        start = cdc.send(f"SESSION {args.gap_ms} {args.first} {args.count}")
        _, text = cdc.wait(r"^(SESSION BEGIN|ERROR)", start, 15)
        if text.startswith("ERROR"):
            raise SystemExit(f"device refused: {text}")
        cdc.wait(r"^SESSION END ", start, args.count * (args.gap_ms / 1000.0 + 6.0) + 120)
    finally:
        cdc.close()
    print(f"console part done -> {out}. Get the {args.peer_name} request log (+ queue_sim directory), then:\n"
          f"  week10_lab.py import-kv260 --out {out} --kv260-log <file> --edge-reference <predictions.jsonl>"
          " [--queue-dir <dir>]")
    return checker("session", out, record)


def dongle_cycles(out: Path) -> dict:
    """{cycle: (request_id, logits bits)} of the CYCLE lines of cdc.log."""
    rows = {}
    for _, text in wc.read_capture(out / "cdc.log"):
        if text.startswith("CYCLE i="):
            r = wc.kv(text)
            rows[int(r["i"])] = (int(r["rid"]), r["logits"])
    return rows


def cmd_import_kv260(args) -> int:
    import week10_analysis as wa
    out = Path(args.out)
    record = json.loads((out / "session.json").read_text(encoding="utf-8"))
    if record.get("schema") != "week10-lab-session/1" or record.get("kind") != "session":
        raise SystemExit(f"{out} is not a week10_lab.py session directory")
    host = wb.HostRefs(Path(record["samples"]), Path(record["plan"]), out / "host_shim")
    edge_ref = wb.load_edge_reference(args.edge_reference, host)
    edge = out / "edge"
    edge.mkdir(exist_ok=False)
    raw = edge / "kv260_requests_raw.jsonl"
    shutil.copyfile(args.kv260_log, raw)
    for i, path in enumerate(args.edge_reference):
        shutil.copyfile(path, edge / f"edge_reference_{i}{Path(path).suffix}")
    records, counters = wb.normalize_kv260_log(raw.read_text(encoding="utf-8").splitlines(), host)
    with open(edge / "peer.jsonl", "x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps({"ev": "request", **r}) + "\n")
    rows = list(host.plans.ble)[record["first"]:record["first"] + record["count"]]
    result = wb.evaluate_requests(records, counters, rows, edge_ref, dongle_cycles(out))
    queue_match = None
    if args.queue_dir:
        shutil.copytree(args.queue_dir, edge / "queue")
        fg = wa.foreground_rows(wa.queue_jobs(wa.read_jsonl(edge / "queue" / "jobs.jsonl")))
        t_rx = [r.get("t_rx_ms") for r in records]
        queue_match = wa.match_requests(t_rx, fg) if all(isinstance(t, (int, float)) for t in t_rx) else \
            {"pass": False, "reason": "t_rx_ms missing in the KV260 request log"}
        result["checks"]["requests_through_queue_fifo"] = bool(queue_match["pass"])
    elif args.require_queue:
        result["checks"]["requests_through_queue_fifo"] = False
    wc.write_new_json(edge / "summary.json", {
        "schema": "week10-kv260-import/1", "source_log": str(args.kv260_log), "source_log_sha256": wc.sha256_file(raw),
        "edge_reference": edge_ref["sources_sha256"], "queue_dir": str(args.queue_dir) if args.queue_dir else None,
        "queue_match": queue_match, "imported_utc": datetime.now(timezone.utc).isoformat(), "counters": counters,
        "result": result, "tool_sha256": {n: wc.sha256_file(HERE / n) for n in TOOLS}})
    print(f"KV260 log: {len(records)} requests {counters}")
    return checker("session", out, record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", type=Path, required=True, help="new directory")
        p.add_argument("--port", help="application CDC port (default: VID 2FE3 PID 0004)")
        p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
        p.add_argument("--plan", type=Path, required=True, help="generate_week10_plan.py directory")

    p = sub.add_parser("verify")
    common(p)
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("session")
    common(p)
    p.add_argument("--gap-ms", type=int, default=1000, help="gap between cycles (energy session: 1000)")
    p.add_argument("--first", type=int, default=0, help="first cycle of the plan")
    p.add_argument("--count", type=int, default=w10.BLE_CYCLES, help="cycles")
    p.add_argument("--conn-interval", type=int, default=12, help="CONNPARAM in 1.25 ms units (0 = do not ask)")
    p.add_argument("--connect-timeout-s", type=float, default=180.0)
    p.add_argument("--peer-name", default="KV260")
    p.set_defaults(func=cmd_session)
    p = sub.add_parser("import-kv260")
    p.add_argument("--out", type=Path, required=True, help="the session directory")
    p.add_argument("--kv260-log", type=Path, required=True, help="KV260 request log (JSON lines, with split)")
    p.add_argument("--edge-reference", type=Path, action="append", required=True,
                   help="KV260 offline predictions (one file with a split field, or one file per s)")
    p.add_argument("--queue-dir", type=Path, help="queue_sim output of the run (jobs.jsonl, ...)")
    p.add_argument("--require-queue", action="store_true", help="fail when --queue-dir is missing (TC2)")
    p.set_defaults(func=cmd_import_kv260)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
