"""Write a new-run receipt after gates; never rewrite historical provenance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def record(repo, logs):
    receipt = logs / "receipt.json"
    if receipt.exists():
        raise ValueError("Run receipt exists; refusing to overwrite")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    sources = {}
    for line in (logs / "source_hashes.stdout.txt").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        if digest(repo / relative) != expected:
            raise ValueError("Source changed during recipe: " + relative)
        sources[relative] = expected
    commands = []
    for status in sorted(logs.glob("*.exit_code.txt")):
        name = status.name.removesuffix(".exit_code.txt")
        if name in ("recipe", "receipt"):
            continue
        code = int(status.read_text())
        if code:
            raise ValueError("Cannot issue PASS receipt for failed step: " + name)
        argv = (logs / f"{name}.argv.bin").read_bytes().split(b"\0")[:-1]
        streams = {stream: {"path": f"{name}.{stream}.txt", "sha256": digest(logs / f"{name}.{stream}.txt"),
                            "size_bytes": (logs / f"{name}.{stream}.txt").stat().st_size}
                   for stream in ("stdout", "stderr")}
        commands.append({"step": name, "argv": [a.decode() for a in argv],
                         "cwd": (logs / f"{name}.cwd.txt").read_text().strip(), "exit_code": code,
                         "started_utc": (logs / f"{name}.started_utc.txt").read_text().strip(),
                         "finished_utc": (logs / f"{name}.finished_utc.txt").read_text().strip(), "streams": streams})
    before = json.loads((logs / "authenticate_before.stdout.txt").read_bytes())
    after = json.loads((logs / "authenticate_after.stdout.txt").read_bytes())
    if before != after:
        raise ValueError("Artifact bytes changed during recipe")
    result = {"schema": "sv3-linux-fp32-recipe-receipt-v2", "base_commit": (logs / "base_commit.stdout.txt").read_text().strip(),
              "source_sha256": sources, "python_runtime": json.loads((logs / "venv_python.stdout.txt").read_bytes()),
              "recomputation_policy": "portable-fp32-v2", "legacy_contract_pass_claimed": False,
              "artifact_before_after_equal": True, "artifact_authentication": before,
              "commands": commands, "status": "AUTHOR_MACHINE_PORTABLE_RECIPE_PASS",
              "receipt_scope": "Completed steps before receipt creation; receipt command and final exit log are outside self-authentication"}
    receipt.write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(receipt), "source_count": len(sources), "completed_step_count": len(commands)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--log-root", type=Path, required=True)
    args = parser.parse_args()
    record(args.repo_root.resolve(), args.log_root.resolve())
