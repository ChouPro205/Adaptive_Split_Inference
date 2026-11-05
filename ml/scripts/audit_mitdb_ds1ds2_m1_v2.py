"""Run real-data reproducibility and semantic tamper checks for the M1 candidate."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from mitdb_ds1ds2_m1_v2 import ROOT, digest, read_json, write_json, write_csv, patient


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
               'argv':[os.path.relpath(sys.executable,ROOT).replace('\\','/')]+[
                   os.path.relpath(x,ROOT).replace('\\','/') if Path(x).is_absolute() else x for x in argv],
               'exit_code':r.returncode,'expected_failure':expected,'pass':ok,
               'log_sha256':digest(logs/(name+'.txt'))}
        results.append(entry)
        print(name,'PASS' if ok else 'FAIL',r.returncode,flush=True)
        if not ok:
            write_json(logs/'failed-receipt.json',results)
            raise RuntimeError('Audit failed: '+name)

    config=ROOT/'ml/configs/mitdb_ds1ds2_m1_v2.json'
    verifier='ml/scripts/verify_mitdb_ds1ds2_m1_v2.py'
    def arguments(o=output,a=artifacts,r=raw):
        return [verifier,'--config',str(config),'--raw-dir',str(r),
                '--output',str(o),'--artifacts',str(a)]

    for flags,label in [(['-B'],'normal'),(['-O','-B'],'optimized')]:
        run('verify-'+label,flags+arguments())
        run('unit-tests-'+label,flags+['ml/scripts/test_mitdb_ds1ds2_m1_v2.py'])

    repro=logs/'reproduction-metadata'
    repro_arrays=ROOT/'ml/data/processed'/(output.name+'-reproduction-'+logs.name)
    run('reproduce',['-B','ml/scripts/mitdb_ds1ds2_m1_v2.py','--config',str(config),
        '--raw-dir',str(raw),'--output',str(repro),'--artifacts',str(repro_arrays)])
    comparisons={name:digest(output/name)==digest(repro/name)
                 for name in ['split.csv','normalization.json','record-audit.json','processed-manifest.json',
                              'metric-policy.json','validation-feasibility.json','validation-combinations.csv.gz']}
    comparisons.update({name:digest(artifacts/name)==digest(repro_arrays/name)
                        for name in read_json(output/'processed-manifest.json')['artifacts']})
    if not all(comparisons.values()):
        raise RuntimeError('Byte reproducibility failed')
    write_json(logs/'reproducibility.json',comparisons)

    negative=logs/'negative-fixtures'
    negative.mkdir()
    with (output/'split.csv').open(encoding='utf-8',newline='') as f:
        real_rows=list(csv.DictReader(f))
    train_record=next(r['record_id'] for r in real_rows if r['split']=='train')
    val_record=next(r['record_id'] for r in real_rows if r['split']=='val')
    cases=['patient-forgery','ds2-in-train','202-in-val','normalization-mean',
           'alternate-validation','normalized-array','metadata-lead','missing-source',
           'missing-record','raw-checksum','metric-K','enumeration-row','force-five']
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
            find('100')['split'],find(train_record)['split']='train','test_main'
            expected='DS1 train/validation inventory differs'
        elif case=='202-in-val':
            find('202')['split'],find(val_record)['split']='val','auxiliary_only'
            expected='DS1 train/validation inventory differs'
        elif case=='normalization-mean':
            n['mean']+=.001
            expected='Train-only normalization reconstruction differs'
        elif case=='alternate-validation':
            find(val_record)['split'],find(train_record)['split']='train','val'
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
                meta[0]['lead_index']='1' if meta[0]['lead_index']=='0' else '0'
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
        elif case=='metric-K':
            policy=read_json(target/'metric-policy.json')
            policy['K_indices']=[0]
            (target/'metric-policy.json').write_text(json.dumps(policy,indent=2)+'\n',encoding='utf-8',newline='\n')
            m['metric_policy_sha256']=digest(target/'metric-policy.json',True)
            expected='Frozen validation metric policy differs'
        elif case=='enumeration-row':
            import gzip,hashlib
            file=target/'validation-combinations.csv.gz'
            text=gzip.decompress(file.read_bytes()).decode('utf-8')
            lines=text.splitlines()
            # Alter a feasibility flag but retain CSV and gzip hash bindings.
            lines[1]=lines[1][:-1]+('1' if lines[1][-1]=='0' else '0')
            content=('\n'.join(lines)+'\n').encode('utf-8')
            file.write_bytes(gzip.compress(content,mtime=0))
            m['combinations_gzip_sha256']=digest(file)
            m['combinations_csv_sha256']=hashlib.sha256(content).hexdigest()
            expected='Exhaustive combination rows differ'
        elif case=='force-five':
            find(train_record)['split']='val'
            n['fit_records']=[x['record_id'] for x in rows if x['split']=='train']
            n['fit_patient_ids']=[patient(x) for x in n['fit_records']]
            expected='Reproducible validation differs'
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
             'audit_source_sha256':digest(Path(__file__)),
             'config_sha256':digest(config,True),
             'data_manifest_sha256':digest(output/'processed-manifest.json'),
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
