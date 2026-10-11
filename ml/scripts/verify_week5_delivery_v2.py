"""Portable scope/coverage/source/preservation verifier; registry stays BLOCKED."""
import argparse
import csv
import gzip
import hashlib
from pathlib import Path
import subprocess

from week5_delivery_scope_v2 import ROOT, SCOPE, inventory, need, read, sha, write_new, safe_path

# Required fresh commands; author/reviewer receipts cannot substitute for these.
UNIT_SCRIPTS = {
    'quantization': 'ml/scripts/test_week5_quantization.py',
    'interfaces': 'ml/scripts/test_week5_interfaces.py',
    'i2': 'contracts/i2_ref/test_i2.py',
    'delivery_policy': 'ml/scripts/test_week5_delivery_v2.py',
    'registry_policy': 'ml/scripts/test_week5_registry_v2.py',
    'week4_policy': 'ml/scripts/verify_week4_current.py',
    'week4_tests': 'ml/scripts/test_week4_current.py',
    'week4_release': 'ml/scripts/test_week4_release.py',
    'week3_sv2': 'ml/scripts/test_week3_sv2.py',
    'week3_policy': 'ml/scripts/test_week3_sv2_policy.py',
    'device_quantization': 'device/scripts/test_week5_quantization_c.py',
    'device_handoff': 'device/scripts/test_week4_handoff.py',
}
REQUIRED = {**{name: script for name, script in UNIT_SCRIPTS.items()},
            **{name+'_O': script for name, script in UNIT_SCRIPTS.items()},
            'p1': 'ml/scripts/test_week5_p1.py', 'real': 'ml/scripts/verify_week5_real.py',
            'accuracy': 'ml/scripts/evaluate_week5_v2.py'}


def check_receipt(evidence, name, script, root=ROOT):
    record = read(evidence/f'{name}.command.json')
    need(record['exit_code'] == 0, f'Fresh gate failed: {name}')
    command = record['command']
    need(script in command and bool('-O' in command) == name.endswith('_O'), f'Wrong gate command: {name}')
    for stream in ('stdout', 'stderr'):
        need(sha(evidence/f'{name}.{stream}.txt') == record[f'{stream}_sha256'], f'Log bytes changed: {name}/{stream}')
    # Every source bound by the runner must still match raw bytes. Require the
    # complete tracked source set so an omitted transitive import cannot PASS.
    source_names = subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines()
    required = {p for p in source_names if p.endswith(('.py', '.c', '.h', '.ps1'))
                or p.startswith(('ml/configs/', 'ml/manifests/', 'contracts/'))}
    tested = record['source_files_sha256']
    need(required <= tested.keys() and script in tested, f'Incomplete source provenance: {name}')
    for path, expected in tested.items():
        need(sha(safe_path(root, path)) == expected, f'Tested source drift: {name}/{path}')
    return {'scope': 'FRESH', 'command': command, 'source_commit': record['source_git_commit'],
            'source_tree': record['source_tree'], 'exit_code': 0,
            'receipt_sha256': sha(evidence/f'{name}.command.json')}


def check_accuracy(accuracy):
    with (accuracy/'accuracy.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    need(len(rows) == 11 and {int(r['split_point_s']) for r in rows} == set(range(11)), 'Missing/duplicate accuracy split')
    for r in rows:
        n, fp, q = [int(r[k]) for k in ('num_samples', 'correct_fp32', 'correct_int8_fp16')]
        need(n == 8544 and 0 <= fp <= n and 0 <= q <= n and 200*(fp-q) < n
             and r['gate_status'] == 'PASS', 'Exact strict accuracy gate failed')
    gates = read(accuracy/'fp32_gates.json')
    need(len(gates) == 11 and {r['split_point_s'] for r in gates} == set(range(11))
         and all(r['num_samples'] == 8544 and r['status'] == 'PASS' and r['max_abs_error'] < 1e-3 for r in gates),
         'FP32 coverage/tolerance failed')
    counts = {s: [0, 0, 0, set()] for s in range(11)}
    with (accuracy/'predictions.csv').open(newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            s = int(r['split_point_s'])
            need(s in counts, 'Unknown prediction split')
            c = counts[s]
            need(r['sample_id'] not in c[3], 'Duplicate prediction sample')
            c[3].add(r['sample_id'])
            c[0] += 1
            c[1] += int(r['prediction_fp32'] == r['true_label'])
            c[2] += int(r['prediction_int8_fp16'] == r['true_label'])
    for r in rows:
        s = int(r['split_point_s'])
        need(counts[s][:3] == [8544, int(r['correct_fp32']), int(r['correct_int8_fp16'])], 'Prediction coverage/counts differ')
        need(counts[s][3] == counts[0][3], 'Prediction sample sets differ')
    need(sha(accuracy/'predictions.csv') == sha(ROOT/'ml/results/week5/predictions.csv'), 'Frozen predictions changed')
    return rows


def historical_preservation(scope):
    base = ROOT/'ml/provenance/week5-20261009-v1'
    before_raw = gzip.decompress((base/'preservation_before.json.gz').read_bytes())
    import json
    before, after, storage = json.loads(before_raw), read(base/'preservation_after.json'), read(base/'preservation_inventory_storage.json')
    need(sha(base/'preservation_before.json.gz') == storage['gzip_sha256'], 'Historical compressed inventory changed')
    need(hashlib.sha256(before_raw).hexdigest() == after['before_sha256'], 'Historical inventory bytes changed')
    digest = hashlib.sha256(json.dumps(before['files'], sort_keys=True).encode()).hexdigest()
    need(after['status'] == 'PASS' and after['changed'] == [] and after['file_count'] == 94518
         and digest == after['before_inventory_sha256'] == after['after_inventory_sha256'], 'Historical preservation differs')
    old_copies = sum(n.startswith(('ml/artifacts/', 'ml/data/processed/mitdb/')) for n in before['files'])
    need(old_copies == 754, 'Historical copy scope differs')
    return {'scope': 'REUSED_AUTHOR_WORKSPACE_AUDIT; not recipient inventory', 'file_count': 94518,
            'copied_asset_files': old_copies, 'status': 'AUTHENTICATED_HISTORICAL_RECEIPT'}


def verify(evidence, accuracy):
    scope = read(SCOPE)
    current = inventory(ROOT, scope)
    before, after = read(evidence/'scope_before.json'), read(evidence/'scope_after.json')
    need(before['scope_manifest_sha256'] == after['scope_manifest_sha256'] == sha(SCOPE), 'Preservation scope changed')
    need(before['files'] == after['files'] == current, 'Portable delivery preservation failed')
    records = {n: check_receipt(evidence, n, s) for n, s in REQUIRED.items()}
    p1, real = read(evidence/'p1_10000.json'), read(evidence/'real_220.json')
    need(p1['status'] == real['status'] == 'PASS' and p1['cases'] >= 10000
         and p1['failed_tensors'] == real['failed_tensors'] == 0, 'Roundtrip failed')
    need(p1['bit_exact_roundtrips'] == p1['determinism_checks'] == p1['cases'], 'Synthetic coverage differs')
    need(real['tensors_executed'] == 220 and real['per_split_counts'] == {str(s):20 for s in range(11)}, 'Real coverage differs')
    need(p1['output_stream_sha256'] == read(ROOT/'ml/provenance/week5/p1_10000.json')['output_stream_sha256'], 'Historical synthetic checksum differs')
    need(real['golden_manifest_sha256'] == sha(ROOT/'ml/artifacts/week5/quantization20/manifest.json'), 'Real golden binding differs')
    # Result files are also bound by per-run receipts; logs alone are insufficient.
    for name, result in [('p1','p1_10000.json'), ('real','real_220.json'), ('accuracy','accuracy/evaluation.json')]:
        record = read(evidence/f'{name}.command.json')
        for path, expected in record['result_files_sha256'].items():
            need(sha(safe_path(ROOT, path)) == expected, f'Fresh result changed: {path}')
        target = (accuracy/'evaluation.json') if name == 'accuracy' else evidence/result
        need(str(target.resolve().relative_to(ROOT).as_posix()) in record['result_files_sha256'], f'Unbound result: {name}')
    rows = check_accuracy(accuracy)
    history = historical_preservation(scope)
    registry = read(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
    need(registry['model_profile_id'] is None and all(r['wire_split_id'] is None for r in registry['splits']),
         'Registry changed; use approved reconciliation verifier before claiming acceptance')
    return {'schema': 'week5-portable-delivery/2', 'status':'BLOCKED', 'CURRENT_WEEK':5, 'REVIEW_STATUS':'PENDING',
            'gates': {'portable_dependencies':'PASS', 'portable_preservation':'PASS', 'source_dependencies':'PASS',
                      'p1_10000':'PASS','real_220':'PASS','accuracy_8544_x11':'PASS','related_regressions':'PASS',
                      'deployment_registry':'BLOCKED'},
            'blocker':'Châu allocation and Châu/Trung shared registry confirmation pending',
            'scope_manifest_sha256':sha(SCOPE),'recipient_scope_file_count':len(current),
            'historical_preservation_reuse':history,'fresh_receipts':records,'accuracy':rows,
            'SV1_package_acceptance':'SEPARATE_RECEIPT_REQUIRED; portable ML gate does not imply MCU acceptance',
            'I1_transport':'NOT_RUN','week6':'NOT_RUN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--accuracy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.evidence.resolve(), args.accuracy.resolve())
    write_new(args.output, result)
    print('BLOCKED: portable Python/ML gates PASS; deployment registry awaits approval')
    raise SystemExit(2)


if __name__ == '__main__':
    main()
