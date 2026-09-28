"""Generate an MCU C array from the authenticated v2 inputs.npy bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

TRUSTED_MANIFEST = "0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_inventory(package: Path) -> dict:
    manifest_path = package / "manifest.json"
    if sha256(manifest_path) != TRUSTED_MANIFEST:
        raise ValueError("Week 3 v2 manifest does not match trusted SHA-256")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["handoff_id"] != "mitdb-week3-fp32-20260925-v2":
        raise ValueError("Unexpected Week 3 handoff ID")
    expected = {item["path"] for item in manifest["files"]} | {"manifest.json"}
    actual = {path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()}
    if actual != expected or len(expected) != 29:
        raise ValueError(f"v2 package inventory differs: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    for item in manifest["files"]:
        path = package / item["path"]
        if path.stat().st_size != item["size_bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"v2 package file differs from manifest: {item['path']}")
    return manifest


def generate(package: Path, output: Path) -> None:
    manifest = check_inventory(package)
    entry = next((item for item in manifest["files"] if item["path"] == "inputs.npy"), None)
    inputs_path = package / "inputs.npy"
    if entry is None or sha256(inputs_path) != entry["sha256"]:
        raise ValueError("inputs.npy hash differs from authenticated manifest")
    inputs = np.load(inputs_path, allow_pickle=False)
    if inputs.shape != (20, 1, 360) or inputs.dtype.str != "<f4" or not np.isfinite(inputs).all():
        raise ValueError("inputs.npy must be finite FP32 with shape (20,1,360)")
    lines = [
        "/* Generated from authenticated MIT-BIH Week 3 v2 inputs.npy. Already normalized. */",
        "#ifndef WEEK3_INPUTS_H",
        "#define WEEK3_INPUTS_H",
        "#define WEEK3_SAMPLE_COUNT 20",
        "static const float week3_inputs[WEEK3_SAMPLE_COUNT][360] = {",
    ]
    for sample in inputs[:, 0, :]:
        lines.append("    {")
        for start in range(0, 360, 6):
            lines.append("        " + ", ".join(float(value).hex() + "f" for value in sample[start:start + 6]) + ",")
        lines.append("    },")
    lines.extend(["};", "#endif", ""])
    content = "\n".join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_text(encoding="utf-8") != content:
        output.write_text(content, encoding="utf-8", newline="\n")
    print(f"INPUTS_HEADER: {output} SHA-256 {sha256(output)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.package.resolve(), args.output.resolve())
