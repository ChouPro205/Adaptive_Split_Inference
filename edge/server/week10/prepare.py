#!/usr/bin/env python3
"""Prepare an immutable Week 10 source/input bundle; never runs SSH or models."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from evidence import ROOT, BUNDLE_SHA, COMPILE_SHA, PACKAGE_SHA, models, package, save, seal, sha, verify


def prepare(repo, packet_path, bundle, output, pointer=None):
    repo, packet_path, bundle, output = map(lambda p: Path(p).resolve(), (repo, packet_path, bundle, output))
    if output.exists():
        raise FileExistsError('Output exists; use verify or a new _lan_2 directory')
    if output.is_relative_to(packet_path) or output.is_relative_to(bundle):
        raise ValueError('Output must not be inside immutable inputs')
    if pointer and Path(pointer).exists():
        raise FileExistsError('Pointer exists; use the current session or explicit new output without pointer')
    vectors = package(packet_path)
    model_hashes = models(bundle)
    expected = json.loads((repo / 'experiments/configs/sv2_edge_week9/expected_backend.json').read_text())
    source_files = []
    for directory in ('edge/server/week10', 'edge/runtime/model_cache',
                      'contracts/i1v2_ref', 'contracts/i2_ref'):
        for p in sorted((repo / directory).rglob('*')):
            if p.is_file() and p.suffix in ('.py', '.cpp', '.hpp', '.h', '.c', '.sh', '.md', '.json'):
                if p.is_symlink():
                    raise ValueError('Source symlink: ' + str(p))
                source_files.append(p)
    source_files += [repo / 'contracts/sv3_week5_approved_registry_v2.json',
                     repo / 'edge/runtime/single_input/tail_io.hpp',
                     repo / 'edge/runtime/single_input/tail_runner.cpp']
    output.mkdir(parents=True)
    for name in ('source', 'inputs', 'config', 'logs', 'nhan_board', 'analyses'):
        (output / name).mkdir()
    for p in source_files:
        target = output / 'source' / p.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    shutil.copytree(packet_path, output / 'inputs/packets')
    git = lambda *args: subprocess.check_output(['git', '-C', str(repo), *args], text=True)
    save(output / 'source/source.json', {
        'git_head': git('rev-parse', 'HEAD').strip(),
        'git_status': git('status', '--short'),
        'source_binding': 'actual copied bytes; uncommitted files are not claimed to be in HEAD',
        'files': {p.relative_to(repo).as_posix(): sha(p) for p in source_files},
    })
    (output / 'source/tracked_diff.patch').write_text(git('diff', 'HEAD', '--', 'edge'))
    save(output / 'config/backend.json', {
        'bundle_inventory_sha256': BUNDLE_SHA, 'compile_manifest_sha256': COMPILE_SHA,
        'models': model_hashes, 'plugins': expected['plugins'],
    })
    save(output / 'config/benchmark.json', {
        'warmup_per_split': 20, 'cycles': 100, 'splits': list(range(10)),
        'plan': 'ascending and descending cycles; same-split controls and s10 separate',
        'switch_threshold_ms': 50, 'acceptance': 'ENGINEERING_REPORT_PENDING_REVIEW',
    })
    save(output / 'preparation.json', {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Week10 offline I1 model cache; no BLE validation, no measurements yet',
        'packet_manifest_sha256': PACKAGE_SHA, 'vectors': len(vectors),
        'source_repo': str(repo), 'packet_source': str(packet_path), 'bundle_source': str(bundle),
        'board_deploy': '/home/root/asi_week10', 'status': 'PREPARED_NOT_EXECUTED',
    })
    # Include only immutable preparation content, not future logs/results.
    with (output / 'sha256sum_prepare.txt').open('x') as f:
        for p in sorted(output.rglob('*')):
            if p.is_file() and p.name != 'sha256sum_prepare.txt':
                f.write(sha(p) + '  ' + p.relative_to(output).as_posix() + '\n')
    verify(output, 'sha256sum_prepare.txt')
    with tarfile.open(output / 'deploy.tar.gz', 'x:gz') as archive:
        for name in ('source', 'inputs', 'config', 'preparation.json', 'sha256sum_prepare.txt'):
            archive.add(output / name, arcname=name)
    (output / 'deploy.tar.gz.sha256.txt').write_text(sha(output / 'deploy.tar.gz') + '  deploy.tar.gz\n')
    if pointer:
        pointer = Path(pointer)
        pointer.parent.mkdir(parents=True, exist_ok=True)
        with pointer.open('x') as f:
            f.write(str(output) + '\n')
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=ROOT)
    p.add_argument('--package', type=Path)
    p.add_argument('--bundle', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--pointer', type=Path)
    p.add_argument('--verify', type=Path, help='Verify an existing session; creates no new files')
    p.add_argument('--check-source', action='store_true', help='With --verify, also compare current repo source bytes to snapshot')
    a = p.parse_args()
    if a.verify:
        verify(a.verify, 'sha256sum_prepare.txt')
        if sha(a.verify / 'deploy.tar.gz') != (a.verify / 'deploy.tar.gz.sha256.txt').read_text().split()[0]:
            raise ValueError('Deploy archive hash differs')
        if a.check_source:
            source = json.loads((a.verify / 'source/source.json').read_text())
            for relative, expected in source['files'].items():
                if sha(a.repo / relative) != expected:
                    raise ValueError('Current source differs from snapshot: ' + relative)
        print('PREPARATION_HASH_OK', a.verify)
    else:
        if not all((a.package, a.bundle, a.output)):
            p.error('Need --package, --bundle, --output (or --verify)')
        if a.check_source:
            p.error('--check-source requires --verify')
        print('WEEK10_PREPARED_NOT_EXECUTED', prepare(a.repo, a.package, a.bundle, a.output, a.pointer))


if __name__ == '__main__':
    main()
