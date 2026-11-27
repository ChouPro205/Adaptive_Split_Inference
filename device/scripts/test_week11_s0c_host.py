#!/usr/bin/env python3
"""Host tests of the week 11 S0c v1 encoder in C (device/week11/s0c.c; no dongle). Needs gcc on PATH (or CC).

The numpy reference contracts/s0c_v1_ref/s0c_v1_ref.py (S0C-V1) is normative; the C encoder must give its
reduced 46 values (bit for bit), q, FP16 scale, Rice k and body bytes exactly:
1. the 20 golden beats of contracts/s0c_v1_ref/s0c_v1_golden20.{npz,json} (SHA-256 pinned below);
2. the 100 W8-D3 inputs the firmware encodes (week8_inputs.h of the sample set, WEEK10_SAMPLES);
3. edge cases: an all-zero beat (scale 1), a constant beat, alternating +-extremes (k = 7, the longest body),
   values past the FP16 scale range and NaN/Inf (refused by both), tiny values (FP16 minimum normal scale),
   and 2000 random beats with seeded mixtures of scales.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week11_s0c_host.py
"""
from __future__ import annotations

import ctypes as ct
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WEEK11 = ROOT / "device" / "week11"
REF_DIR = ROOT / "contracts" / "s0c_v1_ref"
SAMPLES = Path(os.environ.get("WEEK10_SAMPLES", r"D:\HUST\ASI_week8\samples-20261023-c"))
REF_SHA256 = {
    "s0c_v1_ref.py": "323ffabaa255f80de9730279e7d0abee7571125bb61d1c36e871dc113bcaf0a0",
    "s0c_v1_golden20.npz": "2923fe85c5d6fa111e97dbf47f10b81bc487a6b9cca7d8fa8becbfb109089d87",
    "s0c_v1_golden20.json": "23eb93f4e7d69dbd15b04167401d3e046c4ddd212409efadb8377a80c2c672f9",
}
WEEK8_SET_SHA256 = "7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639"
WEEK8_INPUTS_SHA256 = "4091e4613e0680aebd7c656c408311534a5645bf4ab30ef3faf0d7e896d41317"
HAVE_CC = bool(os.environ.get("CC") or shutil.which("gcc"))
TMP = Path(tempfile.mkdtemp(prefix="week11_s0c_host_"))
LIB = None
REF = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_ref():
    global REF
    if REF is None:
        for name, digest in REF_SHA256.items():
            if sha256_file(REF_DIR / name) != digest:
                raise ValueError(f"{name} differs from S0C-V1 ({digest[:8]}...)")
        spec = importlib.util.spec_from_file_location("s0c_v1_ref", REF_DIR / "s0c_v1_ref.py")
        REF = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(REF)
    return REF


def build(with_week8: bool) -> ct.CDLL:
    cc = os.environ.get("CC") or shutil.which("gcc")
    out = TMP / f"s0c_shim-{os.getpid()}-{int(with_week8)}{'.dll' if os.name == 'nt' else '.so'}"
    cmd = [cc, "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
           "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
           "-I", str(WEEK11), "-I", str(ROOT / "device" / "week5")]
    if with_week8:
        cmd += ["-DS0C_SHIM_WEEK8", "-I", str(SAMPLES)]
    cmd += ["-o", str(out), str(WEEK11 / "host_test" / "s0c_shim.c"), str(WEEK11 / "s0c.c"),
            str(ROOT / "device" / "week5" / "quantization.c")]
    subprocess.run(cmd, check=True)
    lib = ct.CDLL(str(out))
    lib.shim_s0c_encode.argtypes = [ct.POINTER(ct.c_float), ct.POINTER(ct.c_float), ct.c_char_p, ct.c_char_p,
                                    ct.c_char_p, ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint)]
    if with_week8:
        lib.shim_set_sha256.restype = ct.c_char_p
        lib.shim_week8_input.argtypes = [ct.c_uint, ct.POINTER(ct.c_float)]
    return lib


def lib() -> ct.CDLL:
    global LIB
    if LIB is None:
        LIB = build(False)
    return LIB


def c_encode(x: np.ndarray, library=None):
    """(status, reduced, q, scale_le, body, k) of the C encoder."""
    library = library or lib()
    x = np.ascontiguousarray(x, dtype="<f4")
    reduced = np.zeros(46, dtype="<f4")
    q = ct.create_string_buffer(46)
    scale = ct.create_string_buffer(2)
    body = ct.create_string_buffer(int(library.shim_body_max()))
    body_len, k = ct.c_uint(), ct.c_uint()
    status = library.shim_s0c_encode(x.ctypes.data_as(ct.POINTER(ct.c_float)),
                                     reduced.ctypes.data_as(ct.POINTER(ct.c_float)), q, scale, body,
                                     ct.byref(body_len), ct.byref(k))
    if status != 0:
        return status, None, None, None, None, None
    return (status, reduced, np.frombuffer(q.raw, dtype=np.int8).copy(), scale.raw,
            body.raw[:body_len.value], k.value)


def assert_equal_to_ref(case: unittest.TestCase, x: np.ndarray, label: str, library=None):
    ref = load_ref()
    status, reduced, q, scale, body, k = c_encode(x, library)
    case.assertEqual(status, 0, label)
    r_reduced = ref.reduce46(x)
    r_body, r_scale, r_q = ref.encode(x)
    case.assertEqual(reduced.view("<u4").tolist(), r_reduced.view("<u4").tolist(), label + " reduced46")
    case.assertEqual(q.tolist(), r_q.tolist(), label + " q")
    case.assertEqual(scale, np.asarray(r_scale, dtype="<f2").tobytes(), label + " scale")
    case.assertEqual(body, r_body, label + " body")
    case.assertEqual(k, r_body[1], label + " k")
    case.assertLessEqual(len(body), int(lib().shim_body_max()), label)
    # The reference decoder (edge side) gives back q from the C bytes.
    case.assertEqual(ref.rice_decode(body).tolist(), q.tolist(), label + " decode")
    return body


def setUpModule():
    if not HAVE_CC:
        raise unittest.SkipTest("no gcc on PATH (set CC)")


class Golden(unittest.TestCase):
    def test_golden20(self):
        load_ref()
        meta = json.loads((REF_DIR / "s0c_v1_golden20.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["version"], "S0C-V1")
        self.assertEqual(meta["reference_sha256"], REF_SHA256["s0c_v1_ref.py"])
        with np.load(REF_DIR / "s0c_v1_golden20.npz", allow_pickle=False) as npz:
            arrays = {k: npz[k] for k in npz.files}
        self.assertEqual(len(meta["beats"]), 20)
        for n, beat in enumerate(meta["beats"]):
            x = arrays["x"][n]
            body = assert_equal_to_ref(self, x, f"golden {n}")
            status, reduced, q, scale, body, k = c_encode(x)
            self.assertEqual(reduced.view("<u4").tolist(), arrays["reduced_v46"][n].view("<u4").tolist())
            self.assertEqual(q.tolist(), arrays["q"][n].tolist())
            self.assertEqual(q.tolist(), beat["q"])
            self.assertEqual(scale, arrays["scale_fp16"][n:n + 1].astype("<f2").tobytes())
            self.assertEqual(scale.hex(), beat["scale_fp16_le_hex"])
            self.assertEqual(body.hex(), beat["body_hex"])
            self.assertEqual(len(body), beat["body_len_B"])
            self.assertEqual(k, beat["rice_k"])


class Week8Inputs(unittest.TestCase):
    def test_w8d3_inputs(self):
        if not SAMPLES.exists():
            self.skipTest(f"W8-D3 set not found at {SAMPLES} (set WEEK10_SAMPLES)")
        self.assertEqual(sha256_file(SAMPLES / "week8_inputs.h"), WEEK8_INPUTS_SHA256)
        library = build(True)
        self.assertEqual(library.shim_set_sha256().decode(), WEEK8_SET_SHA256)
        lengths = []
        for n in range(100):
            x = np.zeros(360, dtype="<f4")
            self.assertEqual(library.shim_week8_input(n, x.ctypes.data_as(ct.POINTER(ct.c_float))), 0)
            lengths.append(len(assert_equal_to_ref(self, x, f"W8-D3 {n}", library)))
        self.assertTrue(all(2 < b <= 64 for b in lengths))


class EdgeCases(unittest.TestCase):
    def test_zero_and_constant(self):
        status, _, q, scale, body, k = c_encode(np.zeros(360, np.float32))
        self.assertEqual((status, scale, q.tolist(), k), (0, np.float16(1).tobytes(), [0] * 46, 0))
        assert_equal_to_ref(self, np.zeros(360, np.float32), "zero")
        assert_equal_to_ref(self, np.full(360, -3.25, np.float32), "constant")

    def test_extremes_and_longest_body(self):
        x = np.where(np.arange(360) % 16 < 8, 4.0, -4.0).astype(np.float32)
        assert_equal_to_ref(self, x, "square")
        # Alternating bins at +-max: every delta is +-254, the worst case of the size bound.
        b = load_ref().BINS
        x = np.zeros(360, np.float32)
        for i, (lo, hi) in enumerate(b):
            x[lo:hi] = 100.0 if i % 2 == 0 else -100.0
        body = assert_equal_to_ref(self, x, "alternating")
        self.assertEqual(body[1], 7)
        self.assertLessEqual(len(body), 64)
        assert_equal_to_ref(self, np.full(360, 1e-12, np.float32), "tiny")
        assert_equal_to_ref(self, np.full(360, 8.3e6, np.float32), "large but in range")

    def test_refused(self):
        ref = load_ref()
        for label, x in (("nan", np.full(360, np.nan, np.float32)), ("inf", np.full(360, np.inf, np.float32)),
                         ("scale out of FP16 range", np.full(360, 3.0e7, np.float32))):
            self.assertNotEqual(c_encode(x)[0], 0, label)
            with self.assertRaises(ValueError):
                ref.encode(x)

    def test_random(self):
        rng = np.random.default_rng(20261126)
        for n in range(2000):
            scale = 10.0 ** rng.uniform(-6, 3)
            x = (rng.standard_normal(360) * scale).astype(np.float32)
            if n % 3 == 0:
                x = np.cumsum(x).astype(np.float32)     # smooth, ECG-like small deltas
            assert_equal_to_ref(self, x, f"random {n}")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if result.wasSuccessful() else 1)
