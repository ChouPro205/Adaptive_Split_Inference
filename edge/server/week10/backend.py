"""Authenticated KV260 cache backend and bounded native transport (Python 3.9+)."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import platform
import select
import struct
import subprocess
import threading
import time

import numpy as np
from evidence import models, sha

SHAPES = ((1, 360), (16, 360), (16, 180), (32, 180), (32, 90),
          (48, 90), (48, 45), (64, 45), (64, 22), (32,), (5,))


class Transport:
    """One outstanding transaction. Any protocol error/timeout poisons the process."""
    def __init__(self, command, log_path, env=None):
        self.log = Path(log_path).open('xb')
        self.buffer = b''
        self.alive = False
        self.job = 0
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.log, env=env, bufsize=0)
            os.set_blocking(self.process.stdin.fileno(), False)
            self.alive = True
            ready = self.line(time.monotonic() + 30)
            if ready != {'event': 'ready', 'protocol': 1, 'execution': 'root_graph'}:
                raise ValueError('Unexpected worker readiness')
        except BaseException:
            self.close()
            raise

    def line(self, deadline):
        while True:
            if b'\n' in self.buffer:
                raw, self.buffer = self.buffer.split(b'\n', 1)
                try:
                    row = json.loads(raw)
                except (ValueError, UnicodeError):
                    self.log.write(b'NATIVE_STDOUT_DIAGNOSTIC ' + raw + b'\n')
                    continue
                if not isinstance(row, dict):
                    raise ValueError('Worker response must be a JSON object')
                return row
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('Worker response deadline exceeded')
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError('Native EOF; inspect worker.log')
            self.buffer += data
            if len(self.buffer) > 1024 * 1024:
                raise ValueError('Worker stdout exceeds limit')

    def transact(self, op, split, data=b'', timeout=4):
        if not self.alive:
            raise RuntimeError('Worker faulted; start a new session after investigation')
        try:
            self.job += 1
            if self.job > 0xffffffff:
                raise RuntimeError('Internal job counter exhausted')
            deadline = time.monotonic() + timeout
            pending = memoryview(struct.pack('<4I', op, self.job, split, len(data)) + data)
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                    raise TimeoutError('Worker input deadline exceeded')
                try:
                    written = os.write(self.process.stdin.fileno(), pending)
                except BlockingIOError:
                    continue
                if written <= 0:
                    raise RuntimeError('Worker input closed')
                pending = pending[written:]
            row = self.line(deadline)
            if (row.get('job_id'), row.get('split'), row.get('event')) != (
                    self.job, split, 'selected' if op == 1 else 'result'):
                raise ValueError('Stale/wrong native job, split or event')
            return row
        except BaseException:
            self.close()
            raise

    def close(self):
        self.alive = False
        process = getattr(self, 'process', None)
        if process is not None:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if process.stdout:
                process.stdout.close()
        if not self.log.closed:
            self.log.close()


def authenticated_backend(binary, deploy, cpu_ops, expected_file):
    binary, deploy, cpu_ops = map(lambda p: Path(p).resolve(), (binary, deploy, cpu_ops))
    if platform.system() != 'Linux' or platform.machine() != 'aarch64':
        raise ValueError('Real backend requires KV260 Linux aarch64')
    header = binary.read_bytes()[:20]
    if header[:5] != b'\x7fELF\x02' or header[5:6] != b'\x01' or header[18:20] != b'\xb7\x00':
        raise ValueError('Worker must be little-endian ARM64 ELF')
    expected = json.loads(Path(expected_file).read_text())
    model_hashes = models(deploy)
    if expected['models'] != model_hashes:
        raise ValueError('Models differ from prepared source session')
    actual = {p.name: sha(p) for p in cpu_ops.glob('libvart_op_imp_*.so')}
    if actual != expected['plugins']:
        raise ValueError('CPU plugins differ from verified baseline')
    return {'backend': 'KV260_ROOT_CPU_DPU_MODEL_CACHE', 'models': model_hashes,
            'plugins': actual, 'worker_sha256': sha(binary),
            'bundle_inventory_sha256': sha(deploy / 'sha256sum_bundle.txt')}


class CacheBackend:
    def __init__(self, binary, deploy, cpu_ops, expected_file, log_path):
        self.metadata = authenticated_backend(binary, deploy, cpu_ops, expected_file)
        env = os.environ.copy()
        env['LD_LIBRARY_PATH'] = str(Path(cpu_ops).resolve()) + ':' + env.get('LD_LIBRARY_PATH', '')
        self.transport = Transport([str(Path(binary).resolve()), str(Path(deploy).resolve() / 'release/models')], log_path, env)
        self.lock = threading.Lock()
        self.previous_s = None
        self.contexts = {}

    def infer(self, split, values):
        if not isinstance(split, int) or not 0 <= split <= 10:
            raise ValueError('split must be 0..10')
        data = np.asarray(values, dtype='<f4')
        if data.size != math.prod(SHAPES[split]) or not np.isfinite(data).all():
            raise ValueError('Input shape/values differ from split contract')
        data = data.reshape((1, *SHAPES[split])).tobytes()
        with self.lock:
            try:
                start = time.monotonic_ns()
                selected = self.transport.transact(1, split, timeout=30)
                switch_ms = (time.monotonic_ns() - start) / 1e6
                hit = split < 10 and split in self.contexts
                context_id = selected.get('context_id')
                if (selected.get('model_cache_hit') is not hit or
                        selected.get('load_count') != (1 if split < 10 else 0) or
                        (split < 10 and context_id != split + 1) or
                        (split == 10 and context_id is not None)):
                    raise ValueError('Native cache counters/context identity invalid')
                native_ms = selected.get('native_select_ms')
                if not isinstance(native_ms, (int, float)) or not math.isfinite(native_ms) or native_ms < 0:
                    raise ValueError('Invalid native select duration')
                if split < 10:
                    self.contexts[split] = context_id
                if selected.get('contexts_count') != len(self.contexts):
                    raise ValueError('Native contexts count differs')
                if split == 10:
                    result = {'logits': np.frombuffer(data, dtype='<f4').tolist(), 'tail_ms': None}
                else:
                    result = self.transport.transact(2, split, data)
                    tail_ms = result.get('tail_ms')
                    if not isinstance(tail_ms, (int, float)) or not math.isfinite(tail_ms) or tail_ms < 0:
                        raise ValueError('Invalid native tail duration')
                logits = result.get('logits', [])
                if len(logits) != 5 or not all(math.isfinite(x) for x in logits):
                    raise ValueError('Invalid final logits')
                row = dict(result, **{k: selected[k] for k in (
                    'model_cache_hit', 'context_id', 'load_count', 'contexts_count', 'native_select_ms')})
                row.update(previous_s=self.previous_s, split_s=split, switch_ms=switch_ms,
                           load_ms=native_ms if split < 10 and not hit else None,
                           worker_pid=self.transport.process.pid)
                self.previous_s = split
                return row
            except BaseException:
                self.transport.close()
                raise

    def close(self):
        self.transport.close()
