# Checks the attack v2 lock with the runner's own require_authorization (the gate run-trial applies before any data,
# model or output), plus the informative bindings the gate does not read (runner, code receipt, checkpoint hashes against
# the plan). Negative controls must be rejected. Does not load arrays, build a model or train. Run from the worktree root.
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'ml/scripts')
from attack_m1_v2 import require_authorization  # noqa: E402

lock = Path('ml/provenance/m1-attack-v2-lock-20261113/m1_attack_v2_lock_and_trial_authorization.json')
plan = Path('ml/manifests/mitdb-attack-m1-v2/plan-manifest.json').resolve()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
a = require_authorization(lock, plan)
print('require_authorization: ACCEPTED', a['protocol_sha256'], a['plan_manifest_sha256'], a['review_evidence'])
for key in ('protocol', 'plan_manifest', 'runner', 'code_receipt'):
    ok = sha(a[f'{key}_path']) == a[f'{key}_sha256']
    print(f'{key}: {"MATCH" if ok else "DIFFERS"} {a[f"{key}_path"]}')
    if not ok:
        sys.exit(1)
p = json.loads(plan.read_text(encoding='utf-8'))
ok = (p['checkpoints']['rho0']['sha256'] == a['rho0_sha256'] and p['checkpoint_lock_sha256'] == a['checkpoint_lock_sha256']
      and {s: e['sha256'] for s, e in p['checkpoints']['rho1'].items()} == a['rho1_sha256'] and p['sources_sha256'][a['runner_path']] == a['runner_sha256'])
print(f'checkpoints and runner in plan: {"MATCH" if ok else "DIFFERS"}')
if not ok:
    sys.exit(1)
controls = {'allow_trial=false': {'allow_trial': False},
            'review_evidence_path=SV1 2026-11-09 message': {
                'review_evidence_path': 'ml/provenance/m1-sv1-evidence-20261111/tra_loi_Ky_Anh_PR44_20261109.txt',
                'review_evidence': sha('ml/provenance/m1-sv1-evidence-20261111/tra_loi_Ky_Anh_PR44_20261109.txt')},
            'protocol_sha256=v1': {'protocol_sha256': '869170470794aa2b1e7fca6eb217bc96b7eb0396be0720e39ca82cf79a19b5a0'},
            'type=NoPeek v2 lock': {'type': 'M1_NOPEEK_V2_LOCK_AND_TRAIN_AUTHORIZATION'},
            'approved_by empty': {'approved_by': ''}}
with tempfile.TemporaryDirectory() as d:
    for name, change in controls.items():
        bad = Path(d)/'bad.json'
        bad.write_text(json.dumps({**a, **change}), encoding='utf-8')
        try:
            require_authorization(bad, plan)
        except ValueError as e:
            print(f'negative control {name}: REJECTED {type(e).__name__}')
        else:
            print(f'negative control {name}: ACCEPTED (unexpected)')
            sys.exit(1)
