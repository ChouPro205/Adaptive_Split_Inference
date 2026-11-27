# Checks the NoPeek v2 lock with the v2 runner's own require_authorization (the gate `run` and `run-pilot-grid`
# apply before any data, model, optimizer or output), plus the informative bindings the runner does not read.
# Negative controls must be rejected. Does not load arrays, build a model or train. Run from the worktree root.
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'ml/scripts')
from nopeek_m1_v2 import require_authorization  # noqa: E402

lock = Path('ml/provenance/m1-nopeek-v2-lock-20261112/m1_nopeek_v2_lock_and_train_authorization.json')
plan = Path('ml/manifests/mitdb-nopeek-m1-v2/plan-manifest.json').resolve()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
a = require_authorization(lock, plan)
print('require_authorization: ACCEPTED', a['protocol_sha256'], a['plan_manifest_sha256'], a['review_evidence'])
for key in ('protocol', 'plan_manifest', 'runner', 'code_receipt'):
    ok = sha(a[f'{key}_path']) == a[f'{key}_sha256']
    print(f'{key}: {"MATCH" if ok else "DIFFERS"} {a[f"{key}_path"]}')
    if not ok:
        sys.exit(1)
controls = {'allow_training=false': {'allow_training': False},
            'review_evidence_path=SV1 2026-11-05 review': {
                'review_evidence_path': 'ml/provenance/m1-v4-checkpoint-lock-20261105/sv1_evidence/sv1_review_m1_v4_grid_20261105.txt',
                'review_evidence': sha('ml/provenance/m1-v4-checkpoint-lock-20261105/sv1_evidence/sv1_review_m1_v4_grid_20261105.txt')},
            'protocol_sha256=v1': {'protocol_sha256': '1e180b45258d4f9c6902aeee8ccfedd5de38f62b9bb4a2f16f9030391b72ebf4'},
            'type=v1': {'type': 'M1_NOPEEK_V1_LOCK_AND_TRAIN_AUTHORIZATION'}}
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
