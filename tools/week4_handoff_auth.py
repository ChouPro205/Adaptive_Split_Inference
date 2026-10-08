"""Shared device/ML authentication of current source and immutable R3/R4 assets.

R3 evidence is never relabelled. R4 compatibility requires both pinned source
bindings and byte-identical payloads; historical blobs are checked, not run.
The three reviewed PR22 verifier sources form one explicit current-R4 update.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

WEEK4_MANIFEST = "80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c"
R4_MANIFEST = "3ca39030081c6b53a5191f927ead6fdc84cdeba1c69766bbdbc9f1cb9ca3d49a"
ALL_SPLIT_MANIFEST = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
PACKAGE = "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
R3 = "ml/results/week4-r3"
R4 = "ml/results/week4-r4"
SOURCE_COMMITS = {"r3": "c793c06385198accc964e0e60988d7e7a7e9b566",
                  "r4": "89109fd352d84a5fe0815d7e045e52538de7bad8"}
SOURCE_ANCHORS = {"r3": WEEK4_MANIFEST, "r4": R4_MANIFEST}
PR22_SOURCE_COMMIT = "add8503d58c6f707a35b4502bf98aff91109c1cd"
PR22_MERGE_COMMIT = "e6d3e8cc40323227d0f15a4bb4091957f2498744"
# Independently checked against SOURCE_COMMITS['r4'], PR22_SOURCE_COMMIT and
# PR22_MERGE_COMMIT. Tuples bind (original R4 hash, reviewed PR22 hash) per path.
# The immutable R4 manifest and all other source/payload bindings stay strict.
PR22_R4_SOURCE_HASHES = {
    "ml/scripts/verify_week3_sv2.py": (
        "b4c9562ee74c4922fd6180bc9a1a85ffc8a44871fd45ed87610728f2e31230ce",
        "c783c81a12439618c3ede435b495f7a2e605bc216dc9efa1fe04ecc9f35e31cb"),
    "ml/scripts/test_week3_sv2.py": (
        "c6bad027185bf63c280dc9abc2c9e9a96d809eabd6e42853a7b2cbd732b7fda6",
        "215e11a614986cd2fbacb67ac8ed2fd4711e8525180cfab28a5a8ec176ec7041"),
    "ml/scripts/test_week3_sv2_cache.py": (
        "9c7a2b6cdba237145ad127a45e5938e7d657b20caa1faaafbf7f5e885232b9b4",
        "7d448049234882f159401d0d1d5dfc703309d207730d01d4661a9c51bdb87f0f"),
}
ACCEPTED_R3_REPORT_SHA256 = "4a0342593270485b409465741a6c555659dc98b541c277b264d9727da4605a4d"
# The report committed at efc0af72aeae3ef6ff872ad3cae19e6304899530 is LF.
# Converting only its LF bytes to CRLF reproduces the original Windows pin.
# These two independently verified raw hashes apply only to this R3 report.
ACCEPTED_R3_REPORT_LF_SHA256 = "022a5172edd75c60826d27db16761df9d5236caaa1cad312c14ce59c1dd5ab21"
ACCEPTED_R3_REPORT_HASHES = frozenset({ACCEPTED_R3_REPORT_SHA256, ACCEPTED_R3_REPORT_LF_SHA256})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authenticated_json(path: Path, expected: str) -> dict:
    if sha256(path) != expected:
        raise ValueError(f"Manifest anchor mismatch: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def bound_path(root: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    if parts.is_absolute() or ".." in parts.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe binding path: {name}")
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Binding escapes root: {name}")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Binding symlink forbidden: {name}")
    return path


def check_file(path: Path, entry: dict) -> None:
    size = entry.get("file_size_bytes", entry.get("size_bytes"))
    if (size is not None and path.stat().st_size != size) or sha256(path) != entry["sha256"]:
        raise ValueError(f"Pinned file mismatch: {path}")


def source_hash(raw: bytes) -> str:
    # Same sha256-utf8-lf-v1 policy as the authenticated ML manifests.
    return hashlib.sha256(raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def check_sources(repo: Path, manifest: dict, revision: str, *, historical: bool) -> list[dict]:
    if revision not in SOURCE_COMMITS or manifest["source_git_commit"] != SOURCE_COMMITS[revision]:
        raise ValueError("Unsupported revision/source commit binding")
    if manifest["source_hash_policy"] != "sha256-utf8-lf-v1":
        raise ValueError("Unsupported source hash policy")
    seen = set()
    updates = []
    for entry in manifest["source_files"]:
        name = entry["path"]
        path = bound_path(repo, name)
        if name in seen:
            raise ValueError(f"Duplicate source binding: {name}")
        seen.add(name)
        if historical:
            # The commit is fixed by both the trusted manifest and our revision
            # binding. Never substitute HEAD or fall back to current source.
            raw = subprocess.check_output(["git", "show", f"{SOURCE_COMMITS[revision]}:{name}"], cwd=repo)
        else:
            raw = path.read_bytes()
        actual = source_hash(raw)
        reviewed = PR22_R4_SOURCE_HASHES.get(name)
        if revision == "r4" and reviewed is not None and entry["sha256"] != reviewed[0]:
            raise ValueError(f"Unsupported verified source update binding: {name}")
        if actual != entry["sha256"]:
            if (revision == "r4" and not historical
                    and reviewed == (entry["sha256"], actual)):
                updates.append({"path": name, "r4_manifest_sha256": entry["sha256"],
                                "current_source_sha256": actual,
                                "reviewed_source_commit": PR22_SOURCE_COMMIT,
                                "reviewed_merge_commit": PR22_MERGE_COMMIT})
                continue
            mode = "historical" if historical else "current"
            raise ValueError(f"Pinned ML source mismatch ({revision} {mode}): {name}")
    if updates and {row["path"] for row in updates} != set(PR22_R4_SOURCE_HASHES):
        raise ValueError("Incomplete verified PR22 source update")
    return updates


def check_payload_parity(repo: Path, r3: dict, r4: dict) -> int:
    # Only source provenance may differ. Every scientific field, reused-file
    # binding, dependency pin and payload inventory must remain identical.
    def science(manifest):
        return {k: v for k, v in manifest.items() if k not in ("source_git_commit", "source_files")}
    if science(r3) != science(r4):
        raise ValueError("R3/R4 scientific bindings differ")
    if [e["path"] for e in r3["source_files"]] != [e["path"] for e in r4["source_files"]]:
        raise ValueError("Unsupported R3/R4 source binding inventory")
    for entry in r3["files"]:
        left = bound_path(repo / R3, entry["path"])
        right = bound_path(repo / R4, entry["path"])
        check_file(left, entry)
        check_file(right, entry)
        if left.read_bytes() != right.read_bytes():
            raise ValueError(f"R3/R4 payload bytes differ: {entry['path']}")
    return len(r3["files"])


def authenticate_handoff(repo: Path, source_revision: str = "r4",
                         expected_source_anchor: str | None = None, *,
                         source_mode: str = "current") -> tuple[dict, dict, dict]:
    if source_mode not in ("current", "historical"):
        raise ValueError(f"Unsupported source verification mode: {source_mode}")
    if source_revision not in SOURCE_ANCHORS:
        raise ValueError(f"Unsupported source revision: {source_revision}")
    anchor = SOURCE_ANCHORS[source_revision]
    if expected_source_anchor is not None and expected_source_anchor != anchor:
        raise ValueError("Source trust anchor differs from the supported revision")
    r3 = authenticated_json(repo / R3 / "manifest.json", WEEK4_MANIFEST)
    splits = authenticated_json(repo / PACKAGE / "manifest.json", ALL_SPLIT_MANIFEST)
    for entry in r3["files"]:
        check_file(bound_path(repo / R3, entry["path"]), entry)
    for entry in splits["files"]:
        check_file(bound_path(repo / PACKAGE, entry["path"]), entry)
    for entry in r3["reused_files"]:
        check_file(bound_path(repo, entry["path"]), entry)
    check_sources(repo, r3, "r3", historical=True)
    payload_count = 0
    current = r3
    if source_revision == "r4":
        current = authenticated_json(repo / R4 / "manifest.json", R4_MANIFEST)
        payload_count = check_payload_parity(repo, r3, current)
    updates = check_sources(repo, current, source_revision, historical=source_mode == "historical")
    proof = {"firmware_payload_revision": "r3", "firmware_manifest_sha256": WEEK4_MANIFEST,
             "source_verification_mode": source_mode,
             "historical_r3_source_commit": SOURCE_COMMITS["r3"],
             "historical_r3_source_bindings_checked": len(r3["source_files"]),
             "r3_r4_identical_payload_files": payload_count,
             "all_split_manifest_sha256": ALL_SPLIT_MANIFEST,
             "verified_current_source_updates": updates}
    if source_mode == "current":
        proof.update(current_source_revision=source_revision, current_source_manifest_sha256=anchor,
                     current_source_bindings_checked=len(current["source_files"]))
    else:
        proof.update(historical_source_revision=source_revision, historical_source_manifest_sha256=anchor,
                     historical_source_commit=SOURCE_COMMITS[source_revision],
                     historical_source_bindings_checked=len(current["source_files"]))
    return r3, splits, proof


def accepted_r3_provenance(repo: Path) -> dict:
    """Preserve the authenticated 02/10 report; tools may change, firmware may not."""
    report_path = repo / "results/week4/week4_mcu_validation.json"
    report_bytes = report_path.read_bytes()
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    if report_sha256 not in ACCEPTED_R3_REPORT_HASHES:
        raise ValueError(f"Accepted R3 report anchor mismatch: {report_path}")
    accepted = json.loads(report_bytes)
    provenance = accepted["provenance"]
    if provenance["week4_manifest_sha256"] != WEEK4_MANIFEST:
        raise ValueError("Accepted MCU evidence is not R3")
    for name, expected in provenance["compiled_source_sha256"].items():
        raw = bound_path(repo, name).read_bytes()
        # Compiled sources were recorded as raw Windows checkout bytes. Permit
        # Git's LF/CRLF transport only; no source content changes are accepted.
        lf = raw.replace(b"\r\n", b"\n")
        if expected not in {hashlib.sha256(b).hexdigest() for b in (raw, lf, lf.replace(b"\n", b"\r\n"))}:
            raise ValueError(f"Accepted R3 firmware source mismatch: {name}")
    for name, expected in provenance["generated_header_sha256"].items():
        check_file(bound_path(repo / "device/generated", name), {"sha256": expected})
    binaries = {"device/build-week4/zephyr/zephyr.elf": provenance["elf_sha256"],
                "device/artifacts/adaptive_split_week4_r3_fp32.zip": provenance["dfu_zip_sha256"]}
    available = {}
    for name, expected in binaries.items():
        path = bound_path(repo, name)
        if path.exists():
            check_file(path, {"sha256": expected})
            available[name] = "MATCH"
        else:
            available[name] = "UNAVAILABLE (ignored historical binary; no new image inferred)"
    return {"accepted_report_sha256": report_sha256,
            "measurement_revision": "r3", "validated_at": provenance["validated_at"],
            "compiled_source_sha256": provenance["compiled_source_sha256"],
            "elf_sha256": provenance["elf_sha256"], "dfu_zip_sha256": provenance["dfu_zip_sha256"],
            "application_sha256": provenance["application_sha256"], "local_historical_binaries": available}
