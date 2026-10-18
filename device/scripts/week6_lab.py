#!/usr/bin/env python3
"""Week 6 lab driver on the laptop: USB CDC control of the dongle + BLE central peer.

The laptop is the BLE central/echo peer of I1 BLE binding v1 (same GATT, fragments and rules
as KV260; contracts/i1_ble_binding_v1.md §1). Fragmenting/reassembly reuse the reference
contracts/i1v2_ref/i1_ble_binding.py. USB CDC only sends commands and captures the log.

Subcommands (each writes a NEW --out directory: cdc.log, peer.jsonl, session.json):
  selftest      SELFTEST ENC / P1 / QUANT + STATUS + STACK      (criteria 1, 2, 8)
  provision     bench key over CDC in provisioning mode; key never logged (nonce §4)
  nonce-reboot  automatic soft resets inside the nonce stress loop (criterion 7, D1)
  nonce-unplug  operator unplugs/replugs USB during the stress loop (criterion 7, D1)
  nonce-hooks   storage-layer fault tests: write failure, bad read-back, damaged records (D2)
  sentinel      write/read the DFU sentinel record (nonce §8 item 6)
  loopback      RUN <count> <pattern> with the peer echoing/responding  (criteria 3-5, 8)
  negative      every scenario of week6_common.NEGATIVE_SCENARIOS, one run each (criterion 6)
Run with device/host/.venv (bleak 3.0.2, pyserial 3.5). Exit 0 = the checker PASSED.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import struct
import subprocess
import sys
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import serial
from serial.tools import list_ports

sys.path.insert(0, str(Path(__file__).resolve().parent))
import week6_common as wc  # noqa: E402
import i1_ble_binding as ble  # noqa: E402
import i1v2_reference as ref  # noqa: E402

HERE = Path(__file__).resolve().parent
FRAME_GAP_S = 0.3  # between a bogus whole frame and the real one (avoid rx_busy, rule 8)


def now_ms() -> int:
    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------- USB CDC

def find_app_port(timeout_s: float = 20.0, wanted: str | None = None) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for p in list_ports.comports():
            if wanted and p.device.upper() == wanted.upper():
                return p.device
            if not wanted and p.vid == wc.APP_VID and p.pid == wc.APP_PID:
                return p.device
        time.sleep(0.25)
    raise SystemExit(f"application CDC port not found (VID {wc.APP_VID:04X} PID {wc.APP_PID:04X})")


class Cdc:
    """Captures every device line to cdc.log; survives the port vanishing on reboot."""

    def __init__(self, port: str | None, log_path: Path):
        self.wanted = port
        self.log = open(log_path, "a", encoding="utf-8", newline="\n")
        self.lines: list = []
        self.cond = threading.Condition()
        self.serial = None
        self.thread = None
        self.lost = threading.Event()
        self.stop = threading.Event()

    def note(self, text: str) -> None:
        self._append(f"#HOST {text}")

    def _append(self, text: str) -> None:
        stamp = now_ms()
        with self.cond:
            self.lines.append((stamp, text))
            self.log.write(f"{stamp}\t{text}\n")
            self.log.flush()
            self.cond.notify_all()

    def open(self, timeout_s: float = 20.0) -> None:
        port = find_app_port(timeout_s, self.wanted)
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                self.serial = serial.Serial(port, 115200, timeout=0.1)
                break
            except serial.SerialException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.3)
        self.serial.dtr = True
        self.lost.clear()
        self.note(f"CDC_OPEN port={port}")
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self) -> None:
        buffer = b""
        while not self.stop.is_set():
            try:
                chunk = self.serial.read(512)
            except (serial.SerialException, OSError):
                self.note("CDC_LOST")
                self.lost.set()
                try:
                    self.serial.close()
                except Exception:  # noqa: BLE001
                    pass
                return
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                self._append(raw.decode("ascii", "replace").rstrip("\r"))

    def send(self, command: str, log_as: str | None = None) -> int:
        """Returns the index of the first line that can answer this command."""
        with self.cond:
            mark = len(self.lines)
        self.note(f"SEND {log_as if log_as is not None else command}")
        self.serial.write((command + "\n").encode("ascii"))
        self.serial.flush()
        return mark + 1

    def wait(self, pattern: str, start: int, timeout_s: float) -> tuple:
        """First (index, text) at or after start matching the regex; SystemExit on timeout."""
        rx = re.compile(pattern)
        deadline = time.monotonic() + timeout_s
        index = start
        with self.cond:
            while True:
                while index < len(self.lines):
                    text = self.lines[index][1]
                    if not text.startswith("#HOST") and rx.search(text):
                        return index, text
                    index += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"timeout waiting for /{pattern}/")
                self.cond.wait(min(remaining, 0.5))

    def mark(self) -> int:
        with self.cond:
            return len(self.lines)

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(2)
        try:
            if self.serial:
                self.serial.close()
        except Exception:  # noqa: BLE001
            pass
        self.log.close()


def wait_ready(cdc: Cdc, start: int, timeout_s: float = 20.0) -> dict:
    _, text = cdc.wait(r"^NONCE status=", start, timeout_s)
    return wc.kv(text)


def reopen_after_reset(cdc: Cdc, timeout_s: float = 25.0) -> dict:
    if not cdc.lost.wait(timeout_s):
        # Some drivers keep a dead handle open instead of failing the read: force a reopen.
        cdc.note("CDC_NO_LOSS_DETECTED")
        try:
            cdc.serial.close()
        except Exception:  # noqa: BLE001
            pass
    cdc.thread.join(2)
    mark = cdc.mark()
    cdc.open(timeout_s)
    return wait_ready(cdc, mark, timeout_s)


# ---------------------------------------------------------------------------- BLE peer

class Peer:
    """BLE central: echo (stream 0x02) or a minimal Edge responder (stream 0x01)."""

    def __init__(self, mode: str, log_path: Path, fault: str = "none", fault_count: int = 1,
                 keys: dict | None = None, expect_mtu: int | None = None):
        self.mode = mode
        self.fault = fault
        self.fault_left = fault_count
        self.fault_rid = None
        self.keys = keys or {}
        self.expect_mtu = expect_mtu
        self.log = open(log_path, "a", encoding="utf-8", newline="\n")
        self.profile = ref.load_profile(wc.REGISTRY)
        self.reasm = ble.Reassembler()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()
        self.client = None
        self.tids = ble.TransferIds()
        self.counts = {"rx_frames": 0, "tx_frames": 0, "rx_crc_fail": 0, "connections": 0,
                       "faults_applied": 0, "rx_fragments": 0, "tx_fragments": 0}
        self.disconnect_on_rx = False

    def event(self, ev: str, **fields) -> None:
        self.log.write(json.dumps({"t": now_ms(), "ev": ev, **fields}) + "\n")
        self.log.flush()

    def request_disconnect(self) -> None:
        asyncio.ensure_future(self.client.disconnect())

    async def pause(self, seconds: float) -> None:
        """Lets the Device take a delivered frame before the next one: binding §5 rule 8 drops a
        new transfer while the previous frame is still pending (rx_busy)."""
        await asyncio.sleep(seconds)

    def on_notify(self, _char, data: bytearray) -> None:
        self.counts["rx_fragments"] += 1
        if self.disconnect_on_rx and self.client is not None:
            self.disconnect_on_rx = False
            self.event("fault_disconnect_rx")
            self.request_disconnect()
            return
        done = self.reasm.feed(bytes(data), now_ms())
        if done is not None:
            self.queue.put_nowait(done)

    def on_disconnect(self, _client) -> None:
        self.ready.clear()
        self.reasm.disconnect()
        self.event("disconnected")

    async def find(self, timeout: float = 15.0):
        from bleak import BleakScanner

        def match(device, adv):
            return adv.local_name == wc.NAME and wc.SERVICE in [u.lower() for u in adv.service_uuids]
        return await BleakScanner.find_device_by_filter(match, timeout=timeout)

    async def run(self) -> None:
        from bleak import BleakClient
        responder = asyncio.ensure_future(self.respond_loop())
        try:
            while not self.stop.is_set():
                device = await self.find()
                if device is None:
                    self.event("scan_timeout")
                    continue
                try:
                    async with BleakClient(device, disconnected_callback=self.on_disconnect,
                                           timeout=20) as client:
                        self.client = client
                        self.tids = ble.TransferIds()
                        await client.start_notify(wc.TX, self.on_notify)
                        await self.settle_mtu(client)
                        self.counts["connections"] += 1
                        self.event("connected", address=device.address, att_mtu=client.mtu_size)
                        self.ready.set()
                        while client.is_connected and not self.stop.is_set():
                            await asyncio.sleep(0.1)
                except Exception as error:  # noqa: BLE001  (Windows reports link loss as errors)
                    self.event("session_error", error=repr(error))
                finally:
                    self.ready.clear()
                    self.client = None
        finally:
            responder.cancel()

    async def settle_mtu(self, client) -> None:
        """Windows exchanges the MTU ~1 s after connecting (README week 6)."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.expect_mtu is None or client.mtu_size >= self.expect_mtu:
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)

    async def send_fragments(self, fragments: list, label: str) -> None:
        client = self.client
        if client is None:
            return
        for fragment in fragments:
            await client.write_gatt_char(wc.RX, fragment, response=False)
            self.counts["tx_fragments"] += 1
        self.event("tx_transfer", label=label, fragments=len(fragments))

    def fragments(self, frame: bytes, stream: int) -> list:
        mtu = self.client.mtu_size if self.client else ble.MIN_ATT_MTU
        return ble.fragment(frame, stream, self.tids.next(), mtu)

    async def send_frame(self, frame: bytes, stream: int, label: str = "reply") -> None:
        await self.send_fragments(self.fragments(frame, stream), label)
        self.counts["tx_frames"] += 1

    def take_fault(self, request_id: int) -> str:
        if self.fault == "none" or self.fault_left <= 0:
            return "none"
        if self.fault_rid is None:
            self.fault_rid = request_id
        if request_id != self.fault_rid:
            return "none"
        self.fault_left -= 1
        self.counts["faults_applied"] += 1
        return self.fault

    async def respond_loop(self) -> None:
        while True:
            stream, frame = await self.queue.get()
            try:
                await self.handle(stream, frame)
            except Exception as error:  # noqa: BLE001
                self.event("handle_error", error=repr(error))

    async def handle(self, stream: int, frame: bytes) -> None:
        crc_ok = len(frame) >= 36 and struct.unpack_from("<I", frame, len(frame) - 4)[0] == \
            (zlib.crc32(frame[:-4]) & 0xFFFFFFFF)
        request_id = struct.unpack_from("<I", frame, 16)[0] if len(frame) >= 20 else 0
        self.counts["rx_frames"] += 1
        self.counts["rx_crc_fail"] += 0 if crc_ok else 1
        self.event("rx_frame", stream=stream, length=len(frame), request_id=request_id,
                   crc=frame[-4:][::-1].hex(), crc_ok=crc_ok,
                   sha256=hashlib.sha256(frame).hexdigest())
        if self.mode == "echo":
            if stream != ble.STREAM_DIAG_ECHO:
                self.event("drop_stream", stream=stream)   # echo-only tool (binding §9)
                return
            reply, out_stream = frame, ble.STREAM_DIAG_ECHO
        else:
            if stream != ble.STREAM_I1:
                self.event("drop_stream", stream=stream)
                return
            reply = ref.receive_request(frame, self.profile, self.keys)
            if reply is None:
                self.event("drop_request", request_id=request_id)
                return
            out_stream = ble.STREAM_I1
        fault = self.take_fault(request_id)
        if fault != "none":
            self.event("fault", fault=fault, request_id=request_id)
        await self.apply(fault, reply, out_stream, request_id)

    async def apply(self, fault: str, reply: bytes, stream: int, request_id: int) -> None:
        other = ble.STREAM_I1 if stream == ble.STREAM_DIAG_ECHO else ble.STREAM_DIAG_ECHO
        if fault == "none":
            await self.send_frame(reply, stream)
        elif fault in ("silent", "silent_once", "silent_all"):
            return
        elif fault == "crc":
            await self.send_frame(reply[:-1] + bytes([reply[-1] ^ 0x01]), stream, "bad_crc")
        elif fault == "mismatch":
            middle = len(reply) // 2
            await self.send_frame(ref.recrc(reply[:middle] + bytes([reply[middle] ^ 0x01]) +
                                            reply[middle + 1:]), stream, "byte_changed")
        elif fault in ("drop_fragment", "duplicate_fragment", "reorder"):
            frags = self.fragments(reply, stream)
            if len(frags) < 3:
                raise ValueError("fragment faults need a frame of at least 3 fragments")
            if fault == "drop_fragment":
                frags = frags[:len(frags) // 2] + frags[len(frags) // 2 + 1:]
            elif fault == "duplicate_fragment":
                frags = frags[:2] + [frags[1]] + frags[2:]
            else:
                frags[1], frags[2] = frags[2], frags[1]
            await self.send_fragments(frags, fault)
        elif fault == "malformed":
            first = self.fragments(reply, stream)[0]
            await self.send_fragments([bytes([2]) + first[1:]], "malformed")
            await self.send_frame(reply, stream)
        elif fault == "orphan":
            frags = self.fragments(reply, stream)
            await self.send_fragments([frags[1]], "orphan")
            await self.send_frame(reply, stream)
        elif fault == "superseded":
            first = self.fragments(reply, stream)[0]
            await self.send_fragments([first], "abandoned")
            await self.send_frame(reply, stream)
        elif fault == "header_mismatch":
            wrong = reply[:12] + struct.pack("<I", len(reply) + 1) + reply[16:]
            await self.send_frame(wrong, stream, "header_mismatch")
        elif fault == "reasm_timeout":
            await self.send_fragments(self.fragments(reply, stream)[:1], "first_fragment_only")
        elif fault == "disconnect_mid":
            frags = self.fragments(reply, stream)
            await self.send_fragments(frags[:len(frags) // 2], "half")
            self.event("fault_disconnect_mid")
            await self.client.disconnect()
        elif fault == "duplicate_response":
            await self.send_frame(reply, stream)
            await self.pause(FRAME_GAP_S)
            await self.send_frame(reply, stream, "duplicate")
        elif fault == "stale":
            stale = ref.recrc(reply[:16] + struct.pack("<I", (request_id ^ 0x5A5A5A5A) or 1) + reply[20:])
            await self.send_frame(stale, stream, "stale")
            await self.pause(FRAME_GAP_S)
            await self.send_frame(reply, stream)
        elif fault == "wrong_stream":
            await self.send_frame(reply, other, "wrong_stream")
            await self.pause(FRAME_GAP_S)
            await self.send_frame(reply, stream)
        elif fault == "busy_once":
            await self.send_frame(ref.encode_error(request_id, ref.STATUS["EDGE_BUSY"]), stream, "edge_busy")
        elif fault == "invalid_once":
            invalid = ref.recrc(reply[:6] + struct.pack("<H", 1) + reply[8:])   # flags != 0
            await self.send_frame(invalid, stream, "invalid")
            await self.pause(FRAME_GAP_S)
            await self.send_frame(reply, stream)
        else:
            raise ValueError(f"unknown fault {fault}")

    def close(self) -> None:
        self.event("peer_counts", **self.counts, reassembler=self.reasm.counters)
        self.log.close()


# ---------------------------------------------------------------------------- sessions

def new_out(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        raise SystemExit(f"refusing to reuse {path}; give a new --out directory")
    path.mkdir(parents=True)
    return path


def session_record(out: Path, args, extra: dict) -> None:
    wc.write_new_json(out / "session.json", {
        "schema": "week6-lab-session/1",
        "command": sys.argv,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": wc.tool_hashes(),
        "scope": "USB CDC = control/debug only; radio evidence = BLE frames counted by the device "
                 "and logged by the peer",
        **extra,
    })


def run_checker(kind: str, out: Path, extra: list) -> int:
    cmd = [sys.executable, "-B", str(HERE / "check_week6.py"), kind, "--session", str(out),
           "--output", str(out / f"check_{kind}.json")] + extra
    print("+", " ".join(cmd))
    return subprocess.run(cmd).returncode


def open_cdc(args, out: Path) -> tuple:
    cdc = Cdc(args.port, out / "cdc.log")
    mark = cdc.mark()
    cdc.open()
    try:
        ready = wait_ready(cdc, mark, 10)
    except TimeoutError:
        ready = wc.kv(cdc.wait(r"^NONCE status=", cdc.send("STATUS"), 10)[1])
    return cdc, ready


def cmd_selftest(args) -> int:
    out = new_out(args.out)
    session_record(out, args, {"kind": "selftest"})
    cdc, _ = open_cdc(args, out)
    try:
        cdc.wait(r"^STATUS mode=", cdc.send("STATUS"), 10)
        cdc.wait(r"^ENC END", cdc.send("SELFTEST ENC"), 60)
        cdc.wait(r"^P1 END", cdc.send("SELFTEST P1"), 300)
        cdc.wait(r"^QUANT END", cdc.send("SELFTEST QUANT"), 300)
        cdc.wait(r"^STACK ", cdc.send("STACK"), 10)
        time.sleep(0.5)
    finally:
        cdc.close()
    return run_checker("selftest", out, [])


def cmd_provision(args) -> int:
    out = new_out(args.out)
    key = Path(args.key_file).read_bytes()
    if len(key) != 32:
        raise SystemExit("key file must hold exactly 32 raw bytes")
    if Path(args.key_file).resolve().is_relative_to(wc.ROOT):
        raise SystemExit("the bench key must live outside the repository (nonce §4)")
    from nonce_reservation import key_check
    expected = key_check(key).hex()
    session_record(out, args, {"kind": "provision", "key_id": wc.KEY_ID, "sender_id": wc.SENDER_ID,
                               "expected_key_check": expected})
    cdc, ready = open_cdc(args, out)
    try:
        cdc.wait(r"^PROV MODE=ON", cdc.send("PROV MODE ON"), 10)
        if ready.get("reason") == "MOUNT":
            # nonce §4 step 4: storage_partition holds non-NVS data (never auto-formatted).
            if not args.erase_if_unmountable:
                raise SystemExit("NVS did not mount; rerun with --erase-if-unmountable to erase "
                                 "storage_partition once (nonce §4 step 4)")
            _, text = cdc.wait(r"^PROV ERASE err=", cdc.send("PROV ERASE"), 60)
            if "err=0" not in text:
                raise SystemExit(f"erase failed: {text}")
        _, text = cdc.wait(r"^PROV RESULT=", cdc.send(
            f"PROV KEY {wc.KEY_ID} {wc.SENDER_ID} {key.hex()}",
            log_as=f"PROV KEY {wc.KEY_ID} {wc.SENDER_ID} <key redacted>"), 30)
        cdc.wait(r"^PROV MODE=OFF", cdc.send("PROV MODE OFF"), 10)
        result = wc.kv(text)
    finally:
        cdc.close()
    ok = result.get("RESULT") == "OK" and result.get("key_check") == expected
    print(f"PROVISION {'PASS' if ok else 'FAIL'}: {text} (expected key_check {expected})")
    return 0 if ok else 1


def cmd_nonce_reboot(args) -> int:
    out = new_out(args.out)
    session_record(out, args, {"kind": "nonce-reboot", "cycles": args.cycles,
                               "stress_ms": [args.min_ms, args.max_ms], "seed": args.seed})
    rng = random.Random(args.seed)
    cdc, ready = open_cdc(args, out)
    try:
        if ready.get("status") != "READY":
            raise SystemExit(f"nonce state not READY: {ready}")
        for cycle in range(args.cycles):
            duration = rng.randint(args.min_ms, args.max_ms)
            cdc.note(f"CYCLE {cycle} kind=SOFT_RESET stress_ms={duration}")
            cdc.send(f"NTEST STRESS {duration} 1 {args.gap_ms}")
            state = reopen_after_reset(cdc)
            print(f"cycle {cycle + 1}/{args.cycles}: status={state.get('status')} "
                  f"reserved_through={state.get('reserved_through')}")
            if state.get("status") != "READY":
                cdc.note("STOP status not READY")
                break
        cdc.wait(r"^NONCE status=", cdc.send("NONCE"), 10)
    finally:
        cdc.close()
    return run_checker("nonce", out, ["--min-soft", str(args.cycles)])


def cmd_nonce_unplug(args) -> int:
    out = new_out(args.out)
    session_record(out, args, {"kind": "nonce-unplug", "cycles": args.cycles})
    cdc, ready = open_cdc(args, out)
    try:
        if ready.get("status") != "READY":
            raise SystemExit(f"nonce state not READY: {ready}")
        for cycle in range(args.cycles):
            cdc.note(f"CYCLE {cycle} kind=POWER_CUT")
            cdc.send(f"NTEST STRESS 0 0 {args.gap_ms}")
            print(f"[{cycle + 1}/{args.cycles}] RUT USB cua dongle bay gio (dang ghi Flash lien tuc), "
                  "doi 2 s roi cam lai.")
            state = reopen_after_reset(cdc, timeout_s=300)
            print(f"  -> boot status={state.get('status')} reserved_through={state.get('reserved_through')}")
            if state.get("status") != "READY":
                break
        cdc.wait(r"^NONCE status=", cdc.send("NONCE"), 10)
    finally:
        cdc.close()
    return run_checker("nonce", out, ["--min-power", str(args.cycles)])


def cmd_nonce_hooks(args) -> int:
    out = new_out(args.out)
    session_record(out, args, {"kind": "nonce-hooks"})
    cdc, ready = open_cdc(args, out)
    try:
        if ready.get("status") != "READY":
            raise SystemExit(f"nonce state not READY: {ready}")
        for test in ("FAILWRITE", "READBACK"):
            cdc.note(f"HOOK {test}")
            cdc.wait(r"^NTEST " + test, cdc.send(f"NTEST {test}"), 30)
            cdc.wait(r"^NONCE status=FAULT", cdc.send("NONCE"), 10)
            cdc.note("CYCLE hook kind=SOFT_RESET")
            cdc.send("REBOOT")
            reopen_after_reset(cdc)
        for hook in ("STATE_CRC", "STATE_MISSING", "PROVISION_CORRUPT", "KEY_MISMATCH", "NONE"):
            cdc.note(f"HOOK BOOT {hook}")
            cdc.wait(r"^NONCE status=", cdc.send(f"NTEST BOOT {hook}"), 30)
        cdc.note("CYCLE final kind=SOFT_RESET")
        cdc.send("REBOOT")
        reopen_after_reset(cdc)
        cdc.wait(r"^NONCE ALLOC", cdc.send("NONCE ALLOC 3"), 10)
    finally:
        cdc.close()
    return run_checker("nonce", out, ["--hooks"])


def cmd_sentinel(args) -> int:
    out = new_out(args.out)
    session_record(out, args, {"kind": "sentinel", "op": args.op})
    cdc, _ = open_cdc(args, out)
    try:
        _, text = cdc.wait(r"^SENTINEL ", cdc.send(f"NTEST SENTINEL {args.op.upper()}"), 20)
        cdc.wait(r"^NONCE status=", cdc.mark(), 5)
        cdc.wait(r"^STATUS mode=", cdc.send("STATUS"), 10)
    finally:
        cdc.close()
    print(text)
    return 0 if wc.kv(text).get("err") == "0" else 1


def load_keys(args) -> dict:
    if not getattr(args, "key_file", None):
        return {}
    key = Path(args.key_file).read_bytes()
    if len(key) != 32:
        raise SystemExit("key file must hold exactly 32 raw bytes")
    return {wc.KEY_ID: key}


async def drive_run(cdc: Cdc, peer: Peer, mode: str, command: str, arm_i2: bool,
                    timeout_s: float, pre: list | None = None) -> None:
    peer_task = asyncio.ensure_future(peer.run())
    try:
        await asyncio.wait_for(peer.ready.wait(), 60)
        await asyncio.sleep(1.0)
        for extra in pre or []:   # e.g. CONNPARAM 6 12; the result is logged as EVT CONN_PARAM
            cdc.send(extra)
            await asyncio.sleep(2.0)
        await asyncio.to_thread(cdc.wait, r"^MODE ",
                                cdc.send(f"MODE {'ECHO' if mode == 'echo' else 'NORMAL'}"), 10)
        if arm_i2:
            _, text = await asyncio.to_thread(cdc.wait, r"^I2 ARM=", cdc.send("I2 ARM"), 10)
            if "ARM=1" not in text:
                raise SystemExit(f"device refused I2 ARM: {text}")
        for _ in range(10):
            start = cdc.send(command)
            _, text = await asyncio.to_thread(cdc.wait, r"^(RUN BEGIN|ERROR)", start, 15)
            if text.startswith("RUN BEGIN"):
                break
            await asyncio.sleep(1.5)
        else:
            raise SystemExit("device never started the run")
        await asyncio.to_thread(cdc.wait, r"^COUNTERS ", start, timeout_s)
        await asyncio.to_thread(cdc.wait, r"^REASM ", start, 10)
        await asyncio.sleep(1.0)
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


def cmd_loopback(args) -> int:
    out = new_out(args.out)
    session_record(out, args, {"kind": "loopback", "count": args.count, "pattern": args.pattern,
                               "mode": args.mode, "expect_mtu": args.expect_mtu})
    cdc, _ = open_cdc(args, out)
    peer = Peer(args.mode, out / "peer.jsonl", keys=load_keys(args), expect_mtu=args.expect_mtu)
    try:
        needs_i2 = args.pattern == "MIX" or any(
            int(s) in _i2_sizes() | {6380} for s in _sizes(args.pattern))
        asyncio.run(drive_run(cdc, peer, args.mode, f"RUN {args.count} {args.pattern}", needs_i2,
                              args.timeout, args.pre))
    finally:
        peer.close()
        cdc.close()
    extra = ["--expect-mtu", str(args.expect_mtu), "--count", str(args.count)]
    if args.require_sizes:
        extra += ["--require-sizes", args.require_sizes]
    return run_checker("loopback", out, extra)


def _sizes(pattern: str) -> list:
    return pattern[6:].split(",") if pattern.startswith("SIZES=") else []


def _i2_sizes() -> set:
    vectors = json.loads((wc.REF / "vectors.json").read_text(encoding="utf-8"))
    return {row["total_i2"] for row in vectors["split_table"]}


def cmd_negative(args) -> int:
    out = new_out(args.out)
    names = args.only.split(",") if args.only else list(wc.NEGATIVE_SCENARIOS)
    session_record(out, args, {"kind": "negative", "scenarios": names})
    failures = 0
    for name in names:
        spec = wc.NEGATIVE_SCENARIOS[name]
        sub = out / name
        sub.mkdir()
        print(f"=== negative scenario {name}: {spec}")
        cdc, _ = open_cdc(args, sub)
        peer = Peer(spec["mode"], sub / "peer.jsonl", fault=name if name not in ("silent_once", "silent_all")
                    else "silent", fault_count=spec["fault_count"], expect_mtu=args.expect_mtu)
        if name == "disconnect_rx":
            peer.fault = "none"
            peer.disconnect_on_rx = True
            peer.counts["faults_applied"] += 1
        try:
            asyncio.run(drive_run(cdc, peer, spec["mode"], f"RUN {spec['count']} SIZES={spec['sizes']}",
                                  False, 180, args.pre))
        except (TimeoutError, SystemExit) as error:
            cdc.note(f"SCENARIO_ERROR {error!r}")
        finally:
            peer.close()
            cdc.close()
        failures += run_checker("negative", sub, ["--scenario", name]) != 0
    print(f"NEGATIVE scenarios failed: {failures}/{len(names)}")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="application CDC port (default: find VID 2FE3 PID 0004)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True, type=Path)
        p.set_defaults(func=func)
        return p

    add("selftest", cmd_selftest)
    p = add("provision", cmd_provision)
    p.add_argument("--key-file", required=True)
    p.add_argument("--erase-if-unmountable", action="store_true")
    p = add("nonce-reboot", cmd_nonce_reboot)
    p.add_argument("--cycles", type=int, default=110)
    p.add_argument("--min-ms", type=int, default=150)
    p.add_argument("--max-ms", type=int, default=1200)
    p.add_argument("--gap-ms", type=int, default=3)
    p.add_argument("--seed", type=int, default=20261019)
    p = add("nonce-unplug", cmd_nonce_unplug)
    p.add_argument("--cycles", type=int, default=12)
    p.add_argument("--gap-ms", type=int, default=3)
    add("nonce-hooks", cmd_nonce_hooks)
    p = add("sentinel", cmd_sentinel)
    p.add_argument("--op", required=True, choices=["write", "read"])
    p = add("loopback", cmd_loopback)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--pattern", required=True, help="MIX | PLAIN | SIZES=a,b,..")
    p.add_argument("--mode", choices=["echo", "respond"], default="echo")
    p.add_argument("--expect-mtu", type=int, required=True, choices=[23, 247])
    p.add_argument("--require-sizes", help="e.g. 113,153,6124,6380")
    p.add_argument("--key-file", help="bench key, only for --mode respond with I2/1 requests")
    p.add_argument("--timeout", type=float, default=7200)
    p.add_argument("--pre", action="append", help="device command sent before RUN (repeatable)")
    p = add("negative", cmd_negative)
    p.add_argument("--expect-mtu", type=int, default=247, choices=[23, 247])
    p.add_argument("--only", help="comma-separated scenario names")
    p.add_argument("--pre", action="append", help="device command sent before each RUN")
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
