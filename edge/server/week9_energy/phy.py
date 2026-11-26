"""Handle-safe active-PHY gate for the single-connection energy session."""
import json
from pathlib import Path
import re
import subprocess
import time

def now():
    return time.monotonic_ns() // 1_000_000

def gate(adapter, peer, output, connection=0):
    from supplemental_link import handle_for, phy_args, command_status
    if not re.fullmatch(r'hci[0-9]+', adapter):
        raise ValueError('Invalid adapter')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', peer):
        raise ValueError('Invalid peer address')
    output = Path(output)
    def record(name, row):
        with (output/name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, allow_nan=False)+'\n')
    def call(args):
        start = now()
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        record('hci_commands.jsonl', dict(t_start_ms=start, t_ms=now(), argv=args,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            connection=connection, clock='EDGE_MONOTONIC_MS'))
        result.check_returncode()
        return result.stdout
    def handle():
        return handle_for(call(['hcitool', '-i', adapter, 'con']), peer)
    h = handle()
    text = call(['hcitool', '-i', adapter, 'cmd', *phy_args(h, 'set-2m')])
    if command_status(text, 0x2032)[0]:
        raise ValueError('Set PHY rejected; notifications remain disabled')
    end = time.monotonic()+5
    while time.monotonic() < end:
        if handle() != h:
            raise ValueError('Connection handle changed during PHY gate')
        try:
            text = call(['hcitool', '-i', adapter, 'cmd', *phy_args(h, 'read')])
            status, payload = command_status(text, 0x2030)
        except Exception as exc:
            record('phy.jsonl', dict(event='read_phy',t_ms=now(),connection=connection,
                handle=h,tx_phy=None,rx_phy=None,hci_status=None,error=type(exc).__name__,
                clock='EDGE_MONOTONIC_MS'))
            raise
        row = dict(event='read_phy', t_ms=now(), connection=connection, handle=h,
                   tx_phy=None, rx_phy=None, hci_status=status, clock='EDGE_MONOTONIC_MS')
        if status == 0 and len(payload) == 4 and int.from_bytes(payload[:2], 'little') == h:
            names = {1: '1M', 2: '2M', 3: 'Coded'}
            row.update(tx_phy=names.get(payload[2], str(payload[2])),
                       rx_phy=names.get(payload[3], str(payload[3])))
        record('phy.jsonl', row)
        if status or row['tx_phy'] is None:
            raise ValueError('Read PHY failed or returned another handle')
        if row['tx_phy'] == row['rx_phy'] == '2M':
            return h
        time.sleep(.1)
    raise ValueError('Actual TX/RX PHY did not reach 2M')
