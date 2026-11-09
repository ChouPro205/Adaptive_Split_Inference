"""Package A builder: rules, scope and tamper checks. Builds small packages under ignored ml/data; no DS2."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import package_m1_v4_a as pkg

ROOT = pkg.ROOT


class RuleTests(unittest.TestCase):
    def test_calibration_rule_is_sv2_even_spacing(self):
        for n, count in ((41472, 1000), (41472, 8), (41472, 1), (5, 9)):
            expected = np.unique(np.linspace(0, n-1, min(count, n)).round().astype(np.int64)).tolist()
            got = pkg.calibration_indices(n, count)
            self.assertEqual(got, expected)
            self.assertTrue(all(0 <= i < n for i in got) and got == sorted(set(got)))
        for bad in (0, -1, 2.0):
            with self.assertRaises(ValueError):
                pkg.calibration_indices(100, bad)

    def test_comparison_rule_sorts_numeric_record_rpeak_lead(self):
        rows = [{'record_id': r, 'r_peak_sample': p, 'lead_name': 'MLII'} for r, p in
                (('230', '5'), ('101', '900'), ('101', '80'), ('99', '7'))] * 6
        order = pkg.comparison_indices(rows)
        self.assertEqual(len(order), 20)
        keys = [(int(rows[i]['record_id']), int(rows[i]['r_peak_sample'])) for i in order]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(keys[0], (99, 7))


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT/'ml/data', prefix='test-package-a-')
        cls.package = Path(cls.tmp.name)/'package'
        opened = []
        real_load = np.load
        def spy(path, *a, **k):
            opened.append(Path(path).name)
            return real_load(path, *a, **k)
        with patch.object(pkg.np, 'load', spy):
            pkg.build(cls.package, 8)
        cls.opened = opened

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def copy(self):
        target = Path(tempfile.mkdtemp(dir=self.tmp.name))/'copy'
        shutil.copytree(self.package, target)
        return target

    def test_verify_accepts_built_package(self):
        r = pkg.verify(self.package)
        self.assertTrue(r['status'].startswith('PACKAGE_A_VERIFIED_'))

    def test_no_ds2_array_opened(self):
        self.assertTrue(self.opened)
        self.assertFalse([n for n in self.opened if n.startswith('test')])

    def test_golden_and_calibration_are_train_only(self):
        for name in ('samples.csv', 'calibration/samples.csv'):
            lines = (self.package/name).read_text(encoding='utf-8').splitlines()[1:]
            self.assertTrue(lines and all(',train,' in line and 'train_metadata.csv' in line for line in lines))
        self.assertEqual(np.load(self.package/'calibration/z_s0.npy').shape, (8, 1, 360))

    def test_tampered_golden_rejected(self):
        p = self.copy()
        z = np.load(p/'golden/z_s2.npy'); z[0, 0, 0] += 1
        np.save(p/'golden/z_s2.npy', z)
        with self.assertRaises(ValueError):
            pkg.verify(p)

    def test_tampered_header_rejected(self):
        p = self.copy()
        h = p/'firmware/head_parameters.h'
        h.write_bytes(h.read_bytes().replace(b'0x1.', b'0x1.0', 1))
        with self.assertRaises(ValueError):
            pkg.verify(p)

    def test_other_checkpoint_rejected(self):
        p = self.copy()
        lock = pkg.read_json(ROOT/pkg.LOCK)
        other = next(c for c in lock['checkpoints'] if c['role'] != 'deployment')
        shutil.copyfile(ROOT/other['path'], p/'model/checkpoint.pt')
        with self.assertRaises(ValueError):
            pkg.verify(p)

    def test_existing_or_outside_output_refused(self):
        with self.assertRaises(ValueError):
            pkg.build(self.package, 8)
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):
                pkg.build(Path(outside)/'package', 8)


class BindingTests(unittest.TestCase):
    def test_lock_hash_bound(self):
        with patch.object(pkg, 'LOCK_SHA', '0'*64):
            with self.assertRaises(ValueError):
                pkg.locked()

    def test_test_split_in_binding_refused(self):
        _, _, plan, _ = pkg.locked()
        plan['binding']['data_files']['test_main_X.npy'] = {'sha256': '0'*64}
        with self.assertRaises(ValueError):
            pkg.arrays(plan)


if __name__ == '__main__':
    unittest.main(verbosity=2)
