#!/usr/bin/env python3
"""Week 6 runbook helper. Board timing, immutable Week 5 inputs, new output only."""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LOAD = ('deserialize_ms', 'create_runner_ms', 'tensor_setup_ms', 'model_load_ms')
TIMED = ('prepare_ms', 'input_sync_ms', 'execute_wait_ms', 'output_read_ms', 'tail_total_ms')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def stats(values):
    xs = sorted(float(x) for x in values)
    if not xs or any(not math.isfinite(x) or x < 0 for x in xs):
        raise ValueError('Missing/negative/nonfinite measurement')
    n = len(xs)
    mean = statistics.mean(xs)
    std = statistics.stdev(xs) if n > 1 else None
    p = (n - 1) * .95
    p95 = xs[int(p)] + (p - int(p)) * (xs[min(int(p) + 1, n - 1)] - xs[int(p)])
    # Conservative Student-t interval: choose the nearest available LOWER df.
    table = {1: 12.706205, 2: 4.302653, 3: 3.182447, 4: 2.776445,
             5: 2.570582, 9: 2.262158, 19: 2.093025, 29: 2.045230, 30: 2.042273}
    df = max(k for k in table if k <= n - 1) if n > 1 else None
    half = table[df] * std / math.sqrt(n) if df else None
    return dict(n=n, mean_ms=mean, std_ms=std, min_ms=xs[0], max_ms=xs[-1],
                median_ms=statistics.median(xs), p95_ms=p95,
                ci95_mean_ms=[mean - half, mean + half] if half is not None else None,
                ci_method='conservative Student-t, assumes independent observations', ci_df=df)


def validate(record, split, warmup, repeats):
    if (record.get('execution') != 'root_graph' or record.get('split') != split or
            record.get('clock') != 'std::chrono::steady_clock' or
            record.get('warmup') != warmup or record.get('repeats') != repeats or
            record.get('status') != 'PROFILE_EXECUTED_NUMERIC_ACCEPTANCE_SEPARATE' or
            record.get('output_tensor', {}).get('shape') != [1, 5]):
        raise ValueError('Incomplete/wrong graph, clock, shape or run configuration')
    rows = record.get('measurements', [])
    if len(rows) != repeats or [r['sample_index'] for r in rows] != [i % 20 for i in range(repeats)]:
        raise ValueError('Missing/duplicate/reordered measured iterations')
    for k in LOAD:
        stats([record[k]])
    parts = sum(record[k] for k in LOAD[:3])
    if not math.isclose(parts, record['model_load_ms'], rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError('Model load timing parts do not add up')
    for r in [record['first_inference']] + rows:
        for k in TIMED:
            stats([r[k]])
        if (not 0 <= r['sample_index'] < 20 or len(r['logits']) != 5 or
                any(not math.isfinite(x) for x in r['logits'])):
            raise ValueError('Invalid final logits')
        if not math.isclose(sum(r[k] for k in TIMED[:4]), r['tail_total_ms'], rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError('Tail timing parts do not add up')
    return rows


def inventory(root):
    items = sorted(p for p in root.rglob('*') if p.is_file() and p.name != 'sha256sum_results.txt')
    (root / 'sha256sum_results.txt').write_text(''.join(sha(p) + '  ' + p.relative_to(root).as_posix() + '\n' for p in items))


def environment():
    # No env dump: avoid tokens/passwords. Read only known public system metadata.
    data = {'machine': platform.machine(), 'platform': platform.platform(), 'python': sys.version}
    if hasattr(os, 'sched_getaffinity'):
        data['process_cpu_affinity'] = sorted(os.sched_getaffinity(0))
    for name in ('/etc/os-release', '/proc/loadavg', '/proc/meminfo'):
        p = Path(name)
        if p.is_file():
            data[name] = p.read_text()
    for pattern in ('/sys/class/thermal/thermal_zone*/temp',
                    '/sys/class/thermal/thermal_zone*/type',
                    '/sys/devices/system/cpu/cpufreq/policy*/scaling_governor',
                    '/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq'):
        for p in Path('/').glob(pattern.lstrip('/')):
            try:
                data[str(p)] = p.read_text().strip()
            except OSError as e:
                data[str(p)] = str(e)
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deploy', type=Path, required=True)
    ap.add_argument('--runner', type=Path, required=True)
    ap.add_argument('--cpu-op-dir', type=Path, required=True)
    ap.add_argument('--week5-results', type=Path, required=True, help='Original on-board completed 200-case run')
    select = ap.add_mutually_exclusive_group(required=True)
    select.add_argument('--all', action='store_true')
    select.add_argument('--split', type=int, choices=range(10))
    ap.add_argument('--loads', type=int, default=5)
    ap.add_argument('--warmup', type=int, default=20)
    ap.add_argument('--repeats', type=int, default=100)
    ap.add_argument('--timeout-s', type=int, default=1800, help='Per child process, not latency threshold')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(argv)
    if platform.machine() != 'aarch64':
        ap.error('Run on KV260 aarch64. PC cannot provide board timings.')
    if not (1 <= a.loads <= 100 and 0 <= a.warmup <= 100000 and 1 <= a.repeats <= 100000 and a.timeout_s > 0):
        ap.error('Invalid load/warmup/repeats/timeout')
    if a.output.exists():
        ap.error('Output exists: choose a new directory')
    import numpy as np
    deploy = a.deploy.resolve()
    anchor = Path((deploy / 'hash_check_dang_dung.txt').read_text().strip()) / 'verified_anchor.txt'
    if anchor.read_text().strip() != sha(deploy / 'sha256sum_bundle.txt'):
        raise ValueError('Bundle differs from independently verified Week 5 anchor')
    check = subprocess.run(['sha256sum', '-c', 'sha256sum_bundle.txt'], cwd=deploy, capture_output=True, text=True)
    if check.returncode:
        raise ValueError('Bundle checksum FAIL: ' + check.stdout + check.stderr)
    old = a.week5_results.resolve()
    oldcheck = subprocess.run(['sha256sum', '-c', 'sha256sum_results.txt'], cwd=old, capture_output=True, text=True)
    if oldcheck.returncode:
        raise ValueError('Week 5 checksum FAIL')
    status = json.loads((old / 'status.json').read_text())
    summary = json.loads((old / 'summary.json').read_text())
    if (not status.get('full_10_tail_executed') or len(summary) != 10 or
            sorted(r['split'] for r in summary) != list(range(10)) or
            any(r['execution'] != 'FULL_TAIL_EXECUTED' or r['samples'] != 20 for r in summary)):
        raise ValueError('Missing completed Week 5 200-case execution')
    previous = json.loads((old / 'run.json').read_text())
    if Path(previous['deploy']).resolve() != deploy:
        raise ValueError('Week 5 run used a different deploy')
    manifest = json.loads((deploy / 'release/provenance/compile_manifest.json').read_text())
    models = {r['split']: r for r in manifest['splits']}
    reference = np.load(str(deploy / 'golden/reference_logits.npy'), allow_pickle=False)
    if reference.shape != (20, 5) or reference.dtype != np.float32 or not np.isfinite(reference).all():
        raise ValueError('Invalid frozen reference logits')
    runner_env = os.environ.copy()
    plugins = {}
    for name in ('libvart_op_imp_conv1d.so', 'libvart_op_imp_maxpool1d.so', 'libvart_op_imp_relu.so'):
        p = a.cpu_op_dir.resolve() / name
        digest = sha(p)
        if previous['cpu_plugins'][name]['sha256'] != digest:
            raise ValueError('CPU plugin differs from Week 5 execution: ' + name)
        plugins[name] = {'path': str(p), 'sha256': digest}
    runner_env['LD_LIBRARY_PATH'] = str(a.cpu_op_dir.resolve()) + (':' + runner_env['LD_LIBRARY_PATH'] if runner_env.get('LD_LIBRARY_PATH') else '')
    a.output.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    profile = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
               'scope': 'KV260 root graph CPU+PS+DPU, fixed batch 1; calibration-reuse inputs',
               'units': 'ms', 'load_scope': 'fresh process reload; OS filesystem cache uncontrolled',
               'configuration': dict(loads=a.loads, warmup=a.warmup, repeats=a.repeats, timeout_s=a.timeout_s),
               'week5_status': status, 'week5_results': str(old), 'deploy': str(deploy),
               'week5_status_sha256': sha(old / 'status.json'),
               'bundle_inventory_sha256': sha(deploy / 'sha256sum_bundle.txt'),
               'runner_sha256': sha(a.runner), 'driver_sha256': sha(Path(__file__)),
               'source_hashes': {p.name: sha(p) for p in Path(__file__).parent.iterdir()
                                 if p.is_file() and p.suffix in ('.py', '.cpp', '.hpp', '.sh')},
               'cpu_plugins': plugins, 'environment_before': environment(), 'splits': []}
    dump(a.output / 'run.json', profile)
    (a.output / 'bundle_hash_check.txt').write_text(check.stdout)
    (a.output / 'week5_hash_check.txt').write_text(oldcheck.stdout)
    splits = list(range(10)) if a.all else [a.split]
    pre = [sys.executable, '-B', str(Path(__file__).with_name('check_cpu_libraries.py')),
           '--models', str(deploy / 'release/models'), '--cpu-op-dir', str(a.cpu_op_dir.resolve()),
           '--output', str((a.output / 'cpu_libraries.json').resolve()), '--splits'] + [str(s) for s in splits]
    with (a.output / 'cpu_preflight.log').open('x') as f:
        precode = subprocess.run(pre, env=runner_env, stdout=f, stderr=subprocess.STDOUT).returncode
    for s in splits:
        row = {'split': s, 'status': 'FAILED', 'runs': []}
        folder = a.output / ('s%d' % s)
        folder.mkdir()
        try:
            if precode:
                raise ValueError('CPU library preflight failed; inspect cpu_preflight.log')
            model = deploy / 'release/models' / ('tail_s%d.xmodel' % s)
            source = deploy / 'golden' / ('z_s%d.npy' % s)
            if sha(model) != models[s]['xmodel_sha256']:
                raise ValueError('Model/manifest mismatch')
            prior = json.loads((old / ('s%d/logits.json' % s)).read_text())
            prior_cases = prior['samples']
            if (prior.get('split') != s or len(prior_cases) != 20 or
                    [r['sample_index'] for r in prior_cases] != list(range(20))):
                raise ValueError('Incomplete Week 5 sample outputs')
            baseline = np.asarray([r['logits'] for r in prior_cases], dtype=np.float32)
            if baseline.shape != (20, 5) or not np.isfinite(baseline).all():
                raise ValueError('Invalid Week 5 baseline')
            row.update(model_sha256=sha(model), input_sha256=sha(source))
            if (row['model_sha256'] != next(r['model_sha256'] for r in summary if r['split'] == s) or
                    row['input_sha256'] != next(r['input_sha256'] for r in summary if r['split'] == s)):
                raise ValueError('Model/input differs from Week 5 execution')
            records, worst = [], 0.0
            all_loads = []
            for load in range(a.loads):
                output = (folder / ('load_%d.json' % (load + 1))).resolve()
                cmd = [str(a.runner.resolve()), '--model', str(model), '--input', str(source),
                       '--split', str(s), '--warmup', str(a.warmup), '--repeats', str(a.repeats), '--output', str(output)]
                dump(folder / ('load_%d.command.json' % (load + 1)), cmd)
                print('PROFILE split=%d load=%d/%d' % (s, load + 1, a.loads), flush=True)
                with (folder / ('load_%d.log' % (load + 1))).open('x') as f:
                    try:
                        code = subprocess.run(cmd, env=runner_env, stdout=f, stderr=subprocess.STDOUT, timeout=a.timeout_s).returncode
                    except subprocess.TimeoutExpired:
                        code = 124
                row['runs'].append({'file': str(output.relative_to(a.output.resolve())), 'exit_code': code})
                if code:
                    raise ValueError('Profiler child failed: %s' % code)
                data = json.loads(output.read_text())
                measured = validate(data, s, a.warmup, a.repeats)
                for r in [data['first_inference']] + measured:
                    values = np.asarray(r['logits'], dtype=np.float32)
                    # Exact regression against the previously executed binary on this board.
                    if not np.array_equal(values.view(np.uint32), baseline[r['sample_index']].view(np.uint32)):
                        raise ValueError('Logits differ from Week 5 runtime; investigate before profiling acceptance')
                    worst = max(worst, float(np.max(np.abs(values.astype(np.float64) - reference[r['sample_index']]))))
                records.extend(measured)
                all_loads.append(data)
            with (folder / 'measurements.csv').open('x', newline='') as f:
                fields = ['sample_index'] + list(TIMED) + ['logits']
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for r in records:
                    w.writerow(r)
            row.update(status='PROFILE_EXECUTED', loading={k: stats([d[k] for d in all_loads]) for k in LOAD},
                       first_inference={k: stats([d['first_inference'][k] for d in all_loads]) for k in TIMED},
                       steady={k: stats([r[k] for r in records]) for k in TIMED},
                       steady_run_means={k: stats([statistics.mean(r[k] for r in d['measurements']) for d in all_loads]) for k in TIMED},
                       regression_vs_week5='BIT_EXACT', max_abs_error_vs_fp32=worst,
                       sequential_rate_hz=1000 / statistics.mean(r['tail_total_ms'] for r in records))
        except (OSError, ValueError, KeyError, TypeError, StopIteration, ZeroDivisionError) as e:
            row['error'] = str(e)
        profile['splits'].append(row)
    complete = len(profile['splits']) == 10 and all(r['status'] == 'PROFILE_EXECUTED' for r in profile['splits'])
    profile.update(environment_after=environment(), full_10_tail_profiled=complete,
                   status='PROFILE_EXECUTION_COMPLETE_REVIEW_PENDING' if complete else 'SMOKE_OR_PARTIAL',
                   numeric_acceptance='SEPARATE_SEE_WEEK5_STATUS_AND_TEAM_DECISION', independent_test_accuracy='NOT_MEASURED',
                   dpu_only_timing='NOT_MEASURED', s10={'status': 'NOT_APPLICABLE_EMPTY_TAIL', 'latency_ms': None})
    dump(a.output / 'profile_edge.json', profile)
    dump(a.output / 'status.json', {k: profile[k] for k in ('status', 'full_10_tail_profiled', 'numeric_acceptance')})
    inventory(a.output)
    print('PROFILE_DIR=' + str(a.output.resolve()))
    return 0 if all(r['status'] == 'PROFILE_EXECUTED' for r in profile['splits']) else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, ImportError) as e:
        print('PROFILE_BLOCKED: ' + str(e), file=sys.stderr)
        sys.exit(1)
