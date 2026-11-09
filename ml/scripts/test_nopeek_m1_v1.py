"""NoPeek v1 rules on fixtures, plan and gates; never fits on MITDB (the smoke has its own receipt)."""
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import numpy as np

import nopeek_m1_v1 as nop
from m1_metrics_v4 import all_metrics

ROOT = nop.ROOT
A = nop.a_confusion()
BAD = [row[:] for row in A]
BAD[1] = [172, 0, 0, 0, 0]  # Every S beat predicted N: macro-F1 falls below 19/20 x A.
ALL_N = [[sum(row), 0, 0, 0, 0] for row in A]


def h(epoch, matrix, rn, state='s'):
    m = all_metrics(*expand(matrix))
    m.update(subset_Rn=rn, validation_macro_f1_K_fixed=float(np.mean(m['f1'][:4])))
    return {'epoch': epoch, 'validation': m, 'state_sha256': state}


def expand(matrix):
    y, p = [], []
    for i, row in enumerate(matrix):
        for j, n in enumerate(row):
            y += [i]*n
            p += [j]*n
    return y, p


class RuleTests(unittest.TestCase):
    def test_exact_macro_f1_matches_float_and_gate(self):
        self.assertAlmostEqual(float(nop.macro_f1_exact(A)), float(np.mean(all_metrics(*expand(A))['f1'][:4])), places=14)
        self.assertEqual(nop.macro_f1_exact(A), Fraction(11488986689, 20219195700))
        self.assertTrue(nop.passes(A, A))
        self.assertFalse(nop.passes(BAD, A))

    def test_collapse_rules(self):
        self.assertFalse(nop.collapsed(A))
        self.assertTrue(nop.collapsed(ALL_N))
        low_v = [row[:] for row in A]
        low_v[2] = [903, 0, 101, 0, 0]  # Se_V = 101/1004 >= 0.10.
        self.assertFalse(nop.collapsed(low_v))
        low_v[2] = [904, 0, 100, 0, 0]  # Se_V = 100/1004 < 0.10.
        self.assertTrue(nop.collapsed(low_v))

    def test_epoch_selection(self):
        hist = [h(0, A, .9), h(1, A, .5), h(2, BAD, .1), h(3, A, .5)]
        self.assertEqual(nop.select_epoch(hist, 0, A)['epoch'], 0)
        e = nop.select_epoch(hist, 1, A)
        self.assertEqual((e['epoch'], e['flag']), (1, 'OK'))
        fail = nop.select_epoch([h(0, A, .9), h(1, BAD, .1), h(2, ALL_N, .05)], 1, A)
        self.assertEqual((fail['epoch'], fail['flag'], fail['utility']), (1, 'UTILITY_FAIL', False))


def write_results(root, plan_dir, runs):
    plan = {'runs': [], '_dir': str(plan_dir)}
    for (stage, s, lam, seed, lr), hist in runs.items():
        rid = nop.run_id(stage, s, lam, seed, lr if stage == 'pilot' else None)
        (plan_dir/f'{rid}.json').write_text(json.dumps({'s': s, 'lambda': lam, 'seed': seed, 'lr': lr}), encoding='utf-8')
        (root/rid).mkdir(parents=True)
        (root/rid/'history.json').write_text(json.dumps(hist), encoding='utf-8')
        plan['runs'].append({'run_id': rid, 'stage': stage, 'config': f'{rid}.json'})
    return plan


class SelectionTests(unittest.TestCase):
    def grid(self, rn, lambda0_state=lambda s: 'same'):
        runs = {}
        for s in (2, 4):
            for lam in (0, 1, 5):
                for seed in (1, 2, 3):
                    state = lambda0_state(s) if lam == 0 else f'{s}-{lam}-{seed}'
                    runs[('grid', s, lam, seed, None)] = [h(0, A, .9, state), h(1, A if lam != 5 else BAD, rn(s, lam, seed), state)]
        return runs

    def test_grid_lambda_and_deployment_seed(self):
        rn = lambda s, lam, seed: {0: .9, 1: .5 + .01*seed, 5: .1}[lam]
        with tempfile.TemporaryDirectory() as d:
            plan = write_results(Path(d)/'r', Path(d), self.grid(rn))
            out = nop.choose_grid(Path(d)/'r', plan, A)
        self.assertEqual(out['per_s']['s2']['lambda'], 1)  # lambda 5 fails utility; lambda 1 has the lower mean R_n.
        self.assertEqual(out['per_s']['s2']['deployment_seed'], 2)  # Median R_n among seeds 1, 2, 3.

    def test_lambda_tie_smaller_and_seed_tie_smaller(self):
        rn = lambda s, lam, seed: .9 if lam == 0 else .4
        runs = self.grid(rn)
        for seed in (1, 2, 3):
            runs[('grid', 2, 5, seed, None)][1] = h(1, A, .4, f'x{seed}')
        with tempfile.TemporaryDirectory() as d:
            plan = write_results(Path(d)/'r', Path(d), runs)
            out = nop.choose_grid(Path(d)/'r', plan, A)
        self.assertEqual((out['per_s']['s2']['lambda'], out['per_s']['s2']['deployment_seed']), (1, 1))

    def test_lambda0_states_must_match_across_s(self):
        runs = self.grid(lambda s, lam, seed: .5, lambda0_state=lambda s: f'state-{s}')
        with tempfile.TemporaryDirectory() as d:
            plan = write_results(Path(d)/'r', Path(d), runs)
            with self.assertRaises(ValueError):
                nop.choose_grid(Path(d)/'r', plan, A)

    def test_pilot_rule(self):
        def pilot(lam0_ok):
            runs = {}
            for lr, ok, rn in ((1e-5, lam0_ok[0], .6), (3e-5, lam0_ok[1], .3), (1e-4, lam0_ok[2], .2)):
                runs[('pilot', 2, 0, 1, lr)] = [h(e, A if ok else BAD, .9) for e in range(3)]
                for s in (2, 8):
                    runs[('pilot', s, 5, 1, lr)] = [h(0, A, .9), h(1, A, rn), h(2, BAD, .01)]
            return runs
        with tempfile.TemporaryDirectory() as d:
            plan = write_results(Path(d)/'r', Path(d), pilot((True, True, False)))
            out = nop.choose_pilot(Path(d)/'r', plan, A)
        self.assertEqual((out['status'], out['learning_rate']), ('PILOT_LR_CHOSEN', 3e-5))  # 1e-4 is unsafe.
        with tempfile.TemporaryDirectory() as d:
            plan = write_results(Path(d)/'r', Path(d), pilot((False, False, False)))
            self.assertEqual(nop.choose_pilot(Path(d)/'r', plan, A)['status'], 'NO_SAFE_LEARNING_RATE_REPORT_TO_SV1')


class PlanAndGateTests(unittest.TestCase):
    def test_prepare_counts_and_bindings(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'ml/data') as d:
            rel = Path(d).relative_to(ROOT)/'plan'
            nop.prepare(rel)
            plan = json.loads((ROOT/rel/'plan-manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(sum(r['stage'] == 'pilot' for r in plan['runs']), 9)
            self.assertEqual(sum(r['stage'] == 'grid' for r in plan['runs']), 72)
            self.assertEqual(plan['protocol_sha256'], nop.sha(ROOT/nop.PROTOCOL))
            config = json.loads((ROOT/rel/plan['runs'][0]['config']).read_text(encoding='utf-8'))
            self.assertEqual((config['cudnn_allow_tf32'], config['matmul_allow_tf32'], config['epochs']), (True, False, 10))
            self.assertEqual(nop.preflight(ROOT/rel/'plan-manifest.json')['runs'], 81)
            with self.assertRaises(ValueError):
                nop.prepare(rel)

    def test_run_refused_without_authorization_before_any_load(self):
        opened = []
        real = np.load
        def spy(path, *a, **k):
            opened.append(str(path))
            return real(path, *a, **k)
        with tempfile.TemporaryDirectory(dir=ROOT/'ml/data') as d:
            rel = Path(d).relative_to(ROOT)
            nop.prepare(rel/'plan')
            with patch.object(nop.np, 'load', spy):
                with self.assertRaises(ValueError):
                    nop.run_stage('pilot', ROOT/rel/'plan/plan-manifest.json', rel/'out', None)
                bad = ROOT/rel/'auth.json'
                bad.write_text(json.dumps({'type': nop.AUTH_TYPE, 'allow_training': True, 'protocol_sha256': '0'*64}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    nop.run_stage('pilot', ROOT/rel/'plan/plan-manifest.json', rel/'out', bad)
        self.assertEqual(opened, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
