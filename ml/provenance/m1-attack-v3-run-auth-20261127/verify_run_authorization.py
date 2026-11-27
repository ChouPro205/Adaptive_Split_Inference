# Checks the attack v3 run authorization with the runner's own require_authorization (the gate that attack_m1_v3.py run
# and noise_m1_v3.py run apply before any data, model or output), for each allowed part, plus the bindings the gate does
# not read (runner, part c script, tests, code receipt, checkpoint lock, rho0, noise plan). Five negative controls must
# be rejected for every part. Loads no array, builds no model, trains nothing, opens no DS2. Run from the worktree root.
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'ml/scripts')
from attack_m1_v3 import require_authorization  # noqa: E402

auth = Path(__file__).resolve().parent/'m1_attack_v3_run_authorization.json'
plan = Path('ml/manifests/mitdb-attack-m1-v3/plan-manifest.json').resolve()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
PARTS = ['a', 'b', 'd', 'c']


def fail(msg):
    print(f'FAIL: {msg}')
    sys.exit(1)


a = json.loads(auth.read_text(encoding='utf-8'))
print('authorization', sha(auth))
if a['allow_parts'] != PARTS or a['allow_DS2'] is not False:
    fail('allow_parts or allow_DS2 differ')
for part in PARTS:
    require_authorization(auth, plan, part)
    print(f'require_authorization part {part}: ACCEPTED')
for key in ('protocol', 'protocol_lock', 'plan_manifest', 'code_receipt', 'runner', 'noise_script', 'tests', 'checkpoint_lock', 'rho0'):
    ok = sha(a[f'{key}_path']) == a[f'{key}_sha256']
    print(f'{key}: {"MATCH" if ok else "DIFFERS"} {a[f"{key}_path"]}')
    if not ok:
        fail(key)
p = json.loads(plan.read_text(encoding='utf-8'))
ok = (p['rho0'] == {'path': a['rho0_path'], 'sha256': a['rho0_sha256']} and p['checkpoint_lock_sha256'] == a['checkpoint_lock_sha256']
      and p['sources_sha256'][a['runner_path']] == a['runner_sha256'] and p['sources_sha256'][a['noise_script_path']] == a['noise_script_sha256']
      and p['DS2_access'] is False)
print(f'checkpoint, rho0, runner and part c script in plan: {"MATCH" if ok else "DIFFERS"}')
if not ok:
    fail('plan bindings')
r = json.loads(Path(a['code_receipt_path']).read_text(encoding='utf-8'))
ok = a['noise_plan'] == 'fresh' and r['noise_plan_proposal'].startswith('fresh noise every epoch (no fallback)')
print(f'noise_plan fresh, as in the code receipt proposal: {"MATCH" if ok else "DIFFERS"}')
if not ok:
    fail('noise plan')
# The v3 gate checks that the evidence file exists and has the SHA the authorization states; unlike the v2 gate it cannot
# pin the file through the protocol (the SV1 message postdates r5). This script pins it instead.
EVIDENCE = ('ml/provenance/m1-sv1-evidence-20261127/tra_loi_Ky_Anh_tong_hop_tuan11_20261127.txt',
            '696f3309170ab5649da91806b688cf515bfafe053c342975c93e8b9e0c8a3d55')
ok = (a['review_evidence_path'], a['review_evidence']) == EVIDENCE and sha(EVIDENCE[0]) == EVIDENCE[1]
print(f'review evidence is SV1 2026-11-27 (pinned here, not by the gate): {"MATCH" if ok else "DIFFERS"}')
if not ok:
    fail('review evidence')
OLD = 'ml/provenance/m1-sv1-evidence-20261126/tra_loi_Ky_Anh_r5_xac_nhan_khoa_20261126.txt'
swapped = {**a, 'review_evidence_path': OLD, 'review_evidence': sha(OLD)}
with tempfile.TemporaryDirectory() as d:
    bad = Path(d)/'swapped.json'
    bad.write_text(json.dumps(swapped), encoding='utf-8')
    require_authorization(bad, plan, 'a')
    print('gate limitation: evidence swapped for SV1 2026-11-26 with its own SHA is ACCEPTED by the gate; '
          'rejected only by the pinned check above')
controls = {'allow_DS2=true': {'allow_DS2': True},
            'review_evidence=SHA of SV1 2026-11-26 with the 2026-11-27 path': {'review_evidence': sha(OLD)},
            'protocol_sha256=r4': {'protocol_sha256': '7b2b1271c292ca9003dfb5e6e2980d032f3af371dee289e41967bb48d5675200'},
            'type=attack v2 lock': {'type': 'M1_ATTACK_V2_LOCK_AND_TRIAL_AUTHORIZATION'},
            'approved_by empty': {'approved_by': ''}}
with tempfile.TemporaryDirectory() as d:
    for name, change in controls.items():
        bad = Path(d)/'bad.json'
        bad.write_text(json.dumps({**a, **change}), encoding='utf-8')
        for part in PARTS:
            try:
                require_authorization(bad, plan, part)
            except ValueError as e:
                print(f'negative control {name} part {part}: REJECTED {type(e).__name__}')
            else:
                fail(f'negative control {name} part {part}: ACCEPTED (unexpected)')
print('PASS_GATE_CHECK_NO_ARRAY_NO_MODEL_NO_FIT_NO_DS2')
