"""Reproduce portable Week 5 gates in a clean hydrated checkout, offline CPU."""
import argparse
from pathlib import Path
import subprocess
import sys

from week5_delivery_scope_v2 import ROOT, SCOPE, inventory, sha, write_new, need
from verify_week5_delivery_v2 import UNIT_SCRIPTS


def run(output):
    need(not output.exists(), 'Use a new evidence directory')
    output.mkdir(parents=True)
    write_new(output/'scope_before.json', {'scope_manifest_sha256':sha(SCOPE), 'files':inventory()})
    logger = 'ml/scripts/run_week5_logged_v2.py'
    statuses = {}

    def gate(name, script, arguments=(), optimized=False, result=None):
        command = [sys.executable, '-B', logger, '--output', str(output/name)]
        if result is not None:
            command += ['--result-path', str(result)]
        command += ['--', sys.executable, '-B', *(['-O'] if optimized else []), script, *map(str, arguments)]
        statuses[name] = subprocess.run(command, cwd=ROOT).returncode

    for name, script in UNIT_SCRIPTS.items():
        arguments = ['--regressions'] if name == 'week4_policy' else []
        if name == 'week3_sv2':
            arguments = ['--package','ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1',
                         '--expected-manifest-sha256','a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6']
        for optimized in (False, True):
            gate_name = name+('_O' if optimized else '')
            actual = ['--output', output/(gate_name+'-results')] if name == 'device_quantization' else arguments
            gate(gate_name, script, actual, optimized)
    for name, script, args, result in [
        ('p1','ml/scripts/test_week5_p1_v2.py',['--cases','10000','--output',output/'p1_10000.json'],output/'p1_10000.json'),
        ('real','ml/scripts/verify_week5_real.py',['--output',output/'real_220.json'],output/'real_220.json'),
        ('accuracy','ml/scripts/evaluate_week5_v2.py',['--batch-size','1','--output',output/'accuracy'],output/'accuracy')]:
        gate(name, script, args, result=result)
    write_new(output/'scope_after.json', {'scope_manifest_sha256':sha(SCOPE), 'files':inventory()})
    write_new(output/'suite.json', {'scope':'FRESH_PORTABLE_COMMANDS', 'exit_codes':statuses})
    code = subprocess.run([sys.executable,'-B',logger,'--output',str(output/'delivery'), '--result-path',str(output/'delivery.json'),
                           '--',sys.executable,'-B','ml/scripts/verify_week5_delivery_v2.py',
                           '--evidence',str(output),'--accuracy',str(output/'accuracy'),'--output',str(output/'delivery.json')],cwd=ROOT).returncode
    raise SystemExit(code)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())
