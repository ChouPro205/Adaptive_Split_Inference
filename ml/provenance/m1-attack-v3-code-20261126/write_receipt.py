# Writes receipt.json and SHA256SUMS.txt of the attack v3 r5 code delivery from the logs, the plan and the smoke and
# timing outputs (ignored ml/data). Reads no MITDB array. Run from the worktree root after the logged commands.
import hashlib
import json
import subprocess
from pathlib import Path

D = Path('ml/provenance/m1-attack-v3-code-20261126')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))  # noqa: E731
plan_path = 'ml/manifests/mitdb-attack-m1-v3/plan-manifest.json'
plan = read(plan_path)
codes = dict(line.rsplit(' ', 1) for line in (D/'logs/exit-codes.txt').read_text(encoding='utf-8').splitlines())
smoke_abd = read('ml/data/smoke-attack-m1-v3-abd-20261126/smoke-result.json')
smoke_c = read('ml/data/smoke-attack-m1-v3-c-20261126/smoke-result.json')
timing = read('ml/data/timing-attack-m1-v3-c-20261126/timing.json')
tests = {m: (D/f'logs/tests-{m}.txt').read_text(encoding='utf-8').strip().splitlines()[-3:] for m in ('normal', 'optimized')}
receipt = {
    'type': 'M1_ATTACK_V3_CODE_RECEIPT_NOT_AUTHORIZED',
    'prepared_by': 'SV3',
    'request': 'SV1 2026-11-26 (confirmation of r5) section 3: lock r5, then code, tests and random-data smoke by 2026-11-29',
    'base_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip(),
    'protocol': {'path': 'ml/configs/mitdb_m1_attack_protocol_v3_r5.json', 'sha256': plan['protocol_sha256'],
                 'lock': {'path': 'ml/provenance/m1-attack-v3-r5-lock-20261126/m1_attack_v3_r5_protocol_lock.json', 'sha256': plan['protocol_lock_sha256']}},
    'plan': {'path': plan_path, 'sha256': sha(plan_path), 'status': plan['status'], 'sources_sha256': plan['sources_sha256'],
             'v2_trial_outputs_checked': len(plan['v2_trial_outputs_sha256']), 'part_d_pair_keys': plan['part_d_pair_keys'],
             'part_c_pair_key_offset': plan['part_c_pair_key_offset']},
    'exit_codes': codes,
    'tests': tests,
    'smoke_parts_a_b_d': {k: smoke_abd[k] for k in ('status', 'device', 'epochs', 's0c_golden', 's0c_reference_synthetic', 'composite_rerun_identical',
                                                    'k_beat_rerun_identical')},
    'smoke_part_c': {k: smoke_c[k] for k in ('status', 'device', 'epochs', 'C0c_point_rerun_identical', 'fallback_plan_runs')}
                    | {'gpu_cpu_epoch1': {c: r['gpu_cpu_epoch1'] for c, r in smoke_c['points'].items()}},
    'timing_part_c_random_arrays': timing,
    'noise_plan_proposal': ('fresh noise every epoch (no fallback): on random arrays of the real sizes the extrapolated upper bound of utility '
                            'search plus training at 50 epochs is the value in timing_part_c_random_arrays.extrapolation; the fallback of '
                            'noise_generator.fallback is not needed. Recorded in the run manifest before the first fit; DS2 follows the same plan'),
    'run_manifest_requirements_implemented': {
        'epochs_run_per_variant': 'noise_m1_v3.run_point writes epochs_run of every variant and seed; part-c-result.json collects them',
        'gpu_cpu_epoch1': 'noise_m1_v3.gpu_cpu_check at epoch 1 for every composite target (max |GPU - CPU| of u_s\', fraction of values that differ); report only',
        'DS2_follows_DS1_noise_plan': 'run-manifest.json records the plan; DS2 streams (part_index 4-7) are declared and refused in this code'},
    'numbers_meaning': 'Smoke and timing numbers come from synthetic beats; they say nothing about MITDB and choose no parameter',
    'not_covered': ['Any MITDB run: needs the run authorization (type M1_ATTACK_V3_RUN_AUTHORIZATION) binding this plan',
                    'DS2 quality-round script (S0c, A FP32 macro-F1 on DS2): to SV1 before 2026-12-07',
                    'k-beat tables and test predictions are not in the timing extrapolation'],
    'files_committed': False,
}
(D/'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
files = sorted(p for p in D.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
(D/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)} *{p.relative_to(D).as_posix()}\n' for p in files), encoding='utf-8', newline='\n')
print('receipt', sha(D/'receipt.json'))
