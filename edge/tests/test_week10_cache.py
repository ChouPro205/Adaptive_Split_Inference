"""HOST cache/protocol tests. Mock VART is not a hardware/numeric timing proof."""
from pathlib import Path
import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'edge/server/week10'))
from backend import CacheBackend, SHAPES, Transport
import numpy as np


class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        inc = cls.folder / 'include'
        fixture = ROOT / 'edge/tests/fixtures/week10_mock_vart.hpp'
        for header in ('glog/logging.h', 'vitis/ai/graph_runner.hpp', 'xir/graph/graph.hpp',
                       'xir/attrs/attrs.hpp', 'xir/tensor/tensor.hpp'):
            p = inc / header
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('#include "' + str(fixture) + '"\n')
        cls.binary = cls.folder / 'mock-vart-worker'
        subprocess.run(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(inc),
                        str(ROOT / 'edge/runtime/model_cache/tail_cache_worker.cpp'), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.addCleanup(self.case.cleanup)

    def backend(self):
        backend = CacheBackend.__new__(CacheBackend)
        backend.transport = Transport([str(self.binary), '/MOCK_NOT_A_MODEL'], Path(self.case.name) / 'worker.log')
        backend.lock = threading.Lock()
        backend.previous_s = None
        backend.contexts = {}
        self.addCleanup(backend.close)
        return backend

    def test_actual_cpp_reuses_context_and_executes_new_input(self):
        b = self.backend()
        rows = []
        for i, s in enumerate((2, 5, 2, 8, 5, 2)):
            rows.append(b.infer(s, np.full((1, *SHAPES[s]), i + 1, dtype='<f4')))
        self.assertEqual([r['model_cache_hit'] for r in rows], [False, False, True, False, True, True])
        self.assertEqual([r['context_id'] for r in rows], [3, 6, 3, 9, 6, 3])
        self.assertEqual([r['logits'][0] for r in rows], list(range(1, 7)))
        self.assertEqual(rows[-1]['contexts_count'], 3)
        b.close()
        self.assertEqual(b.transport.process.returncode, 0)

    def test_ten_contexts_shapes_and_s10_identity(self):
        b = self.backend()
        for s in range(10):
            r = b.infer(s, np.ones(SHAPES[s], dtype='<f4'))
            self.assertEqual(r['contexts_count'], s + 1)
        identity = [63.5, -31.75, 0., 2., -.125]
        r = b.infer(10, identity)
        self.assertEqual(r['logits'], identity)
        self.assertEqual(r['contexts_count'], 10)
        self.assertIsNone(r['tail_ms'])
        self.assertIsNone(r['context_id'])
        self.assertTrue(b.infer(2, np.ones(SHAPES[2]))['model_cache_hit'])

    def test_native_rejects_bad_op_length_and_truncation(self):
        for packet in (struct.pack('<4I', 2, 1, 2, 0), struct.pack('<4I', 1, 1, 11, 0),
                       struct.pack('<4I', 1, 1, 2, 4), b'\x01\x00'):
            p = subprocess.run([str(self.binary), '/MOCK'], input=packet, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn(b'CACHE_WORKER_FAILED', p.stderr)

    def test_bad_shape_nonfinite_rejected_before_write(self):
        b = self.backend()
        for s, values in ((2, [1]), (10, [float('nan')] * 5), (-1, [])):
            with self.assertRaises(ValueError):
                b.infer(s, values)
        self.assertEqual(b.transport.job, 0)

    def test_stale_response_or_timeout_faults_transport(self):
        for response in ('print(json.dumps(dict(event="selected",job_id=999,split=s)))', 'time.sleep(2)'):
            script = ('import json,struct,sys,time\n'
                      'print(json.dumps(dict(event="ready",protocol=1,execution="root_graph")),flush=True)\n'
                      'op,j,s,n=struct.unpack("<4I",sys.stdin.buffer.read(16))\n' + response + '\n')
            log = Path(self.case.name) / ('timeout.log' if 'sleep' in response else 'stale.log')
            t = Transport([sys.executable, '-u', '-c', script], log)
            with self.assertRaises((ValueError, TimeoutError)):
                t.transact(1, 2, timeout=.05)
            self.assertFalse(t.alive)
            with self.assertRaises(RuntimeError):
                t.transact(1, 2)


if __name__ == '__main__':
    unittest.main()
