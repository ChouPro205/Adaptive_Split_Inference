"""Validate the existing frozen reference with the fixed evaluator, without inference."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'ml/scripts'))
import numpy as np
from review_week7_sv2 import read_csv, sha, need
from week7_dpu_accuracy import validate_reference


def main():
    reference=ROOT/'.cache/week7-reconcile/accuracy-8544-delivery'
    manifest=validate_reference(reference)
    original=ROOT/'ml/provenance/week7-reconcile-20261026/prepared-reference-manifest.json'
    need((reference/'manifest.json').read_bytes()==original.read_bytes(), 'Original manifest changed')
    manifest_sha=sha(reference/'manifest.json')
    need(manifest_sha=='612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c',
         'Frozen manifest anchor differs')
    samples=read_csv(reference/'samples.csv')
    need(len(samples)==8544 and len({r['sample_id'] for r in samples})==8544,'Sample IDs differ')
    labels=np.array([int(r['true_label']) for r in samples])
    full=np.load(reference/'reference_fp32.npy',mmap_mode='r',allow_pickle=False)
    need(full.shape==(8544,5) and np.isfinite(full).all(),'FP32 shape/values differ')
    correct=int(np.count_nonzero(full.argmax(axis=1)==labels))
    need(correct==8393,'Historical FP32 correct count differs')
    shapes={}
    expected={2:(8544,16,180),5:(8544,48,90),8:(8544,64,22)}
    for s in manifest['split_points']:
        inputs=np.load(reference/f'inputs_s{s}.npy',mmap_mode='r',allow_pickle=False)
        wire=np.load(reference/f'reference_wire_fp32tail_s{s}.npy',mmap_mode='r',allow_pickle=False)
        need(inputs.shape==expected[s] and wire.shape==(8544,5),'Prepared tensor shape differs')
        shapes[str(s)]={'inputs':list(inputs.shape),'wire_reference':list(wire.shape)}
    print(json.dumps({'status':'PASS_EXISTING_REFERENCE_VALIDATION_ONLY',
          'evaluator_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'evaluator_sha256':sha(ROOT/'ml/scripts/week7_dpu_accuracy.py'),
          'verifier_sha256':sha(__file__), 'reference_generation_commit':manifest['source_commit'],
          'reference_manifest_sha256':manifest_sha,'split_points':manifest['split_points'],
          'files_hash_size_verified':len(manifest['files']),
          'size_bytes_verified':sum(r['size_bytes'] for r in manifest['files'].values()),
          'unique_test_sample_ids':8544,'fp32_correct_recounted_without_inference':correct,
          'shapes':shapes,'DPU_acceptance':'NOT_EVALUATED_NO_REAL_DPU_OUTPUT',
          'reference_regenerated':False},indent=2))


if __name__=='__main__':main()
