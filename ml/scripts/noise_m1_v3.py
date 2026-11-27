"""Part c of attack protocol v3 revision 5 (locked): R2 (z_s2 of checkpoint A plus Gaussian noise) and the C0c
control (S0c reduced values plus Gaussian noise), on DS1 only.

Order (run_order_after_lock): sigma file, then the matched-utility search on DS1 validation (with C0c payload sizes),
then the run manifest (alpha_t, pair keys, noise plan) written before the first fit, then the privacy points (Pi,
Pi_k10, reconstruction). Checkpoint A stays frozen. No run starts without the external run authorization (part 'c');
DS2 is never opened (its part_index 4-7 are declared here for the official round, never used by this script).
`smoke` uses synthetic beats and checkpoint A; `timing` measures the fresh-noise plan on random arrays of the real
sizes (no MITDB) for the fallback decision of noise_generator.fallback.
"""
from __future__ import annotations

import attack_m1_v3 as v3  # noqa: I001  (imports attack_m1_v2 first: CUBLAS_WORKSPACE_CONFIG before torch)

import argparse  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402
from fractions import Fraction  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch.nn import functional as F  # noqa: E402

import nopeek_m1_v2 as nopeek  # noqa: E402
from quantization import FP16_MAX, FP16_MIN_NORMAL  # noqa: E402
from week3_common import need, read_json, sha, write_json  # noqa: E402
from week3_sv2_common import configure  # noqa: E402

v2 = v3.v2
ROOT = v3.ROOT
CONFIG_INDEX = {'R2': 0, 'C0c': 2}  # 1 is not used.
SOURCE = {'R2': 's2', 'C0c': 's0c'}
PART_INDEX = {'attacker_train': 0, 'attacker_validation': 1, 'test': 2, 'utility': 3}
PART_INDEX_DS2 = {'utility': 4, 'attacker_validation': 5, 'test': 6, 'attacker_train': 7}  # Official DS2 round only.
UTILITY_DRAWS = (0, 1, 2)
GRID = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0)
TARGETS = (Fraction(99, 100), Fraction(98, 100), Fraction(97, 100), Fraction(95, 100))
BISECTION_STEPS = 8
F1_A = Fraction(11488986689, 20219195700)
GATE = Fraction(19, 20)*F1_A
COMPOSITE_TARGETS = {'R2': [4, 5, 8, 9, 10], 'C0c': [2, 4, 5, 8, 9, 10]}
GPU_CHUNK = 4096


# ---------- noise ----------

def alpha_key(alpha):
    return int(round(alpha*1e6))


def on_key(alpha):
    """Every alpha used is first put on the 1e-6 grid of alpha_key, so the key and the noise scale always agree."""
    return alpha_key(alpha)/1e6


def noise(shape, config, alpha, part, draw, sigma, ds2=False):
    """e = float32(standard_normal(shape) * (alpha * sigma)), standard normals drawn in float64 in row-major order of
    `shape` (rows in the fixed order of the part) by default_rng(SeedSequence([20261120, config_index, alpha_key,
    part_index, draw])). sigma: per channel [1, C, 1] (R2) or a scalar (C0c)."""
    index = (PART_INDEX_DS2 if ds2 else PART_INDEX)[part]
    need(not ds2, 'DS2 noise streams belong to the official DS2 round and need its own authorization')
    rng = np.random.default_rng(np.random.SeedSequence([v3.SEED_BASE, CONFIG_INDEX[config], alpha_key(alpha), index, int(draw)]))
    return (rng.standard_normal(size=shape)*(alpha*np.asarray(sigma, dtype=np.float64))).astype('<f4')


class Mechanism:
    """Clean device-side values of the rows and the noisy observed view the edge holds."""

    def __init__(self, config, model, sigma):
        self.config, self.model, self.sigma = config, model, sigma

    def clean(self, x):
        """R2: FP32 z_s2 of checkpoint A [N, 16, 180]; C0c: the 46 reduced values [N, 46]."""
        return v2.head_output(self.model, x, 2) if self.config == 'R2' else v3.reduce46(x)

    def transmit(self, clean, alpha, part, draw):
        """Noisy device values -> registry v2 quantization -> what the edge dequantizes: {'view', 'q'}."""
        noisy = (clean + noise(clean.shape, self.config, alpha, part, draw, self.sigma)).astype('<f4')
        if self.config == 'R2':
            q, scale = v3.quantize_per_channel(noisy)
            return {'view': v3.dequantize_per_channel(q, scale), 'q': q}
        t = v3.s0c_transmit(noisy)
        return {'view': t['deq'][:, None, :], 'q': t['q']}

    def view(self, clean, alpha, part, draw):
        return self.transmit(clean, alpha, part, draw)['view']


def sigma_values(model, x_train):
    """sigma_c: population std over N and L of channel c of the clean z_s2 on DS1 train; sigma_v: population std over
    N and the 46 positions of the clean reduced values on DS1 train (float64)."""
    z = v2.head_output(model, x_train, 2)
    v = v3.reduce46(x_train)
    return {'R2': z.std(axis=(0, 2), dtype=np.float64).reshape(1, -1, 1), 'C0c': float(v.std(dtype=np.float64))}


def write_sigma(output, sig, rows):
    path = Path(output)/'sigma.json'
    write_json(path, {'sigma_c_R2': sig['R2'].reshape(-1).tolist(), 'sigma_v_C0c': sig['C0c'], 'DS1_train_beats': int(rows),
                      'definition': 'population std (ddof 0), float64; written before any noisy evaluation'})
    return sha(path)


def read_sigma(path):
    d = read_json(path)
    return {'R2': np.asarray(d['sigma_c_R2'], dtype=np.float64).reshape(1, -1, 1), 'C0c': float(d['sigma_v_C0c'])}


# ---------- utility (DS1 validation) and matched-utility search ----------

def logits_of(mech, view, batch=1024):
    """The edge: R2 runs the frozen tail from s2; C0c interpolates and runs the whole frozen model. CPU, batched."""
    cut = v3.cut_of(SOURCE[mech.config])
    start = v3.start_of(view, SOURCE[mech.config])
    ops = v3.frozen_ops(mech.model, cut, 10)
    out = []
    with torch.no_grad():
        for i in range(0, len(start), batch):
            out.append(ops(torch.from_numpy(np.ascontiguousarray(start[i:i+batch]))).numpy())
    return np.concatenate(out)


def confusion5(y, pred):
    return np.bincount(5*np.asarray(y, dtype=np.int64) + np.asarray(pred, dtype=np.int64), minlength=25).reshape(5, 5)


class Utility:
    """Macro-F1 (fixed4, exact Fraction) from the confusion summed over draws 0, 1, 2 of part_index 3; cached per alpha."""

    def __init__(self, mech, x_val, y_val, ref=None):
        self.mech, self.y, self.cache = mech, y_val, {}
        self.clean = mech.clean(x_val)
        self.ref = ref  # S0c reference for the C0c payload sizes (None: sizes not computed).

    def __call__(self, alpha):
        alpha = on_key(alpha)
        if alpha not in self.cache:
            total, draws, sizes = np.zeros((5, 5), dtype=np.int64), [], []
            for d in UTILITY_DRAWS:
                sent = self.mech.transmit(self.clean, alpha, 'utility', d)
                view = sent['view']
                pred = logits_of(self.mech, view).argmax(1)
                c = confusion5(self.y, pred)
                total += c
                draws.append({'draw': d, 'macro_f1': float(nopeek.macro_f1_exact(c.tolist())), 'accuracy': float(np.trace(c)/c.sum())})
                if self.mech.config == 'C0c' and self.ref is not None:
                    sizes += [len(self.ref.rice_encode(r)) for r in sent['q']]
            f1 = nopeek.macro_f1_exact(total.tolist())
            row = {'alpha': alpha, 'alpha_key': alpha_key(alpha), 'macro_f1': f1, 'macro_f1_float': float(f1), 'per_draw': draws,
                   'confusion_sum': total.tolist()}
            if sizes:
                row['rice_body_bytes'] = {'mean': float(np.mean(sizes)), 'median': float(np.median(sizes)), 'max': int(np.max(sizes)),
                                          'beats': len(sizes), 'note': 'Rice body only; the FP16 scale adds 2 B'}
            self.cache[alpha] = row
        return self.cache[alpha]['macro_f1']


def search(f, target):
    """matched_utility_search.rule: grid first; bisection in log(alpha) for 8 steps between the last grid alpha that
    passes before the first failing one (first crossing from small alpha) and that failing alpha; downward to
    0.05/2^8 if 0.05 fails; alpha_t = largest alpha found that passes."""
    passes = [f(a) >= target for a in GRID]
    note = None
    if all(passes):
        return {'alpha_t': GRID[-1], 'reachable': True, 'note': 'largest grid alpha passes; not extended beyond the grid', 'non_monotone': []}
    first = passes.index(False)
    non_monotone = [GRID[i] for i in range(first + 1, len(GRID)) if passes[i]]
    if first == 0:
        lo = None
        for i in range(1, BISECTION_STEPS + 1):
            a = on_key(GRID[0]/2**i)
            if f(a) >= target:
                lo, hi = a, on_key(GRID[0]/2**(i - 1))
                break
        if lo is None:
            return {'alpha_t': None, 'reachable': False, 'note': 'no alpha down to 0.05/2^8 reaches the target', 'non_monotone': non_monotone}
        note = 'grid 0.05 fails; searched downward'
    else:
        lo, hi = GRID[first - 1], GRID[first]
    for _ in range(BISECTION_STEPS):
        mid = on_key(math.exp((math.log(lo) + math.log(hi))/2))
        if mid in (lo, hi):
            break
        if f(mid) >= target:
            lo = mid
        else:
            hi = mid
    return {'alpha_t': lo, 'reachable': True, 'bracket_end': hi, 'note': note, 'non_monotone': non_monotone}


def matched_utility(mech, x_val, y_val, ref=None):
    u = Utility(mech, x_val, y_val, ref)
    for a in GRID:
        u(a)
    out = {}
    for t in TARGETS:
        target = t*F1_A
        r = search(u, target)
        out[str(t)] = {'target_fraction_of_F1_A': str(t), 'target_exact': str(target), 'target_float': float(target), **r}
    evaluated = [{**row, 'macro_f1': str(row['macro_f1'])} for _, row in sorted(u.cache.items())]
    return {'config': mech.config, 'targets': out, 'evaluated': evaluated, 'gate_exact': str(GATE)}


# ---------- GPU composites for training (CPU is used for validation and test) ----------

def quant_dequant_torch(z):
    """Registry v2 rule in torch (z [N, C, L] float32): fp16 scale of max|z|/127 (smallest normal floor, 1 for zeros)."""
    maxima = z.abs().amax(dim=2)
    raw = maxima/torch.tensor(127., dtype=torch.float32, device=z.device)
    need(bool((raw <= float(FP16_MAX)).all()), 'Scale exceeds finite FP16 range')
    scale = torch.where(maxima == 0, torch.ones_like(raw), torch.clamp(raw, min=float(FP16_MIN_NORMAL))).half().float()
    return torch.clamp(torch.round(z/scale[..., None]), -127, 127)*scale[..., None]


class GpuPath:
    """Noisy source view (numpy) -> u_s' on the device, chunked: s0c interpolation, frozen ops, re-quantization."""

    def __init__(self, model, src, targets, device):
        self.src, self.device = src, device
        self.ops = {t: copy.deepcopy(v3.frozen_ops(model, v3.cut_of(src), t)).to(device).eval() for t in targets}
        self.i0, self.i1 = torch.from_numpy(v3.I0).to(device), torch.from_numpy(v3.I1).to(device)
        self.w, self.omw = torch.from_numpy(v3.W).to(device), torch.from_numpy(v3.ONE_MINUS_W).to(device)

    def start(self, view):
        v = torch.from_numpy(np.ascontiguousarray(view)).to(self.device)
        if self.src == 's0c':
            v = v[:, 0, :]
            return (self.omw*v[:, self.i0] + self.w*v[:, self.i1])[:, None, :]
        return v

    def __call__(self, view, t):
        out = []
        with torch.no_grad():
            for i in range(0, len(view), GPU_CHUNK):
                z = self.ops[t](self.start(view[i:i+GPU_CHUNK]))
                out.append(quant_dequant_torch(z if z.dim() == 3 else z[..., None]))
        return torch.cat(out)


def gpu_cpu_check(gpu, model, view, t, rows=256):
    """Epoch 1 diagnostic (report only): max |GPU - CPU| of u_s' on one batch and the fraction of values that differ."""
    g = gpu(view[:rows], t).cpu().numpy()
    c = v3.composite(v3.frozen_ops(model, v3.cut_of(gpu.src), t), v3.start_of(view[:rows], gpu.src), t)
    return {'target': t, 'rows': int(min(rows, len(view))), 'max_abs_diff': float(np.max(np.abs(g - c))),
            'fraction_quantized_values_differ': float(np.mean(g != c))}


# ---------- lockstep training (identical per model to v2.fit; the epoch's noise is drawn once for all models) ----------

class Member:
    def __init__(self, name, key, kind, seed, factory, cfg, device, train_y, val_x, val_y, n=None, weight=None):
        v2.seed_all(seed)
        self.name, self.key, self.kind, self.seed, self.n = name, key, kind, seed, n
        self.model = factory().to(device)
        self.opt = torch.optim.AdamW(self.model.parameters(), lr=cfg['lr'], betas=cfg['betas'], eps=cfg['eps'], weight_decay=cfg['weight_decay'])
        self.ty = torch.from_numpy(train_y).to(device)
        self.vx, self.vy = torch.from_numpy(val_x), val_y
        self.w = None if weight is None else torch.from_numpy(weight).to(device)
        self.best, self.history, self.stopped = None, [], False

    def epoch(self, epoch, tx, cfg, device):
        perm = torch.randperm(len(tx), generator=torch.Generator().manual_seed(self.seed + epoch - 1)).to(device)
        self.model.train()
        total = 0.
        for i in range(0, len(tx), cfg['batch_size']):
            idx = perm[i:i+cfg['batch_size']]
            self.opt.zero_grad(set_to_none=True)
            out = self.model(tx[idx])
            loss = F.cross_entropy(out, self.ty[idx], weight=self.w) if self.kind == 'B' else F.mse_loss(out, self.ty[idx])
            need(bool(torch.isfinite(loss)), 'Non-finite attack loss')
            loss.backward()
            self.opt.step()
            total += float(loss.detach())*len(idx)
        self.model.eval()
        out = v2.predict(self.model, self.vx, device)
        metric = (v2.balanced_accuracy(self.vy, out.argmax(1), self.n)[0] if self.kind == 'B'
                  else float(np.mean((out - self.vy)**2, dtype=np.float64)))
        self.history.append({'epoch': epoch, 'train_loss': total/len(tx), 'validation': metric})
        if v2.improves(self.kind, metric, self.best):
            self.best = {'epoch': epoch, 'validation': metric, 'state': {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()}}
        elif v2.stops(epoch, self.best['epoch'], cfg['patience']):
            self.stopped = True

    def finish(self):
        self.model.load_state_dict(self.best['state'])
        self.model.eval()
        return {'best_epoch': self.best['epoch'], 'validation': self.best['validation'], 'epochs_run': len(self.history),
                'history': self.history}, self.best['state']


def lockstep(members, inputs, cfg, device, log=None):
    """Each epoch: inputs(epoch, keys) -> {key: train tensor on device}, then one epoch of every active member."""
    for epoch in range(1, cfg['max_epochs'] + 1):
        active = [m for m in members if not m.stopped]
        if not active:
            break
        tensors = inputs(epoch, sorted({m.key for m in active}))
        for m in active:
            m.epoch(epoch, tensors[m.key], cfg, device)
        if log:
            log(f'epoch {epoch}: {len(active)} active')
    return {m.name: m.finish() for m in members}


# ---------- one privacy point ----------

class Point:
    """Everything the variants of one (configuration, alpha_t) need: fixed draw-0 views, the fresh-noise provider."""

    def __init__(self, ctx, mech, alpha, targets, noise_plan):
        self.ctx, self.mech, self.alpha, self.targets = ctx, mech, on_key(alpha), targets
        self.src = SOURCE[mech.config]
        rows = [ctx.split[k] for k in v3.parts_of(ctx.split)]
        self.clean = [mech.clean(ctx.x[r]) for r in rows]
        self.val = mech.view(self.clean[1], self.alpha, 'attacker_validation', 0)
        self.test = mech.view(self.clean[2], self.alpha, 'test', 0)
        self.plan = noise_plan  # {'kind': 'fresh'} or {'kind': 'fallback', 'R': R}
        self.gpu = GpuPath(ctx.model, self.src, targets, ctx.device)
        self.stats, self.gpu_cpu = {}, []
        self._cache = {}

    def train_view(self, epoch):
        """Fresh: SeedSequence(..., 0, epoch). Fallback: realization (epoch - 1) mod R, drawn with key ((epoch - 1) mod R) + 1."""
        key = epoch if self.plan['kind'] == 'fresh' or epoch == 0 else (epoch - 1) % self.plan['R'] + 1
        if key not in self._cache:
            if self.plan['kind'] == 'fresh':
                self._cache.clear()
            self._cache[key] = self.mech.view(self.clean[0], self.alpha, 'attacker_train', key)
        return self._cache[key]

    def inputs(self, epoch, keys):
        view = self.train_view(epoch)
        out = {}
        for key in keys:
            if key == 'source':
                if 'source' not in self.stats:
                    self.stats['source'] = v3.fit_stats(view, self.ctx.cfg['std_floor'])
                out[key] = torch.from_numpy(v3.attacker_input(view, self.stats['source'], self.s_in)).to(self.ctx.device)
            elif key == 'xc':
                out[key] = torch.from_numpy(v3.start_of(view, 's0c')).to(self.ctx.device)
            else:
                t = int(key[1:])
                u = self.gpu(view, t)
                if key not in self.stats:  # Epoch 1 realization of its own attacker-train part.
                    self.stats[key] = v3.fit_stats(u.cpu().numpy(), self.ctx.cfg['std_floor'])
                    self.gpu_cpu.append(gpu_cpu_check(self.gpu, self.ctx.model, view, t))
                mean, std = (torch.from_numpy(a).to(self.ctx.device) for a in self.stats[key])
                f = ((u.double() - mean)/std).float()
                out[key] = f[..., 0].contiguous() if t >= 9 else f
        return out

    @property
    def s_in(self):
        return 's0c' if self.src == 's0c' else 2

    def eval_input(self, key, part_view):
        """Validation/test tensors of a key from a fixed noisy view, CPU composites (part b computation)."""
        if key == 'source':
            return v3.attacker_input(part_view, self.stats['source'], self.s_in)
        if key == 'xc':
            return v3.start_of(part_view, 's0c')
        t = int(key[1:])
        u = v3.composite(v3.frozen_ops(self.ctx.model, v3.cut_of(self.src), t), v3.start_of(part_view, self.src), t)
        return v3.attacker_input(u, self.stats[key], t)


def run_point(ctx, mech, alpha, targets, noise_plan, out, pair_key, clean_attackers, k_values=None, draws=None):
    """B_naive, B_adaptive, B_composite_adaptive (every s' in targets), A1_adaptive; Pi, Pi_k10 (all k), reconstruction."""
    t0 = time.time()
    cfg, n = ctx.cfg, ctx.split['n']
    pt = Point(ctx, mech, alpha, targets, noise_plan)
    y_tr, y_va, y_te = ctx.labels()
    weight = v3.class_weight(y_tr, n)
    arch = cfg['architectures']['base']
    name = f"{mech.config}-alpha{alpha_key(pt.alpha)}"
    # B_naive: one realization (draw 0 of part_index 0), fixed tensors, v2.fit.
    v0 = pt.train_view(0)
    st0 = v3.fit_stats(v0, cfg['std_floor'])
    f_naive = [v3.attacker_input(a, st0, pt.s_in) for a in (v0, pt.val, pt.test)]
    b_naive, p_naive, lp_naive, states, m_naive = v3.train_b(f_naive, (y_tr, y_va, y_te), n, cfg, ctx.device)
    # Epoch 1 sets the standardization of every adaptive key before validation tensors are built.
    keys = ['source', *[f's{t}' for t in targets]] + (['xc'] if mech.config == 'C0c' else [])
    pt.inputs(1, keys)
    val_in = {k: pt.eval_input(k, pt.val) for k in keys}
    x_parts = v3.cut_parts(ctx.x[v3.split_rows(ctx.split)], ctx.split)
    clean_x = [np.ascontiguousarray(p.reshape(-1, 1, 360), dtype='<f4') for p in x_parts]
    members = []
    for seed in cfg['B_seeds']:
        members.append(Member(f'B_adaptive seed{seed}', 'source', 'B', seed, lambda: v2.b_classifier(val_in['source'].shape[1:], n, arch),
                              cfg, ctx.device, y_tr, val_in['source'], y_va, n, weight))
        for t in targets:
            members.append(Member(f'B_composite_adaptive s{t} seed{seed}', f's{t}', 'B', seed,
                                  lambda t=t: v2.b_classifier(val_in[f's{t}'].shape[1:], n, arch), cfg, ctx.device, y_tr, val_in[f's{t}'], y_va, n, weight))
    a1_key = 'xc' if mech.config == 'C0c' else 'source'
    a1_factory = v3.s0c_refiner if mech.config == 'C0c' else (lambda: v2.a1_decoder(2))
    members.append(Member('A1_adaptive', a1_key, 'A1', cfg['A1_seeds'][0], a1_factory, cfg, ctx.device, clean_x[0], val_in[a1_key], clean_x[1]))
    trained = lockstep(members, pt.inputs, cfg, ctx.device)
    test_in = {k: pt.eval_input(k, pt.test) for k in keys}
    variants = {'B_naive': {'models': m_naive, 'preds': p_naive, 'logprobs': lp_naive, 'stats': st0, 'kind': 'source'}}
    report = {'B_naive': b_naive}
    by_name = {m.name: m for m in members}
    for var, key in [('B_adaptive', 'source'), *[(f'B_composite_adaptive s{t}', f's{t}') for t in targets]]:
        models = [by_name[f'{var} seed{sd}'].model for sd in cfg['B_seeds']]
        preds, lps = v3.predict_seeds(models, test_in[key], ctx.device)
        extra = [{k: trained[f'{var} seed{sd}'][0][k] for k in ('best_epoch', 'epochs_run', 'history')} for sd in cfg['B_seeds']]
        report[var] = v3.b_summary(v3.score_seeds(preds, y_te, n, cfg, extra), preds, y_te, n, cfg, 'base')
        variants[var] = {'models': models, 'preds': preds, 'logprobs': lps, 'stats': pt.stats[key], 'kind': key}
        for sd in cfg['B_seeds']:
            states[f'{var} seed{sd}'] = trained[f'{var} seed{sd}'][1]
    win = max(report, key=lambda k: report[k]['Adv_mean'])
    pi = 1 - report[win]['Adv_mean']
    ci = v2.bootstrap_pi(y_te, list(variants[win]['preds']), n, cfg['resamples'], cfg['bootstrap_seed'], cfg['block_beats'])
    # Reconstruction: floor (C0c only) and A1_adaptive; headline by attacker-validation NRMSE.
    a1_model = by_name['A1_adaptive'].model
    recon_val = v2.predict(a1_model, torch.from_numpy(val_in[a1_key]), ctx.device).reshape(-1, 360)
    recon_te = v2.predict(a1_model, torch.from_numpy(test_in[a1_key]), ctx.device).reshape(-1, 360)
    states['A1_adaptive'] = trained['A1_adaptive'][1]
    recon = {'A1_adaptive': {'attacker_validation_NRMSE_mean': v3.nrmse_mean(recon_val, x_parts[1]),
                             **{k: trained['A1_adaptive'][0][k] for k in ('best_epoch', 'epochs_run')},
                             'metrics': v2.reconstruction_metrics(recon_te, x_parts[2])}}
    if mech.config == 'C0c':
        recon['floor'] = {'attacker_validation_NRMSE_mean': v3.nrmse_mean(val_in['xc'][:, 0, :], x_parts[1]),
                          'metrics': v2.reconstruction_metrics(test_in['xc'][:, 0, :], x_parts[2])}
    recon['headline'] = min((k for k in recon), key=lambda k: recon[k]['attacker_validation_NRMSE_mean'])
    # k-beat: every trained variant plus the clean rho0 attackers of the same source and at every s'.
    attackers = []
    for var, v in variants.items():
        attackers.append({'name': f'{var} (noisy-trained)', 'preds': v['preds'], 'logprobs': v['logprobs'],
                          'mean_fn': mean_fn(ctx, pt, v['models'], v['stats'], v['kind'])})
    for label, a in clean_attackers.items():
        if label == 'source' or int(label[1:]) in targets:
            kind = 'source' if label == 'source' else label
            f = eval_with(ctx, pt, kind, pt.test, a['stats'])
            preds, lps = v3.predict_seeds(a['models'], f, ctx.device)
            attackers.append({'name': f'clean rho0 attacker {"at source" if label == "source" else "at " + label}', 'preds': preds, 'logprobs': lps,
                              'mean_fn': mean_fn(ctx, pt, a['models'], a['stats'], kind)})
    kb = v3.k_beat(attackers, pt.test, y_te, n, cfg, pair_key, k_values, draws)
    k10 = kb[str(cfg['k_decision'])]['Pi_k'] if str(cfg['k_decision']) in kb else None
    result = {'config': mech.config, 'alpha': pt.alpha, 'alpha_key': alpha_key(pt.alpha), 'pair_key': pair_key, 'noise_plan': noise_plan,
              'Pi': pi, 'winner': win, 'ci95': ci, 'variants': report, 'Pi_k10': k10, 'k_beat': kb, 'reconstruction': recon,
              'epochs_run': {m.name: trained[m.name][0]['epochs_run'] for m in members} | {f'B_naive seed{r["seed"]}': r['epochs_run'] for r in b_naive['seeds']},
              'gpu_cpu_epoch1': pt.gpu_cpu, 'standardization': 'B_naive: its draw-0 train tensor; adaptive keys: epoch-1 realization',
              'seconds': round(time.time() - t0, 1)}
    write_json(Path(out)/f'point-{name}.json', result)
    np.savez(Path(out)/f'point-{name}-arrays.npz', test_rows=ctx.split['test'], test_labels=y_te,
             **{f'{var}|pred_seed{sd}': v['preds'][i] for var, v in variants.items() for i, sd in enumerate(cfg['B_seeds'])},
             **{f'{var}|logprob_seed{sd}': v['logprobs'][i] for var, v in variants.items() for i, sd in enumerate(cfg['B_seeds'])})
    torch.save(states, Path(out)/f'point-{name}-attackers.pt')
    ctx.log(f'part c {name}: Pi={pi:.4f} ({win}) Pi_k10={k10}')
    return result


def eval_with(ctx, pt, kind, part_view, stats):
    """Test tensors of a clean attacker from the noisy view: its own standardization (source or composite at s')."""
    if kind == 'source':
        return v3.attacker_input(part_view, stats, pt.s_in)
    t = int(kind[1:])
    u = v3.composite(v3.frozen_ops(ctx.model, v3.cut_of(pt.src), t), v3.start_of(part_view, pt.src), t)
    return v3.attacker_input(u, stats, t)


def mean_fn(ctx, pt, models, stats, kind):
    """Mean aggregator: averaged noisy source views -> (source attacker) or (frozen ops, re-quantized at s') -> attacker."""
    return lambda avg: v3.predict_seeds(models, eval_with(ctx, pt, kind, avg, stats), ctx.device)[0]


def clean_attackers_for(ctx_clean, config, targets):
    """Clean rho0 attackers: the same source (v2 trial s2-rho0 for R2, part a s0c-rho0 for C0c) and every s' target,
    each passing the reproduction gate on genuine tensors first."""
    out = {'source': v3.naive_source(ctx_clean, SOURCE[config])}
    v3.reproduction_gate(ctx_clean, out['source'])
    for t in targets:
        out[f's{t}'] = v3.target_of(ctx_clean, t, {})
    return out


# ---------- run, timing, smoke ----------

def run(plan_path, output, authorization, part_a_dir, device='auto', noise_plan=None):
    auth = v3.require_authorization(authorization, plan_path, 'c')  # Before any data, model or output.
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Output must be a new path under ignored ml/data')
    pf = v3.preflight(plan_path)
    cfg = v3.settings()
    precision = v2.set_precision()
    configure()
    dev = v2.device_of(device)
    x, split, rho0, data = v3.load_trial(plan_path)
    need(v2.split_counts(split, len(x)) == pf['counts'], 'Split counts differ from preflight')
    need(nopeek.macro_f1_exact(nopeek.a_confusion()) == F1_A, "A's validation macro-F1 differs from the protocol")
    output.mkdir(parents=True)
    sig = sigma_values(rho0, data['train'][0])
    sigma_sha = write_sigma(output, sig, len(data['train'][0]))
    ref = v3.s0c_reference()
    x_val, y_val = data['val'][0], data['val'][1]
    utility = {c: matched_utility(Mechanism(c, rho0, sig[c]), x_val, y_val, ref if c == 'C0c' else None) for c in CONFIG_INDEX}
    write_json(output/'utility.json', utility)
    noise_plan = noise_plan or {'kind': 'fresh'}
    points = []
    for c in CONFIG_INDEX:
        for t, r in utility[c]['targets'].items():
            if r['reachable']:
                points.append({'config': c, 'target': t, 'alpha_t': r['alpha_t']})
    for i, p in enumerate(points):
        p['pair_key'] = read_json(plan_path)['part_c_pair_key_offset'] + i
    part_a_files = {f: sha(Path(part_a_dir)/f) for f in sorted(p.name for p in Path(part_a_dir).glob('s*-rho0*'))}
    manifest = {'protocol_sha256': v3.PROTOCOL_SHA, 'authorization_sha256': sha(authorization), 'sigma_sha256': sigma_sha,
                'utility_sha256': sha(output/'utility.json'), 'points': points, 'noise_plan': noise_plan, 'part_a_files_sha256': part_a_files,
                'DS2_rule_from_lock': 'DS2 follows the DS1 noise plan, with part_index 7 in place of 0 (lock run_manifest_requirements)',
                **v2.environment(dev, precision), 'written': 'before the first privacy fit'}
    write_json(output/'run-manifest.json', manifest)
    receipt = read_json(ROOT/v3.protocol()['source_bindings']['attack_v2_trial_receipt']['path'])['outputs_sha256']
    ctx = v3.Context(model=rho0, x=x, split=split, cfg=cfg, device=dev, out=output, v2dir=ROOT/v3.V2_RUNS, receipt=receipt,
                     log=lambda m: print(m, flush=True))
    ctx_clean = v3.Context(**{**ctx.__dict__, 'out': Path(part_a_dir)})
    results = []
    for p in points:
        clean = clean_attackers_for(ctx_clean, p['config'], COMPOSITE_TARGETS[p['config']])
        results.append(run_point(ctx, Mechanism(p['config'], rho0, sig[p['config']]), p['alpha_t'], COMPOSITE_TARGETS[p['config']],
                                 noise_plan, output, p['pair_key'], clean))
    summary = summarize(results, utility, cfg)
    write_json(output/'part-c-result.json', {'status': 'COMPLETED_DS1_REPORT_FOR_SV1', 'approved_by': auth['approved_by'], **summary,
                                             'DS2_opened': False})
    return summary


def summarize(results, utility, cfg):
    rows = []
    for r in results:
        f1 = next(Fraction(e['macro_f1']) for e in utility[r['config']]['evaluated'] if e['alpha_key'] == r['alpha_key'])
        rows.append({'config': r['config'], 'alpha': r['alpha'], 'macro_f1': float(f1), 'passes_gate': f1 >= GATE, 'Pi': r['Pi'],
                     'Pi_k10': r['Pi_k10'], 'winner': r['winner'], 'reconstruction_headline': r['reconstruction']['headline'],
                     'pass_on_DS1': bool(f1 >= GATE and r['Pi'] >= cfg['Pi_min'] and r['Pi_k10'] is not None and r['Pi_k10'] >= cfg['Pi_min'])})
    selected = {c: [r['alpha'] for r in rows if r['config'] == c and r['pass_on_DS1']] for c in CONFIG_INDEX}
    reading = ('control_selected' if selected['C0c'] else 'only_R2_selected' if selected['R2'] else 'neither')
    return {'points': rows, 'selected_on_DS1': selected, 'reading_declared_before_run': reading,
            'epochs_run': {f"{r['config']}-alpha{r['alpha_key']}": r['epochs_run'] for r in results}}


def timing(output, device='auto', epochs=2):
    """Random arrays of the real part sizes (no MITDB): seconds per lockstep epoch of one R2 and one C0c point with all
    variants, utility seconds per alpha, and an extrapolation of the whole part c for the fallback decision."""
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Timing output must be a new path under ignored ml/data')
    counts = v2.protocol()['data']['trial_week11']['counts']
    cfg = {**v3.settings(), 'max_epochs': epochs, 'patience': 10**6}
    precision = v2.set_precision()
    configure()
    dev = v2.device_of(device)
    rng = np.random.default_rng(7)
    n_rec = 22
    per = (counts['attacker_side'] + counts['test'])//n_rec + 1
    rows, x = v2.synthetic_beats(rng, list(range(100, 100 + n_rec)), per)
    split = v2.time_split(rows, v2.protocol()['data']['trial_week11'])
    rho0 = v2.load_rho(v2.checkpoint_table(v2.protocol())['rho0'])
    ctx = v3.Context(model=rho0, x=x, split=split, cfg=cfg, device=dev, out=output, v2dir=None, receipt=None, log=lambda m: None)
    sig = sigma_values(rho0, x[:4000])
    out = {'parts': {k: int(len(split[k])) for k in v3.parts_of(split)}, **v2.environment(dev, precision), 'epochs_timed': epochs}
    x_val, y_val = x[:9523], rng.integers(0, 4, 9523)
    for c in CONFIG_INDEX:
        mech = Mechanism(c, rho0, sig[c])
        u = Utility(mech, x_val, y_val)
        t0 = time.time()
        u(0.5)
        t_util = time.time() - t0
        pt = Point(ctx, mech, 0.5, COMPOSITE_TARGETS[c], {'kind': 'fresh'})
        t0 = time.time()
        pt.inputs(1, ['source', *[f's{t}' for t in COMPOSITE_TARGETS[c]]])
        t_inputs = time.time() - t0
        n = split['n']
        keys = ['source', *[f's{t}' for t in COMPOSITE_TARGETS[c]]]
        val_in = {k: pt.eval_input(k, pt.val) for k in keys}
        y_tr, y_va, _ = ctx.labels()
        members = [Member(f'{k} seed{sd}', k, 'B', sd, lambda k=k: v2.b_classifier(val_in[k].shape[1:], n, cfg['architectures']['base']),
                          cfg, dev, y_tr, val_in[k], y_va, n, v3.class_weight(y_tr, n)) for sd in cfg['B_seeds'] for k in keys]
        t0 = time.time()
        lockstep(members, pt.inputs, cfg, dev)
        per_epoch = (time.time() - t0)/epochs
        out[c] = {'utility_seconds_per_alpha': t_util, 'epoch1_inputs_seconds': t_inputs, 'lockstep_seconds_per_epoch': per_epoch,
                  'variants_x_seeds': len(members)}
    alphas = 2*(len(GRID) + 4*BISECTION_STEPS)
    worst = sum(out[c]['utility_seconds_per_alpha'] for c in CONFIG_INDEX)/2*alphas + 4*sum(50*out[c]['lockstep_seconds_per_epoch'] for c in CONFIG_INDEX)
    out['extrapolation'] = {'utility_alphas_upper_bound': alphas, 'points': 8, 'max_epochs': 50,
                            'hours_upper_bound_training_and_utility': round(worst/3600, 2),
                            'not_included': 'B_naive (fixed tensors), test predictions, k-beat tables, reconstruction metrics'}
    write_json(output/'timing.json', out)
    return out


def smoke(output, device='auto', epochs=2):
    """Synthetic beats and a synthetic validation set, checkpoint A: sigma, the matched-utility search, one point per
    configuration with the reduced composite targets and k values; one point rerun must be identical."""
    output = (ROOT/output).resolve()
    need(output.is_relative_to(ROOT/'ml/data') and not output.exists(), 'Smoke output must be a new path under ignored ml/data')
    cfg = {**v3.settings(), 'max_epochs': epochs, 'resamples': 200, 'k_resamples': 200}
    precision = v2.set_precision()
    configure()
    dev = v2.device_of(device)
    rows, x = v2.synthetic_beats(np.random.default_rng(12345), [101, 106, 108, 109, 112, 114, 115, 116], 400)
    split = v2.time_split(rows, v2.protocol()['data']['trial_week11'])
    rho0 = v2.load_rho(v2.checkpoint_table(v2.protocol())['rho0'])
    output.mkdir(parents=True)
    (output/'v2-stand-in').mkdir()
    ctx = v3.Context(model=rho0, x=x, split=split, cfg=cfg, device=dev, out=output, v2dir=output/'v2-stand-in', receipt=None, log=print)
    v3.smoke_naive(ctx, 's2')
    v3.part_a(ctx)  # Clean s9, s10, s0c attackers (part a files in the smoke directory).
    sig = sigma_values(rho0, x[split['attacker_train']])
    write_sigma(output, sig, len(split['attacker_train']))
    rng = np.random.default_rng(99)
    x_val, y_val = x[rng.choice(len(x), 600, replace=False)], rng.integers(0, 4, 600)
    ref = v3.s0c_reference()
    utility = {c: matched_utility(Mechanism(c, rho0, sig[c]), x_val, y_val, ref if c == 'C0c' else None) for c in CONFIG_INDEX}
    write_json(output/'utility.json', utility)
    targets = {'R2': [9, 10], 'C0c': [2, 9, 10]}
    res = {}
    for i, c in enumerate(CONFIG_INDEX):
        clean = clean_attackers_for(ctx, c, targets[c])
        res[c] = run_point(ctx, Mechanism(c, rho0, sig[c]), 0.5, targets[c], {'kind': 'fresh'}, output, 100 + i, clean,
                           k_values=[1, 5, 10], draws=20)
    again = run_point(ctx, Mechanism('C0c', rho0, sig['C0c']), 0.5, targets['C0c'], {'kind': 'fresh'}, output/'v2-stand-in', 101,
                      clean_attackers_for(ctx, 'C0c', targets['C0c']), k_values=[1, 5, 10], draws=20)
    strip = lambda r: json.dumps({k: v for k, v in r.items() if k != 'seconds'}, sort_keys=True)  # noqa: E731
    same = strip(again) == strip(res['C0c'])
    need(same, 'Smoke determinism check failed: C0c point rerun differs')
    fb = run_point(ctx, Mechanism('R2', rho0, sig['R2']), 0.5, [9], {'kind': 'fallback', 'R': 20}, output/'v2-stand-in', 102,
                   clean_attackers_for(ctx, 'R2', [9]), k_values=[10], draws=20)
    result = {'status': 'SMOKE_PASS_RANDOM_DATA_NOT_MITDB', 'epochs': epochs, **v2.environment(dev, precision),
              'utility_alpha_t': {c: {t: r['alpha_t'] for t, r in u['targets'].items()} for c, u in utility.items()},
              'points': {c: {'Pi': r['Pi'], 'Pi_k10': r['Pi_k10'], 'winner': r['winner'], 'gpu_cpu_epoch1': r['gpu_cpu_epoch1'],
                             'epochs_run': r['epochs_run']} for c, r in res.items()},
              'C0c_point_rerun_identical': same, 'fallback_plan_runs': {'Pi': fb['Pi'], 'noise_plan': fb['noise_plan']}}
    write_json(output/'smoke-result.json', result)
    return result


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('mode', choices=['smoke', 'timing', 'run'])
    a.add_argument('--plan', type=Path, default=Path(v3.PLAN_DIR)/'plan-manifest.json')
    a.add_argument('--output', type=Path)
    a.add_argument('--authorization', type=Path)
    a.add_argument('--part-a-dir', type=Path)
    a.add_argument('--device', default='auto')
    a.add_argument('--epochs', type=int, default=2)
    a.add_argument('--fallback-R', type=int)
    args = a.parse_args()
    if args.mode == 'smoke':
        print(json.dumps(smoke(args.output, args.device, args.epochs), indent=2))
    elif args.mode == 'timing':
        print(json.dumps(timing(args.output, args.device, args.epochs), indent=2))
    else:
        need(args.fallback_R is None or args.fallback_R >= 20, 'Fallback needs R >= 20')
        plan = {'kind': 'fallback', 'R': args.fallback_R} if args.fallback_R else {'kind': 'fresh'}
        print(json.dumps(run(ROOT/args.plan, args.output, args.authorization, ROOT/args.part_a_dir, args.device, plan), indent=2, default=str))


if __name__ == '__main__':
    main()
