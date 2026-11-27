"""NoPeek stage of M1 under protocol mitdb-m1-nopeek-v2: plan, preflight, pilot/grid runs and selection.

Training never starts without an external lock and train authorization that binds the protocol, the plan and
the SV1 review evidence file. Only DS1 train/val arrays are read. `smoke` trains on random arrays it writes
itself (no MITDB file). Protocol v2 runs every training and evaluation step with TF32 off (cuDNN and matmul).
`run-pilot-grid` applies pilot.after_pilot: the grid starts at once when the pilot chooses a safe learning rate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ml/src'))
import package_m1_v4_a as pkg  # noqa: E402
from baseline_sampler_v4 import build_sampler  # noqa: E402
from m1_metrics_v4 import confusion, freeze_validation_policy, validation_metrics  # noqa: E402
from week3_common import need, read_json, sha, write_json  # noqa: E402
from week3_sv2_common import CUTS, wrappers  # noqa: E402

PROTOCOL = 'ml/configs/mitdb_m1_nopeek_protocol_v2.json'
PLAN_DIR = 'ml/manifests/mitdb-nopeek-m1-v2'
METRIC_POLICY = 'ml/manifests/mitdb-ds1ds2-m1-v3-r2/metric-policy.json'
SOURCES = ['ml/scripts/nopeek_m1_v2.py', 'ml/scripts/package_m1_v4_a.py', 'ml/scripts/baseline_sampler_v4.py',
           'ml/scripts/m1_metrics_v4.py', 'ml/scripts/week3_common.py', 'ml/scripts/week3_sv2_common.py', 'ml/scripts/week4_common.py',
           'ml/src/distance_correlation.py', 'ml/src/nopeek.py', 'ml/src/mitdb_baseline_model.py']
AUTH_TYPE = 'M1_NOPEEK_V2_LOCK_AND_TRAIN_AUTHORIZATION'
REVIEW_EVIDENCE_KEY = 'sv1_review_20261109'  # Protocol source binding the lock must name as review evidence.


def precision_flags(protocol):
    """TF32 flags of protocol v2 training.precision; v2 only allows both off."""
    p = protocol['training']['precision']
    need(p['cudnn_allow_tf32'] is False and p['matmul_allow_tf32'] is False, 'Protocol v2 requires TF32 off for cuDNN and matmul')
    return {'cudnn_allow_tf32': False, 'matmul_allow_tf32': False}


def set_precision(config):
    """Apply the config's TF32 flags (must be off) and return what PyTorch reports after setting them."""
    import torch
    need(config.get('cudnn_allow_tf32') is False and config.get('matmul_allow_tf32') is False,
         'Run config must carry cudnn_allow_tf32 false and matmul_allow_tf32 false (protocol v2 training.precision)')
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    need(torch.backends.cudnn.allow_tf32 is False and torch.backends.cuda.matmul.allow_tf32 is False, 'TF32 still enabled after setting it off')
    state = {'cudnn_allow_tf32': torch.backends.cudnn.allow_tf32, 'matmul_allow_tf32': torch.backends.cuda.matmul.allow_tf32}
    for name, get in (('cudnn_conv_fp32_precision', lambda: torch.backends.cudnn.conv.fp32_precision),
                      ('matmul_fp32_precision', lambda: torch.backends.cuda.matmul.fp32_precision)):
        try:  # Newer PyTorch also exposes the fp32_precision API; recorded for the receipt, never set here.
            state[name] = str(get())
        except (AttributeError, RuntimeError) as error:
            state[name] = f'unavailable: {type(error).__name__}'
    return state


# ---------- plan ----------

def run_id(stage, s, lam, seed, lr=None):
    return f"{stage}-s{s}-lambda{lam:g}-seed{seed}" + (f"-lr{lr:g}" if lr is not None else '')


def prepare(output):
    """Write the candidate plan: 9 pilot and 72 grid run configs, each bound by SHA-256."""
    output = ROOT/output
    need(not output.exists(), 'Plan directory exists; a new protocol version needs a new plan directory')
    p = read_json(ROOT/PROTOCOL)
    lock, deployment, plan_v4, _ = pkg.locked()
    counts = [int(n) for n in read_json(ROOT/'ml/manifests/mitdb-ds1ds2-m1-v3-r2/processed-manifest.json')['splits']['train']['counts']]
    common = {'protocol_sha256': sha(ROOT/PROTOCOL), 'init_checkpoint': deployment['path'], 'init_checkpoint_sha256': deployment['sha256'],
              'batch_size': p['training']['batch_size'], 'epochs': p['training']['epochs'], 'optimizer': p['training']['optimizer'],
              'samples_per_epoch': p['training']['sampler']['samples_per_epoch'], 'train_counts': counts, 'dropout': 0.2,
              # Protocol v2 training.precision: TF32 off (SV1 2026-11-09 item 4(5)); A itself was trained with cuDNN TF32 on.
              **precision_flags(p), 'DS2_access': False}
    runs = []
    pilot_seed = 20261030
    for lr in p['pilot']['learning_rate_candidates']:
        runs.append({'stage': 'pilot', 's': 2, 'lambda': 0, 'seed': pilot_seed, 'lr': lr})
        runs += [{'stage': 'pilot', 's': s, 'lambda': 5, 'seed': pilot_seed, 'lr': lr} for s in (2, 8)]
    g = p['grid']
    runs += [{'stage': 'grid', 's': s, 'lambda': lam, 'seed': seed, 'lr': None} for seed in g['seeds'] for s in g['s'] for lam in g['lambda']]
    output.mkdir(parents=True)
    rows = []
    for r in runs:
        rid = run_id(r['stage'], r['s'], r['lambda'], r['seed'], r['lr'] if r['stage'] == 'pilot' else None)
        config = {**common, **r, 'run_id': rid, 'lr_source': 'config' if r['stage'] == 'pilot' else 'pilot_decision'}
        write_json(output/f'{rid}.json', config)
        rows.append({'run_id': rid, 'stage': r['stage'], 'config': f'{rid}.json', 'sha256': sha(output/f'{rid}.json')})
    need(sum(r['stage'] == 'pilot' for r in rows) == 9 and sum(r['stage'] == 'grid' for r in rows) == g['runs'] == 72, 'Run count differs')
    need(len({r['run_id'] for r in rows}) == len(rows), 'Duplicate run id')
    plan = {'schema': 'm1-nopeek-plan/1', 'status': 'CANDIDATE_NOT_LOCKED', 'protocol_sha256': common['protocol_sha256'],
            'checkpoint_lock_sha256': pkg.LOCK_SHA, 'arrays': pkg.ARRAYS, 'data_files': plan_v4['binding']['data_files'],
            'metric_policy': {'path': METRIC_POLICY, 'sha256': sha(ROOT/METRIC_POLICY)},
            'dcor_subset': {'path': p['data']['dcor_validation_subset']['path'], 'sha256': p['data']['dcor_validation_subset']['sha256']},
            'sources_sha256': {n: sha(ROOT/n) for n in SOURCES}, 'runs': rows}
    write_json(output/'plan-manifest.json', plan)
    return sha(output/'plan-manifest.json')


def require_authorization(path, plan_path):
    need(path is not None and Path(path).is_file(), 'External NoPeek lock and train authorization required')
    a = read_json(path)
    need(a.get('type') == AUTH_TYPE and a.get('allow_training') is True and a.get('protocol_sha256') == sha(ROOT/PROTOCOL) and
         a.get('plan_manifest_sha256') == sha(plan_path) and bool(a.get('approved_by')) and bool(a.get('review_evidence')),
         'Authorization does not bind the protocol and plan')
    # The review evidence is a file in the repo whose SHA-256 the runner checks, and it is the SV1 review the protocol names.
    declared = read_json(ROOT/PROTOCOL)['source_bindings'][REVIEW_EVIDENCE_KEY]
    evidence = a.get('review_evidence_path')
    need(isinstance(evidence, str) and evidence == declared['path'] and (ROOT/evidence).is_file() and
         a['review_evidence'] == declared['raw_sha256'] == sha(ROOT/evidence),
         'Authorization review evidence is not the SV1 review file named by the protocol, or its SHA-256 differs')
    return a


def preflight(plan_path):
    """Bindings only: hashes of protocol, plan runs, sources, arrays, policy, subset and checkpoint. No model, no fit."""
    plan = read_json(plan_path)
    need(plan['protocol_sha256'] == sha(ROOT/PROTOCOL) and plan['checkpoint_lock_sha256'] == pkg.LOCK_SHA, 'Plan binding differs')
    need(all(sha(ROOT/n) == h for n, h in plan['sources_sha256'].items()), 'Source differs from plan')
    for r in plan['runs']:
        need(sha(Path(plan_path).parent/r['config']) == r['sha256'], f"Run config differs: {r['run_id']}")
    for name, expected in plan['data_files'].items():
        need(not name.startswith('test') and sha(ROOT/plan['arrays']/name) == expected['sha256'], f'Array differs: {name}')
    for key in ('metric_policy', 'dcor_subset'):
        need(sha(ROOT/plan[key]['path']) == plan[key]['sha256'], f'{key} differs')
    _, deployment, _, _ = pkg.locked()
    return {'status': 'PASS_PREFLIGHT_NO_MODEL_NO_FIT_NO_DS2', 'runs': len(plan['runs']), 'init_checkpoint_sha256': deployment['sha256']}


# ---------- data ----------

def load_arrays(directory):
    out = {}
    for split in ('train', 'val'):
        x = np.load(directory/f'{split}_X.npy', allow_pickle=False)
        y = np.load(directory/f'{split}_y.npy', allow_pickle=False)
        need(x.dtype == np.dtype('<f4') and y.dtype == np.dtype('<i8') and x.shape == (len(y), 360) and bool(np.isfinite(x).all()), f'{split} contract differs')
        out[split] = (x, y)
    return out


def a_confusion():
    """Locked package A validation confusion of the deployment checkpoint (from the analyze output the lock binds)."""
    _, deployment, _, _ = pkg.locked()
    analysis = read_json(ROOT/read_json(ROOT/pkg.LOCK)['bindings']['analyze_stdout']['path'])
    return next(s['validation']['confusion_matrix'] for cfg in analysis['configurations'] for s in cfg['seeds']
                if s['checkpoint_sha256'] == deployment['sha256'])


def subset_indices(path, n_val):
    with (ROOT/path).open(encoding='utf-8', newline='') as f:
        idx = [int(r['validation_row_index']) for r in csv.DictReader(f)]
    need(len(idx) == 512 and len(set(idx)) == 512 and all(0 <= i < n_val for i in idx), 'dCor subset differs')
    return idx


# ---------- training ----------

def state_digest(model):
    h = hashlib.sha256()
    for k, v in sorted(model.state_dict().items()):
        h.update(k.encode())
        h.update(v.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def fit_run(config, config_sha, data, policy, subset, output, lr, expected_epoch0=None, device='auto'):
    """One run from the package A checkpoint: epoch 0 evaluation, then config['epochs'] epochs of CE + lambda * R_n."""
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    import random
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    from distance_correlation import distance_correlation
    from nopeek import nopeek_loss
    c, seed = config, config['seed']
    need(lr is not None and lr > 0 and math.isfinite(lr), 'Learning rate required')
    precision = set_precision(c)  # Before the model is built; refuses a config with TF32 on.
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    dev = torch.device('cuda' if device == 'auto' and torch.cuda.is_available() else 'cpu' if device == 'auto' else device)
    _, deployment, _, slot_config = pkg.locked()
    need(deployment['sha256'] == c['init_checkpoint_sha256'], 'Init checkpoint differs from config')
    model = pkg.load_model(deployment, slot_config).to(dev)
    head, tail = wrappers(model, c['s'])
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, betas=tuple(c['optimizer']['betas']), eps=c['optimizer']['eps'],
                                  weight_decay=c['optimizer']['weight_decay'])
    tx, ty = data['train']
    vx, vy = data['val']
    train = TensorDataset(torch.from_numpy(np.array(tx, copy=True)).unsqueeze(1), torch.from_numpy(np.array(ty, copy=True)))
    val_x = torch.from_numpy(np.array(vx, copy=True)).unsqueeze(1)
    sub_x = val_x[subset].to(dev)

    def evaluate():
        model.eval()
        pred = []
        with torch.no_grad():
            for i in range(0, len(val_x), c['batch_size']):
                pred.append(tail(head(val_x[i:i+c['batch_size']].to(dev))).argmax(1).cpu())
            rn = float(distance_correlation(sub_x, head(sub_x)))
        m = validation_metrics(vy.tolist(), torch.cat(pred).tolist(), policy)
        m['subset_Rn'] = rn
        return m

    def save(epoch, m):
        state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        torch.save({'state_dict': state, 'epoch': epoch, 'run_config_sha256': config_sha, 'protocol_sha256': c['protocol_sha256'],
                    'validation_confusion': m['confusion_matrix']}, output/f'checkpoint-epoch-{epoch:03}.pt')
        return state

    output.mkdir(parents=True)
    write_json(output/'attempt-identity.json', {'run_id': c['run_id'], 'config_sha256': config_sha, 'seed': seed, 'lr': lr, 'device': str(dev),
               'device_name': torch.cuda.get_device_name(dev) if dev.type == 'cuda' else 'CPU', 'torch': torch.__version__,
               'cuda': torch.version.cuda, **precision, 'DS2_arrays_opened': False})
    history = []
    m = evaluate()
    if expected_epoch0 is not None:
        need(m['confusion_matrix'] == expected_epoch0, 'Epoch 0 does not reproduce package A validation confusion')
    states = {0: save(0, m)}
    history.append({'epoch': 0, 'validation': m, 'state_sha256': state_digest(model), 'lr': lr})
    for epoch in range(1, c['epochs']+1):
        generator = torch.Generator().manual_seed(seed+epoch-1)
        loader = DataLoader(train, batch_size=c['batch_size'], sampler=build_sampler(ty, c['train_counts'], generator), num_workers=0, drop_last=False)
        model.train()
        ce = rn = 0.
        seen = 0
        for x, y in loader:
            x, y = x.to(dev), y.to(dev)
            optimizer.zero_grad(set_to_none=True)
            z = head(x)
            loss, parts = nopeek_loss(tail(z), y, x, z, c['lambda'])
            need(bool(torch.isfinite(loss)), 'Non-finite loss')
            loss.backward()
            optimizer.step()
            ce += float(parts['ce'].detach())*len(y)
            rn += float(parts['dcor'].detach())*len(y)
            seen += len(y)
        need(seen == c['samples_per_epoch'], 'Epoch sample count differs')
        m = evaluate()
        states[epoch] = save(epoch, m)
        history.append({'epoch': epoch, 'validation': m, 'train_CE_mean': ce/seen, 'train_batch_Rn_mean': rn/seen,
                        'state_sha256': state_digest(model), 'lr': optimizer.param_groups[0]['lr']})
        write_json(output/f'epoch-{epoch:03}.json', history[-1])
    for row in history:  # Every saved state must reproduce its logged validation confusion after reload.
        model.load_state_dict(states[row['epoch']])
        need(evaluate()['confusion_matrix'] == row['validation']['confusion_matrix'], f"Reload differs at epoch {row['epoch']}")
    write_json(output/'history.json', history)
    write_json(output/'summary.json', {'status': 'COMPLETED_NOT_SELECTION', 'run_id': c['run_id'], 'config_sha256': config_sha,
               'history_sha256': sha(output/'history.json'), 'epochs': len(history)-1, 'reload_confusion_exact': True,
               'checkpoints_sha256': {f'checkpoint-epoch-{e:03}.pt': sha(output/f'checkpoint-epoch-{e:03}.pt') for e in states},
               'DS2_evaluated': False})
    return history


def run_stage(stage, plan_path, output, authorization, pilot_decision=None):
    require_authorization(authorization, plan_path)  # Before data, model, optimizer or output.
    preflight(plan_path)
    plan = read_json(plan_path)
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Run output must be a new path under ignored ml/data')
    lr_grid = None
    if stage == 'grid':
        d = read_json(pilot_decision)
        need(d.get('status') == 'PILOT_LR_CHOSEN' and d.get('plan_manifest_sha256') == sha(plan_path), 'Pilot decision does not bind this plan')
        lr_grid = d['learning_rate']
    a_conf = a_confusion()
    data = load_arrays(ROOT/plan['arrays'])
    policy = read_json(ROOT/plan['metric_policy']['path'])
    subset = subset_indices(plan['dcor_subset']['path'], len(data['val'][1]))
    output.mkdir(parents=True)
    done = []
    for r in plan['runs']:
        if r['stage'] != stage:
            continue
        config = read_json(Path(plan_path).parent/r['config'])
        lr = config['lr'] if stage == 'pilot' else lr_grid
        fit_run(config, r['sha256'], data, policy, subset, output/r['run_id'], lr, expected_epoch0=a_conf)
        done.append(r['run_id'])
    write_json(output/'stage-result.json', {'stage': stage, 'plan_manifest_sha256': sha(plan_path), 'runs': done, 'status': 'ALL_RUNS_COMPLETED'})
    return done


def run_pilot_grid(plan_path, output, authorization):
    """Protocol v2 pilot.after_pilot: pilot, pilot decision, then the grid at once when a safe learning rate exists."""
    require_authorization(authorization, plan_path)  # Before data, model, optimizer or output.
    root = (ROOT/output).resolve()
    need(root.is_relative_to(ROOT/'ml/data') and not root.exists(), 'Run output must be a new path under ignored ml/data')
    pilot = run_stage('pilot', plan_path, root/'pilot', authorization)
    plan = read_json(plan_path)
    plan['_dir'] = str(Path(plan_path).parent)
    decision = choose_pilot(root/'pilot', plan, a_confusion())
    decision['plan_manifest_sha256'] = sha(plan_path)
    write_json(root/'pilot-decision.json', decision)
    result = {'pilot_runs': pilot, 'pilot_decision': {'path': str((root/'pilot-decision.json').relative_to(ROOT).as_posix()),
              'sha256': sha(root/'pilot-decision.json'), 'status': decision['status']}}
    if decision['status'] != 'PILOT_LR_CHOSEN':  # Protocol pilot.no_safe_candidate: stop, report to SV1.
        result['grid'] = 'NOT_STARTED_NO_SAFE_LEARNING_RATE'
    else:
        result['grid_runs'] = run_stage('grid', plan_path, root/'grid', authorization, root/'pilot-decision.json')
        result['learning_rate'] = decision['learning_rate']
    write_json(root/'pilot-grid-result.json', result)
    return result


# ---------- selection ----------

def macro_f1_exact(matrix):
    c = [[int(v) for v in row] for row in matrix]
    sup = [sum(r) for r in c]
    pred = [sum(c[i][j] for i in range(5)) for j in range(5)]
    f1 = [Fraction(2*c[k][k], sup[k]+pred[k]) if sup[k]+pred[k] else Fraction(0) for k in range(4)]
    return sum(f1)/4


def passes(matrix, a_matrix):
    return macro_f1_exact(matrix) >= Fraction(19, 20)*macro_f1_exact(a_matrix)


def collapsed(matrix):
    c = np.asarray(matrix, dtype=np.int64)
    n, pred, tp_v, sup_v = int(c.sum()), c.sum(0), int(c[2, 2]), int(c[2].sum())
    return bool(100*int(pred.max()) >= 99*n or 10*tp_v < sup_v)


def select_epoch(history, lam, a_matrix):
    rows = {h['epoch']: h['validation'] for h in history}
    if lam == 0:
        best = max(rows, key=lambda e: (macro_f1_exact(rows[e]['confusion_matrix']), -e))
        return {'epoch': best, 'utility': passes(rows[best]['confusion_matrix'], a_matrix), 'flag': 'LAMBDA0'}
    ok = [e for e in rows if e >= 1 and passes(rows[e]['confusion_matrix'], a_matrix)]
    if ok:
        return {'epoch': min(ok, key=lambda e: (rows[e]['subset_Rn'], e)), 'utility': True, 'flag': 'OK'}
    best = max((e for e in rows if e >= 1), key=lambda e: (macro_f1_exact(rows[e]['confusion_matrix']), -e))
    return {'epoch': best, 'utility': False, 'flag': 'UTILITY_FAIL'}


def choose_pilot(results, plan, a_matrix):
    """Protocol pilot rule: safe = lambda 0 passes at all epochs 1-10 without collapse; then lowest mean min-Rn of lambda 5."""
    by = {}
    for r in plan['runs']:
        if r['stage'] == 'pilot':
            c = read_json(Path(plan['_dir'])/r['config'])
            by[(c['lr'], c['lambda'], c['s'])] = read_json(results/r['run_id']/'history.json')
    rows = []
    for lr in sorted({k[0] for k in by}):
        h0 = [h for h in by[(lr, 0, 2)] if h['epoch'] >= 1]
        safe = all(passes(h['validation']['confusion_matrix'], a_matrix) and not collapsed(h['validation']['confusion_matrix']) for h in h0)
        mins = []
        for s in (2, 8):
            ok = [h['validation']['subset_Rn'] for h in by[(lr, 5, s)] if h['epoch'] >= 1 and passes(h['validation']['confusion_matrix'], a_matrix)]
            mins.append(min(ok) if ok else 1.)
        rows.append({'learning_rate': lr, 'safe': safe, 'lambda0_epochs_passing': sum(passes(h['validation']['confusion_matrix'], a_matrix) for h in h0),
                     'lambda5_min_Rn': dict(zip(('s2', 's8'), mins)), 'score': sum(mins)/2})
    safe = [r for r in rows if r['safe']]
    if not safe:
        return {'status': 'NO_SAFE_LEARNING_RATE_REPORT_TO_SV1', 'candidates': rows}
    best = min(safe, key=lambda r: (r['score'], r['learning_rate']))
    return {'status': 'PILOT_LR_CHOSEN', 'learning_rate': best['learning_rate'], 'candidates': rows}


def choose_grid(results, plan, a_matrix):
    runs = {}
    for r in plan['runs']:
        if r['stage'] == 'grid':
            c = read_json(Path(plan['_dir'])/r['config'])
            runs[(c['s'], c['lambda'], c['seed'])] = read_json(results/r['run_id']/'history.json')
    seeds = sorted({k[2] for k in runs})
    # Lambda 0 trains without a dCor gradient, so its states must be identical across s.
    determinism = {seed: len({tuple(h['state_sha256'] for h in runs[(s, 0, seed)]) for s in sorted({k[0] for k in runs})}) == 1 for seed in seeds}
    need(all(determinism.values()), 'Lambda 0 states differ across s: investigate as a technical fault before selection')
    out = {}
    for s in sorted({k[0] for k in runs}):
        table = []
        for lam in sorted({k[1] for k in runs}):
            sel = []
            for seed in seeds:
                h = runs[(s, lam, seed)]
                e = select_epoch(h, lam, a_matrix)
                v = h[e['epoch']]['validation']
                sel.append({'seed': seed, **e, 'subset_Rn': v['subset_Rn'], 'macro_f1': v['validation_macro_f1_K_fixed'],
                            'accuracy': v['accuracy'], 'collapsed': collapsed(v['confusion_matrix'])})
            rn = [x['subset_Rn'] for x in sel]
            eligible = all(x['utility'] and not x['collapsed'] for x in sel)
            table.append({'lambda': lam, 'eligible': eligible, 'mean_Rn': statistics.fmean(rn), 'sd_Rn_ddof1': statistics.stdev(rn),
                          'mean_macro_f1': statistics.fmean(x['macro_f1'] for x in sel), 'sd_macro_f1_ddof1': statistics.stdev(x['macro_f1'] for x in sel),
                          'seeds': sel})
        chosen = min((t for t in table if t['eligible']), key=lambda t: (t['mean_Rn'], t['lambda']))
        ranked = sorted(chosen['seeds'], key=lambda x: (x['subset_Rn'], x['seed']))
        median = ranked[1]['subset_Rn']
        deployment = min(x['seed'] for x in chosen['seeds'] if x['subset_Rn'] == median)
        out[f's{s}'] = {'lambda': chosen['lambda'], 'deployment_seed': deployment, 'table': table}
    return {'status': 'SELECTED_FOR_SV1_REVIEW_NOT_LOCKED', 'lambda0_identical_across_s': determinism, 'per_s': out}


def lambda0_report(results, plan, a_matrix):
    """Per-epoch lambda 0 macro-F1 (epochs 0-10, three seeds) and per-lambda pass counts, sent to SV1 before any Pi."""
    rows = {}
    passes_count = {}
    for r in plan['runs']:
        if r['stage'] != 'grid':
            continue
        c = read_json(Path(plan['_dir'])/r['config'])
        h = read_json(results/r['run_id']/'history.json')
        if c['lambda'] == 0 and c['s'] == 2:
            rows[c['seed']] = [{'epoch': x['epoch'], 'macro_f1': x['validation']['validation_macro_f1_K_fixed'],
                                'passes': passes(x['validation']['confusion_matrix'], a_matrix)} for x in h]
        key = f"s{c['s']}-lambda{c['lambda']:g}"
        passes_count[key] = passes_count.get(key, 0) + sum(passes(x['validation']['confusion_matrix'], a_matrix) for x in h if x['epoch'] >= 1)
    return {'threshold_exact': str(Fraction(19, 20)*macro_f1_exact(a_matrix)), 'lambda0_by_seed': rows,
            'epochs_1_10_passing_summed_over_seeds': passes_count}


# ---------- smoke ----------

def smoke(output, epochs=2):
    """Random arrays with the real class counts; two runs (lambda 0 and 5 at s2) plus lambda 0 at s8. No MITDB file is read."""
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Smoke output must be a new path under ignored ml/data')
    rng = np.random.default_rng(12345)
    manifest = read_json(ROOT/'ml/manifests/mitdb-ds1ds2-m1-v3-r2/processed-manifest.json')['splits']
    arrays = output/'fake_arrays'
    arrays.mkdir(parents=True)
    data = {}
    for split in ('train', 'val'):
        counts = manifest[split]['counts']
        y = np.repeat(np.arange(5, dtype='<i8'), counts)
        rng.shuffle(y)
        x = rng.standard_normal((len(y), 360)).astype('<f4')
        np.save(arrays/f'{split}_X.npy', x, allow_pickle=False)
        np.save(arrays/f'{split}_y.npy', y, allow_pickle=False)
    data = load_arrays(arrays)
    policy = freeze_validation_policy(data['val'][1].tolist())
    subset = list(range(512))
    base = {'protocol_sha256': sha(ROOT/PROTOCOL), 'init_checkpoint_sha256': pkg.locked()[1]['sha256'], 'batch_size': 256, 'epochs': epochs,
            'optimizer': {'betas': [0.9, 0.999], 'eps': 1e-08, 'weight_decay': 0.0001}, 'samples_per_epoch': int(len(data['train'][1])),
            'train_counts': manifest['train']['counts'], 'seed': 20261030, **precision_flags(read_json(ROOT/PROTOCOL))}
    results = {}
    for s, lam in ((2, 0), (8, 0), (2, 5)):
        config = {**base, 's': s, 'lambda': lam, 'run_id': f'smoke-s{s}-lambda{lam}'}
        results[config['run_id']] = fit_run(config, 'SMOKE', data, policy, subset, output/config['run_id'], 1e-5)
    same = [h['state_sha256'] for h in results['smoke-s2-lambda0']] == [h['state_sha256'] for h in results['smoke-s8-lambda0']]
    moved = results['smoke-s2-lambda5'][-1]['state_sha256'] != results['smoke-s2-lambda5'][0]['state_sha256']
    need(same and moved, 'Smoke determinism or update check failed')
    result = {'status': 'SMOKE_PASS_RANDOM_DATA_NOT_MITDB', 'epochs': epochs, 'runs': list(results),
              'lambda0_identical_across_s2_s8': same, 'lambda5_weights_changed': moved,
              'epoch0_state_equals_package_A': all(h[0]['state_sha256'] == results['smoke-s2-lambda0'][0]['state_sha256'] for h in results.values()),
              'subset_Rn_lambda5': [h['validation']['subset_Rn'] for h in results['smoke-s2-lambda5']]}
    write_json(output/'smoke-result.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'preflight', 'run', 'run-pilot-grid', 'analyze-pilot', 'analyze-grid', 'lambda0-report', 'smoke'])
    p.add_argument('--plan', type=Path, default=Path(PLAN_DIR)/'plan-manifest.json')
    p.add_argument('--stage', choices=['pilot', 'grid'])
    p.add_argument('--output', type=Path)
    p.add_argument('--results', type=Path)
    p.add_argument('--authorization', type=Path)
    p.add_argument('--pilot-decision', type=Path)
    p.add_argument('--epochs', type=int, default=2)
    a = p.parse_args()
    if a.mode == 'prepare':
        print('PLAN', prepare(Path(PLAN_DIR)))
    elif a.mode == 'preflight':
        print(json.dumps(preflight(ROOT/a.plan), indent=2))
    elif a.mode == 'run':
        print(json.dumps(run_stage(a.stage, ROOT/a.plan, a.output, a.authorization, a.pilot_decision), indent=2))
    elif a.mode == 'run-pilot-grid':
        print(json.dumps(run_pilot_grid(ROOT/a.plan, a.output, a.authorization), indent=2))
    elif a.mode == 'smoke':
        print(json.dumps(smoke(a.output, a.epochs), indent=2))
    else:
        plan = read_json(ROOT/a.plan)
        plan['_dir'] = str((ROOT/a.plan).parent)
        need(plan['protocol_sha256'] == sha(ROOT/PROTOCOL), 'Plan binding differs')
        f = {'analyze-pilot': choose_pilot, 'analyze-grid': choose_grid, 'lambda0-report': lambda0_report}[a.mode]
        result = f(ROOT/a.results, plan, a_confusion())
        result['plan_manifest_sha256'] = sha(ROOT/a.plan)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
