"""Standalone HOST checks for the single-input adapter; no VART/DPU execution."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SHAPES = [(1, 1, 360), (1, 16, 360), (1, 16, 180), (1, 32, 180), (1, 32, 90),
          (1, 48, 90), (1, 48, 45), (1, 64, 45), (1, 64, 22), (1, 32)]


class SingleInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('g++'):
            raise unittest.SkipTest('g++ required')
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cpp = cls.base / 'single.cpp'
        cpp.write_text(r'''
#include "tail_io.hpp"
#include <iostream>
int main(int argc, char** argv) {
  if (argc != 4) return 2;
  try {
    int s = std::stoi(argv[2]);
    auto shape = asi::sample_shape(s); shape.insert(shape.begin(),1);
    if (s < 9) std::swap(shape[1],shape[2]);
    std::cout << asi::array(asi::input_sample(asi::load_npy(argv[1]),s,std::stoi(argv[3]),shape));
    return 0;
  } catch(const std::exception& e) { std::cerr << e.what(); return 1; }
}
''')
        cls.binary = cls.base / 'single'
        subprocess.run(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'edge/runtime/single_input'), str(cpp), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def invoke(self, array, split, index=0):
        file = self.base / 'input.npy'
        np.save(file, array)
        return subprocess.run([str(self.binary), str(file), str(split), str(index)], capture_output=True, text=True)

    def test_single_tensor_all_layouts(self):
        for split, shape in enumerate(SHAPES):
            with self.subTest(split=split):
                z = np.arange(np.prod(shape), dtype='<f4').reshape(shape)
                run = self.invoke(z, split)
                self.assertEqual(run.returncode, 0, run.stderr)
                expected = z.transpose(0, 2, 1) if split < 9 else z
                np.testing.assert_array_equal(json.loads(run.stdout), expected.reshape(-1))

    def test_rejects_legacy_batches_and_nonzero_sample_index(self):
        for split, shape in enumerate(SHAPES):
            with self.subTest(split=split):
                self.assertNotEqual(self.invoke(np.zeros((20, *shape[1:]), dtype='<f4'), split).returncode, 0)
                self.assertNotEqual(self.invoke(np.zeros(shape, dtype='<f4'), split, 1).returncode, 0)

    def test_rejects_bad_dtype_shape_and_nonfinite(self):
        for array in [np.zeros((1, 32), dtype='<f8'), np.zeros((1, 31), dtype='<f4'),
                      np.full((1, 32), np.nan, dtype='<f4')]:
            with self.subTest(shape=array.shape, dtype=array.dtype):
                self.assertNotEqual(self.invoke(array, 9).returncode, 0)


if __name__ == '__main__':
    unittest.main()
