#!/usr/bin/env python3
"""Week 6 BLE link probe: laptop central <-> week6 skeleton on the dongle.

Checks advertising (name + 128-bit service UUID), the GATT layout of I1 BLE binding v1 §2,
CCCD subscription, the negotiated ATT MTU seen by both sides, RX write counting and
re-advertising after disconnect. The USB CDC log is captured in parallel (debug only,
never radio evidence) for the Device-side MTU and runtime stack high-water marks.
Run with device/host/.venv. Exit 0 = PASS, 1 = FAIL. Writes to a new directory.
"""
import argparse
import asyncio
import json
import pathlib
import re
import sys
import threading
import time
from datetime import datetime, timezone

import serial
from bleak import BleakClient, BleakScanner

SERVICE = "74e40001-0994-465c-bcd4-b94671a54935"
RX = "74e40002-0994-465c-bcd4-b94671a54935"
TX = "74e40003-0994-465c-bcd4-b94671a54935"
NAME = "ASI-SV1"
FRAGMENT_OVERHEAD = 11


class CdcLog(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.serial = serial.Serial(port, 115200, timeout=0.2)
        self.lines = []
        self.stop = threading.Event()

    def run(self):
        buffer = b""
        while not self.stop.is_set():
            buffer += self.serial.read(512)
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                self.lines.append((time.monotonic(), raw.decode("ascii", "replace").strip()))

    def close(self):
        self.stop.set()
        self.join(2)
        self.serial.close()

    def since(self, t0):
        return [line for t, line in self.lines if t >= t0]


def stack_peaks(lines):
    peaks = {}
    for line in lines:
        m = re.match(r"STACK (\S+) used=(\d+) size=(\d+)", line)
        if m:
            name, used, size = m.group(1), int(m.group(2)), int(m.group(3))
            prev = peaks.get(name, {"used": 0, "size": size})
            peaks[name] = {"used": max(prev["used"], used), "size": size}
    return peaks


async def find_device(timeout):
    def match(device, adv):
        return adv.local_name == NAME and SERVICE in [u.lower() for u in adv.service_uuids]
    return await BleakScanner.find_device_by_filter(match, timeout=timeout)


async def probe(args, cdc):
    result = {"steps": {}}
    t_start = time.monotonic()
    device = await find_device(15)
    result["steps"]["advertising_found"] = device is not None
    if device is None:
        return result, t_start
    result["device_address"] = device.address
    notifications = []
    async with BleakClient(device, timeout=20) as client:
        t_conn = time.monotonic()
        service = client.services.get_service(SERVICE)
        props = {}
        if service is not None:
            for char in service.characteristics:
                props[char.uuid.lower()] = sorted(char.properties)
        result["gatt_properties"] = props
        result["steps"]["gatt_layout"] = (
            service is not None
            and {"write", "write-without-response"} <= set(props.get(RX, []))
            and "notify" in props.get(TX, []))
        await client.start_notify(TX, lambda _, data: notifications.append(bytes(data)))
        await asyncio.sleep(3)  # let Windows finish the MTU exchange
        mtu = client.mtu_size
        result["laptop_att_mtu"] = mtu
        payload = bytes(range(256)) * 2
        size = mtu - 3
        await client.write_gatt_char(RX, payload[:size], response=True)
        await client.write_gatt_char(RX, payload[:size], response=False)
        result["rx_written_bytes"] = 2 * size
        await asyncio.sleep(args.connected_seconds)
        await client.stop_notify(TX)
    t_disc = time.monotonic()
    await asyncio.sleep(2)
    result["steps"]["readvertises_after_disconnect"] = await find_device(15) is not None
    await asyncio.sleep(6)  # one more device STATS/STACK block after disconnect
    result["notifications_received"] = len(notifications)
    result["_times"] = (t_conn, t_disc)
    return result, t_start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdc-port", required=True)
    parser.add_argument("--expect-mtu", required=True, type=int)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--connected-seconds", type=float, default=12)
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    args.output.mkdir(parents=True)

    cdc = CdcLog(args.cdc_port)
    cdc.start()
    time.sleep(6)  # baseline READY/STACK block while advertising
    started = datetime.now(timezone.utc).isoformat()
    try:
        result, t_start = asyncio.run(probe(args, cdc))
    finally:
        time.sleep(1)
        cdc.close()
    lines = [line for _, line in cdc.lines]
    (args.output / "cdc.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    device_mtu = [int(m.group(1)) for m in (re.search(r"ATT MTU .*uatt_mtu=(\d+)", l) for l in lines) if m]
    ccc = [l for l in lines if l.startswith("TX CCC notify=1")]
    disconnected = [l for l in lines if l.startswith("DISCONNECTED")]
    rx_bytes = [int(m.group(1)) for m in (re.search(r"STATS .*rx_bytes=(\d+)", l) for l in lines) if m]
    expected_rx = result.get("rx_written_bytes")
    steps = result["steps"]
    steps["laptop_mtu_expected"] = result.get("laptop_att_mtu") == args.expect_mtu
    steps["device_mtu_expected"] = bool(device_mtu) and device_mtu[-1] == args.expect_mtu
    steps["device_saw_cccd_notify"] = bool(ccc)
    steps["device_saw_disconnect"] = bool(disconnected)
    steps["device_counted_rx_bytes"] = bool(rx_bytes) and rx_bytes[-1] == expected_rx
    connected_lines = cdc.since(t_start)
    report = {
        "schema": "week6-ble-probe/1",
        "label": args.label,
        "started_utc": started,
        "status": "PASS" if all(steps.values()) else "FAIL",
        "steps": steps,
        "expected_att_mtu": args.expect_mtu,
        "laptop_att_mtu": result.get("laptop_att_mtu"),
        "device_att_mtu": device_mtu[-1] if device_mtu else None,
        "frame_bytes_per_fragment": (device_mtu[-1] - FRAGMENT_OVERHEAD) if device_mtu else None,
        "gatt_properties": result.get("gatt_properties"),
        "rx_written_bytes": expected_rx,
        "device_rx_bytes": rx_bytes[-1] if rx_bytes else None,
        "stack_high_water_whole_session": stack_peaks(lines),
        "stack_high_water_after_ble_start": stack_peaks(connected_lines),
        "device_address": result.get("device_address"),
        "note": "Skeleton link probe only: not the 1000-packet loopback of criterion 3.",
    }
    (args.output / "probe.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in steps.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"MTU laptop={report['laptop_att_mtu']} device={report['device_att_mtu']} "
          f"expected={args.expect_mtu}; RESULT: {report['status']}")
    for name, s in report["stack_high_water_whole_session"].items():
        print(f"STACK {name}: {s['used']}/{s['size']} B")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
