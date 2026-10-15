"""8544 frozen test samples x 11 splits: standard FP32 head -> actual C -> frozen tail."""
import argparse
import csv
import hashlib
import importlib.util
from pathlib import Path
import sys
import time
import numpy as np
import torch
from week5_common import (ROOT, PACKAGE, Quantizer, authenticate, need, source_hashes,
                         write_json, quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl)

sys.path.insert(0, str(ROOT / 'ml/scripts'))
spec = importlib.util.spec_from_file_location('frozen_week5_loader', ROOT / 'ml/scripts/week5_common.py')
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)

def evaluate(output, compiler):
    need(not output.exists(), 'Use a new accuracy output directory')
    _, proof, _ = authenticate()
    model, _ = ml.baseline(ROOT / PACKAGE)
    checkpoint = torch.load(ROOT / PACKAGE / 'model/checkpoint.pt', map_location='cpu', weights_only=True)
    x, labels, meta, dataset = ml.load_test(checkpoint)
    need(len(labels) == 8544, 'Frozen test set count differs')
    quant = Quantizer(output, compiler)
    write_json(output / 'dataset_manifest.json', dataset)
    write_json(output / 'split_mapping.json', ml.mapping())
    started = time.monotonic()
    with torch.inference_mode():
        full = np.concatenate([model(torch.from_numpy(x[i:i+1].copy())).numpy() for i in range(len(labels))])
        fp_pred = full.argmax(axis=1)
        correct_fp = int(np.count_nonzero(fp_pred == labels))
        need(correct_fp == 8393, f'Baseline differs: {correct_fp}/8544')
        print('FP32 baseline: 8393/8544 PASS; inference batch N=1', flush=True)
        rows = []
        reference_path = ROOT / 'ml/results/week5/predictions.csv'
        with reference_path.open(encoding='utf-8', newline='') as handle:
            reference = list(csv.DictReader(handle))
        need(len(reference) == 8544 * 11, 'Official prediction count differs')
        with (output / 'predictions.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle, lineterminator='\n')
            writer.writerow(['split_point_s', 'sample_id', 'patient_id', 'record_id', 'true_label', 'prediction_fp32', 'prediction_int8_fp16'])
            for s in range(11):
                head, tail = ml.wrappers(model, s)
                preds, maximum, digest = [], 0.0, hashlib.sha256()
                for i in range(len(labels)):
                    z = head(torch.from_numpy(x[i:i+1].copy()))
                    need(tuple(z.shape[1:]) == ml.SHAPES[s][1:], 'Frozen head shape differs')
                    fp_out = tail(z).numpy()
                    maximum = max(maximum, float(np.max(np.abs(fp_out.astype(np.float64) - full[i:i+1].astype(np.float64)))))
                    need(np.isfinite(fp_out).all() and maximum < 1e-3, 'FP32 split/tail gate failed')
                    zn = np.ascontiguousarray(to_ncl(z.numpy(), s))
                    q, scale = quant.quantize(zn)
                    qo, so = quantize_per_channel(zn)
                    need(q.tobytes() == qo.tobytes() and scale.tobytes() == so.tobytes(), f'Full-test C/reference bytes differ s{s}i{i}')
                    # Read serialized FP16 bytes before dequantizing in actual C.
                    stored = np.frombuffer(scale.tobytes(), '<f2').reshape(scale.shape).copy()
                    restored = quant.dequantize(q, stored)
                    need(restored.tobytes() == dequantize_per_channel(q, stored).tobytes(), 'C dequantization differs')
                    q_out = tail(torch.from_numpy(from_ncl(restored, s))).numpy()
                    need(np.isfinite(q_out).all(), 'Nonfinite quantized tail')
                    prediction = int(q_out.argmax(axis=1)[0])
                    preds.append(prediction)
                    m = meta.iloc[i]
                    r = reference[s * 8544 + i]
                    need((int(r['split_point_s']), r['sample_id'], int(r['true_label']), int(r['prediction_fp32']), int(r['prediction_int8_fp16'])) ==
                         (s, m.sample_id, int(labels[i]), int(fp_pred[i]), prediction), f'Official prediction differs s{s}i{i}')
                    writer.writerow([s, m.sample_id, m.patient_id, m.record_id, int(labels[i]), int(fp_pred[i]), prediction])
                    digest.update(q.tobytes())
                    digest.update(scale.tobytes())
                preds = np.array(preds)
                correct_q = int(np.count_nonzero(preds == labels))
                fp_acc, q_acc = 100 * correct_fp / 8544, 100 * correct_q / 8544
                drop = fp_acc - q_acc
                need(drop < .5, f'Strict accuracy drop failed at s{s}: {drop}')
                row = {'split_point_s': s, 'num_samples': 8544, 'correct_fp32': correct_fp, 'correct_int8_fp16': correct_q,
                       'accuracy_fp32_percent': fp_acc, 'accuracy_int8_fp16_percent': q_acc,
                       'accuracy_drop_pp': drop, 'accuracy_drop_relative_percent': 100 * (correct_fp-correct_q)/correct_fp,
                       'prediction_disagreements': int(np.count_nonzero(preds != fp_pred)),
                       'fp32_split_max_abs_error': maximum, 'serialized_q_scale_sha256': digest.hexdigest(), 'status': 'PASS'}
                rows.append(row)
                print(f's{s}: {correct_q}/8544; accuracy={q_acc:.9f}%; drop={drop:.9f} pp; relative={row["accuracy_drop_relative_percent"]:.9f}%; PASS', flush=True)
                write_json(output / 'progress.json', rows)
    with (output / 'accuracy.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / 'evaluation.json', {'status': 'PASS', 'scope': 'OFFLINE_STANDARD_FP32_HEAD_C_QUANTIZATION_FROZEN_TAIL',
        'batch_size': 1, 'num_samples': 8544, 'splits': 11, 'c_oracle_exact_cases': 93984,
        'predictions_match_official': 93984, 'baseline_correct': 8393, 'strict_drop_pp': .5,
        'rows': rows, 'elapsed_seconds': time.monotonic()-started, 'compile_command': quant.command,
        'provenance': ml.provenance(' '.join(sys.argv)), 'source_sha256': source_hashes(),
        'handoff_authentication': proof, 'mcu_validation': 'PENDING'})

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--compiler', default='gcc')
    a = p.parse_args()
    evaluate(a.output, a.compiler)
