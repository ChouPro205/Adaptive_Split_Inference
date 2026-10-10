"""Read-only validation of 220 existing golden pairs and real P1/tail path."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import torch
from week5_common import baseline, PACKAGE, ROOT, CHECKPOINT, mapping, wrappers, samples, sha, need, provenance, write_json
from quantization import quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl
from p1 import descriptor, protect, unprotect
from week5_interfaces import active_profile, scale_wire_fp32_le, load_registry
from test_week5_interfaces import test_registry


def verify(package, goldens, output):
    need(not output.exists(), 'Evidence exists; choose new output')
    model, _ = baseline(package)
    manifest = json.loads((goldens/'manifest.json').read_text(encoding='utf-8'))
    need(manifest['sample_count'] == 20 and manifest['split_count'] == 11, 'Wrong golden version')
    need(manifest['mapping'] == mapping(), 'Golden/model registry mapping differs')
    need(manifest['provenance']['checkpoint_sha256'] == CHECKPOINT, 'Wrong golden checkpoint')
    need(len(manifest['entries']) == 220, 'Expected 220 entries')
    need({(r['split_point_s'], r['sample_index']) for r in manifest['entries']} ==
         {(s, i) for s in range(11) for i in range(20)}, 'Missing/duplicate golden pair')
    registry = test_registry()
    ml_registry = load_registry(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
    inputs = np.load(package/'golden/z_s0.npy', allow_pickle=False)
    identities = samples(package)
    stream = hashlib.sha256()
    counts = {str(s): 0 for s in range(11)}
    wire = []
    with torch.inference_mode():
        for entry in manifest['entries']:
            s, i = entry['split_point_s'], entry['sample_index']
            need(entry['sample_id'] == identities[i]['sample_id'], 'Golden sample identity/order differs')
            head, tail = wrappers(model, s)
            original = head(torch.from_numpy(inputs[i:i+1].copy())).numpy()
            frozen = np.load(package/f'golden/z_s{s}.npy', allow_pickle=False)[i:i+1]
            need(original.tobytes() == frozen.tobytes(), f'Frozen FP32 differs s{s}/{i}')
            q, scale = quantize_per_channel(to_ncl(original, s))
            q_path, scale_path = goldens/entry['int8_path'], goldens/entry['scale_path']
            need(sha(q_path) == entry['int8_sha256'] and sha(scale_path) == entry['scale_sha256'], 'Golden file hash differs')
            need(q.tobytes() == q_path.read_bytes() and scale.tobytes() == scale_path.read_bytes(), 'Reference/golden bytes differ')
            scale_read = np.frombuffer(scale_path.read_bytes(), dtype='<f2').reshape(scale.shape)
            need(scale_read.view('<u2').reshape(-1).tolist() == entry['scale_uint16_bits'], 'FP16 bits differ')
            effective = scale_read.astype(np.float32)
            expected_q = np.clip(np.rint(to_ncl(original, s) / effective[..., None]), -127, 127).astype(np.int8)
            need(expected_q.tobytes() == q.tobytes(), 'q not based on stored/reloaded FP16')
            row = ml_registry['splits'][s]
            need(row['shape_original'] == list(original.shape) and row['i2_shape_NCL'] == list(q.shape), 'Registry shape differs')
            need(row['head_endpoint'] == mapping()[s]['cut_name'], 'Registry endpoint differs')
            profile = active_profile(registry, s, q.shape, CHECKPOINT)
            metadata = descriptor(profile)
            nonce = struct.pack('<IQ', 1, s*20+i+1)
            key = bytes(range(32))  # public test-only profile, no deployment IDs
            protected = protect(q.tobytes(), metadata, nonce, key, profile)
            need(protected == protect(q.tobytes(), metadata, nonce, key, profile), 'Nondeterministic P1')
            recovered = unprotect(protected, metadata, nonce, key, profile)
            need(recovered == q.tobytes(), 'Real q round-trip differs')
            restored_q = np.frombuffer(recovered, dtype=np.int8).reshape(q.shape)
            need(restored_q.dtype == q.dtype and restored_q.shape == q.shape, 'q dtype/shape differs')
            restored = from_ncl(dequantize_per_channel(restored_q, scale_read), s)
            need(restored.shape == original.shape, 'NC adapter did not restore original shape')
            need(hashlib.sha256(restored.astype('<f4').tobytes()).hexdigest() == entry['dequantized_fp32_sha256'], 'Dequantized golden differs')
            logits = tail(torch.from_numpy(restored)).numpy()
            before = tail(torch.from_numpy(from_ncl(dequantize_per_channel(q, scale_read), s))).numpy()
            need(logits.tobytes() == before.tobytes(), 'P1 changed tail output')
            need(logits.tobytes() == np.asarray([entry['reference_logits_int8_fp16']], dtype=np.float32).tobytes(), 'INT8 tail golden differs')
            scale_wire = scale_wire_fp32_le(scale_read)
            need(scale_wire == b''.join(struct.pack('<f', float(v)) for v in scale_read[0]), 'Wire scale bytes differ')
            wire.append({'s': s, 'sample': i, 'scale_count': scale.size, 'wire_scale_sha256': hashlib.sha256(scale_wire).hexdigest()})
            stream.update(metadata + nonce + recovered + scale_wire + logits.tobytes())
            counts[str(s)] += 1
    result = {'status': 'PASS', 'tensors_executed': 220, 'failed_tensors': 0, 'per_split_counts': counts,
              'scale_wire': 'I1 v1 FP32 LE expansion from stored FP16; component only',
              'deployment_registry_status': 'BLOCKED_WIRE_ALLOCATION; all P1 profiles here PUBLIC_TEST_ONLY',
              'test_registry': registry, 'golden_manifest_sha256': sha(goldens/'manifest.json'),
              'stream_sha256': stream.hexdigest(), 'wire_scale_checks': wire,
              'provenance': provenance(' '.join(__import__('sys').argv))}
    write_json(output, result)
    print('PASS: 220 real tensors, 11 splits; exact q, FP16/FP32 wire, adapters and tail goldens')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--goldens', type=Path, default=ROOT/'ml/artifacts/week5/quantization20')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.package, args.goldens, args.output)
