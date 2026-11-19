"""Week 10 evidence helpers; Python 3.9+. No inference or network at import."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SHA = 'd0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36'
BUNDLE_SHA = '41fe3388db89bdb0d1759e4bc7b6b926af1fb8d87bd8c71d880505695ce14a44'
COMPILE_SHA = '4fb7b31a2fe98ee270cc2896e0674d0058be5b4363ff742b3e768150cf012237'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def child(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('Unsafe relative path: ' + str(relative))
    target = root / rel
    if any(p.is_symlink() for p in [target, *target.parents] if p != root and root in p.parents):
        raise ValueError('Symlink in evidence: ' + str(relative))
    if not target.resolve().is_relative_to(root):
        raise ValueError('Path leaves evidence root')
    return target


def verify(folder, inventory='sha256sum_results.txt'):
    folder = Path(folder).resolve()
    seen = set()
    for line in (folder / inventory).read_text().splitlines():
        expected, relative = line.split('  ', 1)
        if relative in seen or len(expected) != 64:
            raise ValueError('Invalid/duplicate inventory row')
        seen.add(relative)
        if sha(child(folder, relative)) != expected:
            raise ValueError('Checksum mismatch: ' + relative)
    if not seen:
        raise ValueError('Empty checksum inventory')
    return seen


def seal(folder, inventory='sha256sum_results.txt'):
    folder = Path(folder).resolve()
    lines = []
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise ValueError('Cannot seal symlink')
        if path.is_file() and path != folder / inventory:
            relative = path.relative_to(folder).as_posix()
            if '\n' in relative:
                raise ValueError('Newline in file name')
            lines.append(sha(path) + '  ' + relative + '\n')
    with (folder / inventory).open('x') as f:
        f.writelines(lines)


def package(path):
    path = Path(path).resolve()
    if sha(path / 'manifest.json') != PACKAGE_SHA:
        raise ValueError('Packet manifest anchor mismatch')
    manifest = json.loads((path / 'manifest.json').read_text())
    expected = {r['path'] for r in manifest['files']}
    actual = {p.relative_to(path).as_posix() for p in path.rglob('*')
              if p.is_file() and p != path / 'manifest.json'}
    if len(expected) != len(manifest['files']) or actual != expected:
        raise ValueError('Packet inventory differs')
    for row in manifest['files']:
        p = child(path, row['path'])
        if p.stat().st_size != row['size_bytes'] or sha(p) != row['sha256']:
            raise ValueError('Packet member differs: ' + row['path'])
    data = json.loads((path / 'vectors.json').read_text())
    vectors = data['vectors']
    if len(vectors) != 50 or {v['split_point_s'] for v in vectors} != set(range(11)):
        raise ValueError('Need 50 authenticated vectors covering s0..s10')
    return vectors


def models(deploy):
    deploy = Path(deploy).resolve()
    if sha(deploy / 'sha256sum_bundle.txt') != BUNDLE_SHA:
        raise ValueError('Bundle inventory anchor mismatch')
    verify(deploy, 'sha256sum_bundle.txt')
    p = deploy / 'release/provenance/compile_manifest.json'
    if sha(p) != COMPILE_SHA:
        raise ValueError('Compile manifest anchor mismatch')
    rows = json.loads(p.read_text())['splits']
    if len(rows) != 10 or {r['split'] for r in rows} != set(range(10)):
        raise ValueError('Need ten native models')
    expected = {}
    for row in rows:
        s = row['split']
        p = deploy / f'release/models/tail_s{s}.xmodel'
        if sha(p) != row['xmodel_sha256']:
            raise ValueError('Model checksum differs: ' + str(s))
        expected[str(s)] = row['xmodel_sha256']
    return expected
