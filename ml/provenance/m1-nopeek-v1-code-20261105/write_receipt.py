# Writes the NoPeek v1 code receipt once (open 'x'). Hashes files only. Run from the worktree root.
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path.cwd();D='ml/provenance/m1-nopeek-v1-code-20261105';L=f'{D}/logs';SMOKE='ml/data/smoke-nopeek-m1-v1-20261105'
PLAN='ml/manifests/mitdb-nopeek-m1-v1/plan-manifest.json'
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
read=lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
text=lambda p:(ROOT/p).read_text(encoding='utf-8').strip()
git=lambda *a:subprocess.check_output(['git',*a],text=True).strip()
plan=read(PLAN)
cmds=[{'argv':['python','-B','ml/scripts/nopeek_m1_v1.py','prepare'],'exit_code':0,'outputs_sha256':{PLAN:sha(PLAN)}}]
for m,flag in (('normal',[]),('optimized',['-O'])):
    cmds.append({'argv':['python','-B',*flag,'ml/scripts/nopeek_m1_v1.py','preflight'],'exit_code':0,'outputs_sha256':{f'{L}/preflight-{m}.txt':sha(f'{L}/preflight-{m}.txt')}})
    cmds.append({'argv':['python','-B',*flag,'ml/scripts/test_nopeek_m1_v1.py'],'exit_code':0,'tests':9,'outputs_sha256':{f'{L}/tests-{m}.txt':sha(f'{L}/tests-{m}.txt')}})
cmds.append({'argv':['python','-B','ml/scripts/nopeek_m1_v1.py','smoke','--output',SMOKE,'--epochs','2'],'exit_code':0,
             'start_utc':text(f'{L}/smoke-start-utc.txt'),'end_utc':text(f'{L}/smoke-end-utc.txt'),
             'outputs_sha256':{p:sha(p) for p in [f'{L}/smoke.stdout.txt',f'{L}/smoke.stderr.txt',f'{SMOKE}/smoke-result.json']}})
smoke=read(f'{SMOKE}/smoke-result.json');identity=read(f'{SMOKE}/smoke-s2-lambda5/attempt-identity.json')
r={'type':'M1_NOPEEK_V1_CODE_RECEIPT_NOT_LOCKED_NO_MITDB_FIT','date':'2026-11-05','prepared_by':'SV3',
   'request':'Runner, plan and tests for protocol mitdb-m1-nopeek-v1, written before SV1 review so both are reviewed together',
   'source_head':git('rev-parse','HEAD'),'branch':git('rev-parse','--abbrev-ref','HEAD'),
   'protocol':{'path':'ml/configs/mitdb_m1_nopeek_protocol_v1.json','sha256':sha('ml/configs/mitdb_m1_nopeek_protocol_v1.json'),'status':'CANDIDATE_FOR_SV1_REVIEW_NOT_LOCKED'},
   'plan':{'path':PLAN,'sha256':sha(PLAN),'status':plan['status'],'pilot_runs':sum(x['stage']=='pilot' for x in plan['runs']),
           'grid_runs':sum(x['stage']=='grid' for x in plan['runs']),'sources_sha256':plan['sources_sha256']},
   'scripts_sha256':{p:sha(p) for p in ['ml/scripts/nopeek_m1_v1.py','ml/scripts/test_nopeek_m1_v1.py',f'{D}/write_receipt.py']},
   'python':sys.version.split()[0],'commands':cmds,
   'smoke':{**smoke,'data':'Random arrays with the real train/val class counts written by the smoke itself; no MITDB file read',
            'device':{k:identity[k] for k in ('device','device_name','torch','cuda','cudnn_allow_tf32','matmul_allow_tf32')},
            'epochs_note':'Smoke runs 2 epochs; the protocol fixes 10'},
   'tf32':'Run configs carry cudnn_allow_tf32 true and matmul_allow_tf32 false explicitly (PyTorch defaults, as package A was trained); open point 5 for SV1',
   'scope':{'MITDB_fit':False,'pilot':False,'grid':False,'DS2_opened':False,'preflight':'hashes train/val array files only; no model, no fit'},
   'not_verified':['Any run on MITDB (needs the NoPeek lock after SV1 review)','Epoch 0 = package A check on real validation (exercised only in run_stage)','Run time of the real grid']}
with (ROOT/D/'receipt.json').open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print('receipt',sha(f'{D}/receipt.json'))
