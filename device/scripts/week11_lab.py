#!/usr/bin/env python3
"""Week 11 lab driver (dongle with the link-usb image on laptop USB): USB CDC commands + capture, then
check_week11.py. TC4 (VERIFY before the week 12 lab) and the joint KV260 tests (H3 part 2, H4).

  verify   STATUS, VERIFY (S0c of the 100 W8-D3 inputs + plan digest), STACK. No link needed.
  session  dry run against the KV260 echo service: wait until the KV260 has connected and subscribed (LINK
           ready=1), then SESSION <first> <count> (default: the whole session plan), every entry printed.
  cmd      one or more console lines (e.g. "STATEX 3 24 0 251 0", "ECHO 4096 1 10", "RECONNECT"), each sent
           after the previous one answered; for the KV260 capability tests. Not checked, only captured.
Each run writes a NEW --out directory: cdc.log (week 6 format), session.json, check_<kind>.json. USB CDC
helpers are week6_lab's, unmodified. Laptop power: correctness and CPU-time evidence, never energy numbers.
Run with device/host/.venv (gcc on PATH for the host references). Exit 0 = PASS.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week11_link as wl  # noqa: E402
import week6_common as wc  # noqa: E402
import week6_lab as w6  # noqa: E402

TOOLS = ("week11_lab.py", "week11_link.py", "week11_common.py", "check_week11.py", "generate_week11_plan.py",
         "test_week11_s0c_host.py", "week10_common.py", "week9_common.py", "week6_lab.py", "week6_common.py")
# Answers of the console, per command word (regex of the line that ends it).
ENDS = {"STATE": r"^OP i=", "STATEX": r"^OP i=", "IDLE": r"^OP i=", "S0C": r"^OP i=", "RECONNECT": r"^LINK connected=",
        "ECHO": r"^ECHO END", "RSSI": r"^LINK connected=", "STATUS": r"^LINK connected=", "LATENCY": r"^LATENCY ",
        "MARKERS": r"^MARKERS END", "STACK": r"^STACK main ", "VERIFY": r"^VERIFY END"}


def session_record(out: Path, kind: str, extra: dict) -> None:
    wc.write_new_json(out / "session.json", {
        "schema": "week11-lab-session/1", "kind": kind, "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": {n: wc.sha256_file(HERE / n) for n in TOOLS},
        "scope": "dongle on laptop USB power: correctness and CPU-time evidence, never energy numbers", **extra})


def open_cdc(port, out: Path) -> tuple:
    cdc = w6.Cdc(port, out / "cdc.log")
    cdc.open()
    _, banner = cdc.wait(r"^READY WEEK11 ", 0, 20)
    return cdc, wl.kv(banner)


def require_image(banner: dict, session: int, digest: str) -> None:
    if banner.get("variant") != "link-usb":
        raise SystemExit(f"dongle runs variant {banner.get('variant')!r}, this step needs 'link-usb'")
    if banner.get("session") != str(session) or banner.get("plan_sha256") != digest or banner.get("plan_ok") != "1":
        raise SystemExit(f"image session {banner.get('session')} plan {banner.get('plan_sha256')} "
                         f"(ok={banner.get('plan_ok')}) != session {session} plan {digest}")


def checker(kind: str, out: Path, args, first: int = 0, count: int | None = None) -> int:
    cmd = [sys.executable, "-B", str(HERE / "check_week11.py"), kind, "--session-dir", str(out),
           "--samples", str(args.samples), "--plan", str(args.plan), "--session", str(args.session),
           "--output", str(out / f"check_{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")]
    if kind == "session":
        cmd += ["--first", str(first), "--count", str(count)]
    print("+", " ".join(cmd))
    return subprocess.run(cmd).returncode


def prepare(args, kind: str, extra: dict) -> tuple:
    rows = wl.load_plan(args.plan)[args.session]    # authenticate before touching the dongle
    digest = wl.w11.sha256_hex(wl.w11.plan_bytes(rows))
    out = w6.new_out(args.out)
    session_record(out, kind, {"samples": str(args.samples), "plan": str(args.plan), "session": args.session,
                               "plan_sha256": digest, **extra})
    cdc, banner = open_cdc(args.port, out)
    return out, cdc, banner, rows, digest


def wait_link(cdc, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        _, text = cdc.wait(r"^LINK connected=", cdc.send("STATUS"), 10)
        info = wl.kv(text)
        if info.get("ready") == "1":
            return info
        if time.monotonic() > deadline:
            raise SystemExit(f"no ready link after {timeout_s} s (KV260 echo service connected to ASI-SV1 and "
                             "subscribed to TX notifications?)")
        time.sleep(2.0)


def cmd_verify(args) -> int:
    out, cdc, banner, rows, digest = prepare(args, "verify", {})
    try:
        require_image(banner, args.session, digest)
        cdc.wait(r"^VERIFY END", cdc.send("VERIFY"), 300)
        cdc.wait(r"^STACK main ", cdc.send("STACK"), 10)
    finally:
        cdc.close()
    return checker("verify", out, args)


def cmd_session(args) -> int:
    rows = wl.load_plan(args.plan)[args.session]
    count = args.count if args.count is not None else len(rows) - args.first
    if not 0 <= args.first < len(rows) or not 1 <= count <= len(rows) - args.first:
        raise SystemExit("--first/--count outside the session plan")
    out, cdc, banner, rows, digest = prepare(args, "session", {"first": args.first, "count": count,
                                                               "peer": f"external: {args.peer_name}"})
    try:
        require_image(banner, args.session, digest)
        wait_link(cdc, args.connect_timeout_s)
        cdc.wait(r"^SESSION END", cdc.send(f"SESSION {args.first} {count}"), args.timeout_s)
    finally:
        cdc.close()
    return checker("session", out, args, args.first, count)


def cmd_cmd(args) -> int:
    out, cdc, banner, rows, digest = prepare(args, "cmd", {"lines": args.line})
    try:
        require_image(banner, args.session, digest)
        if args.wait_link:
            wait_link(cdc, args.connect_timeout_s)
        for line in args.line:
            word = line.split(" ")[0]
            cdc.wait(ENDS.get(word, r"^(OP i=|ERROR)"), cdc.send(line), args.timeout_s)
    finally:
        cdc.close()
    print(f"captured: {out / 'cdc.log'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", type=Path, required=True, help="new directory")
        p.add_argument("--port", help="application CDC port (default: VID 2FE3 PID 0004)")
        p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
        p.add_argument("--plan", type=Path, required=True, help="generate_week11_plan.py directory")
        p.add_argument("--session", type=int, choices=[0, 1], required=True, help="plan session of the image")

    p = sub.add_parser("verify")
    common(p)
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("session")
    common(p)
    p.add_argument("--first", type=int, default=0)
    p.add_argument("--count", type=int)
    p.add_argument("--connect-timeout-s", type=float, default=180.0)
    p.add_argument("--timeout-s", type=float, default=7200.0, help="whole SESSION")
    p.add_argument("--peer-name", default="KV260")
    p.set_defaults(func=cmd_session)
    p = sub.add_parser("cmd")
    common(p)
    p.add_argument("line", nargs="+", help="console lines, in order")
    p.add_argument("--wait-link", action="store_true", help="wait for LINK ready=1 first")
    p.add_argument("--connect-timeout-s", type=float, default=180.0)
    p.add_argument("--timeout-s", type=float, default=600.0, help="per line")
    p.set_defaults(func=cmd_cmd)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
