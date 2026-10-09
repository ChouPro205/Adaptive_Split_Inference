"""Offline checker; simulated fixtures can never establish MCU PASS."""
import argparse
import json
from pathlib import Path
import numpy as np
from week5_common import ROOT, PACKAGE, authenticate, firmware_binding, sha, need, write_json
from week5_capture import CaptureParser

def check(capture, report, simulated=False, collection_receipt=None):
    manifest, proof, history = authenticate()
    binding = firmware_binding()
    if not simulated:
        need(collection_receipt is not None, 'Real MCU checks require a collector receipt')
        receipt = json.loads(Path(collection_receipt).read_text(encoding='utf-8'))
        need(receipt['origin'] == 'REAL_MCU_CAPTURE' and receipt['firmware_id'] == binding['firmware_id'] and
             receipt['capture_sha256'] == sha(capture) and receipt['commands_completed'] == 236 and receipt['port'], 'Invalid collection receipt')
    goldens = [np.load(ROOT / PACKAGE / f'golden/z_s{s}.npy', allow_pickle=False) for s in range(11)]
    parser = CaptureParser(binding, manifest, goldens, simulated)
    with Path(capture).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1379), b''):
            parser.feed(chunk)
    result = parser.finish()
    result.update(capture=str(Path(capture).resolve()), capture_sha256=sha(capture), firmware_binding=binding,
                  handoff_authentication=proof, accepted_r3_provenance=history)
    need(not Path(report).exists(), 'Refuse overwriting acceptance report')
    write_json(report, result)
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--simulated', action='store_true')
    p.add_argument('--collection-receipt', type=Path)
    a = p.parse_args()
    r = check(a.capture, a.report, a.simulated, a.collection_receipt)
    print(f'{r["scope"]}: PASS; MCU={r["mcu_validation"]}')
