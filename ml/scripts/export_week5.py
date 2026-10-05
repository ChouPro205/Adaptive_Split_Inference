"""Byte comparison pack: the unchanged 20 historical samples at all 11 splits."""
import argparse
from pathlib import Path
import sys

import numpy as np
import torch
from week5_common import (baseline, PACKAGE, ROOT, samples, wrappers, mapping, provenance,
                         write_json, sha, need, SHAPES)
from week3_common import same_bits
from quantization import quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl


def export(package, output):
    need(not output.exists(), 'Output exists; choose a new directory')
    model, _ = baseline(package)
    identities = samples(package)
    inputs = np.load(package / 'golden/z_s0.npy', allow_pickle=False)
    full = np.load(package / 'golden/reference_logits.npy', allow_pickle=False)
    output.mkdir(parents=True)
    entries = []
    with torch.inference_mode():
        for s in range(11):
            head, tail = wrappers(model, s)
            frozen_z = np.load(package / f'golden/z_s{s}.npy', allow_pickle=False)
            for i, row in enumerate(identities):
                z = head(torch.from_numpy(inputs[i:i+1].copy())).numpy()
                need(tuple(z.shape) == SHAPES[s], 'Split shape mismatch')
                need(same_bits(z, frozen_z[i:i+1]), f'Golden activation differs s{s}/{i}')
                fp_logits = tail(torch.from_numpy(z.copy())).numpy()
                need(np.max(np.abs(fp_logits - full[i:i+1])) < 1e-3, 'FP32 full-model comparison failed')
                q, scale = quantize_per_channel(to_ncl(z, s))
                prefix = f's{s}/sample_{i:02d}'
                q_path = output / (prefix + '.i8.bin')
                scale_path = output / (prefix + '.scale.f16le.bin')
                q_path.parent.mkdir(parents=True, exist_ok=True)
                q.tofile(q_path)
                scale.tofile(scale_path)
                reread_q = np.fromfile(q_path, dtype=np.int8).reshape(q.shape)
                reread_scale = np.fromfile(scale_path, dtype='<f2').reshape(scale.shape)
                need(same_bits(q, reread_q) and same_bits(scale, reread_scale), 'Serialized quantization bytes differ')
                restored = from_ncl(dequantize_per_channel(reread_q, reread_scale), s)
                logits = tail(torch.from_numpy(restored)).numpy()
                need(np.isfinite(logits).all(), 'Nonfinite output')
                entries.append({'sample_index': i, 'sample_id': row['sample_id'], 'split_point_s': s,
                                'shape_original': list(z.shape), 'quantization_shape_NCL': list(q.shape),
                                'layout_original': 'NC' if s >= 9 else 'NCL', 'layout_quantization': 'NCL',
                                'flatten_order': 'C', 'scale_order': 'n then c; [N,C]', 'scale_dtype': '<f2',
                                'scale_uint16_bits': reread_scale.view('<u2').reshape(-1).tolist(),
                                'int8_path': q_path.relative_to(output).as_posix(), 'int8_sha256': sha(q_path),
                                'scale_path': scale_path.relative_to(output).as_posix(), 'scale_sha256': sha(scale_path),
                                'dequantized_fp32_sha256': __import__('hashlib').sha256(restored.astype('<f4').tobytes()).hexdigest(),
                                'reference_logits_int8_fp16': logits[0].tolist(), 'prediction_fp32': int(fp_logits.argmax()),
                                'prediction_int8_fp16': int(logits.argmax()),
                                'fp32_source': f'ml/artifacts/week3/{package.name}/golden/z_s{s}.npy'})
    manifest = {'status': 'PASS_220_SAMPLE_SPLIT_PAIRS', 'sample_count': 20, 'split_count': 11,
                'not_accuracy_evaluation': 'Historical validation samples, NOT the official test set',
                'not_week6_p1_vectors': True, 'mapping': mapping(), 'entries': entries,
                'provenance': provenance(' '.join(sys.argv))}
    write_json(output / 'manifest.json', manifest)
    print(manifest['status'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/artifacts/week5/quantization20')
    args = parser.parse_args()
    export(args.package, args.output)
