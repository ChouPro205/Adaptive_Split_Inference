#!/usr/bin/env python3
"""Host simulation of a week 6 loopback: the firmware's C exchange + reassembler (device/week6,
through the test shim) driven like main.c exchange_packet(), connected to the real Peer class of
week6_lab.py through a fake BLE client, on a virtual clock.

Checks that every negative scenario of week6_common.NEGATIVE_SCENARIOS produces the counters
the checker expects, and that a fault-free MIX run of 1000 packets completes. This validates
the test design before the lab; it is NOT radio evidence (no BLE stack, no timing realism).
Run: device/host/.venv/Scripts/python.exe -B device/scripts/test_week6_sim.py
"""
from __future__ import annotations

import asyncio
import ctypes
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_week6_host as th  # noqa: E402  (builds the shim DLL)
import week6_common as wc  # noqa: E402
import week6_lab as lab  # noqa: E402
import i1_ble_binding as ble  # noqa: E402

LIB, C = th.LIB, th.C
TMP = Path(tempfile.mkdtemp(prefix="week6_sim_"))
RECONNECT_MS = 2000
TX_MS_PER_FRAGMENT = 2


class FakeClient:
    def __init__(self, sim: "DeviceSim"):
        self.sim = sim
        self.mtu_size = sim.mtu

    @property
    def is_connected(self) -> bool:
        return self.sim.up

    async def write_gatt_char(self, _uuid, data, response=False):
        self.sim.to_device(bytes(data))

    async def disconnect(self):
        self.sim.disconnect()


class SimPeer(lab.Peer):
    def request_disconnect(self) -> None:
        self.sim.disconnect()

    async def pause(self, seconds: float) -> None:
        self.sim.advance(int(seconds * 1000))


class DeviceSim:
    def __init__(self, peer: SimPeer, mtu: int = 247, echo: bool = True):
        self.peer, self.mtu, self.echo = peer, mtu, echo
        peer.sim = self
        peer.client = FakeClient(self)
        self.now = 0
        self.up = True
        self.reconnect_at = None
        self.disconnections = 0
        self.tid = ctypes.c_uint16(0)
        self.tx_result = None
        self.sent = b""
        self.rid = 0x2000
        C.reasm_init(hold=True)
        LIB.shim_exch_init(8000, 30, 2, 250, 10000)
        self.pending = []

    # --- link
    def link_ready(self) -> bool:
        if not self.up and self.reconnect_at is not None and self.now >= self.reconnect_at:
            self.up, self.reconnect_at = True, None
            self.tid = ctypes.c_uint16(0)
            self.peer.tids = ble.TransferIds()
        return self.up

    def disconnect(self) -> None:
        if not self.up:
            return
        self.up = False
        self.disconnections += 1
        self.reconnect_at = self.now + RECONNECT_MS
        LIB.shim_reasm_disconnect()
        self.peer.on_disconnect(None)

    def to_device(self, fragment: bytes) -> None:
        if not self.up:
            return
        done = C.reasm_feed(fragment, self.now)
        if done is not None:
            self.pending.append(done)

    def advance(self, ms: int) -> None:
        self.now += ms
        LIB.shim_reasm_tick(ctypes.c_uint32(self.now))
        self.drain()

    def drain(self) -> None:
        while self.pending:
            stream, frame = self.pending.pop(0)
            C.frame(self.echo, stream, frame, self.sent, self.now)
            LIB.shim_reasm_release()

    # --- device TX (ble_link.c transfer()) and peer reaction
    def transmit(self, frame: bytes) -> None:
        tid = LIB.shim_next_transfer_id(ctypes.byref(self.tid))
        stream = ble.STREAM_DIAG_ECHO if self.echo else ble.STREAM_I1
        frags = ble.fragment(frame, stream, tid, self.mtu)
        for f in frags:
            if not self.up:
                self.tx_result = ("NOTCONN", self.now)
                return
            self.now += TX_MS_PER_FRAGMENT
            self.peer.on_notify(None, bytearray(f))
        self.tx_result = ("DONE", self.now, len(frame))
        while not self.peer.queue.empty():
            stream_in, frame_in = self.peer.queue.get_nowait()
            asyncio.run(self.peer.handle(stream_in, frame_in))

    # --- main.c exchange_packet()
    def run_packet(self, frame: bytes) -> int:
        self.sent = frame
        LIB.shim_exch_begin(struct.unpack_from("<I", frame, 16)[0], ctypes.c_uint32(self.now))
        seen = self.disconnections
        for _ in range(200000):
            LIB.shim_reasm_tick(ctypes.c_uint32(self.now))
            if self.tx_result is not None:
                result, self.tx_result = self.tx_result, None
                if result[0] == "DONE":
                    n_resp = ble.fragment_count(result[2] if self.echo else 64, self.mtu)
                    LIB.shim_exch_sent(ctypes.c_uint32(result[1]), ctypes.c_uint32(n_resp))
                else:
                    LIB.shim_exch_aborted(ctypes.c_uint32(self.now), 0)
            self.drain()
            if self.disconnections != seen:
                seen = self.disconnections
                LIB.shim_exch_disconnected(ctypes.c_uint32(self.now))
            action, wait = C.poll(self.now, self.link_ready())
            if action == th.ACT_FINISHED:
                return LIB.shim_exch_state()
            if action == th.ACT_SEND:
                LIB.shim_exch_started(ctypes.c_uint32(self.now))
                self.transmit(frame)
                continue
            self.advance(min(wait, 50))
        raise AssertionError("simulation did not finish")


def frame_for_size(size: int, rid: int) -> bytes:
    """Plain registry request of the given size with real-looking q (all valid INT8)."""
    for row in th.VECTORS["split_table"]:
        if row["total_plain"] == size:
            c, l = row["C"], row["L"]
            q = bytes((i * 7 + 3) % 255 for i in range(c * l)).replace(b"\x80", b"\x7f")
            frame, _, _ = C.build(rid, 1296651265, row["split_id"], c, l, q, [0x3F800000] * c)
            return frame
    raise ValueError(size)


def mix_frame(i: int, rid: int) -> bytes:
    """Same sizes as spec_for(PATTERN_MIX); I2/1 frames built with the public key (sim only)."""
    if i % 25 == 24:
        q = bytes((k * 5 + 1) % 255 for k in range(5760)).replace(b"\x80", b"\x7f")
        nonce = struct.pack("<IQ", 131073, i + 1)
        frame, _, _ = C.build(rid, 1, 1, 64, 90, q, [0x3F800000] * 64, key=th.PUBLIC_KEY,
                              key_id=65537, nonce=nonce)
        return frame
    s = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5 + [4] * 5 + [5] * 5 + [6] * 4 + [7] * 4 + [8] * 4 + \
        [9] * 4 + [10] * 4
    row = th.VECTORS["split_table"][s[i % 50]]
    q = bytes((k * 3 + i) % 255 for k in range(row["C"] * row["L"])).replace(b"\x80", b"\x7f")
    if (i // 50) % 2 == 1:
        frame, _, _ = C.build(rid, 1296651265, row["split_id"], row["C"], row["L"], q,
                              [0x3F800000] * row["C"], key=th.PUBLIC_KEY, key_id=65537,
                              nonce=struct.pack("<IQ", 131073, i + 1))
    else:
        frame, _, _ = C.build(rid, 1296651265, row["split_id"], row["C"], row["L"], q, [0x3F800000] * row["C"])
    return frame


class NegativeScenarioSimTests(unittest.TestCase):
    def run_scenario(self, name: str) -> tuple:
        spec = wc.NEGATIVE_SCENARIOS[name]
        fault = "silent" if name in ("silent_once", "silent_all") else name
        peer = SimPeer(spec["mode"], TMP / f"{name}.jsonl", fault=fault, fault_count=spec["fault_count"])
        if name == "disconnect_rx":
            peer.fault, peer.disconnect_on_rx = "none", True
        sim = DeviceSim(peer, echo=spec["mode"] == "echo")
        for k in range(spec["count"]):
            sim.rid += 1
            sim.run_packet(frame_for_size(int(spec["sizes"]), sim.rid))
        sim.advance(200)   # main.c: late frames are drained after the run
        peer.close()
        return C.exch_counters(), C.reasm_counters()

    def test_every_scenario_gives_the_expected_counters(self):
        for name, spec in wc.NEGATIVE_SCENARIOS.items():
            with self.subTest(scenario=name):
                counters, reasm = self.run_scenario(name)
                for key, value in spec["expect"].items():
                    self.assertEqual(counters[key], value, f"{name}: {key} {counters} {reasm}")
                for key, value in spec.get("reasm_min", {}).items():
                    self.assertGreaterEqual(reasm.get(key, 0), value, f"{name}: {key} {reasm}")
                self.assertEqual(counters["planned"], spec["count"])

    def test_fault_free_mix_run_completes(self):
        peer = SimPeer("echo", TMP / "mix.jsonl")
        sim = DeviceSim(peer)
        sizes = set()
        for i in range(1000):
            sim.rid += 1
            frame = mix_frame(i, sim.rid)
            sizes.add(len(frame))
            self.assertEqual(sim.run_packet(frame), th.S_DONE, i)
        peer.close()
        c = C.exch_counters()
        self.assertEqual((c["planned"], c["completed"], c["failed"], c["retries"]), (1000, 1000, 0, 0))
        self.assertTrue(set(wc.REQUIRED_SIZES) <= sizes)

    def test_mtu23_large_frames(self):
        peer = SimPeer("echo", TMP / "mtu23.jsonl")
        sim = DeviceSim(peer, mtu=23)
        for size in (113, 6084):
            sim.rid += 1
            self.assertEqual(sim.run_packet(frame_for_size(size, sim.rid)), th.S_DONE)
        peer.close()
        self.assertEqual(C.exch_counters()["timeouts"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
