# Writes the NoPeek v2 code receipt once (open 'x'). Hashes files only. Run from the worktree root.
import hashlib, json, subprocess, sys
from pathlib import Path
ROOT = Path.cwd(); D = 'ml/provenance/m1-nopeek-v2-code-20261111'; L = f'{D}/logs'; F = f'{D}/diffs'
SMOKE = 'ml/data/smoke-nopeek-m1-v2-20261111'; PLAN = 'ml/manifests/mitdb-nopeek-m1-v2/plan-manifest.json'
PROTOCOL = 'ml/configs/mitdb_m1_nopeek_protocol_v2.json'; V1 = 'ml/configs/mitdb_m1_nopeek_protocol_v1.json'
EVIDENCE = 'ml/provenance/m1-sv1-evidence-20261111'
sha = lambda p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
read = lambda p: json.loads((ROOT/p).read_text(encoding='utf-8'))
text = lambda p: (ROOT/p).read_text(encoding='utf-8').strip()
git = lambda *a: subprocess.check_output(['git', *a], text=True).strip()
outs = lambda *ps: {p: sha(p) for p in ps}
plan = read(PLAN); protocol = read(PROTOCOL)
published = {'tra_loi_Ky_Anh_PR44_20261109.txt': '2207542f6e3d09603093c69c9e646327082fe6bda1df2fd1fa71587664e15328',
             'sv1_chot_cau_hoi_SV3_20261103.txt': 'be5d1411a61bcd0dadc614dc9255cf524d8c5854a0fa6e984f9cfd504584a343'}
evidence = {f'{EVIDENCE}/{n}': sha(f'{EVIDENCE}/{n}') for n in
            ('tra_loi_Ky_Anh_PR44_20261109.txt', 'tin_Ky_Anh_tuan10_20261110.txt', 'sv1_chot_cau_hoi_SV3_20261103.txt')}
if not all(evidence[f'{EVIDENCE}/{n}'] == h for n, h in published.items()):
    raise SystemExit('SV1 evidence copy differs from the SHA-256 SV1 published')
cmds = [{'argv': ['python', '-B', 'ml/scripts/nopeek_m1_v2.py', 'prepare'], 'exit_code': 0,
         'outputs_sha256': outs(PLAN, f'{L}/prepare.stdout.txt', f'{L}/prepare.stderr.txt')}]
for m, flag in (('normal', []), ('optimized', ['-O'])):
    cmds.append({'argv': ['python', '-B', *flag, 'ml/scripts/nopeek_m1_v2.py', 'preflight'], 'exit_code': 0,
                 'outputs_sha256': outs(f'{L}/preflight-{m}.txt', f'{L}/preflight-{m}.stderr.txt')})
cmds.append({'argv': ['python', '-B', 'ml/scripts/nopeek_m1_v2.py', 'smoke', '--output', SMOKE, '--epochs', '2'], 'exit_code': 0,
             'start_utc': text(f'{L}/smoke-start-utc.txt'), 'end_utc': text(f'{L}/smoke-end-utc.txt'),
             'outputs_sha256': outs(f'{L}/smoke.stdout.txt', f'{L}/smoke.stderr.txt', f'{SMOKE}/smoke-result.json')})
for m in ('default', 'off'):
    cmds.append({'argv': ['python', '-B', f'{D}/tf32_probe.py', m], 'exit_code': 0,
                 'outputs_sha256': outs(f'{L}/tf32-probe-{m}.stdout.txt', f'{L}/tf32-probe-{m}.stderr.txt')})
for m, flag in (('normal', []), ('optimized', ['-O'])):
    cmds.append({'argv': ['python', '-B', *flag, 'ml/scripts/test_nopeek_m1_v2.py'], 'exit_code': 0, 'tests': 17,
                 'outputs_sha256': outs(f'{L}/tests-{m}.txt')})
cmds.append({'argv': ['python', '-B', f'{D}/compare_v1_v2.py'], 'exit_code': 0, 'outputs_sha256': outs(f'{F}/compare-v1-v2.txt')})
for name, a, b in (('protocol', V1, PROTOCOL), ('runner', 'ml/scripts/nopeek_m1_v1.py', 'ml/scripts/nopeek_m1_v2.py'),
                   ('tests', 'ml/scripts/test_nopeek_m1_v1.py', 'ml/scripts/test_nopeek_m1_v2.py')):
    cmds.append({'argv': ['git', 'diff', '--no-index', '--no-color', '--no-ext-diff', a, b], 'exit_code': 1,
                 'exit_code_meaning': 'files differ', 'outputs_sha256': outs(f'{F}/{name}-v1-v2.diff')})
smoke = read(f'{SMOKE}/smoke-result.json'); identity = read(f'{SMOKE}/smoke-s2-lambda5/attempt-identity.json')
r = {'type': 'M1_NOPEEK_V2_CODE_RECEIPT_NOT_LOCKED_NO_MITDB_FIT', 'date': '2026-11-11', 'prepared_by': 'SV3',
     'request': 'Protocol NoPeek v2 (TF32 off, SV1 2026-11-09 item 4(5)) with its diff against v1, runner, regenerated plan and tests',
     'source_head': git('rev-parse', 'HEAD'), 'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
     'protocol': {'path': PROTOCOL, 'sha256': sha(PROTOCOL), 'status': protocol['status'], 'predecessor': {'path': V1, 'sha256': sha(V1)},
                  'changes_from_v1': protocol['changes_from_v1']},
     'plan': {'path': PLAN, 'sha256': sha(PLAN), 'status': plan['status'], 'pilot_runs': sum(x['stage'] == 'pilot' for x in plan['runs']),
              'grid_runs': sum(x['stage'] == 'grid' for x in plan['runs']), 'sources_sha256': plan['sources_sha256'],
              'run_configs': 'Same run ids and order as plan v1; each config differs only in cudnn_allow_tf32 (true -> false) and protocol_sha256'},
     'sv1_evidence': {'files_sha256': evidence, 'published_by_SV1': published,
                      'note': 'Byte-exact copies; tin_Ky_Anh_tuan10_20261110.txt SHA computed by SV3 on receipt, SV1 published none'},
     'scripts_sha256': outs('ml/scripts/nopeek_m1_v2.py', 'ml/scripts/test_nopeek_m1_v2.py', f'{D}/write_receipt.py', f'{D}/tf32_probe.py',
                            f'{D}/compare_v1_v2.py'),
     'review_document': outs('docs/sv3_m1_nopeek_v2_review_20261111.md'),
     'python': sys.version.split()[0], 'commands': cmds,
     'smoke': {**smoke, 'data': 'Random arrays with the real train/val class counts written by the smoke itself; no MITDB file read',
               'device': {k: identity[k] for k in ('device', 'device_name', 'torch', 'cuda', 'cudnn_allow_tf32', 'matmul_allow_tf32',
                                                   'cudnn_conv_fp32_precision', 'matmul_fp32_precision')},
               'epochs_note': 'Smoke runs 2 epochs; the protocol fixes 10'},
     'tf32_probe': {'data': 'Seeded random input through the package A deployment checkpoint; no MITDB file, no training',
                    'default': text(f'{L}/tf32-probe-default.stdout.txt'), 'off': text(f'{L}/tf32-probe-off.stdout.txt')},
     'scope': {'MITDB_fit': False, 'pilot': False, 'grid': False, 'DS2_opened': False, 'lock_written': False,
               'preflight': 'hashes train/val array files only; no model, no fit'},
     'lock_fields_checked_by_runner': ['type M1_NOPEEK_V2_LOCK_AND_TRAIN_AUTHORIZATION', 'allow_training true', 'protocol_sha256',
                                       'plan_manifest_sha256', 'approved_by', 'review_evidence = SHA-256 of review_evidence_path',
                                       'review_evidence_path = protocol source_bindings.sv1_review_20261109.path'],
     'not_verified': ['Any run on MITDB (needs the NoPeek v2 lock, written by SV3)',
                      'Epoch 0 = package A check on real validation through the runner (first step of the first pilot run)',
                      'Run time of the real pilot and grid']}
with (ROOT/D/'receipt.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(r, ensure_ascii=False, indent=2)+'\n')
print('receipt', sha(f'{D}/receipt.json'))
