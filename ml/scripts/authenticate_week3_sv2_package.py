"""Authenticate existing v1 bytes before the Linux recipe runs tensor gates."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ANCHOR = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
ZIP_SHA = "b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7"


def authenticate(package):
    package = package.resolve()
    archive = package.with_suffix(".zip")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if archive.exists() and digest(archive) != ZIP_SHA:
        raise ValueError("Original ZIP checksum mismatch")
    if not package.exists():
        if not archive.is_file():
            raise ValueError("Place delivered original v1 ZIP or package in ml/artifacts/week3; no dataset download required")
        with zipfile.ZipFile(archive) as zipped:
            for name in zipped.namelist():
                target = (package.parent / name).resolve()
                if target != package and package not in target.parents:
                    raise ValueError("ZIP member escapes expected package directory")
            zipped.extractall(package.parent)
    if digest(package / "manifest.json") != ANCHOR:
        raise ValueError("Manifest anchor mismatch")
    manifest = json.loads((package / "manifest.json").read_bytes())
    rows = {}
    for row in manifest["files"]:
        path = package / row["path"]
        if not path.is_file() or path.stat().st_size != row["size_bytes"] or digest(path) != row["sha256"]:
            raise ValueError("Delivered hash/size mismatch: " + row["path"])
        rows[row["path"]] = {"sha256": row["sha256"], "size_bytes": row["size_bytes"]}
    return {"status": "AUTHENTICATED_ORIGINAL_V1", "manifest_sha256": ANCHOR,
            "files": rows, "original_zip_sha256_if_present": ZIP_SHA if archive.exists() else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(authenticate(args.package), indent=2))
