"""Set and verify active 2M before CCCD; reuse the reviewed Week8 HCI parser."""
import json
import subprocess
import time
from pathlib import Path

def verify(adapter, peer, output):
    from supplemental_link import handle_for, phy_args, command_status
    path = Path(output) / 'phy_gate.jsonl'
    def record(kind, **values):
        with path.open('a') as f:
            f.write(json.dumps(dict(event=kind, unix_ns=time.time_ns(),
                                    monotonic_ns=time.monotonic_ns(), **values))+'\n')
    def call(args):
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        record('command', argv=args, rc=r.returncode, stdout=r.stdout, stderr=r.stderr)
        r.check_returncode()
        return r.stdout
    def handle():
        return handle_for(call(['hcitool', '-i', adapter, 'con']), peer)
    h = handle()
    text = call(['hcitool', '-i', adapter, 'cmd', *phy_args(h, 'set-2m')])
    if command_status(text, 0x2032)[0]:
        raise ValueError('Set PHY rejected; no notification subscription')
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        if handle() != h:
            raise ValueError('Connection changed during PHY gate')
        text = call(['hcitool', '-i', adapter, 'cmd', *phy_args(h, 'read')])
        status, payload = command_status(text, 0x2030)
        if status:
            raise ValueError('Read PHY rejected')
        if len(payload) != 4 or int.from_bytes(payload[:2], 'little') != h:
            raise ValueError('Read PHY handle/payload mismatch')
        if payload[2:] == b'\x02\x02':
            record('PHY_GATE_OK', peer=peer, handle=h, tx='2M', rx='2M')
            return
        time.sleep(.1)
    raise ValueError('Actual TX/RX did not reach 2M; preserve failed run')
