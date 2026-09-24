"""Exercise both provenance gates in an isolated Git snapshot; never train."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from train_mitdb_baseline import SCIENTIFIC_SOURCE_FILES, scientific_source_provenance
from verify_week2_baseline import HISTORICAL_SOURCE_COMMIT, verification_provenance_gate
from week1_common import ML_ROOT, load_config, require, run_cli


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=("train", "verify"), help="Child process: exercise only this gate")
    parser.add_argument("--verify-historical-artifacts", action="store_true")
    args = parser.parse_args()
    if args.gate:
        if args.gate == "train":
            scientific_source_provenance(load_config("mitdb_week2_baseline.json")[0])
        else:
            verification_provenance_gate()
        print(f"{args.gate} provenance gate: PASS")
        return

    repo = ML_ROOT.parent
    helpers = SCIENTIFIC_SOURCE_FILES[4:]
    original_helpers = {name: (repo / name).read_bytes() for name in helpers}
    with tempfile.TemporaryDirectory(prefix="sv3_week2_provenance_") as temporary:
        fixture = Path(temporary)
        files = set(SCIENTIFIC_SOURCE_FILES) | {
            "ml/src/verify_week2_baseline.py", "ml/src/test_week2_provenance.py", ".gitattributes"}
        for directory in ("ml/configs", "ml/manifests"):
            files.update(path.relative_to(repo).as_posix() for path in (repo / directory).glob("*") if path.is_file())
        for name in files:
            target = fixture / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / name, target)

        def git(*arguments: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", *arguments], cwd=fixture, text=True,
                                  capture_output=True, check=True)

        git("init", "--quiet")
        git("config", "core.autocrlf", "false")
        git("add", ".")
        git("-c", "user.name=Provenance Test", "-c", "user.email=provenance-test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Isolated candidate source snapshot")

        def gate_command(gate: str) -> list[str]:
            return [sys.executable, "-B", "ml/src/test_week2_provenance.py", "--gate", gate]

        for gate in ("train", "verify"):
            result = subprocess.run(gate_command(gate), cwd=fixture, text=True, capture_output=True)
            require(result.returncode == 0, f"Clean {gate} gate failed: {result.stdout}{result.stderr}")
            print(f"Clean snapshot {gate} gate: exit=0 PASS")
        for name in helpers:
            path = fixture / name
            original = path.read_bytes()
            try:
                path.write_bytes(original + b"\n# Harmless temporary provenance-negative-test marker.\n")
                for gate in ("train", "verify"):
                    command = gate_command(gate)
                    result = subprocess.run(command, cwd=fixture, text=True, capture_output=True)
                    message = f"ERROR: Scientific source/config differs from HEAD: {name}"
                    log = result.stdout + result.stderr
                    require(result.returncode == 1 and message in log,
                            f"Wrong rejection for {name}/{gate}: exit={result.returncode}: {log}")
                    print(f"MUTATION: {name}")
                    print(f"COMMAND: {subprocess.list2cmdline(command)} (cwd=isolated snapshot)")
                    print(f"EXIT=1 EXPECTED_REJECTION: {message}")
            finally:
                path.write_bytes(original)
            git("diff", "--exit-code", "HEAD", "--", name)
            print(f"RESTORED: git diff --exit-code HEAD -- {name}: exit=0")

        if args.verify_historical_artifacts:
            # Import only the historical commit object; never change its history.
            git("fetch", "--quiet", "--no-tags", str(repo), HISTORICAL_SOURCE_COMMIT)
            for directory in ("ml/data/processed/mitdb", "ml/data/week2/mitdb_baseline"):
                (fixture / directory).mkdir(parents=True, exist_ok=True)
                for path in (repo / directory).iterdir():
                    if path.is_file():
                        # Verifier reads only. Copies avoid links to mutable evidence.
                        shutil.copyfile(path, fixture / directory / path.name)
            target = fixture / "ml/provenance/week2_run_manifest.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / "ml/provenance/week2_run_manifest.json", target)
            command = [sys.executable, "-B", "ml/src/verify_week2_baseline.py", "--historical"]
            result = subprocess.run(command, cwd=fixture, text=True, capture_output=True)
            print(f"COMMAND: {subprocess.list2cmdline(command)} (cwd=isolated snapshot)")
            print(result.stdout + result.stderr, end="")
            require(result.returncode == 0, f"Historical artifact verification failed: exit={result.returncode}")
            print("HISTORICAL_ARTIFACT_EXIT=0")
    for name, original in original_helpers.items():
        require((repo / name).read_bytes() == original, f"Real helper changed: {name}")
        subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", name], cwd=repo, check=True)
        print(f"REAL_HELPER_UNCHANGED: {name}; git diff exit=0")
    print("STATUS: PASS (four intended rejections, two restored helpers)")


if __name__ == "__main__":
    run_cli(main)
