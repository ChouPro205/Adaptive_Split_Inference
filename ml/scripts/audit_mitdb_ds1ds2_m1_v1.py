"""Run real-data reproducibility and semantic tamper checks for the M1 candidate."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from mitdb_ds1ds2_m1_v1 import ROOT, digest, read_json, write_json, write_csv, patient


def audit(raw, output, artifacts, logs):
    logs.mkdir(parents=True,exist_ok=False)
    results=[]

    def run(name,argv,expected=None):
        r=subprocess.run([sys.executable,*argv],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        # Public receipts use logical runtime and repository-relative locations.
        text=r.stdout+r.stderr
        for original,replacement in [(str(ROOT),'WORKTREE'),(str(logs),'AUDIT_LOGS'),
                                     (str(raw),'RAW_DATA'),(str(Path(sys.executable).parent.parent),'PROJECT_VENV')]:
            text=text.replace(original,replacement)
        (logs/(name+'.txt')).write_text(text,encoding='utf-8',newline='\n')
        ok=(r.returncode==0) if expected is None else (r.returncode!=0 and expected in text)
        entry={'name':name,'runtime':'project_shared_venv','python_flags':argv[:2],
               'exit_code':r.returncode,'expected_failure':expected,'pass':ok,
               'log_sha256':digest(logs/(name+'.txt'))}
        results.append(entry)
        print(name,'PASS' if ok else 'FAIL',r.returncode,flush=True)
        if not ok:
            write_json(logs/'failed-receipt.json',results)
            raise RuntimeError('Audit failed: '+name)

    config=ROOT/'ml/configs/mitdb_ds1ds2_m1_v1.json'
    verifier='ml/scripts/verify_mitdb_ds1ds2_m1_v1.py'
    def arguments(o=output,a=artifacts,r=raw):
        return [verifier,'--config',str(config),'--raw-dir',str(r),
                '--output',str(o),'--artifacts',str(a)]

    for flags,label in [(['-B'],'normal'),(['-O','-B'],'optimized')]:
        run('verify-'+label,flags+arguments())
        run('unit-tests-'+label,flags+['ml/scripts/test_mitdb_ds1ds2_m1_v1.py'])

    repro=logs/'reproduction-metadata'
    repro_arrays=ROOT/'ml/data/processed/mitdb-ds1ds2-m1-v1-reproduction'
    run('reproduce',['-B','ml/scripts/mitdb_ds1ds2_m1_v1.py','--config',str(config),
        '--raw-dir',str(raw),'--output',str(repro),'--artifacts',str(repro_arrays)])
    comparisons={name:digest(output/name)==digest(repro/name)
                 for name in ['split.csv','normalization.json','record-audit.json','processed-manifest.json']}
    comparisons.update({name:digest(artifacts/name)==digest(repro_arrays/name)
                        for name in read_json(output/'processed-manifest.json')['artifacts']})
    if not all(comparisons.values()):
        raise RuntimeError('Byte reproducibility failed')
    write_json(logs/'reproducibility.json',comparisons)

    negative=logs/'negative-fixtures'
    negative.mkdir()
    cases=['patient-forgery','ds2-in-train','202-in-val','normalization-mean',
           'alternate-validation','normalized-array','metadata-lead','missing-source',
           'missing-record','raw-checksum']
    for case in cases:
        target=negative/case
        shutil.copytree(output,target)
        m=read_json(target/'processed-manifest.json')
        n=read_json(target/'normalization.json')
        with (target/'split.csv').open(encoding='utf-8',newline='') as f:
            rows=list(csv.DictReader(f))
        find=lambda r:next(x for x in rows if x['record_id']==r)
        a=artifacts
        r=raw
        if case=='patient-forgery':
            find('202')['patient_id']='P202'
            expected='Canonical patient identity mismatch'
        elif case=='ds2-in-train':
            find('100')['split'],find('101')['split']='train','test_main'
            expected='DS1 train/validation inventory differs'
        elif case=='202-in-val':
            find('202')['split'],find('114')['split']='val','auxiliary_only'
            expected='DS1 train/validation inventory differs'
        elif case=='normalization-mean':
            n['mean']+=.001
            expected='Train-only normalization reconstruction differs'
        elif case=='alternate-validation':
            find('114')['split'],find('101')['split']='train','val'
            n['fit_records']=[x['record_id'] for x in rows if x['split']=='train']
            n['fit_patient_ids']=[patient(x) for x in n['fit_records']]
            expected='Reproducible validation differs'
        elif case in ['normalized-array','metadata-lead']:
            a=negative/(case+'-arrays')
            a.mkdir()
            changed='train_X.npy' if case=='normalized-array' else 'val_metadata.csv'
            for file in artifacts.iterdir():
                if file.name==changed:
                    shutil.copy2(file,a/file.name)
                else:
                    os.link(file,a/file.name)
            if case=='normalized-array':
                import numpy as np
                x=np.load(a/changed,mmap_mode='r+')
                x[0,0]+=np.float32(1)
                x.flush()
                del x
                expected='Raw-to-normalized window mismatch'
            else:
                with (a/changed).open(encoding='utf-8',newline='') as f:
                    reader=csv.DictReader(f)
                    fields=reader.fieldnames
                    meta=list(reader)
                next(x for x in meta if x['record_id']=='114')['lead_index']='0'
                with (a/changed).open('w',encoding='utf-8',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n')
                    writer.writeheader()
                    writer.writerows(meta)
                expected='Raw label/identity/lead mismatch'
            m['artifacts'][changed]={'sha256':digest(a/changed),'bytes':(a/changed).stat().st_size}
        elif case=='missing-source':
            m['sources_sha256'].pop('ml/src/mitdb_baseline_model.py')
            expected='Manifest schema/inventory differs'
        elif case=='missing-record':
            rows.pop()
            expected='Duplicate/missing manifest records'
        else:
            r=negative/'bad-raw'
            r.mkdir()
            (r/'SHA256SUMS.txt').write_text('corrupted checksum manifest\n',encoding='ascii')
            expected='Official checksum manifest differs'
        # Rebind the hashes: these tests must fail semantically, not just on stale hashes.
        with (target/'split.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['record_id','patient_id','split'],lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        m['split_sha256']=digest(target/'split.csv',True)
        n['split_sha256']=m['split_sha256']
        (target/'normalization.json').write_text(json.dumps(n,indent=2)+'\n',encoding='utf-8',newline='\n')
        m['normalization_sha256']=digest(target/'normalization.json',True)
        (target/'processed-manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8',newline='\n')
        for flags,label in [(['-B'],'normal'),(['-O','-B'],'optimized')]:
            run(case+'-'+label,flags+arguments(target,a,r),expected)

    # Capture runtime/dependency evidence without requiring GPU or loading checkpoints.
    import numpy,wfdb,platform
    receipt={'status':'PASS_CANDIDATE_AUDIT_NOT_LOCKED_NOT_REVIEWED',
             'python':platform.python_version(),'numpy':numpy.__version__,'wfdb':wfdb.__version__,
             'positive_and_negative_commands':results,'reproducible_files':len(comparisons),
             'real_data':True,'predictions_performed':False,'training_performed':False,
             'negative_fixtures':'Copies/hardlinks in local audit only; synthetic unit fixtures are not dataset evidence.'}
    write_json(logs/'receipt.json',receipt)
    print(receipt['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['raw-dir','output','artifacts','logs']:
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    audit(a.raw_dir.resolve(),a.output.resolve(),a.artifacts.resolve(),a.logs.resolve())
