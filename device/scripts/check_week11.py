#!/usr/bin/env python3
"""Offline checks of week 11 link-usb runs recorded by week11_lab.py (cdc.log), TC4.

  verify   VERIFY: one VS0C line per W8-D3 sample 0..99 whose Rice body, FP16 scale and k equal the normative
           contracts/s0c_v1_ref/s0c_v1_ref.py on the same input; banner and VERIFY END: set SHA-256, the
           session's plan SHA-256 and the device's own plan digest (plan_ok=1), S0C-V1.
  session  SESSION <first> <count> against the KV260 echo service: one OP line per entry in plan order with
           (op, state, a, b) = plan, every op OK, every STATE/RECONNECT granted (interval, latency, timeout,
           PHY both ways, TX data length, TX power = the state table), echo lengths, S0C body/k = refs; DWT
           times per (state, op, a, b) are reported (laptop power: debug only, never energy numbers).
Exit 0 = PASS. Writes a JSON report to a new --output path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week11_link as wl  # noqa: E402
import week6_common as wc  # noqa: E402

SET_SHA256 = "7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=["verify", "session"])
    parser.add_argument("--session-dir", type=Path, required=True, help="week11_lab.py output (cdc.log)")
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--plan", type=Path, required=True, help="generate_week11_plan.py directory")
    parser.add_argument("--session", type=int, choices=[0, 1], required=True, help="plan session of the image")
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--count", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    plans = wl.load_plan(args.plan)
    rows = plans[args.session]
    digest = wl.w11.sha256_hex(wl.w11.plan_bytes(rows))
    refs = wl.s0c_refs(args.samples)
    capture = wc.read_capture(args.session_dir / "cdc.log")
    if args.kind == "verify":
        checks, details = wl.check_verify(capture, refs, args.session, digest, SET_SHA256)
    else:
        count = args.count if args.count is not None else len(rows) - args.first
        checks, details = wl.check_session(capture, rows, args.first, count, refs)
        checks.update(wl.banner_checks(wl.banner_of(capture), args.session, digest, SET_SHA256))
    status = "PASS" if all(checks.values()) else "FAIL"
    report = {"schema": f"week11-check-{args.kind}/1", "status": status, "session": args.session,
              "plan_sha256": digest, "checks": checks, "details": details,
              "scope": "link-usb on laptop USB power: correctness evidence, never energy numbers"}
    wc.write_new_json(args.output, report)
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {status} ({args.kind}, session {args.session})")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
