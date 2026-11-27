# Writes the attack v3 parts a, b, d (DS1) receipt once (open 'x') after attack_m1_v3.py run --parts abd: run logs,
# source head = authorization commit with no tracked change, the authorization used, identity (TF32 off, determinism,
# golden and S0c reference checks, DS2 not opened), the part b reproduction gate, every output file hashed, byte copies
# of the JSON outputs. Hashes and copies local files only; no model, no data. Run from the worktree root:
# python -B <this file>
import hashlib
import json
import shutil
from pathlib import Path

R = Path('ml/provenance/m1-attack-v3-abd-run-20261127'); L = R/'logs'
OUT = Path('ml/data/runs/attack-m1-v3-abd-20261127')
AUTH = Path('ml/provenance/m1-attack-v3-run-auth-20261127/m1_attack_v3_run_authorization.json')
PROTOCOL = Path('ml/configs/mitdb_m1_attack_protocol_v3_r5.json')
PLAN = Path('ml/manifests/mitdb-attack-m1-v3/plan-manifest.json')
AUTH_COMMIT = 'e55e82b1db4e96b2f725d1e56273baa798f0135e'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))  # noqa: E731


def need(condition, message):
    if not condition:
        raise SystemExit(f'CHECK FAILED: {message}')


need((L/'run-exit-code.txt').read_text(encoding='utf-8').strip() == '0', 'run did not exit 0')
need((L/'source-head.txt').read_text(encoding='utf-8').strip() == AUTH_COMMIT, 'Run source head is not the authorization commit')
status = (L/'source-status.txt').read_text(encoding='utf-8').splitlines()
need(all(line.startswith('?? ') for line in status), 'Tracked files differed from the authorization commit at run start')
ident, result = read(OUT/'run-identity-abd.json'), read(OUT/'run-result-abd.json')
need(ident['authorization_sha256'] == sha(AUTH) and ident['plan_manifest_sha256'] == sha(PLAN) and ident['protocol_sha256'] == sha(PROTOCOL),
     'Run bindings differ from the authorization')
need(ident['parts'] == ['a', 'b', 'd'] and read(AUTH)['allow_DS2'] is False, 'Parts or DS2 rule differ')
need(ident['cudnn_allow_tf32'] is False and ident['matmul_allow_tf32'] is False and ident['deterministic_algorithms'] is True, 'TF32 or determinism differs')
need(ident['golden_check_s9_s10']['bitwise_equal'] is True and ident['s0c_golden_check']['bitwise_equal'] is True
     and ident['s0c_reference_check_trial_beats']['bitwise_equal'] is True, 'Golden or S0c reference check differs')
need(ident['DS2_opened'] is False and result['DS2_opened'] is False and result['status'] == 'COMPLETED_REPORT_ONLY', 'Result status or DS2 state differs')
b = read(OUT/'part-b-result.json')
need(b['gate']['element_equal'] is True and b['gate']['targets'] == [2, 4, 5, 8, 9, 10], 'Part b reproduction gate differs')
files = sorted(f for f in OUT.iterdir() if f.is_file())
copies = R/'results'
copies.mkdir()
for f in files:
    if f.suffix == '.json':
        shutil.copyfile(f, copies/f.name)
        need(sha(copies/f.name) == sha(f), f'Copy differs: {f.name}')
stderr = (L/'run.stderr.txt').read_bytes()
receipt = {
    'type': 'M1_ATTACK_V3_ABD_DS1_RECEIPT_REPORT_ONLY', 'prepared_by': 'SV3',
    'authorization': {'path': AUTH.as_posix(), 'sha256': sha(AUTH), 'commit': AUTH_COMMIT},
    'run': {'command': f'python -B ml/scripts/attack_m1_v3.py run --parts abd --output {OUT.as_posix()} --authorization {AUTH.as_posix()}',
            'source_head': AUTH_COMMIT, 'tracked_files_clean': True, 'untracked_at_start': [line[3:] for line in status],
            'start_utc': (L/'run-start-utc.txt').read_text(encoding='utf-8').strip(), 'end_utc': (L/'run-end-utc.txt').read_text(encoding='utf-8').strip(),
            'exit_code': 0, 'stderr_bytes': len(stderr), 'device_name': ident['device_name'], 'torch': ident['torch'], 'cuda': ident['cuda'],
            'cudnn_allow_tf32': False, 'matmul_allow_tf32': False, 'deterministic_algorithms': True},
    'bindings': {'protocol_sha256': ident['protocol_sha256'], 'plan_manifest_sha256': ident['plan_manifest_sha256']},
    'checks': {k: ident[k] for k in ('golden_check_s9_s10', 's0c_golden_check', 's0c_reference_check_trial_beats')} | {'part_b_reproduction_gate': b['gate']},
    'result': {k: result[k] for k in ('a', 'b', 'd')},
    'result_meaning': {'a': 'Pi of B_naive at s9, s10 (FP32 logits) and S0c', 'b': 'Pi_v3 per source = min over B_naive and B_composite',
                       'd': 'Pi_k10 per row (rho0, worst over aggregators and draw modes)'},
    'outputs_sha256': {f.as_posix(): sha(f) for f in files},
    'tracked_copies': {(copies/f.name).as_posix(): sha(copies/f.name) for f in files if f.suffix == '.json'},
    'logs_sha256': {f.as_posix(): sha(f) for f in sorted(L.iterdir())},
    'scope': {'data': 'DS1 (N = 22) only', 'DS2_opened': False, 'parts': ['a', 'b', 'd'],
              'use': 'Development numbers and early warning only (SV1 2026-11-27 section 3); they select no parameter. Part c runs next from this directory'},
    'status': 'ABD_DS1_RECEIPT_REPORT_ONLY'}
with (R/'receipt.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('receipt', sha(R/'receipt.json'))
