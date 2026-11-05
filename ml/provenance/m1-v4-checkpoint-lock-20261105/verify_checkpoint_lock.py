# Checks the M1 v4 checkpoint lock against the files it binds, the analyze output, the SV1 evidence and the
# 2c rerun receipt, then runs negative controls. Hashes files only: no arrays, no model, no DS2.
# Explicit checks (not assert) so that -O behaves the same. Run from the worktree root.
import copy,hashlib,json,sys
from pathlib import Path
LOCK=Path('ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def need(ok,message):
    if not ok:raise ValueError(message)
def verify(lock):
    need(lock['type']=='M1_BASELINE_V4_CHECKPOINT_LOCK' and lock['approved_by']=='SV3' and lock['ds2']['status']=='NOT_OPENED','Lock identity')
    for name,b in lock['bindings'].items():need(sha(b['path'])==b['sha256'],f'Binding hash differs: {name}')
    need(sha(lock['review_evidence_path'])==lock['review_evidence'],'Review evidence hash differs')
    evidence=Path(lock['review_evidence_path']).read_text(encoding='utf-8')
    analysis=read(lock['bindings']['analyze_stdout']['path']);selected=analysis['selected']
    need(selected['configuration']==lock['selection']['configuration'] and selected['seed']==lock['selection']['deployment_seed'],'Selection differs from analyze')
    config=next(c for c in analysis['configurations'] if c['configuration']==selected['configuration'])
    need(config['mean_macro_f1']==lock['selection']['mean_validation_macro_f1_K'] and config['sd_sample']==lock['selection']['sd_sample_ddof1'],'Configuration statistics differ')
    seeds={s['seed']:s for s in config['seeds']};listed=Path(lock['bindings']['selected_checkpoints_list']['path']).read_text(encoding='utf-8')
    need(sorted(c['seed'] for c in lock['checkpoints'])==sorted(seeds) and len(lock['checkpoints'])==3,'Checkpoint set differs')
    need([c['seed'] for c in lock['checkpoints'] if c['role']=='deployment']==[selected['seed']],'Deployment role differs')
    for c in lock['checkpoints']:
        s=seeds[c['seed']];p=Path(c['path'])
        need(p.is_file() and p.stat().st_size==c['bytes'] and sha(p)==c['sha256'],f"Checkpoint file differs: {c['slot_id']}")
        need(c['sha256']==s['checkpoint_sha256'] and c['selected_epoch']==s['selected_epoch'] and c['validation_macro_f1_K']==s['score'] and c['gates']==s['gates'],f"Checkpoint differs from analyze: {c['slot_id']}")
        need(f"{c['sha256']}  {c['path']}" in listed,f"Checkpoint missing from selected list: {c['slot_id']}")
        need(c['sha256'] in evidence,f"SHA not confirmed in SV1 evidence: {c['slot_id']}")
    deployment=next(c for c in lock['checkpoints'] if c['role']=='deployment')
    rerun=read(lock['bindings']['rerun_2c_receipt']['path'])['result']
    need(rerun['status']=='RERUN_BYTE_IDENTICAL_DEPLOYMENT_SHA_REPRODUCED' and rerun['selected_checkpoint_sha256']==deployment['sha256'],'Rerun does not reproduce deployment')
    return deployment['sha256']
lock=read(LOCK)
print('lock',sha(LOCK));print('verify: ACCEPTED deployment',verify(lock))
def mutate(path,value):
    bad=copy.deepcopy(lock);o=bad
    for k in path[:-1]:o=o[k]
    o[path[-1]]=value;return bad
controls={'deployment sha256 changed':mutate(['checkpoints',0,'sha256'],'0'*64),
          'deployment role removed':mutate(['checkpoints',0,'role'],'seed_of_selected_configuration'),
          'review evidence hash changed':mutate(['review_evidence'],'0'*64),
          'ds2 status changed':mutate(['ds2','status'],'OPENED')}
failed=0
for name,bad in controls.items():
    try:verify(bad);print('negative control',name+': ACCEPTED (unexpected)');failed=1
    except (ValueError,KeyError) as e:print('negative control',name+': REJECTED',e)
sys.exit(failed)
