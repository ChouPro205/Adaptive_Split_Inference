"""Release a NEW Week 4 revision from committed source; authenticate ZIP hydration."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

from week3_common import need, read_json, safe_path, sha, text, write_json
from week3_sv2_common import SV1_MANIFEST, authenticate
from week4_common import W3_PATH, W3_SHA, compare_reproduction, source_sha


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def hydrate(repo, archive, expected_sha256, expected_size, files):
    """Add authenticated artifacts only; existing checkout bytes must already match."""
    repo, archive = Path(repo).resolve(), Path(archive).resolve()
    need(sha(archive) == expected_sha256 and archive.stat().st_size == expected_size,
         "Release ZIP hash/size mismatch")
    rows = {row["path"]: row for row in files}
    need(len(rows) == len(files), "Duplicate release inventory paths")
    with zipfile.ZipFile(archive) as zipped:
        need(len(zipped.namelist()) == len(rows) and set(zipped.namelist()) == set(rows),
             "Release ZIP inventory differs")
        for name, row in rows.items():
            target = safe_path(repo, name)
            lexical = repo / name
            need(not any(p.is_symlink() for p in (lexical, *lexical.parents)),
                 f"Artifact symlink forbidden: {name}")
            raw = zipped.read(name)
            need(hashlib.sha256(raw).hexdigest() == row["sha256"]
                 and len(raw) == row["file_size_bytes"], f"ZIP member differs: {name}")
            if target.exists():
                need(target.is_file() and target.read_bytes() == raw,
                     f"Existing checkout artifact differs; refusing overwrite: {name}")
        # All members and existing targets passed authentication before any write.
        for name in rows:
            target = safe_path(repo, name)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(name))


def release(repo, compiler, revision="r3"):
    repo = Path(repo).resolve()
    need(re.fullmatch(r"r[1-9][0-9]*", revision) is not None, "Invalid release revision")
    evidence = repo / f"ml/provenance/week4-{revision}"
    output_path = f"ml/results/week4-{revision}"
    output = repo / output_path
    archive = repo / f"ml/artifacts/week4/mitdb-sv1-week4-fp32-20261001-{revision}.zip"
    need(not evidence.exists() and not output.exists() and not archive.exists(),
         "Release revision exists; preserve it and choose a new revision")
    need(not git(repo, "status", "--porcelain", "--untracked-files=all", "--",
                 "ml/scripts", "ml/src", "ml/configs", "ml/manifests", "contracts"),
         "Release source must be committed and clean")
    commit = git(repo, "rev-parse", "HEAD")
    evidence.mkdir(parents=True)
    records = []
    protected = [repo / name for name in ("ml/artifacts/week3", "ml/results/week4",
                 "ml/results/week4-r2", "ml/provenance/week4-r2", "device", "results/week3")]

    def preserved():
        return {p.relative_to(repo).as_posix(): sha(p) for directory in protected
                for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                and not any(part.startswith("build") for part in p.relative_to(repo).parts)}

    before = preserved()

    def run(name, args, cwd=repo, python=True):
        command = ([sys.executable, "-B"] if python else []) + list(map(str, args))
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        log = evidence / f"{name}.txt"
        text(log, result.stdout + result.stderr)
        records.append({"name": name, "command": command, "cwd": str(cwd),
                        "commit_sha": git(cwd, "rev-parse", "HEAD"), "exit_status": result.returncode,
                        "log_path": log.relative_to(repo).as_posix(), "log_sha256": sha(log)})
        write_json(evidence / "commands.json", records)
        print(f"{name}: exit={result.returncode}", flush=True)
        need(result.returncode == 0, f"Gate failed: {name}; see {log}")

    def week4_gates(prefix, checkout, anchor):
        for name in ("verify_week4", "test_week4"):
            run(prefix + name, [checkout / f"ml/scripts/{name}.py", "--repo-root", checkout,
                "--output-dir", checkout / output_path, "--expected-manifest-sha256", anchor,
                "--compiler", compiler], cwd=checkout)

    try:
        for name in ("verify_week3_sv2", "test_week3_sv2"):
            run(name, [f"ml/scripts/{name}.py", "--package", W3_PATH,
                       "--expected-manifest-sha256", W3_SHA])
        run("test_week3_sv2_cache", ["ml/scripts/test_week3_sv2_cache.py"])
        run("test_week4_release", ["ml/scripts/test_week4_release.py"])
        sv1 = "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
        run("verify_week3", ["ml/scripts/verify_week3.py", "--repo-root", ".", "--package", sv1,
                            "--expected-manifest-sha256", SV1_MANIFEST, "--compiler", compiler])
        run("test_week3", ["ml/scripts/test_week3.py", "--repo-root", ".", "--package", sv1,
                          "--expected-manifest-sha256", SV1_MANIFEST])
        run("profile_week4", ["ml/scripts/profile_week4.py", "--repo-root", ".",
                              "--output-dir", output_path, "--compiler", compiler])
        anchor = sha(output / "manifest.json")
        manifest = read_json(output / "manifest.json")
        need(manifest["source_git_commit"] == commit, "Wrong generating source commit")
        for row in manifest["source_files"]:
            blob = subprocess.check_output(["git", "show", f"{commit}:{row['path']}"], cwd=repo)
            digest = hashlib.sha256(blob.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode()).hexdigest()
            need(digest == row["sha256"], f"Release source is not committed: {row['path']}")
        week4_gates("", repo, anchor)
        w3 = authenticate(repo / W3_PATH, W3_SHA)
        members = [repo / W3_PATH / row["path"] for row in w3["files"]]
        members += [repo / W3_PATH / "manifest.json"]
        members += [output / row["path"] for row in manifest["files"]] + [output / "manifest.json"]
        files = [{"path": p.relative_to(repo).as_posix(), "sha256": sha(p),
                  "file_size_bytes": p.stat().st_size} for p in sorted(members)]
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
            for p in sorted(members):
                zipped.write(p, p.relative_to(repo).as_posix())
        receipt = {"revision": revision, "status": "LOCAL_RELEASE_PASS_RECEIVER_ACCEPTANCE_PENDING",
                   "generation_commit_sha": commit, "source_commit_sha": commit,
                   "week4_manifest_sha256": anchor, "week3_manifest_sha256": W3_SHA,
                   "archive_path": archive.relative_to(repo).as_posix(), "archive_sha256": sha(archive),
                   "archive_size_bytes": archive.stat().st_size, "files": files,
                   "receipt_policy": "Authenticate through trusted checkout/channel, never through the received ZIP alone",
                   "sv1_delivery_confirmed": False, "committed_fix_checkout_gate": "PENDING"}
        write_json(evidence / "deliverables.json", receipt)
        with tempfile.TemporaryDirectory(prefix=f"week4_{revision}_checkout_") as tmp:
            checkout = Path(tmp) / "checkout"
            run("receiver_clone", ["git", "clone", "--local", "--no-hardlinks", str(repo), str(checkout)], python=False)
            run("receiver_checkout", ["git", "checkout", "--detach", commit], cwd=checkout, python=False)
            need(git(checkout, "rev-parse", "HEAD") == commit, "Receiver commit mismatch")
            need(not git(checkout, "status", "--porcelain"), "Receiver checkout not clean")
            hydrate(checkout, archive, receipt["archive_sha256"], receipt["archive_size_bytes"], files)
            week4_gates("receiver_", checkout, anchor)
            for name in ("verify_week3_sv2", "test_week3_sv2"):
                run("receiver_" + name, [checkout / f"ml/scripts/{name}.py", "--package", checkout / W3_PATH,
                    "--expected-manifest-sha256", W3_SHA], cwd=checkout)
            run("receiver_test_week3_sv2_cache", [checkout / "ml/scripts/test_week3_sv2_cache.py"], cwd=checkout)
            run("receiver_reproduction", [checkout / "ml/scripts/profile_week4.py", "--repo-root", checkout,
                "--output-dir", checkout / "ml/results/week4-receiver-repro", "--compiler", compiler], cwd=checkout)
            repro = checkout / "ml/results/week4-receiver-repro"
            run("receiver_verify_reproduction", [checkout / "ml/scripts/verify_week4.py", "--repo-root", checkout,
                "--output-dir", repro, "--expected-manifest-sha256", sha(repro / "manifest.json"),
                "--compiler", compiler], cwd=checkout)
            compare_reproduction(output, repro)
            for row in manifest["source_files"]:
                need(source_sha(checkout / row["path"]) == row["sha256"], "Receiver source changed")
            need(not git(checkout, "diff", "HEAD") and not git(checkout, "ls-files", "--others", "--exclude-standard", "ml/scripts"),
                 "Receiver tracked files/source changed")
            write_json(evidence / "receiver_checks.json", {"status": "PASS", "commit_sha": commit,
                "checkout_kind": "Pinned committed checkout; artifacts from authenticated release ZIP only",
                "no_source_overlay": True, "tracked_files_unchanged": True,
                "scientific_reproduction": "PASS", "dataset_available": False,
                "duplicate_checkpoint_available": False, "docx_available": False, "sv1_delivery": "PENDING"})
        receipt.update(committed_fix_checkout_gate="PASS", historical_files_unchanged=before == preserved())
        need(receipt["historical_files_unchanged"], "Historical package/firmware bytes changed")
        write_json(evidence / "deliverables.json", receipt)
        write_json(evidence / "historical_integrity.json", before)
        write_json(evidence / "summary.json", {"status": "PASS", "revision": revision,
                   "generation_commit_sha": commit, "commands": records, "manifest_sha256": anchor,
                   "historical_files_unchanged": True, "no_source_overlay": True,
                   "limitations": ["SV1 destination and receiver acknowledgement pending",
                     "Week 3 SV1 raw-data regression ran on generating committed checkout; receiver Week 4 needs no dataset"]})
        print(json.dumps({"status": receipt["status"], "archive": str(archive), "manifest_sha256": anchor}, indent=2))
    except Exception as exc:
        write_json(evidence / "summary.json", {"status": "FAIL", "revision": revision,
                   "generation_commit_sha": commit, "error": str(exc), "commands": records,
                   "historical_files_unchanged": before == preserved()})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--revision", default="r3")
    args = parser.parse_args()
    release(args.repo_root, args.compiler, args.revision)
