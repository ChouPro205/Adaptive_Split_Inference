"""Batch failure isolation checks; fixtures do not certify Vitis AI or KV260."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('week4', Path(__file__).resolve().parents[1] / 'build_and_audit_models.py')
week4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(week4)


class BatchTests(unittest.TestCase):
    def test_failed_split_does_not_stop_next_split_or_compile_failed_split(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            calls = []

            def stage(command, log):
                calls.append(str(log.relative_to(out)))
                code = 7 if log.parent.name == 's2' and log.name == 'calib.log' else 0
                log.write_text('FIXTURE EXIT_CODE=%s\n' % code)
                return code

            result = {'classification': 'FIXTURE_NOT_A_MODEL', 'sha256': 'fixture'}
            with patch.object(week4, 'run_stage', side_effect=stage), \
                    patch.object(week4, 'inspect_model', return_value=result):
                rows = week4.build_all(out, Path('fixture_package'), Path('fixture_arch'), None)
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[2]['status'], 'FAIL')
            self.assertEqual(rows[2]['failed_stage'], 'calib')
            self.assertEqual(rows[3]['status'], 'PASS_HOST_ONLY')
            self.assertNotIn('logs/s2/compile.log', calls)
            self.assertIn('logs/s9/compile.log', calls)
            self.assertIn('PASS_HOST_ONLY=9 FAIL=1 TOTAL=10', (out / 'summary.txt').read_text())
            self.assertEqual(rows[2]['stages'][0]['exit_code'], 7)

    def test_missing_executable_is_logged_as_failure(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'missing.log'
            self.assertEqual(week4.run_stage(['/asi_nonexistent_executable'], log), 127)
            self.assertIn('EXIT_CODE=127', log.read_text())


if __name__ == '__main__':
    unittest.main()
