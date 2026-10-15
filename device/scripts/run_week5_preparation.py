"""Log explicit offline preparation steps. Never flashes or opens a serial port."""
from __future__ import annotations
import argparse
import ast
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / 'ml/.venv/Scripts/python.exe'

def run(output, name, command, env):
    receipt = output / 'commands' / (name + '.json')
    if receipt.exists():
        raise ValueError(f'Command receipt already exists: {name}; choose a new run')
    receipt.parent.mkdir(parents=True, exist_ok=True)
    data = {'command': list(map(str, command)), 'cwd': str(ROOT),
            'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'exit_code': None}
    receipt.write_text(json.dumps(data, indent=2), encoding='utf-8')
    log = receipt.with_suffix('.log')
    with log.open('w', encoding='utf-8') as handle:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
    data.update(exit_code=result.returncode, finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    receipt.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f'{name}: exit={result.returncode}; log={log}', flush=True)
    if result.returncode:
        print(log.read_text(encoding='utf-8', errors='replace')[-12000:], flush=True)
        raise RuntimeError(f'Preparation command failed: {name}')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--stage', choices=['baseline', 'host', 'accuracy', 'regression', 'capture-tests', 'package-tests', 'memory-audit', 'tools-check'], required=True)
    p.add_argument('--build-report', type=Path)
    p.add_argument('--compiler', default='C:/msys64/ucrt64/bin/gcc.exe')
    a = p.parse_args()
    output = a.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Evidence must be outside repo')
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(key, None)
    env['CC'] = a.compiler
    env['PYTHONIOENCODING'] = 'utf-8'
    def py(name, script, *args, optimized=False):
        run(output, name, [str(PYTHON), '-B', *(['-O'] if optimized else []), str(ROOT / script), *map(str, args)], env)
    if a.stage == 'baseline':
        for opt in (False, True):
            suffix = '-O' if opt else ''
            py('current-gate' + suffix, 'ml/scripts/verify_week4_current.py', '--compiler', a.compiler, optimized=opt)
        py('week4-host', 'device/scripts/verify_week4_host.py', '--report-dir', output / 'week4-host', '--compiler', a.compiler)
    elif a.stage == 'host':
        for opt in (False, True):
            suffix = '-O' if opt else ''
            py('quantization-tests' + suffix, 'device/scripts/test_week5_quantization_c.py', '--output', output / ('unit' + suffix), '--compiler', a.compiler, optimized=opt)
            py('week5-host' + suffix, 'device/scripts/verify_week5_host.py', '--output', output / ('host' + suffix), '--compiler', a.compiler, optimized=opt)
    elif a.stage == 'accuracy':
        py('accuracy', 'device/scripts/evaluate_week5_c.py', '--output', output / 'accuracy', '--compiler', a.compiler)
    elif a.stage == 'capture-tests':
        for opt in (False, True):
            suffix = '-O' if opt else ''
            fixture_dir = output / ('capture-tests' + suffix)
            py('capture-tests' + suffix, 'device/scripts/test_week5_capture.py', '--output', fixture_dir, '--host', output / 'host', optimized=opt)
            py('checker-fixture' + suffix, 'device/scripts/check_week5_capture.py', '--capture', fixture_dir / 'SIMULATED_HOST_capture.txt',
               '--report', fixture_dir / 'checker.json', '--simulated', optimized=opt)
    elif a.stage == 'package-tests':
        if a.build_report is None:
            raise ValueError('--build-report is required for package tests')
        for opt in (False, True):
            suffix = '-O' if opt else ''
            py('package-tests' + suffix, 'device/scripts/test_week5_package.py', '--build-report', a.build_report,
               '--output', output / ('package-tests' + suffix + '.json'), optimized=opt)
    elif a.stage == 'memory-audit':
        if a.build_report is None:
            raise ValueError('--build-report required')
        audit_output = output / 'memory-audit'
        audit_output.mkdir(parents=True)
        __import__('shutil').copyfile(a.build_report / 'build.log', audit_output / 'build.log')
        py('memory-audit', 'device/scripts/inspect_week5_memory.py', '--build', a.build_report / 'build', '--output', audit_output,
           '--toolchain', 'D:/ncs/toolchains/dcbdc366a1')
    elif a.stage == 'tools-check':
        for path in (ROOT / 'device/scripts').glob('*week5*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        run(output, 'powershell-syntax', ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'device/scripts/test_week5_scripts.ps1')], env)
        run(output, 'collector-dependency', [str(PYTHON),'-B','-c','import serial; print(serial.VERSION); raise SystemExit(0 if serial.VERSION == "3.5" else 1)'], env)
    else:
        for opt in (False, True):
            suffix = '-O' if opt else ''
            for name, script, args in [
                ('current-regressions', 'ml/scripts/verify_week4_current.py', ['--compiler', a.compiler, '--regressions']),
                ('current-policy', 'ml/scripts/test_week4_current.py', []),
                ('handoff-policy', 'device/scripts/test_week4_handoff.py', []),
                ('python-quantization', 'ml/scripts/test_week5_quantization.py', []),
                ('historical-capture', 'device/scripts/check_week4_capture.py', ['--capture', 'results/week4/logs/week4_capture.txt', '--report', output / ('historical-capture' + suffix + '.json'), '--bench-sample', '0', '--mixed-order']),
                ('historical-tamper', 'device/scripts/test_week4_capture.py', ['--capture', 'results/week4/logs/week4_capture.txt', '--work-dir', output / ('historical-tamper' + suffix)])]:
                py(name + suffix, script, *args, optimized=opt)

if __name__ == '__main__':
    main()
