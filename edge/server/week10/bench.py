#!/usr/bin/env python3
"""Run real offline I1 packets through a persistent KV260 model cache.

smoke: selected splits; parity: single-input baseline first, then all 50 P1 packets;
benchmark: fresh P0 requests from authenticated tensors, compared to saved parity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

import numpy as np
from backend import CacheBackend, authenticated_backend
from evidence import PACKAGE_SHA, child, package, save, seal, sha, verify
from service import Receiver, hex_logits, i1


def packet_data(folder, vector, profile):
    packet = child(folder, vector['files']['request']).read_bytes()
    req = i1.parse_request(packet, profile)
    if req.split.split_point != vector['split_point_s']:
        raise ValueError('Vector split mapping differs')
    q = i1.recover_q(req, {profile.key_id: bytes(range(32))})
    if q != child(folder, vector['files']['q']).read_bytes():
        raise ValueError('Recovered q differs from authenticated original')
    return packet, req, q, i1.dequantize(req, q)


def plan(vectors, mode, splits, cycles, warmup):
    if mode == 'parity':
        return [('parity', v) for v in vectors]
    first = {s: next(v for v in vectors if v['split_point_s'] == s) for s in range(11)}
    if mode == 'smoke':
        return [('smoke', first[s]) for s in splits]
    rows = [('first_load', first[s]) for s in range(10)]
    rows += [('warmup', first[s]) for s in range(10) for _ in range(warmup)]
    for _ in range(cycles):
        rows += [('warm_switch', first[s]) for s in range(10)]
        rows += [('warm_switch', first[s]) for s in reversed(range(10))]
    rows += [('same_split', first[s]) for s in range(10) for _ in range(2)]
    rows += [('identity_diagnostic', first[s]) for s in (2, 10, 5)]
    return rows


def rss_kib(pid):
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def single_baseline(a, folder, vectors, profile):
    """Complete all single-input processes before creating the cache worker."""
    baseline = {}
    save(a.output / 'baseline_runner.json', {'sha256': sha(a.single_runner)})
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = str(a.cpu_ops.resolve()) + ':' + env.get('LD_LIBRARY_PATH', '')
    for v in vectors:
        _, req, _, values = packet_data(folder, v, profile)
        s, idx = req.split.split_point, v['vector_index']
        if s == 10:
            logits = values
        else:
            case = a.output / 'single' / f'v{idx:02d}'
            case.mkdir(parents=True)
            tensor = np.asarray(values, dtype='<f4').reshape(
                (1, 32) if s == 9 else (1, req.split.channels, req.split.length))
            np.save(case / 'input.npy', tensor, allow_pickle=False)
            command = [str(a.single_runner.resolve()), '--model',
                       str(a.deploy.resolve() / f'release/models/tail_s{s}.xmodel'),
                       '--input', str((case / 'input.npy').resolve()), '--split', str(s),
                       '--samples', '1', '--output', str((case / 'single.json').resolve())]
            save(case / 'command.json', command)
            with (case / 'single.log').open('x') as log:
                r = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=30)
            (case / 'exit_code.txt').write_text(str(r.returncode) + '\n')
            if r.returncode:
                raise RuntimeError(f'Single-input baseline failed for v{idx}; inspect single.log')
            result = json.loads((case / 'single.json').read_text())
            if result['split'] != s or result['execution'] != 'root_graph' or len(result['samples']) != 1:
                raise ValueError('Wrong baseline runner result')
            logits = result['samples'][0]['logits']
        baseline[str(idx)] = {'split_s': s, 'logits_hex_le': hex_logits(logits)}
    save(a.output / 'baseline.json', baseline)
    return baseline


def run(a):
    if platform.system() != 'Linux' or platform.machine() != 'aarch64':
        raise ValueError('Inference commands require KV260 Linux aarch64')
    session = a.session.resolve()
    verify(session, 'sha256sum_prepare.txt')
    folder = session / 'inputs/packets'
    vectors = package(folder)
    expected_file = session / 'config/backend.json'
    metadata = authenticated_backend(a.worker, a.deploy, a.cpu_ops, expected_file)
    # All hash checks happen before any timing or worker start.
    baseline = None
    if a.mode == 'benchmark':
        if a.baseline is None:
            raise ValueError('Benchmark requires --baseline PARITY_RESULT_DIR')
        verify(a.baseline)
        old_run = json.loads((a.baseline / 'run.json').read_text())
        old_summary = json.loads((a.baseline / 'summary.json').read_text())
        if (old_run['mode'] != 'parity' or old_run['backend'] != metadata or
                old_summary['status'] != 'EXECUTION_COMPLETE_NUMERIC_REVIEW_PENDING' or
                old_summary.get('parity_mismatches') != 0 or old_summary['rows'] != 50):
            raise ValueError('Need complete bit-exact parity of the same model/worker/plugins')
        baseline = json.loads((a.baseline / 'baseline.json').read_text())
    profile = i1.load_profile(session / 'source/contracts/sv3_week5_approved_registry_v2.json')
    execution_plan = plan(vectors, a.mode, a.splits, a.cycles, a.warmup)
    a.output.mkdir(parents=True, exist_ok=False)
    run_id = a.output.name + '-' + uuid.uuid4().hex[:12]
    save(a.output / 'plan.json', [{'phase': ph, 'vector_index': v['vector_index'],
                                 'split_s': v['split_point_s']} for ph, v in execution_plan])
    save(a.output / 'run.json', {
        'run_id': run_id, 'mode': a.mode, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'OFFLINE_I1_KV260_ROOT_CPU_DPU; not BLE or independent test accuracy',
        'packet_mode': 'P1 original vectors' if a.mode == 'parity' else 'fresh P0 from authenticated original q/scales',
        'backend': metadata, 'packet_manifest_sha256': PACKAGE_SHA,
        'preparation_inventory_sha256': sha(session / 'sha256sum_prepare.txt'),
        'plan_sha256': sha(a.output / 'plan.json'),
        'source_files': {p.name: sha(p) for p in Path(__file__).parent.glob('*.py')},
        'clock': 'durations on BOARD_MONOTONIC; native durations on steady_clock',
        'switch_scope': 'Python before SELECT transaction to native selected acknowledgement; includes IPC',
        'tail_scope': 'native layout/quantize/copy/sync/root execute/read, excludes SELECT',
        'service_scope': 'entry to receiver.handle until response encoded, not BLE TX',
        'cycles': a.cycles, 'warmup_per_split': a.warmup,
        'smoke_splits': a.splits,
        'numeric_acceptance': 'SEPARATE_TEAM_REVIEW',
        'baseline_inventory_sha256': None if a.baseline is None else sha(a.baseline / 'sha256sum_results.txt'),
        'host': {'uname': list(platform.uname()), 'python': sys.version},
    })
    worker = None
    rows, mismatch, error = 0, 0, None
    try:
        if a.mode == 'parity':
            if a.single_runner is None:
                raise ValueError('Parity requires --single-runner')
            baseline = single_baseline(a, folder, vectors, profile)
        worker = CacheBackend(a.worker, a.deploy, a.cpu_ops, expected_file, a.output / 'worker.log')
        receiver = Receiver(worker, bytes(range(32)))  # public offline vectors only
        print('CACHE_RUN_READY', run_id, 'pid=' + str(worker.transport.process.pid), flush=True)
        with (a.output / 'requests.jsonl').open('x') as raw:
            for index, (phase, v) in enumerate(execution_plan):
                original, req, q, _ = packet_data(folder, v, profile)
                packet = original if a.mode == 'parity' else i1.encode_request(
                    index + 1, req.model_profile_id, req.split.split_id,
                    req.split.channels, req.split.length, req.scales, q)
                response, row = receiver.handle('OFFLINE_PUBLIC_TEST_ONLY', packet, time.monotonic_ns() / 1e6)
                row.update(run_id=run_id, index=index, phase=phase, vector_index=v['vector_index'],
                           input_id=v['sample_id'], source_packet_sha256=sha(child(folder, v['files']['request'])),
                           model_sha256=metadata['models'].get(str(req.split.split_point)),
                           native_rss_KiB=rss_kib(worker.transport.process.pid),
                           response_hex=None if response is None else response.hex())
                expected = None if baseline is None else baseline.get(str(v['vector_index']))
                row['baseline_bit_exact'] = None if expected is None else row['logits_hex_le'] == expected['logits_hex_le']
                if row['baseline_bit_exact'] is False:
                    mismatch += 1
                raw.write(json.dumps(row, allow_nan=False) + '\n')
                raw.flush()
                rows += 1
                if rows % 50 == 0:
                    print('PROGRESS', rows, '/', len(execution_plan), flush=True)
                if row['result'] != 'OK' or row['response_cache_hit'] or row['baseline_bit_exact'] is False:
                    raise ValueError('Request failed/retried/parity differs; preserve raw and inspect')
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if worker is not None:
            worker.close()
            if error is None and worker.transport.process.returncode != 0:
                error = 'Native shutdown returned nonzero'
        save(a.output / 'summary.json', {
            'status': 'INCOMPLETE' if error else 'EXECUTION_COMPLETE_NUMERIC_REVIEW_PENDING',
            'run_id': run_id, 'rows': rows, 'planned': len(execution_plan),
            'parity_mismatches': mismatch, 'error': error,
            'acceptance': 'NOT_AUTOMATICALLY_ACCEPTED',
        })
        seal(a.output)
    if error:
        raise RuntimeError(error)
    print('CACHE_RUN_SAVED_REVIEW_REQUIRED', a.output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('smoke', 'parity', 'benchmark'), required=True)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--worker', type=Path, required=True)
    p.add_argument('--deploy', type=Path, required=True)
    p.add_argument('--cpu-ops', type=Path, required=True)
    p.add_argument('--single-runner', type=Path)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--splits', type=lambda s: [int(x) for x in s.split(',')], default=[9, 2, 5, 2, 10])
    p.add_argument('--cycles', type=int, default=100)
    p.add_argument('--warmup', type=int, default=20)
    a = p.parse_args()
    if not a.splits or any(s not in range(11) for s in a.splits) or not 1 <= a.cycles <= 1000 or not 20 <= a.warmup <= 1000:
        p.error('splits 0..10, cycles 1..1000, warmup 20..1000 required')
    run(a)


if __name__ == '__main__':
    main()
