# Writes the attack v3 part c (DS1) receipt once (open 'x') after noise_m1_v3.py run: run logs, source head = the
# parts a, b, d receipt commit with no tracked change, the authorization used, the run manifest (fresh noise, written
# before the first privacy fit), the part a files c read against the a, b, d receipt, every output file hashed, byte
# copies of the JSON outputs, and the epochs actually run by every adaptive variant (SV1 2026-11-27 section 2).
# Hashes and copies local files only; no model, no data. Run from the worktree root: python -B <this file>
import hashlib
import json
import shutil
from pathlib import Path

R = Path('ml/provenance/m1-attack-v3-c-run-20261127'); L = R/'logs'
OUT = Path('ml/data/runs/attack-m1-v3-c-20261127')
PART_A = Path('ml/data/runs/attack-m1-v3-abd-20261127')
ABD_RECEIPT = Path('ml/provenance/m1-attack-v3-abd-run-20261127/receipt.json')
AUTH = Path('ml/provenance/m1-attack-v3-run-auth-20261127/m1_attack_v3_run_authorization.json')
PROTOCOL = Path('ml/configs/mitdb_m1_attack_protocol_v3_r5.json')
SOURCE_COMMIT = '7dba869a670d173a9f0309e71a7f921721ba42c8'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))  # noqa: E731


def need(condition, message):
    if not condition:
        raise SystemExit(f'CHECK FAILED: {message}')


need((L/'run-exit-code.txt').read_text(encoding='utf-8').strip() == '0', 'run did not exit 0')
need((L/'source-head.txt').read_text(encoding='utf-8').strip() == SOURCE_COMMIT, 'Run source head is not the a, b, d receipt commit')
status = (L/'source-status.txt').read_text(encoding='utf-8').splitlines()
need(all(line.startswith('?? ') for line in status), 'Tracked files differed from the source commit at run start')
m, res = read(OUT/'run-manifest.json'), read(OUT/'part-c-result.json')
need(m['authorization_sha256'] == sha(AUTH) and m['protocol_sha256'] == sha(PROTOCOL) and 'c' in read(AUTH)['allow_parts'], 'Run bindings differ')
need(m['noise_plan'] == {'kind': 'fresh'} and read(AUTH)['noise_plan'] == 'fresh' and m['written'] == 'before the first privacy fit', 'Noise plan differs')
need(m['sigma_sha256'] == sha(OUT/'sigma.json') and m['utility_sha256'] == sha(OUT/'utility.json'), 'Sigma or utility file differs from the manifest')
need(m['cudnn_allow_tf32'] is False and m['matmul_allow_tf32'] is False and m['deterministic_algorithms'] is True, 'TF32 or determinism differs')
abd = read(ABD_RECEIPT)['outputs_sha256']
need(m['part_a_files_sha256'] and all(abd[(PART_A/f).as_posix()] == h == sha(PART_A/f) for f, h in m['part_a_files_sha256'].items()),
     'Part a files differ from the a, b, d receipt')
need(res['status'] == 'COMPLETED_DS1_REPORT_FOR_SV1' and res['DS2_opened'] is False, 'Result status or DS2 state differs')
need(len(res['points']) == len(m['points']) == len(res['epochs_run']), 'Point count differs')
files = sorted(f for f in OUT.iterdir() if f.is_file())
copies = R/'results'
copies.mkdir()
for f in files:
    if f.suffix == '.json':
        shutil.copyfile(f, copies/f.name)
        need(sha(copies/f.name) == sha(f), f'Copy differs: {f.name}')
adaptive = {pt: {k: v for k, v in d.items() if 'adaptive' in k} for pt, d in res['epochs_run'].items()}
gpu_cpu = {}
for p in m['points']:
    key = next(r for r in res['points'] if r['config'] == p['config'] and r['alpha'] == p['alpha_t'])
    pj = read(OUT/f"point-{p['config']}-alpha{round(p['alpha_t'] * 1e6)}.json")
    gpu_cpu[f"{p['config']}-{p['target']}"] = pj['gpu_cpu_epoch1']
    need(pj['noise_plan'] == {'kind': 'fresh'} and pj['Pi'] == key['Pi'], f"Point file differs: {p['config']} {p['target']}")
stderr = (L/'run.stderr.txt').read_bytes()
receipt = {
    'type': 'M1_ATTACK_V3_C_DS1_RECEIPT_REPORT_ONLY', 'prepared_by': 'SV3',
    'authorization': {'path': AUTH.as_posix(), 'sha256': sha(AUTH), 'commit': 'e55e82b1db4e96b2f725d1e56273baa798f0135e'},
    'run': {'command': (f'python -B ml/scripts/noise_m1_v3.py run --output {OUT.as_posix()} --authorization {AUTH.as_posix()} '
                        f'--part-a-dir {PART_A.as_posix()}'),
            'source_head': SOURCE_COMMIT, 'tracked_files_clean': True, 'untracked_at_start': [line[3:] for line in status],
            'start_utc': (L/'run-start-utc.txt').read_text(encoding='utf-8').strip(), 'end_utc': (L/'run-end-utc.txt').read_text(encoding='utf-8').strip(),
            'exit_code': 0, 'stderr_bytes': len(stderr), 'device_name': m['device_name'], 'torch': m['torch'], 'cuda': m['cuda'],
            'cudnn_allow_tf32': False, 'matmul_allow_tf32': False, 'deterministic_algorithms': True},
    'bindings': {'protocol_sha256': m['protocol_sha256'], 'part_a_receipt_sha256': sha(ABD_RECEIPT), 'sigma_sha256': m['sigma_sha256'],
                 'utility_sha256': m['utility_sha256']},
    'noise_plan': m['noise_plan'], 'run_manifest_written': m['written'],
    'points': m['points'], 'table': res['points'], 'selected_on_DS1': res['selected_on_DS1'],
    'reading_declared_before_run': res['reading_declared_before_run'],
    'epochs_run_adaptive': {pt: {'min': min(d.values()), 'max': max(d.values()), 'below_20': sum(v < 20 for v in d.values()), 'variants': len(d)}
                            for pt, d in adaptive.items()},
    'epochs_run': res['epochs_run'],
    'gpu_cpu_epoch1': gpu_cpu,
    'outputs_sha256': {f.as_posix(): sha(f) for f in files},
    'tracked_copies': {(copies/f.name).as_posix(): sha(copies/f.name) for f in files if f.suffix == '.json'},
    'logs_sha256': {f.as_posix(): sha(f) for f in sorted(L.iterdir())},
    'scope': {'data': 'DS1 (N = 22) only', 'DS2_opened': False, 'part': 'c',
              'use': 'Development numbers and early warning only (SV1 2026-11-27 section 3); alpha is selected on the utility part only. '
                     'epochs_run and gpu_cpu_epoch1 are reported, not gates'},
    'status': 'C_DS1_RECEIPT_REPORT_ONLY'}
with (R/'receipt.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('receipt', sha(R/'receipt.json'))
