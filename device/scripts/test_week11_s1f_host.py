"""Host test of the S1F v1 reference in contracts/s1f_v1_ref/ (fixed S1 compressor, K gate H6).

Pins the SHA-256 of the reference, the constants and the golden files, then re-runs the reference on the 20 golden
beats: encode gives the stored q, scales and payload bytes exactly; decode gives the stored dequantized latent,
z_hat and tail input bit for bit (same numpy code). Also checks the I1 frame sizes of the proposal (S1F46 130 B,
S1F20 104 B: 68 + 8 C + C L) and that malformed payloads are refused. No torch, no MITDB data.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week11_s1f_host.py
"""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REF_DIR = ROOT / "contracts" / "s1f_v1_ref"
SHA = {
    "s1f_v1_ref.py": "292d09148eceb2fd33e709b3919b9cf314565fc4fcf4c6c29a42dabdb4828e93",
    "s1f_v1_constants.json": "36b2a6dacfeeb8623672f48d0f7e0a67d793a20624e8c2c0ee665c03c2f18c80",
    "s1f_v1_golden20.json": "2ea868f396f1e396d1ed3fa64ee08a3659049f0db241f27df0ac771f01771f95",
    "s1f_v1_golden20.npz": "0d6d57ab1468ee65f19d6698c0332c8da366ad63f05b19f340ed358f756ad006",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class S1fReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("s1f_v1_ref", REF_DIR / "s1f_v1_ref.py")
        cls.ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ref)
        cls.B, cls.c = cls.ref.load_constants(REF_DIR / "s1f_v1_constants.json")
        cls.g = np.load(REF_DIR / "s1f_v1_golden20.npz")
        cls.meta = json.loads((REF_DIR / "s1f_v1_golden20.json").read_text(encoding="utf-8"))

    def test_pinned_hashes(self):
        for name, h in SHA.items():
            self.assertEqual(sha(REF_DIR / name), h, name)
        self.assertEqual(self.meta["reference_sha256"], SHA["s1f_v1_ref.py"])
        self.assertEqual(self.meta["constants_sha256"], SHA["s1f_v1_constants.json"])
        for k, h in self.meta["array_sha256"].items():
            self.assertEqual(hashlib.sha256(np.ascontiguousarray(self.g[k]).tobytes()).hexdigest(), h, k)

    def test_constants(self):
        self.assertEqual(self.B.shape, (16, 2))
        self.assertEqual(self.c.shape, (16,))
        self.assertTrue(np.all(self.c >= 0))                      # c = ReLU(bias)
        self.assertLess(np.max(np.abs(self.B.T.astype(np.float64) @ self.B - np.eye(2))), 1e-6)

    def test_golden_encode_exact(self):
        for i, beat in enumerate(self.meta["beats"]):
            data, scales, q, latent = self.ref.encode(self.g["z_s1"][i], self.B, self.c)
            self.assertEqual(data.hex(), beat["payload_hex"])
            self.assertEqual(scales.tobytes().hex(), beat["scales_fp16_le_hex"])
            self.assertEqual(scales.astype("<f4").tobytes().hex(), beat["scales_float32_le_hex_for_I1"])
            self.assertTrue(np.array_equal(q, self.g["q"][i]))
            self.assertTrue(np.array_equal(latent.view(np.uint32), self.g["latent"][i].view(np.uint32)))
            self.assertEqual(len(data), 46)

    def test_golden_decode_exact(self):
        for i, beat in enumerate(self.meta["beats"]):
            v, zh, y = self.ref.decode(bytes.fromhex(beat["payload_hex"]), self.g["scale_fp16"][i], self.B, self.c)
            for got, key in ((v, "dequantized_latent"), (zh, "z_hat_23"), (y, "tail_input_16x360")):
                self.assertTrue(np.array_equal(got.view(np.uint32), self.g[key][i].view(np.uint32)), key)

    def test_i1_frame_sizes_of_proposal(self):
        for c_, l_, total in ((2, 23, 130), (2, 10, 104)):
            self.assertEqual(68 + 8 * c_ + c_ * l_, total)

    def test_s1f20_variant(self):
        data, scales, q, _ = self.ref.encode(self.g["z_s1"][0], self.B, self.c, 10)
        self.assertEqual(len(data), 20)
        v, zh, y = self.ref.decode(data, scales, self.B, self.c, 10)
        self.assertEqual(y.shape, (16, 360))

    def test_refusals(self):
        good = bytes.fromhex(self.meta["beats"][0]["payload_hex"])
        s = self.g["scale_fp16"][0]
        with self.assertRaises(ValueError):
            self.ref.decode(good[:-1], s, self.B, self.c)               # wrong length
        with self.assertRaises(ValueError):
            self.ref.decode(b"\x80" + good[1:], s, self.B, self.c)      # -128
        with self.assertRaises(ValueError):
            self.ref.decode(good, np.zeros(2, dtype="<f2"), self.B, self.c)  # zero scale
        bad = self.g["z_s1"][0].copy()
        bad[0, 0] = np.nan
        with self.assertRaises(ValueError):
            self.ref.encode(bad, self.B, self.c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
