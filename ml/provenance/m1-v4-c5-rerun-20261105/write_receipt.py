import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path.cwd();D='ml/provenance/m1-v4-c5-rerun-20261105';L=f'{D}/logs'
RUN='ml/data/runs/mitdb-baseline-v4-c5-rerun-20261105/C5-seed20261101/attempt-1'
EVIDENCE='docs/inbox/sv1_review_m1_v4_grid_20261105.txt'
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
text=lambda p:(ROOT/p).read_text(encoding='utf-8').strip()
git=lambda *a:subprocess.check_output(['git',*a],text=True).strip()
plan=json.loads(text('ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json'))
identity=json.loads(text(f'{RUN}/attempt-identity.json'));summary=json.loads(text(f'{RUN}/summary.json'))
compare=json.loads(text(f'{D}/compare-normal.json'))
train=text(f'{L}/rerun-command.txt').split(' ')
cmds=[{'argv':['python',*train[1:]],'exit_code':int(text(f'{L}/rerun-exit-code.txt')),
       'start_utc':text(f'{L}/rerun-start-utc.txt'),'end_utc':text(f'{L}/rerun-end-utc.txt'),
       'outputs_sha256':{p:sha(p) for p in [f'{L}/rerun.stdout.txt',f'{L}/rerun.stderr.txt']}}]
for m,flag in (('normal',[]),('optimized',['-O'])):
    cmds.append({'argv':['python','-B',*flag,f'{D}/compare_rerun.py','--out',f'{D}/compare-{m}.json'],'exit_code':0,
                 'outputs_sha256':{p:sha(p) for p in [f'{D}/compare-{m}.json',f'{L}/compare-{m}.txt']}})
r={'type':'M1_V4_C5_RERUN_RECEIPT_NOT_SELECTION_INPUT','date':'2026-11-05','prepared_by':'SV3',
   'request':{'item':'SV1 review of M1 v4 grid, section 2c: rerun C5-seed20261101 once on RTX 5060 into a new directory; expect fcf3f846...; if different report to SV1 and do not change checkpoint',
              'evidence_path':EVIDENCE,'evidence_sha256':sha(EVIDENCE),'evidence_form':'Text pasted by SV3 from the SV1 chat message, saved as UTF-8 LF'},
   'source_head':git('rev-parse','HEAD'),'branch':git('rev-parse','--abbrev-ref','HEAD'),
   'origin_dev_ml_sv3':git('rev-parse','origin/dev/ml-sv3'),'origin_main_commits_not_in_branch':int(git('rev-list','--count','HEAD..origin/main')),
   'inputs_sha256':{p:sha(p) for p in ['ml/configs/mitdb_m1_baseline_protocol_v4.json','ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json',
       'ml/manifests/mitdb-baseline-grid-v4/C5-seed20261101.json','ml/provenance/m1-v4-lock-20261103/m1_baseline_v4_lock_and_train_authorization.json',
       *plan['binding']['sources_sha256']]},
   'arrays':{'directory':'ml/data/processed/mitdb-ds1ds2-m1-v3-r2','files_opened_sha256':{n:sha(f'ml/data/processed/mitdb-ds1ds2-m1-v3-r2/{n}') for n in plan['binding']['data_files']}},
   'scripts_sha256':{p:sha(p) for p in [f'{D}/compare_rerun.py',f'{D}/write_receipt.py']},
   'python':sys.version.split()[0],'device':{k:identity[k] for k in ['device','device_name','torch','cuda']},
   'nvidia_driver':'591.86','commands':cmds,
   'result':{'status':compare['status'],'files_compared':compare['files_compared'],'files_matching':compare['files_matching'],
             'selected_epoch':summary['selected_epoch'],'selected_checkpoint_sha256':summary['checkpoint_sha256'],
             'expected_deployment_sha256':compare['expected_deployment_sha256'],'history_sha256':summary['history_sha256'],
             'reload_confusion_exact_written_by_trainer':summary['reload_confusion_exact']},
   'scope':{'DS2_opened':identity['DS2_arrays_opened'],'DS2_evaluated':summary['DS2_evaluated'],'used_for_selection':False,
            'grid_run_directory_modified':False,'checkpoint_changed':False,'authorization':'existing M1 v4 lock 95e65949..., same protocol/plan/slot'},
   'not_verified':['Seeds 20261030 and 20261031 were not rerun on RTX 5060 (SV1 asked for one rerun)',
                   'Cross-GPU difference reported by SV1 (RTX 3050) was not re-examined here',
                   'No CPU reload of the rerun checkpoints']}
with (ROOT/D/'receipt.json').open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print('receipt',sha(f'{D}/receipt.json'))
