"""Verify an externally trusted Week 5 asset manifest and hydrate safe ZIP members."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

from week5_common import ROOT, sha, need


def hydrate(manifest_path, expected_sha, archive_dir):
    need(sha(manifest_path) == expected_sha, 'External manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    need(manifest['status'] == 'PUBLISHED_PUBLIC_DOWNLOADS_VERIFIED', 'Publication not verified')
    archive_dir.mkdir(parents=True, exist_ok=True)
    for asset in manifest['assets']:
        name = asset['name']
        need(PurePosixPath(name).name == name and '/' not in name and '\\' not in name, 'Unsafe asset name')
        target = archive_dir / name
        if not target.exists():
            need(asset['url'].startswith('https://github.com/ChouPro205/Adaptive_Split_Inference/releases/download/'), 'Unexpected storage URL')
            with urllib.request.urlopen(asset['url'], timeout=60) as response, target.with_suffix('.part').open('wb') as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            target.with_suffix('.part').replace(target)
        need(target.stat().st_size == asset['size_bytes'] and sha(target) == asset['sha256'], f'Wrong asset: {name}')
        prepared = []
        with zipfile.ZipFile(target) as archive:
            members = {i.filename: i for i in archive.infolist()}
            need(len(members) == len(archive.infolist()), 'Duplicate ZIP members')
            need(set(members) == {r['path'] for r in asset['files']}, 'ZIP inventory differs')
            for row in asset['files']:
                relative = row['path']
                need(relative.startswith(('ml/data/processed/mitdb/', 'ml/artifacts/week5/quantization20/', 'ml/results/week5/')), 'Unexpected member destination')
                parts = relative.split('/')
                need(all(p not in ('', '.', '..') for p in parts) and ':' not in relative and '\\' not in relative, 'Unsafe ZIP member')
                destination = (ROOT / relative).resolve()
                need(ROOT in destination.parents, 'Member escapes repository')
                need(members[relative].file_size == row['size_bytes'], 'Member size differs')
                payload = archive.read(relative)
                need(hashlib.sha256(payload).hexdigest() == row['sha256'], 'Member hash differs')
                if destination.exists():
                    need(destination.is_file() and sha(destination) == row['sha256'], f'Existing file differs; no overwrite: {relative}')
                else:
                    prepared.append((destination, payload))
        for destination, payload in prepared:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        print(f'PASS {name}; hydrated {len(prepared)} files', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / 'ml/provenance/week5/external_assets.json')
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--archive-dir', type=Path, default=ROOT / 'ml/artifacts/week5/downloads')
    args = parser.parse_args()
    hydrate(args.manifest, args.expected_manifest_sha256, args.archive_dir)
