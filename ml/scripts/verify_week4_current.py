"""Verify today's checkout and the unchanged R4 scientific release separately.

The current gate checks every current binding through the same policy as SV1.
The numerical engine runs from its authenticated fixed R4 source commit, never
from an overlay of unverified current code. The original verifier stays intact.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from week4_handoff_auth import (R4, R4_MANIFEST, PACKAGE, SOURCE_COMMITS,
                               authenticate_handoff, authenticated_json,
                               bound_path, check_sources, source_hash, sha256)


def historical_source_view(repo: Path, view: Path) -> dict:
    """Materialize exactly one pinned release engine, with no source overlay."""
    if view.exists():
        raise ValueError("Historical source view exists; refuse overwrite")
    manifest = authenticated_json(repo / R4 / "manifest.json", R4_MANIFEST)
    check_sources(repo, manifest, "r4", historical=True)
    commit = SOURCE_COMMITS["r4"]
    names = subprocess.check_output([
        "git", "ls-tree", "-r", "--name-only", commit, "--", "ml/scripts", "ml/src"
    ], cwd=repo, text=True).splitlines()
    names = sorted(set(names) | {row["path"] for row in manifest["source_files"]})
    hashes = {}
    for name in names:
        raw = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo)
        target = bound_path(view, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[name] = source_hash(raw)
    for row in manifest["source_files"]:
        if (hashes[row["path"]] != row["sha256"] or
                source_hash(bound_path(view, row["path"]).read_bytes()) != row["sha256"]):
            raise ValueError(f"Historical engine source mismatch: {row['path']}")
    # Reproduction tests read Git metadata. Give this temporary source view a
    # detached fixed HEAD and read-only access to the existing object store;
    # do not substitute the active checkout's HEAD or modify its refs/index.
    common = Path(subprocess.check_output([
        "git", "rev-parse", "--path-format=absolute", "--git-common-dir"
    ], cwd=repo, text=True).strip())
    info = view / ".git/objects/info"
    info.mkdir(parents=True)
    (view / ".git/refs").mkdir()
    (info / "alternates").write_text((common / "objects").as_posix() + "\n", encoding="utf-8")
    (view / ".git/HEAD").write_text(commit + "\n", encoding="ascii")
    (view / ".git/config").write_text("[core]\nrepositoryformatversion = 0\nbare = false\n", encoding="ascii")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=view, text=True).strip() != commit:
        raise ValueError("Historical source view Git identity differs")
    # Caller authenticates every package member before this copy. The legacy
    # engine authenticates the copied package again against its original anchor.
    shutil.copytree(repo / PACKAGE, view / PACKAGE)
    return {"source_commit": commit, "historical_source_bindings_checked": len(manifest["source_files"]),
            "source_sha256": hashes, "current_checkout_is_historical_snapshot": False,
            "source_view_head": commit}


def run_historical_engine(repo: Path, view: Path, compiler: str, *, regressions: bool = False) -> dict:
    script = "test_week4.py" if regressions else "verify_week4.py"
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    args = [sys.executable, "-B", *(["-O"] if sys.flags.optimize else []),
            str(view / "ml/scripts" / script), "--repo-root", str(view),
            "--output-dir", str(repo / R4), "--expected-manifest-sha256", R4_MANIFEST,
            "--compiler", compiler]
    result = subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError(f"Authenticated historical {script} failed (exit {result.returncode}):\n"
                         + result.stdout + result.stderr)
    if regressions:
        if "WEEK4_TESTS_PASS: 21 expected rejections" not in result.stdout:
            raise ValueError("Historical regression coverage incomplete")
        return {"status": "PASS", "command": args, "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    report = json.loads(result.stdout)
    if report.get("status") != "WEEK4_CHECKS_PASS" or report.get("golden_cases_bitwise") != 220:
        raise ValueError("Historical numerical engine coverage incomplete")
    return report


def verify(repo: Path, expected_manifest_sha256: str = R4_MANIFEST, compiler: str = "gcc",
           source_mode: str = "current", *, regressions: bool = False) -> dict:
    repo = Path(repo).resolve()
    # Mandatory before execution: current source tampering, partial PR22 updates
    # and payload drift must stop here even if the old numerical engine passes.
    _, _, authentication = authenticate_handoff(repo, "r4", expected_manifest_sha256,
                                               source_mode=source_mode)
    with tempfile.TemporaryDirectory(prefix="authenticated-r4-engine-") as temp:
        view = Path(temp) / "source"
        engine = historical_source_view(repo, view)
        numerical = run_historical_engine(repo, view, compiler, regressions=regressions)
    tooling = {"ml/scripts/verify_week4_current.py": sha256(Path(__file__)),
               "tools/week4_handoff_auth.py": sha256(ROOT / "tools/week4_handoff_auth.py")}
    return {"status": "WEEK4_CURRENT_CHECKS_PASS" if source_mode == "current" else "WEEK4_HISTORICAL_CHECKS_PASS",
            "scope": "AUTHENTICATED_CURRENT_SOURCE_AND_R4_RELEASE" if source_mode == "current" else "PINNED_R4_SNAPSHOT_ONLY",
            "source_mode": source_mode, "manifest_sha256": R4_MANIFEST,
            "handoff_authentication": authentication, "historical_numerical_engine": engine,
            "numerical_verification": numerical, "verification_tooling_sha256": tooling,
            "verification_tooling_role": "Reviewed current tooling; never relabelled as release generation source",
            "optimized_python": bool(sys.flags.optimize)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--expected-manifest-sha256", default=R4_MANIFEST)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--source-mode", choices=("current", "historical"), default="current")
    parser.add_argument("--regressions", action="store_true", help="Run the unchanged historical ML Week 4 regression suite")
    args = parser.parse_args()
    print(json.dumps(verify(args.repo_root, args.expected_manifest_sha256, args.compiler,
                            args.source_mode, regressions=args.regressions), indent=2))
