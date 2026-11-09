import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path.cwd();D=Path('ml/provenance/m1-v4-grid-analysis-20261103');RUN='ml/data/runs/mitdb-baseline-v4-20261103'
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
A=['ml/scripts/baseline_grid_v4.py','analyze','--protocol','ml/configs/mitdb_m1_baseline_protocol_v4.json','--plan','ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json','--results',RUN]
def cmd(argv,exit_code,outputs):return {'argv':['python','-B',*argv],'exit_code':exit_code,'outputs_sha256':{o:sha(o) for o in outputs}}
def optimized(c):c=json.loads(json.dumps(c));c['argv'].insert(2,'-O');return c
L=D/'logs';cmds=[]
cmds+=[cmd(A,0,[f'{L}/analyze-normal.stdout.json',f'{L}/analyze-normal.stderr.txt']),
       optimized(cmd(A,0,[f'{L}/analyze-optimized.stdout.json',f'{L}/analyze-optimized.stderr.txt']))]
for m in ('normal','optimized'):
    c=cmd([f'{D}/crosscheck_grid_v4.py','--out',f'{D}/crosscheck-{m}.json'],0,[f'{D}/crosscheck-{m}.json',f'{L}/crosscheck-{m}.txt'])
    cmds.append(optimized(c) if m=='optimized' else c)
cmds.append(cmd([f'{D}/crosscheck_negative.py',f'{D}/crosscheck_grid_v4.py','<scratch directory outside repo>'],0,[f'{L}/crosscheck-negative.txt']))
for t in ('baseline_grid_v4','baseline_sampler_v4','m1_protocol_assets_v4'):
    for m in ('normal','optimized'):
        c=cmd([f'ml/scripts/test_{t}.py','-v'],0,[f'{L}/tests-{t}-{m}.txt']);cmds.append(optimized(c) if m=='optimized' else c)
cmds.append(cmd([f'{D}/render_selection_v4.py','--tables',f'{D}/selection-tables.md','--sums',f'{D}/selected-checkpoints.sha256'],0,[f'{D}/selection-tables.md',f'{D}/selected-checkpoints.sha256',f'{L}/render.txt']))
cmds.append({'argv':['sha256sum','-c',f'{D}/selected-checkpoints.sha256'],'exit_code':0,'outputs_sha256':{f'{L}/checkpoint-sha256sum-c.txt':sha(f'{L}/checkpoint-sha256sum-c.txt')}})
git=lambda *a:subprocess.check_output(['git',*a],text=True).strip()
r={'type':'M1_V4_GRID_ANALYSIS_RECEIPT_NOT_CHECKPOINT_LOCK','date':'2026-11-03','prepared_by':'SV3',
   'source_head':git('rev-parse','HEAD'),'branch':git('rev-parse','--abbrev-ref','HEAD'),
   'origin_dev_ml_sv3':git('rev-parse','origin/dev/ml-sv3'),'origin_main_commits_not_in_branch':int(git('rev-list','--count','HEAD..origin/main')),
   'inputs_sha256':{p:sha(p) for p in ['ml/configs/mitdb_m1_baseline_protocol_v4.json','ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json',
       'ml/provenance/m1-v4-lock-20261103/m1_baseline_v4_lock_and_train_authorization.json','ml/manifests/mitdb-ds1ds2-m1-v3-r2/metric-policy.json',
       f'{RUN}/grid-result.json','ml/scripts/baseline_grid_v4.py','ml/scripts/baseline_selection_v4.py']},
   'scripts_sha256':{p:sha(p) for p in [f'{D}/crosscheck_grid_v4.py',f'{D}/crosscheck_negative.py',f'{D}/render_selection_v4.py']},
   'python':sys.version.split()[0],'commands':cmds,
   'tests':{'baseline_grid_v4':33,'baseline_sampler_v4':12,'m1_protocol_assets_v4':17,'result':'OK in normal and -O'},
   'scope':{'DS2_opened':False,'model_instantiated_by_analysis':False,'arrays_opened_by_analysis':False,'checkpoint_lock':False,
            'tests_open':'train/val arrays and val_metadata.csv only (preflight/assets fixtures); no DS2',
            'run_directory_modified':False},
   'not_verified':['Rerun determinism of the real grid (only random-data smoke before lock)','Checkpoint reload by this analysis (reload_confusion_exact comes from the training script)','Independent review by SV1']}
out=ROOT/D/'receipt.json'
with out.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print('receipt',sha(D/'receipt.json'))
