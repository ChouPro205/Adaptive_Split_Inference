"""Full official test: quantify only activation INT8/FP16, no P1 or hardware."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
from pathlib import Path
import sys
import time

import numpy as np
import torch
from week5_common import (baseline, load_test, provenance, write_csv, write_json,
                         ROOT, PACKAGE, wrappers, SHAPES, mapping, need)
from quantization import quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl


def strict_accuracy_gate(correct_fp32, correct_int8, count):
    """Exact count-based strict <0.5 percentage point acceptance."""
    need(type(count) is int and count > 0, 'Expected positive sample count')
    need(all(type(v) is int and 0 <= v <= count for v in (correct_fp32, correct_int8)),
         'Correct counts must be integers within the sample count')
    return 200 * (correct_fp32 - correct_int8) < count


def evaluate(package, output, batch_size):
    need(batch_size > 0, 'batch-size must be positive')
    need(not output.exists(), 'Output exists; use a new directory to preserve results')
    model, _ = baseline(package)
    checkpoint = torch.load(package / 'model/checkpoint.pt', map_location='cpu', weights_only=True)
    x, labels, meta, data_report = load_test(checkpoint)
    count = len(labels)
    need(count == 8544, 'Week 5 requires exactly 8544 frozen test samples')
    output.mkdir(parents=True)
    write_json(output / 'dataset_manifest.json', data_report)
    write_json(output / 'split_mapping.json', mapping())
    started = time.monotonic()
    with torch.inference_mode():
        full = np.concatenate([model(torch.from_numpy(x[i:i+batch_size].copy())).numpy() for i in range(0, count, batch_size)])
        # First gate every s over every official sample. Fail before quantized comparisons.
        gates = []
        for s in range(11):
            head, tail = wrappers(model, s)
            maximum = 0.0
            for i in range(0, count, batch_size):
                z = head(torch.from_numpy(x[i:i+batch_size].copy()))
                need(tuple(z.shape[1:]) == SHAPES[s][1:], f'shape mismatch at s{s}')
                out = tail(z).numpy()
                need(np.isfinite(out).all(), 'Nonfinite FP32 output')
                maximum = max(maximum, float(np.max(np.abs(out.astype(np.float64) - full[i:i+batch_size].astype(np.float64)))))
                need(maximum < 1e-3, f'FP32 split mismatch at s{s}')
            gates.append({'split_point_s': s, 'num_samples': count, 'max_abs_error': maximum, 'strict_tolerance': 1e-3, 'status': 'PASS'})
        write_json(output / 'fp32_gates.json', gates)
        print(f'FP32 all 11 splits x {count} samples PASS', flush=True)
        rows = []
        with (output / 'predictions.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle, lineterminator='\n')
            writer.writerow(['split_point_s', 'sample_id', 'patient_id', 'record_id', 'true_label', 'prediction_fp32', 'prediction_int8_fp16'])
            for s in range(11):
                head, tail = wrappers(model, s)
                fp_predictions, q_predictions = [], []
                for i in range(0, count, batch_size):
                    z = head(torch.from_numpy(x[i:i+batch_size].copy()))
                    fp_out = tail(z).numpy()
                    q, scale = quantize_per_channel(to_ncl(z.numpy(), s))
                    # Decode serialized bytes, including FP16 bits. Never use unrounded scales.
                    scale_read = np.frombuffer(scale.tobytes(order='C'), dtype='<f2').reshape(scale.shape)
                    q_read = np.frombuffer(q.tobytes(order='C'), dtype=np.int8).reshape(q.shape)
                    restored = from_ncl(dequantize_per_channel(q_read, scale_read), s)
                    q_out = tail(torch.from_numpy(restored)).numpy()
                    need(np.isfinite(q_out).all(), f'Nonfinite quantized output at s{s}')
                    fp_predictions.extend(fp_out.argmax(axis=1).tolist())
                    q_predictions.extend(q_out.argmax(axis=1).tolist())
                fp_preds, q_preds = np.asarray(fp_predictions), np.asarray(q_predictions)
                correct_fp = int(np.count_nonzero(fp_preds == labels))
                correct_q = int(np.count_nonzero(q_preds == labels))
                fp_accuracy, q_accuracy = 100 * correct_fp / count, 100 * correct_q / count
                row = dict(split_point_s=s, num_samples=count, correct_fp32=correct_fp, correct_int8_fp16=correct_q,
                           accuracy_fp32_percent=fp_accuracy, accuracy_int8_fp16_percent=q_accuracy,
                           accuracy_drop_pp=float(Fraction(100 * (correct_fp-correct_q), count)),
                           relative_accuracy_drop_percent=100 * (correct_fp-correct_q) / correct_fp,
                           gate_status='PASS' if strict_accuracy_gate(correct_fp, correct_q, count) else 'FAIL',
                           prediction_disagreements=int(np.count_nonzero(fp_preds != q_preds)))
                rows.append(row)
                for i, m in enumerate(meta.itertuples()):
                    writer.writerow([s, m.sample_id, m.patient_id, m.record_id, int(labels[i]), int(fp_preds[i]), int(q_preds[i])])
                print(f's{s}: accuracy {fp_accuracy:.6f} -> {q_accuracy:.6f}; drop {fp_accuracy-q_accuracy:.6f} pp', flush=True)
    write_csv(output / 'accuracy.csv', rows)
    columns = list(rows[0])
    table = '| ' + ' | '.join(columns) + ' |\n|' + '|'.join(['---'] * len(columns)) + '|\n'
    for row in rows:
        table += '| ' + ' | '.join(f'{row[k]:.6f}' if isinstance(row[k], float) else str(row[k]) for k in columns) + ' |\n'
    (output / 'accuracy.md').write_text(table, encoding='utf-8')
    passed = all(r['gate_status'] == 'PASS' for r in rows)
    result = {'status': 'PASS' if passed else 'FAIL', 'num_samples': count, 'batch_size': batch_size,
              'gate_rule': '200*(correct_fp32-correct_int8) < num_samples; exact integer strict <0.5 pp',
              'scale_policy': 'Independent per sample/channel over L, also when N>1',
              'per_split_threshold': [{'s': r['split_point_s'], 'drop_pp': r['accuracy_drop_pp'], 'pass_strict_lt_0_5_pp': r['gate_status'] == 'PASS'} for r in rows],
              'worst_split': max(rows, key=lambda r: r['accuracy_drop_pp']),
              'elapsed_seconds': time.monotonic() - started, 'provenance': provenance(' '.join(sys.argv))}
    write_json(output / 'evaluation.json', result)
    print(result['status'], flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/results/week5')
    parser.add_argument('--batch-size', type=int, default=1)
    args = parser.parse_args()
    evaluate(args.package, args.output, args.batch_size)
