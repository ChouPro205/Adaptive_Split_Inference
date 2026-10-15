"""Independent binary16 oracle and actual C API contract, valid with Python -O."""
import argparse
import ctypes as ct
from pathlib import Path
import struct
import unittest
import warnings
import numpy as np
from week5_common import Quantizer, FP, QP, BP, write_json, source_hashes, quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl

class Tests(unittest.TestCase):
    def compare(self, z):
        before = z.tobytes()
        q, s = self.c.quantize(z)
        qo, so = quantize_per_channel(z)
        self.assertEqual(q.tobytes(), qo.tobytes())
        self.assertEqual(s.tobytes(), so.tobytes())
        self.assertEqual(self.c.dequantize(q, s).tobytes(), dequantize_per_channel(q, s).tobytes())
        self.assertEqual(z.tobytes(), before)
        return q, s

    def test_half_independent_oracle(self):
        # Python struct implements IEEE binary16 independently of NumPy/C.
        for bits in range(65536):
            value = struct.unpack('<e', struct.pack('<H', bits))[0]
            actual = self.c.dll.week5_f16_to_f32(bits)
            if np.isnan(value):
                self.assertTrue(np.isnan(actual))
            else:
                self.assertEqual(struct.pack('<f', actual), struct.pack('<f', value))
                self.assertEqual(self.c.dll.week5_f32_to_f16(actual), bits)
        values = np.random.default_rng(20261009).integers(0, 2**32, 12000, dtype=np.uint32).view(np.float32)
        positive = np.arange(0x7bff, dtype=np.uint16).view(np.float16).astype(np.float32)
        next_half = np.arange(1, 0x7c00, dtype=np.uint16).view(np.float16).astype(np.float32)
        mid = (positive + next_half) * np.float32(.5)
        boundary = np.concatenate([mid, np.nextafter(mid, np.float32(-np.inf)), np.nextafter(mid, np.float32(np.inf))])
        values = np.concatenate([values, boundary, -boundary, np.array([65519, 65520, -65520, 65536], np.float32)])
        for value in values:
            if np.isnan(value):
                continue
            try:
                expected = int.from_bytes(struct.pack('<e', float(value)), 'little')
            except OverflowError:
                expected = 0xfc00 if np.signbit(value) else 0x7c00
            self.assertEqual(self.c.dll.week5_f32_to_f16(float(value)), expected, f'FP16 RNE: {value}')

    def test_zero_signed_ties_clipping_extremes(self):
        for z in [np.zeros((2, 4, 3), np.float32),
                  np.array([[[0, -0., 0], [2, 2, 2], [-3, -3, -3], [1, -2, 3]]], np.float32),
                  np.array([[[-127, -.5, .5, -1.5, 1.5, 127]]], np.float32),
                  np.array([[[-127.01, 127.01]]], np.float32),
                  np.array([[[1e-45, -1e-45], [1e-20, -1e-20], [.000001, -.000001]]], np.float32),
                  np.array([[[np.float32(65504) * np.float32(127), 0]]], np.float32)]:
            self.compare(z)
        q, _ = self.compare(np.array([[[-127, -.5, .5, -1.5, 1.5, 127]]], np.float32))
        self.assertEqual(q.ravel().tolist(), [-127, 0, 0, -2, 2, 127])

    def test_channel_sample_independence_repeat_and_nc(self):
        rng = np.random.default_rng(20261009)
        z = rng.normal(size=(3, 8, 101)).astype(np.float32)
        z *= np.arange(1, 25, dtype=np.float32).reshape(3, 8, 1)
        q, scale = self.compare(z)
        for n in reversed(range(3)):
            for c in reversed(range(8)):
                qi, si = self.compare(z[n:n+1, c:c+1].copy())
                self.assertEqual(qi.tobytes(), q[n, c].tobytes())
                self.assertEqual(si.tobytes(), scale[n:n+1, c:c+1].tobytes())
        self.compare(z)
        for s, channels in ((9, 32), (10, 5)):
            nc = rng.normal(size=(2, channels)).astype(np.float32)
            self.compare(to_ncl(nc, s))
            self.assertEqual(from_ncl(to_ncl(nc, s), s).tobytes(), nc.tobytes())

    def test_quantize_errors_are_atomic(self):
        z = np.ones((1, 2, 3), np.float32)
        q = np.full(6, 42, np.int8)
        scale = np.full(4, 42, np.uint8)
        def call(zp=None, count=6, n=1, c=2, l=3, qp=None, cap=6, sp=None, scap=4):
            return self.c.dll.week5_quantize(z.ctypes.data_as(FP) if zp is None else zp, count, n, c, l,
                      q.ctypes.data_as(QP) if qp is None else qp, cap, scale.ctypes.data_as(BP) if sp is None else sp, scap)
        size_max = ct.c_size_t(-1).value
        for kwargs in [dict(count=5), dict(n=0), dict(c=0), dict(l=0), dict(cap=5), dict(scap=3),
                       dict(n=size_max, c=2), dict(n=1, c=size_max//2, l=3), dict(n=1, c=1, l=size_max),
                       dict(zp=ct.cast(ct.c_void_p(), FP)), dict(qp=ct.cast(ct.c_void_p(), QP)),
                       dict(sp=ct.cast(ct.c_void_p(), BP)), dict(qp=ct.cast(z.ctypes.data, QP)),
                       dict(sp=ct.cast(q.ctypes.data, BP)), dict(zp=ct.cast(z.ctypes.data+1, FP)),
                       dict(zp=ct.cast(ct.c_size_t(-1).value-3, FP))]:
            self.assertNotEqual(call(**kwargs), 0, str(kwargs))
            self.assertEqual(q.tobytes(), bytes([42])*6)
            self.assertEqual(scale.tobytes(), bytes([42])*4)
        for bad in [np.nan, np.inf, -np.inf, np.finfo(np.float32).max,
                    np.nextafter(np.float32(65504)*np.float32(127), np.float32(np.inf))]:
            z[0, 1, 2] = bad  # error in last channel cannot leave partial output
            self.assertNotEqual(call(), 0)
            self.assertEqual(q.tobytes(), bytes([42])*6)
            self.assertEqual(scale.tobytes(), bytes([42])*4)

    def test_dequantize_errors_are_atomic(self):
        q = np.zeros(6, np.int8)
        scales = np.array([0x3c00, 0x3c00], '<u2')
        z = np.full(6, 42, np.float32)
        def call(count=6, n=1, c=2, l=3, sb=4, cap=6, qp=None, sp=None, zp=None):
            return self.c.dll.week5_dequantize(q.ctypes.data_as(QP) if qp is None else qp, count, n, c, l,
                  scales.ctypes.data_as(BP) if sp is None else sp, sb, z.ctypes.data_as(FP) if zp is None else zp, cap)
        for bits in (0, 0x8000, 1, 0x03ff, 0xbc00, 0x7c00, 0xfc00, 0x7e00):
            scales[1] = bits
            self.assertNotEqual(call(), 0)
            self.assertTrue(np.all(z == 42))
        scales[1] = 0x3c00
        q[-1] = -128
        self.assertNotEqual(call(), 0)
        self.assertTrue(np.all(z == 42))
        q[-1] = 0
        for kwargs in [dict(count=5), dict(n=0), dict(sb=3), dict(sb=5), dict(cap=5),
                       dict(qp=ct.cast(ct.c_void_p(), QP)), dict(sp=ct.cast(ct.c_void_p(), BP)),
                       dict(zp=ct.cast(ct.c_void_p(), FP)), dict(zp=ct.cast(q.ctypes.data, FP)),
                       dict(n=ct.c_size_t(-1).value, c=2)]:
            self.assertNotEqual(call(**kwargs), 0)
            self.assertTrue(np.all(z == 42))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--compiler', default='gcc')
    a = p.parse_args()
    Tests.c = Quantizer(a.output, a.compiler)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    write_json(a.output / 'tests.json', {'status': 'PASS' if result.wasSuccessful() else 'FAIL',
        'tests_run': result.testsRun, 'binary16_decode_patterns': 65536, 'oracle': 'Python struct IEEE binary16',
        'source_sha256': source_hashes(),
        'compile_command': Tests.c.command, 'optimized_python': bool(__import__('sys').flags.optimize)})
    raise SystemExit(0 if result.wasSuccessful() else 1)
