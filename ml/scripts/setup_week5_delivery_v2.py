"""Hydrate only manifest-bound dependencies; no export/build or overwrite."""
import argparse
import shutil
import zipfile
import subprocess
import sys
from pathlib import Path

from week5_delivery_scope_v2 import ROOT, SCOPE, inventory, need, read, safe_path, sha


def setup(cache, root=ROOT):
    scope = read(root / SCOPE.relative_to(ROOT))
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
    subprocess.run([sys.executable, '-B', 'device/scripts/generate_week4_inputs.py',
                    '--generated-dir', 'device/generated'], cwd=root, check=True)
    print(f'PASS: {len(inventory(root, scope))} required delivery files authenticated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-cache', type=Path, required=True, help='Five original ZIPs by their authenticated names')
    args = parser.parse_args()
    setup(args.asset_cache.resolve())
