"""Read-only checks shared by byte-transfer and archive validation."""
import hashlib
import json
from pathlib import Path
import zipfile

BASE = "415d53431c81c465784dc08be42b568827a39cff"
PREFIX = "ml/provenance/week3-sv2-linux"
REV = PREFIX + "/review-v2"
EXAMPLE = PREFIX + "/final_linux_verifier.command.json"
EXAMPLE_SHA = "2784a0df309e37134e80e3b8ac0a80be4f5afae930492ee0674f52ad4fe7f567"
digest = lambda raw: hashlib.sha256(raw).hexdigest()
save = lambda path, value: Path(path).write_bytes((json.dumps(value, indent=2) + "\n").encode())


def collect(root):
    paths = set(json.loads((root / REV / "old_review_source_paths.json").read_bytes()))
    paths.update(p.relative_to(root).as_posix() for p in (root / REV).rglob("*") if p.is_file())
    paths.update(("ml/scripts/authenticate_week3_sv2_package.py", "ml/scripts/record_week3_sv2_recipe.py"))
    report = "docs/sv3_ml_week3_linux_fp32_review_v2_report.md"
    if (root / report).exists(): paths.add(report)
    return sorted(paths)


def transfer_names(root):
    # The byte-transfer contract covers changed/new fix files and receipt-pinned
    # inputs. Unchanged auxiliary R4 context follows its existing LF policy.
    old = json.loads((root / REV / "old_review_scope.json").read_bytes())
    paths = {r["path"] for r in old["fix_files"]}
    paths.update(json.loads((root / PREFIX / "review_receipt.json").read_bytes())["source_sha256"])
    paths.update(p.relative_to(root).as_posix() for p in (root / REV).rglob("*") if p.is_file())
    paths.update((".gitattributes", "ml/scripts/authenticate_week3_sv2_package.py",
                  "ml/scripts/record_week3_sv2_recipe.py", "ml/requirements-core.txt",
                  "ml/requirements-week3-onnx.txt", "ml/requirements-gpu-cu130.txt"))
    report = "docs/sv3_ml_week3_linux_fp32_review_v2_report.md"
    if (root / report).exists(): paths.add(report)
    return sorted(paths)


def check_receipts(root, before):
    for name, row in before["historical_files"].items():
        raw = (root / name).read_bytes()
        assert len(raw) == row["size_bytes"] and digest(raw) == row["sha256"], name
    historical = root / PREFIX
    streams = 0
    for command in historical.glob("*.command.json"):
        record = json.loads(command.read_bytes())
        for row in record["streams"].values():
            raw = (historical / row["path"]).read_bytes()
            assert digest(raw) == row["sha256"], row["path"]
            streams += 1
    old = json.loads((historical / "review_receipt.json").read_bytes())
    for name, row in old["commands"].items():
        assert digest((historical / (name + ".json")).read_bytes()) == row["sha256"], name
    for name, expected in old["source_sha256"].items():
        target = root / name
        if name == "ml/scripts/reproduce_week3_sv2_linux.sh":
            target = root / REV / "source-before" / name
        assert digest(target.read_bytes()) == expected, name
    logs = root / REV / "recipe_success"
    new = json.loads((logs / "receipt.json").read_bytes())
    for name, expected in new["source_sha256"].items():
        assert digest((root / name).read_bytes()) == expected, name
    for command in new["commands"]:
        assert command["exit_code"] == 0
        for row in command["streams"].values():
            raw = (logs / row["path"]).read_bytes()
            assert len(raw) == row["size_bytes"] and digest(raw) == row["sha256"], row["path"]
    assert (logs / "recipe.exit_code.txt").read_text().strip() == "0"
    assert new["artifact_before_after_equal"]
    return {"historical_files": len(before["historical_files"]), "historical_streams": streams,
            "historical_source_hashes": len(old["source_sha256"]), "new_source_hashes": len(new["source_sha256"]),
            "new_completed_commands": len(new["commands"]), "example_sha256": digest((root / EXAMPLE).read_bytes()),
            "historical_script_resolved_to": REV + "/source-before/ml/scripts/reproduce_week3_sv2_linux.sh"}
