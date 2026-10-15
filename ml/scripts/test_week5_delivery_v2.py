"""Reject missing/tampered required assets, path escapes and strict boundaries."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from week5_delivery_scope_v2 import inventory, sha, safe_path
from evaluate_week5_v2 import strict_accuracy_gate


class DeliveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/'checkpoint.pt'
        self.path.write_bytes(b'frozen dependency\r\n')
        self.scope = {'schema':'week5-portable-delivery/2', 'files':[
            {'path':'checkpoint.pt','sha256':sha(self.path),'size_bytes':self.path.stat().st_size}]}

    def test_manifest_scope_does_not_require_author_extras(self):
        (self.root/'old-repro.zip').write_bytes(b'outside portable scope')
        self.assertEqual(set(inventory(self.root, self.scope)), {'checkpoint.pt'})

    def test_historical_p1_keeps_sv1_raw_source_binding(self):
        # SV1 reuses accepted C accuracy only with this exact historical source.
        historical = Path(__file__).with_name('test_week5_p1.py')
        self.assertEqual(hashlib.sha256(historical.read_bytes()).hexdigest(),
                         'ad6be8d9b126448b2b1179cd6f9eb2da007c2c87bbb13f7869b5ad0b8ccf2cac')

    def test_portable_p1_uses_versioned_result_contract(self):
        from verify_week5_delivery_v2 import REQUIRED
        from test_week5_p1_v2 import provenance, run
        self.assertEqual(REQUIRED['p1'], 'ml/scripts/test_week5_p1_v2.py')
        sources = provenance('P1 v2 provenance regression')['source_files_sha256']
        self.assertIn('ml/scripts/test_week5_p1_v2.py', sources)
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            run(10000, self.path)
        self.assertEqual(self.path.read_bytes(), b'frozen dependency\r\n')
        output = self.root/'new-p1.json'
        with self.assertRaisesRegex(ValueError, '10,000'):
            run(9999, output)
        self.assertFalse(output.exists())

    def test_required_missing_is_failure(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing required'):
            inventory(self.root, self.scope)

    def test_raw_newline_and_same_size_tampering_fail(self):
        for payload in (b'frozen dependency\n', b'Frozen dependency\r\n'):
            self.path.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'dependency changed'):
                inventory(self.root, self.scope)

    def test_duplicate_and_unsafe_scope_fail(self):
        duplicate = copy.deepcopy(self.scope)
        duplicate['files'] *= 2
        with self.assertRaises(ValueError):
            inventory(self.root, duplicate)
        for name in ('../checkpoint.pt','/checkpoint.pt','C:/checkpoint.pt','a\\b','a//b'):
            with self.assertRaises(ValueError):
                safe_path(self.root, name)

    def test_half_point_boundary_and_full_count(self):
        self.assertFalse(strict_accuracy_gate(1000,995,1000))
        self.assertTrue(strict_accuracy_gate(1000,996,1000))
        self.assertTrue(strict_accuracy_gate(8393,8388,8544))

    def test_accuracy_coverage_and_count_rejection(self):
        import csv
        from verify_week5_delivery_v2 import check_accuracy
        for n, fp, q in ((1000,1000,995),(8543,8393,8388),(8544,8393,8350)):
            rows = [dict(split_point_s=s,num_samples=n,correct_fp32=fp,correct_int8_fp16=q,gate_status='PASS') for s in range(11)]
            with (self.root/'accuracy.csv').open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
            with self.assertRaisesRegex(ValueError, 'strict accuracy'):
                check_accuracy(self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
