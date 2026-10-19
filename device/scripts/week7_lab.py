#!/usr/bin/env python3
"""Week 7 lab driver (dongle on laptop USB): USB CDC commands + capture, then check_week7.py.

  bench   bench image:      STATUS, CMP ALL, CMP MIX, BENCH ALL (or --bench-splits), STACK  (TC7)
  verify  energy-usb image: STATUS, NONCE, VERIFY <s>|ALL                                    (TC4)
  dryrun  energy-usb image + stub edge (BLE): CONNPARAM, CYCLES <p1> <p0>, NONCE, STACK     (TC4/TC5
          dry run before the PPK2 session; laptop power, so timings are debug evidence only)
Each run writes a NEW --out directory: cdc.log (week 6 format), session.json, check_*.json and
for dryrun stub/ (peer.jsonl, summary.json). USB CDC/BLE helpers are week6_lab's, unmodified.
Run with device/host/.venv. Exit 0 = the checker PASSED.
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
import week7_common as w7  # noqa: E402
import week7_stub_edge as stub  # noqa: E402

TOOLS = ("week7_lab.py", "week7_common.py", "week7_stub_edge.py", "check_week7.py",
         "test_week7_host.py", "week6_lab.py", "week6_common.py")


def session_record(out: Path, kind: str, extra: dict) -> None:
    wc.write_new_json(out / "session.json", {
        "schema": "week7-lab-session/1",
        "kind": kind,
        "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": {n: wc.sha256_file(HERE / n) for n in TOOLS},
        "scope": "dongle on laptop USB power: correctness/timing evidence, never energy numbers",
        **extra,
    })


def open_cdc(port, out: Path) -> tuple:
    cdc = w6.Cdc(port, out / "cdc.log")
    cdc.open()
    mark = cdc.mark()
    _, banner = cdc.wait(r"^READY WEEK7 ", 0, 20)
    return cdc, wc.kv(banner), mark


def checker(kind: str, out: Path, extra: list) -> int:
    cmd = [sys.executable, "-B", str(HERE / "check_week7.py"), kind, "--session", str(out),
           "--output", str(out / f"check_{kind}.json")] + extra
    print("+", " ".join(cmd))
    return subprocess.run(cmd).returncode


def require_variant(banner: dict, variant: str) -> None:
    if banner.get("variant") != variant:
        raise SystemExit(f"dongle runs variant {banner.get('variant')!r}, this step needs {variant!r}")


def cmd_bench(args) -> int:
    out = w6.new_out(args.out)
    session_record(out, "bench", {"bench_splits": args.bench_splits})
    hashes = out / "host_head_hashes.csv"
    subprocess.run([sys.executable, "-B", str(HERE / "test_week7_host.py"), "--write-head-hashes",
                    str(hashes)], check=True)
    cdc, banner, _ = open_cdc(args.port, out)
    try:
        require_variant(banner, "bench")
        cdc.wait(r"^CMP END ", cdc.send("CMP ALL"), 900)
        cdc.wait(r"^MIX END ", cdc.send("CMP MIX"), 120)
        if args.bench_splits == "ALL":
            cdc.wait(r"^BENCH END", cdc.send("BENCH ALL"), 5400)
        else:
            for split in args.bench_splits.split(","):
                for kernel in ("W4", "FAST"):
                    cdc.wait(r"^BENCH END", cdc.send(f"BENCH {kernel} {int(split)}"), 900)
        cdc.wait(r"^STACK ", cdc.send("STACK"), 10)
    finally:
        cdc.close()
    return checker("bench", out, ["--host-hashes", str(hashes)])


def cmd_verify(args) -> int:
    out = w6.new_out(args.out)
    session_record(out, "verify", {"split": args.split})
    cdc, banner, _ = open_cdc(args.port, out)
    try:
        require_variant(banner, "energy-usb")
        cdc.wait(r"^VERIFY END", cdc.send(f"VERIFY {args.split}"), 1200)
        cdc.wait(r"^NONCE status=", cdc.send("NONCE"), 10)
    finally:
        cdc.close()
    return checker("verify", out, [])


async def drive_dryrun(cdc, peer, args) -> None:
    peer_task = asyncio.ensure_future(peer.run())
    try:
        await asyncio.wait_for(peer.ready.wait(), 90)
        await asyncio.sleep(1.0)
        if args.conn_interval:
            cdc.send(f"CONNPARAM {args.conn_interval} {args.conn_interval}")
            await asyncio.sleep(3.0)
        cdc.send("STATUS")
        await asyncio.sleep(1.0)
        start = cdc.send(f"CYCLES {args.p1} {args.p0}")
        _, text = await asyncio.to_thread(cdc.wait, r"^(CYCLES BEGIN|ERROR)", start, 15)
        if text.startswith("ERROR"):
            raise SystemExit(f"device refused: {text}")
        timeout = (args.p1 + args.p0) * 10 + 60
        await asyncio.to_thread(cdc.wait, r"^CYCLES END ", start, timeout)
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


def cmd_dryrun(args) -> int:
    out = w6.new_out(args.out)
    session_record(out, "dryrun", {"p1": args.p1, "p0": args.p0, "split": args.split,
                                   "conn_interval_1250us": args.conn_interval,
                                   "key": "bench key file" if args.key_file else None})
    (out / "stub").mkdir()
    edge = w7.StubEdge(args.split, stub.load_key(args.key_file))
    peer = stub.StubPeer(out / "stub" / "peer.jsonl", edge, args.p1 + args.p0)
    cdc, banner, _ = open_cdc(args.port, out)
    try:
        require_variant(banner, "energy-usb")
        if int(banner.get("split", -1)) != args.split:
            raise SystemExit(f"image split {banner.get('split')} != --split {args.split}")
        asyncio.run(drive_dryrun(cdc, peer, args))
    finally:
        peer.close()
        cdc.close()
    result = stub.evaluate(peer.records, edge.counters, args.p1, args.p0)
    wc.write_new_json(out / "stub" / "summary.json", {
        "schema": "week7-stub-edge/1", "counters": edge.counters, "peer_counts": peer.counts,
        "reassembler": peer.reasm.counters, **result})
    return checker("dryrun", out, ["--p1", str(args.p1), "--p0", str(args.p0),
                                   "--split", str(args.split)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", type=Path, required=True, help="new directory")
        p.add_argument("--port", help="application CDC port (default: VID 2FE3 PID 0004)")

    p = sub.add_parser("bench")
    common(p)
    p.add_argument("--bench-splits", default="ALL", help="ALL or e.g. 0,2,10")
    p.set_defaults(func=cmd_bench)
    p = sub.add_parser("verify")
    common(p)
    p.add_argument("--split", default="ALL", help="ALL or one split 0..10")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("dryrun")
    common(p)
    p.add_argument("--p1", type=int, default=20)
    p.add_argument("--p0", type=int, default=20)
    p.add_argument("--split", type=int, default=2)
    p.add_argument("--conn-interval", type=int, default=12,
                   help="CONNPARAM value in 1.25 ms units (W7-D7), 0 = leave the central's choice")
    p.add_argument("--key-file", help="32-byte bench key (P1 requests need it)")
    p.set_defaults(func=cmd_dryrun)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
