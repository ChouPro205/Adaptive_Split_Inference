#!/usr/bin/env python3
"""Offline SV2 batch build and XIR inspection; never executes a KV260 model.

Run inside the Vitis AI 2.5 pytorch environment. Each invocation needs a fresh
output directory. Source packages and previous builds are never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import runpy
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = Path('/opt/vitis_ai/compiler/arch/DPUCZDX8G/KV260/arch.json')
PACKAGE = ROOT / 'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def run_stage(command, log, cwd=ROOT):
    """Keep return code even on process startup failure; do not stop other splits."""
    with log.open('w', encoding='utf-8') as out:
        out.write('COMMAND ' + json.dumps([str(x) for x in command]) + '\n')
        out.flush()
        try:
            code = subprocess.run([str(x) for x in command], cwd=str(cwd),
                                  stdout=out, stderr=subprocess.STDOUT).returncode
        except OSError as error:
            out.write(repr(error) + '\n')
            code = 127
        out.write('\nEXIT_CODE=%d\n' % code)
    return code


def inspect_model(path, xir):
    graph = xir.Graph.deserialize(str(path))
    partitions = []

    def visit(node):
        partitions.append({'name': node.get_name(),
                           'device': str(node.get_attr('device')) if node.has_attr('device') else None})
        for child in node.toposort_child_subgraph():
            visit(child)

    visit(graph.get_root_subgraph())
    devices = {p['device'] for p in partitions}
    classification = ('HAS_DPU_AND_CPU' if 'DPU' in devices and 'CPU' in devices else
                      'DPU_PRESENT_REVIEW_OTHER_NODES' if 'DPU' in devices else 'NO_DPU_DETECTED')
    return {'graph': graph.get_name(), 'partitions': partitions,
            'operator_types': sorted({op.get_type() for op in graph.get_ops()}),
            'classification': classification, 'sha256': sha(path),
            'runtime': 'NOT_TESTED_NO_BOARD'}


def save_summary(output, rows):
    write_json(output / 'summary.json', rows)
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8') as f:
        fields = ['split', 'status', 'failed_stage', 'classification', 'model_sha256', 'log']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, '') for k in fields})
    passed = sum(row['status'] == 'PASS_HOST_ONLY' for row in rows)
    (output / 'summary.txt').write_text(
        'PASS_HOST_ONLY=%d FAIL=%d TOTAL=%d\nKV260_RUNTIME=NOT_TESTED_NO_BOARD\n' %
        (passed, len(rows) - passed, len(rows)), encoding='utf-8')


def build_all(output, package, arch, xir):
    rows = []
    for s in range(10):
        logs = output / 'logs' / ('s%d' % s)
        logs.mkdir(parents=True)
        qdir = output / 'quantized' / ('s%d' % s)
        compiled = output / 'compiled' / ('s%d' % s)
        compiled.mkdir(parents=True)
        row = {'split': s, 'status': 'FAIL', 'failed_stage': '',
               'log': 'logs/s%d/log_s%d.txt' % (s, s), 'stages': []}
        commands = []
        for mode in ('calib', 'test'):
            commands.append((mode, [sys.executable, '-B', ROOT / 'edge/quantize_tail.py',
                                    '-s', str(s), '--quant_mode', mode,
                                    '--checkpoint', package / 'model/checkpoint.pt',
                                    '--calib_data', package / ('golden/z_s%d.npy' % s),
                                    '--calib-data-split', 'val', '--calib-samples', '20',
                                    '--output_dir', qdir]))
        commands.append(('compile', ['vai_c_xir', '-x', qdir / ('tail_%d_int.xmodel' % s),
                                      '-a', arch, '-o', compiled, '-n', 'tail_s%d' % s]))
        for name, command in commands:
            log = logs / (name + '.log')
            code = run_stage(command, log)
            row['stages'].append({'name': name, 'exit_code': code,
                                  'command': [str(x) for x in command]})
            if code:
                row['failed_stage'] = name
                break
        if not row['failed_stage']:
            try:
                model = compiled / ('tail_s%d.xmodel' % s)
                evidence = inspect_model(model, xir)
                write_json(output / ('graph_s%d.json' % s), evidence)
                row.update(status='PASS_HOST_ONLY', classification=evidence['classification'],
                           model_sha256=evidence['sha256'])
            except Exception as error:
                row.update(failed_stage='inspect', error=repr(error))
        with (logs / ('log_s%d.txt' % s)).open('w', encoding='utf-8') as combined:
            for name, _ in commands:
                log = logs / (name + '.log')
                if log.exists():
                    combined.write('\n=== %s ===\n' % name)
                    combined.write(log.read_text(encoding='utf-8', errors='replace'))
            combined.write('\nRESULT ' + json.dumps(row) + '\n')
        rows.append(row)
        save_summary(output, rows)
        print('s=%d %s failed_stage=%s' % (s, row['status'], row['failed_stage']), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['audit', 'build'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', type=Path, help='Existing compiled folder; required for audit')
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--arch', type=Path, default=ARCH)
    args = parser.parse_args()
    if args.mode == 'audit' and not args.models:
        parser.error('audit requires --models')
    if args.output.exists():
        parser.error('Output already exists; use a NEW directory, no overwrite is allowed')
    if args.mode == 'build' and (not args.arch.is_file() or not shutil.which('vai_c_xir')):
        parser.error('Compiler or KV260 arch missing; activate Vitis AI 2.5 pytorch conda')
    import xir
    authenticate = runpy.run_path(str(ROOT / 'ml/scripts/authenticate_week3_sv2_package.py'))['authenticate']
    authentication = authenticate(args.package)
    try:
        args.output.mkdir(parents=True)
    except PermissionError:
        parser.error('Cannot write output: %s. Check ownership of the parent folder; '
                     'run Docker with the host UID/GID. This is not a model validation failure.' % args.output)
    evidence = args.output / 'provenance'
    evidence.mkdir()
    write_json(evidence / 'handoff_authentication.json', authentication)
    write_json(evidence / 'source_environment.json', {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'platform': platform.platform(),
        'source_sha256': {name: sha(ROOT / name) for name in
                          ('edge/build_and_audit_models.py', 'edge/quantize_tail.py', 'ml/src/mitdb_baseline_model.py')},
        'scope': '20 authenticated golden validation activations; user-approved package-only scope',
        'runtime': 'NOT_TESTED_NO_BOARD'})
    if args.arch.is_file():
        shutil.copyfile(args.arch, evidence / 'arch.json')
    run_stage(['conda', 'list'], evidence / 'conda_packages.log')
    if args.mode == 'build':
        rows = build_all(args.output, args.package, args.arch, xir)
    else:
        rows = []
        for s in range(10):
            row = {'split': s, 'status': 'FAIL', 'failed_stage': 'inspect'}
            try:
                model = args.models / ('tail_s%d.xmodel' % s)
                if not model.is_file():
                    model = args.models / ('s%d' % s) / ('tail_s%d.xmodel' % s)
                detail = inspect_model(model, xir)
                write_json(args.output / ('graph_s%d.json' % s), detail)
                row.update(status='PASS_HOST_ONLY', failed_stage='',
                           classification=detail['classification'], model_sha256=detail['sha256'],
                           model_path=str(model.resolve()))
            except Exception as error:
                row['error'] = repr(error)
            rows.append(row)
        save_summary(args.output, rows)
    write_json(evidence / 'handoff_authentication_after.json', authenticate(args.package))
    print((args.output / 'summary.txt').read_text(), end='')
    print('REPORT_DIR=' + str(args.output.resolve()))
    return 0 if all(row['status'] == 'PASS_HOST_ONLY' for row in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
