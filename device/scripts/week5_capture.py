"""Strict streaming Week 5 debug parser shared by collector and offline checker."""
import re
import numpy as np
from week5_common import need, quantize_per_channel, to_ncl

MIXED_SEQUENCE = [(19,10), (0,0), (7,8), (3,2), (19,1), (0,10), (12,0), (1,9),
                  (18,4), (2,7), (14,6), (5,3), (11,5), (0,2), (19,10), (0,0)]
COMMAND_BANNER = 'COMMAND RUN n s (n=0..19 s=0..10)'

def sequence():
    return [(n, s) for n in range(20) for s in range(11)] + MIXED_SEQUENCE

def banner(binding):
    return f'READY WEEK5 V1 fw={binding["firmware_id"]} r3=80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c model={binding["model_anchor"]} quant={binding["quant_anchor"]} samples=20 splits=11'

class CaptureParser:
    def __init__(self, binding, manifest, goldens, simulated=False, expected=None):
        self.binding, self.manifest, self.goldens = binding, manifest, goldens
        self.simulated = simulated
        self.expected = sequence() if expected is None else expected
        self.pending = b''
        self.state = 'origin' if simulated else 'banner'
        self.rows = []
        self.words = []
        self.case_index = 0
        self.entries = {(e['sample_index'], e['split_point_s']): e for e in manifest['entries']}
        self.boot_lines = set()

    def feed(self, chunk):
        need(isinstance(chunk, bytes), 'CDC parser requires raw bytes')
        self.pending += chunk
        while b'\n' in self.pending:
            raw, self.pending = self.pending.split(b'\n', 1)
            need(len(raw) <= 4096 and b'\r' not in raw.rstrip(b'\r'), 'Invalid CDC line')
            self.line(raw.rstrip(b'\r').decode('ascii', errors='strict'))
        need(len(self.pending) <= 4096, 'CDC partial line too long')

    def line(self, line):
        if self.state == 'origin':
            need(line == 'SIMULATED HOST WEEK5', 'Missing simulated fixture label')
            self.state = 'banner'; return
        if self.state == 'banner':
            if re.fullmatch(r'\*\*\* (?:Booting nRF Connect SDK v3\.4\.0|Using Zephyr OS v4\.4\.0)(?:-[0-9a-f]+)? \*\*\*', line):
                need(line not in self.boot_lines and len(self.boot_lines) < 2, 'Repeated boot before READY')
                self.boot_lines.add(line); return
            need(line == banner(self.binding), 'Wrong firmware/anchors/banner or simulated data in real mode')
            self.state = 'command'; return
        if self.state == 'command':
            need(line == COMMAND_BANNER, 'Unexpected command banner')
            self.state = 'begin'; return
        need(self.case_index < len(self.expected), 'Duplicate/trailing capture data')
        n, s = self.expected[self.case_index]
        entry = self.entries[n, s]
        sid = entry['sample_id']
        shape = entry['shape_original']
        qshape = entry['quantization_shape_NCL']
        count, channels = int(np.prod(shape)), qshape[1]
        headers = {
            'begin': f'BEGIN {n} {sid} {s} RUN',
            'head': f'HEAD {n} {sid} {s} FP32 {entry["layout_original"]} {len(shape)} ' + ' '.join(map(str, shape)) + f' {count}',
            'endhead': f'ENDHEAD {n} {s}',
            'q': f'Q {n} {s} NCL 1 {channels} {qshape[2]} {count}',
            'endq': f'ENDQ {n} {s}',
            'scale': f'SCALE {n} {s} FP16LE 1 {channels} {channels}',
            'endscale': f'ENDSCALE {n} {s}',
            'done': f'DONE {n} {s} RUN'}
        next_state = {'begin':'head', 'head':'head-data', 'endhead':'q', 'q':'q-data',
                      'endq':'scale', 'scale':'scale-data', 'endscale':'done', 'done':'begin'}
        if self.state in headers:
            need(line == headers[self.state], f'Capture order/identity/shape mismatch: expected {headers[self.state]!r}, got {line!r}')
            if self.state == 'done':
                self.validate(n, s, entry)
                self.case_index += 1
            self.state = next_state[self.state]
            self.words = []
            return
        width, group, total, end, target = {
            'head-data': (8, 16, count, 'endhead', 'head_bits'),
            'q-data': (2, 32, count, 'endq', 'q_bits'),
            'scale-data': (4, 16, channels, 'endscale', 'scale_bits')}[self.state]
        words = line.split(' ')
        need(len(words) == min(group, total-len(self.words)) and
             all(re.fullmatch(r'[0-9a-f]{' + str(width) + '}', w) for w in words), 'Corrupt or truncated hex payload')
        self.words.extend(int(w, 16) for w in words)
        if len(self.words) == total:
            setattr(self, target, self.words)
            self.state = end

    def validate(self, n, s, entry):
        actual = np.array(self.head_bits, '<u4').view('<f4').reshape(entry['shape_original'])
        golden = self.goldens[s][n:n+1]
        need(actual.shape == golden.shape and np.isfinite(actual).all(), 'Invalid FP32 activation')
        error = float(np.max(np.abs(actual.astype(np.float64)-golden.astype(np.float64))))
        need(error < 1e-3, f'FP32 head gate failed n{n}s{s}: {error}')
        if s == 0:
            need(actual.tobytes() == golden.tobytes(), 's0 identity bitwise gate failed')
        q = np.array(self.q_bits, np.uint8).view(np.int8).reshape(entry['quantization_shape_NCL'])
        scale = np.array(self.scale_bits, '<u2').view('<f2').reshape(1, -1)
        qo, so = quantize_per_channel(to_ncl(actual, s))
        need(q.tobytes() == qo.tobytes(), f'INT8 differs from actual FP32 oracle n{n}s{s}')
        need(scale.tobytes() == so.tobytes(), f'FP16 scale differs from actual FP32 oracle n{n}s{s}')
        qg, sg = quantize_per_channel(to_ncl(golden, s))
        qdiff = np.flatnonzero(q.ravel() != qg.ravel())
        sdiff = np.flatnonzero(scale.view('<u2').ravel() != sg.view('<u2').ravel())
        self.rows.append({'sample_index': n, 'sample_id': entry['sample_id'], 'split': s, 'shape': entry['shape_original'],
            'max_abs_error': error, 'oracle_exact': True, 'golden_q_differences': qdiff.tolist(),
            'golden_scale_differences': sdiff.tolist(),
            'explanation': 'All transmitted bytes/bits match reference on actual activation; golden differences originate in FP32 head' if len(qdiff) or len(sdiff) else None})

    def finish(self):
        need(not self.pending and self.state == 'begin' and self.case_index == len(self.expected), 'Incomplete capture')
        return {'status': 'PASS', 'scope': 'SIMULATED_HOST_ONLY' if self.simulated else 'REAL_MCU_CAPTURE',
                'primary_cases': min(220,len(self.expected)), 'mixed_cases': max(0,len(self.expected)-220), 'rows': self.rows,
                'mcu_validation': 'PENDING' if self.simulated else 'PASS', 'timing': 'PENDING', 'runtime_stack': 'PENDING'}
