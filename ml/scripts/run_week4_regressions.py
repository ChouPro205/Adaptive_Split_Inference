"""Read-only historical Week 1-3 regression runner; writes only NEW Week 4 evidence."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from week3_common import need, sha, text, write_json
from week3_sv2_common import SV1_MANIFEST
from week4_common import W3_PATH, W3_SHA


def preserved(repo):
    paths = set()
    for directory in ("ml/configs", "ml/manifests", "ml/src", "ml/provenance/week3", "ml/artifacts/week3",
                      "ml/docs/reports", "results/week3", "device/reports"):
        paths.update(p for p in (repo / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for pattern in ("ml/scripts/*week3*.py", "ml/provenance/week[12]*.json", "ml/*.zip", "*.zip"):
        paths.update(repo.glob(pattern))
    return {p.relative_to(repo).as_posix(): sha(p) for p in sorted(paths) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--evidence-dir", type=Path, default=Path("ml/provenance/week4/regressions"))
    args = parser.parse_args()
    repo, evidence = args.repo_root.resolve(), args.evidence_dir.resolve()
    need(not evidence.exists(), "Regression evidence exists; choose a NEW evidence directory")
    before = preserved(repo)
    evidence.mkdir(parents=True)
    scripts = [
        "check_env.py", "verify_mitdb_integrity.py", "test_segmentation.py", "audit_mitdb_preprocessing.py",
        "verify_mitdb_normalization.py", "verify_mitdb_processed.py", "verify_ptbxl_normalization.py",
        "verify_ptbxl.py", "test_week1_negative.py", "test_week2_baseline.py"]
    commands = [["-B", f"ml/src/{n}"] for n in scripts]
    commands += [["-B", "-O", "ml/src/verify_mitdb_integrity.py"],
                 ["-B", "-O", "ml/src/verify_mitdb_processed.py"],
                 ["-B", "ml/src/verify_week2_baseline.py", "--historical"],
                 ["-B", "ml/src/test_week2_provenance.py", "--verify-historical-artifacts"]]
    sv1 = "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    for script in ("verify_week3.py", "test_week3.py"):
        cmd = ["-B", f"ml/scripts/{script}", "--repo-root", ".", "--package", sv1,
               "--expected-manifest-sha256", SV1_MANIFEST]
        if script.startswith("verify"):
            cmd += ["--compiler", "C:/msys64/ucrt64/bin/gcc.exe"]
        commands.append(cmd)
    for script in ("verify_week3_sv2.py", "test_week3_sv2.py"):
        commands.append(["-B", f"ml/scripts/{script}", "--package", W3_PATH, "--expected-manifest-sha256", W3_SHA])
    records = []
    for index, command in enumerate(commands):
        display = "& ml/.venv/Scripts/python.exe " + " ".join(command)
        print(f"RUN {index+1}/{len(commands)}: {display}", flush=True)
        result = subprocess.run([sys.executable, *command], cwd=repo, text=True, encoding="utf-8", errors="replace", capture_output=True)
        log = evidence / f"{index+1:02d}_{Path(command[1]).stem}.txt"
        text(log, result.stdout + result.stderr)
        records.append({"command": display, "exit_status": result.returncode,
                        "status": "PASS" if result.returncode == 0 else "FAIL",
                        "log_path": log.relative_to(repo).as_posix(), "log_sha256": sha(log)})
        print(f"{'PASS' if result.returncode == 0 else 'FAIL'} exit={result.returncode}; {log.name}", flush=True)
        if result.returncode:
            break
    after = preserved(repo)
    unchanged = before == after
    summary = {"status": "PASS" if unchanged and len(records) == len(commands) and all(r["exit_status"] == 0 for r in records) else "FAIL",
               "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
               "commands": records, "historical_files_unchanged": unchanged, "preserved_file_count": len(before),
               "preserved_sha256": before, "runner_sha256": sha(Path(__file__)),
               "policy": "No training, downloads, rebuilds or historical manifest writes; Week 4 evidence only"}
    write_json(evidence / "summary.json", summary)
    need(summary["status"] == "PASS", "Historical regressions FAILED; see Week 4 logs")
    print(f"WEEK1_3_REGRESSIONS_PASS: {len(records)} commands; {len(before)} historical/user files byte-identical", flush=True)


if __name__ == "__main__":
    main()
