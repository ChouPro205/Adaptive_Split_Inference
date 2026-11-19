#!/usr/bin/env python3
"""Verify sealed Week 10 offline runs and summarize warm model switches."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from evidence import save, seal, sha, verify


def stats(values):
    values = sorted(values)
    if not values:
        return {'count': 0, 'mean_ms': None, 'std_ms': None, 'p95_ms': None, 'max_ms': None, 'at_or_above_50_count': 0}
    return {'count': len(values), 'mean_ms': statistics.mean(values),
            'std_ms': statistics.stdev(values) if len(values) > 1 else None,
            'p95_ms': values[max(0, math.ceil(.95 * len(values)) - 1)],
            'max_ms': values[-1], 'at_or_above_50_count': sum(x >= 50 for x in values)}


def read_run(folder):
    folder = Path(folder).resolve()
    listed = verify(folder)
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*')
              if p.is_file() and p.name != 'sha256sum_results.txt'}
    if actual != listed:
        raise ValueError('Result inventory contains missing/extra files')
    run = json.loads((folder / 'run.json').read_text())
    summary = json.loads((folder / 'summary.json').read_text())
    plan = json.loads((folder / 'plan.json').read_text())
    if sha(folder / 'plan.json') != run['plan_sha256']:
        raise ValueError('Plan hash differs from run')
    rows = [json.loads(line) for line in (folder / 'requests.jsonl').read_text().splitlines()]
    if len(rows) != summary['rows'] or len(plan) != summary['planned']:
        raise ValueError('Counts differ from summary/plan')
    if summary['run_id'] != run['run_id']:
        raise ValueError('Run identity differs')
    previous_s, contexts, pids = None, {}, set()
    for i, row in enumerate(rows):
        if (row['run_id'] != run['run_id'] or row['index'] != i or
                (row['phase'], row['vector_index'], row['split_s']) !=
                (plan[i]['phase'], plan[i]['vector_index'], plan[i]['split_s'])):
            raise ValueError('Raw mapping differs from plan')
        if row['result'] != 'OK':
            continue  # Preserve failed/incomplete rows; never treat them as successful timing.
        s = row['split_s']
        if row['previous_s'] != previous_s or row['response_cache_hit']:
            raise ValueError('Previous split or response-cache counter invalid')
        for field in ('switch_ms', 'native_select_ms', 'service_ms'):
            v = row.get(field)
            if not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0:
                raise ValueError('Invalid timing: ' + field)
        if s < 10:
            if row['model_sha256'] != run['backend']['models'][str(s)]:
                raise ValueError('Wrong model identity')
            hit = s in contexts
            if row['model_cache_hit'] is not hit or row['load_count'] != 1 or row['context_id'] != s + 1:
                raise ValueError('Cache reuse invalid')
            contexts[s] = row['context_id']
            if row.get('tail_ms') is None or not math.isfinite(row['tail_ms']) or row['tail_ms'] < 0:
                raise ValueError('Missing native tail duration')
        elif row['context_id'] is not None or row['load_count'] != 0 or row['tail_ms'] is not None:
            raise ValueError('s10 must not execute a tail model')
        if row['contexts_count'] != len(contexts):
            raise ValueError('Contexts count invalid')
        pids.add(row['worker_pid'])
        previous_s = s
    if len(pids) > 1:
        raise ValueError('Worker restarted within run')
    complete = (summary['status'] == 'EXECUTION_COMPLETE_NUMERIC_REVIEW_PENDING' and
                summary['error'] is None and len(rows) == len(plan) and
                all(r['result'] == 'OK' for r in rows))
    actual_mismatches = sum(r.get('baseline_bit_exact') is False for r in rows)
    if actual_mismatches != summary['parity_mismatches']:
        raise ValueError('Parity count differs from raw')
    if complete and run['mode'] == 'parity':
        if len(rows) != 50 or [r['vector_index'] for r in rows] != list(range(50)):
            raise ValueError('Parity must cover all 50 original vectors in source order')
    if complete and run['mode'] == 'benchmark':
        warmup = run['warmup_per_split']
        expected_length = 10 + 10 * warmup + 20 * run['cycles'] + 20 + 3
        if len(rows) != expected_length or warmup < 20:
            raise ValueError('Benchmark phase coverage differs from declared configuration')
        phases = ([('first_load', s) for s in range(10)] +
                  [('warmup', s) for s in range(10) for _ in range(warmup)])
        for _ in range(run['cycles']):
            phases.extend(('warm_switch', s) for s in range(10))
            phases.extend(('warm_switch', s) for s in reversed(range(10)))
        phases.extend(('same_split', s) for s in range(10) for _ in range(2))
        phases.extend(('identity_diagnostic', s) for s in (2, 10, 5))
        if [(r['phase'], r['split_s']) for r in rows] != phases:
            raise ValueError('Benchmark phases/order do not match the declared plan')
    return run, summary, rows, complete


def analyze(folder, output):
    run, summary, rows, complete = read_run(folder)
    groups = {}
    first = {}
    for r in rows:
        if r['result'] != 'OK':
            continue
        if r['phase'] == 'first_load':
            first[str(r['split_s'])] = {k: r.get(k) for k in ('load_ms', 'switch_ms', 'tail_ms', 'native_rss_KiB')}
        if (r['phase'] == 'warm_switch' and r['split_s'] < 10 and
                r['previous_s'] != r['split_s'] and r['model_cache_hit'] and not r['response_cache_hit']):
            groups.setdefault(f"{r['previous_s']}->{r['split_s']}", []).append(r['switch_ms'])
    by_pair = {k: stats(v) for k, v in sorted(groups.items())}
    warm = [x for v in groups.values() for x in v]
    warm_stats = stats(warm)
    all_native = {r['split_s'] for r in rows if r['result'] == 'OK' and r['split_s'] < 10}
    eligible = (complete and run['mode'] == 'benchmark' and all_native == set(range(10)) and
                run['warmup_per_split'] >= 20 and len(first) == 10 and bool(warm) and
                all(r.get('baseline_bit_exact') is True for r in rows))
    gate = 'NOT_EVALUATED'
    if eligible:
        gate = 'ALL_OBSERVED_WARM_SWITCHES_LT_50_MS' if warm_stats['max_ms'] < 50 else 'OBSERVED_WARM_SWITCH_GE_50_MS'
    result = {
        'run_id': run['run_id'], 'mode': run['mode'], 'execution_complete': complete,
        'rows': len(rows), 'native_splits': sorted(all_native),
        'first_load_by_split': first, 'warm_switch': warm_stats, 'warm_switch_by_pair': by_pair,
        'ordered_pairs_observed': len(by_pair), 'all_possible_native_ordered_pairs': 90,
        'timing_observation': gate, 'project_acceptance': 'PENDING_REVIEW_OF_SCOPE_AND_CRITERION',
        'parity_mismatches': summary['parity_mismatches'],
        'source_inventory_sha256': sha(Path(folder) / 'sha256sum_results.txt'),
        'scope': run['scope'], 'switch_scope': run['switch_scope'],
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'summary.json', result)
    fields = ('index', 'phase', 'previous_s', 'split_s', 'switch_ms', 'native_select_ms', 'load_ms',
              'tail_ms', 'service_ms', 'model_cache_hit', 'response_cache_hit', 'load_count',
              'contexts_count', 'native_rss_KiB', 'baseline_bit_exact', 'result')
    with (output / 'timing.csv').open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: r.get(k) for k in fields} for r in rows)
    seal(output)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(analyze(a.run, a.output), indent=2))


if __name__ == '__main__':
    main()
