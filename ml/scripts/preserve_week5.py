"""Read-only raw SHA-256 inventory of frozen assets and existing user work."""
import argparse
import hashlib
import gzip
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def snapshot(root, exclude):
    prefixes = ['ml/artifacts', 'ml/data', 'ml/results', 'ml/provenance',
                'ml/configs', 'ml/manifests', 'device/artifacts', 'device/generated',
                'results', 'week1_handoff_stage', 'exports']
    files = set(p for p in root.iterdir() if p.is_file())
    for prefix in prefixes:
        for directory, dirs, names in os.walk(root / prefix, followlinks=False):
            dirs[:] = [d for d in dirs if d not in {'.git', '.venv', '__pycache__', '.cache'}
                       and (Path(directory) / d).resolve() != exclude]
            files.update(Path(directory) / n for n in names)
    git = ['git', '-c', f'safe.directory={root.as_posix()}']
    status = subprocess.check_output([*git, 'status', '--porcelain=v1', '-uall'], cwd=root, text=True)
    # Include all pre-existing changes, even those outside the asset directories.
    for line in status.splitlines():
        name = line[3:].strip('"')
        p = root / name
        if p.is_file() and not p.resolve().is_relative_to(exclude):
            files.add(p)
    records = {p.relative_to(root).as_posix(): {'size_bytes': p.stat().st_size, 'sha256': digest(p)}
               for p in sorted(files) if not p.resolve().is_relative_to(exclude)
               and '__pycache__' not in p.parts and '.git' not in p.parts}
    return {'root': str(root), 'excluded_new_checkout': str(exclude), 'git_status_before': status,
            'source_commit': subprocess.check_output([*git, 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'file_count': len(records), 'files': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--exclude', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--before', type=Path)
    args = parser.parse_args()
    if args.before:
        raw = gzip.decompress(args.before.read_bytes()) if args.before.suffix == '.gz' else args.before.read_bytes()
        before = json.loads(raw)
        after = {}
        for name in before['files']:
            p = args.root / name
            after[name] = {'size_bytes': p.stat().st_size, 'sha256': digest(p)} if p.is_file() else None
        changed = [n for n in after if after[n] != before['files'][n]]
        result = {'status': 'FAIL' if changed else 'PASS', 'file_count': len(after), 'changed': changed,
                  'before_sha256': hashlib.sha256(raw).hexdigest(), 'before_storage_sha256': digest(args.before),
                  'after_inventory_sha256': hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
                  'before_inventory_sha256': hashlib.sha256(json.dumps(before['files'], sort_keys=True).encode()).hexdigest()}
    else:
        result = snapshot(args.root.resolve(), args.exclude.resolve())
    write(args.output, result)
    print({k: v for k, v in result.items() if k != 'files' and k != 'git_status_before'})
    if result.get('status') == 'FAIL':
        raise SystemExit(1)
