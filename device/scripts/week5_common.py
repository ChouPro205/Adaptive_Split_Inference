"""Shared Week 5 host tools. All evidence is offline unless explicitly captured."""
from __future__ import annotations
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ml/src'))
from quantization import quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl
from generate_week4_inputs import load_handoff, generate, PACKAGE, R3
from week4_handoff import authenticate_handoff, accepted_r3_provenance

RECEIPT_SHA = '3fe550cbd3311825c7def1e2a6bb891032d0dd27ffe3990ced9f36451ee6d3ab'
FP = ct.POINTER(ct.c_float)
QP = ct.POINTER(ct.c_int8)
BP = ct.POINTER(ct.c_uint8)

def need(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def source_hashes():
    paths = [*sorted((ROOT / 'device/week5').rglob('*')),
             *sorted((ROOT / 'device/scripts').glob('*week5*')),
             ROOT / 'device/src/week4_head.c', ROOT / 'device/src/week4_head.h',
             ROOT / 'device/src/week4_protocol.c', ROOT / 'device/src/week4_protocol.h',
             ROOT / 'device/src/markers.c', ROOT / 'device/src/markers.h',
             ROOT / R3 / 'firmware/head_parameters.h',
             ROOT / 'device/generated/week4_graph.h', ROOT / 'device/generated/week4_inputs.h',
             ROOT / 'ml/src/quantization.py', ROOT / 'ml/scripts/week5_common.py',
             ROOT / 'ml/scripts/evaluate_week5.py', ROOT / 'tools/week4_handoff_auth.py',
             ROOT / 'ml/artifacts/week5/quantization20/manifest.json',
             ROOT / 'ml/provenance/week5/external_assets.json',
             ROOT / PACKAGE / 'manifest.json', ROOT / PACKAGE / 'model/checkpoint.pt']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths if p.is_file() and '__pycache__' not in p.parts}

def firmware_binding():
    paths = [*sorted((ROOT / 'device/week5').glob('*')),
             *[ROOT / 'device/src' / n for n in ('week4_head.c', 'week4_head.h', 'week4_protocol.c', 'week4_protocol.h', 'markers.c', 'markers.h')],
             ROOT / R3 / 'firmware/head_parameters.h', ROOT / 'device/generated/week4_graph.h',
             ROOT / 'device/generated/week4_inputs.h']
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths if p.is_file()}
    data = {'source_sha256': hashes,
            'model_anchor': sha(ROOT / PACKAGE / 'manifest.json'),
            'quant_anchor': sha(ROOT / 'ml/artifacts/week5/quantization20/manifest.json')}
    data['firmware_id'] = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return data

def authenticate():
    _, splits, proof = authenticate_handoff(ROOT)
    history = accepted_r3_provenance(ROOT)
    receipt_path = ROOT / 'ml/provenance/week5/external_assets.json'
    need(sha(receipt_path) == RECEIPT_SHA, 'Week 5 receipt trust anchor mismatch')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    for asset in receipt['assets']:
        for entry in asset['files']:
            p = ROOT / entry['path']
            need(p.resolve().is_relative_to(ROOT), 'Unsafe receipt path')
            need(p.stat().st_size == entry['size_bytes'] and sha(p) == entry['sha256'], f'Asset mismatch: {p}')
    manifest = json.loads((ROOT / 'ml/artifacts/week5/quantization20/manifest.json').read_text())
    need(len(manifest['entries']) == 220, 'Incomplete quantization reference')
    mapping = manifest['mapping']
    need(mapping == json.loads((ROOT / 'ml/results/week5/split_mapping.json').read_text()), 'Mapping differs')
    need(max(m['num_elements'] for m in mapping) == 5760 and max(m['channels'] for m in mapping) == 64, 'Buffer limits differ')
    for s, m in enumerate(mapping):
        need(m['split_point_s'] == s and m['shape'] == splits['splits'][s]['shape_N1'], 'Frozen shape mismatch')
    return manifest, proof, history

class Quantizer:
    def __init__(self, directory, compiler):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        compiler = shutil.which(str(compiler))
        need(compiler is not None, 'Host C compiler missing')
        self.path = directory / ('week5_quantization.dll' if os.name == 'nt' else 'week5_quantization.so')
        self.command = [compiler, '-std=c99', '-O2', '-ffp-contract=off', '-fno-fast-math',
                        '-Wall', '-Wextra', '-Werror', '-shared',
                        *([] if os.name == 'nt' else ['-fPIC']),
                        str(ROOT / 'device/week5/quantization.c'), '-o', str(self.path)]
        subprocess.run(self.command, check=True)
        self.dll = ct.CDLL(str(self.path))
        sizes = [ct.c_size_t] * 4
        self.dll.week5_quantize.argtypes = [FP, *sizes, QP, ct.c_size_t, BP, ct.c_size_t]
        self.dll.week5_quantize.restype = ct.c_int
        self.dll.week5_dequantize.argtypes = [QP, *sizes, BP, ct.c_size_t, FP, ct.c_size_t]
        self.dll.week5_dequantize.restype = ct.c_int
        self.dll.week5_f32_to_f16.argtypes = [ct.c_float]
        self.dll.week5_f32_to_f16.restype = ct.c_uint16
        self.dll.week5_f16_to_f32.argtypes = [ct.c_uint16]
        self.dll.week5_f16_to_f32.restype = ct.c_float

    def quantize(self, z):
        need(z.dtype == np.float32 and z.ndim == 3 and z.flags.c_contiguous, 'C API requires contiguous FP32 NCL')
        q = np.empty(z.shape, np.int8)
        scale = np.empty(z.shape[:2], '<f2')
        status = self.dll.week5_quantize(z.ctypes.data_as(FP), z.size, *z.shape,
                                         q.ctypes.data_as(QP), q.size,
                                         scale.ctypes.data_as(BP), scale.nbytes)
        need(status == 0, f'C quantization rejected input: {status}')
        return q, scale

    def dequantize(self, q, scale):
        need(q.dtype == np.int8 and q.ndim == 3 and q.flags.c_contiguous and scale.dtype.str == '<f2' and scale.flags.c_contiguous,
             'C dequantization requires contiguous INT8/FP16')
        z = np.empty(q.shape, np.float32)
        status = self.dll.week5_dequantize(q.ctypes.data_as(QP), q.size, *q.shape,
                                          scale.ctypes.data_as(BP), scale.nbytes, z.ctypes.data_as(FP), z.size)
        need(status == 0, f'C dequantization rejected input: {status}')
        return z
