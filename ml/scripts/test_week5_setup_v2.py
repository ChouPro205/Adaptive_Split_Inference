"""Protect both receiver headers before generating authenticated missing files."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from setup_week5_delivery_v2 import HEADERS, prepare_headers, setup
from week5_delivery_scope_v2 import SCOPE, ROOT, write_new


class HeaderPreservationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.payloads = {name: ('/* ' + name + ' */\n').encode() for name in HEADERS}
        self.scope = {'files': [dict(path=name, size_bytes=len(data),
                                    sha256=hashlib.sha256(data).hexdigest())
                                for name, data in self.payloads.items()]}

    def put(self, name, data=None):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.payloads[name] if data is None else data)
        return path

    def generate(self, argv, **kwargs):
        directory = Path(argv[argv.index('--generated-dir')+1])
        self.assertNotEqual(directory.resolve(), (self.root/'device/generated').resolve())
        for name, data in self.payloads.items():
            (directory/Path(name).name).write_bytes(data)

    def test_both_missing_are_authenticated_before_install(self):
        with patch('setup_week5_delivery_v2.subprocess.run', side_effect=self.generate) as generator:
            prepare_headers(self.root, self.scope)
        generator.assert_called_once()
        for name, data in self.payloads.items():
            self.assertEqual((self.root/name).read_bytes(), data)

    def test_each_missing_preserves_other_header_and_timestamp(self):
        for missing in HEADERS:
            with self.subTest(missing=missing):
                for name in HEADERS:
                    (self.root/name).unlink(missing_ok=True)
                present = next(name for name in HEADERS if name != missing)
                path = self.put(present)
                modified = path.stat().st_mtime_ns
                with patch('setup_week5_delivery_v2.subprocess.run', side_effect=self.generate):
                    prepare_headers(self.root, self.scope)
                self.assertEqual(path.stat().st_mtime_ns, modified)
                for name, data in self.payloads.items():
                    self.assertEqual((self.root/name).read_bytes(), data)

    def test_correct_headers_skip_generator_and_preserve_timestamps(self):
        times = {name: self.put(name).stat().st_mtime_ns for name in HEADERS}
        with patch('setup_week5_delivery_v2.subprocess.run') as generator:
            prepare_headers(self.root, self.scope)
        generator.assert_not_called()
        for name, data in self.payloads.items():
            self.assertEqual((self.root/name).read_bytes(), data)
            self.assertEqual((self.root/name).stat().st_mtime_ns, times[name])

    def test_each_changed_header_fails_before_setup_writes(self):
        scope = dict(self.scope, archives=[{'path':'must-not-write.zip'}])
        write_new(self.root/SCOPE.relative_to(ROOT), scope)
        for changed in HEADERS:
            original = self.payloads[changed]
            for data in (original+b'/* marker */', b'X'+original[1:], original.replace(b'\n',b'\r\n')):
                with self.subTest(header=changed, payload=data):
                    for name in HEADERS:
                        self.put(name)
                    self.put(changed, data)
                    before = {name:(self.root/name).read_bytes() for name in HEADERS}
                    with patch('setup_week5_delivery_v2.subprocess.run') as generator:
                        with self.assertRaisesRegex(ValueError, 'Existing header changed'):
                            setup(self.root/'absent-cache', self.root)
                    generator.assert_not_called()
                    self.assertFalse((self.root/'must-not-write.zip').exists())
                    self.assertEqual(before, {name:(self.root/name).read_bytes() for name in HEADERS})

    def test_bad_candidate_for_either_header_installs_neither(self):
        for changed in HEADERS:
            def corrupt(argv, **kwargs):
                self.generate(argv, **kwargs)
                directory = Path(argv[argv.index('--generated-dir')+1])
                (directory/Path(changed).name).write_bytes(b'bad candidate')
            with self.subTest(header=changed), patch('setup_week5_delivery_v2.subprocess.run', side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, 'Generated header differs'):
                    prepare_headers(self.root, self.scope)
                self.assertTrue(all(not (self.root/name).exists() for name in HEADERS))

    def test_header_created_during_generation_is_not_overwritten(self):
        for changed in HEADERS:
            def appear(argv, **kwargs):
                self.generate(argv, **kwargs)
                self.put(changed, b'/* appeared concurrently */')
            with self.subTest(header=changed), patch('setup_week5_delivery_v2.subprocess.run', side_effect=appear):
                with self.assertRaisesRegex(ValueError, 'Existing header changed'):
                    prepare_headers(self.root, self.scope)
                self.assertEqual((self.root/changed).read_bytes(), b'/* appeared concurrently */')
                (self.root/changed).unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
