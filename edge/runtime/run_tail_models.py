#!/usr/bin/env python3
"""Run frozen ECG tails through the native root-GraphRunner binary on KV260.

No model compilation, random input, board configuration or implicit overwrite.
Without an explicitly approved criterion this reports errors, never acceptance.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import resource
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    with path.open('w', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def load_criterion(path):
    if path is None:
        return None
    record = json.loads(path.read_text())
    if (record.get('status') != 'APPROVED' or not record.get('approved_by') or
            not record.get('revision') or record.get('samples_per_split') != 20 or
            record.get('scope') != 'frozen_week3_calibration_reuse' or
            record.get('argmax_tie_break') != 'first_N_S_V_F_Q' or
            record.get('max_abs_error_comparison') not in ('<', '<=')):
        raise ValueError('Criterion is DRAFT/incomplete or has unsupported scope/tie rule')
    for name, low, high in [('max_abs_error', 0, float('inf')),
                            ('minimum_class_agreement', 0, 1)]:
        value = record.get(name)
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid approved criterion field: ' + name)
    return record


def compare(result, reference, count):
    if result.get('execution') != 'root_graph' or result.get('status') != 'FULL_TAIL_EXECUTED_NOT_NUMERICALLY_ACCEPTED':
        raise ValueError('Missing evidence of completed root graph execution')
    rows = result.get('samples', [])
    if len(rows) != count or [r.get('sample_index') for r in rows] != list(range(count)):
        raise ValueError('Missing, duplicate or unordered sample outputs')
    values = []
    for index, row in enumerate(rows):
        logits = np.asarray(row['logits'], dtype=np.float64)
        if row.get('shape') != [1, 5] or logits.shape != (5,) or not np.isfinite(logits).all():
            raise ValueError('Invalid final logits')
        values.append({'sample_index': index,
                       'max_abs_error': float(np.max(np.abs(logits - reference[index]))),
                       'predicted_class': int(np.argmax(logits)),
                       'reference_class': int(np.argmax(reference[index])),
                       'class_match': bool(np.argmax(logits) == np.argmax(reference[index])),
                       'logits': logits.tolist()})
    return values


def accepted(cases, criterion):
    if criterion is None or len(cases) != 20:
        return None
    worst = max(r['max_abs_error'] for r in cases)
    agreement = sum(r['class_match'] for r in cases) / len(cases)
    limit = criterion['max_abs_error']
    error_ok = worst < limit if criterion['max_abs_error_comparison'] == '<' else worst <= limit
    return bool(error_ok and agreement >= criterion['minimum_class_agreement'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy', type=Path, required=True)
    parser.add_argument('--runner', type=Path, required=True)
    select = parser.add_mutually_exclusive_group(required=True)
    select.add_argument('--split', type=int, choices=range(10))
    select.add_argument('--all', action='store_true')
    parser.add_argument('--samples', type=int, choices=range(1, 21), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--criterion', type=Path)
    parser.add_argument('--cpu-op-dir', type=Path, help='App-local conv1d/maxpool1d/relu libraries; no system installation')
    parser.add_argument('--timeout-s', type=int, default=180)
    args = parser.parse_args(argv)
    if platform.machine() != 'aarch64':
        parser.error('Run inference on the KV260 aarch64 board, not the PC/container')
    if args.timeout_s < 1:
        parser.error('timeout-s must be positive')
    if args.output.exists():
        parser.error('Output exists: use a NEW directory, preserve previous evidence')
    criterion = load_criterion(args.criterion)
    cpu_plugins = {}
    runner_env = os.environ.copy()
    if args.cpu_op_dir:
        library_dir = args.cpu_op_dir.resolve()
        for name in ('libvart_op_imp_conv1d.so', 'libvart_op_imp_maxpool1d.so', 'libvart_op_imp_relu.so'):
            path = library_dir / name
            if not path.is_file():
                parser.error('CPU plugin missing: ' + str(path))
            cpu_plugins[name] = {'path': str(path), 'sha256': sha(path)}
        runner_env['LD_LIBRARY_PATH'] = str(library_dir) + (':' + runner_env['LD_LIBRARY_PATH'] if runner_env.get('LD_LIBRARY_PATH') else '')
    if not args.runner.is_file():
        parser.error('Native runner binary is missing; build it first')
    deploy = args.deploy.resolve()
    anchor_file = Path((deploy / 'hash_check_dang_dung.txt').read_text().strip()) / 'verified_anchor.txt'
    if anchor_file.read_text().strip() != sha(deploy / 'sha256sum_bundle.txt'):
        raise ValueError('B3 bundle anchor mismatch')
    check = subprocess.run(['sha256sum', '-c', 'sha256sum_bundle.txt'], cwd=deploy,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check.returncode:
        print(check.stdout)
        raise ValueError('Bundle changed since B3; stop before inference')
    reference = np.load(str(deploy / 'golden/reference_logits.npy'), allow_pickle=False)
    if reference.shape != (20, 5) or reference.dtype != np.float32 or not np.isfinite(reference).all():
        raise ValueError('Invalid frozen reference logits')
    with (deploy / 'reference/samples.csv').open(newline='') as f:
        samples = list(csv.DictReader(f))
    if len(samples) != 20:
        raise ValueError('Expected 20 frozen sample IDs')
    manifest = json.loads((deploy / 'release/provenance/compile_manifest.json').read_text())
    inventory = {r['split']: r for r in manifest['splits']}
    args.output.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    dump(args.output / 'run.json', {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'machine': platform.machine(),
        'deploy': str(deploy), 'runner': str(args.runner.resolve()), 'runner_sha256': sha(args.runner),
        'driver_sha256': sha(Path(__file__)), 'reference_sha256': sha(deploy / 'golden/reference_logits.npy'),
        'samples_csv_sha256': sha(deploy / 'reference/samples.csv'),
        'criterion_sha256': sha(args.criterion) if args.criterion else None,
        'criterion': criterion, 'samples_per_split': args.samples,
        'cpu_plugins': cpu_plugins,
        'scope': 'frozen Week 3 calibration-reuse golden; not independent test accuracy'})
    (args.output / 'bundle_hash_check.txt').write_text(check.stdout)
    preflight = [sys.executable, '-B', str(Path(__file__).with_name('check_cpu_libraries.py')),
                 '--models', str(deploy / 'release/models'), '--output',
                 str((args.output / 'cpu_libraries.json').resolve()), '--splits']
    preflight += [str(s) for s in (range(10) if args.all else [args.split])]
    if args.cpu_op_dir:
        preflight += ['--cpu-op-dir', str(args.cpu_op_dir.resolve())]
    checked = subprocess.run(preflight, env=runner_env, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (args.output / 'cpu_library_preflight.log').write_text(checked.stdout)
    print(checked.stdout, end='', flush=True)
    if checked.returncode:
        dump(args.output / 'status.json', {'status': 'BLOCKED_CPU_LIBRARY_PREFLIGHT',
                                          'full_10_tail_executed': False,
                                          'approved_golden_scope_pass': False})
        print('RESULT_DIR=' + str(args.output.resolve()))
        return 1
    summary = []
    for split in (range(10) if args.all else [args.split]):
        folder = args.output / ('s%d' % split)
        folder.mkdir()
        model = deploy / 'release/models' / ('tail_s%d.xmodel' % split)
        activation = deploy / 'golden' / ('z_s%d.npy' % split)
        row = {'split': split, 'execution': 'FAIL', 'numeric_acceptance': 'NOT_EVALUATED',
               'output': 's%d/logits.json' % split, 'log': 's%d/runner.log' % split}
        try:
            if sha(model) != inventory[split]['xmodel_sha256']:
                raise ValueError('Compiled model/manifest mismatch')
            row.update(model_sha256=sha(model), input_sha256=sha(activation))
            command = [str(args.runner.resolve()), '--model', str(model), '--input', str(activation),
                       '--split', str(split), '--samples', str(args.samples),
                       '--output', str((folder / 'logits.json').resolve())]
            dump(folder / 'command.json', command)
            print('START split=%d samples=%d' % (split, args.samples), flush=True)
            with (folder / 'runner.log').open('w') as log:
                try:
                    code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=runner_env,
                                          timeout=args.timeout_s).returncode
                except subprocess.TimeoutExpired:
                    code = 124
                    log.write('\nTIMEOUT; direct runner process terminated\n')
            row['exit_code'] = code
            if code:
                raise RuntimeError('Runner exit %s; inspect %s' % (code, row['log']))
            result = json.loads((folder / 'logits.json').read_text())
            if result.get('split') != split:
                raise ValueError('Runner split metadata mismatch')
            cases = compare(result, reference, args.samples)
            fields = ['split', 'sample_index', 'sample_id', 'max_abs_error',
                      'predicted_class', 'reference_class', 'class_match', 'logits']
            with (folder / 'comparison.csv').open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for r in cases:
                    writer.writerow(dict(r, split=split, sample_id=samples[r['sample_index']]['sample_id']))
            verdict = accepted(cases, criterion)
            row.update(execution='FULL_TAIL_EXECUTED', samples=len(cases),
                       max_abs_error=max(r['max_abs_error'] for r in cases),
                       class_agreement=sum(r['class_match'] for r in cases) / len(cases),
                       logits_sha256=sha(folder / 'logits.json'),
                       numeric_acceptance='PENDING_CRITERION_OR_SAMPLE_COUNT' if verdict is None else 'PASS' if verdict else 'FAIL')
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            row['error'] = str(error)
        summary.append(row)
        dump(args.output / 'summary.json', summary)
        print('RESULT ' + json.dumps(row), flush=True)
    requested_executed = all(r['execution'] == 'FULL_TAIL_EXECUTED' for r in summary)
    all_executed = len(summary) == 10 and requested_executed
    scope_pass = all_executed and args.samples == 20 and all(r['numeric_acceptance'] == 'PASS' for r in summary)
    dump(args.output / 'status.json', {
        'full_10_tail_executed': all_executed, 'approved_golden_scope_pass': scope_pass,
        'independent_test_accuracy': 'NOT_MEASURED', 'profiling': 'NOT_MEASURED',
        'status': 'APPROVED_GOLDEN_SCOPE_PASS' if scope_pass else
                  'EXECUTION_COMPLETE_ACCEPTANCE_PENDING' if requested_executed else 'PARTIAL_OR_BLOCKED'})
    print('RESULT_DIR=' + str(args.output.resolve()))
    if any(r['execution'] != 'FULL_TAIL_EXECUTED' or r['numeric_acceptance'] == 'FAIL' for r in summary):
        return 1
    return 0 if scope_pass else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print('BLOCKED_INPUT_OR_ENVIRONMENT: ' + str(error), file=sys.stderr)
        sys.exit(1)
