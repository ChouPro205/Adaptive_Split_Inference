"""Independent SV3 audit of published tables; never claims access to board raw files."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ANCHOR = 'd0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36'
CHECKPOINT = '9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90'
CLASSES = ['N', 'S', 'V', 'F', 'Q']


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def read(path):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, 'Duplicate JSON key: ' + k)
            result[k] = v
        return result
    def bad(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(Path(path).read_text('utf-8'), object_pairs_hook=pairs, parse_constant=bad)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def logits(values):
    need(isinstance(values, list) and len(values) == 5, 'Expected five N/S/V/F/Q logits')
    need(all(type(v) in (int, float) and math.isfinite(v) for v in values), 'Invalid logit')
    return values


def argmax(values):
    return max(range(5), key=values.__getitem__)  # First index on ties.


def audit(root=ROOT, p1_package=None, p1_zip=None):
    root = Path(root)
    folder = root / 'results/week7/edge'
    status, provenance, a, b = [read(folder / p) for p in
                               ('status.json', 'provenance.json', 'p1_host_A.json', 'p1_host_B.json')]
    inputs = {}
    # Check raw bytes of the published exports, not LF-normalized approximations.
    for week in (5, 6, 7):
        directory = root / f'results/week{week}/edge'
        for line in (directory / 'sha256sum_export.txt').read_text().splitlines():
            digest, name = line.split(maxsplit=1)
            p = directory / name.strip().lstrip('*')
            need(p.resolve().is_relative_to(directory.resolve()), 'Unsafe checksum member')
            need(sha(p) == digest, 'Export checksum differs: ' + str(p))
            inputs[p.relative_to(root).as_posix()] = digest
    need(status['class_order'] == b['class_order'] == CLASSES, 'Class order differs')
    need(status['manifest_sha256'] == a['manifest_sha256'] == ANCHOR, 'P1 manifest differs')
    need(status['reference_vectors']==status['kv260_vectors']==50 and status['kv260_root_tail_calls']==46 and
         status['s10_identity_vectors']==4 and status['unique_ecg_samples']==5, 'Status coverage differs')
    need(b['model_checkpoint_sha256'] == CHECKPOINT, 'Checkpoint differs')
    old = root / 'ml/provenance/week6-p1-20261016/final'
    old_a, old_b = read(old / 'p1_50.json'), read(old / 'output_50.json')
    need(a['rows'] == old_a['rows'], 'A vector/q/protect identities differ from SV3')
    for k in ('status', 'vectors', 'split_counts', 'python_roundtrips', 'C_Python_protect_matches',
              'C_roundtrips', 'transformed_0x80_vectors'):
        need(a[k] == old_a[k], 'A receipt differs: ' + k)
    need(len(a['rows']) == len(b['rows']) == 50, 'Incomplete A/B')
    # provenance hashes the ORIGINAL receipts; exporter removes C_build and
    # reserializes JSON. Published bytes are authenticated by sha256sum_export.
    receipt_hashes = {name: {'published_sha256': sha(folder / name),
                           'original_receipt_sha256': provenance['host_verifier_receipts_sha256'][name],
                           'original_bytes_rechecked': False}
                      for name in ('p1_host_A.json', 'p1_host_B.json')}
    rows = read(folder / 'cases.json')['rows']
    need(len(rows) == 100, 'Expected 100 backend/vector rows')
    keyed = {(r['backend'], r['vector_index']): r for r in rows}
    need(len(keyed) == 100 and set(keyed) == {(be, v) for be in ('reference', 'kv260') for v in range(50)},
         'Duplicate or missing backend/vector')
    package_check = {'status': 'NOT_REQUESTED'}
    if p1_package is not None:
        sys.path.insert(0, str(root / 'ml/scripts'))
        from week6_p1 import inventory, authenticated_inputs, metadata, SELECTION
        # The original verifier requires ALL current sources to equal the week6
        # generating checkout. main now contains legitimate SV1/SV2 changes.
        # Authenticate the immutable package and its historical Git blobs here;
        # do not patch that verifier or pretend its current-source gate passed.
        need(sha(p1_package / 'manifest.json') == ANCHOR, 'P1 package anchor differs')
        need(read(p1_package / 'manifest.json')['files'] == inventory(p1_package), 'P1 inventory differs')
        data = read(p1_package / 'vectors.json')
        _, registry, entries = authenticated_inputs(p1_package / 'inputs/quantization20.manifest.json',
                                                   p1_package / 'inputs/registry.json', p1_package / 'inputs/approval.json')
        vectors = data['vectors']
        need(vectors == [metadata(entries[s,i], n, registry) for n,(s,i) in enumerate(SELECTION)],
             'P1 selection/source metadata differs')
        bindings = data['provenance']['source_files_sha256']
        commit = data['provenance']['source_commit']
        for p, digest in bindings.items():
            blob = subprocess.check_output(['git', 'show', commit+':'+p], cwd=root)
            need(hashlib.sha256(blob).hexdigest() == digest, 'Historical P1 source blob differs: '+p)
        for v in vectors:
            for be in ('reference', 'kv260'):
                r = keyed[be, v['vector_index']]
                for k in ('sample_id', 'sample_index', 'request_id', 'wire_split_id'):
                    need(r[k] == v[k], 'P1 package identity differs: '+k)
                for k, kind in (('request_sha256', 'request'), ('q_sha256', 'q')):
                    need(r[k] == sha(p1_package / v['files'][kind]), 'P1 raw input hash differs')
                raw_logits = (p1_package / v['files']['logits']).read_bytes()
                need(struct.pack('<5f', *r['reference_logits']) == raw_logits, 'Frozen logits raw bytes differ')
        package_check = {'status': 'PASS_AUTHENTICATED_P1_INPUT_BYTES', 'vectors': len(vectors),
                         'manifest_sha256': sha(p1_package / 'manifest.json'),
                         'historical_source_commit': commit, 'historical_source_blobs_verified': len(bindings),
                         'current_checkout_week6_verifier_gate': 'NOT_PASSED; source drift from legitimate later work',
                         'sv2_output_raw_bytes_rechecked': False}
    if p1_zip is not None:
        need(sha(p1_zip) == '2afbab35b601ac14128c32018d6dc1d39afd1991759a7a0fd9ad2051d923359a', 'P1 ZIP differs')
        need(p1_zip.stat().st_size == 412045, 'P1 ZIP size differs')
        package_check['zip_sha256'] = sha(p1_zip)
    summary, by_split = {}, []
    old_by_v = {r['vector_index']: r for r in old_b['rows']}
    for be in ('reference', 'kv260'):
        checked = []
        for v in range(50):
            r, ar, br = keyed[be, v], a['rows'][v], b['rows'][v]
            s = ar['s']
            need(ar['vector_index'] == br['vector_index'] == v and br['s'] == s, 'A/B vector mismatch')
            need(r['split'] == s and r['wire_split_id'] == ar['wire_split_id'] == 256+s,
                 'Split/wire mapping differs')
            need(r['request_id'] == ar['sequence'] == v+1 and r['status'] == 'OK', 'Request/status differs')
            other = keyed['reference', v]
            for k in ('sample_id', 'sample_index', 'split', 'wire_split_id', 'request_id', 'request_sha256', 'q_sha256'):
                need(r[k] == other[k], 'Cross-backend identity differs: ' + k)
            need(r['sample_index'] == (v-s*5 if s < 6 else v-30-(s-6)*4),
                 'Unexpected sample index selection')
            need(r['q_sha256'] == ar['q_sha256'] == ar['python_unprotect_sha256'] == ar['C_unprotect_sha256'],
                 'q recovery hash differs')
            need(ar['python_protect_sha256'] == ar['C_protect_sha256'], 'P1 hash mismatch')
            ref, out = logits(r['reference_logits']), logits(r['logits'])
            need(ref == other['reference_logits'], 'Different backend reference')
            error = max(abs(x-y) for x, y in zip(out, ref))
            need(error == r['max_abs_error'] and r['class_match'] == (argmax(out) == argmax(ref)),
                 'Recomputed comparison differs')
            # Saved HOST B rerun is numerically checked, not assumed byte-identical to older FP32 kernels.
            need(br['logits'] == other['logits'] and br['I1_response_sha256'] == other['response_sha256'],
                 'HOST B response differs from reference cases')
            need(max(abs(x-y) for x,y in zip(logits(old_by_v[v]['logits']), ref)) < 1e-3,
                 'Historical SV3 HOST output outside existing FP32 tolerance')
            need(br['argmax'] == argmax(br['logits']) and br['class'] == CLASSES[argmax(br['logits'])],
                 'B class/argmax differs')
            need(br['tail_input_shape'] == ([1,32] if s == 9 else [1,5] if s == 10 else
                 [1, {0:1,1:16,2:16,3:32,4:32,5:48,6:48,7:64,8:64}[s],
                  {0:360,1:360,2:180,3:180,4:90,5:90,6:45,7:45,8:22}[s]]), 'B tail shape differs')
            if s == 10:
                need(error == 0 and struct.pack('<5f', *out) == struct.pack('<5f', *ref), 's10 identity differs')
                need(r['model_sha256'] is None and br['tail_calls'] == 0 and br['s10_identity'], 's10 called model')
            else:
                need(br['tail_calls'] == 1 and not br['s10_identity'], 'Tail call count differs')
                if be == 'kv260':
                    need(r['model_sha256'] == provenance['model_hashes'][str(s)], 'Runtime model hash differs')
            if be == 'kv260':
                raw = provenance['evidence']['kv260']['files_sha256']
                need(raw[f'v{v:02d}/response.bin'] == r['response_sha256'], 'Published raw response hash differs')
                need((f'v{v:02d}/input.npy' in raw) == (s != 10), 'NPY/identity inventory differs')
            checked.append((r, error, argmax(out), argmax(ref)))
        need(len({r['sample_id'] for r, *_ in checked}) == 5, 'Unexpected unique ECG count')
        need(len({r['request_id'] for r, *_ in checked}) == 50, 'Duplicate requests')
        summary[be] = {'requests': 50, 'unique_ecg_samples': 5, 'native_tail_cases': 46 if be == 'kv260' else 0,
                       'identity_cases': 4, 'class_matches': sum(p == q for _, _, p, q in checked),
                       'max_abs_error': max(e for _, e, _, _ in checked),
                       'predicted_class_counts': dict(Counter(CLASSES[p] for _, _, p, _ in checked))}
        for s in range(11):
            group = [x for x in checked if x[0]['split'] == s]
            by_split.append({'backend': be, 'split': s, 'vector_count': len(group),
                             'class_matches': sum(p == q for _, _, p, q in group),
                             'max_abs_error': max(e for _, e, _, _ in group)})
    saved_splits = read_csv(folder / 'by_split.csv')
    for row, saved in zip(by_split, saved_splits):
        need(all(str(v) == saved[k] if k == 'backend' else float(v) == float(saved[k])
                 for k, v in row.items()), 'by_split CSV differs')
    need(len(saved_splits) == 22, 'CSV row count differs')
    for be, prefix in (('reference', 'reference'), ('kv260', 'kv260')):
        need(status[prefix+'_class_matches'] == summary[be]['class_matches'] and
             status[prefix+'_max_abs_error'] == summary[be]['max_abs_error'], 'status summary differs')
    for tie in b['tie_cases']:
        need(argmax(logits(tie['logits'])) == tie['expected_index'], 'Tie policy differs')
    source = {}
    for p, digest in provenance['measured_source_sha256'].items():
        blob = subprocess.check_output(['git', 'show', 'HEAD:'+p], cwd=root)
        blob_sha = hashlib.sha256(blob).hexdigest()
        need(blob_sha == digest, 'Measured source Git blob changed: ' + p)
        source[p] = {'measured_sha256': digest, 'git_blob_sha256': blob_sha,
                     'checkout_sha256': sha(root / p), 'checkout_raw_matches': sha(root / p) == digest}
    need(sha(root / 'edge/export_week7_evidence.py') == provenance['exporter_sha256'], 'Exporter differs')
    normative_sources = {}
    for p,digest in provenance['measured_snapshot_files_sha256'].items():
        if p.startswith('contracts/'):
            blob = subprocess.check_output(['git','show','HEAD:'+p],cwd=root)
            need(hashlib.sha256(blob).hexdigest()==digest,'Measured contract/reference differs: '+p)
            normative_sources[p]=digest
    profile = read(root / 'results/week6/edge/profile_edge.json')
    week5 = read(root / 'results/week5/edge/summary.json')
    if p1_package is not None:
        model_package = root/'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1'
        need(sha(model_package/'manifest.json') == 'a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6',
             'Calibration model package differs')
        for row in week5:
            need(sha(model_package/f"golden/z_s{row['split']}.npy")==row['input_sha256'],
                 'Published week5 calibration/runtime input differs from frozen golden')
        package_check['week5_calibration_golden_input_hashes_verified']=10
    timing = read_csv(root / 'results/week6/edge/timing.csv')
    splits = []
    for p in profile['splits']:
        s = p['split']
        need(p['model_sha256'] == provenance['model_hashes'][str(s)] == week5[s]['model_sha256'],
             'Model differs across weeks 5/6/7')
        expected = {'load_mean_ms': p['loading']['model_load_ms']['mean_ms'],
                    'first_mean_ms': p['first_inference']['tail_total_ms']['mean_ms'],
                    'tail_mean_ms': p['steady']['tail_total_ms']['mean_ms'],
                    'tail_std_ms': p['steady']['tail_total_ms']['std_ms'],
                    'tail_p95_ms': p['steady']['tail_total_ms']['p95_ms']}
        need(all(math.isclose(float(timing[s][k]), v, rel_tol=1e-12) for k, v in expected.items()), 'Timing CSV differs')
        need(p['loading']['model_load_ms']['n'] == 5 and p['steady']['tail_total_ms']['n'] == 500,
             'Profiling observation count differs')
        if s in (2, 5, 8):
            splits.append({'s': s, 'model_sha256': p['model_sha256'], **expected})
    for p in (folder / 'cases.json', folder / 'sha256sum_export.txt', old / 'p1_50.json', old / 'output_50.json',
              root / 'contracts/sv3_week5_approved_registry_v2.json', Path(__file__)):
        inputs[p.relative_to(root).as_posix()] = sha(p)
    return {'status': 'PASS_PUBLISHED_TABLE_AUDIT', 'input_commit': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'scope': 'Published JSON/CSV, receipts, source and hash associations; no new KV260 execution',
            'raw_packet_npy_binary_recheck': 'NOT_PERFORMED; original SV2 raw bytes are outside Git and unavailable here',
            'numeric_acceptance': 'PENDING; no INT8/DPU logit threshold invented',
            'independent_test_accuracy': 'NOT_MEASURED', 'class_order': CLASSES,
            'summary': summary, 'by_split': by_split, 'selected_split_profile': splits,
            'measured_source_sha256': source, 'measured_normative_sources_sha256':normative_sources,
            'receipt_hashes': receipt_hashes,
            'p1_input_package': package_check, 'inputs_sha256': inputs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--p1-package', type=Path)
    parser.add_argument('--p1-zip', type=Path)
    args = parser.parse_args()
    need(not args.output.exists(), 'Refuse to overwrite audit')
    result = audit(p1_package=args.p1_package, p1_zip=args.p1_zip)
    write(args.output, result)
    print(json.dumps({'status': result['status'], 'summary': result['summary']}, indent=2))
