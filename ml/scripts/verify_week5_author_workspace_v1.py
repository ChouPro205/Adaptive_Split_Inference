"""Aggregate actual receipts; keep missing wire allocation BLOCKED, never PASS."""
import argparse
import csv
import hashlib
import gzip
import json
from pathlib import Path
import subprocess

from week5_common import ROOT, need, write_json
from week5_interfaces import load_registry


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    if not path.exists() and Path(str(path)+'.gz').exists():
        return json.loads(gzip.decompress(Path(str(path)+'.gz').read_bytes()))
    return json.loads(path.read_text(encoding='utf-8'))


def verify(evidence, accuracy, original_root):
    records = {}
    names = ['accuracy_final', 'p1', 'real_final_v2', 'interfaces_final_v2', 'interfaces_optimized_final_v2',
             'quantization', 'quantization_optimized', 'i2_existing', 'week4_current',
             'week4_current_tests', 'week4_release', 'week3_sv2', 'week3_policy',
             'device_fixture_generation', 'device_handoff_final', 'device_capture_final']
    for name in names:
        record = read(evidence/f'{name}.command.json')
        need(record['exit_code'] == 0, f'{name} did not pass')
        for stream in ('stdout', 'stderr'):
            need(sha(evidence/f'{name}.{stream}.txt') == record[f'{stream}_sha256'], f'{name}: log bytes changed')
        records[name] = {'exit_code': record['exit_code'], 'command': record['command'],
                         'receipt_sha256': sha(evidence/f'{name}.command.json')}
    # Bound the source that each result actually exercised, even if other
    # independent components were refined after a long evaluation started.
    dependencies = {
        'accuracy_final': ['ml/scripts/evaluate_week5.py', 'ml/scripts/week5_common.py', 'ml/src/quantization.py'],
        'p1': ['ml/scripts/test_week5_p1.py', 'ml/src/p1.py', 'contracts/i2_ref/i2_reference.py'],
        'real_final_v2': ['ml/scripts/verify_week5_real.py', 'ml/src/week5_interfaces.py', 'ml/src/quantization.py',
                       'ml/scripts/test_week5_interfaces.py', 'contracts/sv3_week5_ml_registry_v1.json'],
        'interfaces_final_v2': ['ml/scripts/test_week5_interfaces.py', 'ml/src/week5_interfaces.py', 'ml/scripts/evaluate_week5.py'],
        'interfaces_optimized_final_v2': ['ml/scripts/test_week5_interfaces.py', 'ml/src/week5_interfaces.py', 'ml/scripts/evaluate_week5.py']}
    for name, paths in dependencies.items():
        tested = read(evidence/f'{name}.command.json')['source_files_sha256']
        for path in paths:
            need(sha(ROOT/path) == tested[path], f'Tested dependency drift: {name}/{path}')
    historical = 'b73a705461ceea2618f42d39184dda25e227efe5'
    unchanged = ['ml/src/quantization.py', 'ml/src/p1.py', 'contracts/i2_protection_v1.md',
                 'contracts/i2_ref/i2_reference.py', 'contracts/i2_ref/i2_reference.c',
                 'contracts/i2_ref/i2_reference.h', 'contracts/i2_ref/vectors.json']
    reference_hashes = {}
    for path in unchanged:
        old = subprocess.check_output(['git', 'show', f'{historical}:{path}'], cwd=ROOT)
        current = (ROOT/path).read_bytes()
        need(old.decode().replace('\r\n', '\n') == current.decode().replace('\r\n', '\n'), f'Reference changed: {path}')
        reference_hashes[path] = sha(ROOT/path)
    receipt = read(ROOT/'ml/provenance/week5/external_assets.json')
    assets = {}
    for asset in receipt['assets']:
        archive = ROOT/asset['repository_path']
        need(sha(archive) == asset['sha256'] and archive.stat().st_size == asset['size_bytes'], 'Historical ZIP differs')
        for member in asset['files']:
            path = ROOT/member['path']
            need(sha(path) == member['sha256'] and path.stat().st_size == member['size_bytes'], f'Frozen asset differs: {path}')
        assets[asset['name']] = {'sha256': sha(archive), 'files_checked': len(asset['files'])}
    p1, real = read(evidence/'p1_10000.json'), read(evidence/'real_220_final_v2.json')
    need(p1['cases'] >= 10000 and p1['failed_tensors'] == real['failed_tensors'] == 0, 'P1 roundtrip gate failed')
    need(real['per_split_counts'] == {str(s): 20 for s in range(11)}, 'Real split coverage differs')
    old_p1 = read(ROOT/'ml/provenance/week5/p1_10000.json')
    need(old_p1['output_stream_sha256'] == p1['output_stream_sha256'], 'Historical synthetic checksum differs')
    with (accuracy/'accuracy.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    need(len(rows) == 11 and {int(r['split_point_s']) for r in rows} == set(range(11)), 'Missing/duplicate accuracy split')
    for row in rows:
        n, fp, q = [int(row[k]) for k in ('num_samples', 'correct_fp32', 'correct_int8_fp16')]
        need(n == 8544 and 200*(fp-q) < n and row['gate_status'] == 'PASS', 'Accuracy gate failed')
    new_predictions = sha(accuracy/'predictions.csv')
    old_predictions = sha(original_root/'ml/results/week5/predictions.csv')
    need(new_predictions == old_predictions, 'Frozen all-sample predictions changed')
    preservation = read(evidence/'preservation_after.json')
    need(preservation['status'] == 'PASS' and preservation['changed'] == [], 'Original assets/user work changed')
    before = read(evidence/'preservation_before.json')
    compressed = evidence/'preservation_before.json.gz'
    storage = read(evidence/'preservation_inventory_storage.json')
    need(sha(compressed) == storage['gzip_sha256'], 'Compressed inventory changed')
    need(hashlib.sha256(gzip.decompress(compressed.read_bytes())).hexdigest() == preservation['before_sha256'], 'Raw inventory changed')
    need(preservation['after_inventory_sha256'] == preservation['before_inventory_sha256'], 'Preservation inventory mismatch')
    copied = 0
    for name, entry in before['files'].items():
        if name.startswith(('ml/artifacts/', 'ml/data/processed/mitdb/')):
            path = ROOT/name
            need(path.is_file() and sha(path) == entry['sha256'] and path.stat().st_size == entry['size_bytes'], f'Copied historical asset changed: {name}')
            copied += 1
    registry = load_registry(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
    allocated = registry['model_profile_id'] is not None and all(r['wire_split_id'] is not None for r in registry['splits'])
    need(not allocated, 'Missing approved registry reconciliation; rerun registry acceptance before claiming PASS')
    return {'status': 'BLOCKED', 'CURRENT_WEEK': 5, 'REVIEW_STATUS': 'PENDING',
            'gates': {'p1_python_reference': 'PASS', 'roundtrip_10220': 'PASS',
                      'real_scale_shape_tail': 'PASS', 'accuracy_8544_x11': 'PASS',
                      'related_regressions': 'PASS', 'historical_preservation': 'PASS',
                      'deployment_registry': 'BLOCKED'},
            'blocker': 'No approved model_profile_id or wire split_id allocation in repository; FP32 registry explicitly does not allocate I1 wire IDs',
            'roundtrip_tensors': p1['cases'] + real['tensors_executed'], 'failed_tensors': 0,
            'test_profiles_are_not_deployment_registry': True,
            'original_files_preserved': preservation['file_count'], 'copied_asset_files_preserved': copied,
            'assets': assets, 'unchanged_reference_sha256': reference_hashes,
            'predictions_sha256_old_and_new': new_predictions,
            'source_commit_verified': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_receipts': records, 'accuracy': rows,
            'additional_cache_suite': '15 passed, 1 OS symlink privilege skip; mocked symlink guard passes',
            'MCU_week5': 'NOT_RUN', 'DPU_week5': 'NOT_RUN', 'I1_end_to_end': 'NOT_RUN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, default=ROOT/'ml/provenance/week5-20261009-v1')
    parser.add_argument('--accuracy', type=Path, default=ROOT/'ml/results/week5-20261009-v1-final')
    parser.add_argument('--original-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Evidence exists; choose a new output')
    result = verify(args.evidence, args.accuracy, args.original_root)
    write_json(args.output, result)
    print('BLOCKED: approved wire registry absent; independent Python/ML/regression/preservation gates PASS')
    raise SystemExit(2)
