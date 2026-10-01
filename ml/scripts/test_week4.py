"""Reason-specific tampering tests and byte-for-byte Week 4 reproduction."""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import numpy as np

from profile_week4 import export
from verify_week4 import verify
from week3_common import need, read_json, sha, text, write_json
from week4_common import OUTPUT, analysis, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path(OUTPUT))
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    repo, source = args.repo_root.resolve(), args.output_dir.resolve()
    anchor = args.expected_manifest_sha256
    verify(source, repo, anchor, args.compiler)
    before = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob("*") if p.is_file()}
    def json_mutation(path, change):
        def mutate(root):
            value = read_json(root / path)
            change(value)
            write_json(root / path, value)
        return mutate
    def tensor_mutation(kind):
        def mutate(root):
            p = root / "weights/features.0.weight.npy"
            a = np.load(p)
            if kind == "dtype":
                a = a.astype("float64")
            elif kind == "shape":
                a = a.reshape(-1)
            else:
                a.flat[0] = np.nan if kind == "nan" else a.flat[0] + 1
            np.save(p, a, allow_pickle=False)
        return mutate
    cases = [
        ("metadata without anchor", json_mutation("manifest.json", lambda v: v.update(scope="bad")), False, "manifest SHA-256 mismatch"),
        ("file raw mutation", lambda r: text(r / "tensor_profile.csv", "broken\n"), False, "artifact hash/size mismatch"),
        ("split missing", json_mutation("tensor_profile.json", lambda v: v["splits"].pop()), True, "profile/boundary/analysis differs"),
        ("split duplicate", json_mutation("tensor_profile.json", lambda v: v["splits"].append(v["splits"][0])), True, "profile/boundary/analysis differs"),
        ("boundary", json_mutation("tensor_profile.json", lambda v: v["splits"][2].update(head_last_op="features.3")), True, "profile/boundary/analysis differs"),
        ("N=20 payload", json_mutation("tensor_profile.json", lambda v: v["splits"][0].update(bytes_fp32=28800)), True, "profile/boundary/analysis differs"),
        ("INT8 estimate", json_mutation("tensor_profile.json", lambda v: v["splits"][1].update(bytes_int8_estimated=23040)), True, "profile/boundary/analysis differs"),
        ("analysis", json_mutation("tensor_profile.json", lambda v: v["analysis"].update(NON_MONOTONIC=False)), True, "profile/boundary/analysis differs"),
        ("sample order", json_mutation("manifest.json", lambda v: v["sample_set"]["ordered_sample_ids"].reverse()), True, "identity/order differs"),
        ("checkpoint identity", json_mutation("manifest.json", lambda v: v.update(checkpoint_sha256="0"*64)), True, "provenance differs"),
        ("pool attributes", json_mutation("model_graph.json", lambda v: v["ops"][4]["attributes"].update(ceil_mode=True)), True, "graph/op attributes differ"),
        ("missing bias", lambda r: (r / "weights/classifier.4.bias.npy").unlink(), True, "No such file"),
        ("header precision", lambda r: text(r / "firmware/head_parameters.h", "/* replaced */\n"), True, "Header contents"),
        ("figure missing", lambda r: (r / "tensor_size_vs_split.pdf").unlink(), True, "required file set differs"),
    ]
    cases += [(f"parameter {k}", tensor_mutation(k), True, "Invalid parameter" if k in ("dtype", "nan") else "Parameter FP32 bits differ") for k in ("dtype", "nan", "shape", "value")]
    with tempfile.TemporaryDirectory(prefix="sv3_week4_") as tmp:
        base = Path(tmp)
        for i, (name, mutate, semantic, message) in enumerate(cases):
            root = base / f"case{i}"
            shutil.copytree(source, root)
            mutate(root)
            expected = anchor
            if semantic:
                # Test-controlled trust root only: isolate semantic checks after valid hashes.
                m = read_json(root / "manifest.json")
                m["files"] = inventory(root)
                write_json(root / "manifest.json", m)
                expected = sha(root / "manifest.json")
            try:
                verify(root, repo, expected, args.compiler)
            except (ValueError, OSError) as exc:
                need(message in str(exc), f"Wrong rejection {name}: {exc}")
            else:
                raise ValueError(f"Tampering accepted: {name}")
            print(f"PASS expected rejection: {name}")
        repro = base / "reproduction"
        reproduced_anchor = export(repo, repro, args.compiler)
        verify(repro, repo, reproduced_anchor, args.compiler)
        after = {p.relative_to(repro).as_posix(): sha(p) for p in repro.rglob("*") if p.is_file()}
        need(before == after, "Reproduction raw bytes differ")
        print(f"PASS reproduction: {len(after)} files byte-identical; reused 220 golden cases bitwise")
    for vals, expected in (([1, 2, 3], False), ([3, 2, 1], False), ([2, 2, 2], False), ([1, 3, 2], True)):
        result = analysis([{"s": i, "bytes_fp32": b} for i, b in enumerate(vals)])
        need(result["NON_MONOTONIC"] is expected, "Incorrect non-monotonic classification")
    need(before == {p.relative_to(source).as_posix(): sha(p) for p in source.rglob("*") if p.is_file()}, "Real Week 4 output changed")
    print(f"WEEK4_TESTS_PASS: {len(cases)} expected rejections; 4 monotonic cases; exact reproduction; source unchanged")


if __name__ == "__main__":
    main()
