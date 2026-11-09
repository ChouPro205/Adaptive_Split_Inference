"""DS2 report script: validation dry run, partition rows, statistics and the DS2 gate. Never opens DS2."""
import json
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import evaluate_m1_v4_ds2 as ds2

ROOT = ds2.ROOT


def spy_loads(opened):
    real = np.load
    def spy(path, *a, **k):
        opened.append(Path(path).name)
        return real(path, *a, **k)
    return spy


class DryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT/'ml/data', prefix='test-ds2-')
        cls.out = Path(cls.tmp.name)/'dry'
        cls.opened = []
        with patch.object(ds2.np, 'load', spy_loads(cls.opened)):
            cls.result = ds2.dry_run(cls.out, 'cpu')
        cls.summary = json.loads((cls.out/'summary.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reproduces_three_locked_confusions(self):
        self.assertEqual(self.result['status'], 'VALIDATION_CONFUSION_REPRODUCED_FOR_3_C5_CHECKPOINTS')
        self.assertEqual(len(self.result['matched']), 3)

    def test_no_ds2_file_opened(self):
        self.assertTrue(self.opened)
        self.assertFalse([n for n in self.opened if n.startswith('test')])

    def test_predictions_have_record_ids_for_every_beat_and_seed(self):
        lines = (self.out/'predictions.csv').read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[0].split(',')[:4], ['seed', 'role', 'row_index', 'record_id'])
        self.assertEqual(len(lines)-1, 3*9523)
        self.assertEqual({l.split(',')[3] for l in lines[1:]}, {'118', '119', '205', '223'})

    def test_device_tf32_and_deployment_recorded(self):
        self.assertEqual(self.summary['environment']['device'], 'cpu')
        self.assertIs(self.summary['environment']['cudnn_allow_tf32'], False)
        self.assertEqual(self.summary['deployment_reported_separately']['role'], 'deployment')

    def test_statistics_are_mean_and_sample_sd(self):
        stats = self.summary['statistics']['validation_all']['macro_f1_NSVF_fixed4']
        values = list(stats['per_seed'].values())
        self.assertAlmostEqual(stats['mean'], statistics.fmean(values), places=15)
        self.assertAlmostEqual(stats['sd_ddof1'], float(np.std(values, ddof=1)), places=12)

    def test_existing_output_refused(self):
        with self.assertRaises(ValueError):
            ds2.dry_run(self.out, 'cpu')


class RowTests(unittest.TestCase):
    def test_rows_partition_and_per_record(self):
        rows = [{'record_id': r} for r in ('1', '1', '2', '3')]
        y, pred = np.array([0, 1, 2, 0]), np.array([0, 0, 2, 1])
        result, keep = ds2.report(y, pred, rows, '1', ['main', 'all'])
        self.assertEqual(keep.tolist(), [False, False, True, True])
        self.assertEqual(result['all']['samples'], 4)
        self.assertEqual(result['main']['samples'], 2)
        self.assertEqual(result['all']['S_beats_per_record'], {'1': 1, '2': 0, '3': 0})
        self.assertEqual(result['all']['per_record_confusion_descriptive']['3'][0][1], 1)

    def test_excluded_record_must_split(self):
        rows = [{'record_id': '1'}]*3
        with self.assertRaises(ValueError):
            ds2.report(np.array([0, 0, 0]), np.array([0, 0, 0]), rows, '9', ['main', 'all'])


class GateTests(unittest.TestCase):
    def test_ds2_refused_without_authorization_before_any_load(self):
        opened = []
        with patch.object(ds2.np, 'load', spy_loads(opened)):
            with self.assertRaises(ValueError):
                ds2.ds2(None)
        self.assertEqual(opened, [])

    def test_authorization_must_bind_this_script_and_xmodel_lock(self):
        base = {'type': 'M1_V4_DS2_FP32_AUTHORIZATION', 'checkpoint_lock_sha256': ds2.pkg.LOCK_SHA,
                'script_sha256': ds2.sha(Path(ds2.__file__)), 'xmodel_lock_sha256': 'a'*64, 'review_evidence': 'b'*64,
                'approved_by': 'SV3', 'device': 'cpu'}
        with tempfile.TemporaryDirectory() as d:
            for bad in ({'script_sha256': '0'*64}, {'xmodel_lock_sha256': ''}, {'checkpoint_lock_sha256': '0'*64}, {'type': 'OTHER'},
                        {'device': 'gpu'}):
                path = Path(d)/'a.json'
                path.write_text(json.dumps({**base, **bad}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    ds2.require_authorization(path)
            path.write_text(json.dumps(base), encoding='utf-8')
            self.assertEqual(ds2.require_authorization(path)['type'], 'M1_V4_DS2_FP32_AUTHORIZATION')


if __name__ == '__main__':
    unittest.main(verbosity=2)
