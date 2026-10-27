#!/usr/bin/env python3
"""Week 8 lab driver (dongle on laptop USB): USB CDC commands + capture, then check_week8.py.

  verify  energy-usb image: STATUS, NONCE, VERIFY (100 W8-D3 samples at s=2)              (TC2)
  cycles  energy-usb image + laptop edge with the real tail (week8_edge.py, BLE):
          CONNPARAM, STATUS, PAIRS <first> <pairs> (or --one <n> P1|P0), NONCE, STACK    (TC3)
          --peer external: another central (KV260, TC4/TC5) holds the link; the laptop only drives
          the console: STATUS until LINK ready=1, then the same commands. Its log is checked later:
  import-peer  the external peer's request log (JSON lines, PEER_LOG_FIELDS) -> edge/peer.jsonl
          (normalized; the raw file kept as edge/peer_raw.jsonl), edge/summary.json, then
          check_week8.py cycles. The W8-D3 sample of each request is found from its q/scale SHA-256.
          --edge-reference: labels judged against the peer's offline logits (W8-D8, KV260 INT8 tail).
          Laptop power: labels/logits are G2 evidence, timings are debug only.
Each run writes a NEW --out directory: cdc.log (week 6 format), session.json, check_<kind>.json and
for cycles edge/ (peer.jsonl, tail.log, summary.json). USB CDC/BLE helpers are week6_lab's,
unmodified. Run with device/host/.venv. Exit 0 = the checker PASSED.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import struct
import subprocess
import time
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


# Fields of one request line of an external peer log ({"ev": "request", ...}); see import-peer.
PEER_LOG_FIELDS = {
    "request_id": "uint32 of the I1 v2 header (int, or hex text)",
    "rho": "P1 | P0",
    "sequence": "P1: nonce sequence (uint64) read from the frame",
    "result": "OK when the 64 B response was sent, else an error code (no response)",
    "q_sha256": "SHA-256 hex of q (C*L int8 bytes) after unprotect",
    "scale_sha256": "SHA-256 hex of the C scales as FP16 little-endian",
    "logits": "5 FP32 as sent: '3f800000,...' (bit patterns, hex) or a list of 5 numbers",
    "label": "argmax of the logits (first maximum); optional",
    "len": "request frame length in bytes after reassembly; optional",
    "t_rx_ms": "time the complete request was received (ms, any monotonic clock); optional",
    "t_tx_done_ms": "time the response was sent (ms, same clock); optional",
}


def command_for(args) -> tuple:
    """(console command, end-of-run regex) of the cycles step."""
    if args.one:
        return f"ONE {args.one[0]} {args.one[1]}", r"^ONE END "
    return f"PAIRS {args.first} {args.pairs}", r"^PAIRS END "


def run_command(cdc, args) -> None:
    command, end = command_for(args)
    start = cdc.send(command)
    _, text = cdc.wait(r"^(ONE BEGIN|PAIRS BEGIN|ERROR)", start, 15)
    if text.startswith("ERROR"):
        raise SystemExit(f"device refused: {text}")
    cdc.wait(end, start, (1 if args.one else args.pairs) * 2 * 8 + 60)


def drive_external(cdc, args) -> None:
    """The external central connects and subscribes on its own; wait for LINK ready=1."""
    deadline = time.monotonic() + args.connect_timeout_s
    while True:
        _, text = cdc.wait(r"^LINK connected=", cdc.send("STATUS"), 10)
        if wc.kv(text).get("ready") == "1":
            break
        if time.monotonic() > deadline:
            raise SystemExit(f"no ready link after {args.connect_timeout_s} s (external peer connected "
                             "and subscribed to TX notifications?)")
        time.sleep(2.0)
    if args.conn_interval:
        cdc.send(f"CONNPARAM {args.conn_interval} {args.conn_interval}")
        time.sleep(3.0)
    cdc.wait(r"^LINK connected=", cdc.send("STATUS"), 10)
    run_command(cdc, args)
    cdc.wait(r"^NONCE status=", cdc.send("NONCE"), 10)
    cdc.wait(r"^LINK connected=", cdc.send("STATUS"), 10)


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
        await asyncio.to_thread(run_command, cdc, args)
        await asyncio.to_thread(cdc.wait, r"^NONCE status=", cdc.send("NONCE"), 10)
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


def checker_args(record: dict) -> list:
    extra = ["--first", str(record["first_pair"]), "--pairs", str(record["pairs"])]
    if record.get("one"):
        extra += ["--one", str(record["one"][0]), record["one"][1]]
    if record.get("prior_reserved_through") is not None:
        extra += ["--prior-reserved-through", str(record["prior_reserved_through"])]
    return extra


def cmd_cycles(args) -> int:
    sample_set = w8.load_set(args.samples)
    if args.one:
        args.one = (int(args.one[0]), args.one[1])
        if not (0 <= args.one[0] < w8.SAMPLE_COUNT and args.one[1] in ("P1", "P0")):
            raise SystemExit("--one <n 0..99> P1|P0")
    external = args.peer == "external"
    out = w6.new_out(args.out)
    record = {"samples": str(args.samples), "set_sha256": sample_set.set_sha256,
              "first_pair": args.first, "pairs": args.pairs, "one": list(args.one) if args.one else None,
              "conn_interval_1250us": args.conn_interval,
              "peer": f"external: {args.peer_name}" if external
              else "laptop edge, real tail (W8-D7 fallback), not KV260",
              "prior_reserved_through": args.prior_reserved_through,
              "key": "bench key file" if args.key_file else None}
    session_record(out, "cycles", record)
    if external:
        cdc, banner, _ = open_cdc(args.port, out)
        try:
            require_image(banner, "energy-usb", sample_set)
            drive_external(cdc, args)
        finally:
            cdc.close()
        print(f"console part done -> {out}. Get the {args.peer_name} request log, then:\n"
              f"  week8_lab.py import-peer --out {out} --peer-log <file>")
        return 0
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
    result = edge_mod.evaluate(peer.records, edge.counters, sample_set, args.first, args.pairs, args.one)
    wc.write_new_json(out / "edge" / "summary.json", edge_mod.summary(args, edge, peer, result, started))
    return checker("cycles", out, args.samples, checker_args(record))


def logits_bits(value) -> str:
    """Logits of a peer log -> the firmware's text: 5 FP32 bit patterns, 8 lowercase hex digits each."""
    if isinstance(value, str):
        words = [w.strip().lower().removeprefix("0x") for w in value.split(",")]
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        words = [w.strip().lower().removeprefix("0x") for w in value]
    elif isinstance(value, list):
        words = [f"{struct.unpack('<I', struct.pack('<f', float(v)))[0]:08x}" for v in value]
    else:
        raise ValueError(f"logits {value!r}")
    if len(words) != 5 or not all(re.fullmatch(r"[0-9a-f]{8}", w) for w in words):
        raise ValueError(f"logits {value!r}: need 5 FP32 values")
    return ",".join(words)


def normalize_peer_log(lines: list, sample_set: w8.SampleSet) -> tuple:
    """Request lines of an external peer log -> (records in week8_edge form, counters)."""
    by_hash = {(s.q_sha256, s.scale_sha256): n for n, s in enumerate(sample_set.samples)}
    records, counters = [], {"response_sent": 0, "unknown_sample": 0, "not_ok": 0}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("ev") != "request":
            continue
        rid = event["request_id"]
        r = {"request_id": int(rid, 16) if isinstance(rid, str) else int(rid), "rho": event["rho"],
             "result": event["result"], "line": number}
        if r["rho"] not in ("P1", "P0"):
            raise ValueError(f"line {number}: rho {r['rho']!r}")
        for key in ("sequence", "t_rx_ms", "t_tx_done_ms", "len", "att_mtu", "tail_us"):
            if key in event:
                r[key] = event[key]
        if r["result"] == "OK":
            r["q_sha256"], r["scale_sha256"] = event["q_sha256"].lower(), event["scale_sha256"].lower()
            r["logits"] = logits_bits(event["logits"])
            r["label"] = w8.label(w8.logits_from_hex(r["logits"]))
            if "label" in event and int(event["label"]) != r["label"]:
                raise ValueError(f"line {number}: label {event['label']} is not argmax of the logits")
            r["sample"] = by_hash.get((r["q_sha256"], r["scale_sha256"]))
            counters["response_sent"] += 1
            if r["sample"] is None:
                counters["unknown_sample"] += 1
        else:
            counters["not_ok"] += 1
        records.append(r)
    return records, counters


def cmd_import_peer(args) -> int:
    out = Path(args.out)
    record = json.loads((out / "session.json").read_text(encoding="utf-8"))
    if record.get("schema") != "week8-lab-session/1" or not str(record.get("peer", "")).startswith("external"):
        raise SystemExit(f"{out} is not a week8_lab.py cycles --peer external session")
    sample_set = w8.load_set(Path(record["samples"]))
    edge = out / "edge"
    edge.mkdir(exist_ok=False)
    raw = edge / "peer_raw.jsonl"
    shutil.copyfile(args.peer_log, raw)
    records, counters = normalize_peer_log(raw.read_text(encoding="utf-8").splitlines(), sample_set)
    with open(edge / "peer.jsonl", "x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps({"ev": "request", **r}) + "\n")
    one = tuple(record["one"]) if record.get("one") else None
    edge_ref = w8.load_edge_reference(args.edge_reference, sample_set) if args.edge_reference else None
    result = edge_mod.evaluate(records, counters, sample_set, record["first_pair"], record["pairs"], one,
                               edge_ref.labels if edge_ref else None)
    wc.write_new_json(edge / "summary.json", {
        "schema": "week8-external-peer/1", "peer": record["peer"].removeprefix("external: "),
        "source_log": str(args.peer_log), "source_log_sha256": wc.sha256_file(raw),
        "imported_utc": datetime.now(timezone.utc).isoformat(), "counters": counters,
        "set_sha256": sample_set.set_sha256, "field_spec": PEER_LOG_FIELDS,
        "label_reference": {"path": edge_ref.path, "sha256": edge_ref.sha256} if edge_ref else "W8-D4", **result,
        "tool_sha256": {n: wc.sha256_file(HERE / n) for n in ("week8_lab.py", "week8_edge.py", "week8_common.py")}})
    print(f"peer log: {len(records)} requests, {counters}")
    extra = checker_args(record) + (["--edge-reference", str(args.edge_reference)] if edge_ref else [])
    return checker("cycles", out, Path(record["samples"]), extra)


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
    p.add_argument("--one", nargs=2, metavar=("N", "RHO"), help="ONE <n> P1|P0 instead of PAIRS")
    p.add_argument("--peer", choices=["laptop", "external"], default="laptop")
    p.add_argument("--peer-name", default="KV260", help="--peer external: who the central is")
    p.add_argument("--connect-timeout-s", type=float, default=600.0,
                   help="--peer external: wait this long for LINK ready=1")
    p.set_defaults(func=cmd_cycles)
    p = sub.add_parser("import-peer")
    p.add_argument("--out", type=Path, required=True, help="the cycles --peer external directory")
    p.add_argument("--peer-log", type=Path, required=True, help="request log of the external peer")
    p.add_argument("--edge-reference", type=Path,
                   help="the peer's offline logits of the 100 samples (W8-D8: KV260 predictions.jsonl)")
    p.set_defaults(func=cmd_import_peer)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
