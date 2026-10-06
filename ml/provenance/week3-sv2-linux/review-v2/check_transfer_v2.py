"""Use isolated Git indexes/checkouts, actually apply patches and compare bytes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from review_validation import BASE, PREFIX, REV, EXAMPLE, EXAMPLE_SHA, digest, save, transfer_names, check_receipts

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
before = json.loads((out / "before.json").read_bytes())
events = []
env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}


def git(cwd, *args, stdin=None):
    argv = ["git", "-c", "core.safecrlf=false", *args]
    result = subprocess.run(argv, cwd=cwd, env=env, input=stdin, capture_output=True)
    events.append({"argv": argv, "cwd": str(cwd), "exit_code": result.returncode,
                   "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace")})
    if stdin is not None:
        events[-1]["stdin_pathspecs"] = stdin.decode().strip("\0").split("\0")
    if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def copy(root_from, root_to, names):
    for name in names:
        p = root_to / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((root_from / name).read_bytes())


def compare(target, payload):
    for name, raw in payload.items():
        actual = (target / name).read_bytes()
        assert actual == raw, "Transfer changed bytes: " + name
    return {"compared_files": len(payload), "all_bytes_sha_size_equal": True,
            "example_sha256": digest((target / EXAMPLE).read_bytes())}


if sys.argv[1:] == ["--before"]:
    with tempfile.TemporaryDirectory(prefix="asi_git_before_") as tmp:
        task = Path(tmp).resolve()
        assert Path(tempfile.gettempdir()).resolve() in task.parents
        repo, clean = task / "repo", task / "checkout"
        repo.mkdir(); clean.mkdir()
        git(repo, "init", "--quiet")
        (repo / ".gitattributes").write_bytes((out / "source-before/.gitattributes").read_bytes())
        copy(root, repo, before["historical_files"])
        git(repo, "-c", "core.autocrlf=false", "add", "--all")
        indexed = git(repo, "show", ":" + EXAMPLE)
        git(repo, "-c", "core.autocrlf=false", "checkout-index", "--all", "--prefix=" + clean.as_posix() + "/")
        changed = [name for name, row in before["historical_files"].items()
                   if digest((clean / name).read_bytes()) != row["sha256"]]
        result = {"status": "REPRODUCED_PRE_FIX_NORMALIZATION", "raw_sha256": EXAMPLE_SHA,
                  "indexed_sha256": digest(indexed), "checkout_sha256": digest((clean / EXAMPLE).read_bytes()),
                  "changed_historical_files": changed, "changed_count": len(changed), "commands": events}
        assert result["checkout_sha256"] == "b0304f1c89de0dac68fe8a531e68033600f614c680e19e9429d041ec3639caaa"
        save(out / "transfer_before.json", result)
        print(json.dumps({k: v for k,v in result.items() if k not in ("commands", "changed_historical_files")}, indent=2))
else:
    names = transfer_names(root)
    payload = {n: (root / n).read_bytes() for n in names}
    original_index = digest((root / ".git/index").read_bytes())
    with tempfile.TemporaryDirectory(prefix="asi_git_after_") as tmp:
        task = Path(tmp).resolve()
        assert Path(tempfile.gettempdir()).resolve() in task.parents
        repo, clean, applied = task / "index_repo", task / "checkout", task / "patch_repo"
        git(task, "clone", "--no-hardlinks", "--no-checkout", str(root), str(repo))
        git(repo, "-c", "core.autocrlf=false", "checkout", "--detach", BASE)
        copy(root, repo, names)
        attrs = git(repo, "check-attr", "text", "eol", "--", EXAMPLE, "ml/provenance/week4-r4/commands.json")
        git(repo, "-c", "core.autocrlf=true", "add", "--force", "--pathspec-from-file=-", "--pathspec-file-nul",
            stdin=("\0".join(names) + "\0").encode())
        indexed = git(repo, "show", ":" + EXAMPLE)
        assert digest(indexed) == EXAMPLE_SHA
        tree = git(repo, "write-tree").decode().strip()
        clean.mkdir()
        git(repo, "-c", "core.autocrlf=true", "checkout-index", "--all", "--prefix=" + clean.as_posix() + "/")
        checkout_result = compare(clean, payload)
        checkout_receipts = check_receipts(clean, before)
        patch = git(repo, "diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", BASE, "--")
        patch_file = task / "full.patch"; patch_file.write_bytes(patch)
        git(task, "clone", "--no-hardlinks", "--no-checkout", str(root), str(applied))
        git(applied, "-c", "core.autocrlf=false", "checkout", "--detach", BASE)
        git(applied, "apply", "--binary", "--whitespace=nowarn", str(patch_file))
        patch_result = compare(applied, payload)
        patch_receipts = check_receipts(applied, before)
        assert original_index == digest((root / ".git/index").read_bytes())
        result = {"status": "BYTE_PRESERVATION_PASS", "base_commit": BASE,
                  "temporary_index_tree": tree, "check_attr_after": attrs.decode(),
                  "git_checkout": checkout_result, "git_checkout_receipts": checkout_receipts,
                  "patch_apply": patch_result, "patch_receipts": patch_receipts,
                  "patch_sha256_at_this_probe": digest(patch), "original_index_unchanged": True,
                  "commands": events}
        save(out / "transfer_after.json", result)
        print(json.dumps({k: v for k,v in result.items() if k != "commands"}, indent=2))
