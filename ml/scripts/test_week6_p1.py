"""Real-package acceptance and corruption tests. Fixtures never count as official tensors."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from week6_p1 import (authenticate_package, digest, inventory, metadata, profile, q_and_scale,
                     read, verify, SELECTION, authenticated_inputs, REGISTRY, APPROVAL, GOLDENS)

PACKAGE = None
EXPECTED = None


class SourceTests(unittest.TestCase):
    def test_selection_exactly_50_distinct_and_all_splits(self):
        self.assertEqual(len(SELECTION), 50)
        self.assertEqual(len(set(SELECTION)), 50)
        self.assertEqual({s for s, i in SELECTION}, set(range(11)))

    def test_real_input_bytes_and_NC_adapters(self):
        _, registry, entries = authenticated_inputs(GOLDENS / 'manifest.json', REGISTRY, APPROVAL)
        for index, (s, i) in enumerate(SELECTION):
            e = entries[s, i]; p = profile(registry, s)
            qb = (GOLDENS / e['int8_path']).read_bytes()
            sb = (GOLDENS / e['scale_path']).read_bytes()
            q, scale = q_and_scale(qb, sb, p, e)
            self.assertEqual(q.tobytes(), qb)
            self.assertEqual(scale.tobytes(), sb)
            self.assertEqual(metadata(e, index, registry)['wire_split_id'], 256 + s)
            if s >= 9:
                self.assertEqual(q.shape, (1, 32 if s == 9 else 5, 1))


class RealPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='week6-package-negative-')
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / 'relocated-package'
        shutil.copytree(PACKAGE, self.package)

    def refresh(self):
        manifest = read(self.package / 'manifest.json')
        manifest['files'] = inventory(self.package)
        raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
        (self.package / 'manifest.json').write_bytes(raw)
        return digest(raw)

    def change_metadata(self, mutate):
        value = read(self.package / 'vectors.json')
        mutate(value)
        (self.package / 'vectors.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')
        return self.refresh()

    def first_file(self, kind):
        return self.package / read(self.package / 'vectors.json')['vectors'][0]['files'][kind]

    def test_complete_relocated_package_C_and_Python(self):
        r = verify(self.package, EXPECTED, os.environ.get('CC', 'gcc'))
        self.assertEqual((r['vectors'], r['python_roundtrips'], r['C_Python_protect_matches'], r['C_roundtrips']),
                         (50, 50, 50, 50))
        self.assertGreater(r['transformed_0x80_vectors'], 0)

    def test_missing_file(self):
        self.first_file('nonce').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            authenticate_package(self.package, EXPECTED)

    def test_modified_file(self):
        f = self.first_file('transformed'); f.write_bytes(b'X' + f.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'inventory'):
            authenticate_package(self.package, EXPECTED)

    def test_extra_nested_manifest_is_not_excluded(self):
        (self.package / 'inputs/manifest.json').write_text('{}', 'utf-8')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            authenticate_package(self.package, EXPECTED)

    def test_wrong_external_anchor(self):
        with self.assertRaisesRegex(ValueError, 'anchor'):
            authenticate_package(self.package, '0' * 64)

    def test_duplicate_sequence_even_with_rehashed_manifest(self):
        h = self.change_metadata(lambda d: d['vectors'][1].update(sequence=1))
        with self.assertRaisesRegex(ValueError, 'metadata'):
            authenticate_package(self.package, h)

    def test_logical_split_id_not_wire_id(self):
        h = self.change_metadata(lambda d: d['vectors'][0].update(wire_split_id=0))
        with self.assertRaisesRegex(ValueError, 'metadata'):
            authenticate_package(self.package, h)

    def test_NC_metadata_rejected_on_wire(self):
        def change(d):
            next(v for v in d['vectors'] if v['split_point_s'] == 9)['shape'] = [1, 32]
        h = self.change_metadata(change)
        with self.assertRaisesRegex(ValueError, 'metadata'):
            authenticate_package(self.package, h)

    def test_changed_source_manifest_not_trusted(self):
        f = self.package / 'inputs/quantization20.manifest.json'
        f.write_bytes(f.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Quantization manifest anchor'):
            authenticate_package(self.package, self.refresh())

    def test_q_minus128_cannot_be_relabelled_as_real(self):
        f = self.first_file('q'); f.write_bytes(b'\x80' + f.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'Original q hash'):
            verify(self.package, self.refresh(), os.environ.get('CC', 'gcc'))

    def test_changed_scale_cannot_be_reestimated(self):
        f = self.first_file('scale'); f.write_bytes(b'\x00\x3c')
        with self.assertRaisesRegex(ValueError, 'FP16 scale hash'):
            verify(self.package, self.refresh(), os.environ.get('CC', 'gcc'))

    def test_nonce_zero_rejected_after_integrity_passes(self):
        f = self.first_file('nonce'); f.write_bytes(f.read_bytes()[:4] + bytes(8))
        with self.assertRaisesRegex(ValueError, 'Nonce differs'):
            verify(self.package, self.refresh(), os.environ.get('CC', 'gcc'))

    def test_transformed_mutation_rejected_after_integrity_passes(self):
        f = self.first_file('transformed'); raw = f.read_bytes(); f.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        with self.assertRaisesRegex(ValueError, 'Python protect/roundtrip'):
            verify(self.package, self.refresh(), os.environ.get('CC', 'gcc'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--expected-manifest-sha256')
    parser.add_argument('--source-only', action='store_true')
    args, remaining = parser.parse_known_args()
    PACKAGE, EXPECTED = args.package, args.expected_manifest_sha256
    if args.source_only:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SourceTests)
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    parser.error('--package and --expected-manifest-sha256 required') if not (PACKAGE and EXPECTED) else None
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
