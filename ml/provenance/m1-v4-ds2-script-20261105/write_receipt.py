# Writes the DS2 script receipt once (open 'x'). Hashes files only. Run from the worktree root.
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path.cwd();D='ml/provenance/m1-v4-ds2-script-20261105';L=f'{D}/logs';OUT='ml/data/ds2-dryrun-m1-v4-20261105'
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
read=lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
git=lambda *a:subprocess.check_output(['git',*a],text=True).strip()
cmds=[]
for d in ('cpu','cuda'):
    cmds.append({'argv':['python','-B','ml/scripts/evaluate_m1_v4_ds2.py','dry-run','--output',f'{OUT}/{d}','--device',d],'exit_code':0,
                 'outputs_sha256':{p:sha(p) for p in [f'{L}/dry-run-{d}.stdout.txt',f'{L}/dry-run-{d}.stderr.txt',f'{OUT}/{d}/summary.json',f'{OUT}/{d}/predictions.csv']}})
for m,flag in (('normal',[]),('optimized',['-O'])):
    cmds.append({'argv':['python','-B',*flag,'ml/scripts/test_evaluate_m1_v4_ds2.py'],'exit_code':0,'tests':10,'outputs_sha256':{f'{L}/tests-{m}.txt':sha(f'{L}/tests-{m}.txt')}})
summary={d:read(f'{OUT}/{d}/summary.json') for d in ('cpu','cuda')}
r={'type':'M1_V4_DS2_SCRIPT_RECEIPT_DRY_RUN_ONLY','date':'2026-11-05','prepared_by':'SV3',
   'request':'SV1 review of M1 v4 grid, section 2b: DS2 script for SV1 review before use',
   'source_head':git('rev-parse','HEAD'),'branch':git('rev-parse','--abbrev-ref','HEAD'),
   'scripts_sha256':{p:sha(p) for p in ['ml/scripts/evaluate_m1_v4_ds2.py','ml/scripts/test_evaluate_m1_v4_ds2.py','ml/scripts/package_m1_v4_a.py',
                                         'ml/scripts/m1_metrics_v4.py',f'{D}/write_receipt.py']},
   'python':sys.version.split()[0],'commands':cmds,
   'requirements_2b':{'validation_dry_run_reproduces_locked_confusion_of_3_C5':[s['dry_run']['status'] for s in summary.values()],
                      'two_rows_one_pass':'Both rows come from one prediction pass per checkpoint; the first row drops one record (202 on DS2, 118 in the dry run) and the two confusions are checked to partition',
                      'device_recorded':{d:{k:s['environment'][k] for k in ('device','device_name','cudnn_allow_tf32','matmul_allow_tf32')} for d,s in summary.items()},
                      'per_beat_predictions_with_record_id':'predictions.csv: seed, role, row_index, record_id, patient_id, r_peak_sample, original_symbol, true/predicted class, 5 logits',
                      'per_record_confusion':'Descriptive only, as declared in the checkpoint lock'},
   'cpu_cuda':(ROOT/L/'cpu-cuda-compare.txt').read_text(encoding='utf-8').strip().splitlines(),
   'tf32_finding':'With the PyTorch default (cuDNN TF32 on) the CUDA logits differed from CPU by up to 0.0118 on validation (labels identical); the script now disables TF32 so the DS2 pass is strict FP32. The earlier outputs were removed before this receipt',
   'ds2_gate':'ds2 mode needs an external M1_V4_DS2_FP32_AUTHORIZATION binding the checkpoint lock, the SV2 xmodel lock, SV1 review evidence, the device and this script SHA; writes once to ml/data/ds2-m1-v4-fp32',
   'scope':{'DS2_opened':False,'ds2_mode_run':False,'authorization_file_created':False},
   'not_verified':['ds2 mode itself (never run; tests only check its refusal paths)','test_main == test_aux22 minus 202 (checked only inside ds2 mode)']}
with (ROOT/D/'receipt.json').open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print('receipt',sha(f'{D}/receipt.json'))
