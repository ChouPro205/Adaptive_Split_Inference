"""Hydrate only manifest-bound dependencies; no export/build or overwrite."""
import argparse
import shutil
import zipfile
import subprocess
import sys
import tempfile
from pathlib import Path

from week5_delivery_scope_v2 import ROOT, SCOPE, inventory, need, read, safe_path, sha


HEADERS = ('device/generated/week4_graph.h', 'device/generated/week4_inputs.h')


def header_entries(scope):
    rows = [row for row in scope['files'] if row['path'] in HEADERS]
    need(len(rows) == len(HEADERS) and {row['path'] for row in rows} == set(HEADERS),
         'Missing/duplicate header bindings in delivery manifest')
    return rows


def check_existing_headers(root, rows):
    missing = []
    for row in rows:
        target = safe_path(root, row['path'])
        if target.exists():
            need(target.is_file() and target.stat().st_size == row['size_bytes']
                 and sha(target) == row['sha256'],
                 f'Existing header changed; refusing overwrite: {target}')
        else:
            missing.append(row)
    return missing


def prepare_headers(root, scope):
    rows = header_entries(scope)
    if not check_existing_headers(root, rows):
        return
    with tempfile.TemporaryDirectory(prefix='week5-authenticated-headers-') as directory:
        generated = Path(directory)
        subprocess.run([sys.executable, '-B', *(['-O'] if sys.flags.optimize else []),
                        str(root / 'device/scripts/generate_week4_inputs.py'),
                        '--repo-root', str(root), '--generated-dir', str(generated)],
                       cwd=root, check=True)
        # Authenticate both candidates before creating any receiver header.
        candidates = {}
        for row in rows:
            candidate = generated / Path(row['path']).name
            need(candidate.is_file() and candidate.stat().st_size == row['size_bytes']
                 and sha(candidate) == row['sha256'],
                 f'Generated header differs from delivery manifest: {row["path"]}')
            candidates[row['path']] = candidate.read_bytes()
        # Recheck after generation; exclusive creation also refuses a file that
        # appeared between this check and opening it. Existing bytes never change.
        for row in check_existing_headers(root, rows):
            target = safe_path(root, row['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(candidates[row['path']])


def setup(cache, root=ROOT):
    scope = read(root / SCOPE.relative_to(ROOT))
    check_existing_headers(root, header_entries(scope))
    for asset in scope['archives']:
        target = safe_path(root, asset['path'])
        source = cache / asset['name']
        if not target.exists():
            need(source.is_file(), f'Missing authenticated archive; obtain from {asset["source"]}: {source}')
            need(sha(source) == asset['sha256'] and source.stat().st_size == asset['size_bytes'],
                 f'Wrong cache archive: {source}')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        need(sha(target) == asset['sha256'] and target.stat().st_size == asset['size_bytes'],
             f'Archive changed: {target}')
        with zipfile.ZipFile(target) as archive:
            need(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate ZIP members')
            need(set(archive.namelist()) == {r['member'] for r in asset['members']}, 'ZIP scope differs')
            pending = []
            for row in asset['members']:
                destination = safe_path(root, row['path'])
                data = archive.read(row['member'])
                import hashlib
                need(len(data) == row['size_bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'],
                     f'ZIP member changed: {row["member"]}')
                if destination.exists():
                    need(destination.is_file() and sha(destination) == row['sha256'],
                         f'Existing dependency changed; refusing overwrite: {destination}')
                else:
                    pending.append((destination, data))
            for destination, data in pending:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as f:
                    f.write(data)
        print(f'Authenticated {asset["name"]}; hydrated {len(pending)} members')
    prepare_headers(root, scope)
    print(f'PASS: {len(inventory(root, scope))} required delivery files authenticated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-cache', type=Path, required=True, help='Four published original ZIPs by their authenticated names')
    args = parser.parse_args()
    setup(args.asset_cache.resolve())
