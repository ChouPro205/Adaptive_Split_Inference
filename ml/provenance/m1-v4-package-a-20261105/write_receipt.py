# Writes the package A candidate receipt once (open 'x'). Hashes files only; no arrays, no model, no DS2.
# Run from the worktree root.
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path.cwd();D='ml/provenance/m1-v4-package-a-20261105';L=f'{D}/logs'
PKG='ml/data/package-a/m1-v4-package-a-20261105-v1'
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
read=lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
git=lambda *a:subprocess.check_output(['git',*a],text=True).strip()
manifest=read(f'{PKG}/manifest.json');arch=read(f'{PKG}/model/architecture.json');rule=read(f'{PKG}/calibration/rule.json')
files={f['path']:f for f in manifest['files']}
build=lambda tag,out:{'argv':['python','-B','ml/scripts/package_m1_v4_a.py','build','--output',out,'--calibration-count','1000'],'exit_code':0,
    'outputs_sha256':{p:sha(p) for p in [f'{L}/build-{tag}.stdout.txt',f'{L}/build-{tag}.stderr.txt']}}
cmds=[build('v1',PKG),build('repro',PKG+'-repro')]
for m,flag in (('normal',[]),('optimized',['-O'])):
    cmds.append({'argv':['python','-B',*flag,'ml/scripts/package_m1_v4_a.py','verify','--package',PKG],'exit_code':0,'outputs_sha256':{f'{L}/verify-{m}.txt':sha(f'{L}/verify-{m}.txt')}})
    cmds.append({'argv':['python','-B',*flag,'ml/scripts/test_package_m1_v4_a.py'],'exit_code':0,'tests':11,'outputs_sha256':{f'{L}/tests-{m}.txt':sha(f'{L}/tests-{m}.txt')}})
r={'type':'M1_V4_PACKAGE_A_CANDIDATE_RECEIPT_NOT_DELIVERED','date':'2026-11-05','prepared_by':'SV3',
   'request':'SV1 review of M1 v4 grid: deliver package A after the checkpoint lock, without DS2 predictions (v1.2 sections 4.3-4.4)',
   'source_head':git('rev-parse','HEAD'),'branch':git('rev-parse','--abbrev-ref','HEAD'),
   'scripts_sha256':{p:sha(p) for p in ['ml/scripts/package_m1_v4_a.py','ml/scripts/test_package_m1_v4_a.py',f'{D}/write_receipt.py']},
   'python':sys.version.split()[0],'commands':cmds,
   'package':{'path':PKG,'status':manifest['status'],'manifest_sha256':sha(f'{PKG}/manifest.json'),'files':len(manifest['files']),
              'bytes':sum(f['file_size_bytes'] for f in manifest['files'])+(ROOT/PKG/'manifest.json').stat().st_size,
              'key_files_sha256':{k:files[k]['sha256'] for k in ['model/checkpoint.pt','firmware/head_parameters.h','model/model_graph.json',
                  'model/architecture.json','data/normalization.json','data/processed-manifest.json','samples.csv','calibration/samples.csv','calibration/rule.json']}},
   'checkpoint_lock':manifest['checkpoint_lock'],'checkpoint':manifest['checkpoint'],
   'architecture':{'parameter_count':arch['parameter_count'],'shapes_N1':{r['s']:r['shape_N1'] for r in arch['splits']},'checks':arch['checks']},
   'cpu_validation_reload':arch['cpu_validation_reload'],
   'header':{'generator':'week3_common.header via week4_common.graph_parameters (same generator and format as R3 week 4)',
             'host_c':read(f'{PKG}/firmware/host_c_verification.json')},
   'golden':manifest['golden'],
   'calibration':{**manifest['calibration'],'train_row_indices_le_int64_sha256':rule['train_row_indices_le_int64_sha256']},
   'reproduction':{'second_build':PKG+'-repro','result':(ROOT/L/'repro-compare.txt').read_text(encoding='utf-8').strip(),
                   'file_lists_sha256':{p:sha(p) for p in [f'{L}/repro-v1.sha256',f'{L}/repro-repro.sha256']},'second_build_removed_after_compare':True},
   'scope':{'DS2_opened':False,'arrays_opened':manifest['arrays']['opened'],'not_included':manifest['not_included']},
   'pending':['SV2 confirms calibration count and IDs (protocol v4 quantization); package is a candidate until then',
              'GitHub Release of the package after that confirmation',
              'DS2 FP32 predictions after the SV2 xmodel s0-s9 SHA lock'],
   'not_verified':['Head on nRF52840 (host C compile only)','DPU/VART execution (SV2)','Calibration adequacy for quantization']}
with (ROOT/D/'receipt.json').open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print('receipt',sha(f'{D}/receipt.json'))
