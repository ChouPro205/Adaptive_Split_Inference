"""Simulated HOST fixtures and fake transport; never opens a serial port."""
import argparse
import contextlib
import io
from pathlib import Path
import unittest
import numpy as np
from week5_common import ROOT, PACKAGE, authenticate, firmware_binding, source_hashes, write_json, quantize_per_channel, to_ncl
from week5_capture import CaptureParser, sequence, banner, COMMAND_BANNER
from collect_week5 import collect

def transaction(n, s, manifest, values):
    e = next(e for e in manifest['entries'] if e['sample_index'] == n and e['split_point_s'] == s)
    z = values[s][n:n+1]
    q, scale = quantize_per_channel(to_ncl(z, s))
    shape, qs = e['shape_original'], e['quantization_shape_NCL']
    lines = [f'BEGIN {n} {e["sample_id"]} {s} RUN',
             f'HEAD {n} {e["sample_id"]} {s} FP32 {e["layout_original"]} {len(shape)} ' + ' '.join(map(str, shape)) + f' {z.size}']
    def words(array, width, group):
        flat = array.ravel()
        return [' '.join(f'{int(v):0{width}x}' for v in flat[i:i+group]) for i in range(0, len(flat), group)]
    lines += words(z.view('<u4'), 8, 16) + [f'ENDHEAD {n} {s}', f'Q {n} {s} NCL 1 {qs[1]} {qs[2]} {q.size}']
    lines += words(q.view(np.uint8), 2, 32) + [f'ENDQ {n} {s}', f'SCALE {n} {s} FP16LE 1 {qs[1]} {qs[1]}']
    lines += words(scale.view('<u2'), 4, 16) + [f'ENDSCALE {n} {s}', f'DONE {n} {s} RUN']
    return ('\r\n'.join(lines) + '\r\n').encode('ascii')

class Tests(unittest.TestCase):
    def parser(self, expected=None, simulated=True):
        return CaptureParser(self.binding, self.manifest, self.goldens, simulated, expected)

    def test_full_fixture_chunking(self):
        for width in (1, 7, 4096, 65536):
            parser = self.parser()
            for i in range(0, len(self.fixture), width):
                parser.feed(self.fixture[i:i+width])
            result = parser.finish()
            self.assertEqual(result['scope'], 'SIMULATED_HOST_ONLY')
            self.assertEqual(result['mcu_validation'], 'PENDING')
            self.assertEqual(len(result['rows']), 236)

    def test_fake_collector_chunks_and_pacing(self):
        owner = self
        class Transport:
            def __init__(self):
                self.pending = owner.prefix
                self.index = 0
            def read(self, count):
                count = min(count, 37)
                chunk, self.pending = self.pending[:count], self.pending[count:]
                return chunk
            def write(self, command):
                owner.assertEqual(self.pending, b'', 'Collector sent next command before consuming prior data')
                n, s = sequence()[self.index]
                owner.assertEqual(command, f'RUN {n} {s}\n'.encode())
                self.pending = transaction(n, s, owner.manifest, owner.actuals)
                self.index += 1
                return len(command)
        stream = io.BytesIO()
        with contextlib.redirect_stdout(io.StringIO()):
            result = collect(Transport(), stream, self.parser(), timeout=60)
        self.assertEqual(stream.getvalue(), self.fixture)
        self.assertEqual(result['mcu_validation'], 'PENDING')

    def test_corruption_truncation_identity_order(self):
        primary = self.prefix + transaction(0, 0, self.manifest, self.actuals)
        cases = [primary[:-1], primary.replace(b'BEGIN 0 ', b'BEGIN 1 ', 1),
                 primary.replace(b'FP32 NCL 3 1 1 360 360', b'FP32 NCL 3 1 1 360 359', 1),
                 primary.replace(b'fw=', b'wrong=', 1), primary.replace(b'splits=11', b'splits=10', 1),
                 primary + b'junk\n', primary + transaction(0, 0, self.manifest, self.actuals),
                 primary.replace(b'ENDQ 0 0', b'ENDQ 0 1', 1),
                 primary.replace(b'DONE 0 0 RUN', b'READY WEEK5 V1', 1)]
        lines = primary.decode().splitlines()
        for section, replacement in [('Q ', '80'), ('SCALE ', '0000'), ('HEAD ', '7fc00000')]:
            copy = list(lines)
            pos = next(i for i, line in enumerate(copy) if line.startswith(section)) + 1
            copy[pos] = replacement + copy[pos][len(replacement):]
            cases.append(('\n'.join(copy) + '\n').encode())
        # Finite one-ULP corruption passes tolerance but must fail s0 bitwise.
        copy = list(lines)
        pos = next(i for i, line in enumerate(copy) if line.startswith('HEAD ')) + 1
        word = int(copy[pos][:8], 16)
        copy[pos] = f'{word^1:08x}' + copy[pos][8:]
        cases.append(('\n'.join(copy) + '\n').encode())
        for i, broken in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                parser = self.parser(expected=[(0,0)])
                parser.feed(broken)
                parser.finish()
        with self.assertRaises(ValueError):
            self.parser().feed(self.prefix + b'x'*4097)

    def test_simulation_cannot_claim_mcu(self):
        with self.assertRaises(ValueError):
            self.parser(simulated=False).feed(self.fixture)
        with self.assertRaises(ValueError):
            self.parser().feed(self.fixture.removeprefix(b'SIMULATED HOST WEEK5\r\n'))

    def test_optional_initial_sdk_boot_and_reset_rejection(self):
        boot = b'*** Booting nRF Connect SDK v3.4.0 ***\r\n*** Using Zephyr OS v4.4.0 ***\r\n'
        label = b'SIMULATED HOST WEEK5\r\n'
        parser = self.parser()
        parser.feed(label + boot + self.fixture.removeprefix(label))
        self.assertEqual(len(parser.finish()['rows']), 236)
        with self.assertRaises(ValueError):
            self.parser().feed(label+boot+boot)
        with self.assertRaises(ValueError):
            self.parser().feed(self.prefix+boot)

    def test_fake_collector_rejects_wrong_banner_and_timeout(self):
        class Transport:
            def read(self, count): return b'READY WEEK4\n'
            def write(self, command): raise AssertionError('No command before validated banner')
        with self.assertRaises(ValueError):
            collect(Transport(), io.BytesIO(), self.parser(), .1)
        class Empty:
            def read(self, count): return b''
        with self.assertRaises(ValueError):
            collect(Empty(), io.BytesIO(), self.parser(), .001)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--host', type=Path, required=True)
    a = p.parse_args()
    manifest, _, _ = authenticate()
    Tests.manifest, Tests.binding = manifest, firmware_binding()
    Tests.goldens = [np.load(ROOT / PACKAGE / f'golden/z_s{s}.npy', allow_pickle=False) for s in range(11)]
    Tests.actuals = [np.load(a.host / f'head_c_s{s}.npy', allow_pickle=False) for s in range(11)]
    Tests.prefix = ('SIMULATED HOST WEEK5\r\n' + banner(Tests.binding) + '\r\n' + COMMAND_BANNER + '\r\n').encode()
    Tests.fixture = Tests.prefix + b''.join(transaction(n,s,manifest,Tests.actuals) for n,s in sequence())
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'SIMULATED_HOST_capture.txt').write_bytes(Tests.fixture)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    write_json(a.output / 'tests.json', {'status':'PASS' if result.wasSuccessful() else 'FAIL', 'scope':'SIMULATED_HOST_ONLY',
        'tests_run':result.testsRun, 'fixture_cases':236, 'chunk_sizes':[1,7,4096,65536],
        'source_sha256':source_hashes(), 'mcu_validation':'PENDING'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
