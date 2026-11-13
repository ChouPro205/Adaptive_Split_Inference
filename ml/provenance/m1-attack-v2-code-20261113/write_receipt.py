# Writes the attack v2 code receipt once (open 'x'): protocol v2 and its predecessor, plan, runner, test and source hashes,
# the commands with their exit codes and log hashes, the preflight counts and the smoke summary. Hashes local files only.
# Run from the worktree root after the logs exist: python -B <this file>
import hashlib
import json
import re
from pathlib import Path

R = Path('ml/provenance/m1-attack-v2-code-20261113'); L = R/'logs'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))  # noqa: E731


def need(condition, message):
    if not condition:
        raise SystemExit(f'CHECK FAILED: {message}')


codes = dict(line.split(' ', 1) for line in (L/'exit-codes.txt').read_text(encoding='utf-8').splitlines())
need(all(v.split()[0] == '0' for v in codes.values()), f'A command did not exit 0: {codes}')
plan_path = Path('ml/manifests/mitdb-attack-m1-v2/plan-manifest.json')
plan, protocol = read(plan_path), read('ml/configs/mitdb_m1_attack_protocol_v2.json')
need(plan['protocol_sha256'] == sha('ml/configs/mitdb_m1_attack_protocol_v2.json'), 'Plan does not bind protocol v2')
need(all(sha(n) == h for n, h in plan['sources_sha256'].items()), 'A source changed after the plan')
need(f"plan {sha(plan_path)}" in codes['prepare'] and (L/'prepare.stdout.txt').read_text(encoding='utf-8').strip() == f'PLAN {sha(plan_path)}', 'Prepare log differs from the plan')
tests = {}
for mode in ('normal', 'optimized'):
    text = (L/f'tests-{mode}.txt').read_text(encoding='utf-8')
    ran = re.search(r'^Ran (\d+) tests', text, re.M)
    need(ran and text.rstrip().endswith('OK'), f'Tests {mode} did not pass')
    tests[mode] = {'command': f"python -B{' -O' if mode == 'optimized' else ''} ml/scripts/test_attack_m1_v2.py", 'exit_code': 0,
                   'tests': int(ran.group(1)), 'log_sha256': sha(L/f'tests-{mode}.txt')}
pre_n, pre_o = (L/'preflight-normal.txt').read_bytes(), (L/'preflight-optimized.txt').read_bytes()
need(pre_n == pre_o, 'Preflight differs between normal and -O')
preflight = json.loads(pre_n.decode('utf-8'))
need(preflight['counts'] == protocol['data']['trial_week11']['counts'], 'Preflight counts differ from the protocol')
smoke = json.loads((L/'smoke.stdout.txt').read_text(encoding='utf-8')[(L/'smoke.stdout.txt').read_text(encoding='utf-8').index('{'):])
need(smoke['status'] == 'SMOKE_PASS_RANDOM_DATA_NOT_MITDB' and smoke['s2_rho1_rerun_identical'] is True, 'Smoke did not pass')
need(all((L/n).read_bytes() == b'' for n in ('prepare.stderr.txt', 'preflight-normal.stderr.txt', 'preflight-optimized.stderr.txt', 'smoke.stderr.txt')), 'A command wrote to stderr')

receipt = {
    'type': 'M1_ATTACK_V2_CODE_RECEIPT_NOT_LOCKED', 'prepared_by': 'SV3',
    'request': 'SV1 2026-11-13 section 4: attack protocol v2 with the listed bindings and points, attack code (A1, B-naive, Pi), then the lock and the week 11 trial',
    'base_commit': 'f37164199d150e5348af7152b8797291f98bafdd', 'files_committed': False,
    'protocol': {'path': 'ml/configs/mitdb_m1_attack_protocol_v2.json', 'sha256': plan['protocol_sha256'], 'status': protocol['status'],
                 'predecessor': protocol['predecessor'], 'changes_from_v1': len(protocol['changes_from_v1']),
                 'diff': {'path': (R/'diffs/protocol-v1-v2.diff').as_posix(), 'sha256': sha(R/'diffs/protocol-v1-v2.diff')}},
    'plan': {'path': plan_path.as_posix(), 'sha256': sha(plan_path), 'status': plan['status'], 'checkpoints': plan['checkpoints'],
             'data_files': sorted(plan['data_files']), 'DS2_access': plan['DS2_access']},
    'sources_sha256': plan['sources_sha256'],
    'test': {'path': 'ml/scripts/test_attack_m1_v2.py', 'sha256': sha('ml/scripts/test_attack_m1_v2.py'), **tests},
    'preflight': {'command': 'python -B [-O] ml/scripts/attack_m1_v2.py preflight', 'exit_code': 0, 'normal_and_optimized_identical': True,
                  'status': preflight['status'], 'counts': preflight['counts'], 'reads': 'DS1 train/val metadata CSV only'},
    'smoke': {'command': 'python -B ml/scripts/attack_m1_v2.py smoke --output ml/data/smoke-attack-m1-v2-20261113', 'exit_code': 0,
              'start_utc': (L/'smoke-start-utc.txt').read_text(encoding='utf-8').strip(), 'end_utc': (L/'smoke-end-utc.txt').read_text(encoding='utf-8').strip(),
              'status': smoke['status'], 'device_name': smoke['device_name'], 'cudnn_allow_tf32': smoke['cudnn_allow_tf32'],
              'matmul_allow_tf32': smoke['matmul_allow_tf32'], 'capacity_check': smoke['capacity_check'], 'pairs': [r['pair'] for r in smoke['table']],
              's2_rho1_rerun_identical': smoke['s2_rho1_rerun_identical'],
              'note': 'Synthetic metadata and beats with the real rho0/rho1 checkpoints, 3 epochs, 200 resamples; the numbers say nothing about MITDB'},
    'logs_sha256': {p.as_posix(): sha(p) for p in sorted(L.iterdir())},
    'review_note': {'path': 'docs/sv3_m1_attack_v2_review_20261113.md', 'sha256': sha('docs/sv3_m1_attack_v2_review_20261113.md')},
    'scope': {'MITDB_arrays_read': False, 'attack_on_MITDB': False, 'DS2_opened': False, 'locked': False,
              'next': 'SV3 lock and trial authorization binding protocol v2, this plan and the SV1 2026-11-13 review evidence; then run-trial'},
    'status': 'CODE_AND_PROTOCOL_READY_FOR_LOCK_NOT_LOCKED'}
with (R/'receipt.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('receipt', sha(R/'receipt.json'))
