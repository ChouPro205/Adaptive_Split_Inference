"""Capture pinned GitHub evidence, environment and preservation inventory read-only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'ml/scripts'))
from review_week7_sv2 import sha, write, need


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def inventory():
    # Only this checkout; do not traverse source mirrors or other worktrees.
    paths = set()
    for name in ('ml/data', 'ml/artifacts', '.cache/week7-reconcile'):
        paths.update(p for p in (ROOT/name).rglob('*') if p.is_file() and
                     p.suffix.lower() in ('.npy', '.npz', '.pt', '.pth', '.onnx', '.zip'))
    return {p.relative_to(ROOT).as_posix(): {'sha256': sha(p), 'size': p.stat().st_size}
            for p in sorted(paths)}


def main():
    pins = {'main': '02ad8c83297d5bee9298342b2bd4e4ff406922ac',
            'dev/device-sv1': '549aa1021c250c5c8319f99c35b5b6d90c9744d1',
            'dev/edge-sv2': '8d962095a11a0e41696b9cdeac163ed0d240daed'}
    live = git('-c', 'http.sslBackend=openssl', 'ls-remote', 'origin',
               *(f'refs/heads/{b}' for b in pins)).decode()
    actual = {line.split()[1].removeprefix('refs/heads/'): line.split()[0]
              for line in live.splitlines()}
    need(actual == pins, 'GitHub heads changed: review before continuing')
    write(OUT/'github-refs.json', {'checked_utc': datetime.now(timezone.utc).isoformat(),
          'command': 'git -c http.sslBackend=openssl ls-remote origin refs/heads/main refs/heads/dev/device-sv1 refs/heads/dev/edge-sv2',
          'refs': actual, 'raw_stdout': live, 'local_head': git('rev-parse','HEAD').decode().strip()})
    snapshots = {'main-r2': (pins['main'], 'contracts/sv1_sv2_week8_registry_revision_r2.json'),
                 'sv1-r2': (pins['dev/device-sv1'], 'contracts/sv1_sv2_week8_registry_revision_r2.json'),
                 'edge-summary': (pins['dev/edge-sv2'], 'results/week8/edge/summary.json'),
                 'edge-provenance': (pins['dev/edge-sv2'], 'results/week8/edge/provenance.json')}
    records = {}
    for name, (commit, path) in snapshots.items():
        raw = git('show', commit+':'+path)
        with (OUT/(name+'.json')).open('xb') as f:
            f.write(raw)
        records[name] = {'commit': commit, 'path': path, 'sha256': hashlib.sha256(raw).hexdigest()}
    # Verify published Edge checksum list against exact blobs, without merging PR40.
    commit = pins['dev/edge-sv2']
    checksums = git('show', commit+':results/week8/edge/sha256sum_export.txt').decode()
    checked = []
    for line in checksums.splitlines():
        digest, name = line.split(maxsplit=1)
        name = name.lstrip('*')
        need(hashlib.sha256(git('show',commit+':results/week8/edge/'+name)).hexdigest() == digest,
             'Edge export checksum differs: '+name)
        checked.append(name)
    # Search the published result scope and locally delivered JSON, not source mirrors.
    candidates = []
    for branch, pin in pins.items():
        names = git('ls-tree','-r','--name-only',pin,'results','ml/results').decode().splitlines()
        for name in names:
            if name.endswith('.json'):
                raw = git('show',pin+':'+name)
                if b'sv3-week7-dpu-output/1' in raw:
                    candidates.append({'scope': branch, 'commit': pin, 'path': name})
    for scope in ('.cache', 'ml/results', 'results'):
        for path in (ROOT/scope).rglob('*.json'):
            if b'sv3-week7-dpu-output/1' in path.read_bytes():
                candidates.append({'scope': 'local', 'path': path.relative_to(ROOT).as_posix()})
    write(OUT/'source-review.json', {'snapshots': records, 'edge_export_checksum_files': checked,
          'full_dpu_output_candidates': candidates,
          'search_scope': 'Pinned main/SV1/SV2 results and ml/results JSON; local .cache, results and ml/results JSON. No external inbox claim.',
          'DPU_acceptance': 'INCOMPLETE_NO_ACCEPTANCE' if not candidates else 'REQUIRES_PROVENANCE_REVIEW'})
    import torch
    write(OUT/'environment.json', {'python': sys.version, 'executable': sys.executable,
          'platform': platform.platform(), 'git': git('--version').decode().strip(),
          'packages': {n: importlib.metadata.version(n) for n in ('torch','numpy','pandas','wfdb')},
          'cuda_available': torch.cuda.is_available(), 'torch_cuda': torch.version.cuda,
          'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None})
    write(OUT/'preservation-before.json', inventory())
    print(json.dumps({'status': 'CAPTURED', 'refs': actual, 'output_candidates': candidates,
                      'edge_export_files_verified': len(checked)}))


if __name__ == '__main__':
    main()
