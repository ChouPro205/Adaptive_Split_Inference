# Grid receipt for NoPeek v2: checks every grid run against the plan and lock, runs the runner's own lambda 0
# report and grid selection, and writes them with per-epoch curves once (open 'x'). No model, no DS2, no Pi.
# Run from the worktree root: python -B <this file>
import csv
import hashlib
import io
import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, 'ml/scripts')
import nopeek_m1_v2 as nop  # noqa: E402

D = Path('ml/provenance/m1-nopeek-v2-run-20261112'); L = D/'logs'
OUT = Path('ml/data/runs/nopeek-m1-v2-20261112')
LOCK = Path('ml/provenance/m1-nopeek-v2-lock-20261112/m1_nopeek_v2_lock_and_train_authorization.json')
PLAN = Path(nop.PLAN_DIR)/'plan-manifest.json'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))


def write_once(path, text):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        f.write(text)


lock, plan = read(LOCK), read(PLAN)
nop.need(sha(LOCK) == 'fe38f3a9f8a2dc4596fb46cb16defd9f917336a4efe38d5806ef7205f0872ad5', 'Lock differs')
nop.need(sha(PLAN) == lock['plan_manifest_sha256'] and sha(nop.ROOT/nop.PROTOCOL) == lock['protocol_sha256'], 'Plan or protocol differs from lock')
nop.need((L/'run-exit-code.txt').read_text(encoding='utf-8').strip() == '0', 'run-pilot-grid did not exit 0')
result = read(OUT/'pilot-grid-result.json')
stage = read(OUT/'grid'/'stage-result.json')
decision = read(OUT/'pilot-decision.json')
nop.need(stage['status'] == 'ALL_RUNS_COMPLETED' and stage['plan_manifest_sha256'] == sha(PLAN) and len(stage['runs']) == 72, 'Grid stage incomplete')
nop.need(result['learning_rate'] == decision['learning_rate'], 'Grid learning rate differs from the pilot decision')
A = nop.a_confusion()
threshold = Fraction(19, 20)*nop.macro_f1_exact(A)

runs, rows = [], []
for r in (x for x in plan['runs'] if x['stage'] == 'grid'):
    config = read(PLAN.parent/r['config'])
    rd = OUT/'grid'/r['run_id']
    history, summary, identity = read(rd/'history.json'), read(rd/'summary.json'), read(rd/'attempt-identity.json')
    nop.need(summary['history_sha256'] == sha(rd/'history.json') and summary['config_sha256'] == r['sha256'], f"{r['run_id']} binding differs")
    nop.need(all(sha(rd/n) == h for n, h in summary['checkpoints_sha256'].items()), f"{r['run_id']} checkpoint hash differs")
    nop.need(identity['lr'] == decision['learning_rate'] and identity['cudnn_allow_tf32'] is False and identity['matmul_allow_tf32'] is False,
             f"{r['run_id']} learning rate or TF32 differs")
    for h in history:
        v = h['validation']
        m = nop.macro_f1_exact(v['confusion_matrix'])
        rows.append({'run_id': r['run_id'], 's': config['s'], 'lambda': config['lambda'], 'seed': config['seed'], 'epoch': h['epoch'],
                     'macro_f1_K': float(m), 'passes_utility': m >= threshold, 'collapsed': nop.collapsed(v['confusion_matrix']),
                     'accuracy': v['accuracy'], 'recall_S': v['recall'][1], 'recall_V': v['recall'][2], 'subset_Rn': v['subset_Rn'],
                     'train_CE_mean': h.get('train_CE_mean'), 'train_batch_Rn_mean': h.get('train_batch_Rn_mean')})
    runs.append({'run_id': r['run_id'], 'config_sha256': r['sha256'], 'epoch0_confusion_equals_A': history[0]['validation']['confusion_matrix'] == A,
                 'reload_confusion_exact': summary['reload_confusion_exact'], 'epochs': summary['epochs'],
                 'history_sha256': summary['history_sha256'], 'checkpoints_sha256': summary['checkpoints_sha256']})
nop.need(len(runs) == 72 and all(x['epoch0_confusion_equals_A'] and x['reload_confusion_exact'] and x['epochs'] == 10 for x in runs),
         'Grid run count, epoch 0 or reload check differs')

plan['_dir'] = str(PLAN.parent)
selection = nop.choose_grid(OUT/'grid', plan, A)  # Raises if lambda 0 states differ across s.
selection['plan_manifest_sha256'] = sha(PLAN)
lambda0 = nop.lambda0_report(OUT/'grid', plan, A)
lambda0['plan_manifest_sha256'] = sha(PLAN)
write_once(D/'grid-selection.json', json.dumps(selection, ensure_ascii=False, indent=2) + '\n')
write_once(D/'lambda0-report.json', json.dumps(lambda0, ensure_ascii=False, indent=2) + '\n')
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n')
w.writeheader()
w.writerows(rows)
write_once(D/'grid-curves.csv', buf.getvalue())
for name in ('pilot-grid-result.json',):
    with (OUT/name).open('rb') as src, (D/name).open('xb') as dst:
        shutil.copyfileobj(src, dst)
with (OUT/'grid'/'stage-result.json').open('rb') as src, (D/'grid-stage-result.json').open('xb') as dst:
    shutil.copyfileobj(src, dst)
receipt = {
    'type': 'M1_NOPEEK_V2_GRID_RECEIPT_SELECTION_NOT_LOCKED', 'prepared_by': 'SV3',
    'source_head': (L/'source-head.txt').read_text(encoding='utf-8').strip(),
    'run_start_utc': (L/'run-start-utc.txt').read_text(encoding='utf-8').strip(), 'run_end_utc': (L/'run-end-utc.txt').read_text(encoding='utf-8').strip(),
    'bindings': {'lock': {'path': LOCK.as_posix(), 'sha256': sha(LOCK)}, 'protocol_sha256': lock['protocol_sha256'],
                 'plan_manifest_sha256': lock['plan_manifest_sha256'], 'output_dir': OUT.as_posix(),
                 'pilot_receipt_sha256': sha(D/'pilot-receipt.json')},
    'learning_rate': decision['learning_rate'],
    'utility_threshold': {'exact': str(threshold), 'float': float(threshold)},
    'checks': {'runs': len(runs), 'epoch0_equals_A_all': True, 'reload_confusion_exact_all': True, 'checkpoint_hashes_match_summaries': True,
               'tf32_off_all': True, 'lambda0_identical_across_s': selection['lambda0_identical_across_s']},
    'outputs_sha256': {p.as_posix(): sha(p) for p in (D/'grid-selection.json', D/'lambda0-report.json', D/'grid-curves.csv',
                                                       D/'pilot-grid-result.json', D/'grid-stage-result.json')},
    'selection_status': selection['status'],
    'per_s': {s: {'lambda': v['lambda'], 'deployment_seed': v['deployment_seed']} for s, v in selection['per_s'].items()},
    'runs': runs,
    'scope': {'DS2_opened': False, 'Pi_or_attack': False,
              'next': 'Send SV1 the lambda 0 curve with this receipt before any Pi (protocol reporting_before_privacy)'}}
write_once(D/'grid-receipt.json', json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('grid-receipt', sha(D/'grid-receipt.json'))
print(f"threshold={float(threshold):.6f}  lr={decision['learning_rate']:g}  lambda0 identical across s: {selection['lambda0_identical_across_s']}")
for seed, curve in lambda0['lambda0_by_seed'].items():
    print(f"  lambda0 seed {seed}: " + ' '.join(f"{c['macro_f1']:.4f}{'' if c['passes'] else '*'}" for c in curve))
for s, v in selection['per_s'].items():
    print(f"  {s}: lambda={v['lambda']:g} deployment_seed={v['deployment_seed']}")
    for t in v['table']:
        print(f"    lambda={t['lambda']:<4g} eligible={t['eligible']!s:<5} mean_Rn={t['mean_Rn']:.4f} sd={t['sd_Rn_ddof1']:.4f} "
              f"mean_F1={t['mean_macro_f1']:.4f} flags={[x['flag'] for x in t['seeds']]} epochs={[x['epoch'] for x in t['seeds']]} "
              f"collapsed={[x['collapsed'] for x in t['seeds']]}")
