"""Native acquisition control tests with explicit host-only fixtures."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'edge/server/week9'))
import native_receiver as native


class NativeTests(unittest.TestCase):
    def test_preflight_rejects_bad_clock_rate_and_excess_uncertainty(self):
        m = native.measurement()
        probes = [dict(s1_ns=i * 10**9, s4_ns=i * 10**9 + 3_000_000,
            b2_ns=i * 10**9 + 1_000_000, b3_ns=i * 10**9 + 1_050_000,
            clock_id='HOST_FIXTURE', hostname='mock_board', clock={'resolution_ns': 1})
            for i in range(31)]
        samples = [dict(perf_ns=0, wall_ns=0), dict(perf_ns=30 * 10**9, wall_ns=30 * 10**9)]
        self.assertEqual(native.assess(m, probes, samples)['status'], 'READY_FOR_CAPTURE_NOT_ACCEPTANCE')
        with self.assertRaisesRegex(ValueError, 'TOO_WIDE'):
            native.assess(m, probes, samples, .01)
        samples[-1]['perf_ns'] = int(30 * 1.026 * 10**9)
        with self.assertRaisesRegex(ValueError, 'RATE_MISMATCH'):
            native.assess(m, probes, samples)

    def test_receiver_preserves_self_gateway_role_and_local_broker(self):
        m = native.measurement()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m.save(root / 'windows_config.json', dict(receiver_id='GW_TRUNG', role='gateway',
                network_label='HOST_FIXTURE_ONLY', broker_local_port=1891, clock_local_port=1906))
            pre = root / 'captures/preflight'
            pre.mkdir(parents=True)
            m.save(pre / 'preflight.json', dict(status='READY_FOR_CAPTURE_NOT_ACCEPTANCE',
                hostname=native.platform.node(), source_sha256=m.sha(native.__file__), clock_id='mock'))
            m.seal(pre)
            (root / 'last_preflight.txt').write_text(str(pre))
            def capture(args):
                self.assertEqual((args.receiver_id, args.role, args.port), ('GW_TRUNG', 'gateway', 1891))
                self.assertEqual(args.clock_port, 1906)
                args.output.mkdir()
                m.save(args.output / 'receiver.json', dict(clock_id='mock'))
            with patch.object(native, 'measurement', return_value=m), patch.object(m, 'receive', side_effect=capture):
                with contextlib.redirect_stdout(io.StringIO()):
                    native.receive(root, 'idle')

    def test_stop_does_not_mutate_an_already_sealed_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / 'captures/idle'
            capture.mkdir(parents=True)
            (root / 'last_idle.txt').write_text(str(capture))
            with contextlib.redirect_stdout(io.StringIO()):
                native.stop(root, 'idle')
            self.assertTrue((root / 'stop_idle.flag').exists())
            (capture / 'sha256sum_results.txt').write_text('HOST_FIXTURE_ONLY')
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with contextlib.redirect_stdout(io.StringIO()):
                native.stop(root, 'idle')
            for path, value in before.items():
                self.assertEqual(path.read_bytes(), value)

    def test_export_is_local_and_repeated_names_preserve_zip_extension(self):
        m = native.measurement()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('oneway.py', 'native_receiver.py'):
                shutil.copyfile(ROOT / 'edge/server/week9' / name, root / name)
            m.save(root / 'windows_config.json', dict(receiver_id='GW_TRUNG', role='gateway'))
            (root / 'sha256sum_windows.txt').write_text('HOST_FIXTURE_ONLY')
            for kind in ('idle', 'varying', 'preflight'):
                folder = root / 'captures' / kind
                folder.mkdir(parents=True)
                name = 'preflight.json' if kind == 'preflight' else 'receiver.json'
                m.save(folder / name, dict(status='STOPPED_BY_OPERATOR', scope='HOST_FIXTURE_ONLY'))
                m.seal(folder)
                (root / ('last_' + kind + '.txt')).write_text(str(folder))
            with patch.object(native, 'measurement', return_value=m), contextlib.redirect_stdout(io.StringIO()):
                native.export(root)
                native.export(root)
            archive = Path((root / 'last_export.txt').read_text().strip())
            self.assertEqual(archive.name, 'ket_qua_windows_lan_2.zip')
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertIn('source/windows_config.json', z.namelist())
                self.assertFalse(any('/venv/' in name for name in z.namelist()))


if __name__ == '__main__':
    unittest.main()
