"""Recheck immutable v1 and log integrity; produce local review receipt."""
import hashlib
import json
from pathlib import Path
import subprocess
import struct

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
package = root / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
write = lambda name, data: (out / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
after = {p.relative_to(package).as_posix(): digest(p) for p in package.rglob("*") if p.is_file()}
archive = package.with_suffix(".zip")
after["../" + archive.name] = digest(archive)
before = json.loads((out / "artifact_before.json").read_bytes())
write("artifact_after.json", after)
changed = [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]
receipt = {"unchanged": not changed, "changed_paths": changed, "entries_including_zip": len(after),
           "manifest_sha256": after["manifest.json"], "zip_sha256": after["../" + archive.name]}
write("artifact_preservation.json", receipt)
if changed:
    raise SystemExit("Immutable artifacts changed")
# Reproduce dense comparison from native diagnostic output, without NumPy.
windows = json.loads((out / "dense_windows.stdout.txt").read_bytes())
linux = json.loads((out / "dense_linux.stdout.txt").read_bytes())
dense = {"same_operand_hashes": windows["operand_sha256"] == linux["operand_sha256"]}
for key in ("linear1_pre_relu", "linear2_from_delivered_s9"):
    entries = [(i, j, w, linux[key][i][j]) for i, row in enumerate(windows[key]) for j, w in enumerate(row)]
    i, j, w, l = max(entries, key=lambda row: abs(row[2] - row[3]))
    dense[key] = {"different_bit_elements": sum(struct.pack("<f", a) != struct.pack("<f", b) for _, _, a, b in entries),
                  "max_abs_error_float64": abs(w-l), "max_index": [i, j], "windows_at_max": w, "linux_at_max": l}
write("dense_comparison.json", dense)
logs = {}
for p in sorted(out.glob("*.command.json")):
    record = json.loads(p.read_bytes())
    for stream in record["streams"].values():
        if digest(out / stream["path"]) != stream["sha256"]:
            raise SystemExit("Log checksum mismatch: " + stream["path"])
    logs[p.stem] = {"exit_code": record["exit_code"], "sha256": digest(p),
                    "source_unchanged_during_command": record.get("source_unchanged_during_command")}
sources = {p.relative_to(root).as_posix(): digest(p) for p in sorted((root / "ml/scripts").glob("*week3*")) if p.is_file()}
write("review_receipt.json", {"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
      "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=root).decode().strip(),
      "state": "Uncommitted local review; no new release or recipient acceptance", "source_sha256": sources,
      "artifact_preservation": receipt, "commands": logs})
print(json.dumps(receipt, indent=2))
print("Command/stream checksums verified:", len(logs))
