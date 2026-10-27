#!/usr/bin/env python3
"""Export small Week 8 results from pinned, saved KV260 evidence; never infer."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import tarfile
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'nhan_sau_g2/after_g2.tar.gz': '017298062c086407d94d0c1a9b28df676a06794a50505a3ba85702895119d935',
    'gui_sv1_g2.zip': '0d376d369a20eface170d62d5808998d888133d424913c0f0378defe5a7d078e',
    'bo_sung_link/nhan_request/gui_sv1_bo_sung.zip': 'ee1298b3f9201a211af6f51f5f1d2a5aa9730d43cee568914cf70c62e18b53ab',
    'inputs/reference_s2.npz': 'e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def inventory(folder, required):
    entries = (folder / 'sha256sum_results.txt').read_text().splitlines()
    names = set()
    for line in entries:
        expected, name = line.split(maxsplit=1)
        name = name.lstrip('* ')
        path = folder / name
        require(not path.is_symlink() and folder.resolve() in path.resolve().parents, 'Unsafe checksum path')
        require(name not in names and sha(path) == expected, 'Checksum differs: ' + str(path))
        names.add(name)
    require(set(required) <= names, 'Required evidence not covered by checksum')
    return len(entries)


def stats(values):
    data = np.asarray(values, dtype=float)
    return {'count': len(values), 'min': float(data.min()), 'mean': float(data.mean()),
            'std': float(data.std()), 'p95': float(np.percentile(data, 95)), 'max': float(data.max())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    require(not a.output.exists(), 'Output exists; choose a new directory')
    session = a.session.resolve()
    for name, expected in PINS.items():
        require(sha(session / name) == expected, 'Pinned input/archive differs: ' + name)
    board = session / 'nhan_sau_g2/ho_so'
    # Compare extracted bytes to the independently pinned received archive.
    archive_count = 0
    with tarfile.open(session / 'nhan_sau_g2/after_g2.tar.gz') as archive:
        for member in archive:
            require(member.isfile() or member.isdir(), 'Unexpected archive type')
            if member.isfile():
                path = board / member.name
                require(board in path.resolve().parents, 'Unsafe archived path')
                require(sha(path) == digest(archive.extractfile(member).read()), 'Extracted bytes differ')
                archive_count += 1
    # Two ZIPs pin the second offline run and the supplemental raw evidence.
    with zipfile.ZipFile(session / 'gui_sv1_g2.zip') as archive:
        require(archive.testzip() is None, 'G2 ZIP CRC differs')
        for path in (session / 'nhan_offline_lan_2/offline_second').iterdir():
                require(path.is_file() and path.read_bytes() == archive.read('review/offline_second/' + path.name),
                    'Second offline differs from review ZIP')
    supplemental = session / 'bo_sung_link/nhan_request/raw'
    with zipfile.ZipFile(session / 'bo_sung_link/nhan_request/gui_sv1_bo_sung.zip') as archive:
        require(archive.testzip() is None, 'Supplement ZIP CRC differs')
        for path in supplemental.rglob('*'):
            if path.is_file():
                require(path.read_bytes() == archive.read('raw/' + path.relative_to(supplemental).as_posix()),
                        'Supplement raw differs from pinned ZIP')
    with np.load(session / 'inputs/reference_s2.npz', allow_pickle=False) as data:
        q = data['q'].copy()
        scales = data['scale_f16'].copy()
        reference = data['logits'].copy()
        labels = data['label_ref'].copy()
    require(q.shape == (100, 16, 180) and scales.shape == (100, 16), 'Reference shape differs')
    require(np.array_equal(reference.argmax(1), labels), 'Reference labels differ')
    mapping = {(digest(q[i].tobytes()), digest(scales[i].astype('<f2').tobytes())): i for i in range(100)}
    require(len(mapping) == 100, 'Ambiguous q/scale mapping')
    first, second = board / 'offline_100', session / 'nhan_offline_lan_2/offline_second'
    counts = {}
    offline = []
    backend = None
    for name, folder in [('offline_first', first), ('offline_second', second)]:
        counts[name] = inventory(folder, ['run.json', 'predictions.jsonl', 'summary.json'])
        rows = records(folder / 'predictions.jsonl')
        require([r['sample_index'] for r in rows] == list(range(100)), 'Offline indices differ')
        run = read(folder / 'run.json')
        identity = {key: run[key] for key in ('model_sha256', 'worker_sha256', 'plugins')}
        if backend is None:
            backend = identity
        require(identity == backend, 'Offline backend differs')
        for i, row in enumerate(rows):
            require([struct.pack('<f', x).hex() for x in row['logits']] == row['logits_hex_le'], 'Offline logits bits differ')
            require(row['label'] == int(np.argmax(row['logits'])) and row['label_ref'] == int(labels[i]), 'Offline labels differ')
        offline.append(rows)
    repeat = sum(x['logits_hex_le'] == y['logits_hex_le'] for x, y in zip(*offline))
    all_cases, source_versions = [], {}
    for name, folder, expected in [('g2_212', board / 'sv1_session', 212),
                                   ('supp1', supplemental / 'trial1', 1),
                                   ('supp2', supplemental / 'trial2', 10),
                                   ('supp4', supplemental / 'trial3_2m', 10)]:
        counts[name] = inventory(folder, ['run.json', 'peer.jsonl', 'events.jsonl'])
        run = read(folder / 'run.json')
        require({key: run['backend'][key] for key in backend} == backend, 'Radio backend differs')
        source_versions[name] = run['source_sha256']
        rows = records(folder / 'peer.jsonl')
        require(len(rows) == expected and len({r['request_id'] for r in rows}) == expected, 'Request count/ID differs')
        require(len({r['connection'] for r in rows}) == 1, 'Radio reconnected within trial')
        sequences = [r['sequence'] for r in rows if r['rho'] == 'P1']
        require(all(isinstance(x, int) for x in sequences) and all(y > x for x, y in zip(sequences, sequences[1:])), 'P1 sequence differs')
        events = records(folder / 'events.jsonl')
        connected = [e for e in events if e['event'] == 'connected']
        require(len(connected) == 1 and connected[0]['att_mtu'] == 247, 'Actual MTU/connection differs')
        sample_indices = []
        for j, row in enumerate(rows):
            require(row['result'] == 'OK' and row['response_sent'] and not row.get('cache_hit'), 'Request failed/retried')
            i = mapping[(row['q_sha256'], row['scale_fp16_sha256'])]
            require(row['scale_sha256'] == digest(scales[i].astype('<f4').tobytes()), 'FP32 scale hash differs')
            require(row['logits_hex_le'] == offline[0][i]['logits_hex_le'], 'Radio/offline bits differ')
            require(row['logits_hex_le'] == [struct.pack('<f', x).hex() for x in row['logits_float']], 'Numeric logits differ')
            sample_indices.append(i)
            all_cases.append({'trial': name, 'request_index': j + 1, 'sample_index': i,
                              'rho': row['rho'], 'sequence': row['sequence'], 'label': row['label'],
                              'reference_label': int(labels[i]), 'bit_match_offline': True,
                              'tail_ms': row['tail_ms'], 'edge_rx_to_tx_submit_ms': row['t_tx_done_ms'] - row['t_rx_ms']})
        if name == 'g2_212':
            require(sample_indices == [0, 0] + [i for i in range(5) for _ in range(2)] + [i for i in range(100) for _ in range(2)], 'G2 stage/sample order differs')
        else:
            require(sample_indices == ([0] if expected == 1 else [i for i in range(5) for _ in range(2)]), 'Supplement sample order differs')
        # Each pair must contain both modes, regardless of which mode came first.
        start = 0 if name != 'g2_212' else 2
        if expected > 1:
            for j in range(start, expected, 2):
                require({rows[j]['rho'], rows[j+1]['rho']} == {'P0', 'P1'}, 'Missing P0/P1 pair')
    g2 = [r for r in all_cases if r['trial'] == 'g2_212']
    per_class = [{'class': c, 'reference_count': int(sum(labels == i)),
                  'class_matches': sum(r['label'] == i and r['label_ref'] == i for r in offline[0])}
                 for i, c in enumerate(['N', 'S', 'V', 'F', 'Q'])]
    source_paths = {
        'g2_service': board / 'ble_update/edge/server/week8/ble_service.py',
        'supplement_service': supplemental / 'source/edge/server/week8/ble_service.py',
        'persistent_worker': board / 'source/edge/runtime/persistent/tail_worker.cpp',
    }
    require(sha(source_paths['g2_service']) == source_versions['g2_212'], 'G2 source receipt differs')
    require(all(sha(source_paths['supplement_service']) == source_versions[n] for n in ('supp1', 'supp2', 'supp4')), 'Supplement source receipt differs')
    parity = board / 'parity_3_lan_2'
    counts['parity'] = inventory(parity, ['summary.json', 'comparison.json', 'sample_000/single.json'])
    require(read(parity / 'summary.json')['bit_exact'], 'Native parity failed')
    status = {'schema_version': 1, 'scope': 'SAVED_KV260_EVIDENCE_HOST_VERIFIED',
              'radio_requests': 212, 'g2_requests': 200, 'g2_bit_matches_offline': 200,
              'supplement_requests': 21, 'supplement_bit_matches_offline': 21,
              'offline_repeat_bit_matches': repeat, 'reference_class_matches': sum(r['class_match'] for r in offline[0]),
              'reference_samples': 100, 'per_class_reference_agreement': per_class,
              'tail_ms': stats([r['tail_ms'] for r in g2]),
              'edge_rx_to_tx_submit_ms': stats([r['edge_rx_to_tx_submit_ms'] for r in g2]),
              'independent_test_accuracy': 'NOT_MEASURED', 'supplement_full_hci_trace': 'NOT_RECOVERED',
              'nonce_registry_joint_acceptance': 'PENDING_R2_REVIEW',
              'device_g2_acceptance': 'SV1_REPORTED_PASS_2026_10_27',
              'device_review_source': 'SV1 review relayed by SV2 on 2026-10-27; original Device report/PR absent from fetched branches',
              'worker_backend': backend, 'service_sha256': source_versions}
    provenance = {'schema_version': 1, 'exporter_sha256': sha(__file__), 'pinned_inputs': PINS,
                  'received_archive_files_verified': archive_count, 'checksum_files_verified': counts,
                  'measured_source_sha256': {k: sha(p) for k, p in source_paths.items()},
                  'current_checkout_service_matches_supplement': sha(ROOT / 'edge/server/week8/ble_service.py') == source_versions['supp4'],
                  'trial_mapping': {'supp1': 'trial1', 'supp2': 'trial2', 'supp4': 'trial3_2m'},
                  'receipts': {str(p.relative_to(session)): sha(p) for p in source_paths.values()},
                  'root_tensor_receipt': read(parity / 'sample_000/single.json')}
    a.output.mkdir(parents=True)
    write(a.output / 'summary.json', status)
    write(a.output / 'provenance.json', provenance)
    with (a.output / 'requests.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_cases[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(all_cases)
    with (a.output / 'offline.csv').open('x', newline='') as stream:
        keys = ['sample_index', 'label', 'label_ref', 'class_match', 'max_abs_error', 'tail_ms']
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(offline[0])
    write(a.output / 'source_versions.json', {
        'g2_212': {'service_sha256': source_versions['g2_212'], 'note': 'Before hold-after-count patch'},
        'supplement': {'service_sha256': source_versions['supp4'], 'note': 'Same service in all three trials; final max-s 1800 instead of 900'},
        'persistent_worker_sha256': sha(source_paths['persistent_worker'])})
    # Small export carries derived values only; raw tensors/models/keys stay local.
    with (a.output / 'sha256sum_export.txt').open('x') as stream:
        for path in sorted(a.output.iterdir()):
            if path.name != 'sha256sum_export.txt':
                stream.write(sha(path) + '  ' + path.name + '\n')
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()
