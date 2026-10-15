"""Receipts bind every tracked source; drift, new sources and tampering are rejected."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from week5_delivery_scope_v2 import sha
from verify_week5_delivery_v2 import check_receipt

SOURCES = {'ml/scripts/gate.py': 'print("gate")\n', 'device/src/kernel.c': 'int kernel;\n',
           'device/scripts/build.ps1': 'Write-Output 1\r\n', 'contracts/rule.md': 'rule\n',
           'ml/configs/config.json': '{}\n', 'ml/manifests/scope.json': '{}\n'}
UNBOUND = {'docs/report.md': 'report\n', 'results/table.csv': 'a,b\n'}


class ReceiptScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.evidence = Path(self.tmp.name) / 'evidence'
        self.evidence.mkdir()
        for name, text in {**SOURCES, **UNBOUND}.items():
            self.write(name, text)
        self.git('init', '--quiet')
        self.git('config', 'core.autocrlf', 'false')
        self.commit('snapshot')
        self.record('gate', ['python', '-B', 'ml/scripts/gate.py'])
        self.record('gate_O', ['python', '-B', '-O', 'ml/scripts/gate.py'])

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def commit(self, message):
        self.git('add', '-A')
        self.git('-c', 'user.name=Receipt Test', '-c', 'user.email=receipt-test@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', message)

    def record(self, name, command):
        # Same source selection as ml/scripts/run_week5_logged_v2.py.
        tracked = self.git('ls-files').splitlines()
        bound = [n for n in tracked if n.endswith(('.py', '.c', '.h', '.ps1'))
                 or n.startswith(('ml/configs/', 'ml/manifests/', 'contracts/'))]
        for stream in ('stdout', 'stderr'):
            (self.evidence / f'{name}.{stream}.txt').write_bytes(b'log\r\n')
        record = {'command': command, 'exit_code': 0,
                  'stdout_sha256': sha(self.evidence / f'{name}.stdout.txt'),
                  'stderr_sha256': sha(self.evidence / f'{name}.stderr.txt'),
                  'source_files_sha256': {n: sha(self.root / n) for n in bound},
                  'source_git_commit': self.git('rev-parse', 'HEAD').strip(),
                  'source_tree': self.git('rev-parse', 'HEAD^{tree}').strip()}
        (self.evidence / f'{name}.command.json').write_text(json.dumps(record), encoding='utf-8')

    def check(self, name='gate'):
        return check_receipt(self.evidence, name, 'ml/scripts/gate.py', self.root)

    def test_intact_snapshot_and_unbound_files_pass(self):
        self.assertEqual(self.check()['scope'], 'FRESH')
        self.assertEqual(self.check('gate_O')['scope'], 'FRESH')
        self.write('docs/report.md', 'edited report\n')
        self.commit('docs only')
        self.assertEqual(self.check()['scope'], 'FRESH')

    def test_bound_source_drift_detected(self):
        for name in SOURCES:
            original = (self.root / name).read_bytes()
            for changed in (original + b'#', original.replace(b'\n', b'\r\n') if b'\r' not in original
                            else original.replace(b'\r\n', b'\n')):
                (self.root / name).write_bytes(changed)
                with self.assertRaisesRegex(ValueError, 'Tested source drift'):
                    self.check()
            (self.root / name).write_bytes(original)
        self.check()

    def test_new_tracked_source_requires_new_receipt(self):
        for name in ('edge/new_tool.py', 'device/src/new.h', 'contracts/new_contract.md', 'ml/configs/new.json'):
            self.write(name, 'new\n')
            self.commit(f'add {name}')
            with self.assertRaisesRegex(ValueError, 'Incomplete source provenance'):
                self.check()
            self.git('rm', '--quiet', name)
            self.commit(f'remove {name}')
        self.check()

    def test_missing_bound_source_is_not_pass(self):
        (self.root / 'device/src/kernel.c').unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()

    def test_log_exit_and_mode_tampering_rejected(self):
        (self.evidence / 'gate.stdout.txt').write_bytes(b'log\n')
        with self.assertRaisesRegex(ValueError, 'Log bytes changed'):
            self.check()
        self.record('gate', ['python', '-B', 'ml/scripts/gate.py'])
        record = json.loads((self.evidence / 'gate.command.json').read_text(encoding='utf-8'))
        for change, message in (({'exit_code': 1}, 'Fresh gate failed'),
                                ({'command': ['python', '-B', '-O', 'ml/scripts/gate.py']}, 'Wrong gate command'),
                                ({'command': ['python', '-B', 'ml/scripts/other.py']}, 'Wrong gate command')):
            (self.evidence / 'gate.command.json').write_text(json.dumps({**record, **change}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, message):
                self.check()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReceiptScopeTests))
    sys.exit(0 if result.wasSuccessful() else 1)
