"""Per-class metrics for the frozen Week 5 test predictions, FP32 vs INT8+FP16.

Input is the predictions.csv of a fresh evaluate_week5_v2.py run; it must be
byte-identical to the frozen ml/results/week5/predictions.csv and agree with
that run's accuracy.csv. No new threshold is introduced: the Week 5 gate stays
the strict accuracy-drop rule. Precision is null for a class never predicted;
F1 = 2TP/(2TP+FP+FN), so it is 0 for such a class (macro-F1 averages all 5).
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / 'ml/results/week5/predictions.csv'
CLASSES = ('N', 'S', 'V', 'F', 'Q')
HEADER = ['split_point_s', 'sample_id', 'patient_id', 'record_id', 'true_label', 'prediction_fp32', 'prediction_int8_fp16']


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(predictions):
    with predictions.open(encoding='utf-8', newline='') as handle:
        reader = csv.reader(handle)
        need(next(reader) == HEADER, 'Unexpected predictions header')
        rows = list(reader)
    splits = {}
    for r in rows:
        s, sample, patient, _, y, fp, q = r
        splits.setdefault(int(s), []).append((sample, patient, int(y), int(fp), int(q)))
    need(sorted(splits) == list(range(11)), 'Expected splits 0..10')
    reference = [(sample, patient, y) for sample, patient, y, _, _ in splits[0]]
    need(len(reference) == 8544 and len({r[0] for r in reference}) == 8544, 'Expected 8544 unique test samples')
    for s, items in splits.items():
        need([(a, b, c) for a, b, c, _, _ in items] == reference, f'Split {s} sample order/labels differ')
        need(all(0 <= v < len(CLASSES) for item in items for v in item[2:]), f'Split {s} has an unknown class')
    return splits, reference


def metrics(y, p):
    k = len(CLASSES)
    cm = [[0] * k for _ in range(k)]
    for t, pr in zip(y, p):
        cm[t][pr] += 1
    per_class = {}
    for c, name in enumerate(CLASSES):
        tp = cm[c][c]
        support, predicted = sum(cm[c]), sum(cm[t][c] for t in range(k))
        fp, fn = predicted - tp, support - tp
        per_class[name] = {'support': support, 'predicted': predicted, 'tp': tp, 'fp': fp, 'fn': fn,
                           'precision': tp / predicted if predicted else None,
                           'recall': tp / support if support else None,
                           'f1': 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None}
    recalls = [v['recall'] for v in per_class.values() if v['recall'] is not None]
    f1s = [v['f1'] for v in per_class.values() if v['f1'] is not None]
    correct = sum(cm[c][c] for c in range(k))
    return {'confusion_matrix': cm, 'per_class': per_class, 'correct': correct, 'accuracy': correct / len(y),
            'macro_f1': sum(f1s) / len(f1s), 'balanced_accuracy': sum(recalls) / len(recalls)}


def changes(y, fp, q):
    out = {}
    for c, name in enumerate(CLASSES):
        idx = [i for i, t in enumerate(y) if t == c]
        out[name] = {'changed_predictions': sum(fp[i] != q[i] for i in idx),
                     'fp32_correct_to_int8_wrong': sum(fp[i] == c and q[i] != c for i in idx),
                     'fp32_wrong_to_int8_correct': sum(fp[i] != c and q[i] == c for i in idx)}
    return out


def evaluate(accuracy, output):
    predictions = accuracy / 'predictions.csv'
    need(not output.exists(), 'Use a new output directory')
    need(FROZEN.is_file(), f'Missing frozen predictions {FROZEN}; hydrate the Week 5 assets first')
    need(sha(predictions) == sha(FROZEN), 'Fresh predictions differ from the frozen official predictions')
    splits, reference = load(predictions)
    with (accuracy / 'accuracy.csv').open(encoding='utf-8', newline='') as handle:
        gate = {int(r['split_point_s']): r for r in csv.DictReader(handle)}
    y = [t for _, _, t in reference]
    result = {'schema': 'week5-per-class/1', 'classes': list(CLASSES),
              'source': {'predictions': predictions.resolve().relative_to(ROOT).as_posix(), 'sha256': sha(predictions),
                         'frozen_predictions_sha256': sha(FROZEN),
                         'accuracy_csv_sha256': sha(accuracy / 'accuracy.csv')},
              'test_set': {'num_samples': len(y), 'patients': sorted({p for _, p, _ in reference}),
                           'support': {name: y.count(c) for c, name in enumerate(CLASSES)}},
              'conventions': {'precision': 'null when a class is never predicted',
                              'f1': '2TP/(2TP+FP+FN); 0 when TP=0',
                              'macro_f1': 'unweighted mean over the 5 classes',
                              'balanced_accuracy': 'mean recall over classes with support > 0'},
              'threshold': 'None added; Week 5 acceptance remains the strict accuracy-drop gate',
              'splits': {}}
    for s in range(11):
        fp = [r[3] for r in splits[s]]
        q = [r[4] for r in splits[s]]
        base, quant = metrics(y, fp), metrics(y, q)
        need(base['correct'] == int(gate[s]['correct_fp32']) and quant['correct'] == int(gate[s]['correct_int8_fp16']),
             f'Split {s} counts differ from accuracy.csv')
        result['splits'][str(s)] = {
            'fp32': base, 'int8_fp16': quant,
            'delta': {'macro_f1': quant['macro_f1'] - base['macro_f1'],
                      'balanced_accuracy': quant['balanced_accuracy'] - base['balanced_accuracy'],
                      'recall': {n: quant['per_class'][n]['recall'] - base['per_class'][n]['recall'] for n in CLASSES}},
            'prediction_changes': changes(y, fp, q)}
    output.mkdir(parents=True)
    with (output / 'per_class_metrics.json').open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    with (output / 'per_class_metrics.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['split_point_s', 'precision_mode', 'class', 'support', 'predicted', 'tp', 'fp', 'fn',
                         'precision', 'recall', 'f1', 'changed_predictions', 'fp32_correct_to_int8_wrong', 'fp32_wrong_to_int8_correct'])
        for s, data in result['splits'].items():
            for mode in ('fp32', 'int8_fp16'):
                for n, v in data[mode]['per_class'].items():
                    change = data['prediction_changes'][n] if mode == 'int8_fp16' else {}
                    writer.writerow([s, mode, n, v['support'], v['predicted'], v['tp'], v['fp'], v['fn'],
                                     '' if v['precision'] is None else repr(v['precision']), repr(v['recall']), repr(v['f1']),
                                     change.get('changed_predictions', ''), change.get('fp32_correct_to_int8_wrong', ''),
                                     change.get('fp32_wrong_to_int8_correct', '')])
    with (output / 'confusion_matrices.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['split_point_s', 'precision_mode', 'true_class', *[f'pred_{n}' for n in CLASSES]])
        for s, data in result['splits'].items():
            for mode in ('fp32', 'int8_fp16'):
                for c, n in enumerate(CLASSES):
                    writer.writerow([s, mode, n, *data[mode]['confusion_matrix'][c]])
    with (output / 'summary.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['split_point_s', 'accuracy_fp32', 'accuracy_int8_fp16', 'macro_f1_fp32', 'macro_f1_int8_fp16',
                         'balanced_accuracy_fp32', 'balanced_accuracy_int8_fp16', *[f'recall_{n}_fp32' for n in CLASSES],
                         *[f'recall_{n}_int8_fp16' for n in CLASSES]])
        for s, data in result['splits'].items():
            b, q = data['fp32'], data['int8_fp16']
            writer.writerow([s, repr(b['accuracy']), repr(q['accuracy']), repr(b['macro_f1']), repr(q['macro_f1']),
                             repr(b['balanced_accuracy']), repr(q['balanced_accuracy']),
                             *[repr(b['per_class'][n]['recall']) for n in CLASSES],
                             *[repr(q['per_class'][n]['recall']) for n in CLASSES]])
    print(f"PER_CLASS: 11 splits x {len(y)} samples; support {result['test_set']['support']}; output={output}")
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accuracy', type=Path, required=True, help='Directory of a fresh evaluate_week5_v2.py run')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.accuracy.resolve(), args.output.resolve())
