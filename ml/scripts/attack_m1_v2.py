"""Attack stage of M1 under protocol mitdb-m1-attack-v2: plan, preflight, smoke and the week 11 trial (A1 + B-naive).

The trial never reads a MITDB array without an external lock and trial authorization that binds the protocol, the attack
plan (sources, checkpoints, arrays) and the SV1 review evidence. It reads the DS1 train/val arrays only; DS2 is never
opened. `preflight` checks the bindings and the DS1 time-split counts from metadata (no array, no model, no fit).
`smoke` runs the whole pipeline on random arrays and random metadata it creates itself, with the real rho0/rho1
checkpoints; no MITDB file is read. Every step runs with TF32 off (cuDNN and matmul) and deterministic algorithms.
The attacker sees what the edge receives: z_s of the evaluated checkpoint, quantized and dequantized with the
registry v2 function (ml/src/quantization.py).
"""
from __future__ import annotations

import os

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')  # Before torch creates a CUDA context.

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from fractions import Fraction  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402
from torch.nn import functional as F  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ml/src'))
import package_m1_v4_a as pkg  # noqa: E402
from quantization import dequantize_per_channel, quantize_per_channel, to_ncl  # noqa: E402
from week3_common import need, read_json, sha, write_json  # noqa: E402
from week3_sv2_common import SHAPES, configure, wrappers  # noqa: E402

PROTOCOL = 'ml/configs/mitdb_m1_attack_protocol_v2.json'
PLAN_DIR = 'ml/manifests/mitdb-attack-m1-v2'
NOPEEK_PLAN = 'ml/manifests/mitdb-nopeek-m1-v2/plan-manifest.json'
NOPEEK_GRID_RECEIPT = 'ml/provenance/m1-nopeek-v2-run-20261112/grid-receipt.json'
NOPEEK_RUNS = 'ml/data/runs/nopeek-m1-v2-20261112/grid'
SOURCES = ['ml/scripts/attack_m1_v2.py', 'ml/scripts/package_m1_v4_a.py', 'ml/scripts/week3_common.py',
           'ml/scripts/week3_sv2_common.py', 'ml/scripts/week4_common.py', 'ml/src/quantization.py', 'ml/src/mitdb_baseline_model.py']
AUTH_TYPE = 'M1_ATTACK_V2_LOCK_AND_TRIAL_AUTHORIZATION'
REVIEW_EVIDENCE_KEY = 'sv1_review_20261113'  # Protocol source binding the lock must name as review evidence.
CHANNELS = (1, 16, 16, 32, 32, 48, 48, 64, 64)  # Input channels then the eight Conv1d outputs of the head.
EVIDENCE_KEYS = ('sv1_decisions_20261103', 'sv1_review_20261105', 'sv1_review_20261109', 'sv1_review_20261113')
FILE_KEYS = ('nopeek_protocol_v2', 'grid_selection', 'checkpoint_lock_A', 'quantization')


# ---------- protocol and settings ----------

def protocol():
    return read_json(ROOT/PROTOCOL)


def settings(p):
    """Every run value the code takes from the protocol (single source of truth)."""
    m, t = p['attack_models'], p['attack_models']['training']
    need(t['precision'] == {'cudnn_allow_tf32': False, 'matmul_allow_tf32': False}, 'Protocol v2 requires TF32 off for cuDNN and matmul')
    o, b = t['optimizer'], p['privacy_metric']['bootstrap']
    need(o['name'] == 'AdamW' and t['early_stop']['keep'] == 'best epoch, ties to the earliest', 'Optimizer or early-stop rule differs')
    return {'lr': o['lr'], 'weight_decay': o['weight_decay'], 'betas': tuple(o['betas']), 'eps': o['eps'],
            'batch_size': t['batch_size'], 'max_epochs': t['max_epochs'], 'patience': t['early_stop']['patience'],
            'B_seeds': list(m['B_classifier']['seeds']), 'A1_seeds': list(m['A1_decoder']['seeds']),
            'architectures': {'base': m['B_classifier']['base'], 'escalated': m['B_classifier']['escalated']},
            'capacity_threshold': p['capacity_check']['threshold'], 'std_floor': 1e-6,
            'resamples': b['resamples'], 'bootstrap_seed': b['seed'], 'block_beats': b['block_beats'],
            'Pi_min': p['privacy_metric']['Pi_min'], 'Pi_min_sweep': list(p['privacy_metric']['Pi_min_sweep'])}


def set_precision():
    """TF32 off for cuDNN and matmul, deterministic algorithms; returns what PyTorch reports after setting."""
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    need(torch.backends.cudnn.allow_tf32 is False and torch.backends.cuda.matmul.allow_tf32 is False, 'TF32 still enabled after setting it off')
    need(os.environ.get('CUBLAS_WORKSPACE_CONFIG') == ':4096:8', 'CUBLAS_WORKSPACE_CONFIG must be :4096:8')
    return {'cudnn_allow_tf32': False, 'matmul_allow_tf32': False, 'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(),
            'cudnn_deterministic': torch.backends.cudnn.deterministic, 'cudnn_benchmark': torch.backends.cudnn.benchmark}


def lam_text(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else repr(value)


# ---------- bindings, plan, authorization ----------

def binding_hashes(p):
    """Every file the protocol binds by hash must match: SV1 evidence copies, NoPeek protocol, selection, lock, quantization."""
    sb = p['source_bindings']
    for key in EVIDENCE_KEYS:
        need(sha(ROOT/sb[key]['path']) == sb[key]['raw_sha256'], f'Source binding differs: {key}')
    for key in FILE_KEYS:
        need(sha(ROOT/sb[key]['path']) == sb[key]['sha256'], f'Source binding differs: {key}')
    need(sha(ROOT/sb['quantization']['registry']) == sb['quantization']['registry_sha256'], 'Registry v2 differs')
    need(sb['checkpoint_lock_A']['sha256'] == pkg.LOCK_SHA, 'Checkpoint lock of package A differs')
    need(sha(ROOT/sb['package_A']['path']/Path('manifest.json')) == sb['package_A']['manifest_sha256'], 'Package A manifest differs')


def checkpoint_table(p):
    """rho0 (lock deployment) and rho1 per split, each checked against grid-selection, the NoPeek plan and the grid receipt."""
    _, deployment, _, _ = pkg.locked()
    rho0 = p['checkpoints']['rho0']
    need(deployment['path'] == rho0['path'] and deployment['sha256'] == rho0['sha256'], 'rho0 is not the locked deployment checkpoint')
    selection = read_json(ROOT/p['source_bindings']['grid_selection']['path'])['per_s']
    receipt = {r['run_id']: r for r in read_json(ROOT/NOPEEK_GRID_RECEIPT)['runs']}
    nplan = {r['run_id']: r for r in read_json(ROOT/NOPEEK_PLAN)['runs']}
    table = {'rho0': {'path': rho0['path'], 'sha256': rho0['sha256']}, 'rho1': {}}
    for s, e in p['checkpoints']['rho1'].items():
        v = selection[s]
        row = next(t for t in v['table'] if float(t['lambda']) == float(v['lambda']))
        seed = next(x for x in row['seeds'] if x['seed'] == v['deployment_seed'])
        run_id = f"grid-{s}-lambda{lam_text(v['lambda'])}-seed{v['deployment_seed']}"
        need(row['eligible'] is True and e['run_id'] == run_id and e['lambda'] == v['lambda'] and e['seed'] == v['deployment_seed']
             and e['epoch'] == seed['epoch'], f'rho1 entry differs from grid-selection: {s}')
        name = f"checkpoint-epoch-{e['epoch']:03d}.pt"
        need(receipt[run_id]['checkpoints_sha256'][name] == e['sha256'], f'rho1 hash differs from the grid receipt: {s}')
        table['rho1'][s] = {'run_id': run_id, 'lambda': e['lambda'], 'seed': e['seed'], 'epoch': e['epoch'],
                            'path': f'{NOPEEK_RUNS}/{run_id}/{name}', 'sha256': e['sha256'], 'run_config_sha256': nplan[run_id]['sha256']}
    for s, entries in p['checkpoints']['official_defence_seed_range_3c'].items():
        if s == 'use':
            continue
        v = selection[s]
        row = next(t for t in v['table'] if float(t['lambda']) == float(v['lambda']))
        others = sorted(x['seed'] for x in row['seeds'] if x['seed'] != v['deployment_seed'])
        need(sorted(int(e['run_id'].rsplit('seed', 1)[1]) for e in entries) == others, f'3(c) seeds differ: {s}')
        for e in entries:
            seed = next(x for x in row['seeds'] if e['run_id'].endswith(f"seed{x['seed']}"))
            need(e['epoch'] == seed['epoch'] and receipt[e['run_id']]['checkpoints_sha256'][f"checkpoint-epoch-{e['epoch']:03d}.pt"] == e['sha256'],
                 f"3(c) entry differs: {e['run_id']}")
    return table


def checkpoint_files(table):
    return [table['rho0']] + [table['rho1'][s] for s in sorted(table['rho1'])]


def prepare(output):
    """Write the attack plan: protocol, sources, checkpoints (with their files' hashes), DS1 arrays, trial order."""
    output = ROOT/output
    need(not output.exists(), 'Plan directory exists; a new protocol version needs a new plan directory')
    p = protocol()
    settings(p)
    binding_hashes(p)
    table = checkpoint_table(p)
    for c in checkpoint_files(table):
        need(sha(ROOT/c['path']) == c['sha256'], f"Checkpoint file differs: {c['path']}")
    _, _, plan_v4, _ = pkg.locked()
    files = plan_v4['binding']['data_files']
    need(sorted(files) == sorted(f'{s}_{k}' for s in ('train', 'val') for k in ('X.npy', 'y.npy', 'metadata.csv')), 'Array binding is not DS1 train/val only')
    plan = {'schema': 'm1-attack-plan/1', 'status': 'CANDIDATE_NOT_LOCKED', 'protocol_sha256': sha(ROOT/PROTOCOL),
            'checkpoint_lock_sha256': pkg.LOCK_SHA, 'arrays': pkg.ARRAYS, 'data_files': files,
            'package_A_manifest_sha256': p['source_bindings']['package_A']['manifest_sha256'],
            'sources_sha256': {n: sha(ROOT/n) for n in SOURCES}, 'checkpoints': table,
            'trial_order': p['trial_week11_scope']['order'], 'DS2_access': False}
    output.mkdir(parents=True)
    write_json(output/'plan-manifest.json', plan)
    return sha(output/'plan-manifest.json')


def read_metadata(directory):
    rows = []
    for split in ('train', 'val'):
        with (Path(directory)/f'{split}_metadata.csv').open(encoding='utf-8', newline='') as f:
            rows += list(csv.DictReader(f))
    return rows


def preflight(plan_path):
    """Bindings and the DS1 time-split counts from metadata only. No array, no model, no fit, no DS2."""
    plan, p = read_json(plan_path), protocol()
    need(plan['protocol_sha256'] == sha(ROOT/PROTOCOL) and plan['checkpoint_lock_sha256'] == pkg.LOCK_SHA, 'Plan binding differs')
    need(sorted(plan['sources_sha256']) == sorted(SOURCES) and all(sha(ROOT/n) == h for n, h in plan['sources_sha256'].items()), 'Source differs from plan')
    settings(p)
    binding_hashes(p)
    need(plan['checkpoints'] == checkpoint_table(p) and plan['trial_order'] == p['trial_week11_scope']['order'], 'Plan checkpoints or order differ')
    for c in checkpoint_files(plan['checkpoints']):
        need(sha(ROOT/c['path']) == c['sha256'], f"Checkpoint file differs: {c['path']}")
    for name, expected in plan['data_files'].items():
        need(not name.startswith('test') and sha(ROOT/plan['arrays']/name) == expected['sha256'], f'Array differs: {name}')
    rows = read_metadata(ROOT/plan['arrays'])
    counts = split_counts(time_split(rows, p['data']['trial_week11']), len(rows))
    need(counts == p['data']['trial_week11']['counts'], f'DS1 time-split counts differ from the protocol: {counts}')
    return {'status': 'PASS_PREFLIGHT_METADATA_ONLY_NO_ARRAY_NO_MODEL_NO_FIT_NO_DS2', 'counts': counts,
            'checkpoints': len(checkpoint_files(plan['checkpoints']))}


def require_authorization(path, plan_path):
    need(path is not None and Path(path).is_file(), 'External attack lock and trial authorization required')
    a = read_json(path)
    need(a.get('type') == AUTH_TYPE and a.get('allow_trial') is True and a.get('protocol_sha256') == sha(ROOT/PROTOCOL)
         and a.get('plan_manifest_sha256') == sha(plan_path) and bool(a.get('approved_by')) and bool(a.get('review_evidence')),
         'Authorization does not bind the protocol and plan')
    declared = protocol()['source_bindings'][REVIEW_EVIDENCE_KEY]
    evidence = a.get('review_evidence_path')
    need(isinstance(evidence, str) and evidence == declared['path'] and (ROOT/evidence).is_file()
         and a['review_evidence'] == declared['raw_sha256'] == sha(ROOT/evidence),
         'Authorization review evidence is not the SV1 review file named by the protocol, or its SHA-256 differs')
    return a


# ---------- data: identities and time split ----------

def time_split(rows, rule):
    """Per record: drop |r - center| <= half, earlier beats -> attacker side (last ceil(f n) by time -> attacker validation),
    later beats -> test. Labels are the rank of the numeric record id. Index arrays point into `rows`, patient then time order."""
    center, half = rule['time_split']['center_sample'], rule['time_split']['half_width_samples']
    fraction = Fraction(str(rule['attacker_validation']['fraction']))  # Exact ceiling, independent of float rounding.
    records = sorted({int(r['record_id']) for r in rows})
    label = {rec: k for k, rec in enumerate(records)}
    beats = {rec: [] for rec in records}
    for i, r in enumerate(rows):
        beats[int(r['record_id'])].append((int(r['r_peak_sample']), i))
    parts = {'attacker_train': [], 'attacker_validation': [], 'test': []}
    per_record, dropped = {}, 0
    for rec in records:
        ordered = sorted(beats[rec])
        need(len({t for t, _ in ordered}) == len(ordered), f'Duplicate R peak in record {rec}')
        attacker = [i for t, i in ordered if t < center - half]
        test = [i for t, i in ordered if t > center + half]
        dropped += len(ordered) - len(attacker) - len(test)
        n_val = math.ceil(fraction*len(attacker))
        need(n_val >= 1 and len(attacker) - n_val >= 1 and len(test) >= 1, f'Record {rec} lacks beats on one side')
        parts['attacker_train'] += attacker[:len(attacker)-n_val]
        parts['attacker_validation'] += attacker[len(attacker)-n_val:]
        parts['test'] += test
        per_record[rec] = {'all': len(ordered), 'attacker_side': len(attacker), 'test': len(test)}
    labels = np.array([label[int(r['record_id'])] for r in rows], dtype=np.int64)
    return {'n': len(records), 'records': records, 'labels': labels, 'dropped': dropped, 'per_record': per_record,
            **{k: np.array(v, dtype=np.int64) for k, v in parts.items()}}


def split_counts(split, total):
    pr = split['per_record'].values()
    return {'beats': total, 'dropped': split['dropped'], 'attacker_side': sum(r['attacker_side'] for r in pr),
            'test': sum(r['test'] for r in pr), 'attacker_side_per_record': [min(r['attacker_side'] for r in pr), max(r['attacker_side'] for r in pr)],
            'test_per_record': [min(r['test'] for r in pr), max(r['test'] for r in pr)],
            'largest_patient_share_of_all_beats': round(max(r['all'] for r in pr)/total, 4)}


# ---------- observed tensors ----------

def load_rho(entry, rho1=False):
    """Package A model; for rho1 the NoPeek v2 state dict of the bound checkpoint (identity fields checked)."""
    _, deployment, _, slot_config = pkg.locked()
    need(sha(ROOT/entry['path']) == entry['sha256'], f"Checkpoint differs: {entry['path']}")
    model = pkg.load_model(deployment, slot_config)
    if rho1:
        ck = torch.load(ROOT/entry['path'], map_location='cpu', weights_only=True)
        need(ck['epoch'] == entry['epoch'] and ck['run_config_sha256'] == entry['run_config_sha256']
             and ck['protocol_sha256'] == protocol()['source_bindings']['nopeek_protocol_v2']['sha256'], f"rho1 checkpoint identity differs: {entry['run_id']}")
        model.load_state_dict(ck['state_dict'], strict=True)
        model.eval()
    return model


def head_output(model, x, s, batch=1024):
    """z_s on CPU: s0-s8 in batches, s9-s10 one beat at a time (both bit-equal to the package A golden convention)."""
    head, _ = wrappers(model, s)
    x = np.ascontiguousarray(np.asarray(x, dtype='<f4').reshape(-1, 1, 360))
    step = batch if s <= 8 else 1
    out = []
    with torch.no_grad():
        for i in range(0, len(x), step):
            out.append(head(torch.from_numpy(x[i:i+step])).numpy().copy())
    return np.ascontiguousarray(np.concatenate(out), dtype='<f4')


def observed(model, x, s):
    """What the edge receives, dequantized: INT8 per beat and channel with FP16 scale (registry v2), as FP32 [N, C, L]."""
    q, scale = quantize_per_channel(to_ncl(head_output(model, x, s), s))
    return dequantize_per_channel(q, scale)


def golden_check(model, package, splits):
    """rho0 z_s of the 20 package A golden beats must equal golden/z_s<s>.npy bit for bit at every evaluated split."""
    x = np.load(Path(package)/'golden/z_s0.npy', allow_pickle=False)
    for s in splits:
        g = np.load(Path(package)/f'golden/z_s{s}.npy', allow_pickle=False)
        z = head_output(model, x, s)
        need(z.dtype == g.dtype and z.shape == g.shape and z.tobytes() == g.tobytes(), f'z_s{s} differs from package A golden')
    return {'beats': int(len(x)), 'splits': list(splits), 'bitwise_equal': True}


def standardize(train, *others, floor=1e-6):
    """Per channel mean and population std over N and L of the attacker-train part."""
    mean = train.mean(axis=(0, 2), keepdims=True, dtype=np.float64)
    std = np.maximum(train.std(axis=(0, 2), keepdims=True, dtype=np.float64), floor)
    return [((a - mean)/std).astype('<f4') for a in (train, *others)]


# ---------- attack models ----------

class MeanL(nn.Module):
    def forward(self, x):
        return x.mean(dim=2)


class Upsample(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.size = size

    def forward(self, x):
        return F.interpolate(x, size=self.size, mode='nearest')


def b_classifier(input_shape, n, arch):
    """B: NCL [C, L] -> conv blocks + mean over L + Linear(N); NC [C] -> MLP."""
    layers, c = [], input_shape[0]
    if len(input_shape) == 2:
        a = arch['NCL']
        for _ in range(a['blocks']):
            layers += [nn.Conv1d(c, a['channels'], a['kernel'], padding=a['kernel']//2), nn.ReLU(), nn.MaxPool1d(2)]
            c = a['channels']
        return nn.Sequential(*layers, MeanL(), nn.Linear(c, n))
    for hidden in arch['NC']['hidden']:
        layers += [nn.Linear(c, hidden), nn.ReLU()]
        c = hidden
    return nn.Sequential(*layers, nn.Linear(c, n))


def a1_decoder(s):
    """Mirror of head_s back to [1, 360]; s9/s10 first map back to [64, 22] with dense layers."""
    need(type(s) is int and 1 <= s <= 10, 'A1 decoder needs 1 <= s <= 10 (s0 is the identity)')
    layers = []
    if s == 10:
        layers += [nn.Linear(5, 32), nn.ReLU()]
    if s >= 9:
        layers += [nn.Linear(32, 64*22), nn.ReLU(), nn.Unflatten(1, (64, 22))]
    for k in range(min(s, 8), 0, -1):
        if k % 2 == 0:
            layers.append(Upsample(SHAPES[k-1][2]))
        layers.append(nn.Conv1d(CHANNELS[k], CHANNELS[k-1], 5, padding=2))
        if k > 1:
            layers.append(nn.ReLU())
    return nn.Sequential(*layers)


def choose_architecture(mean_bacc, threshold):
    return 'base' if mean_bacc >= threshold else 'escalated'


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def predict(model, x, device, batch=4096):
    out = []
    with torch.no_grad():
        for i in range(0, len(x), batch):
            out.append(model(x[i:i+batch].to(device)).cpu())
    return torch.cat(out).numpy()


def improves(kind, metric, best):
    """Strict improvement only, so a tie keeps the earliest epoch (B: higher bacc, A1: lower MSE)."""
    return best is None or (metric > best['validation'] if kind == 'B' else metric < best['validation'])


def stops(epoch, best_epoch, patience):
    return epoch - best_epoch >= patience


def fit(factory, seed, data, kind, cfg, device, n=None, weight=None):
    """AdamW, seeded shuffle, early stop on attacker validation (B: bacc up, A1: MSE down), best epoch kept (ties: earliest)."""
    need(kind in ('B', 'A1'), 'Unknown attack kind')
    seed_all(seed)
    model = factory().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg['lr'], betas=cfg['betas'], eps=cfg['eps'], weight_decay=cfg['weight_decay'])
    tx, ty = torch.from_numpy(data['train_x']).to(device), torch.from_numpy(data['train_y']).to(device)
    vx = torch.from_numpy(data['val_x'])
    w = None if weight is None else torch.from_numpy(weight).to(device)
    best, history = None, []
    for epoch in range(1, cfg['max_epochs']+1):
        perm = torch.randperm(len(tx), generator=torch.Generator().manual_seed(seed+epoch-1)).to(device)
        model.train()
        total = 0.
        for i in range(0, len(tx), cfg['batch_size']):
            idx = perm[i:i+cfg['batch_size']]
            opt.zero_grad(set_to_none=True)
            out = model(tx[idx])
            loss = F.cross_entropy(out, ty[idx], weight=w) if kind == 'B' else F.mse_loss(out, ty[idx])
            need(bool(torch.isfinite(loss)), 'Non-finite attack loss')
            loss.backward()
            opt.step()
            total += float(loss.detach())*len(idx)
        model.eval()
        out = predict(model, vx, device)
        metric = balanced_accuracy(data['val_y'], out.argmax(1), n)[0] if kind == 'B' else float(np.mean((out - data['val_y'])**2, dtype=np.float64))
        history.append({'epoch': epoch, 'train_loss': total/len(tx), 'validation': metric})
        if improves(kind, metric, best):
            best = {'epoch': epoch, 'validation': metric, 'state': {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
        elif stops(epoch, best['epoch'], cfg['patience']):
            break
    model.load_state_dict(best['state'])
    model.eval()
    return model, {'best_epoch': best['epoch'], 'validation': best['validation'], 'epochs_run': len(history), 'history': history}, best['state']


# ---------- metrics ----------

def balanced_accuracy(y, pred, n):
    y, pred = np.asarray(y), np.asarray(pred)
    recalls = []
    for k in range(n):
        mask = y == k
        need(bool(mask.any()), f'No beat of patient label {k}')
        recalls.append(float(np.mean(pred[mask] == k)))
    return float(np.mean(recalls)), recalls


def advantage(bacc, n):
    return float(min(1., max(0., (bacc - 1/n)/(1 - 1/n))))


def test_blocks(y_test, n, size):
    """Per patient (label order), its test positions cut into consecutive non-overlapping blocks of `size`."""
    blocks = []
    for k in range(n):
        idx = np.flatnonzero(np.asarray(y_test) == k)
        need(len(idx) >= 1 and bool(np.all(np.diff(idx) == 1)), 'Test beats of a patient must be contiguous and in time order')
        blocks.append([idx[i:i+size] for i in range(0, len(idx), size)])
    return blocks


def bootstrap_pi(y_test, preds, n, resamples, seed, size, level=0.95):
    """Block bootstrap within patients. numpy default_rng(seed); patients in label order, each drawing integers(0, nb,
    (resamples, nb)) block indices. Same draw for every B seed; Pi = 1 - mean over seeds of Adv; percentile interval."""
    rng = np.random.default_rng(seed)
    blocks = test_blocks(y_test, n, size)
    recall = np.zeros((len(preds), resamples, n))
    for k, bl in enumerate(blocks):
        sizes = np.array([len(b) for b in bl])
        correct = np.array([[int(np.sum(np.asarray(p)[b] == k)) for b in bl] for p in preds])
        draw = rng.integers(0, len(bl), size=(resamples, len(bl)))
        recall[:, :, k] = correct[:, draw].sum(-1)/sizes[draw].sum(-1)
    adv = np.clip((recall.mean(-1) - 1/n)/(1 - 1/n), 0, 1).mean(0)
    low, high = np.quantile(1 - adv, [(1 - level)/2, 1 - (1 - level)/2], method='linear')
    return {'low': float(low), 'high': float(high), 'level': level, 'resamples': resamples, 'seed': seed, 'block_beats': size}


def session_bacc(y_test, pred, n, size):
    """Majority vote over the same blocks of consecutive test beats (ties: lowest label), balanced over patients."""
    recalls = []
    for k, bl in enumerate(test_blocks(y_test, n, size)):
        votes = [int(np.bincount(np.asarray(pred)[b], minlength=n).argmax()) for b in bl]
        recalls.append(float(np.mean(np.array(votes) == k)))
    return float(np.mean(recalls))


def reconstruction_metrics(x_hat, x):
    x = np.asarray(x, dtype=np.float64).reshape(len(x), -1)
    h = np.asarray(x_hat, dtype=np.float64).reshape(len(x), -1)
    std = x.std(axis=1)
    need(bool(np.all(std > 0)), 'Constant original beat')
    nrmse = np.sqrt(np.mean((h - x)**2, axis=1))/std
    xc, hc = x - x.mean(axis=1, keepdims=True), h - h.mean(axis=1, keepdims=True)
    den = np.sqrt((xc**2).sum(axis=1)*(hc**2).sum(axis=1))
    pearson = np.where(den > 0, (xc*hc).sum(axis=1)/np.where(den > 0, den, 1.), 0.)
    peak = np.abs(np.abs(h).argmax(axis=1) - np.abs(x).argmax(axis=1)).astype(np.float64)
    summary = lambda a: {'mean': float(np.mean(a)), 'median': float(np.median(a))}  # noqa: E731
    return {'beats': int(len(x)), 'NRMSE': summary(nrmse), 'pearson': summary(pearson),
            'r_peak_error_samples': summary(peak), 'r_peak_error_ms': summary(peak*1000/360)}


# ---------- one (s, rho) evaluation ----------

def evaluate_pair(model, x, split, s, arch_name, cfg, device):
    """A1 (1 seed; identity at s0) and B-naive (3 seeds) on the observed tensors of one (s, rho)."""
    order = ('attacker_train', 'attacker_validation', 'test')
    rows = np.concatenate([split[k] for k in order])
    raw = observed(model, x[rows], s)
    cut = np.cumsum([len(split[k]) for k in order])[:-1]
    raw_tr, raw_va, raw_te = np.split(raw, cut)
    f_tr, f_va, f_te = standardize(raw_tr, raw_va, raw_te, floor=cfg['std_floor'])
    if s >= 9:
        f_tr, f_va, f_te = f_tr[..., 0], f_va[..., 0], f_te[..., 0]
    y = split['labels']
    y_tr, y_va, y_te = y[split['attacker_train']], y[split['attacker_validation']], y[split['test']]
    n = split['n']
    counts = np.bincount(y_tr, minlength=n)
    need(bool(np.all(counts > 0)), 'A patient has no attacker-train beat')
    weight = (len(y_tr)/(n*counts)).astype('<f4')
    arch = cfg['architectures'][arch_name]
    seeds, preds, states = [], [], {}
    for seed in cfg['B_seeds']:
        m, info, state = fit(lambda: b_classifier(f_tr.shape[1:], n, arch), seed,
                             {'train_x': f_tr, 'train_y': y_tr, 'val_x': f_va, 'val_y': y_va}, 'B', cfg, device, n=n, weight=weight)
        pred = predict(m, torch.from_numpy(f_te), device).argmax(1)
        bacc, recalls = balanced_accuracy(y_te, pred, n)
        adv = advantage(bacc, n)
        seeds.append({'seed': seed, 'best_epoch': info['best_epoch'], 'epochs_run': info['epochs_run'],
                      'attacker_validation_bacc': info['validation'], 'test_bacc': bacc, 'Adv': adv, 'Pi': 1 - adv,
                      'per_patient_recall': recalls, 'history': info['history']})
        preds.append(pred)
        states[f'B_seed{seed}'] = state
    adv_mean = float(np.mean([r['Adv'] for r in seeds]))
    pi = 1 - adv_mean
    b = {'architecture': arch_name, 'architecture_spec': arch, 'seeds': seeds,
         'bacc_mean': float(np.mean([r['test_bacc'] for r in seeds])), 'Adv_mean': adv_mean, 'Pi': pi,
         'seed_range': {k: [min(r[k] for r in seeds), max(r[k] for r in seeds)] for k in ('test_bacc', 'Adv', 'Pi')},
         'ci95': bootstrap_pi(y_te, preds, n, cfg['resamples'], cfg['bootstrap_seed'], cfg['block_beats']),
         'session_bacc_per_seed': [session_bacc(y_te, p, n, cfg['block_beats']) for p in preds],
         'chance_bacc': 1/n, 'passes_Pi_min': pi >= cfg['Pi_min'],
         'Pi_min_sweep': {f'{t:.1f}': pi >= t for t in cfg['Pi_min_sweep']}}
    x_te = x[split['test']]
    if s == 0:
        recon = raw_te[:, 0, :]
        a1 = {'decoder': 'identity (dequantized input)', 'metrics': reconstruction_metrics(recon, x_te)}
    else:
        seed = cfg['A1_seeds'][0]
        target = lambda part: np.ascontiguousarray(x[split[part]].reshape(-1, 1, 360), dtype='<f4')  # noqa: E731
        m, info, state = fit(lambda: a1_decoder(s), seed, {'train_x': f_tr, 'train_y': target('attacker_train'),
                             'val_x': f_va, 'val_y': target('attacker_validation')}, 'A1', cfg, device)
        recon = predict(m, torch.from_numpy(f_te), device).reshape(len(f_te), 360)
        a1 = {'decoder': f'mirror of head_s{s}', 'seed': seed, 'best_epoch': info['best_epoch'], 'epochs_run': info['epochs_run'],
              'attacker_validation_mse': info['validation'], 'history': info['history'], 'metrics': reconstruction_metrics(recon, x_te)}
        states['A1'] = state
    first = np.array([np.flatnonzero(y_te == k)[0] for k in range(n)])
    arrays = {'test_rows': split['test'], 'test_labels': y_te, **{f'pred_seed{sd}': p for sd, p in zip(cfg['B_seeds'], preds)},
              'gallery_test_positions': first, 'gallery_original': x_te[first].astype('<f4'), 'gallery_reconstruction': recon[first].astype('<f4')}
    return {'s': s, 'n_identities': n, 'parts': {k: int(len(split[k])) for k in order}, 'observed_shape': list(raw.shape[1:]),
            'B_naive': b, 'A1': a1}, arrays, states


def write_pair(output, name, result, arrays, states):
    write_json(output/f'{name}.json', result)
    np.savez(output/f'{name}-arrays.npz', **arrays)
    torch.save(states, output/f'{name}-attackers.pt')


def summary_row(name, r):
    b = r['B_naive']
    return {'pair': name, 's': r['s'], 'rho': r['rho'], 'Pi': b['Pi'], 'ci95': [b['ci95']['low'], b['ci95']['high']],
            'Pi_seed_range': b['seed_range']['Pi'], 'bacc_mean': b['bacc_mean'], 'passes_Pi_min': b['passes_Pi_min'],
            'architecture': b['architecture'], 'A1_NRMSE_mean': r['A1']['metrics']['NRMSE']['mean'],
            'A1_pearson_mean': r['A1']['metrics']['pearson']['mean']}


def run_pairs(models, x, split, order, cfg, device, output, log=print):
    """Capacity check at s0 first (base; escalate once if the mean s0 test bacc < threshold), then every other pair."""
    results, rows = {}, []

    def one(s, rho, arch, name):
        t0 = time.time()
        r, arrays, states = evaluate_pair(models[(s, rho)], x, split, s, arch, cfg, device)
        r.update(rho=rho, checkpoint_sha256=models['sha'][(s, rho)], seconds=round(time.time() - t0, 1))
        write_pair(output, name, r, arrays, states)
        results[name] = r
        rows.append(summary_row(name, r))
        log(f"{name}: Pi={r['B_naive']['Pi']:.4f} CI95=[{r['B_naive']['ci95']['low']:.4f}, {r['B_naive']['ci95']['high']:.4f}] "
            f"bacc={r['B_naive']['bacc_mean']:.4f} arch={arch} A1_NRMSE={r['A1']['metrics']['NRMSE']['mean']:.4f}")
        return r

    need(tuple(order[0]) == ('s0', 'rho0'), 'The capacity check at s0 rho0 must come first')
    base = one(0, 'rho0', 'base', 's0-rho0-base')
    stat = base['B_naive']['bacc_mean']
    arch = choose_architecture(stat, cfg['capacity_threshold'])
    capacity = {'statistic': 'mean over the B seeds of s0 test bacc (base architecture)', 'value': stat,
                'threshold': cfg['capacity_threshold'], 'decision': arch}
    if arch == 'escalated':
        capacity['s0_escalated_bacc_mean'] = one(0, 'rho0', 'escalated', 's0-rho0-escalated')['B_naive']['bacc_mean']
    for s_name, rho in order[1:]:
        s = int(s_name[1:])
        one(s, rho, arch, f'{s_name}-{rho}')
    return results, rows, capacity


def device_of(name):
    return torch.device('cuda' if name == 'auto' and torch.cuda.is_available() else 'cpu' if name == 'auto' else name)


def environment(device, precision):
    return {'device': str(device), 'device_name': torch.cuda.get_device_name(device) if device.type == 'cuda' else 'CPU',
            'torch': torch.__version__, 'cuda': torch.version.cuda, **precision}


# ---------- trial and smoke ----------

def run_trial(plan_path, output, authorization, device='auto'):
    """Week 11 trial on DS1 (N = 22): s0 capacity check, then s2, s4, s5, s8 with rho0 and rho1. Needs the lock."""
    auth = require_authorization(authorization, plan_path)  # Before any data, model or output.
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Trial output must be a new path under ignored ml/data')
    pf = preflight(plan_path)
    plan, p = read_json(plan_path), protocol()
    cfg = settings(p)
    precision = set_precision()
    configure()
    dev = device_of(device)
    _, _, plan_v4, _ = pkg.locked()
    data = pkg.arrays(plan_v4)  # DS1 train/val only, each file checked against the plan binding.
    x = np.ascontiguousarray(np.concatenate([data['train'][0], data['val'][0]]), dtype='<f4')
    rows = data['train'][2] + data['val'][2]
    split = time_split(rows, p['data']['trial_week11'])
    need(split_counts(split, len(rows)) == pf['counts'], 'Split counts differ from preflight')
    table = plan['checkpoints']
    rho0 = load_rho(table['rho0'])
    golden = golden_check(rho0, ROOT/p['source_bindings']['package_A']['path'], sorted({int(s[1:]) for s, _ in plan['trial_order']}))
    models = {'sha': {}}
    for s_name, rho in plan['trial_order']:
        s = int(s_name[1:])
        models[(s, rho)] = rho0 if rho == 'rho0' else load_rho(table['rho1'][s_name], rho1=True)
        models['sha'][(s, rho)] = table['rho0']['sha256'] if rho == 'rho0' else table['rho1'][s_name]['sha256']
    output.mkdir(parents=True)
    write_json(output/'trial-identity.json', {'authorization_sha256': sha(authorization), 'plan_manifest_sha256': sha(plan_path),
               'protocol_sha256': sha(ROOT/PROTOCOL), **environment(dev, precision), 'golden_check': golden, 'counts': pf['counts'],
               'DS2_opened': False})
    results, table_rows, capacity = run_pairs(models, x, split, plan['trial_order'], cfg, dev, output, log=lambda m: print(m, flush=True))
    result = {'status': 'TRIAL_COMPLETED_REPORT_ONLY', 'protocol_sha256': sha(ROOT/PROTOCOL), 'plan_manifest_sha256': sha(plan_path),
              'authorization_approved_by': auth['approved_by'], 'N': split['n'], 'Pi_min': cfg['Pi_min'], 'capacity_check': capacity,
              'table': table_rows, 'pair_files_sha256': {f'{k}.json': sha(output/f'{k}.json') for k in results},
              'caveat': p['trial_week11_scope']['receipt_caveat'], 'DS2_opened': False}
    write_json(output/'trial-result.json', result)
    return result


def synthetic_beats(rng, records, per):
    """Random metadata and beat-like arrays: per record a QRS bump (own amplitude and width) and a T bump (own offset and
    amplitude) around sample 180, plus white noise. Shape differences a pooled CNN can learn; no MITDB file involved."""
    t = np.arange(360, dtype=np.float64)
    rows, xs = [], []
    for rec in records:
        qrs, width, t_amp, t_off = rng.uniform(1, 3), rng.uniform(3, 12), rng.uniform(-1, 1), rng.uniform(40, 120)
        template = qrs*np.exp(-0.5*((t - 180)/width)**2) + t_amp*np.exp(-0.5*((t - 180 - t_off)/20)**2)
        for peak in np.sort(rng.choice(np.arange(500, 649500, 7), per, replace=False)):
            rows.append({'record_id': str(rec), 'r_peak_sample': str(int(peak))})
        xs.append(template + 0.3*rng.standard_normal((per, 360)))
    return rows, np.ascontiguousarray(np.concatenate(xs), dtype='<f4')


def smoke(output, device='auto', epochs=3, resamples=200):
    """Random metadata and synthetic beats (6 records x 160), real rho0/rho1 checkpoints, s0 (capacity rule), s2 rho0/rho1
    and s9 rho0; s2 rho1 repeated to check determinism. No MITDB file is read; numbers here say nothing about MITDB."""
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Smoke output must be a new path under ignored ml/data')
    p = protocol()
    cfg = {**settings(p), 'max_epochs': epochs, 'resamples': resamples}
    precision = set_precision()
    configure()
    dev = device_of(device)
    rows, x = synthetic_beats(np.random.default_rng(12345), [101, 106, 108, 109, 112, 114], 160)
    split = time_split(rows, p['data']['trial_week11'])
    table = checkpoint_table(p)
    rho0, rho1 = load_rho(table['rho0']), load_rho(table['rho1']['s2'], rho1=True)
    models = {(0, 'rho0'): rho0, (2, 'rho0'): rho0, (2, 'rho1'): rho1, (9, 'rho0'): rho0,
              'sha': {(0, 'rho0'): table['rho0']['sha256'], (2, 'rho0'): table['rho0']['sha256'],
                      (2, 'rho1'): table['rho1']['s2']['sha256'], (9, 'rho0'): table['rho0']['sha256']}}
    order = [['s0', 'rho0'], ['s2', 'rho0'], ['s2', 'rho1'], ['s9', 'rho0']]
    output.mkdir(parents=True)
    results, rows_out, capacity = run_pairs(models, x, split, order, cfg, dev, output)
    again, _, _ = evaluate_pair(rho1, x, split, 2, capacity['decision'], cfg, dev)
    first = results['s2-rho1']
    same = (json.dumps(again['B_naive'], sort_keys=True) == json.dumps(first['B_naive'], sort_keys=True)
            and json.dumps(again['A1'], sort_keys=True) == json.dumps(first['A1'], sort_keys=True))
    need(same, 'Smoke determinism check failed: s2 rho1 rerun differs')
    need(results['s0-rho0-base']['B_naive']['bacc_mean'] > 2/split['n'], 'Smoke attacker did not learn the synthetic identities at s0')
    need(all(results[k]['A1']['metrics']['NRMSE']['mean'] < 1 for k in ('s2-rho0', 's2-rho1')), 'Smoke decoder did not learn at s2')
    result = {'status': 'SMOKE_PASS_RANDOM_DATA_NOT_MITDB', 'epochs': epochs, 'resamples': resamples, **environment(dev, precision),
              'counts': split_counts(split, len(rows)), 'capacity_check': capacity, 'table': rows_out, 's2_rho1_rerun_identical': same}
    write_json(output/'smoke-result.json', result)
    return result


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('mode', choices=['prepare', 'preflight', 'smoke', 'run-trial'])
    a.add_argument('--plan', type=Path, default=Path(PLAN_DIR)/'plan-manifest.json')
    a.add_argument('--output', type=Path)
    a.add_argument('--authorization', type=Path)
    a.add_argument('--device', default='auto')
    a.add_argument('--epochs', type=int, default=3)
    args = a.parse_args()
    if args.mode == 'prepare':
        print('PLAN', prepare(Path(PLAN_DIR)))
    elif args.mode == 'preflight':
        print(json.dumps(preflight(ROOT/args.plan), indent=2))
    elif args.mode == 'smoke':
        print(json.dumps(smoke(args.output, args.device, args.epochs), indent=2))
    else:
        print(json.dumps(run_trial(ROOT/args.plan, args.output, args.authorization, args.device), indent=2))


if __name__ == '__main__':
    main()
