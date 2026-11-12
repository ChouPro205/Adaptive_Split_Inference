# Pilot receipt for NoPeek v2 (protocol pilot.after_pilot: sent to SV1 when the grid starts). Reads the pilot
# outputs under ignored ml/data, recomputes the pilot decision with the runner's own rule, copies the decision
# byte-exact into provenance and writes the receipt and per-epoch curves once (open 'x'). No model, no DS2.
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

lock, plan = read(LOCK), read(PLAN)
nop.need(sha(LOCK) == 'fe38f3a9f8a2dc4596fb46cb16defd9f917336a4efe38d5806ef7205f0872ad5', 'Lock differs')
nop.need(sha(PLAN) == lock['plan_manifest_sha256'] and sha(nop.ROOT/nop.PROTOCOL) == lock['protocol_sha256'], 'Plan or protocol differs from lock')
A = nop.a_confusion()
threshold = Fraction(19, 20)*nop.macro_f1_exact(A)
decision_path = OUT/'pilot-decision.json'
written = read(decision_path)
plan['_dir'] = str(PLAN.parent)
recomputed = nop.choose_pilot(OUT/'pilot', plan, A)
recomputed['plan_manifest_sha256'] = sha(PLAN)
nop.need(recomputed == written, 'Recomputed pilot decision differs from the written one')

runs, rows = [], []
for r in (x for x in plan['runs'] if x['stage'] == 'pilot'):
    config = read(PLAN.parent/r['config'])
    rd = OUT/'pilot'/r['run_id']
    history, summary, identity = read(rd/'history.json'), read(rd/'summary.json'), read(rd/'attempt-identity.json')
    nop.need(summary['history_sha256'] == sha(rd/'history.json') and summary['config_sha256'] == r['sha256'], f"{r['run_id']} binding differs")
    nop.need(all(sha(rd/n) == h for n, h in summary['checkpoints_sha256'].items()), f"{r['run_id']} checkpoint hash differs")
    curve = []
    for h in history:
        v = h['validation']
        m = nop.macro_f1_exact(v['confusion_matrix'])
        row = {'run_id': r['run_id'], 'lr': config['lr'], 's': config['s'], 'lambda': config['lambda'], 'epoch': h['epoch'],
               'macro_f1_K': float(m), 'passes_utility': m >= threshold, 'collapsed': nop.collapsed(v['confusion_matrix']),
               'accuracy': v['accuracy'], 'recall_S': v['recall'][1], 'recall_V': v['recall'][2], 'subset_Rn': v['subset_Rn'],
               'train_CE_mean': h.get('train_CE_mean'), 'train_batch_Rn_mean': h.get('train_batch_Rn_mean')}
        curve.append(row)
        rows.append(row)
    runs.append({'run_id': r['run_id'], 'config_sha256': r['sha256'], 'lr': config['lr'], 's': config['s'], 'lambda': config['lambda'],
                 'epoch0_confusion_equals_A': history[0]['validation']['confusion_matrix'] == A,
                 'reload_confusion_exact': summary['reload_confusion_exact'], 'epochs': summary['epochs'],
                 'history_sha256': summary['history_sha256'], 'checkpoints_sha256': summary['checkpoints_sha256'],
                 'environment': {k: identity[k] for k in ('device', 'device_name', 'torch', 'cuda', 'cudnn_allow_tf32', 'matmul_allow_tf32',
                                                         'cudnn_conv_fp32_precision', 'matmul_fp32_precision', 'DS2_arrays_opened')}})
nop.need(len(runs) == 9 and all(x['epoch0_confusion_equals_A'] and x['reload_confusion_exact'] and x['epochs'] == 10 for x in runs),
         'Pilot run count, epoch 0 or reload check differs')
nop.need(all(x['environment']['cudnn_allow_tf32'] is False and x['environment']['matmul_allow_tf32'] is False for x in runs), 'TF32 was on')

decision_copy = D/'pilot-decision.json'
with decision_path.open('rb') as src, decision_copy.open('xb') as dst:
    shutil.copyfileobj(src, dst)
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n')
w.writeheader()
w.writerows(rows)
with (D/'pilot-curves.csv').open('x', encoding='utf-8', newline='') as f:
    f.write(buf.getvalue())
receipt = {
    'type': 'M1_NOPEEK_V2_PILOT_RECEIPT', 'prepared_by': 'SV3', 'source_head': (L/'source-head.txt').read_text(encoding='utf-8').strip(),
    'run_start_utc': (L/'run-start-utc.txt').read_text(encoding='utf-8').strip(),
    'bindings': {'lock': {'path': LOCK.as_posix(), 'sha256': sha(LOCK)}, 'protocol_sha256': lock['protocol_sha256'],
                 'plan_manifest_sha256': lock['plan_manifest_sha256'], 'output_dir': OUT.as_posix()},
    'utility_threshold': {'exact': str(threshold), 'float': float(threshold), 'A_macro_f1_K': float(nop.macro_f1_exact(A))},
    'pilot_decision': {**written, 'path_in_output': decision_path.as_posix(), 'copy': decision_copy.as_posix(),
                       'sha256': sha(decision_path), 'recomputed_with_runner_rule_equal': True},
    'curves': {'path': (D/'pilot-curves.csv').as_posix(), 'sha256': sha(D/'pilot-curves.csv'), 'rows': len(rows)},
    'runs': runs,
    'grid': 'Started at once by run-pilot-grid with the chosen learning rate (protocol pilot.after_pilot)' if written['status'] == 'PILOT_LR_CHOSEN'
            else 'Not started: no safe learning rate (protocol pilot.no_safe_candidate); SV1 decides',
    'scope': {'DS2_opened': False, 'Pi_or_attack': False, 'lambda_selection_input': False}}
with (D/'pilot-receipt.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('pilot-receipt', sha(D/'pilot-receipt.json'))
print(f"decision: {written['status']} lr={written.get('learning_rate')}  threshold={float(threshold):.6f}")
for c in written['candidates']:
    print(f"  lr={c['learning_rate']:g} safe={c['safe']} lambda0_epochs_passing={c['lambda0_epochs_passing']}/10 "
          f"lambda5_min_Rn s2={c['lambda5_min_Rn']['s2']:.4f} s8={c['lambda5_min_Rn']['s8']:.4f} score={c['score']:.4f}")
