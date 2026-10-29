"""Prepare frozen-test inputs/references and evaluate keyed offline DPU outputs.

No hardware execution, model selection, training, or new numeric threshold.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import subprocess
import sys

import numpy as np

from review_week7_sv2 import ROOT, CHECKPOINT, CLASSES, need, read, read_csv, sha, write


def csv_write(path, fields, rows):
    with Path(path).open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def prepare(output, package, splits=(2, 5, 8), batch_size=32):
    import torch
    from week5_common_v2 import baseline, load_test, mapping, ANCHOR
    from quantization import quantize_per_channel, dequantize_per_channel, to_ncl, from_ncl
    from week3_sv2_common import wrappers
    need(not output.exists(), 'Refuse to overwrite prepared evaluation')
    need(batch_size > 0, 'Batch size must be positive')
    need(splits and len(set(splits)) == len(splits) and all(s in range(10) for s in splits),
         'Choose unique deployed tail splits s0..s9')
    model, _ = baseline(package)
    checkpoint = torch.load(package / 'model/checkpoint.pt', map_location='cpu', weights_only=True)
    x, y, meta, report = load_test(checkpoint)
    need(len(y) == 8544 and len(set(meta.sample_id)) == 8544, 'Expected 8544 unique frozen test IDs')
    output.mkdir(parents=True)
    sample_rows = [{'sample_index': i, 'sample_id': m.sample_id, 'patient_id': m.patient_id,
                    'record_id': m.record_id, 'true_label': int(y[i])} for i,m in enumerate(meta.itertuples())]
    csv_write(output / 'samples.csv', list(sample_rows[0]), sample_rows)
    files = ['samples.csv']
    full = []
    with torch.inference_mode():
        for start in range(0, len(y), batch_size):
            full.append(model(torch.from_numpy(x[start:start+batch_size].copy())).numpy())
        full = np.concatenate(full).astype('<f4')
        need(full.shape == (8544,5) and np.isfinite(full).all(), 'Invalid FP32 baseline')
        np.save(output / 'reference_fp32.npy', full, allow_pickle=False)
        files.append('reference_fp32.npy')
        for s in splits:
            head, tail = wrappers(model, s)
            shape = next(r['shape'] for r in mapping() if r['split_point_s'] == s)
            shape = tuple(shape) if s < 9 else (1,32)
            inputs = np.lib.format.open_memmap(output / f'inputs_s{s}.npy', mode='w+', dtype='<f4',
                                               shape=(8544, *shape[1:]))
            q_logits = []
            for start in range(0, len(y), batch_size):
                z = head(torch.from_numpy(x[start:start+batch_size].copy()))
                # Same per-sample/channel FP16 wire scale serialization as week5.
                q, scales = quantize_per_channel(to_ncl(z.numpy(), s))
                scales = np.frombuffer(scales.tobytes(order='C'), dtype='<f2').reshape(scales.shape)
                restored = from_ncl(dequantize_per_channel(q, scales), s)
                inputs[start:start+len(restored)] = restored
                q_logits.append(tail(torch.from_numpy(restored.copy())).numpy())
            inputs.flush()
            del inputs
            out = np.concatenate(q_logits).astype('<f4')
            need(out.shape == (8544,5) and np.isfinite(out).all(), 'Invalid quantized FP32-tail reference')
            np.save(output / f'reference_wire_fp32tail_s{s}.npy', out, allow_pickle=False)
            files.extend([f'inputs_s{s}.npy', f'reference_wire_fp32tail_s{s}.npy'])
            print(f'prepared s{s}: 8544 authenticated test inputs and reference logits', flush=True)
    prov = read(ROOT / 'results/week7/edge/provenance.json')
    calibration_samples = read_csv(package/'samples.csv')
    need(len(calibration_samples)==20 and all(r['split']=='val' for r in calibration_samples),
         'Frozen golden calibration membership differs')
    summary = metrics(y, full.argmax(axis=1))
    manifest = {'schema': 'sv3-week7-dpu-reference/1', 'status': 'PREPARED_NOT_DPU_ACCEPTANCE',
                'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT,text=True).strip(),
                'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in
                    [Path(__file__), ROOT/'ml/scripts/review_week7_sv2.py', ROOT/'ml/scripts/week5_common_v2.py',
                     ROOT/'ml/scripts/evaluate_week5_v2.py', ROOT/'ml/scripts/week3_sv2_common.py',
                     ROOT/'ml/src/quantization.py', ROOT/'ml/src/mitdb_week2_data.py']},
                'checkpoint_sha256': CHECKPOINT, 'model_manifest_sha256': ANCHOR, 'class_order': CLASSES,
                'count': 8544, 'split_points': list(splits), 'batch_size_reference': batch_size,
                'dataset': report, 'fp32_baseline_metrics': summary,
                'input_policy': 'Per-sample/channel INT8 [-127,127], serialized FP16 scales, unprotected dequantized FP32 NCL; s9 NC. No P1/BLE required for offline numeric evaluation.',
                'dpu_requantization': 'Use actual native runner fix_point/DPU_ROUND and report it; do not apply FP32 <1e-3 as DPU gate',
                'expected_xmodel_sha256': {str(s):prov['model_hashes'][str(s)] for s in splits},
                'expected_calibration': {'split':'val','sample_ids':[r['sample_id'] for r in calibration_samples],
                    'samples_csv_sha256':sha(package/'samples.csv'),
                    'golden_sha256':{str(s):sha(package/f'golden/z_s{s}.npy') for s in splits}},
                'gate': '200*(correct_fp32-correct_dpu) < count; strict accuracy drop <0.5 pp; requires complete coverage',
                'files': {p:{'sha256':sha(output/p), 'size_bytes':(output/p).stat().st_size} for p in files}}
    write(output / 'manifest.json', manifest)
    return manifest


def metrics(labels, predictions):
    cm = np.zeros((5,5), dtype=np.int64)
    for true,pred in zip(labels,predictions):
        cm[int(true), int(pred)] += 1
    per_class = []
    for c,name in enumerate(CLASSES):
        tp, support, predicted = int(cm[c,c]), int(cm[c].sum()), int(cm[:,c].sum())
        precision = tp/predicted if predicted else 0.0
        recall = tp/support if support else 0.0
        per_class.append({'class':name, 'support':support, 'predicted':predicted,
                          'precision':precision, 'recall':recall,
                          'f1':2*precision*recall/(precision+recall) if precision+recall else 0.0})
    return {'count':int(cm.sum()), 'correct':int(np.trace(cm)),
            'accuracy_percent':100*int(np.trace(cm))/int(cm.sum()) if cm.sum() else None,
            'confusion_matrix_true_rows_predicted_columns':cm.tolist(), 'per_class':per_class,
            'macro_f1':sum(r['f1'] for r in per_class)/5, 'zero_division':0}


def error_stats(actual, reference):
    if not len(actual):
        return None
    errors = np.abs(actual.astype(np.float64)-reference.astype(np.float64))
    return {'max_abs':float(errors.max()), 'mean_abs':float(errors.mean()),
            'p95_abs':float(np.percentile(errors,95)),
            'rmse':float(np.sqrt(np.mean(errors**2))),
            'per_class_max_abs':errors.max(axis=0).tolist(), 'gate':'DESCRIPTIVE_ONLY_NO_DPU_LOGIT_THRESHOLD'}


def validate_split_points(splits):
    need(isinstance(splits, list) and bool(splits), 'split_points must be a nonempty list')
    need(all(type(s) is int and 0 <= s <= 9 for s in splits),
         'split_points must contain integers s0..s9, not bool or other types')
    need(len(set(splits)) == len(splits), 'split_points must not contain duplicates')


def validate_reference(reference):
    """Authenticate the complete required inventory before any evaluation reads."""
    manifest = read(reference/'manifest.json')
    need(manifest['schema'] == 'sv3-week7-dpu-reference/1' and manifest['count'] == 8544,
         'Wrong frozen reference schema/count')
    need(manifest['checkpoint_sha256'] == CHECKPOINT and manifest['class_order'] == CLASSES, 'Reference identity differs')
    validate_split_points(manifest.get('split_points'))
    inventory = manifest.get('files')
    need(isinstance(inventory, dict), 'Reference inventory must be an object')
    required = {'samples.csv', 'reference_fp32.npy'}
    for s in manifest['split_points']:
        required.update((f'inputs_s{s}.npy', f'reference_wire_fp32tail_s{s}.npy'))
    missing = required - inventory.keys()
    need(not missing, 'Missing required reference inventory entries: ' + ', '.join(sorted(missing)))
    directory = reference.resolve()
    for p,entry in inventory.items():
        candidate = reference/p
        need(candidate.resolve().is_relative_to(directory), 'Unsafe reference member')
        need(candidate.is_file(), 'Missing reference file: '+p)
        need(candidate.stat().st_size==entry['size_bytes'] and sha(candidate)==entry['sha256'],
             'Reference file differs: '+p)
    return manifest


def ensure_result_coverage(result):
    """Refuse empty, duplicate or partial split results at the CLI boundary."""
    requested = result.get('requested_split_points')
    validate_split_points(requested)
    rows = result.get('results')
    need(isinstance(rows, list) and bool(rows), 'No evaluated split results')
    actual = [r.get('split_point_s') for r in rows]
    need(all(type(s) is int for s in actual) and len(actual)==len(requested) and
         set(actual)==set(requested), 'Results do not cover requested splits exactly')


def evaluate(reference, outputs):
    from evaluate_week5_v2 import strict_accuracy_gate
    manifest = validate_reference(reference)
    samples = read_csv(reference/'samples.csv')
    need(len(samples)==8544 and len({r['sample_id'] for r in samples})==8544, 'Reference IDs differ')
    ids = {r['sample_id']:i for i,r in enumerate(samples)}
    labels = np.array([int(r['true_label']) for r in samples])
    need(set(labels).issubset(range(5)), 'Reference labels invalid')
    full = np.load(reference/'reference_fp32.npy',allow_pickle=False)
    need(full.shape==(8544,5) and np.isfinite(full).all(), 'Reference logits invalid')
    data = read(outputs)
    need(data['schema']=='sv3-week7-dpu-output/1' and data['class_order']==CLASSES, 'Output schema/classes differ')
    need(data['reference_manifest_sha256']==sha(reference/'manifest.json'), 'Output reference manifest differs')
    need(data['checkpoint_sha256']==CHECKPOINT and data['backend']=='kv260_root_cpu_dpu', 'Output backend/checkpoint differs')
    provenance = data['provenance']
    for field in ('board_id','runtime_version','source_commit','runner_sha256','quantization_policy','cpu_plugins_sha256'):
        need(bool(provenance.get(field)), 'Missing backend provenance: '+field)
    def digest(value):
        return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
    need(digest(provenance['runner_sha256']), 'Invalid runner hash')
    need(isinstance(provenance['source_commit'],str) and len(provenance['source_commit'])==40 and
         all(c in '0123456789abcdef' for c in provenance['source_commit']), 'Invalid source commit')
    need(all(digest(v) for v in provenance['cpu_plugins_sha256'].values()), 'Invalid CPU plugin hash')
    calibration = provenance['calibration']
    need(calibration['split'] in ('train','val') and calibration.get('sample_ids') and calibration.get('artifacts_sha256'),
         'Exact non-test calibration identities/artifacts required')
    need(not set(calibration['sample_ids']) & set(ids), 'Test samples leaked into calibration')
    need(len(set(calibration['sample_ids']))==len(calibration['sample_ids']) and
         all(digest(v) for v in calibration['artifacts_sha256'].values()), 'Invalid calibration provenance')
    expected_calibration = manifest['expected_calibration']
    need(calibration['split']==expected_calibration['split'] and
         set(calibration['sample_ids'])==set(expected_calibration['sample_ids']),
         'Calibration membership differs from frozen model build')
    need(calibration['samples_csv_sha256']==expected_calibration['samples_csv_sha256'] and
         calibration['golden_sha256']==expected_calibration['golden_sha256'], 'Calibration golden hashes differ')
    for s in manifest['split_points']:
        model = provenance['models'][str(s)]
        need(model['xmodel_sha256']==manifest['expected_xmodel_sha256'][str(s)], 'Deployment model differs')
        need(digest(model['quant_info_sha256']) and digest(model['compile_log_sha256']), 'Missing quantizer/compiler hashes')
    keyed = {}
    for r in data['rows']:
        need(type(r['split_point_s']) is int and r['split_point_s'] in manifest['split_points'], 'Unexpected split')
        need(r['sample_id'] in ids, 'Unexpected sample ID')
        key = (r['split_point_s'], r['sample_id'])
        need(key not in keyed, 'Duplicate output sample/split')
        keyed[key]=r
    results = []
    for s in manifest['split_points']:
        good, actual, missing, failed = [], [], [], []
        for sid,i in ids.items():
            r = keyed.get((s,sid))
            if r is None:
                missing.append(sid)
                continue
            values = r.get('logits')
            valid = (isinstance(values,list) and len(values)==5 and
                     all(type(v) in (int,float) and np.isfinite(v) and abs(v)<=np.finfo(np.float32).max for v in values))
            if r['status']!='OK' or not valid:
                failed.append({'sample_id':sid,'status':r['status'], 'reason':r.get('reason','invalid logits' if not valid else '')})
                continue
            good.append(i)
            actual.append(values)
        actual = np.array(actual,dtype='<f4').reshape(-1,5)
        good = np.array(good,dtype=int)
        valid_metrics = metrics(labels[good],actual.argmax(axis=1))
        base_correct = int(np.count_nonzero(full.argmax(axis=1)==labels))
        complete = not missing and not failed
        gate = strict_accuracy_gate(base_correct,valid_metrics['correct'],8544)
        wire = np.load(reference/f'reference_wire_fp32tail_s{s}.npy',allow_pickle=False)
        need(wire.shape==(8544,5) and np.isfinite(wire).all(), 'Wire reference invalid')
        failed_indices = [ids[sid] for sid in missing] + [ids[r['sample_id']] for r in failed]
        results.append({'split_point_s':s, 'status':('PASS_ACCURACY_GATE' if gate else 'FAIL_ACCURACY_GATE') if complete else 'INCOMPLETE_NO_ACCEPTANCE',
                        'expected':8544,'received':len(good)+len(failed),'valid':len(good), 'missing_ids':missing,'failures':failed,
                        'valid_output_metrics':valid_metrics,
                        'missing_or_failed_by_true_class':{name:int(sum(labels[i]==c for i in failed_indices)) for c,name in enumerate(CLASSES)},
                        'correct_fp32':base_correct, 'correct_dpu':valid_metrics['correct'],
                        'accuracy_all_8544_percent':100*valid_metrics['correct']/8544,
                        'accuracy_drop_pp':100*(base_correct-valid_metrics['correct'])/8544,
                        'strict_count_gate_met':gate,'complete_coverage':complete,
                        'logit_errors_vs_full_fp32':error_stats(actual,full[good]),
                        'logit_errors_vs_wire_fp32_tail':error_stats(actual,wire[good]),
                        'class_agreement_vs_full_fp32':int(sum(actual.argmax(axis=1)==full[good].argmax(axis=1))),
                        'class_agreement_vs_wire_fp32_tail':int(sum(actual.argmax(axis=1)==wire[good].argmax(axis=1)))})
    return {'schema':'sv3-week7-dpu-evaluation/1','input_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'evaluator_sha256':sha(__file__), 'reference_manifest_sha256':sha(reference/'manifest.json'),
            'output_sha256':sha(outputs), 'class_order':CLASSES, 'backend_provenance':provenance,
            'gate':'200*(correct_fp32-correct_dpu) < 8544; missing/failure prevents acceptance',
            'scope':'Offline accuracy only; no BLE/E2E/privacy or signature acceptance',
            'requested_split_points':manifest['split_points'], 'results':results}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare')
    prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--model-package',type=Path,default=ROOT/'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1')
    prep.add_argument('--splits',type=int,nargs='+',default=[2,5,8])
    prep.add_argument('--batch-size',type=int,default=32)
    ev=sub.add_parser('evaluate')
    ev.add_argument('--reference',type=Path,required=True)
    ev.add_argument('--outputs',type=Path,required=True)
    ev.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=='prepare':
        m=prepare(args.output,args.model_package,tuple(args.splits),args.batch_size)
        print(m['status'], 'FP32 correct:', m['fp32_baseline_metrics']['correct'])
        return 0
    else:
        need(not args.output.exists(),'Refuse to overwrite evaluation')
        result=evaluate(args.reference,args.outputs)
        ensure_result_coverage(result)
        write(args.output,result)
        print([(r['split_point_s'],r['status']) for r in result['results']])
        return 0 if all(r['status']=='PASS_ACCURACY_GATE' for r in result['results']) else 1


if __name__=='__main__':
    sys.exit(main())
