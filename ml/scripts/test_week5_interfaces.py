"""I2 vectors/metadata and stored-scale wire component regression tests."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from p1 import Profile, descriptor, protect, unprotect, I2Error
import i2_reference as ref
import numpy as np
from week5_interfaces import active_profile, scale_wire_fp32_le, load_registry
from quantization import quantize_per_channel, dequantize_per_channel

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = '9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90'


def test_registry():
    registry = load_registry(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
    registry.update(model_profile_id=0x575435, key_id=1, status='PUBLIC_TEST_ONLY')
    for row in registry['splits']:
        # Deliberately explicit, different from s+1; never used for deployment.
        row['wire_split_id'] = 101 + row['split_point_s'] * 7
    return registry


class InterfaceTests(unittest.TestCase):
    def test_existing_vectors(self):
        vectors = json.loads((ROOT/'contracts/i2_ref/vectors.json').read_text())
        for v in vectors['valid']:
            profile = Profile(**v['profile'])
            args = [bytes.fromhex(v[k]) for k in ('descriptor_hex', 'nonce_hex', 'key_hex')]
            data, expected = bytes.fromhex(v['input_hex']), bytes.fromhex(v['output_hex'])
            self.assertEqual(descriptor(profile), args[0])
            self.assertEqual(protect(data, *args, profile), expected)
            self.assertEqual(unprotect(expected, *args, profile), data)

    def test_parameter_order_and_rejection_sampling(self):
        # First C bytes a, next C b. For bound 3 reject 0xffffffff,
        # then consume exactly the next 4 bytes as little-endian integer 1.
        stream = bytes([2, 4, 6, 10, 20, 30]) + struct.pack('<III', 0xffffffff, 1, 0)
        with patch.object(ref, '_stream', return_value=iter(stream)):
            self.assertEqual(ref._parameters(bytes(32), bytes(12), 3), ([3, 5, 7], [10, 20, 30], [2, 0, 1]))

    def test_wire_scale_stored_value(self):
        stored = np.array([[1, 0.00787353515625, 2**-14, 65504]], dtype='<f2')
        wire = scale_wire_fp32_le(stored)
        self.assertEqual(len(wire), 4 * stored.size)
        self.assertEqual(wire, b''.join(struct.pack('<f', float(v)) for v in stored[0]))
        np.testing.assert_array_equal(np.frombuffer(wire, dtype='<f4'), stored[0].astype(np.float32))
        for invalid in (stored.astype('<f4'), np.zeros((1, 2), dtype='<f2'),
                        np.array([[np.inf]], dtype='<f2'), np.ones((2, 2), dtype='<f2')):
            with self.assertRaises(ValueError):
                scale_wire_fp32_le(invalid)

    def test_explicit_registry_and_no_length_inference(self):
        registry = test_registry()
        for row in registry['splits']:
            profile = active_profile(registry, row['split_point_s'], row['i2_shape_NCL'], CHECKPOINT)
            self.assertEqual(profile.split_id, row['wire_split_id'])
            fields = struct.unpack('<BBBBIHHHHIII', descriptor(profile))
            self.assertEqual((fields[6], fields[7], fields[9]), tuple(row['i2_shape_NCL']))
        missing = load_registry(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
        for invalid in (missing, {**registry, 'checkpoint_sha256': '0'*64}):
            with self.assertRaises(I2Error):
                active_profile(invalid, 0, [1, 1, 360], CHECKPOINT)
        with self.assertRaises(I2Error):
            active_profile(registry, 0, [1, 2, 180], CHECKPOINT)  # identical length, wrong C/L
        invalid = copy.deepcopy(registry)
        invalid['splits'][1]['wire_split_id'] = invalid['splits'][0]['wire_split_id']
        with self.assertRaises(I2Error):
            active_profile(invalid, 0, [1, 1, 360], CHECKPOINT)
        for name, value in (('dtype', 'FLOAT32'), ('i2_layout', 'NC'),
                            ('channel_axis', 2), ('max_payload_bytes', 359)):
            invalid = copy.deepcopy(registry)
            invalid['splits'][0][name] = value
            with self.assertRaises(I2Error):
                active_profile(invalid, 0, [1, 1, 360], CHECKPOINT)

    def test_metadata_errors_both_directions(self):
        p = Profile(1, 73, 3, 4, 2)
        metadata = descriptor(p)
        changes = [(0, b'\x02', 'UNSUPPORTED_VERSION'), (1, b'\x02', 'UNSUPPORTED_ALGORITHM'),
                   (2, b'\x01', 'INVALID_METADATA'), (3, b'\x02', 'INVALID_METADATA'),
                   (10, b'\x02\x00', 'INVALID_METADATA'), (14, b'\x01\x00', 'INVALID_METADATA'),
                   (8, b'\x4a\x00', 'PROFILE_MISMATCH'),
                   (20, struct.pack('<I', 3), 'KEY_SCOPE_MISMATCH'),
                   (24, struct.pack('<I', 11), 'LENGTH_MISMATCH')]
        for fn in (protect, unprotect):
            for offset, value, code in changes:
                bad = metadata[:offset] + value + metadata[offset+len(value):]
                with self.assertRaises(I2Error) as caught:
                    fn(bytes(12), bad, bytes(12), bytes(32), p)
                self.assertEqual(caught.exception.code, code)
            for args, code in (([bytes(11), metadata, bytes(12), bytes(32), p], 'LENGTH_MISMATCH'),
                               ([bytes(12), metadata[:-1], bytes(12), bytes(32), p], 'INVALID_METADATA'),
                               ([bytes(12), metadata, bytes(11), bytes(32), p], 'INVALID_NONCE'),
                               ([bytes(12), metadata, bytes(12), bytes(31), p], 'KEY_UNAVAILABLE')):
                with self.assertRaises(I2Error) as caught:
                    fn(*args)
                self.assertEqual(caught.exception.code, code)

    def test_unprotect_before_dequantize(self):
        z = np.array([[[1, .2, -.3], [10, -7, 3], [100, 20, 60]]], dtype=np.float32)
        q, scales = quantize_per_channel(z)
        p = Profile(1, 73, 3, 3, 2)
        nonce, key = bytes(12), bytes(range(32))
        protected = protect(q.tobytes(), descriptor(p), nonce, key, p)
        restored = np.frombuffer(unprotect(protected, descriptor(p), nonce, key, p), dtype=np.int8).reshape(q.shape)
        np.testing.assert_array_equal(restored, q)
        np.testing.assert_array_equal(dequantize_per_channel(restored, scales), dequantize_per_channel(q, scales))
        # Raw affine/permuted bytes do not have the original scales' meaning.
        wrong = np.frombuffer(protected, dtype=np.int8).reshape(q.shape).astype(np.float32) * scales.astype(np.float32)[..., None]
        self.assertFalse(np.array_equal(wrong, dequantize_per_channel(q, scales)))

    def test_strict_accuracy_boundary(self):
        from evaluate_week5 import strict_accuracy_gate
        self.assertFalse(strict_accuracy_gate(1000, 995, 1000))  # exactly 0.5 pp
        self.assertTrue(strict_accuracy_gate(1000, 996, 1000))
        self.assertTrue(strict_accuracy_gate(1000, 999, 1000))
        self.assertTrue(strict_accuracy_gate(990, 995, 1000))  # improvement
        for counts in ((1, 1, 0), (1001, 995, 1000), (1000, -1, 1000)):
            with self.assertRaises(Exception):
                strict_accuracy_gate(*counts)


if __name__ == '__main__':
    unittest.main(verbosity=2)
