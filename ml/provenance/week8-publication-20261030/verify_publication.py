"""Verify the published Week 8 bytes; optionally restore IDs or inspect local checkpoints."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import re
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def member(root, name):
    p = (root / name).resolve()
    need(p.is_relative_to(root.resolve()) and p != root.resolve(), "Unsafe member")
    return p


def verify(root, base=None, hydrate=False, full=False):
    here = root / "ml/provenance/week8-publication-20261030"
    manifest = json.loads((here / "manifest.json").read_text("utf-8"))
    for name, entry in manifest["files"].items():
        data = member(root, name).read_bytes()
        need(len(data) == entry["bytes"] and sha(data) == entry["sha256"], "Changed publication member: " + name)
    ids = manifest["compressed_selected_ids"]
    raw = gzip.decompress(member(root, ids["compressed_path"]).read_bytes())
    need(len(raw) == ids["original_bytes"] and sha(raw) == ids["original_sha256"], "Compressed IDs differ")
    samples = json.loads(raw)
    need(set(samples) == {"train", "val"} and len(samples["train"]) == 81094 and len(samples["val"]) == 15388,
         "Incomplete selected IDs")
    for phase in samples:
        need(len({x["sample_id"] for x in samples[phase]}) == len(samples[phase]), "Duplicate selected IDs")
    need(not {x["patient_id"] for x in samples["train"]} & {x["patient_id"] for x in samples["val"]}, "Patient leakage")
    # Source report was frozen before publication; retain its original bytes separately.
    frozen = manifest["archived_report"]
    need(sha(member(root, frozen["archive_path"]).read_bytes()) == frozen["original_sha256"], "Archived report differs")
    links = 0
    for name in manifest["markdown_to_check"]:
        text = member(root, name).read_text("utf-8")
        need(not re.search(r"[A-Za-z]:[/\\]Users[/\\]", text), "Personal path in documentation")
        for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            candidate = (member(root, name).parent / target).resolve()
            need(candidate.is_relative_to(root.resolve()), "Escaping document link")
            rel = candidate.relative_to(root.resolve())
            need(candidate.exists() or (base is not None and (base / rel).exists()), "Missing document link: " + str(rel))
            links += 1
    if hydrate:
        target = member(root, ids["original_path"])
        if target.exists():
            need(sha(target.read_bytes()) == ids["original_sha256"], "Refuse to overwrite different selected IDs")
        else:
            with target.open("xb") as f:
                f.write(raw)
    if full:
        need(member(root, ids["original_path"]).is_file(), "Hydrate IDs before --full")
        sys.path.insert(0, str(root / "ml/scripts"))
        import analyze_week8_grid
        records = analyze_week8_grid.authenticate(root / manifest["experiment"], root / manifest["artifacts"])[3]
        need(len(records) == 54 and sum(x["epochs_completed"] for x in records) == 386, "Full grid differs")
    return {"status": "PASS_WEEK8_PUBLICATION", "files": len(manifest["files"]), "relative_links": links,
            "compressed_ids_exact": True, "full_local_checkpoint_review": full,
            "test_evaluation": "NOT_RUN", "deployment_status": "EXPERIMENT_ONLY_NOT_APPROVED"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    p.add_argument("--base-root", type=Path)
    p.add_argument("--hydrate-ids", action="store_true")
    p.add_argument("--full", action="store_true")
    a = p.parse_args()
    print(json.dumps(verify(a.root.resolve(), a.base_root, a.hydrate_ids, a.full), indent=2))
