"""Multi-split receiver tests with a HOST fake backend; not real logits/BLE."""
import importlib.util
from pathlib import Path
import struct
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'edge/server/week10'))
spec = importlib.util.spec_from_file_location('week10_service_under_test', ROOT / 'edge/server/week10/service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
i1 = service.i1


class Backend:
    def __init__(self):
        self.calls = []
        self.loaded = set()
        self.previous = None

    def infer(self, s, values):
        self.calls.append((s, values))
        hit = s in self.loaded
        if s < 10:
            self.loaded.add(s)
        row = dict(logits=values if s == 10 else [float(s), 1., 2., 3., 4.],
                   previous_s=self.previous, switch_ms=1., native_select_ms=.1,
                   load_ms=None if hit or s == 10 else .1, tail_ms=None if s == 10 else 1.,
                   worker_pid=123, context_id=s + 1 if s < 10 else None,
                   load_count=1 if s < 10 else 0, contexts_count=len(self.loaded), model_cache_hit=hit)
        self.previous = s
        return row


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.b = Backend()
        self.clock = [0.]
        self.key = bytes(range(32))
        self.r = service.Receiver(self.b, self.key, clock=lambda: self.clock[0])

    def packet(self, s=2, rid=1, seq=None, byte=1):
        split = self.r.profile.splits[256 + s]
        q = bytes([byte] * (split.channels * split.length))
        descriptor = nonce = None
        if seq is not None:
            p = i1.i2.Profile(self.r.profile.model_profile_id, 256 + s,
                             split.channels, split.length, 65537, len(q))
            descriptor = i1.i2.descriptor(p)
            nonce = struct.pack('<IQ', 131073, seq)
            q = i1.i2.protect(q, descriptor, nonce, self.key, p)
        return i1.encode_request(rid, self.r.profile.model_profile_id, 256 + s,
                                 split.channels, split.length, [.5] * split.channels, q, descriptor, nonce)

    def test_all_splits_and_identity(self):
        for s in range(11):
            response, row = self.r.handle('peer', self.packet(s, rid=s + 1), 0)
            self.assertEqual(i1.parse_response(response, s + 1, 6380)[0], 'OK')
            self.assertEqual(row['split_s'], s)
        self.assertEqual(self.b.calls[-1][1], [.5] * 5)
        self.assertEqual(self.b.loaded, set(range(10)))

    def test_retry_model_cache_and_conflict_are_different(self):
        p = self.packet()
        first, row = self.r.handle('peer', p, 0)
        response, retry = self.r.handle('peer', p, 1)
        self.assertEqual(first, response)
        self.assertTrue(retry['response_cache_hit'])
        self.assertIsNone(retry['switch_ms'])
        _, new = self.r.handle('peer', self.packet(rid=2, byte=2), 2)
        self.assertFalse(new['response_cache_hit'])
        self.assertTrue(new['model_cache_hit'])
        self.assertEqual(len(self.b.calls), 2)
        _, conflict = self.r.handle('peer', self.packet(5, rid=1), 3)
        self.assertEqual(conflict['result'], 'DUPLICATE_CONFLICT')
        self.assertEqual(len(self.b.calls), 2)

    def test_nonce_and_p0_p1_values(self):
        _, plain = self.r.handle('peer', self.packet(rid=1), 0)
        p = self.packet(rid=2, seq=1)
        _, protected = self.r.handle('peer', p, 1)
        self.assertEqual(self.b.calls[0], self.b.calls[1])
        self.assertEqual(plain['q_sha256'], protected['q_sha256'])
        self.r.handle('peer', p, 2)
        _, reuse = self.r.handle('peer', self.packet(rid=3, seq=1), 3)
        self.assertEqual(reuse['result'], 'INVALID_NONCE')
        self.assertEqual(len(self.b.calls), 2)

    def test_corrupt_or_invalid_packet_never_calls_backend(self):
        p = bytearray(self.packet())
        p[-1] ^= 1
        self.assertIsNone(self.r.handle('p', bytes(p), 0)[0])
        p = bytearray(self.packet(rid=2))
        p[36:38] = struct.pack('<H', 2)
        _, row = self.r.handle('p', i1.recrc(p), 0)
        self.assertEqual(row['result'], 'UNSUPPORTED_SPLIT')
        _, row = self.r.handle('p', self.packet(rid=3, byte=128), 0)
        self.assertEqual(row['result'], 'UNSUPPORTED_QUANTIZATION')
        self.assertEqual(self.b.calls, [])

    def test_concurrent_retry_attaches_and_new_request_is_busy(self):
        entered, release = threading.Event(), threading.Event()
        original = self.b.infer
        def delayed(s, values):
            entered.set()
            release.wait(2)
            return original(s, values)
        self.b.infer = delayed
        rows = []
        t = threading.Thread(target=lambda: rows.append(self.r.handle('p', self.packet(), 0)))
        t.start()
        self.assertTrue(entered.wait(1))
        _, busy = self.r.handle('p', self.packet(rid=2), 1)
        self.assertEqual(busy['result'], 'EDGE_BUSY')
        retry = threading.Thread(target=lambda: rows.append(self.r.handle('p', self.packet(), 2)))
        retry.start()
        release.set()
        t.join()
        retry.join()
        self.assertEqual(rows[0][0], rows[1][0])
        self.assertEqual(len(self.b.calls), 1)

    def test_error_identity_cache_bound_and_expiry(self):
        for i in range(1, 20):
            self.r.handle('p', self.packet(rid=i), 0)
        self.assertLessEqual(len(self.r.cache), 16)
        self.clock[0] = 61
        self.r.handle('other', self.packet(), 1)
        self.assertEqual(len(self.r.cache), 1)
        self.b.infer = lambda s, v: dict(logits=[0.] * 5)
        _, row = self.r.handle('other', self.packet(10, rid=2), 2)
        self.assertEqual(row['result'], 'INFERENCE_FAILED')


if __name__ == '__main__':
    unittest.main()
