"""Capture one Week7 command with exact return code and LF-normalized source hashes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from week1_common import artifact_sha256


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.name or Path(args.name).name != args.name or any(c in args.name for c in '/\\:'):
        parser.error("name must be a basename")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command required after --")
    args.directory.mkdir(parents=True, exist_ok=True)
    paths = {suffix: args.directory / f"{args.name}.{suffix}" for suffix in ("stdout.txt", "stderr.txt", "command.json")}
    if any(p.exists() for p in paths.values()):
        parser.error("refuse to overwrite command evidence")
    # Includes untracked new sources: committing is a separate delivery step.
    sources = sorted(set((ROOT / "ml/src").glob("*.py")) | set((ROOT / "ml/scripts").glob("*week7*.py")) |
                     set((ROOT / "ml/configs").glob("*nopeek*.json")))
    before = {p.relative_to(ROOT).as_posix(): artifact_sha256(p) for p in sources}
    started, tick = datetime.now(timezone.utc).isoformat(), time.monotonic()
    with paths["stdout.txt"].open("xb") as stdout, paths["stderr.txt"].open("xb") as stderr:
        result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    after = {p.relative_to(ROOT).as_posix(): artifact_sha256(p) for p in sources}
    evidence = {"command": command, "cwd": str(ROOT), "exit_code": result.returncode,
                "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": time.monotonic()-tick,
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source_sha256": before, "sources_unchanged_during_command": before == after,
                "logs_sha256": {s: hashlib.sha256(paths[s].read_bytes()).hexdigest() for s in ("stdout.txt", "stderr.txt")}}
    paths["command.json"].write_text(json.dumps(evidence, indent=2, allow_nan=False)+'\n', encoding="utf-8")
    print(json.dumps({"name": args.name, "exit_code": result.returncode, "sources_unchanged": before == after,
                      "elapsed_seconds": evidence["elapsed_seconds"]}))
    sys.exit(result.returncode if before == after else 2)
