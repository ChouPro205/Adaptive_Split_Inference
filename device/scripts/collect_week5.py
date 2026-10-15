"""LATER DEVICE STEP ONLY. Explicit port, streaming validation, no overwrite."""
import argparse
import datetime
from pathlib import Path
import re
import time
import numpy as np
from week5_common import ROOT, PACKAGE, authenticate, firmware_binding, write_json, sha, need
from week5_capture import CaptureParser, sequence

def collect(transport, sink, parser, timeout=600):
    def until(predicate):
        deadline = time.monotonic() + timeout
        while not predicate():
            need(time.monotonic() < deadline, 'Timed out; partial capture retained')
            chunk = transport.read(4096)
            if chunk:
                sink.write(chunk)
                sink.flush()
                parser.feed(chunk)
    until(lambda: parser.state == 'begin')
    for i, (n, s) in enumerate(parser.expected):
        command = f'RUN {n} {s}\n'.encode('ascii')
        need(transport.write(command) == len(command), 'Serial command write incomplete')
        until(lambda: parser.case_index == i+1)
        need(parser.state == 'begin' and not parser.pending, 'Unsolicited data before next command')
        print(f'CAPTURED {i+1}/{len(parser.expected)} RUN {n} {s}', flush=True)
    # Drain and reject unexpected trailing/reset data before closing the port.
    extra = transport.read(4096)
    if extra:
        sink.write(extra); sink.flush(); parser.feed(extra)
    return parser.finish()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--preparation', type=Path, required=True)
    p.add_argument('--timeout', type=float, default=600)
    a = p.parse_args()
    need(re.fullmatch(r'COM[0-9]+', a.port, re.I) and a.timeout > 0, 'Specify actual application COM port/positive timeout')
    receipt = a.capture.with_suffix('.receipt.json')
    need(not any(p.exists() for p in (a.capture, a.report, receipt)), 'Choose new capture/report names')
    from verify_week5_package import verify_package
    preparation = verify_package(a.preparation)
    manifest, proof, _ = authenticate()
    binding = firmware_binding()
    need(binding == preparation['firmware_binding'], 'Firmware/source identity differs from preparation')
    goldens = [np.load(ROOT / PACKAGE / f'golden/z_s{s}.npy', allow_pickle=False) for s in range(11)]
    parser = CaptureParser(binding, manifest, goldens)
    # pyserial is imported only in the explicitly requested later device stage.
    import serial
    a.capture.parent.mkdir(parents=True, exist_ok=True)
    with serial.Serial(port=None, baudrate=115200, timeout=.2, write_timeout=10) as port:
        port.port = a.port
        port.dtr = True; port.rts = True
        port.open()
        with a.capture.open('xb') as sink:
            result = collect(port, sink, parser, a.timeout)
    write_json(receipt, {'origin':'REAL_MCU_CAPTURE', 'port':a.port, 'firmware_id':binding['firmware_id'],
        'capture_sha256':sha(a.capture), 'commands_completed':len(sequence()),
        'collected_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'preparation_sha256':sha(a.preparation)})
    result.update(capture=str(a.capture.resolve()), capture_sha256=sha(a.capture), handoff_authentication=proof,
                  collection_receipt=str(receipt.resolve()), firmware_binding=binding)
    write_json(a.report, result)
    print(f'MCU validation: PASS; timing/stack PENDING; report={a.report}')

if __name__ == '__main__':
    main()
