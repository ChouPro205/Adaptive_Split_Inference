#!/usr/bin/env python3
"""Run the real 50-vector package through the file service; compare and retain outputs."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--serve',type=Path,required=True);a,extra=ap.parse_known_args()
p=a.package.resolve()
anchor='d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
if sha(p/'manifest.json')!=anchor: raise ValueError('Manifest anchor mismatch')
m=json.loads((p/'manifest.json').read_text())
actual={f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file() and f!=p/'manifest.json'}
if actual!={f['path'] for f in m['files']}:raise ValueError('Inventory differs')
for f in m['files']:
 path=p/f['path']
 if path.is_symlink() or not path.resolve().is_relative_to(p) or sha(path)!=f['sha256'] or path.stat().st_size!=f['size_bytes']:raise ValueError('File mismatch '+str(path))
data=json.loads((p/'vectors.json').read_text());vs=data['vectors']
if len(vs)!=50: raise ValueError('Expected 50 real vectors')
a.output.mkdir(parents=True,exist_ok=False); rows=[]
for v in vs:
 i=v['vector_index'];out=a.output/('v%02d'%i)
 req=p/v['files']['request']
 command=[sys.executable,'-B',str(a.serve),'--request',str(req),'--output',str(out),'--public-test-key',*extra]
 with (a.output/('v%02d.log'%i)).open('x') as log:
  code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
 row={'vector_index':i,'split':v['split_point_s'],'exit_code':code,'request_sha256':sha(req)}
 if (out/'result.json').is_file():
  result=json.loads((out/'result.json').read_text());row['status']=result['status']
  if result['status']=='OK':
   ref=np.frombuffer((p/v['files']['logits']).read_bytes(),dtype='<f4');logits=np.array(result['logits'],dtype='<f4')
   row.update(max_abs_error=float(np.max(np.abs(logits.astype(float)-ref))),class_match=bool(np.argmax(logits)==np.argmax(ref)),logits=result['logits'])
 rows.append(row)
 summary={'scope':'50 validation vectors; not independent test accuracy or BLE','rows':rows,
          'execution_complete':all(r.get('status')=='OK' and r['exit_code']==0 for r in rows),
          'numeric_acceptance':'PENDING_TEAM_REVIEW','manifest_sha256':anchor}
 (a.output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
files=[f for f in sorted(a.output.rglob('*')) if f.is_file()]
(a.output/'sha256sum_results.txt').write_text(''.join(sha(f)+'  '+f.relative_to(a.output).as_posix()+'\n' for f in files))
print(json.dumps({k:v for k,v in summary.items() if k!='rows'}));sys.exit(0 if summary['execution_complete'] else 1)
