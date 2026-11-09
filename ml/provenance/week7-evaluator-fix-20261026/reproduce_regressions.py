"""Reproduce both bugs on 0545b47 and rejection by the fix, using synthetic fixtures only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'ml/scripts'))
import numpy as np
from test_week7_reconcile import AccuracyTests
from review_week7_sv2 import sha, need

BASE='0545b470ebccb577baa8e11c1fff1c502f716b17'


def main():
    raw=subprocess.check_output(['git','show',BASE+':ml/scripts/week7_dpu_accuracy.py'],cwd=ROOT)
    results=[]
    for case in ('empty_splits_and_rows','uninventoried_tampered_baseline'):
        fixture=AccuracyTests()
        fixture.setUp()
        try:
            legacy=fixture.root/'legacy_evaluator.py'
            legacy.write_bytes(raw)
            manifest=json.loads((fixture.ref/'manifest.json').read_text())
            if case=='empty_splits_and_rows':
                manifest['split_points']=[]
                fixture.data['rows']=[]
            else:
                del manifest['files']['reference_fp32.npy']
                np.save(fixture.ref/'reference_fp32.npy',np.zeros((8544,5),dtype='<f4'),allow_pickle=False)
            fixture.save_manifest(manifest)
            inputs=fixture.root/'outputs.json'
            inputs.write_text(json.dumps(fixture.data),encoding='utf-8')
            env=os.environ.copy()
            env['PYTHONPATH']=str(ROOT/'ml/scripts')
            checks={}
            for version,script in (('legacy',legacy),('fixed',ROOT/'ml/scripts/week7_dpu_accuracy.py')):
                output=fixture.root/(version+'-evaluation.json')
                args=[sys.executable,'-B',str(script),'evaluate','--reference',str(fixture.ref),
                      '--outputs',str(inputs),'--output',str(output)]
                proc=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True)
                result=json.loads(output.read_text()) if output.exists() else None
                checks[version]={'exit_code':proc.returncode,'result_file_created':output.exists(),
                                 'split_statuses':[r['status'] for r in result['results']] if result else [],
                                 'stderr_last_line':proc.stderr.splitlines()[-1] if proc.stderr else ''}
            need(checks['legacy']['exit_code']==0,'Legacy bug did not reproduce')
            need(checks['fixed']['exit_code']!=0 and not checks['fixed']['result_file_created'],
                 'Fixed CLI accepted malformed fixture')
            if case=='uninventoried_tampered_baseline':
                need(checks['legacy']['split_statuses']==['PASS_ACCURACY_GATE'],'Legacy false PASS missing')
            results.append({'case':case,**checks})
        finally:fixture.tearDown()
    print(json.dumps({'scope':'SYNTHETIC_TEST_ONLY; all outputs are temporary test fixtures',
          'status':'PASS_BOTH_REGRESSIONS_REPRODUCED_AND_FIXED','legacy_commit':BASE,
          'legacy_evaluator_sha256':hashlib.sha256(raw).hexdigest(),
          'fixed_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'fixed_evaluator_sha256':sha(ROOT/'ml/scripts/week7_dpu_accuracy.py'),
          'test_fixture_sha256':sha(ROOT/'ml/scripts/test_week7_reconcile.py'),
          'reproducer_sha256':sha(__file__),'cases':results},indent=2))


if __name__=='__main__':main()
