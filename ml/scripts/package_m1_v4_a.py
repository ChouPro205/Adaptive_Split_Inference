"""Package A of M1 v4: the locked deployment checkpoint, its firmware header, architecture and tensor
assertions, normalization, data manifests and train-only golden tensors, in a NEW output directory.

Reads only the train/val arrays bound by plan v4; DS2 arrays are never opened. DS2 predictions
(v1.2 section 4.3) are not part of this package: they follow the SV2 xmodel lock.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

from week3_common import FIELDS, MODEL_HASH, compiler_verify, fp32, header, need, read_json, same_bits, sha, text, write_json
from week3_sv2_common import CUTS, OPS, SHAPES, configure, split_map, wrappers
from week4_common import graph_parameters, inventory

ROOT = Path(__file__).resolve().parents[2]
LOCK = 'ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json'
LOCK_SHA = '6848b08dc1f4f55d7d66a4e36b719d55c92eabf37b0c6edbbfdd6b921047d0bc'
PLAN = 'ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json'
ARRAYS = 'ml/data/processed/mitdb-ds1ds2-m1-v3-r2'
MODEL_SOURCE = 'ml/src/mitdb_baseline_model.py'
REGISTRY = 'contracts/sv3_week5_approved_registry_v2.json'
FREEZE = 'ml/configs/week3_model_freeze.json'
DATA_COPIES = {'data/normalization.json': 'ml/manifests/mitdb-ds1ds2-m1-v3-r2/normalization.json',
               'data/processed-manifest.json': 'ml/manifests/mitdb-ds1ds2-m1-v3-r2/processed-manifest.json',
               'data/split.csv': 'ml/manifests/mitdb-ds1ds2-m1-v3-r2/split.csv',
               'data/metric-policy.json': 'ml/manifests/mitdb-ds1ds2-m1-v3-r2/metric-policy.json'}
PARAMETERS = 109653
COMPARISON_RULE = 'sort_numeric_record_id_then_numeric_r_peak_sample_then_lead_name_take_first_20'
CALIBRATION_RULE = 'np.unique(np.linspace(0, n_train-1, min(count, n_train)).round().astype(int64)) over train_X rows'
STATUS = 'CANDIDATE_PENDING_SV2_CALIBRATION_CONFIRMATION_NOT_DELIVERED'


def locked():
    """Bind the package to the checkpoint lock, its deployment checkpoint and the training slot config."""
    need(sha(ROOT/LOCK) == LOCK_SHA, 'Checkpoint lock differs')
    lock = read_json(ROOT/LOCK)
    deployment = [c for c in lock['checkpoints'] if c['role'] == 'deployment']
    need(len(deployment) == 1 and lock['ds2']['status'] == 'NOT_OPENED', 'Lock deployment/DS2 state differs')
    deployment = deployment[0]
    need(sha(ROOT/deployment['path']) == deployment['sha256'], 'Deployment checkpoint differs from lock')
    need(sha(ROOT/MODEL_SOURCE) == MODEL_HASH, 'Model architecture source changed')
    plan = read_json(ROOT/PLAN)
    need(sha(ROOT/PLAN) == lock['bindings']['plan_manifest']['sha256'], 'Plan differs from lock')
    slot = next(s for s in plan['slots'] if s['slot_id'] == deployment['slot_id'])
    config_path = ROOT/Path(PLAN).parent/slot['config']
    need(sha(config_path) == slot['sha256'], 'Slot config differs from plan')
    return lock, deployment, plan, config_path


def load_model(deployment, config):
    checkpoint = torch.load(ROOT/deployment['path'], map_location='cpu', weights_only=True)
    need(checkpoint['epoch'] == deployment['selected_epoch'] and checkpoint['config_sha256'] == sha(config), 'Checkpoint identity differs')
    source = (ROOT/MODEL_SOURCE).read_bytes()
    module = {'__name__': 'm1_v4_package_model'}
    exec(compile(source, str(ROOT/MODEL_SOURCE), 'exec'), module)  # The authenticated bytes, not a cached .pyc.
    model = module['MitdbBaselineCNN'](read_json(config)['dropout'])
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    model.eval()
    need(not any(isinstance(m, torch.nn.modules.batchnorm._BatchNorm) for m in model.modules()), 'Unexpected BatchNorm')
    need(sum(p.numel() for p in model.parameters()) == PARAMETERS, 'Parameter count differs')
    return model


def arrays(plan):
    """Train/val only, each checked against the plan binding before loading."""
    out = {}
    for name, expected in plan['binding']['data_files'].items():
        need(not name.startswith('test'), 'DS2 file in plan binding')
        need(sha(ROOT/ARRAYS/name) == expected['sha256'], f'Array differs from plan: {name}')
    for split in ('train', 'val'):
        x = np.load(ROOT/ARRAYS/f'{split}_X.npy', allow_pickle=False)
        y = np.load(ROOT/ARRAYS/f'{split}_y.npy', allow_pickle=False)
        with (ROOT/ARRAYS/f'{split}_metadata.csv').open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        need(x.dtype == np.float32 and x.ndim == 2 and x.shape[1] == 360 and len(x) == len(y) == len(rows), f'{split} arrays differ')
        out[split] = (x, y, rows)
    return out


def comparison_indices(rows):
    order = sorted(range(len(rows)), key=lambda i: (int(rows[i]['record_id']), int(rows[i]['r_peak_sample']), rows[i]['lead_name'], i))
    return order[:20]


def calibration_indices(n_train, count):
    """Same even spacing as SV2 edge/quantize_tail.py calibration_inputs, applied to DS1 train only."""
    need(type(count) is int and count >= 1, 'Calibration count must be a positive integer')
    return np.unique(np.linspace(0, n_train-1, min(count, n_train)).round().astype(np.int64)).tolist()


def boundaries(model, x):
    """One N=1 pass through the frozen leaf modules; z_s is the output after CUTS[s] leaves."""
    leaves = [m for n, m in model.named_modules() if n and not list(m.children())]
    need(len(leaves) == len(OPS), 'Leaf operation count differs')
    z, out = torch.from_numpy(fp32(x.reshape(1, 1, 360))), []
    with torch.no_grad():
        for index in range(len(OPS)+1):
            if index in CUTS:
                out.append(fp32(z.numpy()))
            if index < len(OPS):
                z = leaves[index](z)
    return out


def golden(model, x, indices):
    per_sample = [boundaries(model, x[i]) for i in indices]
    return [fp32(np.concatenate([p[s] for p in per_sample])) for s in range(11)]


def sample_rows(rows, indices, split):
    return [{'sample_index': k, 'sample_id': f"MIT-BIH:{rows[i]['record_id']}:{rows[i]['r_peak_sample']}:{rows[i]['lead_name']}",
             'dataset_profile': 'MIT-BIH/1.0.0', 'split': split, 'patient_id': rows[i]['patient_id'],
             'record_id': rows[i]['record_id'], 'r_peak_sample': rows[i]['r_peak_sample'], 'lead_name': rows[i]['lead_name'],
             'lead_index': rows[i]['lead_index'], 'source_metadata_path': f'{ARRAYS}/{split}_metadata.csv',
             'source_row_index': i, 'original_symbol': rows[i]['original_symbol'], 'aami_class': rows[i]['aami_class'],
             'class_index': rows[i]['class_index']} for k, i in enumerate(indices)]


def samples_csv(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def architecture(model, comparison_x, z):
    """Executed boundary shapes must equal the Week 3 split convention, registry v2 and the frozen M_final."""
    registry = {r['split_point_s']: r for r in read_json(ROOT/REGISTRY)['splits']}
    freeze = read_json(ROOT/FREEZE)
    need(freeze['model_source_sha256'] == MODEL_HASH and tuple(freeze['boundary']['shape_N1']) == SHAPES[2], 'Week 3 freeze differs')
    rows = []
    with torch.no_grad():
        for entry in split_map():
            s = entry['split_id']
            head, tail = wrappers(model, s)
            for i in range(len(comparison_x)):
                h = fp32(head(torch.from_numpy(fp32(comparison_x[i:i+1]))).numpy())
                need(same_bits(h, z[s][i:i+1]), f'Golden activation differs from head_{s}: sample {i}')
                logits = fp32(tail(torch.from_numpy(h)).numpy())
                need(same_bits(logits, z[10][i:i+1]), f'Head+tail logits differ from full model: s{s} sample {i}')
            shape = list(z[s].shape[1:])
            need([1, *shape] == entry['shape_N1'] == registry[s]['shape_original'], f'Split shape differs: s{s}')
            numel = int(np.prod(shape))
            rows.append({'s': s, 'boundary': entry['head_endpoint'], 'shape_N1': [1, *shape], 'dtype': 'float32', 'numpy_dtype': '<f4',
                         'layout': entry['layout'], 'flatten_order': 'C', 'numel_per_sample': numel, 'bytes_fp32': 4*numel,
                         'bytes_int8_logical': numel, 'registry_v2_shape_original': registry[s]['shape_original'],
                         'registry_v2_max_payload_bytes': registry[s]['max_payload_bytes'], 'head_operations': len(entry['head_operations'])})
    return {'model_source_sha256': MODEL_HASH, 'parameter_count': PARAMETERS, 'operations': list(OPS), 'cuts': list(CUTS),
            'week3_freeze_M_final': freeze['boundary']['M_final'], 'splits': rows,
            'checks': ['executed shapes == Week 3 split convention == registry v2 shape_original for s0-s10',
                       'golden z_s == head_s(x) bitwise on CPU for the 20 comparison samples',
                       'tail_s(head_s(x)) == full-model logits bitwise for every s', 'no BatchNorm; eval mode; strict state_dict load']}


def validation_reload(model, x, y, lock, deployment):
    """CPU reload must reproduce the locked validation confusion (rows true, columns predicted)."""
    analysis = read_json(ROOT/lock['bindings']['analyze_stdout']['path'])
    config = next(c for c in analysis['configurations'] if c['configuration'] == lock['selection']['configuration'])
    expected = next(s for s in config['seeds'] if s['seed'] == deployment['seed'])['validation']['confusion_matrix']
    with torch.no_grad():
        pred = np.concatenate([model(torch.from_numpy(fp32(x[i:i+256]).reshape(-1, 1, 360))).argmax(1).numpy() for i in range(0, len(x), 256)])
    matrix = np.zeros((5, 5), dtype=np.int64)
    np.add.at(matrix, (y.astype(np.int64), pred), 1)
    need(matrix.tolist() == expected, 'CPU validation confusion differs from the locked result')
    return {'device': 'cpu', 'batch_size': 256, 'samples': int(len(x)), 'confusion_matrix': matrix.tolist(), 'matches_locked_validation': True}


def build(output, calibration_count):
    output = Path(output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Output must be a new path under ignored ml/data')
    configure()
    lock, deployment, plan, config = locked()
    model = load_model(deployment, config)
    data = arrays(plan)
    train_x, _, train_rows = data['train']
    compare = comparison_indices(train_rows)
    calibrate = calibration_indices(len(train_x), calibration_count)
    z = golden(model, train_x, compare)
    arch = architecture(model, z[0], z)
    check = validation_reload(model, data['val'][0], data['val'][1], lock, deployment)
    graph, parameters = graph_parameters(model, z[0])
    graph.update(model_revision='m1_v4_C5_seed20261101_epoch4', checkpoint_sha256=deployment['sha256'])
    (output/'model').mkdir(parents=True)
    shutil.copyfile(ROOT/deployment['path'], output/'model/checkpoint.pt')
    shutil.copyfile(ROOT/MODEL_SOURCE, output/'model/mitdb_baseline_model.py')
    shutil.copyfile(config, output/'model/slot_config.json')
    shutil.copyfile(ROOT/LOCK, output/'model/checkpoint_lock.json')
    for target, source in DATA_COPIES.items():
        (output/target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/source, output/target)
    (output/'golden').mkdir()
    for s in range(11):
        np.save(output/f'golden/z_s{s}.npy', z[s], allow_pickle=False)
    np.save(output/'golden/reference_logits.npy', z[10], allow_pickle=False)
    text(output/'samples.csv', samples_csv(sample_rows(train_rows, compare, 'train')))
    (output/'calibration').mkdir()
    zc = golden(model, train_x, calibrate)
    for s in range(10):
        np.save(output/f'calibration/z_s{s}.npy', zc[s], allow_pickle=False)
    text(output/'calibration/samples.csv', samples_csv(sample_rows(train_rows, calibrate, 'train')))
    index_bytes = np.asarray(calibrate, dtype='<i8').tobytes()
    write_json(output/'calibration/rule.json', {'status': 'CANDIDATE_PENDING_SV2_CONFIRMATION', 'split': 'train', 'requested_count': calibration_count,
        'count': len(calibrate), 'n_train': len(train_x), 'rule': CALIBRATION_RULE, 'source': 'SV2 edge/quantize_tail.py calibration_inputs default rule',
        'train_row_indices_le_int64_sha256': hashlib.sha256(index_bytes).hexdigest(), 'validation_used': False, 'DS2_used': False})
    write_json(output/'model/model_graph.json', graph)
    for path, a in parameters.items():
        (output/path).parent.mkdir(parents=True, exist_ok=True)
        np.save(output/path, a, allow_pickle=False)
    text(output/'firmware/head_parameters.h', header(graph, parameters))
    write_json(output/'firmware/host_c_verification.json', compiler_verify(output, graph, parameters))
    write_json(output/'model/architecture.json', {**arch, 'cpu_validation_reload': check})
    text(output/'README.md', readme(deployment, calibration_count, len(calibrate)))
    manifest = {'schema': 'm1-v4-package-a/1', 'status': STATUS, 'checkpoint_lock': {'path': LOCK, 'sha256': LOCK_SHA},
                'checkpoint': {'path': 'model/checkpoint.pt', 'sha256': deployment['sha256'], 'slot_id': deployment['slot_id'],
                               'selected_epoch': deployment['selected_epoch'], 'source_path': deployment['path']},
                'arrays': {'directory': ARRAYS, 'opened': ['train_X.npy', 'train_y.npy', 'train_metadata.csv', 'val_X.npy', 'val_y.npy', 'val_metadata.csv'],
                           'DS2_opened': False},
                'golden': {'path': 'golden/', 'split': 'train', 'count': 20, 'rule': COMPARISON_RULE, 'splits': 's0-s10 plus reference_logits',
                           'computation': 'CPU, eval, torch.no_grad, N=1 per sample, one thread, deterministic, MKLDNN disabled'},
                'calibration': {'path': 'calibration/', 'split': 'train', 'count': len(calibrate), 'rule': CALIBRATION_RULE, 'splits': 's0-s9',
                                'status': 'CANDIDATE_PENDING_SV2_CONFIRMATION'},
                'not_included': {'DS2_predictions': 'v1.2 section 4.3; after the SV2 xmodel s0-s9 SHA lock (SV1 review 2a)',
                                 'DS2_arrays': 'Hashes are in data/processed-manifest.json; arrays ship with the DS2 step',
                                 'onnx_tails': 'Not in the v1.2 section 4.4 list; SV2 tools split the tail from model/checkpoint.pt'},
                'generation': {'command': ' '.join(['python', '-B', 'ml/scripts/package_m1_v4_a.py', 'build', '--output', '<NEW_DIRECTORY>',
                                                    '--calibration-count', str(calibration_count)]),
                               'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                               'script_sha256': sha(Path(__file__)), 'python': sys.version.split()[0], 'torch': torch.__version__, 'numpy': np.__version__},
                'files': inventory(output)}
    write_json(output/'manifest.json', manifest)
    return sha(output/'manifest.json')


def readme(deployment, requested, count):
    return f"""# Gói A, M1 v4 (bản ứng viên, chưa giao)

Checkpoint triển khai đã khóa: `{deployment['slot_id']}`, epoch {deployment['selected_epoch']}, SHA-256 `{deployment['sha256']}`.
File khóa: `{LOCK}` (`{LOCK_SHA}`).

Trạng thái: `{STATUS}`. Số mẫu và cách chọn mẫu calibration chờ SV2 xác nhận (protocol v4, mục quantization).

| Thư mục | Nội dung |
|---|---|
| `model/` | `checkpoint.pt`, mã kiến trúc, cấu hình slot, bản sao file khóa, `model_graph.json`, `architecture.json` (khẳng định tensor từng s, nạp lại validation trên CPU) |
| `firmware/` | `head_parameters.h` (cùng generator và định dạng gói R3 tuần 4), `host_c_verification.json` |
| `weights/` | Tham số FP32 của từng lớp, đúng bit với checkpoint |
| `data/` | Normalization fit trên train DS1, manifest dữ liệu đã xử lý (có SHA của DS2), split, metric policy |
| `golden/`, `samples.csv` | z_s0–z_s10 và logits của 20 nhịp train, định dạng gói tuần 3 |
| `calibration/` | z_s0–z_s9 của {count} nhịp train (yêu cầu {requested}), quy tắc chọn trong `rule.json`; ứng viên chờ SV2 |

Không có trong gói: dự đoán DS2 (sau khi SV2 khóa xmodel s0–s9), arrays DS2, tail ONNX.
Golden và calibration chỉ lấy từ train DS1; validation và DS2 không dùng.

Kiểm gói: `python -B ml/scripts/package_m1_v4_a.py verify --package <thư mục gói>`
Dựng lại: `python -B ml/scripts/package_m1_v4_a.py build --output <thư mục mới trong ml/data> --calibration-count {requested}`
"""


def verify(package):
    package = Path(package).resolve()
    manifest = read_json(package/'manifest.json')
    need(manifest['schema'] == 'm1-v4-package-a/1' and manifest['checkpoint_lock']['sha256'] == LOCK_SHA, 'Package identity differs')
    need(sha(package/'model/checkpoint_lock.json') == LOCK_SHA, 'Packaged lock differs')
    lock = read_json(package/'model/checkpoint_lock.json')
    deployment = next(c for c in lock['checkpoints'] if c['role'] == 'deployment')
    need(sha(package/'model/checkpoint.pt') == deployment['sha256'] == manifest['checkpoint']['sha256'], 'Packaged checkpoint differs from lock')
    need(sha(package/'model/mitdb_baseline_model.py') == MODEL_HASH, 'Packaged architecture source differs')
    need(inventory(package) == manifest['files'], 'Package inventory differs')
    graph = read_json(package/'model/model_graph.json')
    parameters = {p['path']: np.load(package/p['path'], allow_pickle=False) for op in graph['ops'] for p in op['parameters']}
    state = torch.load(package/'model/checkpoint.pt', map_location='cpu', weights_only=True)['state_dict']
    for op in graph['ops']:
        for p in op['parameters']:
            need(same_bits(parameters[p['path']], fp32(state[p['checkpoint_key']].numpy())), f"Weight file differs from checkpoint: {p['path']}")
    need((package/'firmware/head_parameters.h').read_text(encoding='utf-8') == header(graph, parameters), 'Header differs from weights')
    for s in range(11):
        need(np.load(package/f'golden/z_s{s}.npy', allow_pickle=False).shape == (20, *SHAPES[s][1:]), f'Golden shape differs: s{s}')
    rule = read_json(package/'calibration/rule.json')
    need(rule['split'] == 'train' and not rule['validation_used'] and not rule['DS2_used'], 'Calibration scope differs')
    for s in range(10):
        need(np.load(package/f'calibration/z_s{s}.npy', allow_pickle=False).shape == (rule['count'], *SHAPES[s][1:]), f'Calibration shape differs: s{s}')
    return {'status': 'PACKAGE_A_VERIFIED_' + manifest['status'], 'manifest_sha256': sha(package/'manifest.json'), 'files': len(manifest['files'])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['build', 'verify'])
    p.add_argument('--output', type=Path)
    p.add_argument('--package', type=Path)
    p.add_argument('--calibration-count', type=int)
    a = p.parse_args()
    if a.mode == 'build':
        need(a.output is not None and a.calibration_count is not None, 'build needs --output and --calibration-count')
        print('PACKAGE_A_BUILT', a.output.as_posix(), 'MANIFEST_SHA256', build(a.output, a.calibration_count))
    else:
        need(a.package is not None, 'verify needs --package')
        print(json.dumps(verify(a.package), indent=2))


if __name__ == '__main__':
    main()
