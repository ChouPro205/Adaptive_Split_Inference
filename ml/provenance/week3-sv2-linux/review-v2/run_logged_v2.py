"""Record new review-v2 runs without touching historical command records."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
name, *argv = sys.argv[1:]
if (out / f"{name}.command.json").exists():
    raise SystemExit("New run name required; refusing to overwrite")
digest = lambda b: hashlib.sha256(b).hexdigest()
paths = [p for p in (root / "ml/scripts").glob("*week3*") if p.is_file()]
state = lambda: {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in paths}
before = state()
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
result = subprocess.run(argv, cwd=root, capture_output=True)
record = {"argv": argv, "cwd": str(root), "started_utc": started,
          "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
          "source_sha256": before, "source_unchanged_during_command": before == state(),
          "exit_code": result.returncode, "streams": {}}
for stream in ("stdout", "stderr"):
    raw = getattr(result, stream)
    target = out / f"{name}.{stream}.txt"
    target.write_bytes(raw)
    record["streams"][stream] = {"path": target.name, "sha256": digest(raw), "size_bytes": len(raw)}
(out / f"{name}.command.json").write_bytes((json.dumps(record, indent=2) + "\n").encode())
print(json.dumps({"run": name, "exit_code": result.returncode}))
print(result.stdout.decode(errors="replace")[-1800:])
print(result.stderr.decode(errors="replace")[-1800:])
sys.exit(result.returncode)
