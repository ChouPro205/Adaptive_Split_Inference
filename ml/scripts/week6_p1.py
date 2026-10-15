"""Week 6 official real-tensor P1 handoff; existing I2/I1 references stay unchanged."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ml/src'))
sys.path.insert(0, str(ROOT / 'contracts/i1v2_ref'))
import numpy as np
from p1 import Profile, descriptor, protect, unprotect
from quantization import dequantize_per_channel, from_ncl
import i1v2_reference as i1

BASE = 'af31ea784700cea163b5c6290536a5208d052da'
Q_ANCHOR = '8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd'
MODEL_ANCHOR = 'a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6'
APPROVAL_ANCHOR = 'a84b5caf89ffb7f8e11be2b308e2d4e1947e4d4f7ed291c47df083d0e15c7a7d'
REGISTRY_ANCHOR = '79392b6db73cde6d83eadb1f265f14102888ebdbf8ea1b72b6c127c5566eed24'
MODEL_PACKAGE = ROOT / 'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1'
GOLDENS = ROOT / 'ml/artifacts/week5/quantization20'
REGISTRY = ROOT / 'contracts/sv3_week5_approved_registry_v2.json'
APPROVAL = ROOT / 'contracts/sv3_week5_allocation_approval_v2.json'
KEY = bytes(range(32))  # PUBLIC_TEST_ONLY; never read a bench/operational key.
SENDER = 131073
SELECTION = [(s, i) for s in range(11) for i in range(5 if s < 6 else 4)]
KINDS = {'q': 'q.i8.bin', 'scale': 'scale.f16le.bin', 'descriptor': 'descriptor.i2.bin',
         'nonce': 'nonce.bin', 'transformed': 'transformed.bin', 'request': 'request.i1v2.bin',
         'logits': 'logits.quantized.f32le.bin', 'fp32_logits': 'logits.fp32.f32le.bin'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, f'Duplicate JSON key: {k}')
            result[k] = v
        return result
    def reject(value):
        raise ValueError(f'Nonfinite JSON: {value}')
    return json.loads(Path(path).read_text('utf-8'), object_pairs_hook=pairs, parse_constant=reject)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def same(a, b, message):
    need(json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False), message)


def safe(root, name):
    need(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
         and ':' not in name and all(p not in ('', '.', '..') for p in name.split('/')), 'Unsafe package path')
    root = Path(root).resolve()
    p = root / name
    need(not any(t.is_symlink() for t in (p, *p.parents)), 'Package symlink forbidden')
    need(p.resolve().is_relative_to(root), 'Package path escapes root')
    return p


def inventory(package):
    result = []
    for p in sorted(Path(package).rglob('*')):
        need(not p.is_symlink(), 'Package symlink forbidden')
        if p.is_file() and p != Path(package) / 'manifest.json':
            data = p.read_bytes()
            result.append({'path': p.relative_to(package).as_posix(), 'size_bytes': len(data), 'sha256': digest(data)})
    return result


def git(*args):
    return subprocess.check_output(['git', '--no-optional-locks', '-c', 'safe.directory=' + ROOT.as_posix(),
                                    *args], cwd=ROOT)


def source_bindings(commit):
    git('merge-base', '--is-ancestor', BASE, commit)
    names = git('ls-tree', '-r', '--name-only', commit).decode().splitlines()
    names = [n for n in names if n.endswith(('.py', '.c', '.h'))
             or n.startswith(('contracts/', 'ml/configs/', 'ml/manifests/'))
             or n == 'ml/docs/week6_p1_package_readme.md']
    # Read blobs in one batch. Binding the original commit does not require HEAD to remain there.
    data = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'cat-file', '--batch'],
                                   cwd=ROOT, input=(''.join(f'{commit}:{n}\n' for n in names)).encode())
    position, result = 0, {}
    for name in names:
        end = data.index(b'\n', position)
        header = data[position:end].split()
        need(header[1] == b'blob', f'Missing source blob: {name}')
        size = int(header[2]); raw = data[end + 1:end + 1 + size]; position = end + 2 + size
        current = safe(ROOT, name).read_bytes()
        need(raw == current, f'Source differs from generating commit: {name}')
        result[name] = digest(current)
    return result


def authenticated_inputs(quantization, registry, approval):
    need(digest(Path(quantization).read_bytes()) == Q_ANCHOR, 'Quantization manifest anchor differs')
    need(digest(Path(registry).read_bytes()) == REGISTRY_ANCHOR, 'Registry anchor differs')
    need(digest(Path(approval).read_bytes()) == APPROVAL_ANCHOR, 'Approval anchor differs')
    q, r, a = read(quantization), read(registry), read(approval)
    need(a['decision'] == r['status'] == 'APPROVED' and a['registry_sha256'] == REGISTRY_ANCHOR,
         'Registry approval differs')
    need(r['model_profile_id'] == 1296651265 and r['key_id'] == 65537
         and r['sender_scope']['sender_ids'] == [SENDER], 'Approved IDs differ')
    need(len(q['entries']) == 220 and q['sample_count'] == 20 and q['split_count'] == 11,
         'Expected original 220 real tensor pairs')
    entries = {(e['split_point_s'], e['sample_index']): e for e in q['entries']}
    need(set(entries) == {(s, i) for s in range(11) for i in range(20)}, 'Source coverage differs')
    need(q['provenance']['checkpoint_sha256'] == r['checkpoint_sha256'], 'Source checkpoint differs')
    return q, r, entries


def profile(registry, s):
    r = registry['splits'][s]
    need(r['split_point_s'] == s and r['wire_split_id'] == 256 + s, 'Split mapping differs')
    n, c, length = r['i2_shape_NCL']
    need(n == 1 and (s != 9 or [n, c, length] == [1, 32, 1])
         and (s != 10 or [n, c, length] == [1, 5, 1]), 'NCL shape differs')
    return Profile(registry['model_profile_id'], r['wire_split_id'], c, length,
                   registry['key_id'], r['max_payload_bytes'])


def metadata(e, index, registry):
    s, i = e['split_point_s'], e['sample_index']
    p = profile(registry, s)
    directory = f'vectors/{index:03d}_s{s}_sample{i:02d}'
    return {'vector_index': index, 'split_point_s': s, 'sample_index': i, 'sample_id': e['sample_id'],
            'model_profile_id': p.model_profile_id, 'wire_split_id': p.split_id, 'key_id': p.key_id,
            'sender_id': SENDER, 'sequence': index + 1, 'request_id': index + 1,
            'dtype': 'int8', 'layout': 'NCL', 'shape': [1, p.channels, p.length],
            'C_contiguous': True, 'flatten_order': 'C', 'shape_original': e['shape_original'],
            'NC_mapping': '[1,C] -> [1,C,1], reshape only; identical q bytes' if s >= 9 else 'identity NCL',
            'scale_dtype': '<f2', 'scale_byte_order': 'little-endian uint16 bits, source-channel order',
            'scale_uint16_bits': e['scale_uint16_bits'], 'source_q_path': e['int8_path'],
            'source_q_sha256': e['int8_sha256'], 'source_scale_path': e['scale_path'],
            'source_scale_sha256': e['scale_sha256'],
            'files': {k: f'{directory}/{v}' for k, v in KINDS.items()}}


def q_and_scale(qbytes, scales, p, e):
    need(len(qbytes) == p.channels * p.length and digest(qbytes) == e['int8_sha256'], 'Original q hash/size differs')
    need(len(scales) == p.channels * 2 and digest(scales) == e['scale_sha256'], 'Original FP16 scale hash/size differs')
    q = np.frombuffer(qbytes, dtype=np.int8).reshape(1, p.channels, p.length)
    scale = np.frombuffer(scales, dtype='<f2').reshape(1, p.channels)
    need(q.flags.c_contiguous and not np.any(q == -128), 'Original q must be contiguous [-127,127]')
    need(scale.view('<u2').reshape(-1).tolist() == e['scale_uint16_bits'], 'Scale bits differ')
    restored = dequantize_per_channel(q, scale)
    need(digest(restored.astype('<f4').tobytes()) == e['dequantized_fp32_sha256'], 'Dequantized source differs')
    return q, scale


def generate(output, *, goldens=GOLDENS, model_package=MODEL_PACKAGE, source_commit=None):
    from week3_sv2_common import authenticate, samples, versions
    source_commit = source_commit or git('rev-parse', 'HEAD').decode().strip()
    bindings = source_bindings(source_commit)
    need('ml/scripts/generate_week6_p1.py' in bindings, 'Commit generator implementation before generating delivery')
    qmanifest, registry, entries = authenticated_inputs(goldens / 'manifest.json', REGISTRY, APPROVAL)
    authenticate(model_package, MODEL_ANCHOR)
    identities = samples(model_package)
    # Authenticate all 220 inputs before selecting 50, without rewriting a q or scale.
    for (s, i), e in entries.items():
        need(e['sample_id'] == identities[i]['sample_id'], 'Source sample identity differs')
        q_and_scale(safe(goldens, e['int8_path']).read_bytes(), safe(goldens, e['scale_path']).read_bytes(),
                    profile(registry, s), e)
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    for name, path in [('quantization20.manifest.json', goldens / 'manifest.json'),
                       ('registry.json', REGISTRY), ('approval.json', APPROVAL)]:
        target = output / 'inputs' / name; target.parent.mkdir(exist_ok=True); target.write_bytes(path.read_bytes())
    fp32 = np.load(model_package / 'golden/reference_logits.npy', allow_pickle=False)
    vectors = []
    for index, (s, i) in enumerate(SELECTION):
        e = entries[s, i]; v = metadata(e, index, registry); p = profile(registry, s)
        qb, sb = safe(goldens, e['int8_path']).read_bytes(), safe(goldens, e['scale_path']).read_bytes()
        _, scale = q_and_scale(qb, sb, p, e)
        d = descriptor(p); nonce = struct.pack('<IQ', SENDER, index + 1)
        transformed = protect(qb, d, nonce, KEY, p)
        packet = i1.encode_request(index + 1, p.model_profile_id, p.split_id, p.channels, p.length,
                                   scale.astype(np.float32)[0].tolist(), transformed, d, nonce)
        values = {'q': qb, 'scale': sb, 'descriptor': d, 'nonce': nonce, 'transformed': transformed,
                  'request': packet, 'logits': np.asarray(e['reference_logits_int8_fp16'], dtype='<f4').tobytes(),
                  'fp32_logits': fp32[i:i+1].astype('<f4').tobytes()}
        for key, raw in values.items():
            path = safe(output, v['files'][key]); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        vectors.append(v)
    content = {'schema': 'sv3-week6-p1-50/1', 'scope': 'PUBLIC_TEST_ONLY', 'key_hex': KEY.hex(),
               'public_key_notice': 'Public offline reference only; MUST NOT provision as bench or operational key.',
               'selection_rule': 's ascending; first 5 original sample indices for s0..s5; first 4 for s6..s10',
               'nonce_rule': 'sender_id uint32_le=131073 || sequence uint64_le=vector_index+1 (1..50)',
               'class_order': ['N', 'S', 'V', 'F', 'Q'], 'vectors': vectors,
               'provenance': {'base_commit': BASE, 'source_commit': source_commit, 'source_files_sha256': bindings,
                              'quantization_manifest_sha256': Q_ANCHOR, 'model_manifest_sha256': MODEL_ANCHOR,
                              'registry_sha256': REGISTRY_ANCHOR, 'approval_sha256': APPROVAL_ANCHOR,
                              'environment': versions(), 'input_scope': '50 of 220 historical real validation tensors; not test-set accuracy'}}
    write(output / 'vectors.json', content)
    (output / 'README.md').write_bytes((ROOT / 'ml/docs/week6_p1_package_readme.md').read_bytes())
    need(any(0x80 in safe(output, v['files']['transformed']).read_bytes() for v in vectors), 'No natural transformed 0x80')
    write(output / 'manifest.json', {'schema': 'sv3-week6-p1-files/1', 'hash': 'SHA-256 raw bytes',
                                    'scope': 'every regular file except this root manifest.json; ZIP hash is external',
                                    'files': inventory(output)})
    return {'package': str(output), 'manifest_sha256': digest((output / 'manifest.json').read_bytes()), 'vectors': 50}


class CReference:
    class Profile(ctypes.Structure):
        _fields_ = [('model_profile_id', ctypes.c_uint32), ('split_id', ctypes.c_uint16),
                    ('channels', ctypes.c_uint16), ('length', ctypes.c_uint32),
                    ('key_id', ctypes.c_uint32), ('max_payload_bytes', ctypes.c_uint32)]

    def __init__(self, compiler):
        self.temp = tempfile.TemporaryDirectory(prefix='week6-official-c-')
        library = Path(self.temp.name) / ('i2.dll' if os.name == 'nt' else 'libi2.so')
        self.command = [compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
                        *([] if os.name == 'nt' else ['-fPIC']), '-shared', '-o', str(library),
                        str(ROOT / 'contracts/i2_ref/i2_reference.c')]
        p = subprocess.run(self.command, capture_output=True)
        self.build = {'argv': self.command, 'exit_code': p.returncode,
                      'stdout': p.stdout.decode('utf-8', 'replace'), 'stderr': p.stderr.decode('utf-8', 'replace'),
                      'compiler_version': subprocess.check_output([compiler, '--version']).decode('utf-8', 'replace'),
                      'source_sha256': digest((ROOT / 'contracts/i2_ref/i2_reference.c').read_bytes())}
        need(p.returncode == 0, f'C reference build failed: {self.build}')
        self.lib = ctypes.CDLL(str(library))
        args = [ctypes.c_void_p, ctypes.c_size_t] * 4 + [ctypes.POINTER(self.Profile), ctypes.c_void_p, ctypes.c_size_t]
        for name in ('i2_protect', 'i2_unprotect'):
            f = getattr(self.lib, name); f.argtypes = args; f.restype = ctypes.c_int
        self.lib.i2_write_descriptor.argtypes = [ctypes.POINTER(self.Profile), ctypes.c_void_p]
        self.lib.i2_write_descriptor.restype = ctypes.c_int

    def call(self, name, data, d, nonce, p):
        buffers = [ctypes.create_string_buffer(raw) for raw in (data, d, nonce, KEY)]
        out = ctypes.create_string_buffer(len(data))
        cp = self.Profile(p.model_profile_id, p.split_id, p.channels, p.length, p.key_id, p.max_payload_bytes)
        cd = ctypes.create_string_buffer(28)
        need(self.lib.i2_write_descriptor(ctypes.byref(cp), cd) == 0 and cd.raw == d, 'C descriptor differs')
        code = getattr(self.lib, name)(buffers[0], len(data), buffers[1], len(d), buffers[2], len(nonce),
                                      buffers[3], 32, ctypes.byref(cp), out, len(data))
        need(code == 0, f'C {name} status={code}')
        return out.raw

    def close(self):
        if os.name == 'nt':
            import _ctypes
            _ctypes.FreeLibrary(self.lib._handle)
        self.lib = None
        self.temp.cleanup()


def authenticate_package(package, expected):
    package = Path(package).resolve()
    need(len(expected) == 64 and all(c in '0123456789abcdef' for c in expected), 'Expected external manifest SHA256')
    need(digest((package / 'manifest.json').read_bytes()) == expected, 'Package manifest anchor differs')
    manifest = read(package / 'manifest.json')
    need(manifest['schema'] == 'sv3-week6-p1-files/1', 'Wrong manifest schema')
    same(manifest['files'], inventory(package), 'Package inventory/hash/size differs (missing, changed or extra file)')
    names = [f['path'] for f in manifest['files']]
    need(len(names) == len(set(names)) and 'vectors.json' in names, 'Duplicate/empty inventory')
    for name in names:
        safe(package, name)
    data = read(package / 'vectors.json')
    need(data['schema'] == 'sv3-week6-p1-50/1' and data['scope'] == 'PUBLIC_TEST_ONLY'
         and data['key_hex'] == KEY.hex(), 'Wrong schema or public reference key')
    need(data['class_order'] == ['N', 'S', 'V', 'F', 'Q'], 'Class order differs')
    _, registry, entries = authenticated_inputs(package / 'inputs/quantization20.manifest.json',
                                               package / 'inputs/registry.json', package / 'inputs/approval.json')
    same(data['vectors'], [metadata(entries[s, i], index, registry) for index, (s, i) in enumerate(SELECTION)],
         'Vector metadata/selection/nonce/shape/source differs')
    provenance = data['provenance']
    need(provenance['base_commit'] == BASE and provenance['quantization_manifest_sha256'] == Q_ANCHOR
         and provenance['model_manifest_sha256'] == MODEL_ANCHOR
         and provenance['registry_sha256'] == REGISTRY_ANCHOR
         and provenance['approval_sha256'] == APPROVAL_ANCHOR, 'Source provenance anchor differs')
    same(source_bindings(provenance['source_commit']), provenance['source_files_sha256'], 'Generating source bindings differ')
    required = {'vectors.json', 'README.md', 'inputs/quantization20.manifest.json', 'inputs/registry.json', 'inputs/approval.json'}
    required.update(p for v in data['vectors'] for p in v['files'].values())
    need(set(names) == required, 'Package file scope differs')
    return package, data, registry, entries


def verify(package, expected, compiler='gcc'):
    package, data, registry, entries = authenticate_package(package, expected)
    c = CReference(compiler); rows = []
    try:
        for v in data['vectors']:
            index, s, i = v['vector_index'], v['split_point_s'], v['sample_index']
            p = profile(registry, s); b = {k: safe(package, f).read_bytes() for k, f in v['files'].items()}
            _, scale = q_and_scale(b['q'], b['scale'], p, entries[s, i])
            need(b['descriptor'] == descriptor(p) and len(b['descriptor']) == 28, 'Descriptor bytes differ')
            need(b['nonce'] == struct.pack('<IQ', SENDER, index + 1) and len(b['nonce']) == 12, 'Nonce differs')
            transformed = protect(b['q'], b['descriptor'], b['nonce'], KEY, p)
            recovered = unprotect(b['transformed'], b['descriptor'], b['nonce'], KEY, p)
            need(transformed == b['transformed'] and recovered == b['q'], 'Python protect/roundtrip differs')
            cp = c.call('i2_protect', b['q'], b['descriptor'], b['nonce'], p)
            cu = c.call('i2_unprotect', b['transformed'], b['descriptor'], b['nonce'], p)
            need(cp == transformed and cu == b['q'], 'C/Python official vector differs')
            packet = i1.encode_request(index + 1, p.model_profile_id, p.split_id, p.channels, p.length,
                                       scale.astype(np.float32)[0].tolist(), transformed, b['descriptor'], b['nonce'])
            need(packet == b['request'], 'I1 v2 packet/FP16-expanded scale bytes differ')
            need(b['logits'] == np.asarray(entries[s, i]['reference_logits_int8_fp16'], dtype='<f4').tobytes(),
                 'Original quantized reference logits differ')
            need(len(b['fp32_logits']) == 20 and np.isfinite(np.frombuffer(b['fp32_logits'], '<f4')).all(), 'Bad FP32 logits')
            rows.append({'vector_index': index, 's': s, 'wire_split_id': p.split_id, 'sequence': index + 1,
                         'q_sha256': digest(b['q']), 'python_protect_sha256': digest(transformed),
                         'C_protect_sha256': digest(cp), 'python_unprotect_sha256': digest(recovered),
                         'C_unprotect_sha256': digest(cu), 'contains_transformed_0x80': 0x80 in transformed,
                         'python_roundtrip': 'PASS_BYTE_EXACT', 'C_protect': 'PASS_BYTE_EXACT', 'C_unprotect': 'PASS_BYTE_EXACT'})
    finally:
        c.close()
    need(len(rows) == 50 and len({r['sequence'] for r in rows}) == 50, 'Wrong count/duplicate sequence')
    need(any(r['contains_transformed_0x80'] for r in rows), 'No natural transformed 0x80')
    return {'schema': 'week6-p1-verification/1', 'status': 'PASS_A_HOST', 'vectors': 50,
            'split_counts': {str(s): sum(r['s'] == s for r in rows) for s in range(11)},
            'python_roundtrips': 50, 'C_Python_protect_matches': 50, 'C_roundtrips': 50,
            'transformed_0x80_vectors': sum(r['contains_transformed_0x80'] for r in rows),
            'manifest_sha256': expected, 'C_build': c.build, 'rows': rows,
            'scope': 'PUBLIC_TEST_ONLY; host C reference on these exact 50 real tensors; not MCU acceptance'}


def output_semantics(package, expected, model_package=MODEL_PACKAGE):
    import torch
    from week3_sv2_common import authenticate, configure, load_frozen, wrappers, TOLERANCE
    package, data, registry, entries = authenticate_package(package, expected)
    authenticate(model_package, MODEL_ANCHOR); configure(); model = load_frozen(model_package).float().eval()
    labels = read(ROOT / 'ml/configs/mitdb_week1_config.json')['classes']
    same(labels, {name: i for i, name in enumerate(['N', 'S', 'V', 'F', 'Q'])}, 'Model class mapping differs')
    need(model.classifier[-1].out_features == 5 and not any(isinstance(m, (torch.nn.Softmax, torch.nn.LogSoftmax,
         torch.nn.Sigmoid)) for m in model.modules()), 'Model must emit five raw logits without softmax')
    frozen_fp32 = np.load(model_package / 'golden/reference_logits.npy', allow_pickle=False)
    wire_profile = i1.load_profile(package / 'inputs/registry.json'); rows = []
    with torch.inference_mode():
        for v in data['vectors']:
            s, i = v['split_point_s'], v['sample_index']; p = profile(registry, s)
            b = {k: safe(package, f).read_bytes() for k, f in v['files'].items()}
            original_q, scale = q_and_scale(b['q'], b['scale'], p, entries[s, i])
            restored = unprotect(b['transformed'], b['descriptor'], b['nonce'], KEY, p)
            need(restored == b['q'], 'Output path q roundtrip differs')
            rq = np.frombuffer(restored, dtype=np.int8).reshape(v['shape'])
            z = from_ncl(dequantize_per_channel(rq, scale), s)
            _, tail = wrappers(model, s)
            need((s != 9 or z.shape == (1, 32)) and (s != 10 or len(tail) == 0), 'NC/identity mapping differs')
            logits = tail(torch.from_numpy(z.copy())).numpy().astype('<f4')
            baseline = tail(torch.from_numpy(from_ncl(dequantize_per_channel(original_q, scale), s).copy())).numpy()
            need(logits.tobytes() == baseline.tobytes(), 'P1 changed reference tail output')
            expected_logits = np.frombuffer(b['logits'], '<f4').reshape(1, 5)
            reference_error = float(np.max(np.abs(logits.astype(np.float64) - expected_logits)))
            need(reference_error < TOLERANCE, 'Quantized tail differs from original FP32 reference engine')
            need(b['fp32_logits'] == frozen_fp32[i:i+1].astype('<f4').tobytes(), 'Frozen FP32 baseline logits differ')
            calls = []
            def callback(split, values):
                need(split.split_point == s and s < 10, 'Wrong tail callback / tail_s10 requested')
                incoming = np.array(values, dtype=np.float32).reshape(1, p.channels, p.length)
                need(incoming.tobytes() == dequantize_per_channel(original_q, scale).tobytes(),
                     'I1 did not unprotect before original-channel dequantization')
                incoming = from_ncl(incoming, s); calls.append(list(incoming.shape))
                return tail(torch.from_numpy(incoming.copy())).numpy()[0].tolist()
            response = i1.receive_request(b['request'], wire_profile, {p.key_id: KEY}, tail=callback)
            status, observed = i1.parse_response(response, v['request_id'], wire_profile.max_packet)
            need(status == 'OK' and np.asarray(observed, '<f4').tobytes() == logits.tobytes(), 'I1 raw logits response differs')
            need(len(calls) == (0 if s == 10 else 1), 'Tail execution count differs')
            if s == 10:
                need(logits.tobytes() == z.tobytes(), 's10 must be exact dequantized identity')
            rows.append({'vector_index': v['vector_index'], 's': s, 'tail_input_shape': list(z.shape),
                         'tail_calls': len(calls), 'output_shape': list(logits.shape), 'logits': observed,
                         'argmax': i1.predicted_class(observed), 'class': list(labels)[i1.predicted_class(observed)],
                         'reference_tail_max_abs_error': reference_error, 'P1_tail_bit_exact': True,
                         'quantization_vs_FP32_max_abs_error': float(np.max(np.abs(logits.astype(np.float64) - frozen_fp32[i:i+1]))),
                         'I1_response_sha256': digest(response), 's10_identity': s == 10})
    ties = [([-2., -2., -3., -4., -5.], 0), ([0., 3., 3., 1., 0.], 1), ([0.] * 5, 0)]
    for logits, index in ties:
        response = i1.encode_response(1, logits); status, result = i1.parse_response(response, 1, 6380)
        need(status == 'OK' and result == logits and i1.predicted_class(result) == index, 'Tie-breaking differs')
    need(any(min(r['logits']) < 0 or max(r['logits']) > 1 for r in rows), 'No evidence of unnormalized logits')
    return {'schema': 'week6-output-semantics/1', 'status': 'PASS_B_HOST_REFERENCE', 'vectors': 50,
            'class_order': list(labels), 'softmax_applied': False, 'tie_cases': [{'logits': a, 'expected_index': b} for a, b in ties],
            'tie_scope': 'Separate small synthetic tie tests; excluded from the 50 real vectors',
            's0_s9_tail_cases': sum(r['s'] < 10 for r in rows), 's10_identity_cases': sum(r['s'] == 10 for r in rows),
            'reference_tolerance_strict': TOLERANCE, 'reference_tolerance_source': 'unchanged week3_sv2_common.TOLERANCE',
            'quantization_error_scope': 'diagnostic only; no new threshold, no DPU accuracy claim',
            'model_checkpoint_sha256': registry['checkpoint_sha256'], 'rows': rows,
            'DPU': 'NOT_RUN_DEPENDENCY_SV2_REAL_KV260_BACKEND', 'MCU_BLE': 'NOT_RUN_DEPENDENCY_SV1'}


def archive(package, destination):
    package, destination = Path(package), Path(destination)
    need(not destination.exists(), 'Archive exists; refusing overwrite')
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(package.rglob('*')):
            need(not p.is_symlink(), 'Package symlink forbidden')
            if p.is_file():
                info = zipfile.ZipInfo(package.name + '/' + p.relative_to(package).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
                z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    raw = destination.read_bytes()
    return {'path': str(destination), 'sha256': digest(raw), 'size_bytes': len(raw)}
