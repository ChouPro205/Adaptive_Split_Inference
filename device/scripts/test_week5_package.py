"""Read-only production package check plus tampering tests on temporary copies."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from week5_common import ROOT, source_hashes, firmware_binding, write_json
from verify_week5_package import package_metadata, verify_artifacts

class Tests(unittest.TestCase):
    def test_actual_package(self):
        self.assertIs(verify_artifacts(self.prepared), self.prepared)

    def test_artifact_tamper(self):
        for name in ('elf','hex','zip'):
            with self.subTest(artifact=name), tempfile.TemporaryDirectory(prefix='week5-package-negative-') as temp:
                data = copy.deepcopy(self.prepared)
                source = Path(data['artifacts'][name]['path'])
                target = Path(temp) / source.name
                raw = bytearray(source.read_bytes()); raw[-1] ^= 1
                target.write_bytes(raw)
                data['artifacts'][name]['path'] = str(target)
                with self.assertRaises(ValueError): verify_artifacts(data)

    def test_source_binding_and_application_tamper(self):
        data = copy.deepcopy(self.prepared)
        data['firmware_binding']['firmware_id'] = '0'*64
        with self.assertRaises(ValueError): verify_artifacts(data)
        data = copy.deepcopy(self.prepared)
        data['source_sha256']['device/week5/quantization.c'] = '0'*64
        with self.assertRaises(ValueError): verify_artifacts(data)
        data = copy.deepcopy(self.prepared)
        data['application']['sha256'] = '0'*64
        with self.assertRaises(ValueError): verify_artifacts(data)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    Tests.prepared = {**package_metadata(a.build_report), 'source_sha256':source_hashes(), 'firmware_binding':firmware_binding()}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    write_json(a.output, {'status':'PASS' if result.wasSuccessful() else 'FAIL', 'scope':'OFFLINE_PACKAGE_ONLY',
        'tests_run':result.testsRun, 'source_sha256':source_hashes()})
    raise SystemExit(0 if result.wasSuccessful() else 1)
