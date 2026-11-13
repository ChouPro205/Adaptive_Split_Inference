"""Attack v2 rules on fixtures: protocol settings and bindings, time split, metrics, bootstrap, models, observed tensors,
precision and the authorization gate. Never reads a MITDB array or metadata file (the smoke has its own receipt)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

import attack_m1_v2 as att

ROOT = att.ROOT
P = att.protocol()
RULE = P['data']['trial_week11']


def rows_of(spec):
    """spec: {record_id: [r_peak_sample, ...]} -> metadata-like rows, interleaved to check the split sorts by time."""
    rows = []
    for rec, peaks in spec.items():
        rows += [{'record_id': str(rec), 'r_peak_sample': str(t)} for t in peaks]
    return rows[::-1]


class ProtocolTests(unittest.TestCase):
    def test_settings_from_protocol(self):
        s = att.settings(P)
        self.assertEqual((s['lr'], s['weight_decay'], s['betas'], s['eps']), (1e-3, 1e-4, (0.9, 0.999), 1e-8))
        self.assertEqual((s['batch_size'], s['max_epochs'], s['patience']), (256, 50, 5))
        self.assertEqual(s['B_seeds'], [20261030, 20261031, 20261101])
        self.assertEqual(s['A1_seeds'], [20261030])
        self.assertEqual((s['resamples'], s['bootstrap_seed'], s['block_beats']), (2000, 20261105, 10))
        self.assertEqual((s['capacity_threshold'], s['Pi_min']), (0.8, 0.5))
        self.assertEqual(s['architectures']['base']['NCL'], {'blocks': 2, 'channels': 64, 'kernel': 5,
                         'block': 'Conv1d(padding 2) + ReLU + MaxPool1d(2)', 'head': 'mean over L, Linear(channels, N)'})
        self.assertEqual(s['architectures']['escalated']['NCL'], {'blocks': 3, 'channels': 128, 'kernel': 5})
        self.assertEqual(s['architectures']['escalated']['NC']['hidden'], [256, 256])

    def test_settings_refuse_tf32_on(self):
        bad = copy.deepcopy(P)
        bad['attack_models']['training']['precision']['matmul_allow_tf32'] = True
        with self.assertRaises(ValueError):
            att.settings(bad)

    def test_bindings_and_change_sources(self):
        att.binding_hashes(P)
        self.assertEqual(P['predecessor']['sha256'], att.sha(ROOT/P['predecessor']['path']))
        self.assertTrue(all(c['source'] for c in P['changes_from_v1']))
        self.assertEqual([c['item'] for c in P['changes_from_v1']], list(range(1, 16)))
        self.assertEqual(P['trial_week11_scope']['order'][0], ['s0', 'rho0'])
        self.assertEqual(P['attacks']['in_this_lock'], ['A1', 'B_naive'])
        self.assertFalse(P['authority']['locked'] or P['authority']['attack_runs_permitted'] or P['data']['DS2_in_trial'])

    def test_checkpoint_table_matches_selection_receipt_and_files(self):
        table = att.checkpoint_table(P)
        self.assertEqual(table['rho0']['sha256'], 'fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c')
        self.assertEqual({s: (e['lambda'], e['seed'], e['epoch']) for s, e in table['rho1'].items()},
                         {'s2': (2, 20261101, 3), 's4': (1, 20261031, 3), 's5': (1, 20261030, 2), 's8': (5, 20261031, 5)})
        for c in att.checkpoint_files(table):
            self.assertEqual(att.sha(ROOT/c['path']), c['sha256'])

    def test_checkpoint_table_rejects_a_changed_rho1(self):
        bad = copy.deepcopy(P)
        bad['checkpoints']['rho1']['s4']['epoch'] = 4
        with self.assertRaises(ValueError):
            att.checkpoint_table(bad)


class SplitTests(unittest.TestCase):
    def test_boundaries_validation_labels_and_order(self):
        rows = rows_of({101: [100, 200, 300, 400, 314199, 314200, 325000, 335800, 335801, 600000],
                        7: [10, 20, 30, 40, 50, 60, 400000, 500000]})
        sp = att.time_split(rows, RULE)
        self.assertEqual(sp['records'], [7, 101])  # Numeric rank, not text order.
        r = lambda idx: [(int(rows[i]['record_id']), int(rows[i]['r_peak_sample'])) for i in idx]  # noqa: E731
        self.assertEqual(sp['dropped'], 3)  # 314200, 325000 and 335800 lie within 10800 of 325000.
        self.assertEqual(r(sp['attacker_train']), [(7, 10), (7, 20), (7, 30), (7, 40), (101, 100), (101, 200), (101, 300), (101, 400)])
        self.assertEqual(r(sp['attacker_validation']), [(7, 50), (7, 60), (101, 314199)])  # ceil(0.2 x 6) = 2, ceil(0.2 x 5) = 1.
        self.assertEqual(r(sp['test']), [(7, 400000), (7, 500000), (101, 335801), (101, 600000)])
        self.assertEqual(sp['labels'][sp['test']].tolist(), [0, 0, 1, 1])
        counts = att.split_counts(sp, len(rows))
        self.assertEqual((counts['attacker_side'], counts['test'], counts['attacker_side_per_record'], counts['test_per_record']),
                         (11, 4, [5, 6], [2, 2]))

    def test_validation_size_is_the_exact_ceiling(self):
        for n, want in ((15, 3), (16, 4), (1000, 200), (767, 154), (1637, 328), (4, 1)):
            sp = att.time_split(rows_of({101: list(range(1, n+1)) + [400000]}), RULE)
            self.assertEqual(len(sp['attacker_validation']), want)

    def test_record_without_test_or_duplicate_peak_refused(self):
        with self.assertRaises(ValueError):
            att.time_split(rows_of({101: [100, 200, 300]}), RULE)
        with self.assertRaises(ValueError):
            att.time_split(rows_of({101: [100, 100, 200, 400000]}), RULE)


class MetricTests(unittest.TestCase):
    def test_balanced_accuracy_and_advantage(self):
        bacc, rec = att.balanced_accuracy([0, 0, 1, 1, 1], [0, 1, 1, 1, 0], 2)
        self.assertEqual(rec, [0.5, 2/3])
        self.assertAlmostEqual(bacc, (0.5 + 2/3)/2)
        self.assertEqual(att.advantage(1/22, 22), 0.)
        self.assertEqual(att.advantage(1., 22), 1.)
        self.assertEqual(att.advantage(0.01, 22), 0.)  # Below chance is clipped.
        self.assertAlmostEqual(att.advantage(0.5, 2), 0.)
        with self.assertRaises(ValueError):
            att.balanced_accuracy([0, 0], [0, 0], 2)  # A patient without test beats.

    def test_bootstrap_blocks_seeds_and_determinism(self):
        y = np.repeat(np.arange(3), [25, 31, 12])
        perfect = y.copy()
        ci = att.bootstrap_pi(y, [perfect], 3, 200, 20261105, 10)
        self.assertEqual((ci['low'], ci['high']), (0., 0.))  # Always right: Adv = 1, Pi = 0.
        rng = np.random.default_rng(1)
        noisy = [np.where(rng.random(len(y)) < 0.6, y, rng.integers(0, 3, len(y))) for _ in range(3)]
        a = att.bootstrap_pi(y, noisy, 3, 300, 20261105, 10)
        self.assertEqual(a, att.bootstrap_pi(y, noisy, 3, 300, 20261105, 10))
        self.assertNotEqual(a, att.bootstrap_pi(y, noisy, 3, 300, 7, 10))
        self.assertLessEqual(a['low'], a['high'])
        point = 1 - np.mean([att.advantage(att.balanced_accuracy(y, p, 3)[0], 3) for p in noisy])
        self.assertTrue(a['low'] - 0.2 <= point <= a['high'] + 0.2)
        one = att.bootstrap_pi(y, [noisy[0]], 3, 300, 20261105, 10)
        self.assertEqual(one, att.bootstrap_pi(y, [noisy[0]]*3, 3, 300, 20261105, 10))  # Same draw for every seed.

    def test_blocks_need_contiguous_patients(self):
        self.assertEqual([len(b) for b in att.test_blocks(np.repeat([0, 1], [23, 10]), 2, 10)[0]], [10, 10, 3])
        with self.assertRaises(ValueError):
            att.test_blocks(np.array([0, 1, 0]), 2, 10)

    def test_session_vote_ties_to_lowest_label(self):
        y = np.array([0]*4 + [1]*4)
        self.assertEqual(att.session_bacc(y, np.array([1, 0, 1, 0, 1, 1, 1, 1]), 2, 4), 1.)  # Tie 2-2 in block 0 -> label 0.
        self.assertEqual(att.session_bacc(y, np.array([1, 1, 1, 0, 0, 0, 1, 1]), 2, 4), 0.)  # Patient 1 tie -> label 0, wrong.
        self.assertEqual(att.session_bacc(y, np.array([0, 0, 0, 1, 1, 1, 1, 0]), 2, 4), 1.)

    def test_reconstruction_metrics(self):
        x = np.random.default_rng(0).standard_normal((4, 360))
        m = att.reconstruction_metrics(x, x)
        self.assertEqual((m['NRMSE']['mean'], m['r_peak_error_samples']['mean']), (0., 0.))
        self.assertAlmostEqual(m['pearson']['mean'], 1.)
        z = att.reconstruction_metrics(np.zeros_like(x), x)
        self.assertEqual(z['pearson']['mean'], 0.)
        self.assertAlmostEqual(z['NRMSE']['mean'], float(np.mean(np.sqrt((x**2).mean(1))/x.std(1))))
        b, h = np.zeros((1, 360)), np.zeros((1, 360))
        b[0, 180], h[0, 189] = 5., -5.  # |argmax| uses the absolute value.
        self.assertEqual(att.reconstruction_metrics(h, b)['r_peak_error_samples']['mean'], 9.)
        self.assertAlmostEqual(att.reconstruction_metrics(h, b)['r_peak_error_ms']['mean'], 25.)


class ModelTests(unittest.TestCase):
    def test_decoder_mirrors_the_head(self):
        for s in range(1, 11):
            d = att.a1_decoder(s)
            x = torch.zeros((2, 32) if s == 9 else (2, 5) if s == 10 else (2, *att.SHAPES[s][1:]))
            self.assertEqual(tuple(d(x).shape), (2, 1, 360))
            convs = [m for m in d if isinstance(m, torch.nn.Conv1d)]
            self.assertEqual(len(convs), min(s, 8))
            self.assertEqual(sum(isinstance(m, att.Upsample) for m in d), min(s, 8)//2)
            self.assertNotIsInstance(list(d)[-1], torch.nn.ReLU)
        with self.assertRaises(ValueError):
            att.a1_decoder(0)

    def test_classifier_shapes(self):
        arch = att.settings(P)['architectures']
        for name in ('base', 'escalated'):
            for s in (0, 2, 4, 5, 8):
                shape = att.SHAPES[s][1:]
                self.assertEqual(tuple(att.b_classifier(shape, 22, arch[name])(torch.zeros(2, *shape)).shape), (2, 22))
            for c in (32, 5):
                self.assertEqual(tuple(att.b_classifier((c,), 22, arch[name])(torch.zeros(2, c)).shape), (2, 22))
        convs = [m for m in att.b_classifier((16, 180), 22, arch['escalated']) if isinstance(m, torch.nn.Conv1d)]
        self.assertEqual([(m.in_channels, m.out_channels) for m in convs], [(16, 128), (128, 128), (128, 128)])

    def test_capacity_rule_and_early_stop(self):
        self.assertEqual(att.choose_architecture(0.8, 0.8), 'base')
        self.assertEqual(att.choose_architecture(0.7999, 0.8), 'escalated')
        self.assertTrue(att.improves('B', 0.5, None))
        self.assertFalse(att.improves('B', 0.5, {'validation': 0.5}))  # Tie keeps the earlier epoch.
        self.assertTrue(att.improves('A1', 0.1, {'validation': 0.2}))
        self.assertFalse(att.improves('A1', 0.2, {'validation': 0.2}))
        self.assertFalse(att.stops(7, 3, 5))
        self.assertTrue(att.stops(8, 3, 5))

    def test_capacity_check_runs_first_and_escalates_once(self):
        order = [['s0', 'rho0'], ['s2', 'rho0'], ['s2', 'rho1']]
        for s0_bacc, decision, names in ((0.85, 'base', ['s0-rho0-base', 's2-rho0', 's2-rho1']),
                                         (0.40, 'escalated', ['s0-rho0-base', 's0-rho0-escalated', 's2-rho0', 's2-rho1'])):
            calls = []

            def fake(model, x, split, s, arch, cfg, device):
                calls.append((s, arch))
                b = {'Pi': 0.5, 'ci95': {'low': 0.4, 'high': 0.6}, 'seed_range': {'Pi': [0.4, 0.6]}, 'passes_Pi_min': True,
                     'architecture': arch, 'bacc_mean': s0_bacc if s == 0 and arch == 'base' else 0.1}
                return {'s': s, 'B_naive': b, 'A1': {'metrics': {'NRMSE': {'mean': 0.5}, 'pearson': {'mean': 0.5}}}}, {}, {}

            models = {(0, 'rho0'): 'm0', (2, 'rho0'): 'm0', (2, 'rho1'): 'm1', 'sha': {(0, 'rho0'): 'a', (2, 'rho0'): 'a', (2, 'rho1'): 'b'}}
            with patch.object(att, 'evaluate_pair', side_effect=fake), patch.object(att, 'write_pair'):
                results, rows, capacity = att.run_pairs(models, None, None, order, att.settings(P), 'cpu', None, log=lambda m: None)
            self.assertEqual(capacity['decision'], decision)
            self.assertEqual(list(results), names)
            self.assertEqual([a for s, a in calls if s > 0], [decision, decision])
        with self.assertRaises(ValueError):
            att.run_pairs(models, None, None, [['s2', 'rho0']], att.settings(P), 'cpu', None, log=lambda m: None)

    def test_standardize_uses_train_statistics(self):
        rng = np.random.default_rng(0)
        tr = (rng.standard_normal((50, 3, 7))*[[[2.], [5.], [0.]]] + [[[1.], [-3.], [4.]]]).astype('<f4')
        other = np.full((2, 3, 7), 1., dtype='<f4')
        a, b = att.standardize(tr, other)
        self.assertTrue(np.allclose(a.mean(axis=(0, 2)), 0, atol=1e-5))
        self.assertTrue(np.allclose(a.std(axis=(0, 2))[:2], 1, atol=1e-4))
        self.assertTrue(np.all(a[:, 2] == 0))  # Constant channel: std floor, no division by zero.
        self.assertAlmostEqual(float(b[0, 0, 0]), (1 - tr[:, 0].mean(dtype=np.float64))/tr[:, 0].std(dtype=np.float64), places=4)

    def test_fit_is_deterministic_and_keeps_best_epoch(self):
        att.configure()
        cfg = {**att.settings(P), 'max_epochs': 4, 'batch_size': 16}
        rng = np.random.default_rng(3)
        y = np.repeat(np.arange(3), 20).astype(np.int64)
        x = (rng.standard_normal((60, 4, 12)) + y[:, None, None]).astype('<f4')
        data = {'train_x': x, 'train_y': y, 'val_x': x[::2], 'val_y': y[::2]}
        arch = cfg['architectures']['base']
        runs = [att.fit(lambda: att.b_classifier((4, 12), 3, arch), 20261030, data, 'B', cfg, torch.device('cpu'), n=3) for _ in range(2)]
        self.assertEqual(runs[0][1]['history'], runs[1][1]['history'])
        self.assertTrue(all(torch.equal(runs[0][2][k], runs[1][2][k]) for k in runs[0][2]))
        best = max(runs[0][1]['history'], key=lambda h: (h['validation'], -h['epoch']))
        self.assertEqual((runs[0][1]['best_epoch'], runs[0][1]['validation']), (best['epoch'], best['validation']))


class ObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        att.configure()
        cls.model = att.load_rho(att.checkpoint_table(P)['rho0'])
        cls.x = np.random.default_rng(5).standard_normal((7, 360)).astype('<f4')

    def test_observed_is_the_registry_quantization_of_z_s(self):
        from quantization import dequantize_per_channel, quantize_per_channel
        z = att.head_output(self.model, self.x, 2)
        q, scale = quantize_per_channel(z)
        self.assertEqual(att.observed(self.model, self.x, 2).tobytes(), dequantize_per_channel(q, scale).tobytes())
        self.assertEqual(att.observed(self.model, self.x, 0).shape, (7, 1, 360))
        self.assertEqual(att.observed(self.model, self.x, 9).shape, (7, 32, 1))

    def test_batched_head_equals_one_beat_at_a_time(self):
        for s in (2, 5, 8):
            one = np.concatenate([att.head_output(self.model, self.x[i:i+1], s) for i in range(len(self.x))])
            self.assertEqual(att.head_output(self.model, self.x, s).tobytes(), one.tobytes())

    def test_golden_check_on_a_synthetic_package(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'golden').mkdir()
            x = self.x.reshape(-1, 1, 360)
            np.save(Path(d)/'golden/z_s0.npy', x)
            for s in (2, 8):
                np.save(Path(d)/f'golden/z_s{s}.npy', att.head_output(self.model, x, s))
            self.assertTrue(att.golden_check(self.model, d, [0, 2, 8])['bitwise_equal'])
            bad = np.load(Path(d)/'golden/z_s8.npy')
            bad[0, 0, 0] = np.nextafter(bad[0, 0, 0], np.float32(np.inf))
            np.save(Path(d)/'golden/z_s8.npy', bad)
            with self.assertRaises(ValueError):
                att.golden_check(self.model, d, [8])

    def test_rho1_loads_nopeek_weights(self):
        table = att.checkpoint_table(P)
        rho1 = att.load_rho(table['rho1']['s2'], rho1=True)
        a = dict(self.model.state_dict())
        self.assertTrue(any(not torch.equal(a[k], v) for k, v in rho1.state_dict().items()))
        bad = {**table['rho1']['s2'], 'epoch': 4}
        with self.assertRaises(ValueError):
            att.load_rho(bad, rho1=True)


class GateTests(unittest.TestCase):
    def test_trial_refused_without_authorization_before_any_load(self):
        boom = AssertionError('loaded before the authorization check')
        with patch.object(att, 'preflight', side_effect=boom), patch.object(att.pkg, 'arrays', side_effect=boom), \
                patch.object(att, 'load_rho', side_effect=boom), patch.object(att, 'read_metadata', side_effect=boom):
            with self.assertRaises(ValueError):
                att.run_trial(ROOT/'ml/configs/mitdb_m1_attack_protocol_v2.json', 'ml/data/never', None)
            with tempfile.TemporaryDirectory() as d:
                missing = Path(d)/'nothing.json'
                with self.assertRaises(ValueError):
                    att.run_trial(ROOT/'ml/configs/mitdb_m1_attack_protocol_v2.json', 'ml/data/never', missing)
        self.assertFalse((ROOT/'ml/data/never').exists())

    def test_authorization_binds_protocol_plan_and_review_file(self):
        declared = P['source_bindings'][att.REVIEW_EVIDENCE_KEY]
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d)/'plan.json'
            plan.write_text('{"x": 1}\n', encoding='utf-8')
            good = {'type': att.AUTH_TYPE, 'allow_trial': True, 'protocol_sha256': att.sha(ROOT/att.PROTOCOL),
                    'plan_manifest_sha256': att.sha(plan), 'approved_by': 'SV3', 'review_evidence': declared['raw_sha256'],
                    'review_evidence_path': declared['path']}
            path = Path(d)/'auth.json'
            path.write_text(json.dumps(good), encoding='utf-8')
            self.assertEqual(att.require_authorization(path, plan)['approved_by'], 'SV3')
            for change in ({'review_evidence_path': P['source_bindings']['sv1_review_20261109']['path']},
                           {'review_evidence': '0'*64}, {'plan_manifest_sha256': '0'*64}, {'allow_trial': False}, {'type': 'OTHER'}):
                path.write_text(json.dumps({**good, **change}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    att.require_authorization(path, plan)


class TrialWiringTests(unittest.TestCase):
    def test_run_trial_end_to_end_on_synthetic_arrays(self):
        """run_trial with the gate, preflight, arrays and golden check replaced by fixtures; real checkpoints, synthetic beats."""
        rows, x = att.synthetic_beats(np.random.default_rng(7), [101, 106, 108, 109], 80)
        n_train = 160  # Records 101 and 106 as 'train', 108 and 109 as 'val', as DS1 keeps whole records per split.
        arrays = {'train': (x[:n_train], None, rows[:n_train]), 'val': (x[n_train:], None, rows[n_train:])}
        counts = att.split_counts(att.time_split(rows, RULE), len(rows))
        cfg = {**att.settings(P), 'max_epochs': 1, 'resamples': 20}
        with tempfile.TemporaryDirectory(dir=ROOT/'ml/data') as d:
            plan = Path(d)/'plan.json'
            plan.write_text(json.dumps({'checkpoints': att.checkpoint_table(P), 'trial_order': [['s0', 'rho0'], ['s2', 'rho1']]}), encoding='utf-8')
            out = Path(d).relative_to(ROOT)/'trial'
            (Path(d)/'auth.json').write_text('{}\n', encoding='utf-8')  # The gate is replaced; the runner still hashes the file.
            with patch.object(att, 'require_authorization', return_value={'approved_by': 'SV3'}), \
                    patch.object(att, 'preflight', return_value={'counts': counts}), patch.object(att.pkg, 'arrays', return_value=arrays), \
                    patch.object(att, 'golden_check', return_value={'bitwise_equal': True}), patch.object(att, 'settings', return_value=cfg):
                result = att.run_trial(plan, out, Path(d)/'auth.json')
            self.assertEqual(result['status'], 'TRIAL_COMPLETED_REPORT_ONLY')
            self.assertEqual(result['N'], 4)
            self.assertFalse(result['DS2_opened'])
            self.assertEqual(result['caveat'], P['trial_week11_scope']['receipt_caveat'])
            pairs = [r['pair'] for r in result['table']]
            self.assertEqual(pairs[0], 's0-rho0-base')
            self.assertEqual(pairs[-1], 's2-rho1')
            r = json.loads((ROOT/out/'s2-rho1.json').read_text(encoding='utf-8'))
            self.assertEqual(r['checkpoint_sha256'], att.checkpoint_table(P)['rho1']['s2']['sha256'])
            self.assertEqual(r['observed_shape'], [16, 180])
            self.assertEqual(len(r['B_naive']['seeds']), 3)
            ident = json.loads((ROOT/out/'trial-identity.json').read_text(encoding='utf-8'))
            self.assertEqual((ident['cudnn_allow_tf32'], ident['matmul_allow_tf32'], ident['DS2_opened']), (False, False, False))


class PrecisionTests(unittest.TestCase):
    def test_set_precision_turns_tf32_off(self):
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cuda.matmul.allow_tf32 = True
        state = att.set_precision()
        self.assertEqual((state['cudnn_allow_tf32'], state['matmul_allow_tf32'], state['deterministic_algorithms']), (False, False, True))
        self.assertFalse(torch.backends.cudnn.allow_tf32 or torch.backends.cuda.matmul.allow_tf32)


if __name__ == '__main__':
    unittest.main(verbosity=2)
