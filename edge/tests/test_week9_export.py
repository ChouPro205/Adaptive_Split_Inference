"""Publication guards and optional read-only replay of real Week 9 inputs."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('week9_export', ROOT / 'edge/export_week9_evidence.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class Guards(unittest.TestCase):
    def test_output_existing_is_rejected_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                exporter.export(Path(tmp) / 'missing', Path(tmp), '2026-11-09')

    def test_pointer_cannot_escape_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'session'
            root.mkdir()
            with self.assertRaises(ValueError):
                exporter.inside(root, root / '../outside')

    def test_source_inventory_detects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.py'
            source.write_text('HOST_FIXTURE_ONLY\n')
            (root / 'sha256sum_prepare.txt').write_text(exporter.sha(source) + '  source.py\n')
            exporter.verify_prepared(root)
            source.write_text('changed\n')
            with self.assertRaises(ValueError):
                exporter.verify_prepared(root)

    def test_bad_w10_archive_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'gui_review_windows.zip'
            with zipfile.ZipFile(archive, 'x') as z:
                z.writestr('HOST_FIXTURE_ONLY', 'not measurement evidence')
            (root / 'gui_review_windows.zip.sha256.txt').write_text('0' * 64 + '  ' + archive.name + '\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                exporter.verify_review_zip(root, root / 'analysis')

    def test_real_replay_if_authenticated_session_is_available(self):
        pointer = ROOT / 'edge/build_vai25/ket_qua_hien_tai/week9/phien_dang_dung.txt'
        if not pointer.exists():
            self.skipTest('Original session is stored outside Git')
        week = Path(pointer.read_text().strip())
        native_pointer = week / 'do_tre_windows_phien.txt'
        if not native_pointer.exists():
            self.skipTest('No restored native-Windows acquisition')
        session = Path(native_pointer.read_text().strip())
        saved = session / 'analysis_hien_tai.txt'
        if not saved.exists():
            self.skipTest('Acquisition has not been analyzed')
        before = {p: exporter.sha(p) for p in session.rglob('*') if p.is_file()
                  and 'venv' not in p.parts and '__pycache__' not in p.parts}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'publication'
            with contextlib.redirect_stdout(io.StringIO()):
                exporter.export(session, output, '2026-11-09')
            summary = json.loads((output / 'summary.json').read_text())
            self.assertEqual(summary['runs']['idle']['matching']['sent'], 901)
            self.assertEqual(summary['runs']['varying']['matching']['received'], 1501)
            for line in (output / 'sha256sum_export.txt').read_text().splitlines():
                digest, name = line.split('  ', 1)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            text = '\n'.join(p.read_text() for p in output.glob('*.json'))
            self.assertNotIn('/home/', text)
            self.assertNotIn('C:\\Users\\', text)
            for path, digest in before.items():
                self.assertEqual(exporter.sha(path), digest)


if __name__ == '__main__':
    unittest.main()
