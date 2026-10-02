"""Authenticate R3 and generate input/graph tables; never modify ML artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

WEEK4_MANIFEST = "80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c"
ALL_SPLIT_MANIFEST = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
PACKAGE = "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
R3 = "ml/results/week4-r3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authenticated_json(path: Path, expected: str) -> dict:
    if sha256(path) != expected:
        raise ValueError(f"Manifest anchor mismatch: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path, entry: dict) -> None:
    size = entry.get("file_size_bytes", entry.get("size_bytes"))
    if (size is not None and path.stat().st_size != size) or sha256(path) != entry["sha256"]:
        raise ValueError(f"Pinned file mismatch: {path}")


def load_handoff(repo: Path) -> tuple[dict, dict, dict, np.ndarray, list[str]]:
    r3 = repo / R3
    package = repo / PACKAGE
    manifest = authenticated_json(r3 / "manifest.json", WEEK4_MANIFEST)
    split_manifest = authenticated_json(package / "manifest.json", ALL_SPLIT_MANIFEST)
    for entry in manifest["files"]:
        check_file(r3 / entry["path"], entry)
    for entry in split_manifest["files"]:
        check_file(package / entry["path"], entry)
    for entry in manifest["source_files"]:
        # The accepted source policy normalizes UTF-8 CRLF to LF.
        raw = (repo / entry["path"]).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"Pinned ML source mismatch: {entry['path']}")
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


def generate(repo: Path) -> tuple[dict, dict, dict, np.ndarray, list[str]]:
    handoff = load_handoff(repo)
    _, splits, graph, inputs, ids = handoff
    generated = repo / "device/generated"
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
    print("R3_AUTHENTICATION: PASS; generated exact inputs and 25-op graph / 11 splits")
    return handoff


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    generate(parser.parse_args().repo_root.resolve())
