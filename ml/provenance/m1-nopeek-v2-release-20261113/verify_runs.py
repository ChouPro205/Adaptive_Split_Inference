# Hash-only check of the NoPeek v2 run directory published on the GitHub Release (SV1 2026-11-13, section 4): 9 pilot and
# 72 grid runs, checkpoints of epochs 0-10 (891 files) with their per-epoch metrics, history, summary and attempt identity.
# Standard library only, so it runs without torch. The tracked files (protocol, plan manifest, run configs, pilot and grid
# receipts, grid selection) are read from the current directory, which must be the root of a checkout at the tag commit;
# the run files are read from <root>/ml/data/runs/nopeek-m1-v2-20261112 (default root: the current directory, i.e. the zip
# extracted at the checkout root). If <root>/PACKAGE_SHA256SUMS.txt exists it must equal the list built here.
# Checks: tracked hashes; exact inventory (no missing or extra file); every checkpoint, history and config hash against the
# plan manifest and the receipts; TF32 off and DS2 not opened in every run; top-level files equal the tracked copies.
# Prints the checkpoint roles used by the attack protocol (rho1, lambda 0 controls, other seeds of the selected lambda).
# Never opens arrays or DS2. Usage: python -B ml/provenance/m1-nopeek-v2-release-20261113/verify_runs.py [--root DIR]
import argparse
import hashlib
import json
from pathlib import Path

RUNS = 'ml/data/runs/nopeek-m1-v2-20261112'
PROV = Path('ml/provenance/m1-nopeek-v2-run-20261112')
PLAN = Path('ml/manifests/mitdb-nopeek-m1-v2/plan-manifest.json')
SUMS_NAME = 'PACKAGE_SHA256SUMS.txt'
TRACKED_SHA256 = {
    'ml/configs/mitdb_m1_nopeek_protocol_v2.json': '83cce64defefa979abcf8c31cc27daf9ae81604caae911acf0901cba3783cf35',
    'ml/provenance/m1-nopeek-v2-lock-20261112/m1_nopeek_v2_lock_and_train_authorization.json': 'fe38f3a9f8a2dc4596fb46cb16defd9f917336a4efe38d5806ef7205f0872ad5',
    PLAN.as_posix(): 'e2e4e85856ed1d1861a771388d40de24c27c1ff6ffbfac2138ea275f76b650f9',
    (PROV/'pilot-receipt.json').as_posix(): '6b507258466aa1a21fba12365b8ba1e52512b4b820256586639e4fbdd809dc5b',
    (PROV/'grid-receipt.json').as_posix(): '67c938817f8f6eea0ab493d34e66bf6d04df3baec05bef043a4b6cb766dc7d84',
    (PROV/'grid-selection.json').as_posix(): '9f7ab9bf008e066f6d921fa231a7d4b72ae8d4b75cb82d11c6f31b651ea8e48e',
    (PROV/'pilot-decision.json').as_posix(): '6d3130b1fc123d7011430fd90dd019a5e7a3b4f479b81bac8621adb71215012e',
    (PROV/'pilot-grid-result.json').as_posix(): '2a8cf8845864c6f567bf6223bb42e45c60d02a26b63692016ec3472263f85e25',
    (PROV/'grid-stage-result.json').as_posix(): 'ee59fc0f5eae5d78ecc0ed19aaab4022235be3c6f9e03820fd74ddde1c71945a',
}
# Top-level run files that are byte copies of tracked files.
TOP_COPIES = {'pilot-decision.json': PROV/'pilot-decision.json', 'pilot-grid-result.json': PROV/'pilot-grid-result.json',
              'grid/stage-result.json': PROV/'grid-stage-result.json'}
EPOCHS = range(11)
RUN_FILES = (['attempt-identity.json', 'history.json', 'summary.json'] + [f'checkpoint-epoch-{e:03d}.pt' for e in EPOCHS]
             + [f'epoch-{e:03d}.json' for e in EPOCHS if e >= 1])


def need(condition, message):
    if not condition:
        raise SystemExit(f'CHECK FAILED: {message}')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def lam(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else repr(value)


def expected_files(plan):
    """Relative paths (inside the run directory) the published tree must hold, sorted."""
    files = ['pilot-decision.json', 'pilot-grid-result.json', 'pilot/stage-result.json', 'grid/stage-result.json']
    files += [f"{r['stage']}/{r['run_id']}/{name}" for r in plan['runs'] for name in RUN_FILES]
    return sorted(files)


def sums_text(entries):
    """sha256sum -c format, paths relative to the checkout root, LF line ends."""
    return ''.join(f'{digest}  {RUNS}/{rel}\n' for rel, digest in entries)


def check(root='.'):
    root = Path(root)
    runs_dir = root/RUNS
    out = {'tracked_sha256_match': True}
    for path, digest in TRACKED_SHA256.items():
        need(Path(path).is_file() and sha(path) == digest, f'Tracked file differs or is missing: {path}')

    plan = read(PLAN)
    stages = {'pilot': [r for r in plan['runs'] if r['stage'] == 'pilot'], 'grid': [r for r in plan['runs'] if r['stage'] == 'grid']}
    need(len(plan['runs']) == 81 and len(stages['pilot']) == 9 and len(stages['grid']) == 72, 'Plan manifest does not list 9 pilot + 72 grid runs')
    for r in plan['runs']:
        need(sha(PLAN.parent/r['config']) == r['sha256'], f"Run config differs from the plan manifest: {r['config']}")
    receipts = {'pilot': read(PROV/'pilot-receipt.json'), 'grid': read(PROV/'grid-receipt.json')}
    by_run = {}
    for stage, receipt in receipts.items():
        need(sorted(x['run_id'] for x in receipt['runs']) == sorted(r['run_id'] for r in stages[stage]),
             f'{stage} receipt runs differ from the plan manifest')
        need(receipt['bindings']['output_dir'] == RUNS, f'{stage} receipt output_dir differs')
        by_run.update({x['run_id']: x for x in receipt['runs']})

    # Exact inventory: nothing missing, nothing extra.
    need(runs_dir.is_dir(), f'Run directory not found: {runs_dir}')
    want = expected_files(plan)
    have = sorted(p.relative_to(runs_dir).as_posix() for p in runs_dir.rglob('*') if p.is_file())
    need(have == want, f'Inventory differs: missing {sorted(set(want) - set(have))[:5]}, extra {sorted(set(have) - set(want))[:5]}')
    entries = [(rel, sha(runs_dir/rel)) for rel in want]
    digests = dict(entries)

    # Per run: config, checkpoints, history, identity.
    for r in plan['runs']:
        rid, base = r['run_id'], f"{r['stage']}/{r['run_id']}"
        rec, summary, ident = by_run[rid], read(runs_dir/base/'summary.json'), read(runs_dir/base/'attempt-identity.json')
        need(summary['run_id'] == ident['run_id'] == rid, f'{rid}: run_id differs inside the run')
        need(summary['config_sha256'] == ident['config_sha256'] == rec['config_sha256'] == r['sha256'], f'{rid}: config hash differs')
        need(summary['status'] == 'COMPLETED_NOT_SELECTION' and summary['epochs'] == rec['epochs'] == 10, f'{rid}: status or epoch count differs')
        need(summary['reload_confusion_exact'] is True and rec['reload_confusion_exact'] is True, f'{rid}: reload check not recorded as exact')
        need(rec['epoch0_confusion_equals_A'] is True, f'{rid}: epoch 0 not recorded as equal to A')
        names = [f'checkpoint-epoch-{e:03d}.pt' for e in EPOCHS]
        need(sorted(rec['checkpoints_sha256']) == sorted(summary['checkpoints_sha256']) == names, f'{rid}: checkpoint list differs')
        for name in names:
            need(digests[f'{base}/{name}'] == rec['checkpoints_sha256'][name] == summary['checkpoints_sha256'][name], f'{rid}: {name} hash differs')
        need(digests[f'{base}/history.json'] == rec['history_sha256'] == summary['history_sha256'], f'{rid}: history hash differs')
        need(ident['cudnn_allow_tf32'] is False and ident['matmul_allow_tf32'] is False, f'{rid}: TF32 not off')
        need(ident['DS2_arrays_opened'] is False and summary['DS2_evaluated'] is False, f'{rid}: DS2 opened')

    # Top-level files.
    for rel, tracked in TOP_COPIES.items():
        need(digests[rel] == sha(tracked), f'{rel} differs from {tracked.as_posix()}')
    for stage in ('pilot', 'grid'):
        result = read(runs_dir/stage/'stage-result.json')
        need(result['stage'] == stage and result['status'] == 'ALL_RUNS_COMPLETED' and result['plan_manifest_sha256'] == TRACKED_SHA256[PLAN.as_posix()]
             and sorted(result['runs']) == sorted(r['run_id'] for r in stages[stage]), f'{stage}/stage-result.json differs from the plan')

    # Checkpoint roles from the grid selection (each seed at its own selected epoch).
    selection, roles = read(PROV/'grid-selection.json'), []
    for s, v in selection['per_s'].items():
        row = next(t for t in v['table'] if float(t['lambda']) == float(v['lambda']))
        need(row['eligible'] is True and len(row['seeds']) == 3, f'{s}: selected lambda not eligible with 3 seeds')
        for seed in row['seeds']:
            epoch = seed['epoch']
            name = f'checkpoint-epoch-{epoch:03d}.pt'
            picked = f"grid-{s}-lambda{lam(v['lambda'])}-seed{seed['seed']}"
            control = f"grid-{s}-lambda0-seed{seed['seed']}"
            deploy = seed['seed'] == v['deployment_seed']
            other = 'other seed of the selected lambda' + (' (point 3c candidate: s2 and s_m in {s4, s5})' if s in ('s2', 's4', 's5') else ' (s8 offline only)')
            roles.append({'s': s, 'role': 'rho1 (deployment seed)' if deploy else other,
                          'lambda': v['lambda'], 'seed': seed['seed'], 'epoch': epoch,
                          'path': f'{RUNS}/grid/{picked}/{name}', 'sha256': digests[f'grid/{picked}/{name}']})
            if deploy:
                roles.append({'s': s, 'role': 'lambda 0 control, same seed and epoch (point 3a)', 'lambda': 0, 'seed': seed['seed'],
                              'epoch': epoch, 'path': f'{RUNS}/grid/{control}/{name}', 'sha256': digests[f'grid/{control}/{name}']})
    need(sum(r['role'].startswith('rho1') for r in roles) == 4, 'Expected 4 rho1 checkpoints')

    text = sums_text(entries)
    if (root/SUMS_NAME).exists():
        need((root/SUMS_NAME).read_bytes() == text.encode('ascii'), f'{SUMS_NAME} differs from the files')
        out['package_sums_file_checked'] = True
    out.update({
        'run_dir': RUNS, 'runs': {'pilot': 9, 'grid': 72}, 'files': len(entries),
        'checkpoints': sum(rel.endswith('.pt') for rel, _ in entries), 'bytes': sum((runs_dir/rel).stat().st_size for rel, _ in entries),
        'package_sums_sha256': hashlib.sha256(text.encode('ascii')).hexdigest(),
        'checks': ['inventory exact', 'run configs = plan manifest', 'checkpoint and history hashes = pilot/grid receipts = summaries',
                   'TF32 off and DS2 not opened in every run', 'top-level files = tracked copies', 'stage results = plan'],
        'roles': roles, 'scope': {'arrays_read': False, 'DS2_opened': False, 'model_quality_evidence': False},
        'status': 'NOPEEK_V2_RUNS_HASH_CHECK_PASS'})
    return out, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='Directory that holds ml/data/runs/nopeek-m1-v2-20261112 (default: current directory)')
    out, _ = check(parser.parse_args().root)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
