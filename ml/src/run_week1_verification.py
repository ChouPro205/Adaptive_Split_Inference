"""Run the reproducible Week 1 suite and write a machine-readable run manifest."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from week1_common import ML_ROOT, config_sha256, load_config, load_json, require, run_cli, sha256_file


REPO_ROOT = ML_ROOT.parent
PROVENANCE_DIR = ML_ROOT / "provenance"
OUTPUT = PROVENANCE_DIR / "week1_run_manifest.json"
COMMANDS = [
    ["-B", "ml/src/check_env.py"],
    ["-B", "ml/src/download_mitdb.py"],
    ["-B", "ml/src/verify_mitdb_integrity.py"],
    ["-B", "ml/src/inspect_mitdb.py"],
    ["-B", "ml/src/test_segmentation.py"],
    ["-B", "ml/src/audit_mitdb_preprocessing.py"],
    ["-B", "ml/src/build_mitdb_manifest.py"],
    ["-B", "ml/src/compute_mitdb_normalization.py"],
    ["-B", "ml/src/verify_mitdb_normalization.py"],
    ["-B", "ml/src/build_mitdb_processed.py"],
    ["-B", "ml/src/verify_mitdb_processed.py"],
    ["-O", "ml/src/verify_mitdb_integrity.py"],
    ["-O", "ml/src/verify_mitdb_processed.py"],
    ["-B", "ml/src/download_ptbxl.py"],
    ["-B", "ml/src/build_ptbxl_manifest.py"],
    ["-B", "ml/src/compute_ptbxl_normalization.py"],
    ["-B", "ml/src/verify_ptbxl_normalization.py"],
    ["-B", "ml/src/verify_ptbxl.py"],
    ["-B", "ml/src/test_week1_negative.py"],
]
PACKAGES = ["torch", "numpy", "pandas", "scipy", "matplotlib", "wfdb", "scikit-learn"]


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def main() -> None:
    started = datetime.now(timezone.utc)
    command_results: list[dict[str, object]] = []
    dataset_tree_hashes: dict[str, str] = {}
    for arguments in COMMANDS:
        display = "python " + " ".join(shlex.quote(item) for item in arguments)
        print(f"\n>>> {display}", flush=True)
        before = time.perf_counter()
        result = subprocess.run([sys.executable, *arguments], cwd=REPO_ROOT, text=True,
                                capture_output=True, check=False)
        duration = time.perf_counter() - before
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
        combined = result.stdout + result.stderr
        for label, pattern in (
            ("mitdb", r"Required-file tree SHA-256:\s*([0-9a-f]{64})"),
            ("ptbxl", r"File tree SHA-256\s*:\s*([0-9a-f]{64})"),
        ):
            match = re.search(pattern, combined)
            if match:
                dataset_tree_hashes[label] = match.group(1)
        command_results.append({
            "command": display,
            "exit_status": result.returncode,
            "duration_seconds": round(duration, 3),
            "output_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        })

    configs: dict[str, dict[str, str]] = {}
    datasets: dict[str, dict[str, str]] = {}
    for name in ("environment.json", "mitdb_week1_config.json", "ptbxl_week1_config.json"):
        path, config = load_config(name)
        configs[name] = {"path": path.relative_to(REPO_ROOT).as_posix(), "sha256": config_sha256(path)}
        if "dataset" in config:
            slug = config["dataset"]["slug"]
            datasets[slug] = {
                "version": config["dataset"]["version"],
                "source_url": config["dataset"]["source_url"],
                "checksum_manifest_sha256": config["integrity"]["physionet_checksum_manifest_sha256"],
                "required_file_tree_sha256": dataset_tree_hashes.get(slug, "verification-command-failed"),
            }

    artifact_paths = [
        ML_ROOT / "manifests" / "mitdb_expected_records.txt",
        ML_ROOT / "manifests" / "mitdb_patient_split.csv",
        ML_ROOT / "manifests" / "ptbxl_patient_split.csv",
        ML_ROOT / "configs" / "mitdb_normalization.json",
        ML_ROOT / "configs" / "ptbxl_normalization.json",
    ]
    artifacts = {path.relative_to(REPO_ROOT).as_posix(): sha256_file(path) for path in artifact_paths}
    processed_manifest_path = ML_ROOT / "data" / "processed" / "mitdb" / "processed_manifest.json"
    if processed_manifest_path.is_file():
        processed = load_json(processed_manifest_path)
        artifacts.update({f"ml/data/processed/mitdb/{name}": digest
                          for name, digest in processed.get("artifacts", {}).items()})
        artifacts[processed_manifest_path.relative_to(REPO_ROOT).as_posix()] = sha256_file(processed_manifest_path)

    exit_status = 0 if all(item["exit_status"] == 0 for item in command_results) else 1
    manifest = {
        "schema_version": 1,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "git": {
            "commit_sha": git_output("rev-parse", "HEAD"),
            "branch": git_output("branch", "--show-current"),
            "dirty": git_output("status", "--porcelain") != "",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "os": platform.platform(),
            "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        },
        "configs": configs,
        "datasets": datasets,
        "commands": command_results,
        "artifact_sha256": artifacts,
        "exit_status": exit_status,
    }
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(f"\nRun manifest: {OUTPUT.relative_to(REPO_ROOT)}")
    print(f"Overall exit status: {exit_status}")
    if exit_status != 0:
        raise SystemExit(exit_status)


if __name__ == "__main__":
    run_cli(main)
