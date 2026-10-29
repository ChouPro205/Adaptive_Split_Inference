#!/usr/bin/env python3
"""Week 9 lab driver (dongle with the dev-usb image on laptop USB): USB CDC commands + capture,
then check_week9.py.

  verify   STATUS, VERIFY ALL (50 samples x 11 splits, q/scale SHA-256), TDEV ALL (DWT t_dev of every
           s, IRQs locked), STACK                                                          (TC2)
  session  SESSION <gap_ms> <first> <count>: dry run of the W9-D4 plan, every cycle printed
           (default: the whole plan with the energy session's 1000 ms gap, about 11 min)
Each run writes a NEW --out directory: cdc.log (week 6 format), session.json, check_<kind>.json.
USB CDC helpers are week6_lab's, unmodified. Laptop power: correctness and CPU-time evidence, never
energy numbers. Run with device/host/.venv. Exit 0 = the checker PASSED.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402
import week6_lab as w6  # noqa: E402
import week9_common as w9  # noqa: E402

TOOLS = ("week9_lab.py", "week9_common.py", "check_week9.py", "test_week9_host.py", "week8_common.py",
         "week7_common.py", "week6_lab.py", "week6_common.py")


def session_record(out: Path, kind: str, extra: dict) -> None:
    wc.write_new_json(out / "session.json", {
        "schema": "week9-lab-session/1",
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
    _, banner = cdc.wait(r"^READY WEEK9 ", 0, 20)
    return cdc, wc.kv(banner)


def require_image(banner: dict, sample_set) -> None:
    if banner.get("variant") != "dev-usb":
        raise SystemExit(f"dongle runs variant {banner.get('variant')!r}, this step needs 'dev-usb'")
    if banner.get("set_sha256") != sample_set.set_sha256:
        raise SystemExit(f"image set {banner.get('set_sha256')} != W8-D3 set {sample_set.set_sha256}")
    if banner.get("plan_sha256") != w9.PLAN_SHA256 or banner.get("plan_ok") != "1":
        raise SystemExit(f"image plan {banner.get('plan_sha256')} (ok={banner.get('plan_ok')}) "
                         f"!= W9-D4 plan {w9.PLAN_SHA256}")


def checker(kind: str, out: Path, args, extra: list = ()) -> int:
    cmd = [sys.executable, "-B", str(HERE / "check_week9.py"), kind, "--session", str(out),
           "--samples", str(args.samples), "--refs", str(args.refs),
           "--output", str(out / f"check_{kind}.json"), *extra]
    print("+", " ".join(cmd))
    return subprocess.run(cmd).returncode


def prepare(args, kind: str, extra: dict) -> tuple:
    sample_set = w9.w8.load_set(args.samples)   # authenticate before touching the dongle
    w9.load_refs(args.refs, sample_set)
    out = w6.new_out(args.out)
    session_record(out, kind, {"samples": str(args.samples), "refs": str(args.refs),
                               "set_sha256": sample_set.set_sha256, "plan_sha256": w9.PLAN_SHA256, **extra})
    cdc, banner = open_cdc(args.port, out)
    return out, cdc, banner, sample_set


def cmd_verify(args) -> int:
    out, cdc, banner, sample_set = prepare(args, "verify", {})
    try:
        require_image(banner, sample_set)
        cdc.wait(r"^READY WEEK9 ", cdc.send("STATUS"), 10)
        cdc.wait(r"^VERIFY END", cdc.send("VERIFY ALL"), 900)
        cdc.wait(r"^TDEV END", cdc.send("TDEV ALL"), 900)
        start = cdc.send("STACK")
        cdc.wait(r"^STACK main ", start, 10)
    finally:
        cdc.close()
    return checker("verify", out, args)


def cmd_session(args) -> int:
    if not 0 <= args.first < w9.CYCLES or not 1 <= args.count <= w9.CYCLES - args.first:
        raise SystemExit("--first/--count outside the 550-cycle plan")
    out, cdc, banner, sample_set = prepare(args, "session", {"gap_ms": args.gap_ms, "first": args.first,
                                                             "count": args.count})
    try:
        require_image(banner, sample_set)
        start = cdc.send(f"SESSION {args.gap_ms} {args.first} {args.count}")
        _, text = cdc.wait(r"^(SESSION BEGIN|ERROR)", start, 15)
        if text.startswith("ERROR"):
            raise SystemExit(f"device refused: {text}")
        cdc.wait(r"^SESSION END ", start, args.count * (args.gap_ms / 1000.0 + 0.6) + 120)
    finally:
        cdc.close()
    return checker("session", out, args, ["--first", str(args.first), "--count", str(args.count)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", type=Path, required=True, help="new directory")
        p.add_argument("--port", help="application CDC port (default: VID 2FE3 PID 0004)")
        p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
        p.add_argument("--refs", type=Path, required=True, help="generate_week9_refs.py directory")

    p = sub.add_parser("verify")
    common(p)
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("session")
    common(p)
    p.add_argument("--gap-ms", type=int, default=1000, help="gap between cycles (energy session: 1000)")
    p.add_argument("--first", type=int, default=0, help="first cycle of the plan")
    p.add_argument("--count", type=int, default=w9.CYCLES, help="cycles")
    p.set_defaults(func=cmd_session)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
