#!/usr/bin/env python3
"""Week 7 laptop "stub edge" (decision W7-D6): BLE central that answers every measurement-cycle
request of the dongle with a valid 64 B I1 v2 RESPONSE.

BLE handling (scan, connect, notify, MTU settle, fragments, reassembly) is week6_lab.Peer,
reused unmodified by subclassing; only the request handler differs. Each request goes through
week7_common.StubEdge: CRC + I1 v2 header (reference parser), expected split, P1 sequence
strictly increasing, q recovered (P1: unprotect with the bench key) and matched byte for byte to
the SV3 golden tensor of one of the 20 samples, then the RESPONSE with that sample's reference
logits. Invalid requests are logged and not answered (the dongle times out; never a fake OK).

Start it BEFORE the dongle is powered (it keeps scanning). Ends after --expect requests have
been answered (+ --linger-s), on --max-s, or Ctrl+C. Writes a NEW --out directory:
peer.jsonl (one JSON line per event/request), summary.json (counters, checks, tool hashes).
Exit 0 = every expected request was valid and answered, in order.

  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week7_stub_edge.py --out D:\\HUST\\ASI_week7\\session-...\\stub ^
      --split 2 --expect-p1 50 --expect-p0 50 --key-file D:\\HUST\\ASI_week6\\secrets\\bench_key_65537.bin
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402
import week6_lab  # noqa: E402
import week7_common as w7  # noqa: E402
import i1_ble_binding as ble  # noqa: E402


class StubPeer(week6_lab.Peer):
    def __init__(self, log_path: Path, edge: w7.StubEdge, expect: int):
        super().__init__("normal", log_path, expect_mtu=247)
        self.edge = edge
        self.expect = expect
        self.records = []
        self.done = asyncio.Event()

    async def handle(self, stream: int, frame: bytes) -> None:
        t = week6_lab.now_ms()
        self.counts["rx_frames"] += 1
        if stream != ble.STREAM_I1:
            self.event("drop_stream", stream=stream, length=len(frame))
            return
        response, record = self.edge.handle(frame)
        record["t_rx_ms"] = t
        record["att_mtu"] = self.client.mtu_size if self.client else None
        if response is not None:
            await self.send_frame(response, ble.STREAM_I1)
            record["t_tx_done_ms"] = week6_lab.now_ms()
        self.records.append(record)
        self.event("request", index=len(self.records) - 1, **record)
        if self.edge.counters["received"] >= self.expect:
            self.done.set()


def load_key(path: str | None) -> bytes | None:
    if not path:
        return None
    key = Path(path).read_bytes()
    if len(key) != 32:
        raise SystemExit("key file must hold exactly 32 raw bytes")
    return key


def evaluate(records: list, counters: dict, expect_p1: int, expect_p0: int) -> dict:
    """P1 requests first, then P0, samples rotating 0..19 (firmware cycle i uses sample i % 20)."""
    expected = ["P1"] * expect_p1 + ["P0"] * expect_p0
    rho = [r.get("rho") for r in records]
    samples = [r.get("sample") for r in records]
    request_ids = [r.get("request_id") for r in records]
    checks = {
        "count": len(records) == len(expected),
        "all_ok": bool(records) and all(r.get("result") == "OK" for r in records),
        "rho_order": rho == expected,
        "samples_rotate": samples == [i % 20 for i in range(len(records))],
        "request_id_increasing": all(b == (a % 0xFFFFFFFF) + 1
                                     for a, b in zip(request_ids, request_ids[1:])
                                     if a is not None and b is not None),
        "responses_sent": counters["response_sent"] == len(expected),
    }
    gaps = [b["t_rx_ms"] - a["t_rx_ms"] for a, b in zip(records, records[1:])]
    sequences = [r["sequence"] for r in records if "sequence" in r]
    return {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL",
            "request_lengths": sorted({r["len"] for r in records}),
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
            "inter_request_ms": {"min": min(gaps), "max": max(gaps)} if gaps else None}


async def serve(args, out: Path) -> int:
    edge = w7.StubEdge(args.split, load_key(args.key_file))
    expect = args.expect_p1 + args.expect_p0
    peer = StubPeer(out / "peer.jsonl", edge, expect)
    started = datetime.now(timezone.utc).isoformat()
    runner = asyncio.ensure_future(peer.run())
    t0 = time.monotonic()
    print(f"stub edge: scanning for {wc.NAME}; expecting {args.expect_p1} P1 + {args.expect_p0} P0 "
          f"requests at s={args.split}")
    try:
        while not peer.done.is_set() and time.monotonic() - t0 < args.max_s:
            await asyncio.sleep(0.5)
        if peer.done.is_set():
            await asyncio.sleep(args.linger_s)
    finally:
        peer.stop.set()
        await asyncio.sleep(0.5)
        runner.cancel()
        peer.close()
    result = evaluate(peer.records, edge.counters, args.expect_p1, args.expect_p0)
    summary = {
        "schema": "week7-stub-edge/1",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv,
        "split": args.split,
        "expect_p1": args.expect_p1,
        "expect_p0": args.expect_p0,
        "key": "bench key file given" if args.key_file else "none (P1 requests are not answered)",
        "counters": edge.counters,
        "peer_counts": peer.counts,
        "reassembler": peer.reasm.counters,
        **result,
        "tool_sha256": {name: w7.sha256_file(HERE / name) for name in (
            "week7_stub_edge.py", "week7_common.py", "week6_lab.py", "week6_common.py")},
        "golden": {"quantization20_manifest_sha256": w7.sha256_file(w7.QUANT20 / "manifest.json")},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"counters {edge.counters}")
    print(f"RESULT: {result['status']} -> {out}")
    return 0 if result["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="new directory")
    parser.add_argument("--split", type=int, default=2)
    parser.add_argument("--expect-p1", type=int, default=50)
    parser.add_argument("--expect-p0", type=int, default=50)
    parser.add_argument("--key-file", help="32-byte bench key (never printed or logged)")
    parser.add_argument("--max-s", type=float, default=900.0)
    parser.add_argument("--linger-s", type=float, default=3.0)
    args = parser.parse_args()
    if w7.sha256_file(w7.QUANT20 / "manifest.json") != w7.QUANT20_MANIFEST_SHA256:
        raise SystemExit("quantization20 manifest differs from the week 5 anchor")
    out = week6_lab.new_out(args.out)
    return asyncio.run(serve(args, out))


if __name__ == "__main__":
    sys.exit(main())
