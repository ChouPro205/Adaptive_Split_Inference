#!/usr/bin/env python3
"""Week 8 lab driver (dongle on laptop USB): USB CDC commands + capture, then check_week8.py.

  verify  energy-usb image: STATUS, NONCE, VERIFY (100 W8-D3 samples at s=2)              (TC2)
  cycles  energy-usb image + laptop edge with the real tail (week8_edge.py, BLE):
          CONNPARAM, STATUS, PAIRS <first> <pairs>, NONCE, STACK                          (TC3)
          Laptop power: labels/logits are G2 evidence, timings are debug only.
Each run writes a NEW --out directory: cdc.log (week 6 format), session.json, check_<kind>.json and
for cycles edge/ (peer.jsonl, tail.log, summary.json). USB CDC/BLE helpers are week6_lab's,
unmodified. Run with device/host/.venv. Exit 0 = the checker PASSED.
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402
import week6_lab as w6  # noqa: E402
import week8_common as w8  # noqa: E402
import week8_edge as edge_mod  # noqa: E402

TOOLS = ("week8_lab.py", "week8_common.py", "check_week8.py", "test_week8_host.py", "week8_edge.py",
         "week8_tail_worker.py", "week7_common.py", "week6_lab.py", "week6_common.py")


def session_record(out: Path, kind: str, extra: dict) -> None:
    wc.write_new_json(out / "session.json", {
        "schema": "week8-lab-session/1",
        "kind": kind,
        "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": {n: wc.sha256_file(HERE / n) for n in TOOLS},
        "scope": "dongle on laptop USB power: correctness evidence, never energy numbers",
        **extra,
    })


def open_cdc(port, out: Path) -> tuple:
    cdc = w6.Cdc(port, out / "cdc.log")
    cdc.open()
    mark = cdc.mark()
    _, banner = cdc.wait(r"^READY WEEK8 ", 0, 20)
    return cdc, wc.kv(banner), mark


def checker(kind: str, out: Path, samples: Path, extra: list = ()) -> int:
    cmd = [sys.executable, "-B", str(HERE / "check_week8.py"), kind, "--session", str(out),
           "--samples", str(samples), "--output", str(out / f"check_{kind}.json"), *extra]
    print("+", " ".join(cmd))
    return subprocess.run(cmd).returncode


def require_image(banner: dict, variant: str, sample_set: w8.SampleSet) -> None:
    if banner.get("variant") != variant:
        raise SystemExit(f"dongle runs variant {banner.get('variant')!r}, this step needs {variant!r}")
    if banner.get("set_sha256") != sample_set.set_sha256:
        raise SystemExit(f"image set {banner.get('set_sha256')} != W8-D3 set {sample_set.set_sha256}")


def cmd_verify(args) -> int:
    sample_set = w8.load_set(args.samples)   # authenticate before touching the dongle
    out = w6.new_out(args.out)
    session_record(out, "verify", {"samples": str(args.samples), "set_sha256": sample_set.set_sha256})
    cdc, banner, _ = open_cdc(args.port, out)
    try:
        require_image(banner, "energy-usb", sample_set)
        cdc.wait(r"^VERIFY END", cdc.send("VERIFY"), 900)
        cdc.wait(r"^NONCE status=", cdc.send("NONCE"), 10)
    finally:
        cdc.close()
    return checker("verify", out, args.samples)


async def drive_cycles(cdc, peer, args) -> None:
    peer_task = asyncio.ensure_future(peer.run())
    try:
        await asyncio.wait_for(peer.ready.wait(), 90)
        await asyncio.sleep(1.0)
        if args.conn_interval:
            cdc.send(f"CONNPARAM {args.conn_interval} {args.conn_interval}")
            await asyncio.sleep(3.0)
        cdc.send("STATUS")
        await asyncio.sleep(1.0)
        start = cdc.send(f"PAIRS {args.first} {args.pairs}")
        _, text = await asyncio.to_thread(cdc.wait, r"^(PAIRS BEGIN|ERROR)", start, 15)
        if text.startswith("ERROR"):
            raise SystemExit(f"device refused: {text}")
        timeout = args.pairs * 2 * 8 + 60
        await asyncio.to_thread(cdc.wait, r"^PAIRS END ", start, timeout)
        await asyncio.to_thread(cdc.wait, r"^NONCE status=", start, 10)
        await asyncio.sleep(2.0)
    finally:
        peer.stop.set()
        await asyncio.sleep(0.2)
        if peer.client is not None:
            try:
                await peer.client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        peer_task.cancel()
        try:
            await peer_task
        except BaseException:  # noqa: BLE001
            pass


def cmd_cycles(args) -> int:
    sample_set = w8.load_set(args.samples)
    out = w6.new_out(args.out)
    session_record(out, "cycles", {"samples": str(args.samples), "set_sha256": sample_set.set_sha256,
                                   "first_pair": args.first, "pairs": args.pairs,
                                   "conn_interval_1250us": args.conn_interval,
                                   "peer": "laptop edge, real tail (W8-D7 fallback), not KV260",
                                   "key": "bench key file" if args.key_file else None})
    (out / "edge").mkdir()
    tail = edge_mod.TailClient(args.samples, out / "edge" / "tail.log")
    edge = edge_mod.LaptopEdge(sample_set, edge_mod.load_key(args.key_file), tail)
    peer = edge_mod.EdgePeer(out / "edge" / "peer.jsonl", edge, 2 * args.pairs)
    started = datetime.now(timezone.utc).isoformat()
    try:
        cdc, banner, _ = open_cdc(args.port, out)
        try:
            require_image(banner, "energy-usb", sample_set)
            asyncio.run(drive_cycles(cdc, peer, args))
        finally:
            peer.close()
            cdc.close()
    finally:
        tail.close()
    result = edge_mod.evaluate(peer.records, edge.counters, sample_set, args.first, args.pairs)
    wc.write_new_json(out / "edge" / "summary.json", edge_mod.summary(args, edge, peer, result, started))
    extra = ["--first", str(args.first), "--pairs", str(args.pairs)]
    if args.prior_reserved_through is not None:
        extra += ["--prior-reserved-through", str(args.prior_reserved_through)]
    return checker("cycles", out, args.samples, extra)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", type=Path, required=True, help="new directory")
        p.add_argument("--port", help="application CDC port (default: VID 2FE3 PID 0004)")
        p.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")

    p = sub.add_parser("verify")
    common(p)
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("cycles")
    common(p)
    p.add_argument("--first", type=int, default=0, help="first pair (sample first mod 100)")
    p.add_argument("--pairs", type=int, default=100)
    p.add_argument("--conn-interval", type=int, default=12,
                   help="CONNPARAM value in 1.25 ms units (W7-D7), 0 = leave the central's choice")
    p.add_argument("--key-file", help="32-byte bench key (P1 requests need it)")
    p.add_argument("--prior-reserved-through", type=int,
                   help="NONCE reserved_through read with the previous boot/image")
    p.set_defaults(func=cmd_cycles)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
