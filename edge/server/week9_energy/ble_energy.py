#!/usr/bin/env python3
"""One KV260 BLE energy session: unchanged Week8 inference, no load generator/MQTT."""
from __future__ import annotations
import argparse
import asyncio
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'week8'))
from common import Worker, save, seal, file_sha
from service import Receiver
from sv1_log import sv1_row
import i1_ble_binding as ble
from phy import gate, now

NAME = 'ASI-SV1'
SERVICE = '74e40001-0994-465c-bcd4-b94671a54935'
RX = '74e40002-0994-465c-bcd4-b94671a54935'
TX = '74e40003-0994-465c-bcd4-b94671a54935'

async def run(a):
    from bleak import BleakClient, BleakScanner
    if platform.system() != 'Linux' or platform.machine() != 'aarch64':
        raise ValueError('Run the official energy session on KV260 Linux aarch64')
    if version('bleak') != '0.22.3':
        raise ValueError('Use the verified Bleak 0.22.3 environment')
    preparation = json.loads((a.session/'preparation.json').read_text())
    expected = json.loads((a.session/'expected_backend.json').read_text())
    a.output.mkdir(parents=True, exist_ok=False)
    worker = None
    rows = []
    natural_disconnect = False
    connected_count = 0
    overflow = 0
    failure = None
    streams = {n: (a.output/n).open('x', encoding='utf-8') for n in
               ('peer.jsonl', 'requests.jsonl', 'events.jsonl')}
    def event(kind, **fields):
        if not streams['events.jsonl'].closed:
            streams['events.jsonl'].write(json.dumps(dict(event=kind, t_ms=now(),
                clock='EDGE_MONOTONIC_MS', connection=0, **fields))+'\n')
            streams['events.jsonl'].flush()
    try:
        key = a.key_file.read_bytes()
        if len(key) != 32:
            raise ValueError('Bench key must contain 32 raw bytes')
        worker = Worker(a.worker, a.deploy, a.cpu_ops, a.output/'worker.log')
        if any(worker.metadata.get(k) != v for k, v in expected.items()):
            raise ValueError('Worker/model/plugins differ from the Week8 pins')
        receiver = Receiver(worker, key)
        save(a.output/'run.json', dict(scope='KV260_ENERGY_S2_NOT_MQTT',
            start_unix_ms=time.time_ns()//1_000_000, start_monotonic_ms=now(),
            clock='EDGE_MONOTONIC_MS', adapter=a.adapter, target_address=a.address,
            session_deadline_s=a.max_s, final_disconnect_deadline_s=a.disconnect_s,
            source_commit=preparation['service_commit'],
            service_sha256=file_sha(Path(__file__)), phy_sha256=file_sha(Path(__file__).with_name('phy.py')),
            backend=worker.metadata, expected_requests=200, target_mtu=a.mtu,
            sequence_scope='RAM per process, unchanged Week8 receiver; bench only',
            timing_scope='RX complete to final BlueZ response submission; not Device receipt',
            changes='PHY gate, energy lifecycle and direct numeric/PHY logs; no inference changes',
            queue_mqtt=False, extra_warmup=0))
        deadline = time.monotonic()+a.max_s
        device = None
        while device is None and time.monotonic() < deadline:
            print('SCANNING ASI-SV1; ready for SV1 to start PPK2 power', flush=True)
            device = await BleakScanner.find_device_by_filter(
                lambda d, v: v.local_name == NAME and SERVICE in
                [u.lower() for u in (v.service_uuids or [])] and
                (a.address is None or d.address.upper() == a.address.upper()),
                timeout=min(10, max(.1, deadline-time.monotonic())), adapter=a.adapter)
            if device is None:
                event('scan_timeout')
        if device is None:
            raise TimeoutError('No peer before session deadline')
        disconnected = asyncio.Event()
        queue = asyncio.Queue(maxsize=1)
        reasm = ble.Reassembler(streams=frozenset({1}))
        tids = ble.TransferIds()
        def on_disconnect(client):
            event('disconnected', peer=device.address)
            disconnected.set()
        def notified(char, data):
            nonlocal overflow
            frame = reasm.feed(bytes(data), now())
            if frame:
                try:
                    queue.put_nowait((frame, now()))
                except asyncio.QueueFull:
                    overflow += 1
                    event('rx_busy')
        # There is intentionally no reconnect loop after this first attempt.
        async with BleakClient(device, adapter=a.adapter, disconnected_callback=on_disconnect) as client:
            connected_count = 1
            event('connected', peer=device.address)
            await client._backend._acquire_mtu()
            if client.mtu_size != a.mtu:
                raise ValueError('Actual MTU differs: '+str(client.mtu_size))
            h = await asyncio.to_thread(gate, a.adapter, device.address, a.output, 0)
            event('phy_gate_ok', handle=h, tx_phy='2M', rx_phy='2M', att_mtu=client.mtu_size)
            await client.start_notify(TX, notified)
            print('BLE_READY PHY=2M/2M MTU=%d; connection=0'%client.mtu_size, flush=True)
            while client.is_connected and not disconnected.is_set() and len(rows) < 200:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Session deadline reached')
                try:
                    (stream, packet), t_rx = await asyncio.wait_for(queue.get(), .2)
                except asyncio.TimeoutError:
                    reasm.tick(now())
                    continue
                response, row = await asyncio.to_thread(receiver.handle, device.address, packet, t_rx)
                row.update(connection=0, response_sent=False, t_tx_done_ms=None)
                if response is not None:
                    try:
                        for fragment in ble.fragment(response, stream, tids.next(), client.mtu_size):
                            await client.write_gatt_char(RX, fragment, response=False)
                        row.update(response_sent=True, t_tx_done_ms=now())
                    except Exception as exc:
                        row['send_error'] = type(exc).__name__
                streams['peer.jsonl'].write(json.dumps(row, allow_nan=False)+'\n')
                streams['peer.jsonl'].flush()
                streams['requests.jsonl'].write(json.dumps(sv1_row(row), allow_nan=False)+'\n')
                streams['requests.jsonl'].flush()
                rows.append(row)
                print('REQUEST %d/200 result=%s'%(len(rows), row['result']), flush=True)
                if row['result'] != 'OK' or not row['response_sent'] or row.get('cache_hit') or overflow:
                    raise ValueError('Request error/retry/overflow; preserve failed session')
            if len(rows) == 200:
                print('COUNT_200; waiting for DEVICE disconnect; do not Ctrl+C', flush=True)
                try:
                    await asyncio.wait_for(disconnected.wait(), min(a.disconnect_s,
                        max(.1, deadline-time.monotonic())))
                except asyncio.TimeoutError:
                    raise TimeoutError('Device did not disconnect after the final response')
                if not queue.empty() or overflow:
                    raise ValueError('Unexpected request after the expected 200 responses')
            natural_disconnect = disconnected.is_set()
            event('connection_end', rows=len(rows), reassembly=reasm.counters,
                  device_disconnect_observed=natural_disconnect)
        if len(rows) != 200 or not natural_disconnect:
            raise ValueError('Incomplete single-connection energy session')
    except BaseException as exc:
        failure = type(exc).__name__+': '+str(exc)
        event('session_error', error=failure)
        raise
    finally:
        if worker:
            worker.close()
        complete = failure is None and len(rows) == 200 and natural_disconnect and not overflow
        save(a.output/'summary.json', dict(status='CAPTURE_COMPLETE_REVIEW_REQUIRED' if complete else
            'INCOMPLETE_REVIEW_REQUIRED', requests=len(rows), connections=connected_count,
            ok=sum(r['result']=='OK' and r['response_sent'] for r in rows),
            device_disconnect_observed=natural_disconnect, overflow=overflow, error=failure,
            acceptance='PENDING_SV1_PPK2_AND_CHECKER'))
        for stream in streams.values():
            stream.close()
        seal(a.output)
    print('ENERGY_CAPTURE_SAVED; no reconnect; send sealed logs to SV1', flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('session', 'output', 'worker', 'deploy', 'cpu-ops', 'key-file'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--adapter', default='hci0')
    p.add_argument('--address', default='C8:F6:EE:EF:02:CF')
    p.add_argument('--mtu', type=int, default=247)
    p.add_argument('--max-s', type=float, default=1200)
    p.add_argument('--disconnect-s', type=float, default=30)
    a = p.parse_args()
    if a.max_s <= 0 or a.disconnect_s <= 0 or a.mtu != 247:
        p.error('Energy bench requires MTU247 and positive deadlines')
    try:
        asyncio.run(run(a))
    except KeyboardInterrupt:
        print('Interrupted; preserve failed/incomplete output; do not append another trial')
        raise SystemExit(130)

if __name__ == '__main__':
    main()
