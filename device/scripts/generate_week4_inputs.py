"""Authenticate R3 payload with explicit R3/R4 source bindings; generate tables."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from week4_handoff import (ALL_SPLIT_MANIFEST, PACKAGE, R3, WEEK4_MANIFEST,
                           authenticate_handoff, sha256)


def load_handoff(repo: Path, source_revision: str = "r4",
                 expected_source_anchor: str | None = None) -> tuple[dict, dict, dict, np.ndarray, list[str]]:
    r3 = repo / R3
    package = repo / PACKAGE
    manifest, split_manifest, _ = authenticate_handoff(repo, source_revision, expected_source_anchor)
    graph = json.loads((r3 / "model_graph.json").read_text(encoding="utf-8"))
    inputs = np.load(package / "golden/z_s0.npy", allow_pickle=False)
    if inputs.shape != (20, 1, 360) or inputs.dtype.str != "<f4" or not np.isfinite(inputs).all():
        raise ValueError("Expected finite little-endian FP32 inputs (20,1,360)")
    with (package / "samples.csv").open(encoding="utf-8", newline="") as stream:
        ids = [row["sample_id"] for row in csv.DictReader(stream)]
    if ids != manifest["sample_set"]["ordered_sample_ids"]:
        raise ValueError("Sample order/IDs differ from R3")
    ops = graph["ops"]
    if len(ops) != 25 or graph["parameter_logical_bytes_fp32"] != 438612:
        raise ValueError("Unexpected R3 graph")
    for split in split_manifest["splits"]:
        names = [op["module_path"] for op in ops[:len(split["head_operations"])]]
        if names != split["head_operations"]:
            raise ValueError(f"Split {split['split_id']} is not the graph prefix")
        expected_shape = ops[len(names) - 1]["output_shape_n1"] if names else [1, 1, 360]
        if expected_shape != split["shape_N1"] or split["flatten_order"] != "C":
            raise ValueError("Split shape/order mismatch")
    if len(split_manifest["splits"]) != 11:
        raise ValueError("Expected all eleven splits")
    return manifest, split_manifest, graph, inputs, ids


def write_generated(path: Path, lines: list[str]) -> None:
    content = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8", newline="\n")


def generate(repo: Path, source_revision: str = "r4", expected_source_anchor: str | None = None,
             generated_dir: Path | None = None) -> tuple[dict, dict, dict, np.ndarray, list[str]]:
    handoff = load_handoff(repo, source_revision, expected_source_anchor)
    _, splits, graph, inputs, ids = handoff
    generated = generated_dir if generated_dir is not None else repo / "device/generated"
    lines = ["/* Authenticated R3; exact normalized FP32 inputs, original order. */",
             "#ifndef WEEK4_INPUTS_H", "#define WEEK4_INPUTS_H",
             "#define WEEK4_SAMPLE_COUNT 20U",
             f'#define WEEK4_MANIFEST_SHA256 "{WEEK4_MANIFEST}"',
             "static const char *const week4_sample_ids[WEEK4_SAMPLE_COUNT] = {"]
    lines.extend(f"    {json.dumps(sample_id)}," for sample_id in ids)
    lines.extend(["};", "static const float week4_inputs[WEEK4_SAMPLE_COUNT][360] = {"])
    for sample in inputs[:, 0]:
        lines.append("    {")
        for start in range(0, 360, 6):
            lines.append("        " + ", ".join(float(x).hex() + "f" for x in sample[start:start + 6]) + ",")
        lines.append("    },")
    lines.extend(["};", "#endif"])
    write_generated(generated / "week4_inputs.h", lines)
    lines = ["/* Authenticated R3 graph; included once after head_op declaration. */",
             "static const struct head_op head_ops[] = {"]
    for op in graph["ops"]:
        kind = op["type"]
        attrs = op["attributes"]
        shape = op["input_shape_n1"]
        weight, bias = "NULL", "NULL"
        if kind == "Conv1d":
            if (attrs["kernel_size"], attrs["stride"], attrs["padding"], attrs["dilation"], attrs["groups"]) != (5, 1, 2, 1, 1):
                raise ValueError("Unsupported convolution")
            token, ic, oc, length = "OP_CONV", attrs["in_channels"], attrs["out_channels"], shape[2]
        elif kind == "Linear":
            token, ic, oc, length = "OP_LINEAR", attrs["in_features"], attrs["out_features"], 1
        elif kind in ("Flatten", "Dropout"):
            if kind == "Dropout" and attrs["training"]:
                raise ValueError("Only eval Dropout is supported")
            token, ic, oc, length = "OP_IDENTITY", 0, 0, 0
        else:
            token = {"ReLU": "OP_RELU", "MaxPool1d": "OP_POOL"}[kind]
            ic = oc = shape[1]
            length = shape[2] if len(shape) == 3 else 1
            if kind == "MaxPool1d" and (attrs["kernel_size"], attrs["stride"], attrs["padding"], attrs["ceil_mode"]) != (2, 2, 0, False):
                raise ValueError("Unsupported pool")
        if op["parameters"]:
            weight, bias = [parameter["c_name"] for parameter in op["parameters"]]
        lines.append(f"    {{ {token}, {ic}, {oc}, {length}, {weight}, {bias} }}, /* {op['module_path']} */")
    lines.extend(["};", "static const unsigned split_op_counts[WEEK4_SPLIT_COUNT] = {"])
    lines.append("    " + ", ".join(str(len(s["head_operations"])) for s in splits["splits"]))
    lines.extend(["};", "static const struct week4_shape split_shapes[WEEK4_SPLIT_COUNT] = {"])
    for split in splits["splits"]:
        shape = split["shape_N1"]
        padded = shape + [0] * (3 - len(shape))
        lines.append(f"    {{ {len(shape)}, {{ {', '.join(map(str, padded))} }}, {math.prod(shape)} }},")
    lines.append("};")
    write_generated(generated / "week4_graph.h", lines)
    print(f"R3_PAYLOAD / {source_revision.upper()}_SOURCE: PASS; generated exact inputs and 25-op graph / 11 splits")
    return handoff


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--source-revision", choices=("r3", "r4"), default="r4")
    parser.add_argument("--expected-source-anchor")
    parser.add_argument("--generated-dir", type=Path)
    args = parser.parse_args()
    generate(args.repo_root.resolve(), args.source_revision, args.expected_source_anchor,
             args.generated_dir.resolve() if args.generated_dir else None)
