"""Attack stage of M1 under protocol v3 revision 5 (locked): S0c observed tensor, part a (s9, s10, s0c under rho0),
part b (B_composite and Pi_v3), part d (k-beat vote under rho0) and the k-beat aggregators that part c
(noise_m1_v3.py) shares.

No run reads a MITDB array without an external run authorization that binds the protocol, the protocol lock, the
plan (sources, checkpoint A, arrays, the saved v2 trial outputs) and the SV1 review evidence. DS1 train/val only;
DS2 is never opened. `smoke` runs parts a, b, d on synthetic beats it makes itself, with checkpoint A, and reads no
MITDB file and no v2 trial output. Settings, attack models, time split and metrics are those of v2 (attack_m1_v2.py),
reused, not copied, so every inherited rule stays identical.
"""
from __future__ import annotations

import attack_m1_v2 as v2  # noqa: I001  (sets CUBLAS_WORKSPACE_CONFIG before torch creates a CUDA context)

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

import package_m1_v4_a as pkg  # noqa: E402
from quantization import dequantize_per_channel, quantize_per_channel, to_ncl  # noqa: E402
from week3_common import need, read_json, sha, write_json  # noqa: E402
from week3_sv2_common import CUTS, OPS, configure  # noqa: E402

ROOT = v2.ROOT
PROTOCOL = 'ml/configs/mitdb_m1_attack_protocol_v3_r5.json'
PROTOCOL_SHA = '9235b795ec53b9d4c79e90cad4f1114c260e05b8070c67a62fc23be656ca82fb'
LOCK = 'ml/provenance/m1-attack-v3-r5-lock-20261126/m1_attack_v3_r5_protocol_lock.json'
LOCK_SHA = 'b3a89cbb07c23ca05671c3d8e95435a2de86d810775e80ec0d077c94d0eafff3'
PLAN_DIR = 'ml/manifests/mitdb-attack-m1-v3'
V2_RUNS = 'ml/data/runs/attack-m1-v2-trial-20261113'
AUTH_TYPE = 'M1_ATTACK_V3_RUN_AUTHORIZATION'
SOURCES = ['ml/scripts/attack_m1_v3.py', 'ml/scripts/noise_m1_v3.py', 'ml/scripts/nopeek_m1_v2.py', 'ml/scripts/baseline_sampler_v4.py',
           'ml/scripts/m1_metrics_v4.py', *v2.SOURCES]
SOURCES_B = ['s0', 's0c', 's2', 's4', 's5', 's8', 's9']
TARGETS_B = [2, 4, 5, 8, 9, 10]
PART_D_ROWS = ['s0c', 's0', 's2', 's4', 's5', 's8', 's9', 's10']  # pair_key = index; s0c is the primary row.
SEED_BASE = 20261120
SCATTER_TAG = 4  # SeedSequence([20261120, 4, pair_key, k]) of k_beat_vote.modes.scattered.
SCATTER_DRAWS = 200
CHUNK = 256  # Blocks averaged at a time by the mean aggregator (memory only; results do not depend on it).


# ---------- protocol, lock, settings ----------

def protocol():
    need(sha(ROOT/PROTOCOL) == PROTOCOL_SHA, 'Protocol v3 r5 differs from the locked SHA-256')
    return read_json(ROOT/PROTOCOL)


def require_lock():
    """The protocol lock the user provided: it binds r5 and grants neither runs nor DS2 by itself."""
    need(sha(ROOT/LOCK) == LOCK_SHA, 'Protocol lock differs')
    lock = read_json(ROOT/LOCK)
    need(lock['type'] == 'M1_ATTACK_V3_R5_PROTOCOL_LOCK' and lock['protocol_locked'] is True
         and lock['protocol_sha256'] == PROTOCOL_SHA, 'Lock does not lock protocol v3 r5')
    return lock


def settings():
    """v2 settings (inherited unchanged) plus the k-beat values of v3."""
    p = protocol()
    k = p['k_beat_vote']
    cfg = v2.settings(v2.protocol())
    cfg.update(k_values=list(k['k_values']), k_decision=k['k_decision'], scatter_draws=SCATTER_DRAWS, k_resamples=cfg['resamples'])
    need(cfg['k_decision'] in cfg['k_values'] and '200 draws' in k['modes']['scattered'], 'k-beat settings differ from the protocol')
    return cfg


# ---------- S0c v1 (vectorized; must equal the reference bit for bit before any S0c number) ----------

def s0c_reference():
    """The bound numpy reference, executed from its authenticated bytes."""
    b = protocol()['source_bindings']['s0c_definition']['reference']
    path = ROOT/b['path']
    need(sha(path) == b['sha256'], 'S0c v1 reference differs')
    module = {'__name__': 's0c_v1_ref'}
    exec(compile(path.read_bytes(), str(path), 'exec'), module)
    return SimpleNamespace(**module)


N_IN, N_OUT = 360, 46
BINS = [((i*N_IN)//N_OUT, -((-(i + 1)*N_IN)//N_OUT)) for i in range(N_OUT)]


def _interpolation_table():
    scale = np.float32(N_OUT)/np.float32(N_IN)
    i0, i1, w = np.empty(N_IN, np.int64), np.empty(N_IN, np.int64), np.empty(N_IN, np.float32)
    for j in range(N_IN):
        src = np.float32(scale*np.float32(np.float32(j) + np.float32(0.5)) - np.float32(0.5))
        src = np.float32(0) if src < 0 else src
        i0[j] = int(np.floor(src))
        i1[j] = min(i0[j] + 1, N_OUT - 1)
        w[j] = np.float32(src - np.float32(i0[j]))
    return i0, i1, w, (np.float32(1) - w).astype(np.float32)


I0, I1, W, ONE_MINUS_W = _interpolation_table()


def reduce46(x):
    """Step 2 for [N, 360] float32: float32 sums over each bin in index order, divided by the float32 bin length."""
    x = np.asarray(x)
    need(x.dtype == np.float32 and x.ndim == 2 and x.shape[1] == N_IN and bool(np.isfinite(x).all()), 'Beats must be finite float32 [N, 360]')
    out = np.empty((len(x), N_OUT), dtype=np.float32)
    for i, (a, b) in enumerate(BINS):
        acc = np.zeros(len(x), dtype=np.float32)
        for t in range(a, b):
            acc = acc + x[:, t]
        out[:, i] = acc/np.float32(b - a)
    return out


def interpolate360(v):
    """Step 7 for [N, 46]: half-pixel linear interpolation in float32, same operation order as the reference."""
    v = np.asarray(v, dtype=np.float32)
    need(v.ndim == 2 and v.shape[1] == N_OUT, 'Reduced beats must be [N, 46]')
    return np.ascontiguousarray(ONE_MINUS_W*v[:, I0] + W*v[:, I1], dtype=np.float32)


def s0c_transmit(v):
    """Steps 3, 6, 7 from (clean or noisy) reduced values [N, 46]: q, FP16 scale (registry v2 rule, C = 1), the
    dequantized values the edge decodes and the 360 interpolated samples x_c. Rice is lossless and is not needed here."""
    q, scale = quantize_per_channel(np.ascontiguousarray(v, dtype=np.float32)[:, None, :])
    deq = dequantize_per_channel(q, scale)[:, 0, :]
    return {'q': q[:, 0, :], 'scale': scale[:, 0], 'deq': deq, 'xc': interpolate360(deq)}


def _bits(a):
    a = np.ascontiguousarray(a)
    return a.view(np.uint16 if a.dtype == np.float16 else np.uint32 if a.dtype == np.float32 else a.dtype)


def s0c_reference_check(x, ref):
    """Every beat: reduced values, q, FP16 scale, dequantized values, x_c and Rice body of the vectorized path against
    the reference. Stops at the first difference (protocol s0c_observed_tensor.implementation)."""
    v = reduce46(x)
    t = s0c_transmit(v)
    sizes = np.empty(len(x), dtype=np.int64)
    for i in range(len(x)):
        body, scale, q = ref.encode(x[i])
        vv, xc = ref.decode(body, scale)
        same = (np.array_equal(_bits(ref.reduce46(x[i])), _bits(v[i])) and np.array_equal(q, t['q'][i])
                and np.float16(scale).view(np.uint16) == t['scale'][i].view(np.uint16)
                and np.array_equal(_bits(vv), _bits(t['deq'][i])) and np.array_equal(_bits(xc), _bits(t['xc'][i]))
                and ref.rice_encode(t['q'][i]) == body)
        need(bool(same), f'S0c vectorized path differs from the reference at beat {i}; S0c items stop before any number')
        sizes[i] = len(body)
    return {'beats': int(len(x)), 'bitwise_equal': True, 'rice_body_bytes': {'mean': float(sizes.mean()), 'max': int(sizes.max())}}


def s0c_golden_check(ref, package):
    """The 20 golden beats of S0c v1: x equals package A golden z_s0, the vectorized path equals every golden array and
    body; then the reference check on the same beats."""
    b = protocol()['source_bindings']['s0c_definition']
    for key in ('golden_npz', 'golden_json'):
        need(sha(ROOT/b[key]['path']) == b[key]['sha256'], f'S0c v1 {key} differs')
    d = np.load(ROOT/b['golden_npz']['path'], allow_pickle=False)
    beats = read_json(ROOT/b['golden_json']['path'])['beats']
    z0 = np.load(Path(package)/'golden/z_s0.npy', allow_pickle=False)
    need(np.array_equal(_bits(d['x']), _bits(z0[:, 0, :])), 'S0c golden x differs from package A golden z_s0')
    v = reduce46(d['x'])
    t = s0c_transmit(v)
    for name, mine in (('reduced_v46', v), ('q', t['q']), ('scale_fp16', t['scale']), ('dequantized_v46', t['deq']),
                       ('reconstructed_x360', t['xc'])):
        need(np.array_equal(_bits(np.asarray(d[name])), _bits(mine)), f'S0c golden {name} differs')
    need([ref.rice_encode(q).hex() for q in t['q']] == [r['body_hex'] for r in beats], 'S0c golden Rice bodies differ')
    return {'beats': int(len(v)), 'arrays_bitwise_equal': True, **s0c_reference_check(d['x'], ref)}


# ---------- observed tensors, frozen ops, composites ----------

def cut_of(src):
    return 0 if src == 's0c' else int(src[1:])


def view_of(model, x, src):
    """What the edge holds at the source, dequantized: s0c -> v [N, 1, 46]; s -> v2 observed_tensor [N, C, L]."""
    return s0c_transmit(reduce46(x))['deq'][:, None, :] if src == 's0c' else v2.observed(model, x, int(src[1:]))


def start_of(view, src):
    """Composite start from the source view: s0c -> x_c [N, 1, 360] (edge interpolation); s9 -> [N, 32]; else the view."""
    if src == 's0c':
        return interpolate360(view[:, 0, :])[:, None, :]
    return np.ascontiguousarray(view[:, :, 0]) if cut_of(src) >= 9 else view


def frozen_ops(model, cut_from, s_to):
    leaves = [(n, m) for n, m in model.named_modules() if n and not list(m.children())]
    need(tuple(n for n, _ in leaves) == OPS and not model.training, 'Frozen operation order mismatch or model not in eval')
    need(CUTS[cut_from] < CUTS[s_to], 'Composite target must be deeper than the source')
    return nn.Sequential(*[m for _, m in leaves][CUTS[cut_from]:CUTS[s_to]]).eval()


def composite(ops, start, s_to, batch=1024):
    """CPU: frozen ops from the source start to s', batched when s' <= 8 and one beat at a time when s' >= 9, then
    to_ncl and registry v2 quantize/dequantize (what the s' attacker was trained on)."""
    start = np.ascontiguousarray(start, dtype='<f4')
    step = batch if s_to <= 8 else 1
    out = []
    with torch.no_grad():
        for i in range(0, len(start), step):
            out.append(ops(torch.from_numpy(start[i:i+step])).numpy().copy())
    z = np.ascontiguousarray(np.concatenate(out), dtype='<f4')
    q, scale = quantize_per_channel(to_ncl(z, s_to))
    return dequantize_per_channel(q, scale)


def fit_stats(train, floor=1e-6):
    """v2 input_standardization: per channel mean and population std over N and L of the attacker-train part."""
    return (train.mean(axis=(0, 2), keepdims=True, dtype=np.float64),
            np.maximum(train.std(axis=(0, 2), keepdims=True, dtype=np.float64), floor))


def attacker_input(u, stats, s):
    f = ((u - stats[0])/stats[1]).astype('<f4')
    return np.ascontiguousarray(f[..., 0]) if s != 's0c' and int(s) >= 9 else f


def predict_seeds(models, f, device):
    """Per seed: argmax predictions [S, N] and log-probabilities [S, N, n] (float32)."""
    logits = [v2.predict(m, torch.from_numpy(np.ascontiguousarray(f)), device) for m in models]
    preds = np.stack([lg.argmax(1) for lg in logits]).astype(np.int64)
    lps = np.stack([torch.log_softmax(torch.from_numpy(lg), dim=1).numpy() for lg in logits]).astype('<f4')
    return preds, lps


def load_b(states, shape, n, arch, seeds, device):
    models = []
    for seed in seeds:
        m = v2.b_classifier(shape, n, arch)
        m.load_state_dict(states[f'B_seed{seed}'], strict=True)
        models.append(m.to(device).eval())
    return models


# ---------- training (v2 rules) with log-probabilities ----------

def class_weight(y_tr, n):
    counts = np.bincount(y_tr, minlength=n)
    need(bool(np.all(counts > 0)), 'A patient has no attacker-train beat')
    return (len(y_tr)/(n*counts)).astype('<f4')


def b_summary(seeds, preds, y_te, n, cfg, arch_name):
    adv = float(np.mean([r['Adv'] for r in seeds]))
    return {'architecture': arch_name, 'seeds': seeds, 'bacc_mean': float(np.mean([r['test_bacc'] for r in seeds])),
            'Adv_mean': adv, 'Pi': 1 - adv,
            'seed_range': {k: [min(r[k] for r in seeds), max(r[k] for r in seeds)] for k in ('test_bacc', 'Adv', 'Pi')},
            'ci95': v2.bootstrap_pi(y_te, list(preds), n, cfg['resamples'], cfg['bootstrap_seed'], cfg['block_beats']),
            'session_bacc_per_seed': [v2.session_bacc(y_te, p, n, cfg['block_beats']) for p in preds],
            'chance_bacc': 1/n, 'passes_Pi_min': 1 - adv >= cfg['Pi_min']}


def score_seeds(preds, y_te, n, cfg, extra=None):
    rows = []
    for i, seed in enumerate(cfg['B_seeds']):
        bacc, recalls = v2.balanced_accuracy(y_te, preds[i], n)
        adv = v2.advantage(bacc, n)
        rows.append({'seed': seed, 'test_bacc': bacc, 'Adv': adv, 'Pi': 1 - adv, 'per_patient_recall': recalls, **((extra or [{}]*len(preds))[i])})
    return rows


def train_b(f, y, n, cfg, device, arch_name='base'):
    """B_naive as v2 (3 seeds, class weights, early stop on attacker-validation bacc) on fixed tensors f = (tr, va, te)."""
    arch = cfg['architectures'][arch_name]
    weight = class_weight(y[0], n)
    models, states, extra = [], {}, []
    for seed in cfg['B_seeds']:
        m, info, state = v2.fit(lambda: v2.b_classifier(f[0].shape[1:], n, arch), seed,
                                {'train_x': f[0], 'train_y': y[0], 'val_x': f[1], 'val_y': y[1]}, 'B', cfg, device, n=n, weight=weight)
        models.append(m)
        states[f'B_seed{seed}'] = state
        extra.append({'best_epoch': info['best_epoch'], 'epochs_run': info['epochs_run'], 'attacker_validation_bacc': info['validation'],
                      'history': info['history']})
    preds, lps = predict_seeds(models, f[2], device)
    return b_summary(score_seeds(preds, y[2], n, cfg, extra), preds, y[2], n, cfg, arch_name), preds, lps, states, models


def s0c_refiner():
    """Part a A1 for s0c: Conv1d(1, 16, 5) + ReLU, Conv1d(16, 16, 5) + ReLU, Conv1d(16, 1, 5), padding 2, applied to x_c."""
    return nn.Sequential(nn.Conv1d(1, 16, 5, padding=2), nn.ReLU(), nn.Conv1d(16, 16, 5, padding=2), nn.ReLU(), nn.Conv1d(16, 1, 5, padding=2))


def nrmse_mean(recon, x):
    return v2.reconstruction_metrics(recon, x)['NRMSE']['mean']


# ---------- context ----------

def parts_of(split):
    return ('attacker_train', 'attacker_validation', 'test')


def split_rows(split):
    return np.concatenate([split[k] for k in parts_of(split)])


def cut_parts(a, split):
    return np.split(a, np.cumsum([len(split[k]) for k in parts_of(split)])[:-1])


class Context(SimpleNamespace):
    """model (checkpoint A), x (all trial beats), split (v2 time split), cfg, device, out (this run), v2dir (saved v2
    trial outputs), receipt (outputs_sha256 to check before loading, or None in the smoke), log."""

    def labels(self):
        y = self.split['labels']
        return tuple(y[self.split[k]] for k in parts_of(self.split))

    def views(self, src):
        """Source view of attacker-train, attacker-validation and test rows (cached)."""
        cache = self.__dict__.setdefault('_views', {})
        if src not in cache:
            cache[src] = cut_parts(view_of(self.model, self.x[split_rows(self.split)], src), self.split)
        return cache[src]

    def checked(self, name):
        path = Path(self.v2dir)/name
        if self.receipt is not None:
            rel = path.resolve().relative_to(ROOT).as_posix()
            need(self.receipt.get(rel) == sha(path), f'v2 trial output differs from receipt b2861c71: {rel}')
        return path


# ---------- part a ----------

def part_a_pair(ctx, src):
    """B_naive (3 seeds, per-beat log-probabilities saved) and A1 at s9, s10 or s0c under rho0."""
    t0 = time.time()
    cfg, n = ctx.cfg, ctx.split['n']
    raw = ctx.views(src)
    stats = fit_stats(raw[0], cfg['std_floor'])
    s_in = 's0c' if src == 's0c' else cut_of(src)
    f = [attacker_input(r, stats, s_in) for r in raw]
    y = ctx.labels()
    b, preds, lps, states, _ = train_b(f, y, n, cfg, ctx.device)
    x_parts = cut_parts(ctx.x[split_rows(ctx.split)], ctx.split)
    target = [np.ascontiguousarray(p.reshape(-1, 1, 360), dtype='<f4') for p in x_parts]
    seed = cfg['A1_seeds'][0]
    if src == 's0c':
        xc = [start_of(r, 's0c') for r in raw]
        m, info, state = v2.fit(s0c_refiner, seed, {'train_x': xc[0], 'train_y': target[0], 'val_x': xc[1], 'val_y': target[1]},
                                'A1', cfg, ctx.device)
        refined = [v2.predict(m, torch.from_numpy(a), ctx.device).reshape(len(a), 360) for a in (xc[1], xc[2])]
        floor_val, refined_val = nrmse_mean(xc[1][:, 0, :], x_parts[1]), nrmse_mean(refined[0], x_parts[1])
        headline = 'floor' if floor_val <= refined_val else 'refiner'
        recon = xc[2][:, 0, :] if headline == 'floor' else refined[1]
        a1 = {'floor': {'decoder': 'x_c (edge interpolation, training-free)', 'attacker_validation_NRMSE_mean': floor_val,
                        'metrics': v2.reconstruction_metrics(xc[2][:, 0, :], x_parts[2])},
              'refiner': {'decoder': 's0c refiner on x_c', 'seed': seed, 'best_epoch': info['best_epoch'], 'epochs_run': info['epochs_run'],
                          'attacker_validation_NRMSE_mean': refined_val, 'history': info['history'],
                          'metrics': v2.reconstruction_metrics(refined[1], x_parts[2])},
              'headline': headline, 'metrics': v2.reconstruction_metrics(recon, x_parts[2])}
    else:
        s = cut_of(src)
        m, info, state = v2.fit(lambda: v2.a1_decoder(s), seed, {'train_x': f[0], 'train_y': target[0], 'val_x': f[1], 'val_y': target[1]},
                                'A1', cfg, ctx.device)
        recon = v2.predict(m, torch.from_numpy(f[2]), ctx.device).reshape(len(f[2]), 360)
        a1 = {'decoder': f'mirror of head_s{s}', 'seed': seed, 'best_epoch': info['best_epoch'], 'epochs_run': info['epochs_run'],
              'attacker_validation_mse': info['validation'], 'history': info['history'], 'metrics': v2.reconstruction_metrics(recon, x_parts[2])}
    states['A1'] = state
    result = {'pair': f'{src}-rho0', 's': src, 'n_identities': n, 'parts': {k: int(len(ctx.split[k])) for k in parts_of(ctx.split)},
              'observed_shape': list(raw[0].shape[1:]), 'B_naive': b, 'A1': a1, 'seconds': round(time.time() - t0, 1)}
    arrays = {'test_rows': ctx.split['test'], 'test_labels': y[2], 'std_mean': stats[0], 'std_std': stats[1],
              **{f'pred_seed{sd}': p for sd, p in zip(cfg['B_seeds'], preds)}, **{f'logprob_seed{sd}': p for sd, p in zip(cfg['B_seeds'], lps)}}
    write_pair(ctx.out, f'{src}-rho0', result, arrays, states)
    ctx.log(f"part a {src}: Pi={b['Pi']:.4f} CI95=[{b['ci95']['low']:.4f}, {b['ci95']['high']:.4f}] bacc={b['bacc_mean']:.4f}")
    return result


def write_pair(output, name, result, arrays, states):
    write_json(Path(output)/f'{name}.json', result)
    np.savez(Path(output)/f'{name}-arrays.npz', **arrays)
    torch.save(states, Path(output)/f'{name}-attackers.pt')


def part_a(ctx, sources=('s9', 's10', 's0c')):
    results = {src: part_a_pair(ctx, src) for src in sources}
    pi = lambda s: results[s]['B_naive']['Pi'] if s in results else None  # noqa: E731
    reading = {}
    if 's10' in results:
        reading['Pi_logits'] = 'Pi_logits_below_Pi_min' if pi('s10') < ctx.cfg['Pi_min'] else 'Pi_logits_at_least_Pi_min'
    summary = {'Pi_naive': {s: pi(s) for s in results}, 'reading_declared_before_run': reading,
               'note': 'Pi_v3(s9) and Pi_v3(s0c) come from part b (max with B_composite); Pi_logits = Pi of B_naive at s10'}
    write_json(Path(ctx.out)/'part-a-summary.json', summary)
    return summary


# ---------- part b ----------

def naive_source(ctx, src):
    """Saved naive attackers, standardization, per-beat predictions/log-probabilities and Adv_naive of a source:
    v2 trial files for s0-s8 (checked against the receipt), part a files for s9, s10, s0c."""
    n, cfg = ctx.split['n'], ctx.cfg
    v2_name = 's0-rho0-base' if src == 's0' else f'{src}-rho0'
    from_v2 = src not in ('s9', 's10', 's0c')
    base = (lambda nm: ctx.checked(nm)) if from_v2 else (lambda nm: Path(ctx.out)/nm)
    result = read_json(base(f'{v2_name}.json'))
    arrays = np.load(base(f'{v2_name}-arrays.npz'), allow_pickle=False)
    states = torch.load(base(f'{v2_name}-attackers.pt'), map_location='cpu', weights_only=True)
    need(np.array_equal(arrays['test_rows'], ctx.split['test']), f'Saved test rows differ from the time split: {src}')
    raw = ctx.views(src)
    stats = fit_stats(raw[0], cfg['std_floor'])
    s_in = 's0c' if src == 's0c' else cut_of(src)
    f_te = attacker_input(raw[2], stats, s_in)
    models = load_b(states, f_te.shape[1:], n, cfg['architectures'][result['B_naive']['architecture']], cfg['B_seeds'], ctx.device)
    saved = np.stack([arrays[f'pred_seed{sd}'] for sd in cfg['B_seeds']])
    lps = np.stack([arrays[f'logprob_seed{sd}'] for sd in cfg['B_seeds']]) if f'logprob_seed{cfg["B_seeds"][0]}' in arrays.files else None
    return {'src': src, 's_in': s_in, 'models': models, 'stats': stats, 'preds': saved, 'logprobs': lps,
            'Adv_naive': result['B_naive']['Adv_mean'], 'from': 'v2 trial' if from_v2 else 'part a', 'f_te': f_te}


def reproduction_gate(ctx, a):
    """Predictions of the loaded attackers on the genuine test tensors must equal the saved ones element for element."""
    preds, _ = predict_seeds(a['models'], a['f_te'], ctx.device)
    need(np.array_equal(preds, a['preds']), f"Reproduction gate failed for {a['src']}: loaded attackers do not reproduce the saved predictions")
    return True


def target_of(ctx, s_to, cache):
    if s_to not in cache:
        a = naive_source(ctx, f's{s_to}')
        reproduction_gate(ctx, a)
        cache[s_to] = a
    return cache[s_to]


def part_b(ctx, sources=SOURCES_B, targets=TARGETS_B):
    """Gate every target attacker, then every (s, s') composite, then Pi_v3(s) = 1 - max(Adv_naive, Adv_composite)."""
    cfg, n = ctx.cfg, ctx.split['n']
    y_te = ctx.labels()[2]
    cache, rows, table = {}, {}, {}
    pairs = [(s, t) for s in sources for t in targets if t > cut_of(s)]
    for t in sorted({t for _, t in pairs}):
        target_of(ctx, t, cache)
    ctx.log(f'part b: reproduction gate passed for targets {sorted(cache)}')
    for src, s_to in pairs:
        tgt = cache[s_to]
        start = start_of(ctx.views(src)[2], src)
        u = composite(frozen_ops(ctx.model, cut_of(src), s_to), start, s_to)
        preds, lps = predict_seeds(tgt['models'], attacker_input(u, tgt['stats'], s_to), ctx.device)
        seeds = score_seeds(preds, y_te, n, cfg)
        name = f'{src}-to-s{s_to}'
        rows[name] = {'source': src, 'target': s_to, 'seeds': seeds, 'Adv_mean': float(np.mean([r['Adv'] for r in seeds])),
                      'bacc_mean': float(np.mean([r['test_bacc'] for r in seeds])),
                      'seed_range': {k: [min(r[k] for r in seeds), max(r[k] for r in seeds)] for k in ('test_bacc', 'Adv', 'Pi')},
                      'session_bacc_per_seed': [v2.session_bacc(y_te, p, n, cfg['block_beats']) for p in preds]}
        np.savez(Path(ctx.out)/f'composite-{name}.npz', test_rows=ctx.split['test'], test_labels=y_te,
                 **{f'pred_seed{sd}': p for sd, p in zip(cfg['B_seeds'], preds)}, **{f'logprob_seed{sd}': p for sd, p in zip(cfg['B_seeds'], lps)})
        ctx.log(f"part b {name}: Adv={rows[name]['Adv_mean']:.4f}")
    for src in sources:
        nv = naive_source(ctx, src)
        variants = {f'{src} B_naive': (nv['Adv_naive'], nv['preds'])}
        for name, r in rows.items():
            if r['source'] == src:
                d = np.load(Path(ctx.out)/f'composite-{name}.npz')
                variants[f'{name} B_composite'] = (r['Adv_mean'], np.stack([d[f'pred_seed{sd}'] for sd in cfg['B_seeds']]))
        win = max(variants, key=lambda k: variants[k][0])
        adv = variants[win][0]
        table[src] = {'Pi_v3': 1 - adv, 'winner': win, 'Adv_naive': nv['Adv_naive'], 'naive_from': nv['from'],
                      'Adv_per_variant': {k: v[0] for k, v in variants.items()}, 'passes_Pi_min': 1 - adv >= cfg['Pi_min'],
                      'ci95': v2.bootstrap_pi(y_te, list(variants[win][1]), n, cfg['resamples'], cfg['bootstrap_seed'], cfg['block_beats'])}
    reading = {}
    if 's9' in table:
        reading['Pi_s9'] = 'Pi_s9_at_least_Pi_min' if table['s9']['Pi_v3'] >= cfg['Pi_min'] else 'Pi_s9_below_Pi_min'
    result = {'composites': rows, 'Pi_v3': table, 'gate': {'targets': sorted(cache), 'element_equal': True},
              'reading_declared_before_run': reading}
    write_json(Path(ctx.out)/'part-b-result.json', result)
    return result


# ---------- k-beat vote (part d and part c) ----------

def make_blocks(y_te, n, k, mode, pair_key, draws=SCATTER_DRAWS):
    """Test positions [B, k] and owner [B]. consecutive: per patient, time order, non-overlapping, short last block
    dropped. scattered: rng = default_rng(SeedSequence([20261120, 4, pair_key, k])); patients in label order, each
    `draws` times rng.choice(n_test_of_patient, k, replace=False) (positions in draw order)."""
    y_te = np.asarray(y_te)
    pos, owner = [], []
    rng = np.random.default_rng(np.random.SeedSequence([SEED_BASE, SCATTER_TAG, int(pair_key), int(k)])) if mode == 'scattered' else None
    for p in range(n):
        idx = np.flatnonzero(y_te == p)
        need(len(idx) >= k and bool(np.all(np.diff(idx) == 1)), f'Patient {p} has fewer than k test beats or they are not contiguous')
        if mode == 'consecutive':
            nb = len(idx)//k
            pos.append(idx[:nb*k].reshape(nb, k))
        else:
            need(mode == 'scattered', f'Unknown mode {mode}')
            pos.append(np.stack([idx[rng.choice(len(idx), k, replace=False)] for _ in range(draws)]))
        owner.append(np.full(len(pos[-1]), p, dtype=np.int64))
    return np.concatenate(pos), np.concatenate(owner)


def vote_hard(preds, positions, n):
    p = preds[:, positions]  # [S, B, k]
    counts = (p[..., None] == np.arange(n)).sum(axis=2)
    return counts.argmax(axis=2)  # Ties: lowest label.


def vote_soft(lps, positions):
    out = np.empty((len(lps), len(positions)), dtype=np.int64)
    for i in range(0, len(positions), CHUNK):
        out[:, i:i+CHUNK] = lps[:, positions[i:i+CHUNK]].astype(np.float64).sum(axis=2).argmax(axis=2)
    return out


def average_views(view, positions):
    """Element-wise mean of the k dequantized observed tensors of each block: float64 accumulation, cast to float32."""
    return np.ascontiguousarray(view[positions].mean(axis=1, dtype=np.float64), dtype='<f4')


def vote_mean(mean_fn, view, positions):
    out = []
    for i in range(0, len(positions), CHUNK):
        out.append(mean_fn(average_views(view, positions[i:i+CHUNK])))
    return np.concatenate(out, axis=1)


def k_bacc(correct, owner, n):
    """Per seed: mean over patients of the fraction of the patient's blocks assigned to the right identity."""
    return np.stack([correct[:, owner == p].mean(axis=1) for p in range(n)], axis=1).mean(axis=1)


def adv_of(bacc, n):
    return np.clip((bacc - 1/n)/(1 - 1/n), 0, 1)


def ci_consecutive(correct, owner, n, resamples, seed, level=0.95):
    """Within-patient bootstrap over the k-beat blocks, identity set fixed: default_rng(seed), patients in label order,
    integers(0, n_blocks, (resamples, n_blocks)) each; Pi = 1 - mean over seeds of Adv; percentile interval."""
    rng = np.random.default_rng(seed)
    recall = np.zeros((len(correct), resamples, n))
    for p in range(n):
        b = np.flatnonzero(owner == p)
        draw = rng.integers(0, len(b), size=(resamples, len(b)))
        recall[:, :, p] = correct[:, b][:, draw].mean(axis=-1)
    pi = 1 - adv_of(recall.mean(axis=-1), n).mean(axis=0)
    low, high = np.quantile(pi, [(1 - level)/2, 1 - (1 - level)/2], method='linear')
    return {'method': 'within-patient block bootstrap', 'low': float(low), 'high': float(high), 'resamples': resamples, 'seed': seed}


def ci_scattered(correct, n, draws):
    """2.5 and 97.5 percentiles over the draws of Pi computed from draw d of every patient."""
    per_draw = correct.reshape(len(correct), n, draws).mean(axis=1)  # [S, draws]
    pi = 1 - adv_of(per_draw, n).mean(axis=0)
    low, high = np.quantile(pi, [0.025, 0.975], method='linear')
    return {'method': 'percentiles over draws', 'low': float(low), 'high': float(high), 'draws': draws}


def k_beat(attackers, view, y_te, n, cfg, pair_key, k_values=None, draws=None):
    """attackers: [{'name', 'preds' [S, N], 'logprobs' [S, N, n] or None, 'mean_fn' (averaged views -> [S, B])}].
    Every (k, mode, attacker, aggregator) value; Pi_k = 1 - max of the mean-seed Adv_k; CI95 on the winner."""
    k_values = k_values or cfg['k_values']
    draws = draws or cfg['scatter_draws']
    table = {}
    for k in k_values:
        rows, best = [], None
        for mode in ('consecutive', 'scattered'):
            positions, owner = make_blocks(y_te, n, k, mode, pair_key, draws)
            truth = owner[None, :]
            for a in attackers:
                votes = {'hard': vote_hard(a['preds'], positions, n)}
                if a['logprobs'] is not None:
                    votes['soft'] = vote_soft(a['logprobs'], positions)
                votes['mean'] = vote_mean(a['mean_fn'], view, positions)
                for agg, v in votes.items():
                    correct = v == truth
                    bacc = k_bacc(correct, owner, n)
                    adv = adv_of(bacc, n)
                    row = {'mode': mode, 'attacker': a['name'], 'aggregator': agg, 'blocks': int(len(positions)),
                           'bacc_per_seed': bacc.tolist(), 'Adv_per_seed': adv.tolist(), 'Adv_mean': float(adv.mean()),
                           'seed_range_Adv': [float(adv.min()), float(adv.max())]}
                    rows.append(row)
                    if mode == 'consecutive':
                        row['ci95'] = ci_consecutive(correct, owner, n, cfg['k_resamples'], cfg['bootstrap_seed'])
                    else:
                        row['ci95'] = ci_scattered(correct, n, draws)
                    if best is None or row['Adv_mean'] > best['Adv_mean']:
                        best = row
        table[str(k)] = {'Pi_k': 1 - best['Adv_mean'], 'winner': {x: best[x] for x in ('mode', 'attacker', 'aggregator')},
                         'ci95_winner': best['ci95'], 'rows': rows}
    return table


def naive_mean_fn(models, stats, s_in, device):
    return lambda avg: predict_seeds(models, attacker_input(avg, stats, s_in), device)[0]


def composite_mean_fn(model, src, s_to, target, device):
    ops = frozen_ops(model, cut_of(src), s_to)
    return lambda avg: predict_seeds(target['models'], attacker_input(composite(ops, start_of(avg, src), s_to), target['stats'], s_to), device)[0]


def part_d(ctx, rows=PART_D_ROWS, targets=TARGETS_B, k_values=None, draws=None, result_name='part-d-result.json'):
    """k-beat vote under rho0 from saved predictions and attackers: naive at s plus every composite s -> s'."""
    cfg, n = ctx.cfg, ctx.split['n']
    y_te = ctx.labels()[2]
    cache, out = {}, {}
    for key, src in enumerate(rows):
        nv = naive_source(ctx, src)
        reproduction_gate(ctx, nv)
        attackers = [{'name': f'{src} B_naive', 'preds': nv['preds'], 'logprobs': nv['logprobs'],
                      'mean_fn': naive_mean_fn(nv['models'], nv['stats'], nv['s_in'], ctx.device)}]
        for s_to in [t for t in targets if t > cut_of(src)] if src != 's10' else []:
            d = np.load(Path(ctx.out)/f'composite-{src}-to-s{s_to}.npz')
            attackers.append({'name': f'{src}-to-s{s_to} B_composite', 'preds': np.stack([d[f'pred_seed{sd}'] for sd in cfg['B_seeds']]),
                              'logprobs': np.stack([d[f'logprob_seed{sd}'] for sd in cfg['B_seeds']]),
                              'mean_fn': composite_mean_fn(ctx.model, src, s_to, target_of(ctx, s_to, cache), ctx.device)})
        out[src] = {'pair_key': key, 'attackers': [a['name'] for a in attackers],
                    'k': k_beat(attackers, ctx.views(src)[2], y_te, n, cfg, key, k_values, draws)}
        ctx.log(f"part d {src}: Pi_k10={out[src]['k'].get(str(cfg['k_decision']), {}).get('Pi_k')}")
    write_json(Path(ctx.out)/result_name, {'status': 'DISCUSSION_ONLY_RHO0_NOT_PI_NOT_A_DECISION_RULE', 'rows': out})
    return out


# ---------- plan, preflight, authorization ----------

def v2_outputs(receipt):
    return {k: v for k, v in receipt['outputs_sha256'].items() if '-rho0' in k and k.endswith(('.npz', '.pt', '.json'))}


def prepare(output=PLAN_DIR):
    output = ROOT/output
    need(not output.exists(), 'Plan directory exists; a new protocol version needs a new plan directory')
    p = protocol()
    require_lock()
    settings()
    v2.binding_hashes(v2.protocol())
    rb = p['source_bindings']['attack_v2_trial_receipt']
    need(sha(ROOT/rb['path']) == rb['sha256'], 'v2 trial receipt differs')
    table = v2.checkpoint_table(v2.protocol())
    _, _, plan_v4, _ = pkg.locked()
    s0c = p['source_bindings']['s0c_definition']
    plan = {'schema': 'm1-attack-plan/3', 'status': 'CANDIDATE_NOT_AUTHORIZED', 'protocol_sha256': PROTOCOL_SHA, 'protocol_lock_sha256': LOCK_SHA,
            'checkpoint_lock_sha256': pkg.LOCK_SHA, 'rho0': table['rho0'], 'arrays': pkg.ARRAYS, 'data_files': plan_v4['binding']['data_files'],
            'v2_trial_receipt_sha256': rb['sha256'], 'v2_trial_outputs_sha256': v2_outputs(read_json(ROOT/rb['path'])),
            's0c_v1': {k: s0c[k]['sha256'] for k in ('reference', 'golden_npz', 'golden_json')},
            'sources_sha256': {nm: sha(ROOT/nm) for nm in SOURCES},
            'part_d_pair_keys': {src: i for i, src in enumerate(PART_D_ROWS)},
            'part_c_pair_key_offset': len(PART_D_ROWS), 'DS2_access': False}
    output.mkdir(parents=True)
    write_json(output/'plan-manifest.json', plan)
    return sha(output/'plan-manifest.json')


def preflight(plan_path):
    """Bindings, sources, v2 trial outputs and the DS1 split counts from metadata only. No array, no model, no fit, no DS2."""
    plan = read_json(plan_path)
    require_lock()
    need(plan['protocol_sha256'] == PROTOCOL_SHA and plan['protocol_lock_sha256'] == LOCK_SHA and plan['DS2_access'] is False, 'Plan binding differs')
    need(sorted(plan['sources_sha256']) == sorted(SOURCES) and all(sha(ROOT/nm) == h for nm, h in plan['sources_sha256'].items()), 'Source differs from plan')
    settings()
    v2.binding_hashes(v2.protocol())
    need(plan['rho0'] == v2.checkpoint_table(v2.protocol())['rho0'] and sha(ROOT/plan['rho0']['path']) == plan['rho0']['sha256'], 'Checkpoint A differs')
    for rel, h in plan['v2_trial_outputs_sha256'].items():
        need(sha(ROOT/rel) == h, f'v2 trial output differs: {rel}')
    for name, expected in plan['data_files'].items():
        need(not name.startswith('test') and sha(ROOT/plan['arrays']/name) == expected['sha256'], f'Array differs: {name}')
    rows = v2.read_metadata(ROOT/plan['arrays'])
    rule = v2.protocol()['data']['trial_week11']
    counts = v2.split_counts(v2.time_split(rows, rule), len(rows))
    need(counts == rule['counts'], f'DS1 time-split counts differ from the protocol: {counts}')
    return {'status': 'PASS_PREFLIGHT_METADATA_ONLY_NO_ARRAY_NO_MODEL_NO_FIT_NO_DS2', 'counts': counts,
            'v2_outputs_checked': len(plan['v2_trial_outputs_sha256'])}


def require_authorization(path, plan_path, part):
    """The run authorization the user provides: binds protocol, lock, plan and SV1 evidence, names the parts, no DS2."""
    need(path is not None and Path(path).is_file(), 'External run authorization required')
    a = read_json(path)
    need(a.get('type') == AUTH_TYPE and a.get('protocol_sha256') == PROTOCOL_SHA and a.get('protocol_lock_sha256') == LOCK_SHA
         and a.get('plan_manifest_sha256') == sha(plan_path) and part in a.get('allow_parts', []) and a.get('allow_DS2') is False
         and bool(a.get('approved_by')), 'Authorization does not bind the protocol, lock and plan, or does not allow this part')
    ev = a.get('review_evidence_path')
    need(isinstance(ev, str) and (ROOT/ev).is_file() and sha(ROOT/ev) == a.get('review_evidence'), 'Authorization review evidence differs')
    return a


def load_trial(plan_path):
    """DS1 train/val arrays (checked against the plan), the v2 time split and checkpoint A, with the golden checks."""
    plan = read_json(plan_path)
    _, _, plan_v4, _ = pkg.locked()
    data = pkg.arrays(plan_v4)
    x = np.ascontiguousarray(np.concatenate([data['train'][0], data['val'][0]]), dtype='<f4')
    rows = data['train'][2] + data['val'][2]
    split = v2.time_split(rows, v2.protocol()['data']['trial_week11'])
    rho0 = v2.load_rho(plan['rho0'])
    return x, split, rho0, data


def run(parts, plan_path, output, authorization, device='auto'):
    """Parts a, b, d in that order (each named by the authorization), into one new directory under ml/data/runs."""
    for part in parts:
        auth = require_authorization(authorization, plan_path, part)  # Before any data, model or output.
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and (not output.exists() or parts[0] != 'a'), 'Output must be under ignored ml/data; part a needs a new path')
    pf = preflight(plan_path)
    cfg = settings()
    precision = v2.set_precision()
    configure()
    dev = v2.device_of(device)
    x, split, rho0, _ = load_trial(plan_path)
    need(v2.split_counts(split, len(x)) == pf['counts'], 'Split counts differ from preflight')
    package = ROOT/v2.protocol()['source_bindings']['package_A']['path']
    output.mkdir(parents=True, exist_ok=True)
    identity = {'authorization_sha256': sha(authorization), 'plan_manifest_sha256': sha(plan_path), 'protocol_sha256': PROTOCOL_SHA,
                **v2.environment(dev, precision), 'parts': parts, 'DS2_opened': False}
    if 'a' in parts:
        ref = s0c_reference()
        identity['golden_check_s9_s10'] = v2.golden_check(rho0, package, [9, 10])
        identity['s0c_golden_check'] = s0c_golden_check(ref, package)
        identity['s0c_reference_check_trial_beats'] = s0c_reference_check(x, ref)
    write_json(output/f"run-identity-{''.join(parts)}.json", identity)
    receipt = read_json(ROOT/protocol()['source_bindings']['attack_v2_trial_receipt']['path'])['outputs_sha256']
    ctx = Context(model=rho0, x=x, split=split, cfg=cfg, device=dev, out=output, v2dir=ROOT/V2_RUNS, receipt=receipt,
                  log=lambda m: print(m, flush=True))
    result = {}
    if 'a' in parts:
        result['a'] = part_a(ctx)
    if 'b' in parts:
        result['b'] = {s: r['Pi_v3'] for s, r in part_b(ctx)['Pi_v3'].items()}
    if 'd' in parts:
        result['d'] = {s: r['k'][str(cfg['k_decision'])]['Pi_k'] for s, r in part_d(ctx).items()}
    write_json(output/f"run-result-{''.join(parts)}.json", {'status': 'COMPLETED_REPORT_ONLY', 'approved_by': auth['approved_by'], **result,
                                                            'DS2_opened': False})
    return result


# ---------- smoke (synthetic beats, checkpoint A; no MITDB file, no v2 trial output) ----------

def smoke_naive(ctx, src):
    """Stand-in for a v2 trial pair in the smoke: B_naive at s0/s2 written in the v2 file format into the smoke directory."""
    raw = ctx.views(src)
    stats = fit_stats(raw[0], ctx.cfg['std_floor'])
    f = [attacker_input(r, stats, cut_of(src)) for r in raw]
    b, preds, _, states, _ = train_b(f, ctx.labels(), ctx.split['n'], ctx.cfg, ctx.device)
    name = 's0-rho0-base' if src == 's0' else f'{src}-rho0'
    write_pair(ctx.v2dir, name, {'B_naive': b}, {'test_rows': ctx.split['test'], **{f'pred_seed{sd}': p for sd, p in zip(ctx.cfg['B_seeds'], preds)}},
               states)


def smoke(output, device='auto', epochs=3):
    """Synthetic beats (8 records x 400), checkpoint A, parts a, b, d on reduced source/target sets and k values; the
    S0c golden and reference checks; a rerun of one composite and one k-beat table must be identical."""
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Smoke output must be a new path under ignored ml/data')
    cfg = {**settings(), 'max_epochs': epochs, 'resamples': 200, 'k_resamples': 200}
    precision = v2.set_precision()
    configure()
    dev = v2.device_of(device)
    rows, x = v2.synthetic_beats(np.random.default_rng(12345), [101, 106, 108, 109, 112, 114, 115, 116], 400)
    split = v2.time_split(rows, v2.protocol()['data']['trial_week11'])
    rho0 = v2.load_rho(v2.checkpoint_table(v2.protocol())['rho0'])
    ref = s0c_reference()
    package = ROOT/v2.protocol()['source_bindings']['package_A']['path']
    checks = {'s0c_golden': s0c_golden_check(ref, package), 's0c_reference_synthetic': s0c_reference_check(x, ref)}
    output.mkdir(parents=True)
    (output/'v2-stand-in').mkdir()
    ctx = Context(model=rho0, x=x, split=split, cfg=cfg, device=dev, out=output, v2dir=output/'v2-stand-in', receipt=None, log=print)
    for src in ('s0', 's2'):
        smoke_naive(ctx, src)
    a = part_a(ctx)
    b = part_b(ctx, sources=['s0', 's0c', 's2', 's9'], targets=[2, 9, 10])
    d = part_d(ctx, rows=['s0c', 's2', 's10'], targets=[2, 9, 10], k_values=[1, 5, 10], draws=20)
    first = np.load(output/'composite-s0c-to-s9.npz')
    u = composite(frozen_ops(rho0, 0, 9), start_of(ctx.views('s0c')[2], 's0c'), 9)
    tgt = naive_source(ctx, 's9')
    again, _ = predict_seeds(tgt['models'], attacker_input(u, tgt['stats'], 9), dev)
    same_b = bool(np.array_equal(again, np.stack([first[f'pred_seed{sd}'] for sd in cfg['B_seeds']])))
    d2 = part_d(ctx, rows=['s0c'], targets=[2, 9, 10], k_values=[5], draws=20, result_name='part-d-rerun.json')
    same_d = json.dumps(d2['s0c']['k']['5'], sort_keys=True) == json.dumps(d['s0c']['k']['5'], sort_keys=True)
    need(same_b and same_d, 'Smoke determinism check failed')
    result = {'status': 'SMOKE_PASS_RANDOM_DATA_NOT_MITDB', 'epochs': epochs, **v2.environment(dev, precision), **checks,
              'counts': v2.split_counts(split, len(rows)), 'part_a': a, 'part_b_Pi_v3': {s: r['Pi_v3'] for s, r in b['Pi_v3'].items()},
              'part_d_Pi_k10': {s: r['k']['10']['Pi_k'] for s, r in d.items()}, 'composite_rerun_identical': same_b,
              'k_beat_rerun_identical': same_d}
    write_json(output/'smoke-result.json', result)
    return result


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('mode', choices=['prepare', 'preflight', 'smoke', 'run'])
    a.add_argument('--parts', default='abd')
    a.add_argument('--plan', type=Path, default=Path(PLAN_DIR)/'plan-manifest.json')
    a.add_argument('--output', type=Path)
    a.add_argument('--authorization', type=Path)
    a.add_argument('--device', default='auto')
    a.add_argument('--epochs', type=int, default=3)
    args = a.parse_args()
    if args.mode == 'prepare':
        print('PLAN', prepare())
    elif args.mode == 'preflight':
        print(json.dumps(preflight(ROOT/args.plan), indent=2))
    elif args.mode == 'smoke':
        print(json.dumps(smoke(args.output, args.device, args.epochs), indent=2))
    else:
        print(json.dumps(run(list(args.parts), ROOT/args.plan, args.output, args.authorization, args.device), indent=2))


if __name__ == '__main__':
    main()
