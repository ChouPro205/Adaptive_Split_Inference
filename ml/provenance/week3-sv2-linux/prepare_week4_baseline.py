"""Materialize only R4 gate inputs from base commit, without changing the checkout."""
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[3]
view = root / "exports/week3-sv2-linux-review-20261006/baseline"
if view.exists():
    raise SystemExit("Baseline view exists; refusing to overwrite")
base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
manifest = json.loads((root / "ml/results/week4-r4/manifest.json").read_bytes())
paths = {row["path"] for row in manifest["source_files"]}
paths.update(subprocess.check_output(["git", "ls-files", "ml/scripts/*.py"], cwd=root).decode().splitlines())
for relative in sorted(paths):
    raw = subprocess.check_output(["git", "show", f"{base}:{relative}"], cwd=root)
    target = view / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
package = Path("ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1")
shutil.copytree(root / package, view / package)
receipt = {"base_commit": base, "view": view.relative_to(root).as_posix(),
           "materialized_source_files": sorted(paths), "package": package.as_posix(),
           "policy": "Separate base-commit source view; original artifacts read only; no new release"}
(Path(__file__).resolve().parent / "week4_baseline_view.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
