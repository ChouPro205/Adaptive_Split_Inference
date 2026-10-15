"""I1 v1 addendum r1 profile boundaries on the actual producers/consumers.

Checks q in [-127,127], q=-128 rejection at the quantized-tensor level only,
payload length C*L, valid wire scales and the packet bounds of the approved
registry. Host only; no I1 codec or transport exists yet.
"""
import argparse
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from week5_common import ROOT, Quantizer, quantize_per_channel, dequantize_per_channel, to_ncl
from week5_interfaces import active_profile, scale_wire_fp32_le
from p1 import I2Error, descriptor, protect, unprotect

REGISTRY = json.loads((ROOT / 'contracts/sv3_week5_approved_registry_v2.json').read_text(encoding='utf-8'))
PUBLIC_TEST_KEY = bytes(range(32))  # Public I2 vector key; never deployment material.


class ProfileBoundaryTests(unittest.TestCase):
    def both(self, z):
        q, s = quantize_per_channel(z)
        qc, sc = self.c.quantize(z)
        self.assertEqual((q.tobytes(), s.tobytes()), (qc.tobytes(), sc.tobytes()))
        return q, s

    def test_extremes_map_to_pm127_never_minus128(self):
        # 1023/127 and 3/127 round down in FP16, so |x|/scale exceeds 127 and must clip.
        z = np.array([[[-1023, -0.5, 0, 0.5, 1023], [-3, 3, 1, -1, 0]]], np.float32)
        q, s = self.both(z)
        for channel, maximum in ((0, 1023), (1, 3)):
            self.assertLess(np.float32(s[0, channel]), np.float32(maximum) / np.float32(127))
        self.assertEqual(q[0, 0].tolist(), [-127, 0, 0, 0, 127])
        self.assertEqual(q[0, 1].tolist(), [-127, 127, 42, -42, 0])
        self.assertNotIn(-128, q)
        restored = dequantize_per_channel(q, s)
        self.assertEqual(restored.tobytes(), self.c.dequantize(q, s).tobytes())

    def test_minus128_rejected_by_profile_consumers(self):
        q = np.array([[[-128, 1, 2]]], np.int8)
        scale = np.array([[1.0]], '<f2')
        with self.assertRaises(ValueError):
            dequantize_per_channel(q, scale)
        with self.assertRaises(ValueError):
            self.c.dequantize(q, scale)
        q[0, 0, 0] = -127
        self.assertEqual(dequantize_per_channel(q, scale).ravel().tolist(), [-127.0, 1.0, 2.0])

    def test_wire_scales_valid_and_invalid(self):
        stored = np.array([[2**-14, 1.0, 65504]], '<f2')
        wire = scale_wire_fp32_le(stored)
        self.assertEqual(wire, struct.pack('<3f', 2**-14, 1.0, 65504.0))
        for bits in (0x0000, 0x0001, 0x8000, 0xbc00, 0x7c00, 0x7e00):
            bad = np.array([[bits]], '<u2').view('<f2')
            with self.assertRaises(ValueError):
                scale_wire_fp32_le(bad)
            with self.assertRaises(ValueError):
                self.c.dequantize(np.zeros((1, 1, 1), np.int8), bad)

    def test_payload_length_and_registry_bounds(self):
        limits = REGISTRY['buffer_limits']
        for side in ('device', 'edge'):
            self.assertEqual(limits[side]['per_channel_quant_metadata_bytes'], 4 + 8 * limits[side]['channels'])
            self.assertEqual(limits[side]['fp32_le_scale_array_bytes'], 4 * limits[side]['channels'])
        rng = np.random.default_rng(20261015)
        for row in REGISTRY['splits']:
            n, c, l = row['i2_shape_NCL']
            z = rng.normal(size=row['shape_original']).astype(np.float32)
            q, s = self.both(to_ncl(z, row['split_point_s']))
            self.assertEqual(q.size, c * l)
            self.assertLessEqual(q.size, row['max_payload_bytes'])
            self.assertLessEqual(c, limits['device']['channels'])
            self.assertEqual(len(scale_wire_fp32_le(s)), 4 * c)
        channels, payload = limits['device']['channels'], limits['device']['payload_bytes']
        v1_packet = 32 + (12 + 4 * 3) + limits['device']['per_channel_quant_metadata_bytes'] + payload + 4
        self.assertEqual(v1_packet, 6336)
        self.assertEqual(v1_packet + 4 + 28 + 12, REGISTRY['packet_planning']['protected_budget_bytes'])

    def test_0x80_allowed_in_transformed_bytes_only(self):
        row = REGISTRY['splits'][2]
        profile = active_profile(REGISTRY, 2, row['i2_shape_NCL'], REGISTRY['checkpoint_sha256'])
        z = np.random.default_rng(20261015).normal(size=row['i2_shape_NCL']).astype(np.float32)
        q, s = self.both(z)
        nonce = struct.pack('<IQ', REGISTRY['sender_scope']['sender_ids'][0], 1)
        meta = descriptor(profile)
        protected = protect(q.tobytes(), meta, nonce, PUBLIC_TEST_KEY, profile)
        self.assertIn(0x80, protected)  # Valid transformed byte, not a q value.
        restored = np.frombuffer(unprotect(protected, meta, nonce, PUBLIC_TEST_KEY, profile), np.int8).reshape(q.shape)
        self.assertEqual(restored.tobytes(), q.tobytes())
        dequantize_per_channel(restored, s)
        tampered = q.copy()
        tampered[0, 0, 0] = -128  # I2 carries it bit-exact; the profile consumer rejects it.
        roundtrip = unprotect(protect(tampered.tobytes(), meta, nonce, PUBLIC_TEST_KEY, profile), meta, nonce, PUBLIC_TEST_KEY, profile)
        self.assertEqual(roundtrip, tampered.tobytes())
        with self.assertRaises(ValueError):
            dequantize_per_channel(np.frombuffer(roundtrip, np.int8).reshape(q.shape), s)
        with self.assertRaises(I2Error):
            protect(q.tobytes()[:-1], meta, nonce, PUBLIC_TEST_KEY, profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='gcc')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='i1-profile-', ignore_cleanup_errors=True) as directory:
        ProfileBoundaryTests.c = Quantizer(directory, args.compiler)
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ProfileBoundaryTests))
        del ProfileBoundaryTests.c
    sys.exit(0 if result.wasSuccessful() else 1)
