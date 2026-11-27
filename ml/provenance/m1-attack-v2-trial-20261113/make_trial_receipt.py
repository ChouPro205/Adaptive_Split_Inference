# Writes the attack v2 week 11 trial receipt once (open 'x') after run-trial: run logs, source head = lock commit, the
# authorization used = the lock file, identity (TF32 off, golden check, DS2 not opened), the pair order of the protocol,
# every output file hashed, byte copies of the result and pair JSON files, and the caveat line SV1 asked for.
# Hashes and copies local files only; no model, no data. Run from the worktree root: python -B <this file>
import hashlib
import json
import shutil
from pathlib import Path

R = Path('ml/provenance/m1-attack-v2-trial-20261113'); L = R/'logs'
OUT = Path('ml/data/runs/attack-m1-v2-trial-20261113')
LOCK = Path('ml/provenance/m1-attack-v2-lock-20261113/m1_attack_v2_lock_and_trial_authorization.json')
PROTOCOL = Path('ml/configs/mitdb_m1_attack_protocol_v2.json')
PLAN = Path('ml/manifests/mitdb-attack-m1-v2/plan-manifest.json')
LOCK_COMMIT = '96c2ac9148b12544aaf712346db92cf4072b1e2c'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))  # noqa: E731


def need(condition, message):
    if not condition:
        raise SystemExit(f'CHECK FAILED: {message}')


need((L/'run-exit-code.txt').read_text(encoding='utf-8').strip() == '0', 'run-trial did not exit 0')
need((L/'source-head.txt').read_text(encoding='utf-8').strip() == LOCK_COMMIT, 'Run source head is not the lock commit')
need((L/'source-status.txt').read_bytes() == b'', 'Tracked files differed from the lock commit at run start')
ident, result, p = read(OUT/'trial-identity.json'), read(OUT/'trial-result.json'), read(PROTOCOL)
need(ident['authorization_sha256'] == sha(LOCK) and ident['plan_manifest_sha256'] == sha(PLAN) == result['plan_manifest_sha256']
     and ident['protocol_sha256'] == sha(PROTOCOL) == result['protocol_sha256'], 'Run bindings differ from the lock')
need(ident['cudnn_allow_tf32'] is False and ident['matmul_allow_tf32'] is False and ident['deterministic_algorithms'] is True, 'TF32 or determinism differs')
need(ident['golden_check']['bitwise_equal'] is True and ident['DS2_opened'] is False and result['DS2_opened'] is False, 'Golden check or DS2 state differs')
need(ident['counts'] == p['data']['trial_week11']['counts'], 'Split counts differ from the protocol')
need(result['status'] == 'TRIAL_COMPLETED_REPORT_ONLY' and result['caveat'] == p['trial_week11_scope']['receipt_caveat'], 'Result status or caveat differs')
order = ['s0-rho0-base'] + (['s0-rho0-escalated'] if result['capacity_check']['decision'] == 'escalated' else []) + \
        [f'{s}-{rho}' for s, rho in p['trial_week11_scope']['order'][1:]]
need([r['pair'] for r in result['table']] == order, 'Pair order differs from the protocol')
need(all(sha(OUT/name) == digest for name, digest in result['pair_files_sha256'].items()), 'A pair file differs from trial-result.json')
files = sorted(f for f in OUT.iterdir() if f.is_file())
need(sorted(f.name for f in files) == sorted(['trial-identity.json', 'trial-result.json'] + [f'{k}{e}' for k in order for e in ('.json', '-arrays.npz', '-attackers.pt')]),
     'Output inventory differs')
copies = R/'results'
copies.mkdir()
for f in files:
    if f.suffix == '.json':
        shutil.copyfile(f, copies/f.name)
        need(sha(copies/f.name) == sha(f), f'Copy differs: {f.name}')
stderr = (L/'run.stderr.txt').read_text(encoding='utf-8')
receipt = {
    'type': 'M1_ATTACK_V2_TRIAL_RECEIPT_REPORT_ONLY', 'prepared_by': 'SV3',
    'lock': {'path': LOCK.as_posix(), 'sha256': sha(LOCK), 'commit': LOCK_COMMIT},
    'run': {'command': f'python -B ml/scripts/attack_m1_v2.py run-trial --authorization {LOCK.as_posix()} --output {OUT.as_posix()}',
            'source_head': LOCK_COMMIT, 'tracked_files_clean': True,
            'start_utc': (L/'run-start-utc.txt').read_text(encoding='utf-8').strip(), 'end_utc': (L/'run-end-utc.txt').read_text(encoding='utf-8').strip(),
            'exit_code': 0, 'stderr_bytes': len(stderr.encode('utf-8')), 'device_name': ident['device_name'], 'torch': ident['torch'], 'cuda': ident['cuda'],
            'cudnn_allow_tf32': False, 'matmul_allow_tf32': False, 'deterministic_algorithms': True},
    'bindings': {'protocol_sha256': ident['protocol_sha256'], 'plan_manifest_sha256': ident['plan_manifest_sha256']},
    'golden_check': ident['golden_check'], 'counts': ident['counts'], 'N': result['N'], 'Pi_min': result['Pi_min'],
    'capacity_check': result['capacity_check'], 'table': result['table'],
    'caveat': result['caveat'],
    'outputs_sha256': {f.as_posix(): sha(f) for f in files},
    'tracked_copies': {(copies/f.name).as_posix(): sha(copies/f.name) for f in files if f.suffix == '.json'},
    'logs_sha256': {f.as_posix(): sha(f) for f in sorted(L.iterdir())},
    'scope': {'data': 'DS1 train/val (N = 22) only', 'DS2_opened': False, 'attacks': ['A1', 'B_naive'], 'defence_seeds': 'deployment seed only',
              'use': 'Early warning only; never the paper main numbers (protocol data.trial_week11.caveat)'},
    'status': 'TRIAL_RECEIPT_REPORT_ONLY'}
with (R/'receipt.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('receipt', sha(R/'receipt.json'))
