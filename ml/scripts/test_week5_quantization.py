"""Numerical/byte contract tests; no model or dataset required."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from quantization import (FP16_MIN_NORMAL, quantize_per_channel as quantize,
                          dequantize_per_channel as dequantize, to_ncl, from_ncl)


class QuantizationTests(unittest.TestCase):
    def test_zero_constant_signed_channels(self):
        z = np.array([[[0, 0, 0], [2, 2, 2], [-3, -3, -3], [1, 2, 3]]], dtype=np.float32)
        q, scale = quantize(z)
        np.testing.assert_array_equal(q[0, 0], 0)
        self.assertEqual(scale[0, 0], np.float16(1))
        np.testing.assert_array_equal(q[0, 1], 127)
        np.testing.assert_array_equal(q[0, 2], -127)
        self.assertEqual(q.dtype, np.int8)
        self.assertEqual(scale.dtype.str, "<f2")
        self.assertEqual(dequantize(q, scale).dtype, np.float32)

    def test_rounding_and_clipping(self):
        # Max=127 -> exactly stored scale 1. Both tie directions are exercised.
        z = np.array([[[-127, -.5, .5, -1.5, 1.5, 127]]], dtype=np.float32)
        q, scale = quantize(z)
        np.testing.assert_array_equal(q, [[[-127, 0, 0, -2, 2, 127]]])
        # Stored scale rounds down: ratio exceeds 127, clip before INT8 cast.
        z = np.array([[[-127.01, 127.01]]], dtype=np.float32)
        q, scale = quantize(z)
        self.assertGreater(float(z[0, 0, 1] / np.float32(scale[0, 0])), 127)
        np.testing.assert_array_equal(q, [[[-127, 127]]])

    def test_small_and_batch_independence(self):
        z = np.array([[[1e-20, -1e-20], [1, -1]], [[.001, -.001], [100, -100]]], dtype=np.float32)
        q, scale = quantize(z)
        self.assertEqual(scale[0, 0], FP16_MIN_NORMAL)
        np.testing.assert_array_equal(q[0, 0], 0)
        for n in range(2):
            qi, si = quantize(z[n:n+1])
            np.testing.assert_array_equal(q[n:n+1], qi)
            np.testing.assert_array_equal(scale[n:n+1].view("<u2"), si.view("<u2"))
        self.assertNotEqual(scale[0, 1], scale[1, 1])

    def test_file_roundtrip_and_effective_scale(self):
        z = np.array([[[1, .3, -.2], [0, 0, 0]]], dtype=np.float32)
        q, scale = quantize(z)
        expected = np.clip(np.rint(z / scale.astype(np.float32)[..., None]), -127, 127).astype(np.int8)
        np.testing.assert_array_equal(q, expected)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scale.f16le.bin"
            scale.tofile(path)
            reread = np.fromfile(path, dtype="<f2").reshape(scale.shape)
            self.assertEqual(path.read_bytes(), scale.view("<u2").tobytes())
            np.testing.assert_array_equal(dequantize(q, reread), q.astype(np.float32) * reread.astype(np.float32)[..., None])

    def test_rejections(self):
        for value in (np.nan, np.inf, -np.inf, np.finfo(np.float32).max):
            with self.assertRaises(ValueError):
                quantize(np.array([[[value]]], dtype=np.float32))
        for z in (np.zeros((1, 1)), np.zeros((1, 1, 0), dtype=np.float32), np.zeros((1, 1, 1), dtype=np.float64)):
            with self.assertRaises(ValueError):
                quantize(z)
        q = np.zeros((1, 1, 1), dtype=np.int8)
        for scale in (np.array([[0]], dtype=np.float16), np.array([[np.nan]], dtype=np.float16),
                      np.array([[np.inf]], dtype=np.float16), np.array([[-1]], dtype=np.float16),
                      np.array([[np.nextafter(np.float16(0), np.float16(1))]], dtype=np.float16),
                      np.ones((1, 2), dtype=np.float16), np.ones((1, 1), dtype=np.float32)):
            with self.assertRaises(ValueError):
                dequantize(q, scale)
        with self.assertRaises(ValueError):
            dequantize(np.full_like(q, -128), np.ones((1, 1), dtype=np.float16))

    def test_nc_and_boundaries(self):
        for s, shape in ((0, (1, 1, 360)), (9, (1, 32)), (10, (1, 5))):
            z = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
            np.testing.assert_array_equal(from_ncl(to_ncl(z, s), s), z)
        with self.assertRaises(ValueError):
            to_ncl(np.zeros((1, 32), dtype=np.float32), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
