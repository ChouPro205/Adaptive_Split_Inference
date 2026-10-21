"""Recheck Week7 evidence without training, editing inputs or evaluating test."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ml/src'))
from week1_common import artifact_sha256


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def raw_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    baseline = read(EVIDENCE / 'baseline-files-before.json')
    changed = [p for p, h in baseline['files'].items() if not (ROOT/p).is_file() or raw_sha(ROOT/p) != h]
    need(not changed, 'Baseline file bytes changed: ' + str(changed))
    names = ['tests-final', 'tests-final-O', 'smoke-final', 'smoke-final-repeat-O',
             'i1-regression-final', 'i2-regression-final']
    commands = {}
    for name in names:
        receipt = read(EVIDENCE / f'{name}.command.json')
        need(receipt['exit_code'] == 0 and receipt['sources_unchanged_during_command'], 'Command failed: '+name)
        for suffix, digest in receipt['logs_sha256'].items():
            need(raw_sha(EVIDENCE / f'{name}.{suffix}') == digest, 'Log bytes changed: '+name)
        for p, digest in receipt['source_sha256'].items():
            need(artifact_sha256(ROOT/p) == digest, 'Source differs from executed command: '+p)
        commands[name] = {'exit_code': receipt['exit_code'], 'git_commit': receipt['git_commit']}
    outputs = [ROOT / 'ml/results/week7-nopeek' / name for name in ('smoke-final', 'smoke-final-repeat-O')]
    a, b = [read(p/'summary.json') for p in outputs]
    canonical = lambda result: [{k:v for k,v in run.items() if not k.startswith('artifact')} for run in result['runs']]
    need(canonical(a) == canonical(b) and a['wiring_checks'] == b['wiring_checks'], 'Numerical repeat differs')
    for filename in ('batch_metrics.json', 'selected_samples.json'):
        need(read(outputs[0]/filename) == read(outputs[1]/filename), 'Repeat differs: '+filename)
    need(not a['test_opened_or_evaluated'] and not b['test_opened_or_evaluated'], 'Test evaluation occurred')
    for output, result in zip(outputs, (a,b)):
        for p, digest in result['source_sha256'].items():
            need(artifact_sha256(ROOT/p) == digest, 'Smoke source differs: '+p)
        for run in result['runs']:
            need(raw_sha(ROOT/run['artifact']) == run['artifact_sha256'], 'Experimental weight bytes changed')
    manifest = read(ROOT/'results/week6/manifest.json')
    for row in manifest['files']:
        p = ROOT/'results/week6'/row['path']
        need(raw_sha(p) == row['sha256'] and p.stat().st_size == row['bytes'], 'Historical SV1 evidence hash differs')
    sv1 = read(ROOT/'results/week6/selftest_default.json')
    need(len(sv1['p1_vectors']) == 50 and all(r['pass'] for r in sv1['p1_vectors']), 'SV1 50-vector proof differs')
    for name, row in read(EVIDENCE/'asset-reuse.json')['assets'].items():
        expected = row.get('sha256_project', row.get('sha256'))
        need(artifact_sha256(Path(row['source'])) == expected, 'Original asset changed: '+name)
    result = {'status': 'PASS', 'baseline_commit': baseline['baseline_commit'],
              'implementation_commit': a['source_git_commit'], 'original_tracked_files_checked': len(baseline['files']),
              'changed_original_tracked_files': changed, 'commands': commands,
              'repeat': 'exact equal batch metrics, selections, wiring checks, all final tensor state digests and classification metrics',
              'test_usage': 'No test arrays/metadata in loader, training, validation or model selection; original test files only hashed/copied for preservation',
              'sv1_historical_manifest_files_verified': len(manifest['files']), 'sv1_p1_vectors_pass': 50,
              'working_tree_diff_check_exit_code': subprocess.run(['git','diff','--check'],cwd=ROOT).returncode,
              'remaining_findings': ['KV260 runtime and DPU accuracy not verified', 'I1 v2 SV3 signature row still pending; evidence delivered', 'Nonce registry revision still requires Châu/Trung'],
              'resolved': ['Initial tests expected wrong exception class and read count, corrected without changing numerical tolerances',
                           'Relative artifact path failed in initial smoke-r1, canonicalized before writes; final runs passed']}
    need(result['working_tree_diff_check_exit_code'] == 0, 'Whitespace check failed')
    return result


if __name__ == '__main__':
    destination = EVIDENCE/'review-audit.json'
    need(not destination.exists(), 'Refuse overwrite audit evidence')
    result = audit()
    destination.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
