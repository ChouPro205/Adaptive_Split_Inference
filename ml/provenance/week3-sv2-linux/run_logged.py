"""Local evidence runner; records exact argv, cwd, source state and both streams."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
name, *command = sys.argv[1:]
out = Path(__file__).resolve().parent
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
source_paths = list((root / "ml/scripts").glob("*week3*py")) + list((root / "ml/scripts").glob("*week4*py"))
source_state = lambda: {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_paths)}
before = source_state()
result = subprocess.run(command, cwd=root, capture_output=True)
record = {"argv": command, "cwd": str(root), "started_utc": started,
          "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
          "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=root).decode().strip(),
          "exit_code": result.returncode, "streams": {}}
for stream in ("stdout", "stderr"):
    raw = getattr(result, stream)
    path = out / f"{name}.{stream}.txt"
    path.write_bytes(raw)
    record["streams"][stream] = {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
record["source_sha256"] = before
record["source_unchanged_during_command"] = before == source_state()
(out / f"{name}.command.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"name": name, "exit_code": result.returncode}))
print(result.stdout.decode("utf-8", errors="replace")[-3000:])
print(result.stderr.decode("utf-8", errors="replace")[-3000:])
sys.exit(result.returncode)
