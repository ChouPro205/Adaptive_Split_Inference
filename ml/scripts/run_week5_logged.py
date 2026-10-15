"""Run one command with exclusive new logs and source/environment provenance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True, help='New evidence prefix')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Missing command')
    paths = [Path(str(args.output) + suffix) for suffix in ('.stdout.txt', '.stderr.txt', '.command.json')]
    if any(p.exists() for p in paths):
        raise ValueError('Evidence exists; choose a fresh prefix')
    paths[0].parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    # Scope Git trust to this explicitly authorized checkout, without global changes.
    env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='safe.directory', GIT_CONFIG_VALUE_0=ROOT.as_posix())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
    sources = [*sorted((ROOT/'ml/scripts').glob('*week5*.py')), ROOT/'ml/src/quantization.py',
               ROOT/'ml/src/p1.py', ROOT/'ml/src/week5_interfaces.py',
               *sorted((ROOT/'contracts/i2_ref').glob('*')), ROOT/'contracts/sv3_week5_ml_registry_v1.json']
    sources = [p for p in sources if p.is_file()]
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    started = time.monotonic()
    with paths[0].open('xb') as out, paths[1].open('xb') as err:
        process = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=err)
    record = {'command': command, 'cwd': str(ROOT), 'exit_code': process.returncode,
              'elapsed_seconds': time.monotonic()-started, 'source_git_commit': commit,
              'source_files_sha256': hashes,
              'stdout_sha256': sha(paths[0]), 'stderr_sha256': sha(paths[1]),
              'git_trust': ROOT.as_posix(), 'python': sys.version}
    with paths[2].open('x', encoding='utf-8', newline='\n') as f:
        json.dump(record, f, indent=2)
        f.write('\n')
    print(f"exit={process.returncode}; {paths[2]}", flush=True)
    raise SystemExit(process.returncode)
