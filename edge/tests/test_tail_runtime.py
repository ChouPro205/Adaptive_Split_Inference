"""Host checks for input conversion/report validation, not VART/DPU acceptance."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('tail_batch', ROOT / 'edge/runtime/run_tail_models.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class TailRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('g++'):
            raise unittest.SkipTest('g++ is required for standalone C++ input checks')
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        source = cls.base / 'io_check.cpp'
        source.write_text(r'''
#include "tail_io.hpp"
#include <iostream>
int main(int argc, char** argv) {
  try {
    if (argc == 1) {
      for (float x : {-200.f, -128.5f, -1.5f, -0.5f, 0.5f, 1.5f, 126.5f, 200.f})
        std::cout << +asi::quantize(x, 0) << " ";
    } else {
      auto input = asi::load_npy(argv[1]);
      int split = std::stoi(argv[2]);
      auto target = asi::sample_shape(split);
      target.insert(target.begin(), 1);
      if (split < 9) std::swap(target[1], target[2]);
      std::cout << asi::array(asi::input_sample(input, split, 0, target));
    }
    return 0;
  } catch (const std::exception& e) { std::cerr << e.what(); return 1; }
}
''')
        cls.binary = cls.base / 'io_check'
        subprocess.run(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'edge/runtime'), str(source), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_rounding_negative_ties_and_saturation(self):
        actual = subprocess.check_output([str(self.binary)], text=True)
        self.assertEqual([int(x) for x in actual.split()], [-128, -128, -1, 0, 1, 2, 127, 127])

    def test_frozen_goldens_parse_and_ncl_to_nlc(self):
        package = ROOT / 'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1'
        if not package.is_dir():
            self.skipTest('frozen package unavailable')
        for split in range(10):
            path = package / ('golden/z_s%d.npy' % split)
            z = np.load(path, allow_pickle=False)[0:1]
            expected = z.transpose(0, 2, 1) if split < 9 else z
            result = subprocess.check_output([str(self.binary), str(path), str(split)], text=True)
            np.testing.assert_array_equal(np.asarray(json.loads(result)), expected.reshape(-1))

    def test_rejects_wrong_dtype_fortran_and_truncated_files(self):
        for label, values in [('dtype', np.zeros((20,1,360), dtype=np.float64)),
                              ('fortran', np.asfortranarray(np.zeros((20,16,360), dtype=np.float32)))]:
            path = self.base / (label + '.npy')
            np.save(path, values)
            result = subprocess.run([str(self.binary), str(path), '0'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        path = self.base / 'truncated.npy'
        path.write_bytes(b'\x93NUMPY\x01\x00\xff\xff')
        self.assertNotEqual(subprocess.run([str(self.binary), str(path), '0'], capture_output=True).returncode, 0)

    def test_comparison_rejects_missing_root_execution_and_wrong_shape(self):
        with self.assertRaises(ValueError):
            batch.compare({'samples': []}, np.zeros((20,5)), 1)
        result = {'execution': 'root_graph', 'status': 'FULL_TAIL_EXECUTED_NOT_NUMERICALLY_ACCEPTED',
                  'samples': [{'sample_index': 0, 'shape': [1,4], 'logits': [0,0,0,0]}]}
        with self.assertRaises(ValueError):
            batch.compare(result, np.zeros((20,5)), 1)

    def test_missing_criterion_never_accepts_and_draft_is_rejected(self):
        cases = [{'max_abs_error': 0.0, 'class_match': True}] * 20
        self.assertIsNone(batch.accepted(cases, None))
        with self.assertRaises(ValueError):
            batch.load_criterion(ROOT / 'edge/runtime/criterion_draft.json')
        criterion = {'max_abs_error': 0.1, 'minimum_class_agreement': 1.0,
                     'max_abs_error_comparison': '<'}
        self.assertIsNone(batch.accepted(cases[:1], criterion))
        self.assertTrue(batch.accepted(cases, criterion))
        cases[5] = {'max_abs_error': 0.1, 'class_match': True}
        self.assertFalse(batch.accepted(cases, criterion))


if __name__ == '__main__':
    unittest.main()
