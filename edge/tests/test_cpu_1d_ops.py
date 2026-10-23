"""CPU-kernel host fixtures compared to PyTorch; not KV260/full-tail evidence."""
import ctypes
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]


class Cpu1dTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('g++'):
            raise unittest.SkipTest('g++ required')
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        source = base / 'kernel_check.cpp'
        source.write_text(r'''
#include "cpu_1d.hpp"
extern "C" int conv(float* y,const float* x,const float* w,const float* b,int l,int ci,int co) {
  try { asi_cpu::conv1d(y,x,w,b,{1,l,ci},{co,5,ci},{1,l,co},1,1,2,2); return 0; }
  catch(...) { return 1; }
}
extern "C" int pool(float* y,const float* x,int l,int c,int out) {
  try { asi_cpu::maxpool1d(y,x,{1,l,c},{1,out,c},2,2); return 0; }
  catch(...) { return 1; }
}
extern "C" float relu(float x) { return asi_cpu::relu(x); }
''')
        lib = base / 'kernel_check.so'
        subprocess.run(['g++', '-std=c++17', '-O2', '-ffp-contract=off', '-fPIC', '-shared',
                        '-I', str(ROOT / 'edge/runtime/cpu_ops'), str(source), '-o', str(lib)], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        cls.ptr = ctypes.POINTER(ctypes.c_float)
        cls.lib.conv.argtypes = [cls.ptr] * 4 + [ctypes.c_int] * 3
        cls.lib.pool.argtypes = [cls.ptr] * 2 + [ctypes.c_int] * 3
        cls.lib.conv.restype = cls.lib.pool.restype = ctypes.c_int
        cls.lib.relu.argtypes = [ctypes.c_float]
        cls.lib.relu.restype = ctypes.c_float

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def ptr_of(self, value):
        return value.ctypes.data_as(self.ptr)

    def test_conv_all_frozen_layer_shapes_against_torch(self):
        rng = np.random.default_rng(420)
        for length, ci, co in [(360,1,16),(360,16,16),(180,16,32),(180,32,32),
                               (90,32,48),(90,48,48),(45,48,64),(45,64,64)]:
            with self.subTest(length=length, ci=ci, co=co):
                x = rng.normal(0, 0.2, (1,length,ci)).astype('float32')
                w = rng.normal(0, 0.05, (co,5,ci)).astype('float32')
                b = rng.normal(0, 0.01, co).astype('float32')
                y = np.empty((1,length,co), dtype='float32')
                self.assertEqual(self.lib.conv(self.ptr_of(y),self.ptr_of(x),self.ptr_of(w),self.ptr_of(b),length,ci,co),0)
                expected = F.conv1d(torch.from_numpy(x).permute(0,2,1),
                                    torch.from_numpy(w).permute(0,2,1),torch.from_numpy(b),padding=2)
                np.testing.assert_allclose(y,expected.permute(0,2,1).numpy(),rtol=2e-5,atol=2e-5)

    def test_pool_negative_values_odd_and_even_lengths(self):
        rng = np.random.default_rng(421)
        for length, channels in [(360,16),(180,32),(90,48),(45,64)]:
            x = -rng.uniform(0.1,5,(1,length,channels)).astype('float32')
            y = np.empty((1,length//2,channels),dtype='float32')
            self.assertEqual(self.lib.pool(self.ptr_of(y),self.ptr_of(x),length,channels,length//2),0)
            expected = F.max_pool1d(torch.from_numpy(x).permute(0,2,1),2,2).permute(0,2,1).numpy()
            np.testing.assert_array_equal(y,expected)

    def test_reject_wrong_pool_output_shape(self):
        x=np.ones((1,45,64),dtype='float32');y=np.empty((1,23,64),dtype='float32')
        self.assertNotEqual(self.lib.pool(self.ptr_of(y),self.ptr_of(x),45,64,23),0)

    def test_relu_negative_positive_and_nonfinite_semantics(self):
        values = [-float('inf'), -3.5, -0.0, 0.0, 2.5, float('inf'), float('nan')]
        actual = [self.lib.relu(x) for x in values]
        expected = F.relu(torch.tensor(values, dtype=torch.float32)).numpy()
        np.testing.assert_allclose(actual, expected, rtol=0, atol=0, equal_nan=True)


if __name__ == '__main__':
    unittest.main()
