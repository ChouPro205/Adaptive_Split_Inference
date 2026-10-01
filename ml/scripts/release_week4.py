"""Build a NEW Week 4 release, retain gate logs and package binaries outside Git."""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from profile_week4 import export
from verify_week4 import verify
from week3_common import need, read_json, sha, text, write_json
from week3_sv2_common import SV1_MANIFEST
from week4_common import OUTPUT, W3_PATH, W3_SHA, compare_reproduction


def release(repo, compiler):
    repo = Path(repo).resolve()
    evidence = repo / "ml/provenance/week4-r2"
    output = repo / OUTPUT
    archive = repo / "ml/artifacts/week4/mitdb-sv1-week4-fp32-20261001-r2.zip"
    need(not evidence.exists() and not output.exists() and not archive.exists(),
         "Release revision exists; preserve it and choose a new revision")
    evidence.mkdir(parents=True)
    records = []
    protected = [repo / "ml/artifacts/week3", repo / "ml/results/week4", repo / "device", repo / "results/week3"]
    def preserved():
        return {p.relative_to(repo).as_posix(): sha(p) for directory in protected
                for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                and not any(part.startswith("build") for part in p.parts)}
    before = preserved()

    def run(name, args, cwd=repo):
        command = [sys.executable, "-B", *map(str, args)]
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        log = evidence / f"{name}.txt"
        text(log, result.stdout + result.stderr)
        records.append({"name": name, "command": command, "cwd": str(cwd),
                        "exit_status": result.returncode, "log_path": log.relative_to(repo).as_posix(),
                        "log_sha256": sha(log)})
        write_json(evidence / "commands.json", records)
        print(f"{name}: exit={result.returncode}", flush=True)
        need(result.returncode == 0, f"Gate failed: {name}; see {log}")

    try:
        for script in repo.glob("ml/scripts/*week4*.py"):
            ast.parse(script.read_text(encoding="utf-8"))
        for name in ("verify_week3_sv2", "test_week3_sv2"):
            run(name, [f"ml/scripts/{name}.py", "--package", W3_PATH,
                       "--expected-manifest-sha256", W3_SHA])
        sv1 = "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
        run("verify_week3", ["ml/scripts/verify_week3.py", "--repo-root", ".", "--package", sv1,
                            "--expected-manifest-sha256", SV1_MANIFEST, "--compiler", compiler])
        run("test_week3", ["ml/scripts/test_week3.py", "--repo-root", ".", "--package", sv1,
                          "--expected-manifest-sha256", SV1_MANIFEST])
        anchor = export(repo, output, compiler)
        write_json(evidence / "verification.json", verify(output, repo, anchor, compiler))
        run("test_week4", ["ml/scripts/test_week4.py", "--repo-root", ".", "--output-dir", OUTPUT,
                          "--expected-manifest-sha256", anchor, "--compiler", compiler])
        # The clone is a receiver snapshot with reviewed source overlays, NOT a committed fix.
        with tempfile.TemporaryDirectory(prefix="week4_receiver_") as tmp:
            receiver = Path(tmp) / "checkout"
            subprocess.run(["git", "clone", "--local", "--no-hardlinks", str(repo), str(receiver)],
                           check=True, capture_output=True)
            m = read_json(output / "manifest.json")
            for row in m["source_files"]:
                target = receiver / row["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / row["path"], target)
            shutil.copytree(repo / W3_PATH, receiver / W3_PATH)
            shutil.copytree(output, receiver / OUTPUT)
            need(not (receiver / "ml/data/week2/mitdb_baseline/best_checkpoint.pt").exists(), "Duplicate checkpoint leaked")
            need(not (receiver / "ml/docs/project_sources").exists(), "DOCX dependencies leaked")
            write_json(evidence / "receiver_verification.json", verify(receiver / OUTPUT, receiver, anchor, compiler))
            # Exercise production source verification with CRLF, then actual content corruption.
            csv = receiver / "ml/manifests/mitdb_patient_split.csv"
            raw = csv.read_bytes()
            csv.write_bytes(raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            verify(receiver / OUTPUT, receiver, anchor, compiler)
            csv.write_bytes(csv.read_bytes() + b"corrupted\r\n")
            try:
                verify(receiver / OUTPUT, receiver, anchor, compiler)
            except ValueError as exc:
                need("Source file changed" in str(exc), f"Wrong source rejection: {exc}")
            else:
                raise ValueError("Source corruption accepted")
            csv.write_bytes(raw)
            subprocess.run(["git", "checkout", "-b", "test/receiver-other-branch"], cwd=receiver,
                           check=True, capture_output=True)
            repro = receiver / "ml/results/week4-receiver-repro"
            repro_anchor = export(receiver, repro, compiler)
            verify(repro, receiver, repro_anchor, compiler)
            compare_reproduction(output, repro)
            run("receiver_test_week4", [receiver / "ml/scripts/test_week4.py", "--repo-root", receiver,
                                       "--output-dir", receiver / OUTPUT, "--expected-manifest-sha256", anchor,
                                       "--compiler", compiler], cwd=receiver)
            write_json(evidence / "receiver_checks.json", {
                "status": "PASS", "dataset_available": False, "duplicate_checkpoint_available": False,
                "docx_available": False, "crlf_production_verify": "PASS", "source_corruption_rejected": True,
                "different_branch_reproduction": "PASS", "fixes_committed": False,
                "checkout_kind": "Fresh local clone with reviewed source overlays; committed-fix gate pending"})
        archive.parent.mkdir(parents=True, exist_ok=True)
        members = [p for directory in (repo / W3_PATH, output) for p in directory.rglob("*") if p.is_file()]
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(members):
                z.write(p, p.relative_to(repo).as_posix())
        with tempfile.TemporaryDirectory(prefix="week4_zip_") as tmp:
            with zipfile.ZipFile(archive) as z:
                need(z.testzip() is None, "ZIP integrity failed")
                z.extractall(tmp)
            for p in members:
                need(sha(Path(tmp) / p.relative_to(repo)) == sha(p), "Extracted ZIP bytes differ")
        receipt = {"status": "LOCAL_RELEASE_PASS_RECEIVER_ACCEPTANCE_PENDING",
                   "week4_manifest_sha256": anchor, "week3_manifest_sha256": W3_SHA,
                   "archive_path": archive.relative_to(repo).as_posix(), "archive_sha256": sha(archive),
                   "archive_size_bytes": archive.stat().st_size,
                   "files": [{"path": p.relative_to(repo).as_posix(), "sha256": sha(p),
                              "file_size_bytes": p.stat().st_size} for p in sorted(members)],
                   "receipt_policy": "Authenticate this receipt through trusted checkout/channel, never from the received ZIP",
                   "sv1_delivery_confirmed": False, "committed_fix_checkout_gate": "PENDING",
                   "historical_files_unchanged": before == preserved()}
        need(receipt["historical_files_unchanged"], "Historical package/firmware bytes changed")
        write_json(evidence / "deliverables.json", receipt)
        write_json(evidence / "historical_integrity.json", before)
        write_json(evidence / "summary.json", {"status": "PASS", "commands": records,
                   "manifest_sha256": anchor, "historical_files_unchanged": True,
                   "limitations": ["Fixes not committed; committed checkout must be rechecked", "SV1 receipt pending",
                                   "Alternate compiler version simulated in regression; local GCC actually executed"]})
        print(json.dumps({"status": receipt["status"], "archive": str(archive), "manifest_sha256": anchor}, indent=2))
    except Exception as exc:
        write_json(evidence / "summary.json", {"status": "FAIL", "error": str(exc), "commands": records,
                                               "historical_files_unchanged": before == preserved()})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    release(args.repo_root, args.compiler)