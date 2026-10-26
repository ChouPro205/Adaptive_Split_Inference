#!/usr/bin/env python3
"""Week 8 laptop edge with the real tail (W8-D7 fallback peer for G2, TC3): BLE central that
answers every G2 request of the dongle with the logits of the frozen tail computed from the q it
received.

BLE handling (scan, connect, notify, MTU settle, fragments, reassembly) is week6_lab.Peer, reused
unmodified by subclassing (as week7_stub_edge.py). Each request: CRC + I1 v2 header (reference
parser), split 2, P1 sequence strictly increasing and q recovered with the bench key (unprotect),
scales narrowed to FP16 (must widen back exactly), then week8_tail_worker.py (ml\\.venv, torch)
dequantizes and runs the tail; the RESPONSE carries those logits. Nothing is looked up: the W8-D3
set is used only afterwards, to record which sample the q/scale bytes are (evaluation). Invalid
requests are logged and not answered (the dongle times out; never a fake OK).

Standalone (e.g. the energy image, no CDC): start it BEFORE the dongle is powered; it ends after
--pairs pairs (2 requests each) have been handled (+ --linger-s), on --max-s, or Ctrl+C.
week8_lab.py cycles drives it together with the CDC console. Writes a NEW --out directory:
peer.jsonl (one JSON line per event/request), tail.log (worker stderr), summary.json.

  device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\week8_edge.py --out <new dir> ^
      --samples D:\\HUST\\ASI_week8\\samples-20261023-c --pairs 100 ^
      --key-file D:\\HUST\\ASI_week6\\secrets\\bench_key_65537.bin
"""
from __future__ import annotations

import argparse
import asyncio
import json
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402
import week6_lab  # noqa: E402
import week7_common as w7  # noqa: E402
import week8_common as w8  # noqa: E402
import i1_ble_binding as ble  # noqa: E402

ML_PYTHON = w8.ROOT / "ml" / ".venv" / "Scripts" / "python.exe"
TOOLS = ("week8_edge.py", "week8_tail_worker.py", "week8_common.py", "week7_common.py", "week6_lab.py",
         "week6_common.py")


class TailClient:
    """week8_tail_worker.py in ml/.venv, JSON lines over pipes (one request at a time)."""

    def __init__(self, samples: Path, stderr_path: Path, python: Path = ML_PYTHON):
        self.stderr = open(stderr_path, "a", encoding="utf-8")
        self.proc = subprocess.Popen([str(python), "-B", str(HERE / "week8_tail_worker.py"), "--samples",
                                      str(samples)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, text=True, encoding="utf-8", bufsize=1)
        line = self.proc.stdout.readline()
        self.info = json.loads(line) if line else {"ready": False}
        if not self.info.get("ready"):
            self.close()
            raise SystemExit(f"tail worker not ready: {self.info}")
        self.next_id = 0

    def logits(self, q: bytes, scale_le: bytes, channels: int, length: int) -> dict:
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"id": self.next_id, "C": channels, "L": length, "q": q.hex(),
                                          "scale_f16": scale_le.hex()}) + "\n")
        self.proc.stdin.flush()
        reply = json.loads(self.proc.stdout.readline())
        if reply.get("id") != self.next_id:
            raise RuntimeError("tail worker reply out of order")
        return reply

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.stderr.close()


class LaptopEdge:
    def __init__(self, sample_set: w8.SampleSet, key: bytes | None, tail: TailClient):
        self.set = sample_set
        self.key = key
        self.tail = tail
        self.last_sequence = 0
        self.by_bytes = {(s.q, s.scale_le): s.index for s in sample_set.samples}
        self.counters = {name: 0 for name in (
            "received", "crc_fail", "drop", "reject", "wrong_split", "sequence_not_increasing", "no_key",
            "scale_not_fp16", "tail_error", "p1", "p0", "response_sent", "unknown_sample")}

    def handle(self, frame: bytes) -> tuple[bytes | None, dict]:
        self.counters["received"] += 1
        record = {"len": len(frame), "sha256": w8.sha256_hex(frame)}
        if len(frame) >= 4 and struct.unpack_from("<I", frame, len(frame) - 4)[0] != w8.ref.crc32(frame[:-4]):
            return self._fail(record, "CRC_FAIL", "crc_fail")
        try:
            request = w8.ref.parse_request(frame, w7.registry_profile())
        except w8.ref.Drop as error:
            return self._fail(record, f"DROP_{error}", "drop")
        except w8.ref.Reject as error:
            return self._fail(record, f"REJECT_{error.status}", "reject")
        record.update(request_id=request.request_id, rho="P1" if request.transformed else "P0")
        if request.split.split_point != w8.SPLIT:
            return self._fail(record, "WRONG_SPLIT", "wrong_split")
        q = request.payload
        if request.transformed:
            _, sequence = struct.unpack("<IQ", request.nonce)
            record["sequence"] = sequence
            if sequence <= self.last_sequence:
                return self._fail(record, "SEQUENCE_NOT_INCREASING", "sequence_not_increasing")
            self.last_sequence = sequence
            if self.key is None:
                return self._fail(record, "NO_KEY", "no_key")
            try:
                q = w8.ref.recover_q(request, {w7.KEY_ID: self.key})
            except w8.ref.Reject as error:
                return self._fail(record, f"REJECT_{error.status}", "reject")
        scales = np.array(list(request.scales), np.float32)
        scale_le = scales.astype("<f2").tobytes()
        if np.frombuffer(scale_le, "<f2").astype(np.float32).tobytes() != scales.tobytes():
            return self._fail(record, "SCALE_NOT_FP16", "scale_not_fp16")
        channels, length = len(scales), len(q) // max(len(scales), 1)
        record.update(q_sha256=w8.sha256_hex(q), scale_sha256=w8.sha256_hex(scale_le))
        # Evaluation only (which W8-D3 sample these bytes are); the answer never uses it.
        record["sample"] = self.by_bytes.get((q, scale_le))
        if record["sample"] is None:
            self.counters["unknown_sample"] += 1
        reply = self.tail.logits(q, scale_le, channels, length)
        if "error" in reply:
            record["tail_error"] = reply["error"]
            return self._fail(record, "TAIL_ERROR", "tail_error")
        logits = w8.logits_from_hex(",".join(reply["logits_bits"]))
        record.update(logits=",".join(reply["logits_bits"]), label=w8.label(logits), tail_us=reply["tail_us"])
        response = w8.ref.encode_response(request.request_id, list(logits))
        assert len(response) == w7.RESPONSE_BYTES
        self.counters["p1" if request.transformed else "p0"] += 1
        self.counters["response_sent"] += 1
        record["result"] = "OK"
        return response, record

    def _fail(self, record: dict, result: str, counter: str):
        self.counters[counter] += 1
        record["result"] = result
        return None, record


class EdgePeer(week6_lab.Peer):
    def __init__(self, log_path: Path, edge: LaptopEdge, expect: int):
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
        response, record = await asyncio.to_thread(self.edge.handle, frame)
        record["t_rx_ms"] = t
        record["att_mtu"] = self.client.mtu_size if self.client else None
        if response is not None:
            await self.send_frame(response, ble.STREAM_I1)
            record["t_tx_done_ms"] = week6_lab.now_ms()
        self.records.append(record)
        self.event("request", index=len(self.records) - 1, **record)
        if self.edge.counters["received"] >= self.expect:
            self.done.set()


def evaluate(records: list, counters: dict, sample_set: w8.SampleSet, first: int, pairs: int,
             one: tuple | None = None) -> dict:
    """Requests in the W8-D1 order of PAIRS <first> <pairs> (or ONE <n> <rho>); labels against W8-D4."""
    plan = w8.one_plan(*one) if one else w8.plan(first, pairs)
    want = {rho: sum(1 for p in plan if p[3] == rho) for rho in ("P1", "P0")}
    request_ids = [r.get("request_id") for r in records]
    labels_ok = {rho: sum(1 for r in records if r.get("rho") == rho and r.get("sample") is not None
                          and r.get("label") == sample_set.samples[r["sample"]].label_ref) for rho in ("P1", "P0")}
    checks = {
        "count": len(records) == len(plan),
        "all_ok": bool(records) and all(r.get("result") == "OK" for r in records),
        "rho_order": [r.get("rho") for r in records] == [p[3] for p in plan],
        "samples_in_plan_order": [r.get("sample") for r in records] == [p[2] for p in plan],
        "request_id_increasing": all(b == (a % 0xFFFFFFFF) + 1 for a, b in zip(request_ids, request_ids[1:])
                                     if a is not None and b is not None),
        "responses_sent": counters["response_sent"] == len(plan),
        "labels_equal_reference_p1": labels_ok["P1"] == want["P1"],
        "labels_equal_reference_p0": labels_ok["P0"] == want["P0"],
    }
    gaps = [b["t_rx_ms"] - a["t_rx_ms"] for a, b in zip(records, records[1:])]
    tail_us = [r["tail_us"] for r in records if "tail_us" in r]
    sequences = [r["sequence"] for r in records if "sequence" in r]
    return {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL",
            "labels_equal_reference": labels_ok,
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
            "request_lengths": sorted({r["len"] for r in records if "len" in r}),
            "tail_us": {"min": min(tail_us), "max": max(tail_us)} if tail_us else None,
            "inter_request_ms": {"min": min(gaps), "max": max(gaps)} if gaps else None}


def load_key(path: str | None) -> bytes | None:
    if not path:
        return None
    key = Path(path).read_bytes()
    if len(key) != 32:
        raise SystemExit("key file must hold exactly 32 raw bytes")
    return key


def summary(args, edge: LaptopEdge, peer: EdgePeer, result: dict, started: str) -> dict:
    return {
        "schema": "week8-laptop-edge/1",
        "peer": "laptop (W8-D7 fallback): real tail on CPU, not KV260",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv,
        "first_pair": args.first, "pairs": args.pairs,
        "key": "bench key file given" if args.key_file else "none (P1 requests are not answered)",
        "tail_worker": edge.tail.info,
        "set_sha256": edge.set.set_sha256,
        "counters": edge.counters, "peer_counts": peer.counts, "reassembler": peer.reasm.counters,
        **result,
        "tool_sha256": {name: wc.sha256_file(HERE / name) for name in TOOLS},
    }


async def serve(args, out: Path) -> int:
    sample_set = w8.load_set(args.samples)
    tail = TailClient(args.samples, out / "tail.log")
    edge = LaptopEdge(sample_set, load_key(args.key_file), tail)
    peer = EdgePeer(out / "peer.jsonl", edge, 2 * args.pairs)
    started = datetime.now(timezone.utc).isoformat()
    runner = asyncio.ensure_future(peer.run())
    t0 = time.monotonic()
    print(f"laptop edge: tail ready (self-test 100/100), scanning for {wc.NAME}; expecting {args.pairs} pairs")
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
        tail.close()
    result = evaluate(peer.records, edge.counters, sample_set, args.first, args.pairs)
    wc.write_new_json(out / "summary.json", summary(args, edge, peer, result, started))
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {result['status']} -> {out}")
    return 0 if result["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="new directory")
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--pairs", type=int, default=100)
    parser.add_argument("--key-file", help="32-byte bench key (never printed or logged)")
    parser.add_argument("--max-s", type=float, default=1800.0)
    parser.add_argument("--linger-s", type=float, default=3.0)
    args = parser.parse_args()
    out = week6_lab.new_out(args.out)
    return asyncio.run(serve(args, out))


if __name__ == "__main__":
    sys.exit(main())
