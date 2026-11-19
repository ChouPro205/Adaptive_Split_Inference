"""Evidence/plan tests, using authenticated saved inputs when locally available."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'edge/server/week10'))
from evidence import package, save, seal, sha, verify
from prepare import prepare
from bench import plan
from analyze import analyze, read_run, stats


class ToolsTests(unittest.TestCase):
    def fixture(self, folder, omit_warmup=False):
        vectors = [dict(vector_index=s, split_point_s=s) for s in range(11)]
        schedule = plan(vectors, 'benchmark', [], 1, 20)
        if omit_warmup:
            schedule = [(ph, v) for ph, v in schedule if ph != 'warmup']
        save(folder / 'plan.json', [dict(phase=ph, vector_index=v['vector_index'], split_s=v['split_point_s'])
                                   for ph, v in schedule])
        model_hashes = {str(s): str(s) * 64 for s in range(10)}
        save(folder / 'run.json', dict(run_id='HOST_FIXTURE_ONLY', mode='benchmark',
             plan_sha256=sha(folder / 'plan.json'), backend=dict(models=model_hashes),
             cycles=1, warmup_per_split=20, scope='HOST_UNIT_FIXTURE_NOT_HARDWARE', switch_scope='TEST_ONLY'))
        seen, previous = set(), None
        with (folder / 'requests.jsonl').open('x') as f:
            for i, (phase, v) in enumerate(schedule):
                s = v['split_point_s']
                hit = s in seen and s < 10
                if s < 10:
                    seen.add(s)
                row = dict(run_id='HOST_FIXTURE_ONLY', index=i, phase=phase, vector_index=v['vector_index'],
                           previous_s=previous, split_s=s, result='OK', response_cache_hit=False,
                           model_cache_hit=hit, load_count=1 if s < 10 else 0,
                           context_id=s + 1 if s < 10 else None, contexts_count=len(seen),
                           model_sha256=model_hashes.get(str(s)), switch_ms=1., native_select_ms=.1,
                           tail_ms=1. if s < 10 else None, load_ms=None if hit or s == 10 else .1,
                           service_ms=2., worker_pid=123, baseline_bit_exact=True)
                f.write(json.dumps(row) + '\n')
                previous = s
        save(folder / 'summary.json', dict(run_id='HOST_FIXTURE_ONLY', rows=len(schedule), planned=len(schedule),
             status='EXECUTION_COMPLETE_NUMERIC_REVIEW_PENDING', parity_mismatches=0, error=None))
        seal(folder)

    def test_analyzer_checks_warmup_and_plan_before_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            run = p / 'run'
            run.mkdir()
            self.fixture(run)
            result = analyze(run, p / 'analysis')
            self.assertTrue(result['execution_complete'])
            self.assertEqual(result['timing_observation'], 'ALL_OBSERVED_WARM_SWITCHES_LT_50_MS')
            self.assertLess(result['ordered_pairs_observed'], 90)
            self.assertEqual(result['project_acceptance'], 'PENDING_REVIEW_OF_SCOPE_AND_CRITERION')
            (run / 'requests.jsonl').write_text('changed')
            with self.assertRaises(ValueError):
                read_run(run)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.fixture(p, omit_warmup=True)
            with self.assertRaisesRegex(ValueError, 'phase coverage'):
                read_run(p)

    def test_checksums_reject_mutation_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'row').write_text('original')
            seal(p)
            self.assertEqual(verify(p), {'row'})
            (p / 'row').write_text('changed')
            with self.assertRaises(ValueError):
                verify(p)
            (p / 'sha256sum_results.txt').write_text('a' * 64 + '  ../outside\n')
            with self.assertRaises(ValueError):
                verify(p)

    def test_plan_excludes_identity_from_first_load_and_preserves_phases(self):
        vectors = [dict(vector_index=s, split_point_s=s) for s in range(11)]
        p = plan(vectors, 'benchmark', [], 1, 20)
        self.assertEqual([v['split_point_s'] for phase, v in p if phase == 'first_load'], list(range(10)))
        self.assertEqual(sum(phase == 'warmup' for phase, _ in p), 200)
        self.assertEqual(sum(phase == 'warm_switch' for phase, _ in p), 20)
        self.assertEqual([v['split_point_s'] for phase, v in p if phase == 'identity_diagnostic'], [2, 10, 5])
        self.assertEqual(stats([1., 2., 50.])['at_or_above_50_count'], 1)
        self.assertIsNone(stats([])['max_ms'])

    def test_prepare_real_inputs_preserves_old_and_rejects_overwrite(self):
        base = ROOT / 'edge/build_vai25/ket_qua_hien_tai'
        p7 = base / 'week7/phien_dang_dung.txt'
        p5 = base / 'week5/phien_dang_dung.txt'
        if not p7.is_file() or not p5.is_file():
            self.skipTest('Authenticated local packet/model artifacts not present')
        packets = Path(p7.read_text().strip()) / 'du_lieu/mitdb-week6-p1-50-20261016-v1'
        bundle = Path(p5.read_text().strip()) / 'bundle'
        if not packets.is_dir() or not bundle.is_dir():
            self.skipTest('Authenticated local packet/model artifacts not present')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'prepared'
            pointer = Path(tmp) / 'active.txt'
            prepare(ROOT, packets, bundle, out, pointer)
            self.assertEqual(Path(pointer.read_text().strip()), out)
            self.assertEqual(len(package(out / 'inputs/packets')), 50)
            verify(out, 'sha256sum_prepare.txt')
            self.assertTrue((out / 'source/edge/runtime/model_cache/tail_cache_worker.cpp').is_file())
            with self.assertRaises(FileExistsError):
                prepare(ROOT, packets, bundle, out)
            (out / 'source/edge/server/week10/service.py').write_text('tampered')
            with self.assertRaises(ValueError):
                verify(out, 'sha256sum_prepare.txt')


if __name__ == '__main__':
    unittest.main()
