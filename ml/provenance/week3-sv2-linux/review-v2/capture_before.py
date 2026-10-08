"""Capture historical bytes read-only before review-v2 changes."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
historical = root / "ml/provenance/week3-sv2-linux"
digest = lambda raw: hashlib.sha256(raw).hexdigest()
files = {p.relative_to(root).as_posix(): p.read_bytes() for p in historical.rglob("*")
         if p.is_file() and out not in p.parents}
snapshot = {name: {"sha256": digest(raw), "size_bytes": len(raw), "has_crlf": b"\r\n" in raw}
            for name, raw in sorted(files.items())}
for name in ("ml/scripts/reproduce_week3_sv2_linux.sh", ".gitattributes"):
    target = out / "source-before" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((root / name).read_bytes())
package = root / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
artifacts = {p.relative_to(root).as_posix(): {"sha256": digest(p.read_bytes()), "size_bytes": p.stat().st_size}
             for p in package.rglob("*") if p.is_file()}
for name in ("SV3_LINUX_FP32_REVIEW.zip", "SV3_LINUX_FP32_REVIEW.validation.json",
             "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1.zip"):
    p = root / name
    artifacts[name] = {"sha256": digest(p.read_bytes()), "size_bytes": p.stat().st_size}
attrs = subprocess.check_output(["git", "check-attr", "text", "eol", "--",
           "ml/provenance/week3-sv2-linux/final_linux_verifier.command.json"], cwd=root)
record = {"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
          "historical_files": snapshot, "historical_file_count": len(snapshot),
          "historical_crlf_count": sum(r["has_crlf"] for r in snapshot.values()),
          "artifact_and_old_archive_files": artifacts,
          "old_script_sha256": digest((root / "ml/scripts/reproduce_week3_sv2_linux.sh").read_bytes()),
          "check_attr_before": attrs.decode()}
(out / "before.json").write_bytes((json.dumps(record, indent=2) + "\n").encode())
assert snapshot["ml/provenance/week3-sv2-linux/final_linux_verifier.command.json"]["sha256"] == "2784a0df309e37134e80e3b8ac0a80be4f5afae930492ee0674f52ad4fe7f567"
print(json.dumps({k: record[k] for k in ("historical_file_count", "historical_crlf_count", "old_script_sha256", "check_attr_before")}, indent=2))
