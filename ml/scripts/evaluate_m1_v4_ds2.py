"""FP32 DS2 report for M1 v4 (protocol v4 ds2_report) on the three locked C5 checkpoints.

`dry-run` runs the same prediction and reporting path on DS1 validation and must reproduce the locked
validation confusion of every checkpoint; it never opens a DS2 file. `ds2` refuses to start without an
external authorization that binds the checkpoint lock, the SV2 xmodel lock and this script, and writes
to one fixed path so the evaluation cannot be repeated. Neither the dry run nor the tests run `ds2`.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import statistics
import sys
from pathlib import Path

import numpy as np
import torch

import package_m1_v4_a as pkg
from m1_metrics_v4 import CLASSES, confusion, ds2_reporting_metrics
from week3_common import need, read_json, sha, text, write_json

ROOT = pkg.ROOT
PROTOCOL = 'ml/configs/mitdb_m1_baseline_protocol_v4.json'
MANIFEST = 'ml/manifests/mitdb-ds1ds2-m1-v3-r2/processed-manifest.json'
DS2_OUTPUT = 'ml/data/ds2-m1-v4-fp32'
EXCLUDED_FROM_MAIN = '202'  # Same patient as 201 in DS1 train; test_main = test_aux22 without it.
DRY_RUN_EXCLUDED = '118'  # Lowest validation record; only exercises the subset path in the dry run.
BATCH = 256
REPORTED = ['accuracy', 'macro_f1_NSVF_fixed4', 'macro_f1_NSVFQ_fixed5', 'Se_S', 'P_S', 'Se_V', 'P_V']
PREDICTION_FIELDS = ['seed', 'role', 'row_index', 'record_id', 'patient_id', 'r_peak_sample', 'original_symbol',
                     'true_class', 'predicted_class', 'logit_N', 'logit_S', 'logit_V', 'logit_F', 'logit_Q']


def configure(device):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    # Strict FP32 reference: cuDNN TF32 convolutions (PyTorch default on) moved logits by ~5e-3 against CPU on validation.
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    need(device in ('cpu', 'cuda') and (device == 'cpu' or torch.cuda.is_available()), 'Device must be cpu or an available cuda')
    return torch.device(device)


def checkpoints():
    """The three locked C5 checkpoints, deployment first, each with its training slot config."""
    lock, _, plan, _ = pkg.locked()
    out = []
    for c in sorted(lock['checkpoints'], key=lambda c: c['role'] != 'deployment'):
        need(pkg.sha(ROOT/c['path']) == c['sha256'], f"Checkpoint differs from lock: {c['slot_id']}")
        slot = next(s for s in plan['slots'] if s['slot_id'] == c['slot_id'])
        config = ROOT/Path(pkg.PLAN).parent/slot['config']
        need(sha(config) == slot['sha256'], f"Slot config differs: {c['slot_id']}")
        out.append((c, config))
    need(len(out) == 3 and out[0][0]['role'] == 'deployment', 'Expected one deployment and two seed checkpoints')
    return lock, out


def read_split(name):
    """One processed split, each file checked against the processed manifest before loading."""
    artifacts = read_json(ROOT/MANIFEST)['artifacts']
    for suffix in ('_X.npy', '_y.npy', '_metadata.csv'):
        need(sha(ROOT/pkg.ARRAYS/(name+suffix)) == artifacts[name+suffix]['sha256'], f'{name}{suffix} differs from manifest')
    x = np.load(ROOT/pkg.ARRAYS/f'{name}_X.npy', allow_pickle=False)
    y = np.load(ROOT/pkg.ARRAYS/f'{name}_y.npy', allow_pickle=False)
    with (ROOT/pkg.ARRAYS/f'{name}_metadata.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    need(x.dtype == np.dtype('<f4') and x.shape == (len(y), 360) and len(rows) == len(y), f'{name} contract differs')
    need(bool(np.isfinite(x).all()) and [int(r['class_index']) for r in rows] == y.tolist(), f'{name} labels or values differ')
    return x, y, rows


def predict(model, x, device):
    model.eval()
    logits = []
    with torch.no_grad():
        for i in range(0, len(x), BATCH):
            batch = torch.from_numpy(np.ascontiguousarray(x[i:i+BATCH])).reshape(-1, 1, 360).to(device)
            logits.append(model(batch).float().cpu().numpy())
    out = np.concatenate(logits)
    need(out.shape == (len(x), 5) and bool(np.isfinite(out).all()), 'Logits differ from contract')
    return out


def row_report(y, pred, rows):
    m = ds2_reporting_metrics(y, pred)
    m.update(Se_S=m['recall'][1], P_S=m['precision'][1], Se_V=m['recall'][2], P_V=m['precision'][2], Q_beats=int(m['support'][4]))
    records = sorted({r['record_id'] for r in rows}, key=int)
    ids = np.array([r['record_id'] for r in rows])
    m['per_record_confusion_descriptive'] = {r: confusion(y[ids == r], pred[ids == r]).tolist() for r in records}
    m['S_beats_per_record'] = {r: int((y[ids == r] == 1).sum()) for r in records}
    return m


def report(y, pred, rows, excluded, names):
    """Both rows from one prediction pass: `names[1]` is everything, `names[0]` drops the excluded record."""
    keep = np.array([r['record_id'] != excluded for r in rows])
    need(keep.any() and not keep.all(), 'Excluded record must split the rows')
    main = row_report(y[keep], pred[keep], [r for r, k in zip(rows, keep) if k])
    full = row_report(y, pred, rows)
    need((np.array(main['confusion_matrix']) + confusion(y[~keep], pred[~keep]) == np.array(full['confusion_matrix'])).all(),
         'Row confusions are not one partition')
    return {names[0]: main, names[1]: full}, keep


def statistics_over_seeds(per_seed, row):
    out = {}
    for key in REPORTED:
        values = [s['rows'][row][key] for s in per_seed]
        out[key] = {'per_seed': {str(s['seed']): s['rows'][row][key] for s in per_seed},
                    'mean': statistics.fmean(values), 'sd_ddof1': statistics.stdev(values)}
    return out


def literature(per_seed, row):
    deployment = per_seed[0]['rows'][row]
    mean = statistics_over_seeds(per_seed, row)
    out = io.StringIO(newline='')
    w = csv.writer(out, lineterminator='\n')
    w.writerow(['id', 'lead', 'uses_RR', 'notes', 'reported_Se_S', 'reported_P_S', 'reported_Se_V', 'reported_P_V',
                'project_deployment_Se_S', 'project_deployment_P_S', 'project_deployment_Se_V', 'project_deployment_P_V',
                'project_mean_Se_S', 'project_mean_P_S', 'project_mean_Se_V', 'project_mean_P_V'])
    for p in read_json(ROOT/PROTOCOL)['baseline']['ds2_report']['literature_comparison']['papers']:
        r = p['reported_percent']
        w.writerow([p['id'], p['lead'], p['uses_RR'], p['notes'], r['Se_S'], r['+P_S'], r['Se_V'], r['+P_V'],
                    *[100*deployment[k] for k in ('Se_S', 'P_S', 'Se_V', 'P_V')], *[100*mean[k]['mean'] for k in ('Se_S', 'P_S', 'Se_V', 'P_V')]])
    return out.getvalue()


def prediction_rows(seed, role, logits, pred, y, rows):
    return [[seed, role, i, r['record_id'], r['patient_id'], r['r_peak_sample'], r['original_symbol'], int(y[i]), int(pred[i]),
             *[repr(float(v)) for v in logits[i]]] for i, r in enumerate(rows)]


def evaluate(split, excluded, names, device, output, check=None):
    """Shared path of the dry run and the DS2 pass: one prediction pass per checkpoint, two report rows."""
    dev = configure(device)
    lock, entries = checkpoints()
    x, y, rows = read_split(split)
    output.mkdir(parents=True)
    table, per_seed = [], []
    for entry, config in entries:
        model = pkg.load_model(entry, config).to(dev)
        logits = predict(model, x, dev)
        pred = logits.argmax(1)
        result, _ = report(y, pred, rows, excluded, names)
        if check is not None:
            check(entry, result[names[1]]['confusion_matrix'])
        per_seed.append({'seed': entry['seed'], 'role': entry['role'], 'slot_id': entry['slot_id'], 'checkpoint_sha256': entry['sha256'], 'rows': result})
        table += prediction_rows(entry['seed'], entry['role'], logits, pred, y, rows)
    out = io.StringIO(newline='')
    w = csv.writer(out, lineterminator='\n')
    w.writerow(PREDICTION_FIELDS)
    w.writerows(table)
    text(output/'predictions.csv', out.getvalue())
    text(output/'literature-comparison.csv', literature(per_seed, names[1]))
    environment = {'device': str(dev), 'device_name': torch.cuda.get_device_name(dev) if dev.type == 'cuda' else 'CPU',
                   'torch': torch.__version__, 'cuda': torch.version.cuda, 'python': sys.version.split()[0], 'batch_size': BATCH,
                   'deterministic': True, 'threads': 1, 'cudnn_allow_tf32': torch.backends.cudnn.allow_tf32,
                   'matmul_allow_tf32': torch.backends.cuda.matmul.allow_tf32}
    summary = {'split_read': split, 'rows': names, 'excluded_record_for_first_row': excluded, 'checkpoint_lock_sha256': pkg.LOCK_SHA,
               'script_sha256': sha(Path(__file__)), 'environment': environment, 'per_seed': per_seed,
               'statistics': {n: statistics_over_seeds(per_seed, n) for n in names},
               'deployment_reported_separately': per_seed[0], 'note': 'Sample SD over 3 seeds is descriptive, not a confidence interval',
               'per_record_confusion': 'Descriptive addition declared in the checkpoint lock before DS2; not a ds2_report metric',
               'files_sha256': {f: sha(output/f) for f in ('predictions.csv', 'literature-comparison.csv')}}
    write_json(output/'summary.json', summary)
    return summary


def dry_run(output, device):
    output = Path(output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Output must be a new path under ignored ml/data')
    lock = read_json(ROOT/pkg.LOCK)
    analysis = read_json(ROOT/lock['bindings']['analyze_stdout']['path'])
    config = next(c for c in analysis['configurations'] if c['configuration'] == lock['selection']['configuration'])
    expected = {s['seed']: s['validation']['confusion_matrix'] for s in config['seeds']}
    matched = []
    def check(entry, matrix):
        need(matrix == expected[entry['seed']], f"Validation confusion differs from the locked summary: {entry['slot_id']}")
        matched.append(entry['slot_id'])
    summary = evaluate('val', DRY_RUN_EXCLUDED, [f'validation_without_{DRY_RUN_EXCLUDED}', 'validation_all'], device, output, check)
    need(len(matched) == 3, 'Not every checkpoint was checked')
    summary['dry_run'] = {'status': 'VALIDATION_CONFUSION_REPRODUCED_FOR_3_C5_CHECKPOINTS', 'matched': matched, 'DS2_opened': False}
    write_json(output/'summary.json', summary)
    return summary['dry_run']


def require_authorization(path):
    need(path is not None and Path(path).is_file(), 'DS2 needs an external authorization file; none given')
    a = read_json(path)
    hexsha = lambda v: isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) is not None
    need(a.get('type') == 'M1_V4_DS2_FP32_AUTHORIZATION' and a.get('checkpoint_lock_sha256') == pkg.LOCK_SHA and
         a.get('script_sha256') == sha(Path(__file__)) and hexsha(a.get('xmodel_lock_sha256')) and hexsha(a.get('review_evidence')) and
         a.get('device') in ('cpu', 'cuda') and bool(a.get('approved_by')),
         'Authorization does not bind the checkpoint lock, xmodel lock, review, device and this script')
    return a


def ds2(authorization):
    a = require_authorization(authorization)  # Before any DS2 path is touched.
    output = (ROOT/DS2_OUTPUT).resolve()
    need(not output.exists(), 'DS2 output exists: protocol v4 allows one evaluation only')
    main_x, main_y, main_rows = read_split('test_main')
    summary = evaluate('test_aux22', EXCLUDED_FROM_MAIN, ['test_main', 'test_aux22'], a['device'], output)
    x, y, rows = read_split('test_aux22')
    keep = np.array([r['record_id'] != EXCLUDED_FROM_MAIN for r in rows])
    need(np.array_equal(x[keep], main_x) and np.array_equal(y[keep], main_y) and [r for r, k in zip(rows, keep) if k] == main_rows,
         'test_main is not test_aux22 without record 202; preprocessing differs')
    summary['test_main_equals_aux22_without_202'] = True
    write_json(output/'summary.json', summary)
    return {'status': 'DS2_FP32_EVALUATED_ONCE', 'output': DS2_OUTPUT}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['dry-run', 'ds2'])
    p.add_argument('--output', type=Path)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    p.add_argument('--authorization', type=Path)
    a = p.parse_args()
    if a.mode == 'dry-run':
        need(a.output is not None, 'dry-run needs --output')
        print(json.dumps(dry_run(a.output, a.device), indent=2))
    else:
        print(json.dumps(ds2(a.authorization), indent=2))


if __name__ == '__main__':
    main()
