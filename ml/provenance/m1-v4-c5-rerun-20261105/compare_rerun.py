# Compares the 2c rerun of C5-seed20261101 with the grid attempt byte for byte. Hashes files only:
# no arrays, no model, no DS2. Run from the worktree root. Exit 0 only if every trainer output matches
# and the selected checkpoint is the SV1-confirmed deployment SHA.
import argparse, hashlib, json, sys
from pathlib import Path
ORIGINAL=Path('ml/data/runs/mitdb-baseline-v4-20261103/C5-seed20261101/attempt-1')
RERUN=Path('ml/data/runs/mitdb-baseline-v4-c5-rerun-20261105/C5-seed20261101/attempt-1')
DEPLOYMENT='fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c'
RUNNER_ONLY={'stdout.txt','stderr.txt'}  # Written by baseline_grid_v4 run, not by the trainer.
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
original={f.name for f in ORIGINAL.iterdir()}-RUNNER_ONLY;rerun={f.name for f in RERUN.iterdir()}
files=[{'file':n,'original_sha256':sha(ORIGINAL/n),'rerun_sha256':sha(RERUN/n)} for n in sorted(original&rerun)]
for f in files:f['match']=f['original_sha256']==f['rerun_sha256']
summary=json.loads((RERUN/'summary.json').read_text(encoding='utf-8'))
selected=sha(RERUN/summary['checkpoint'])
r={'original':ORIGINAL.as_posix(),'rerun':RERUN.as_posix(),'files_compared':len(files),
   'files_matching':sum(f['match'] for f in files),'only_in_original':sorted(original-rerun),'only_in_rerun':sorted(rerun-original),
   'runner_only_files_excluded':sorted(RUNNER_ONLY),'selected_epoch':summary['selected_epoch'],'selected_checkpoint':summary['checkpoint'],
   'selected_checkpoint_sha256':selected,'expected_deployment_sha256':DEPLOYMENT,'files':files}
ok=not r['only_in_original'] and not r['only_in_rerun'] and r['files_matching']==len(files) and selected==DEPLOYMENT
r['status']='RERUN_BYTE_IDENTICAL_DEPLOYMENT_SHA_REPRODUCED' if ok else 'RERUN_DIFFERS_REPORT_TO_SV1_NO_CHECKPOINT_CHANGE'
with a.out.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,indent=2)+'\n')
print(r['status'],r['files_matching'],'/',len(files),selected)
sys.exit(0 if ok else 1)
