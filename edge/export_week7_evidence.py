#!/usr/bin/env python3
"""Validate saved Week 7 evidence and export small portable results without rerunning inference."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import tarfile
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'contracts/i1v2_ref'))
import i1v2_reference as i1

PACKAGE_ANCHOR = 'd0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def check_inventory(folder, name):
    inventory = folder / name
    entries = inventory.read_text().splitlines()
    for line in entries:
        digest, relative = line.split('  ', 1)
        p = folder / relative
        require(not p.is_symlink() and p.resolve().is_relative_to(folder.resolve()), 'Unsafe inventory path')
        require(sha(p) == digest, 'Checksum mismatch: ' + relative)
    return len(entries)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--session', type=Path, required=True)
    ap.add_argument('--expected-archive-sha256', required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    require(not a.output.exists(), 'Output exists; choose a new output directory')
    session = a.session.resolve()
    received = session / 'nhan_board'
    archive = received / 'ho_so_week7.tar.gz'
    require(sha(archive) == a.expected_archive_sha256, 'Independent archive anchor differs')
    require((received / 'remote_sha256.txt').read_text().split()[0] == a.expected_archive_sha256,
            'Transfer receipt differs')
    board = received / 'ho_so'
    archive_files_verified = 0
    with tarfile.open(archive, 'r:gz') as saved:
        for member in saved:
            require(not member.issym() and not member.islnk(), 'Archive links are not supported')
            if not member.isfile():
                continue
            path = board / member.name
            require(path.resolve().is_relative_to(board.resolve()), 'Unsafe archive member')
            with saved.extractfile(member) as stream:
                digest = hashlib.sha256(stream.read()).hexdigest()
            require(path.stat().st_size == member.size and sha(path) == digest,
                    'Extracted file differs from authenticated archive: ' + member.name)
            archive_files_verified += 1
    package = session / 'du_lieu/mitdb-week6-p1-50-20261016-v1'
    require(sha(package / 'manifest.json') == PACKAGE_ANCHOR, 'P1 package anchor differs')
    manifest = read(package / 'manifest.json')
    expected = {r['path']: r for r in manifest['files']}
    actual = {p.relative_to(package).as_posix() for p in package.rglob('*')
              if p.is_file() and p != package / 'manifest.json'}
    require(actual == set(expected), 'P1 package inventory differs')
    for name, row in expected.items():
        p = package / name
        require(not p.is_symlink() and p.resolve().is_relative_to(package), 'Unsafe P1 path')
        require(sha(p) == row['sha256'] and p.stat().st_size == row['size_bytes'], 'P1 member differs')
    vectors = read(package / 'vectors.json')['vectors']
    require(len(vectors) == 50 and [v['vector_index'] for v in vectors] == list(range(50)), 'Vector order/count differs')
    profile = i1.load_profile(ROOT / 'contracts/sv3_week5_approved_registry_v2.json')
    checksums = {}
    source_mapping = {
        'serve.py': 'edge/server/week7/serve.py',
        'batch.py': 'edge/server/week7/batch.py',
        'edge/runtime/tail_runner.cpp': 'edge/runtime/single_input/tail_runner.cpp',
        'edge/runtime/tail_io.hpp': 'edge/runtime/single_input/tail_io.hpp',
        'edge/runtime/build_tail_runner.sh': 'edge/runtime/single_input/build_tail_runner.sh',
    }
    for src, dest in source_mapping.items():
        require(sha(board / 'source' / src) == sha(ROOT / dest), 'Published source differs from measured snapshot: ' + dest)
    source_inventory_count = check_inventory(board / 'source', 'sha256sum_source.txt')
    binary_hash = sha(board / 'build/asi-tail-runner')
    require((board / 'build/binary_sha256.txt').read_text().split()[0] == binary_hash, 'Binary receipt mismatch')
    preflight = read(board / 'cpu_preflight.json')
    require(preflight['all_loadable'], 'CPU library preflight incomplete')
    rows = []
    evidence_hashes = {}
    for label, folder in [('reference', session / 'reference_50'), ('kv260', board / 'kv260_50')]:
        checksums[label] = check_inventory(folder, 'sha256sum_results.txt')
        summary = read(folder / 'summary.json')
        require(summary['execution_complete'] and summary['manifest_sha256'] == PACKAGE_ANCHOR, 'Incomplete summary')
        require(len(summary['rows']) == 50, 'Summary count differs')
        evidence_hashes[label] = {
            'inventory_sha256': sha(folder / 'sha256sum_results.txt'),
            'summary_sha256': sha(folder / 'summary.json'),
            'files_sha256': {p.relative_to(folder).as_posix(): sha(p)
                             for p in sorted(folder.rglob('*')) if p.is_file()},
        }
        for index, (v, row) in enumerate(zip(vectors, summary['rows'])):
            require(row['vector_index'] == index and row['split'] == v['split_point_s'], 'Vector mapping mismatch')
            require(row['exit_code'] == 0 and row['status'] == 'OK', 'Failed vector')
            folder_case = folder / ('v%02d' % index)
            result = read(folder_case / 'result.json')
            request_path = package / v['files']['request']
            request = i1.parse_request(request_path.read_bytes(), profile)
            q = i1.recover_q(request, {profile.key_id: bytes(range(32))})
            require(q == (package / v['files']['q']).read_bytes(), 'P1 recovered bytes differ')
            require(result['request_id'] == v['request_id'] and result['split'] == v['split_point_s'], 'Request mapping differs')
            require(result['backend'] == label and result['status'] == 'OK', 'Backend/status differs')
            require(result['source_sha256'] == sha(board / 'source/serve.py'), 'Service source differs')
            require(result['request_sha256'] == row['request_sha256'] == sha(request_path), 'Request hash differs')
            response = folder_case / 'response.bin'
            require(result['response_sha256'] == sha(response), 'Response hash differs')
            kind, logits = i1.parse_response(response.read_bytes(), v['request_id'], 6380)
            require(kind == 'OK' and logits == result['logits'] == row['logits'], 'Response logits differ')
            reference = np.frombuffer((package / v['files']['logits']).read_bytes(), dtype='<f4')
            output = np.asarray(logits, dtype='<f4')
            error = float(np.max(np.abs(output.astype(float) - reference)))
            require(error == row['max_abs_error'] and bool(np.argmax(output) == np.argmax(reference)) == row['class_match'],
                    'Comparison differs from saved tensors')
            s = v['split_point_s']
            if label == 'kv260' and s < 10:
                z = np.asarray(i1.dequantize(request, q), dtype='<f4').reshape(1, request.split.channels, request.split.length)
                if s == 9:
                    z = z.reshape(1, 32)
                saved_input = np.load(folder_case / 'input.npy', allow_pickle=False)
                require(saved_input.shape == z.shape and saved_input.dtype == z.dtype and saved_input.tobytes() == z.tobytes(),
                        'Actual native input differs from packet dequantization')
                run = read(folder_case / 'runner.json')
                require(run['execution'] == 'root_graph' and run['split'] == s and len(run['samples']) == 1,
                        'Missing root graph execution')
                require(run['samples'][0]['shape'] == [1, 5] and run['samples'][0]['logits'] == logits,
                        'Runner logits differ from response')
                require(result['runner_sha256'] == binary_hash, 'Runner binary differs')
                require(preflight['model_hashes'][str(s)] == result['model_sha256'], 'Model preflight hash differs')
            elif s == 10:
                require(np.asarray(i1.dequantize(request, q), dtype='<f4').tobytes() == output.tobytes(), 's10 identity differs')
                require(not (folder_case / 'runner.json').exists(), 's10 unexpectedly executed a model')
            rows.append({'backend': label, 'vector_index': index, 'sample_id': v['sample_id'],
                         'sample_index': v['sample_index'], 'split': s, 'wire_split_id': v['wire_split_id'],
                         'request_id': v['request_id'], 'status': 'OK', 'logits': logits,
                         'reference_logits': reference.tolist(), 'max_abs_error': error,
                         'class_match': row['class_match'], 'request_sha256': sha(request_path),
                         'response_sha256': sha(response), 'q_sha256': hashlib.sha256(q).hexdigest(),
                         'model_sha256': result.get('model_sha256')})
    socket_rows = []
    for path in sorted(session.glob('socket_smoke*/socket_summary.json')):
        socket_rows.append({'run_id': path.parent.name, 'sha256': sha(path), **read(path)})
    require(any(r['rows'] and all(x.get('exit_code') == 0 and x.get('response_sent') for x in r['rows'])
                for r in socket_rows), 'Missing successful socket session')
    environment = (board / 'build/build_environment.txt').read_text().splitlines()
    status = {
        'schema_version': 1, 'status': 'FILE_PIPELINE_EXECUTED_NUMERIC_REVIEW_PENDING',
        'scope': '50 validation sample/split pairs, PUBLIC_TEST_ONLY, file transport; TCP HOST smoke separately',
        'unique_ecg_samples': len({v['sample_id'] for v in vectors}), 'class_order': list(i1.CLASS_ORDER),
        'manifest_sha256': PACKAGE_ANCHOR, 'reference_vectors': 50, 'kv260_vectors': 50,
        'kv260_root_tail_calls': 46, 's10_identity_vectors': 4,
        'reference_class_matches': sum(r['class_match'] for r in rows if r['backend'] == 'reference'),
        'kv260_class_matches': sum(r['class_match'] for r in rows if r['backend'] == 'kv260'),
        'reference_max_abs_error': max(r['max_abs_error'] for r in rows if r['backend'] == 'reference'),
        'kv260_max_abs_error': max(r['max_abs_error'] for r in rows if r['backend'] == 'kv260'),
        'numeric_acceptance': 'PENDING_TEAM_REVIEW', 'independent_test_accuracy': 'NOT_MEASURED',
        'ble_device_kv260': 'NOT_TESTED', 'service_latency_throughput': 'NOT_MEASURED',
    }
    a.output.mkdir(parents=True)
    dump(a.output / 'status.json', status)
    dump(a.output / 'cases.json', {'schema_version': 1, 'rows': rows})
    dump(a.output / 'socket.json', {'schema_version': 1, 'runs': socket_rows})
    provenance = {
        'schema_version': 1, 'source_run_id': session.name, 'processing_version': 1,
        'exporter_sha256': sha(__file__), 'archive_sha256': a.expected_archive_sha256,
        'archive_storage': 'Original local evidence archive, excluded from Git',
        'archive_files_verified': archive_files_verified,
        'source_checksums_ok': checksums, 'source_inventory_files_ok': source_inventory_count,
        'binary_sha256': binary_hash, 'build_utc': environment[0], 'architecture': environment[1],
        'compiler': environment[2], 'measured_source_sha256': {dest: sha(board / 'source' / src)
                                                            for src, dest in source_mapping.items()},
        'measured_snapshot_files_sha256': {p.relative_to(board / 'source').as_posix(): sha(p)
                                         for p in sorted((board / 'source').rglob('*')) if p.is_file()},
        'model_hashes': preflight['model_hashes'], 'evidence': evidence_hashes,
        'host_verifier_receipts_sha256': {name: sha(session / name) for name in ['p1_host_A.json', 'p1_host_B.json']},
    }
    dump(a.output / 'provenance.json', provenance)
    for name in ['p1_host_A.json', 'p1_host_B.json']:
        d = read(session / name)
        d.pop('C_build', None)  # Compiler command contains machine-specific paths.
        dump(a.output / name, d)
    with (a.output / 'by_split.csv').open('x', newline='') as stream:
        fields = ['backend', 'split', 'vector_count', 'class_matches', 'max_abs_error']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for label in ['reference', 'kv260']:
            for split in range(11):
                group = [r for r in rows if r['backend'] == label and r['split'] == split]
                writer.writerow(dict(backend=label, split=split, vector_count=len(group),
                                     class_matches=sum(r['class_match'] for r in group),
                                     max_abs_error=max(r['max_abs_error'] for r in group)))
    files = sorted(a.output.iterdir())
    (a.output / 'sha256sum_export.txt').write_text(''.join(sha(p) + '  ' + p.name + '\n' for p in files))
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()
