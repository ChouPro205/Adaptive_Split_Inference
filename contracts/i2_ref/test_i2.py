"""Run with: python -B contracts/i2_ref/test_i2.py (stdlib + host C compiler)."""

from __future__ import annotations

import ctypes
import gc
import json
import os
import random
import subprocess
import tempfile
import unittest
from pathlib import Path

from i2_reference import I2Error, Profile, chacha20_block, descriptor, protect, unprotect

HERE = Path(__file__).resolve().parent
VECTORS = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))
STATUS = {
    "OK": 0,
    "INVALID_ARGUMENT": 1,
    "INVALID_NONCE": 2,
    "KEY_UNAVAILABLE": 3,
    "INVALID_PROFILE": 4,
    "INVALID_METADATA": 5,
    "UNSUPPORTED_VERSION": 6,
    "UNSUPPORTED_ALGORITHM": 7,
    "SIZE_LIMIT": 8,
    "LENGTH_MISMATCH": 9,
    "PROFILE_MISMATCH": 10,
    "KEY_SCOPE_MISMATCH": 11,
    "BUFFER_TOO_SMALL": 12,
}


class CProfile(ctypes.Structure):
    _fields_ = [("model_profile_id", ctypes.c_uint32), ("split_id", ctypes.c_uint16),
                ("channels", ctypes.c_uint16), ("length", ctypes.c_uint32),
                ("key_id", ctypes.c_uint32), ("max_payload_bytes", ctypes.c_uint32)]


class I2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / ("i2_reference.dll" if os.name == "nt" else "libi2_reference.so")
        compiler = os.environ.get("CC", "gcc")
        position_independent = [] if os.name == "nt" else ["-fPIC"]
        subprocess.run([compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-pedantic", *position_independent, "-shared", "-o", str(library),
                        str(HERE / "i2_reference.c")], check=True)
        cls.c = ctypes.CDLL(str(library))
        argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                    ctypes.POINTER(CProfile), ctypes.c_void_p, ctypes.c_size_t]
        for name in ("i2_protect", "i2_unprotect"):
            function = getattr(cls.c, name)
            function.argtypes = argtypes
            function.restype = ctypes.c_int
        cls.c.i2_chacha20_block.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                             ctypes.c_void_p, ctypes.c_void_p]
        cls.c.i2_write_descriptor.argtypes = [ctypes.POINTER(CProfile), ctypes.c_void_p]
        cls.c.i2_write_descriptor.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls) -> None:
        if os.name == "nt":
            import _ctypes
            _ctypes.FreeLibrary(cls.c._handle)
        cls.c = None
        gc.collect()
        cls.temp.cleanup()

    def c_call(self, name: str, data: bytes, metadata: bytes, nonce: bytes,
               key: bytes, profile: Profile, output_capacity: int | None = None):
        output_capacity = len(data) if output_capacity is None else output_capacity
        buffers = [ctypes.create_string_buffer(item) for item in (data, metadata, nonce, key)]
        result = ctypes.create_string_buffer(max(output_capacity, 1))
        c_profile = CProfile(profile.model_profile_id, profile.split_id,
                             profile.channels, profile.length, profile.key_id,
                             profile.max_payload_bytes)
        code = getattr(self.c, name)(buffers[0], len(data), buffers[1], len(metadata),
                                      buffers[2], len(nonce), buffers[3], len(key),
                                      ctypes.byref(c_profile), result, output_capacity)
        return code, result.raw[:len(data)]

    def test_rfc8439_chacha_block(self) -> None:
        key = bytes(range(32))
        nonce = bytes.fromhex("000000090000004a00000000")
        expected = bytes.fromhex(
            "10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e"
            "d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e"
        )
        self.assertEqual(chacha20_block(key, 1, nonce), expected)
        result = ctypes.create_string_buffer(64)
        self.c.i2_chacha20_block(ctypes.create_string_buffer(key), 1,
                                  ctypes.create_string_buffer(nonce), result)
        self.assertEqual(result.raw, expected)

    def test_normative_vectors(self) -> None:
        for vector in VECTORS["valid"]:
            with self.subTest(vector=vector["id"]):
                profile = Profile(**vector["profile"])
                data = bytes.fromhex(vector["input_hex"])
                metadata = bytes.fromhex(vector["descriptor_hex"])
                nonce = bytes.fromhex(vector["nonce_hex"])
                key = bytes.fromhex(vector["key_hex"])
                expected = bytes.fromhex(vector["output_hex"])
                self.assertEqual(descriptor(profile), metadata)
                c_profile = CProfile(profile.model_profile_id, profile.split_id,
                                     profile.channels, profile.length, profile.key_id,
                                     profile.max_payload_bytes)
                c_metadata = ctypes.create_string_buffer(28)
                self.assertEqual(self.c.i2_write_descriptor(ctypes.byref(c_profile), c_metadata),
                                 STATUS["OK"])
                self.assertEqual(c_metadata.raw, metadata)
                self.assertEqual(protect(data, metadata, nonce, key, profile), expected)
                self.assertEqual(unprotect(expected, metadata, nonce, key, profile), data)
                self.assertEqual(self.c_call("i2_protect", data, metadata, nonce, key, profile),
                                 (STATUS["OK"], expected))
                self.assertEqual(self.c_call("i2_unprotect", expected, metadata, nonce, key, profile),
                                 (STATUS["OK"], data))

    def test_invalid_vectors(self) -> None:
        vector = VECTORS["valid"][0]
        source = bytes.fromhex(vector["input_hex"])
        original_metadata = bytes.fromhex(vector["descriptor_hex"])
        original_nonce = bytes.fromhex(vector["nonce_hex"])
        key = bytes.fromhex(vector["key_hex"])
        for case in VECTORS["invalid"]:
            with self.subTest(case=case["id"]):
                data, metadata, nonce = source, original_metadata, original_nonce
                fields = dict(vector["profile"])
                capacity = None
                if case["id"] == "version_2":
                    metadata = bytes([2]) + metadata[1:]
                elif case["id"] == "algorithm_2":
                    metadata = metadata[:1] + bytes([2]) + metadata[2:]
                elif case["id"] == "wrong_dtype":
                    metadata = metadata[:2] + bytes([1]) + metadata[3:]
                elif case["id"] == "oversized_shape":
                    changed = bytearray(metadata)
                    changed[12:14] = (256).to_bytes(2, "little")
                    changed[16:20] = (129).to_bytes(4, "little")
                    changed[24:28] = (33024).to_bytes(4, "little")
                    metadata = bytes(changed)
                elif case["id"] == "wrong_model":
                    fields["model_profile_id"] += 1
                elif case["id"] == "wrong_key_id":
                    fields["key_id"] += 1
                elif case["id"] == "short_payload":
                    data = data[:-1]
                elif case["id"] == "short_nonce":
                    nonce = nonce[:-1]
                elif case["id"] == "small_output_buffer_c":
                    capacity = len(data) - 1
                profile = Profile(**fields)
                expected = STATUS[case["expected"]]
                c_status, _ = self.c_call("i2_protect", data, metadata, nonce, key,
                                          profile, capacity)
                self.assertEqual(c_status, expected)
                if capacity is None:
                    with self.assertRaises(I2Error) as caught:
                        protect(data, metadata, nonce, key, profile)
                    self.assertEqual(caught.exception.code, case["expected"])

    def test_cross_language_shapes_and_tamper_limit(self) -> None:
        rng = random.Random(20260924)
        key = bytes(range(32))
        for channels, length in ((1, 1), (2, 33), (7, 15), (128, 128),
                                 (256, 1), (256, 128)):
            profile = Profile(0x87654321, 9, channels, length, 17)
            metadata = descriptor(profile)
            nonce = (3).to_bytes(4, "little") + channels.to_bytes(8, "little")
            data = rng.randbytes(channels * length)
            expected = protect(data, metadata, nonce, key, profile)
            status, c_output = self.c_call("i2_protect", data, metadata, nonce, key, profile)
            self.assertEqual(status, STATUS["OK"])
            self.assertEqual(c_output, expected)
            self.assertEqual(self.c_call("i2_unprotect", expected, metadata, nonce, key, profile),
                             (STATUS["OK"], data))
        vector = VECTORS["valid"][0]
        profile = Profile(**vector["profile"])
        metadata = bytes.fromhex(vector["descriptor_hex"])
        nonce = bytes.fromhex(vector["nonce_hex"])
        protected = bytearray.fromhex(vector["output_hex"])
        protected[0] ^= 1
        decoded = unprotect(bytes(protected), metadata, nonce, key, profile)
        self.assertNotEqual(decoded, bytes.fromhex(vector["input_hex"]))
        wrong_key = bytes([key[0] ^ 1]) + key[1:]
        self.assertNotEqual(unprotect(bytes.fromhex(vector["output_hex"]), metadata,
                                      nonce, wrong_key, profile),
                            bytes.fromhex(vector["input_hex"]))

    def test_c_error_does_not_write_output(self) -> None:
        vector = VECTORS["valid"][0]
        profile = Profile(**vector["profile"])
        c_profile = CProfile(profile.model_profile_id, profile.split_id,
                             profile.channels, profile.length, profile.key_id,
                             profile.max_payload_bytes)
        data = bytes.fromhex(vector["input_hex"])
        metadata = bytes([2]) + bytes.fromhex(vector["descriptor_hex"])[1:]
        nonce = bytes.fromhex(vector["nonce_hex"])
        key = bytes.fromhex(vector["key_hex"])
        output = ctypes.create_string_buffer(b"Z" * len(data))
        status = self.c.i2_protect(ctypes.create_string_buffer(data), len(data),
                                   ctypes.create_string_buffer(metadata), len(metadata),
                                   ctypes.create_string_buffer(nonce), len(nonce),
                                   ctypes.create_string_buffer(key), len(key),
                                   ctypes.byref(c_profile), output, len(data))
        self.assertEqual(status, STATUS["UNSUPPORTED_VERSION"])
        self.assertEqual(output.raw[:len(data)], b"Z" * len(data))


if __name__ == "__main__":
    unittest.main()
