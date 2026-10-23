"""Host-only evidence validation. These fixtures are NOT board measurements."""
import copy
import math
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from profile_tail_models import stats, validate


def fixture():
    r = dict(sample_index=0, prepare_ms=1., input_sync_ms=2., execute_wait_ms=3.,
             output_read_ms=4., tail_total_ms=10., logits=[1., 2., 3., 4., 5.])
    return dict(execution='root_graph', clock='std::chrono::steady_clock', split=9,
                warmup=2, repeats=1, status='PROFILE_EXECUTED_NUMERIC_ACCEPTANCE_SEPARATE',
                output_tensor={'shape': [1, 5]}, deserialize_ms=1., create_runner_ms=2.,
                tensor_setup_ms=3., model_load_ms=6., first_inference=copy.deepcopy(r), measurements=[r])


class Checks(unittest.TestCase):
    def test_known_statistics_and_singleton(self):
        s = stats([1, 2, 3, 4, 5])
        self.assertEqual(s['mean_ms'], 3.)
        self.assertEqual(s['median_ms'], 3.)
        self.assertAlmostEqual(s['p95_ms'], 4.8)
        self.assertAlmostEqual(s['std_ms'], math.sqrt(2.5))
        self.assertEqual(s['ci_df'], 4)
        self.assertIsNone(stats([1])['ci95_mean_ms'])

    def test_rejects_bad_measurements(self):
        for values in ([], [-1], [float('nan')], [float('inf')]):
            with self.assertRaises(ValueError):
                stats(values)

    def test_validate_complete_and_reject_timing_mismatch(self):
        self.assertEqual(len(validate(fixture(), 9, 2, 1)), 1)
        for key in ('model_load_ms',):
            r = fixture()
            r[key] = 99
            with self.assertRaises(ValueError):
                validate(r, 9, 2, 1)
        r = fixture()
        r['measurements'][0]['tail_total_ms'] = 99
        with self.assertRaises(ValueError):
            validate(r, 9, 2, 1)

    def test_reject_wrong_graph_configuration_and_incomplete_run(self):
        for key, value in [('execution', 'child_dpu'), ('split', 8), ('warmup', 3),
                           ('clock', 'wall'), ('status', 'PARTIAL'), ('measurements', [])]:
            r = fixture()
            r[key] = value
            with self.assertRaises(ValueError):
                validate(r, 9, 2, 1)

    def test_reject_bad_sample_order_and_logits(self):
        for field, value in [('sample_index', 1), ('logits', [1, 2, 3]),
                             ('logits', [0, 0, 0, 0, float('nan')])]:
            r = fixture()
            r['measurements'][0][field] = value
            with self.assertRaises(ValueError):
                validate(r, 9, 2, 1)


if __name__ == '__main__':
    unittest.main()
