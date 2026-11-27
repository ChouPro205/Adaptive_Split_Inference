"""Attack v3 r5 rules on fixtures: protocol lock, S0c vectorized path against the bound reference, composites against
the head of checkpoint A, k-beat blocks, votes and statistics, the authorization gate, the part c noise streams,
matched-utility search, the torch quantization and the lockstep trainer. Never reads a MITDB array or metadata file
(the smokes have their own receipt)."""
import json
import re
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np
import torch

import attack_m1_v3 as v3
import noise_m1_v3 as nz

v2 = v3.v2
ROOT = v3.ROOT
P = v3.protocol()
CFG = v3.settings()
REF = v3.s0c_reference()
RHO0 = v2.load_rho(v2.checkpoint_table(v2.protocol())['rho0'])


def beats(n, seed=0, scale=1.0):
    return np.ascontiguousarray(np.random.default_rng(seed).standard_normal((n, 360))*scale, dtype=np.float32)


class ProtocolTests(unittest.TestCase):
    def test_protocol_and_lock(self):
        self.assertEqual(v3.sha(ROOT/v3.PROTOCOL), v3.PROTOCOL_SHA)
        lock = v3.require_lock()
        self.assertFalse(lock['allow_attack_runs'] or lock['allow_DS2'])
        self.assertEqual(P['revision'], 5)

    def test_settings(self):
        self.assertEqual(CFG['k_values'], [1, 2, 5, 10, 20, 50, 100])
        self.assertEqual((CFG['k_decision'], CFG['scatter_draws'], CFG['k_resamples']), (10, 200, 2000))
        self.assertEqual(CFG['B_seeds'], [20261030, 20261031, 20261101])
        self.assertEqual(CFG['Pi_min'], 0.5)

    def test_part_b_pairs_are_27(self):
        pairs = [(s, t) for s in v3.SOURCES_B for t in v3.TARGETS_B if t > v3.cut_of(s)]
        self.assertEqual(len(pairs), 27)

    def test_part_c_constants_follow_protocol(self):
        c = P['part_c_rho2_and_s0c_noise_control']
        self.assertEqual(list(nz.GRID), c['matched_utility_search']['coarse_grid_alpha'])
        self.assertEqual(nz.F1_A, Fraction(re.search(r'(\d+/\d+)', c['utility']['F1_A']).group(1)))
        self.assertEqual(nz.GATE, Fraction(re.search(r'F1_A = (\d+/\d+)', c['utility']['gate']).group(1)))
        self.assertEqual(nz.CONFIG_INDEX, {'R2': 0, 'C0c': 2})
        self.assertEqual(sorted(nz.PART_INDEX_DS2.values()), [4, 5, 6, 7])
        self.assertEqual(nz.PART_INDEX_DS2['attacker_train'], 7)


class S0cTests(unittest.TestCase):
    def test_golden(self):
        r = v3.s0c_golden_check(REF, ROOT/v2.protocol()['source_bindings']['package_A']['path'])
        self.assertTrue(r['arrays_bitwise_equal'] and r['bitwise_equal'])

    def test_vectorized_equals_reference_on_random_beats(self):
        for scale in (1.0, 1e-3, 30.0):
            self.assertTrue(v3.s0c_reference_check(beats(40, 1, scale), REF)['bitwise_equal'])

    def test_zero_beat(self):
        t = v3.s0c_transmit(v3.reduce46(np.zeros((2, 360), np.float32)))
        self.assertTrue(np.all(t['scale'] == np.float16(1)) and np.all(t['xc'] == 0))

    def test_bins_and_interpolation_table(self):
        self.assertEqual(v3.BINS, REF.BINS)
        v = np.random.default_rng(3).standard_normal((5, 46)).astype(np.float32)
        mine = v3.interpolate360(v)
        for i in range(5):
            self.assertTrue(np.array_equal(mine[i].view(np.uint32), REF.interpolate360(v[i]).view(np.uint32)))

    def test_difference_is_refused(self):
        class Bad:
            def __getattr__(self, name):
                return getattr(REF, name)

            def reduce46(self, x):
                return REF.reduce46(x) + np.float32(1e-3)
        with self.assertRaises(ValueError):
            v3.s0c_reference_check(beats(3), Bad())


class CompositeTests(unittest.TestCase):
    def test_composite_from_input_equals_observed(self):
        x = beats(6, 4)
        for s in (2, 5, 9, 10):
            u = v3.composite(v3.frozen_ops(RHO0, 0, s), x[:, None, :], s)
            self.assertTrue(np.array_equal(u, v2.observed(RHO0, x, s)), s)

    def test_composite_chain_from_unquantized_head(self):
        x = beats(4, 5)
        z2 = v2.head_output(RHO0, x, 2)
        u = v3.composite(v3.frozen_ops(RHO0, 2, 8), z2, 8)
        self.assertTrue(np.array_equal(u, v2.observed(RHO0, x, 8)))

    def test_start_of(self):
        x = beats(3, 6)
        view = v3.view_of(RHO0, x, 's0c')
        self.assertEqual(view.shape, (3, 1, 46))
        self.assertEqual(v3.start_of(view, 's0c').shape, (3, 1, 360))
        self.assertEqual(v3.start_of(v3.view_of(RHO0, x, 's9'), 's9').shape, (3, 32))

    def test_target_must_be_deeper(self):
        with self.assertRaises(ValueError):
            v3.frozen_ops(RHO0, 4, 4)

    def test_standardization_matches_v2(self):
        a = np.random.default_rng(1).standard_normal((50, 3, 7)).astype(np.float32)
        b = np.random.default_rng(2).standard_normal((9, 3, 7)).astype(np.float32)
        st = v3.fit_stats(a)
        ref = v2.standardize(a, b)
        self.assertTrue(np.array_equal(v3.attacker_input(a, st, 2), ref[0]) and np.array_equal(v3.attacker_input(b, st, 2), ref[1]))


class KBeatTests(unittest.TestCase):
    y = np.repeat(np.arange(3), [25, 12, 30])

    def test_consecutive_drops_short_last_block(self):
        pos, owner = v3.make_blocks(self.y, 3, 10, 'consecutive', 0)
        self.assertEqual(np.bincount(owner).tolist(), [2, 1, 3])
        self.assertTrue(np.array_equal(pos[0], np.arange(10)))

    def test_scattered_is_keyed_and_without_replacement(self):
        a, oa = v3.make_blocks(self.y, 3, 10, 'scattered', 7, draws=5)
        b, _ = v3.make_blocks(self.y, 3, 10, 'scattered', 7, draws=5)
        c, _ = v3.make_blocks(self.y, 3, 10, 'scattered', 8, draws=5)
        self.assertTrue(np.array_equal(a, b) and not np.array_equal(a, c))
        self.assertTrue(all(len(set(r)) == 10 and np.all(self.y[r] == o) for r, o in zip(a, oa)))

    def test_too_few_beats_refused(self):
        with self.assertRaises(ValueError):
            v3.make_blocks(self.y, 3, 20, 'scattered', 0)

    def test_votes(self):
        preds = np.array([[0, 1, 1, 2, 2, 0]])
        self.assertEqual(v3.vote_hard(preds, np.array([[0, 1, 3, 5]]), 3).tolist(), [[0]])  # 0,1,2,0 -> tie-free 0
        self.assertEqual(v3.vote_hard(preds, np.array([[1, 3]]), 3).tolist(), [[1]])  # Tie 1 vs 2 -> lowest.
        lps = np.log(np.array([[[.6, .3, .1], [.1, .5, .4], [.1, .4, .5]]], dtype=np.float32))
        self.assertEqual(v3.vote_soft(lps, np.array([[0, 1, 2]])).tolist(), [[1]])

    def test_average_views_float64(self):
        view = np.array([[[1e8]], [[1.0]], [[-1e8]]], dtype=np.float32)
        self.assertEqual(float(v3.average_views(view, np.array([[0, 1, 2]]))[0, 0, 0]), np.float32(1/3))

    def test_statistic_and_ci(self):
        owner = np.repeat(np.arange(2), 4)
        correct = np.array([[1, 1, 1, 1, 0, 0, 1, 1]], dtype=bool)
        self.assertEqual(v3.k_bacc(correct, owner, 2).tolist(), [0.75])
        self.assertAlmostEqual(float(v3.adv_of(np.array([0.75]), 2)[0]), 0.5)
        ci = v3.ci_consecutive(correct, owner, 2, 50, 1)
        self.assertLessEqual(ci['low'], ci['high'])
        self.assertEqual(v3.ci_scattered(correct, 2, 4)['draws'], 4)

    def test_k_beat_table(self):
        y = np.repeat(np.arange(2), 20)
        preds = np.stack([y, 1 - y])
        view = np.random.default_rng(0).standard_normal((40, 1, 4)).astype(np.float32)
        att = [{'name': 'a', 'preds': preds, 'logprobs': None, 'mean_fn': lambda avg: np.zeros((2, len(avg)), dtype=np.int64)}]
        t = v3.k_beat(att, view, y, 2, {**CFG, 'k_resamples': 20}, 3, [1, 5], 4)
        self.assertEqual(t['1']['Pi_k'], 0.5)  # Mean over seeds of Adv: (1 + 0) / 2.
        self.assertEqual({(r['mode'], r['aggregator']) for r in t['5']['rows']},
                         {(m, a) for m in ('consecutive', 'scattered') for a in ('hard', 'mean')})


class GateTests(unittest.TestCase):
    def _auth(self, d, **change):
        plan = Path(d)/'plan.json'
        plan.write_text('{}', encoding='utf-8')
        ev = 'ml/provenance/m1-sv1-evidence-20261126/tra_loi_Ky_Anh_r5_xac_nhan_khoa_20261126.txt'
        a = {'type': v3.AUTH_TYPE, 'protocol_sha256': v3.PROTOCOL_SHA, 'protocol_lock_sha256': v3.LOCK_SHA, 'plan_manifest_sha256': v3.sha(plan),
             'allow_parts': ['a', 'b', 'd'], 'allow_DS2': False, 'approved_by': 'SV3', 'review_evidence_path': ev,
             'review_evidence': v3.sha(ROOT/ev), **change}
        path = Path(d)/'auth.json'
        path.write_text(json.dumps(a), encoding='utf-8')
        return path, plan

    def test_accepts_bound_authorization(self):
        with tempfile.TemporaryDirectory() as d:
            path, plan = self._auth(d)
            self.assertEqual(v3.require_authorization(path, plan, 'a')['approved_by'], 'SV3')

    def test_negative_controls(self):
        for change, part in (({}, 'c'), ({'allow_DS2': True}, 'a'), ({'protocol_sha256': '0'*64}, 'a'), ({'protocol_lock_sha256': '0'*64}, 'a'),
                             ({'approved_by': ''}, 'a'), ({'review_evidence': '0'*64}, 'a'), ({'type': 'M1_ATTACK_V2_LOCK_AND_TRIAL_AUTHORIZATION'}, 'a')):
            with tempfile.TemporaryDirectory() as d:
                path, plan = self._auth(d, **change)
                with self.assertRaises(ValueError, msg=str(change)):
                    v3.require_authorization(path, plan, part)

    def test_missing_authorization(self):
        with self.assertRaises(ValueError):
            v3.require_authorization(None, Path('x'), 'a')


class NoiseTests(unittest.TestCase):
    def test_streams(self):
        a = nz.noise((4, 3), 'R2', 0.5, 'test', 0, 1.0)
        self.assertTrue(np.array_equal(a, nz.noise((4, 3), 'R2', 0.5, 'test', 0, 1.0)))
        others = [nz.noise((4, 3), 'C0c', 0.5, 'test', 0, 1.0), nz.noise((4, 3), 'R2', 0.25, 'test', 0, 1.0),
                  nz.noise((4, 3), 'R2', 0.5, 'attacker_validation', 0, 1.0), nz.noise((4, 3), 'R2', 0.5, 'test', 1, 1.0)]
        self.assertTrue(all(not np.array_equal(a/0.5, o/(0.25 if i == 1 else 0.5)) for i, o in enumerate(others)))
        ss = np.random.SeedSequence([20261120, 0, 500000, 2, 0])
        expected = (np.random.default_rng(ss).standard_normal((4, 3))*0.5).astype(np.float32)
        self.assertTrue(np.array_equal(a, expected))

    def test_ds2_streams_refused_here(self):
        with self.assertRaises(ValueError):
            nz.noise((2,), 'R2', 0.5, 'test', 0, 1.0, ds2=True)

    def test_alpha_key(self):
        self.assertEqual(nz.alpha_key(0.05), 50000)
        self.assertEqual(nz.on_key(0.1234567), 0.123457)

    def test_torch_quantization_equals_registry(self):
        z = np.random.default_rng(0).standard_normal((7, 4, 9)).astype(np.float32)*3
        z[0, 0] = 0
        q, s = v3.quantize_per_channel(z)
        self.assertTrue(np.array_equal(nz.quant_dequant_torch(torch.from_numpy(z)).numpy(), v3.dequantize_per_channel(q, s)))

    def test_search_monotone_bisection(self):
        f = lambda a: Fraction(1) - Fraction(nz.alpha_key(a), 10**6)/10  # noqa: E731  (crosses 0.85 at alpha = 1.5)
        r = nz.search(f, Fraction(85, 100))
        self.assertTrue(r['reachable'] and 1.49 < r['alpha_t'] <= 1.5 and f(r['alpha_t']) >= Fraction(85, 100))
        self.assertTrue(f(r['bracket_end']) < Fraction(85, 100) and r['bracket_end']/r['alpha_t'] < 1.01)

    def test_search_downward_and_unreachable(self):
        r = nz.search(lambda a: Fraction(1) if a <= 0.01 else Fraction(0), Fraction(1, 2))
        self.assertTrue(r['reachable'] and r['alpha_t'] <= 0.01 and r['note'] == 'grid 0.05 fails; searched downward')
        self.assertFalse(nz.search(lambda a: Fraction(0), Fraction(1, 2))['reachable'])

    def test_search_non_monotone_first_crossing(self):
        r = nz.search(lambda a: Fraction(1) if a <= 0.25 or a == 2.0 else Fraction(0), Fraction(1, 2))
        self.assertEqual(r['non_monotone'], [2.0])
        self.assertTrue(0.25 <= r['alpha_t'] < 0.5)

    def test_search_all_pass(self):
        self.assertEqual(nz.search(lambda a: Fraction(1), Fraction(1, 2))['alpha_t'], 4.0)

    def test_macro_f1_of_A(self):
        self.assertEqual(nz.nopeek.macro_f1_exact(nz.nopeek.a_confusion()), nz.F1_A)


class LockstepTests(unittest.TestCase):
    def test_lockstep_equals_v2_fit(self):
        """Fixed inputs: the lockstep member reproduces v2.fit (same best epoch, history and state) for two seeds."""
        rng = np.random.default_rng(0)
        n = 3
        tr = rng.standard_normal((90, 2, 8)).astype(np.float32)
        va = rng.standard_normal((30, 2, 8)).astype(np.float32)
        ytr, yva = np.repeat(np.arange(n), 30), np.repeat(np.arange(n), 10)
        cfg = {**CFG, 'max_epochs': 4, 'batch_size': 32}
        dev = torch.device('cpu')
        arch = cfg['architectures']['base']
        w = v3.class_weight(ytr, n)
        members = [nz.Member(f'm{s}', 'k', 'B', s, lambda: v2.b_classifier((2, 8), n, arch), cfg, dev, ytr, va, yva, n, w) for s in (11, 12)]
        got = nz.lockstep(members, lambda e, keys: {'k': torch.from_numpy(tr)}, cfg, dev)
        for s in (11, 12):
            _, info, state = v2.fit(lambda: v2.b_classifier((2, 8), n, arch), s, {'train_x': tr, 'train_y': ytr, 'val_x': va, 'val_y': yva},
                                    'B', cfg, dev, n=n, weight=w)
            self.assertEqual(got[f'm{s}'][0]['history'], info['history'])
            self.assertTrue(all(torch.equal(got[f'm{s}'][1][k], state[k]) for k in state))


if __name__ == '__main__':
    unittest.main()
