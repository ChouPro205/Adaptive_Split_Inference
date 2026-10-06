"""Package v2 and verify its exact snapshot through Git checkout and patch."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile
from review_validation import BASE, PREFIX, REV, EXAMPLE, EXAMPLE_SHA, digest, save, collect, transfer_names, check_receipts

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
archive = root / "SV3_LINUX_FP32_REVIEW_v2.zip"
sidecar = root / "SV3_LINUX_FP32_REVIEW_v2.validation.json"
if archive.exists() or sidecar.exists(): raise SystemExit("Review v2 output exists; refusing to overwrite")
before = json.loads((out / "before.json").read_bytes())
env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
events = []


def git(cwd, *args, stdin=None):
    argv = ["git", "-c", "core.safecrlf=false", *args]
    r = subprocess.run(argv, cwd=cwd, env=env, input=stdin, capture_output=True)
    event = {"argv": argv, "cwd": str(cwd), "exit_code": r.returncode,
             "stdout_sha256": digest(r.stdout), "stderr": r.stderr.decode(errors="replace")}
    if args and "diff" in args and "--cached" in args:
        event["stdout_member"] = "_review/diff_vs_415d534.patch"
    else: event["stdout"] = r.stdout.decode(errors="replace")
    if stdin is not None: event["stdin_pathspecs"] = stdin.decode().strip("\0").split("\0")
    events.append(event)
    if r.returncode: raise RuntimeError(r.stderr.decode(errors="replace"))
    return r.stdout


paths = collect(root)
payload = {n: (root / n).read_bytes() for n in paths}
names = transfer_names(root)
assert set(names) <= set(paths)
original_index = digest((root / ".git/index").read_bytes())
tracked_before = git(root, "diff", "--binary", "--full-index", BASE, "--")
cached_before = git(root, "diff", "--cached", "--binary", "--full-index", "--")
status = git(root, "status", "--short", "--untracked-files=all")
receipts = check_receipts(root, before)
for name, row in before["artifact_and_old_archive_files"].items():
    p = root / name
    assert p.stat().st_size == row["size_bytes"] and digest(p.read_bytes()) == row["sha256"], name
package = "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
manifest = json.loads(payload[package + "/manifest.json"])
assert digest(payload[package + "/manifest.json"]) == "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
package_paths = {n for n in paths if n.startswith(package + "/")}
assert package_paths == {package + "/manifest.json"} | {package + "/" + r["path"] for r in manifest["files"]}
for row in manifest["files"]:
    raw = payload[package + "/" + row["path"]]
    assert len(raw) == row["size_bytes"] and digest(raw) == row["sha256"], row["path"]
for name in paths:
    assert not any(part in (".git", ".venv", "venv", "__pycache__", "datasets", "data") for part in Path(name).parts), name
    assert "week5" not in name, name
    assert not name.endswith(".zip"), name
# Validate new outer run records too, including both expected nonzero failures.
for p in out.glob("*.command.json"):
    r = json.loads(p.read_bytes())
    for stream in r["streams"].values():
        assert digest((out / stream["path"]).read_bytes()) == stream["sha256"]
    for name, expected in r["source_sha256"].items():
        assert digest(payload[name]) == expected, name
validation = {"base_commit": BASE, "raw_provenance_example_sha256": EXAMPLE_SHA,
              "historical_crlf_files_retained": 61, "historical_receipts": receipts,
              "artifact_v1_and_old_review_archive_unchanged": True,
              "new_recipe": {"status": "PASS", "completed_steps_before_receipt": 27,
                             "failure_fixtures": json.loads((out / "failure_fixtures.json").read_bytes())["results"]}}
with tempfile.TemporaryDirectory(prefix="asi_final_review_v2_") as tmp:
    task = Path(tmp).resolve()
    assert Path(tempfile.gettempdir()).resolve() in task.parents
    index_repo, checkout, applied = task / "index_repo", task / "checkout", task / "patch_repo"
    git(task, "clone", "--no-hardlinks", "--no-checkout", str(root), str(index_repo))
    git(index_repo, "-c", "core.autocrlf=false", "checkout", "--detach", BASE)
    for name in names:
        p = index_repo / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(payload[name])
    attr = git(index_repo, "check-attr", "text", "eol", "--", EXAMPLE, "ml/provenance/week4-r4/commands.json")
    git(index_repo, "-c", "core.autocrlf=true", "add", "--force", "--pathspec-from-file=-", "--pathspec-file-nul",
        stdin=("\0".join(names) + "\0").encode())
    indexed = git(index_repo, "show", ":" + EXAMPLE)
    assert digest(indexed) == EXAMPLE_SHA
    tree = git(index_repo, "write-tree").decode().strip()
    checkout.mkdir()
    git(index_repo, "-c", "core.autocrlf=true", "checkout-index", "--all", "--prefix=" + checkout.as_posix() + "/")
    for name in names: assert (checkout / name).read_bytes() == payload[name], name
    checkout_receipts = check_receipts(checkout, before)
    patch = git(index_repo, "diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", BASE, "--")
    patch_file = task / "full.patch"; patch_file.write_bytes(patch)
    git(task, "clone", "--no-hardlinks", "--no-checkout", str(root), str(applied))
    git(applied, "-c", "core.autocrlf=false", "checkout", "--detach", BASE)
    git(applied, "apply", "--binary", "--whitespace=nowarn", str(patch_file))
    for name in names: assert (applied / name).read_bytes() == payload[name], name
    patch_receipts = check_receipts(applied, before)
    validation.update({"git_checkout": {"status": "PASS", "byte_equal_files": len(names), "index_tree": tree,
                      "example_sha256": digest((checkout / EXAMPLE).read_bytes()), "receipts": checkout_receipts},
                      "patch_apply": {"status": "PASS", "byte_equal_files": len(names), "sha256": digest(patch),
                      "example_sha256": digest((applied / EXAMPLE).read_bytes()), "receipts": patch_receipts},
                      "check_attr": attr.decode()})
payload["_review/diff_vs_415d534.patch"] = patch
payload["_review/git_status.txt"] = status
payload["_review/fix_files.json"] = (json.dumps({"base_commit": BASE, "transfer_paths": names,
        "context_and_package_paths": sorted(set(paths)-set(names)),
        "byte_verification_scope": "All fix/provenance and receipt-referenced source/requirements; immutable package authenticated separately",
        "existing_LF_context_policy_exclusions": ["ml/configs/week4_requirement_references.json", "ml/manifests/mitdb_patient_split.csv"]}, indent=2) + "\n").encode()
readme = '''# SV3 Linux FP32 review v2

Read docs/sv3_ml_week3_linux_fp32_review_v2_report.md, then the original fix report.
Current uncommitted source on base 415d53431c81c465784dc08be42b568827a39cff.
No main-worktree index change, commit, push, merge or release.

Git attributes preserve raw provenance bytes. Full patch was built from an isolated
index with current attributes and ACTUALLY applied to a clean base clone; resulting
files and historical/new receipts were checked. Final commands/results are in
_review/git_transfer_commands.json and _review/transfer_validation.json.
The patch includes untracked files and binary logs, plus .gitattributes.

Old provenance/receipts remain byte-identical. Resolve the historical recipe hash
using review-v2/source-before/ml/scripts/reproduce_week3_sv2_linux.sh, not today's
root script. New-run receipt is review-v2/recipe_success/receipt.json. Metadata/scope
of the old archive are retained under review-v2, without embedding its duplicate ZIP.

Overlay this archive onto a separate clean clone at base 415d534; then run:
    bash ml/scripts/reproduce_week3_sv2_linux.sh
The script requires a Git checkout for source logging. It creates its own Linux
venv, logs setup/download/auth and all SV2 gates, refuses an existing wrong Python
version, and emits a new receipt. Use a NEW ASI_LINUX_LOG_ROOT for each run.
Use current root ml/scripts, not historical scripts inside package v1.

The full immutable v1 package (41 files) is included, no duplicate v1 ZIP. No raw
dataset, venv or .git is included. Historical SV1/R4 full-device/data gates are
outside this rerun bundle; their existing FAIL/SKIP/PENDING evidence remains intact.
The two intermediate v1 records still refer to a deleted temporary policy module;
this historical source gap is unchanged, not filled with invented source.

_review/file_inventory.json authenticates each member except itself; the externally
provided ZIP SHA authenticates the complete archive. Byte-transfer equality covers
every fix/provenance/receipt-pinned input. Unchanged auxiliary R4 context still uses
the existing LF Git policy; its raw working-copy bytes are preserved in the ZIP for
context, not treated as new fix files. Scientific package hashes are checked separately.

PASS is author-machine portable-fp32-v2 only. bitwise-v1 remains default; s9 strict
<1e-5 and logits/ORT strict <1e-3. Recipient SV2 acceptance is still pending.
'''
payload["_review/README.md"] = readme.encode()
local_links = []
for report in ("docs/sv3_ml_week3_linux_fp32_fix_report.md", "docs/sv3_ml_week3_linux_fp32_review_v2_report.md"):
    for target in re.findall(r"\]\(([^)]+)\)", payload[report].decode()):
        if target.startswith(("https:", "http:")): continue
        name = (root / Path(report).parent / target).resolve().relative_to(root).as_posix().rstrip("/")
        assert name in payload or any(n.startswith(name + "/") for n in payload), name
        local_links.append(name)
validation["report_links_present"] = sorted(set(local_links))
validation["original_index_unchanged"] = original_index == digest((root / ".git/index").read_bytes())
assert validation["original_index_unchanged"]
assert tracked_before == git(root, "diff", "--binary", "--full-index", BASE, "--")
assert cached_before == git(root, "diff", "--cached", "--binary", "--full-index", "--")
assert all((root / n).read_bytes() == raw for n,raw in payload.items() if not n.startswith("_review/"))
payload["_review/git_transfer_commands.json"] = (json.dumps(events, indent=2) + "\n").encode()
payload["_review/transfer_validation.json"] = (json.dumps(validation, indent=2) + "\n").encode()
inventory = [{"path": n, "size_bytes": len(b), "sha256": digest(b)} for n,b in sorted(payload.items())]
payload["_review/file_inventory.json"] = (json.dumps({"self_hash_excluded": "_review/file_inventory.json", "files": inventory}, indent=2) + "\n").encode()
with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
    for name, raw in sorted(payload.items()):
        info = zipfile.ZipInfo(name); info.create_system = 3
        info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        zipped.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
with zipfile.ZipFile(archive) as zipped:
    assert zipped.testzip() is None
    assert len(zipped.namelist()) == len(set(zipped.namelist())) == len(payload)
    assert set(zipped.namelist()) == set(payload)
    for name, raw in payload.items(): assert zipped.read(name) == raw, name
    for row in inventory:
        raw = zipped.read(row["path"])
        assert len(raw) == row["size_bytes"] and digest(raw) == row["sha256"]
result = {"archive": str(archive), "size_bytes": archive.stat().st_size, "sha256": digest(archive.read_bytes()),
          "member_count": len(payload), "zip_crc_inventory_all_bytes_sha_size": "PASS", **validation,
          "source_and_historical_files_not_mutated_by_packaging": True,
          "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
save(sidecar, result)
print(json.dumps({k:result[k] for k in ("archive", "size_bytes", "sha256", "member_count", "zip_crc_inventory_all_bytes_sha_size", "git_checkout", "patch_apply", "original_index_unchanged")}, indent=2))
