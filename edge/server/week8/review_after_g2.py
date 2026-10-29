#!/usr/bin/env python3
"""Derive SV1 review files from sealed evidence; never infer, tune, or accept G2."""
import argparse
import csv
import json
import math
import shutil
import statistics
from pathlib import Path
from common import file_sha, hex_logits, save, seal
from summarize import verify
from sv1_log import STAGES, stage_for, sv1_row


def records(folder):
    verify(folder)
    rows = [json.loads(x) for x in (folder/'predictions.jsonl').read_text().splitlines()]
    if len(rows) != 100 or [r['sample_index'] for r in rows] != list(range(100)):
        raise ValueError('Offline requires ordered 100 sample indices')
    for r in rows:
        if hex_logits(r['logits']) != r['logits_hex_le']:
            raise ValueError('Offline FP32 values/hex differ')
    return rows, json.loads((folder/'run.json').read_text())


def stats(values):
    return {'count': len(values), 'min': min(values), 'max': max(values),
            'mean': statistics.mean(values), 'median': statistics.median(values)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('session', 'offline-first', 'offline-second', 'output'):
        ap.add_argument('--'+name, type=Path, required=True)
    a = ap.parse_args()
    verify(a.session)
    raw = [json.loads(x) for x in (a.session/'peer.jsonl').read_text().splitlines()]
    if len(raw) != 212:
        raise ValueError('Need all 212 requests; preserve incomplete evidence separately')
    first, first_run = records(a.offline_first)
    second, second_run = records(a.offline_second)
    session_run = json.loads((a.session/'run.json').read_text())
    for field in ('reference_sha256', 'model_sha256', 'worker_sha256', 'plugins'):
        if first_run[field] != second_run[field]:
            raise ValueError('Offline run identities differ: '+field)
    for field in ('model_sha256', 'worker_sha256', 'plugins'):
        if session_run['backend'][field] != first_run[field]:
            raise ValueError('Radio backend differs from offline: '+field)
    repeat = []
    for old, new in zip(first, second):
        if (old['sample_id'], old['test_index']) != (new['sample_id'], new['test_index']):
            raise ValueError('Offline sample mapping differs')
        repeat.append({'sample_index': old['sample_index'], 'sample_id': old['sample_id'],
                       'bit_exact': old['logits_hex_le'] == new['logits_hex_le'],
                       'label_equal': old['label'] == new['label']})
    derived, timing = [], []
    for i, r in enumerate(raw):
        if r.get('stage') != stage_for(i):
            raise ValueError('Unexpected stage at request '+str(i+1))
        if r.get('logits_float') is None or hex_logits(r['logits_float']) != r['logits_hex_le']:
            raise ValueError('Radio FP32 values/hex differ')
        if not r.get('scale_fp16_sha256'):
            raise ValueError('Missing original FP16 scale hash')
        ms = r.get('tail_ms')
        if not isinstance(ms, (int, float)) or not math.isfinite(ms) or ms < 0:
            raise ValueError('Missing/invalid saved tail_ms; cannot invent timing')
        row = sv1_row(r)
        row.update(request_index_1based=i+1, stage=stage_for(i), tail_us=ms*1000,
                   tail_us_origin='unit conversion of saved native steady_clock tail_ms',
                   cache_hit=bool(r.get('cache_hit')))
        elapsed = None if r.get('t_tx_done_ms') is None else r['t_tx_done_ms']-r['t_rx_ms']
        row['edge_response_ms'] = elapsed
        derived.append(row)
        timing.append({'request_index_1based': i+1, 'stage': stage_for(i),
                       'request_id': r['request_id'], 'rho': r['rho'],
                       'tail_ms': ms, 'tail_us': ms*1000, 'edge_response_ms': elapsed,
                       'cache_hit': bool(r.get('cache_hit'))})
    sequences = [r['sequence'] for r in raw if r['rho'] == 'P1']
    sequence_ok = (len(sequences) == 106 and all(isinstance(x, int) for x in sequences)
                   and all(b > a for a, b in zip(sequences, sequences[1:])))
    mismatches = [r['sample_index'] for r in repeat if not r['bit_exact']]
    summary = {
        'scope': 'DERIVED_REVIEW_NOT_A_NEW_MEASUREMENT_OR_G2_ACCEPTANCE',
        'requests': 212, 'stage_counts': dict(STAGES),
        'all_ok_and_sent': all(r['result'] == 'OK' and r.get('response_sent') for r in raw),
        'cache_hits': sum(bool(r.get('cache_hit')) for r in raw),
        'unique_request_ids': len({r['request_id'] for r in raw}),
        'connections': sorted({r.get('connection') for r in raw}, key=str),
        'p1_monotonic': sequence_ok,
        'p1_first': sequences[0] if sequences else None,
        'p1_last': sequences[-1] if sequences else None,
        'offline_repeat_bit_matches': 100-len(mismatches),
        'offline_repeat_mismatches': mismatches,
        'tail_ms': stats([r['tail_ms'] for r in raw]),
        'edge_response_ms': stats([r['edge_response_ms'] for r in derived
                                   if r['edge_response_ms'] is not None])
                            if any(r['edge_response_ms'] is not None for r in derived) else None,
        'edge_elapsed_shorter_than_tail_requests': [r['request_index_1based'] for r in timing
            if not r['cache_hit'] and r['edge_response_ms'] is not None
            and r['edge_response_ms']+2 < r['tail_ms']],
        'timing_note': 'Allow 2ms for integer timestamp rounding; compare Device clocks/boundaries separately',
        'offline_first_reference_matches': sum(r['class_match'] for r in first),
        'offline_second_reference_matches': sum(r['class_match'] for r in second),
        'acceptance': 'PENDING_DEVICE_LOG_LINK_TIMING_NUMERIC_AND_REGISTRY_REVIEW',
        'sources': {str(f): file_sha(f) for f in
                    (a.session/'sha256sum_results.txt', a.offline_first/'sha256sum_results.txt',
                     a.offline_second/'sha256sum_results.txt')},
    }
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/'requests_212_sv1.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in derived))
    for name, _ in STAGES:
        (a.output/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in derived if r['stage'] == name))
    with (a.output/'timing_212.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, list(timing[0]));writer.writeheader();writer.writerows(timing)
    save(a.output/'summary.json', summary)
    save(a.output/'offline_repeat_comparison.json', repeat)
    shutil.copytree(a.offline_second, a.output/'offline_second')
    (a.output/'DOC_TRUOC.txt').write_text(
        'DERIVED COPY: original session/offline logs unchanged.\n'
        'Rows 1: ONE0P0; 2: ONE0P1; 3..12: PAIRS05; 13..212: PAIRS0100.\n'
        'scale_sha256 hashes FP16 LE; logits are FP32 response numbers.\n'
        'tail_us = saved tail_ms * 1000; no new timing or stronger precision claimed.\n'
        'Native timer: C++ steady_clock, input layout/quantize/copies/execute/wait/output conversion;\n'
        'excludes model loading, BLE, Python parser/unprotect and pipe transport.\n'
        'Root GraphRunner may execute CPU plugins and DPU; this is not DPU-only time.\n'
        't_tx_done_ms marks BlueZ submissions, not an over-the-air ACK.\n'
        'Review Device clock units and measurement boundaries before explaining 3ms vs ~45ms.\n')
    seal(a.output)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
