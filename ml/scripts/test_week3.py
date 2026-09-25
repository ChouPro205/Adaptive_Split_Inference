"""Corrupt copies of review or release evidence; never modify the source package."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import io
from pathlib import Path
import shutil
import tempfile

import numpy as np

from export_week3 import export
from verify_week3 import verify
from week3_common import FIELDS, check_decision, inventory, need, read_json, sha, text, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    package, repo = args.package.resolve(), args.repo_root.resolve()
    before = {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*") if p.is_file()}
    package_status = read_json(package / "manifest.json")["release_status"]
    need(package_status in ("REVIEW_ONLY_M_FINAL_UNCONFIRMED", "SV3_RELEASE_PACKAGE"), "Unknown package status")
    review = package_status == "REVIEW_ONLY_M_FINAL_UNCONFIRMED"
    verify(package, repo, review=review)
    print("PASS: real package, raw-derived inputs, compiled C and all golden")
    cases = []

    def release_gate(p):
        verify(p, repo, review=False)

    def missing_sv1(p):
        decision = read_json(p / "model/freeze_decision.json")
        decision["boundary"]["sv1_confirmation"]["status"] = "PENDING"
        write_json(p / "model/freeze_decision.json", decision)

    def missing_bias(p):
        # Deliberately remove a required parameter only in the isolated test copy.
        (p / "weights/conv2.bias.npy").unlink()

    def changed_tensor(p, relative):
        a = np.load(p / relative, allow_pickle=False)
        a.flat[0] = np.nextafter(a.flat[0], np.float32(np.inf), dtype=np.float32)
        np.save(p / relative, a, allow_pickle=False)

    def sample_swap(p):
        with (p / "samples.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        rows[0], rows[1] = rows[1], rows[0]
        rows[0]["sample_index"], rows[1]["sample_index"] = "0", "1"
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
        text(p / "samples.csv", out.getvalue())

    def changed_graph(p):
        graph = read_json(p / "model/graph.json")
        graph["ops"].pop(1)  # Remove the real intermediate ReLU.
        write_json(p / "model/graph.json", graph)

    def changed_header(p):
        path = p / "firmware/head_parameters.h"
        text(path, path.read_text(encoding="utf-8").replace("static const float", "static float", 1))

    def changed_dtype(p):
        path = p / "inputs.npy"
        np.save(path, np.load(path).astype(np.float64), allow_pickle=False)

    def nonfinite(p):
        path = p / "golden/M2.npy"
        a = np.load(path); a.flat[0] = np.nan
        np.save(path, a, allow_pickle=False)

    cases.extend([
        (("release gate", lambda p: None, False, "Release gate:", release_gate) if review else
         ("release gate without SV1", missing_sv1, True, "Explicit SV1 confirmation", None)),
        ("missing real bias", missing_bias, True, "Missing required package files", None),
        ("input value with recomputed file hash", lambda p: changed_tensor(p, "inputs.npy"), True,
         "Delivered inputs differ", None),
        ("golden value with recomputed file hash", lambda p: changed_tensor(p, "golden/M1.npy"), True,
         "FP32 recomputation bits differ", None),
        ("weight value with recomputed file hash", lambda p: changed_tensor(p, "weights/conv1.weight.npy"), True,
         "FP32 recomputation bits differ", None),
        ("sample order with recomputed file hash", sample_swap, True, "Samples differ", None),
        ("omitted intermediate op", changed_graph, True, "Graph differs", None),
        ("C header representation", changed_header, True, "Header contents", None),
        ("wrong dtype", changed_dtype, False, "File hash/size mismatch", None),
        ("nonfinite golden", nonfinite, False, "File hash/size mismatch", None),
    ])
    for label, mutate, rehash, message, action in cases:
        with tempfile.TemporaryDirectory(prefix="sv3_week3_negative_") as directory:
            copy = Path(directory) / package.name
            shutil.copytree(package, copy)
            mutate(copy)
            if rehash:
                manifest = read_json(copy / "manifest.json")
                manifest["files"] = inventory(copy)
                write_json(copy / "manifest.json", manifest)
            try:
                (action or (lambda p: verify(p, repo, review=review)))(copy)
            except ValueError as exc:
                need(message in str(exc), f"Wrong failure for {label}: {exc}")
            else:
                raise ValueError(f"Mutation accepted: {label}")
            print(f"PASS expected rejection: {label}")
    try:
        export(repo, package / "model/freeze_decision.json", package.name, package.parent, review=review)
    except ValueError as exc:
        need("Immutable revision already exists" in str(exc), f"Wrong overwrite failure: {exc}")
    else:
        raise ValueError("Exporter accepted overwrite")
    print("PASS expected rejection: immutable revision overwrite")
    unconfirmed = deepcopy(read_json(package / "model/freeze_decision.json"))
    unconfirmed["boundary"]["status"] = "OPEN_DECISION"
    unconfirmed["boundary"]["confirmation"] = None
    try:
        check_decision(unconfirmed, review=False)
    except ValueError as exc:
        need("M_final requires SV3/SV1 confirmation" in str(exc), f"Wrong freeze failure: {exc}")
    else:
        raise ValueError("Exporter release gate accepted open M_final")
    print("PASS expected rejection: export without M_final confirmation")
    current = read_json(repo / "ml/configs/week3_model_freeze.json")
    # Test one-party consent and a stale generic approval flag only in memory.
    for generic_confirmed, message in ((False, "SV1 confirmation PENDING"),
                                        (True, "Explicit SV1 confirmation")):
        fixture = deepcopy(current)
        fixture["boundary"]["status"] = "SV3_CONFIRMED_SV1_PENDING"
        fixture["boundary"]["sv1_confirmation"] = {"status": "PENDING", "M_final": None,
                                                   "authority": None, "evidence": None}
        if generic_confirmed:
            fixture["boundary"]["status"] = "CONFIRMED"
            fixture["boundary"]["confirmation"] = "Synthetic regression flag; not actual approval"
        try:
            check_decision(fixture, review=False)
        except ValueError as exc:
            need(message in str(exc), f"Wrong one-party consent rejection: {exc}")
        else:
            raise ValueError("Release accepted without explicit SV1 confirmation")
        print(f"PASS expected rejection: {message}")
    after = {p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*") if p.is_file()}
    need(before == after, "Real review package changed during tests")
    print(f"PASS: {len(cases) + 4} expected rejections; source package unchanged")


if __name__ == "__main__":
    main()
