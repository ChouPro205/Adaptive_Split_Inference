"""Week 4 offline tensor profiling, using the confirmed Week 3 executable graph."""
from __future__ import annotations

import csv
import hashlib
import io
import math
from pathlib import Path

import numpy as np
import torch

from week3_common import (CHECKPOINT, MODEL_HASH, MODEL_VERSION, compiler_verify,
                         fp32, header, need, read_json, sha, text, write_json)
from week3_sv2_common import (CONTRACT, INPUT_SHA, OPS, SAMPLES_SHA, authenticate,
                            configure, load_frozen, samples, split_map, wrappers)

W3_PATH = "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
W3_SHA = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
OUTPUT = "ml/results/week4-r2"
SOURCE_HASH_POLICY = "sha256-utf8-lf-v1"
SCRIPTS = ("week4_common.py", "profile_week4.py", "verify_week4.py", "test_week4.py")
FIELDS = ("s", "boundary_name", "head_last_op", "tail_first_op", "shape", "dtype",
          "layout", "numel_per_sample", "bytes_fp32", "kib_fp32",
          "bytes_int8_estimated", "kib_int8_estimated")


def frozen(repo):
    package = repo / W3_PATH
    manifest = authenticate(package, W3_SHA)
    need(manifest["splits"] == split_map(), "Week 3 canonical split mismatch")
    config = read_json(repo / "ml/configs/week3_sv2_interface_review.json")
    need(config == read_json(package / "model/sv2_interface.json")
         and config["status"] == config["split_registry_status"] == "CONFIRMED",
         "Confirmed split authority differs")
    need(sha(repo / "ml/src/mitdb_baseline_model.py") == MODEL_HASH,
         "Repository architecture changed")
    need(sha(package / "model/checkpoint.pt") == CHECKPOINT,
         "Packaged frozen checkpoint changed")
    need(sha(package / "golden/z_s0.npy") == INPUT_SHA, "Week 3 input differs")
    need(sha(package / "samples.csv") == SAMPLES_SHA, "Week 3 sample order differs")
    model = load_frozen(package)
    configure()
    return package, manifest, model, np.load(package / "golden/z_s0.npy", allow_pickle=False), samples(package)


def source_sha(path):
    """Hash UTF-8 source text, normalizing line endings only; binaries stay raw."""
    value = Path(path).read_bytes().decode("utf-8")
    return hashlib.sha256(value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def check_compiled(report, count):
    need(isinstance(report, dict) and set(report) == {"compiler", "flags", "fp32_elements", "status", "target"},
         "Host C evidence schema differs")
    need(isinstance(report["compiler"], str) and bool(report["compiler"].strip())
         and report["flags"] == "-std=c99 -Wall -Wextra -Werror -pedantic"
         and type(report["fp32_elements"]) is int and report["fp32_elements"] == count
         and report["status"] == "PASS" and report["target"] == "host; not nRF52840 firmware",
         "Host C evidence invariant differs")


def compare_reproduction(original, reproduced):
    """Compare scientific bytes strictly; allow only declared run metadata to vary."""
    a, b = read_json(original / "manifest.json"), read_json(reproduced / "manifest.json")
    excluded = {"manifest.json", "firmware/host_c_verification.json"}
    hashes = lambda root: {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*")
                           if p.is_file() and p.relative_to(root).as_posix() not in excluded}
    need(hashes(original) == hashes(reproduced), "Reproduction scientific bytes differ")
    for value in (a, b):
        for field in ("source_git_commit", "source_branch", "generation_command"):
            value.pop(field)
        value["files"] = [r for r in value["files"] if r["path"] != "firmware/host_c_verification.json"]
    need(a == b, "Reproduction scientific provenance differs")
    for root in (original, reproduced):
        graph = read_json(root / "model_graph.json")
        check_compiled(read_json(root / "firmware/host_c_verification.json"), graph["parameter_count"])


def analysis(rows):
    values = [r["bytes_fp32"] for r in rows]
    transitions = []
    for a, b in zip(rows, rows[1:]):
        delta = b["bytes_fp32"] - a["bytes_fp32"]
        transitions.append({"from_s": a["s"], "to_s": b["s"], "delta_bytes": delta,
                            "direction": "increase" if delta > 0 else "decrease" if delta < 0 else "equal",
                            "next_over_previous": b["bytes_fp32"] / a["bytes_fp32"],
                            "previous_over_next": a["bytes_fp32"] / b["bytes_fp32"]})
    up = [t for t in transitions if t["direction"] == "increase"]
    down = [t for t in transitions if t["direction"] == "decrease"]
    return {"NON_MONOTONIC": bool(up and down), "transitions": transitions,
            "increase_s": [[t["from_s"], t["to_s"]] for t in up],
            "decrease_s": [[t["from_s"], t["to_s"]] for t in down],
            "equal_s": [[t["from_s"], t["to_s"]] for t in transitions if t["direction"] == "equal"],
            "max_bytes_fp32": max(values), "max_s": [r["s"] for r in rows if r["bytes_fp32"] == max(values)],
            "min_bytes_fp32": min(values), "min_s": [r["s"] for r in rows if r["bytes_fp32"] == min(values)],
            "max_over_min": max(values) / min(values),
            "requirement_warning": "Non-increasing payload: report to GV; keep frozen model unchanged" if not up else None}


def profile(model, inputs):
    """Execution confirms all cuts, per inference N=1, with no timing measurements."""
    rows = []
    with torch.no_grad():
        for entry in split_map():
            s = entry["split_id"]
            head, _ = wrappers(model, s)
            # All 20 samples confirm shape; payload remains per ONE inference.
            shapes = [list(head(torch.from_numpy(inputs[i:i+1])).shape) for i in range(20)]
            need(all(v == entry["shape_N1"] for v in shapes), f"Executed boundary shape mismatch: {s}")
            numel = math.prod(shapes[0])
            rows.append({"s": s, "boundary_name": entry["head_endpoint"],
                         "head_last_op": entry["head_operations"][-1] if s else None,
                         "tail_first_op": entry["tail_start"], "shape_n1": shapes[0],
                         "dtype": "float32", "layout": entry["layout"], "flatten_order": "C",
                         "numel_per_sample": numel, "bytes_fp32": numel * 4,
                         "kib_fp32": numel * 4 / 1024, "bytes_int8_estimated": numel,
                         "kib_int8_estimated": numel / 1024,
                         "golden_path": f"{W3_PATH}/{entry['golden_path']}",
                         "execution_samples": 20})
    return {"schema_version": 1, "model_revision": MODEL_VERSION, "checkpoint_sha256": CHECKPOINT,
            "split_convention_version": CONTRACT, "canonical_registry_source": "ml/configs/week3_sv2_interface_review.json",
            "L": 10, "batch_size_for_payload": 1, "splits": rows, "analysis": analysis(rows),
            "payload_semantics": "Logical tensor only; excludes file headers, allocator/workspace/stack, packet/scale metadata and Flash parameters",
            "int8_semantics": "Theoretical estimated size = numel * 1; no quantization performed",
            "execution": "CPU eval; torch.no_grad; N=1; 20 frozen inputs; one thread; deterministic; MKLDNN disabled"}


def csv_profile(value):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in value["splits"]:
        writer.writerow({k: "x".join(map(str, row["shape_n1"])) if k == "shape" else row[k] for k in FIELDS})
    return out.getvalue()


def graph_parameters(model, inputs):
    """Independent full-forward hooks record every op; exact original parameter bits."""
    live = dict(model.named_modules())
    observed, handles = [], []
    for name in OPS:
        def hook(module, args, output, name=name):
            observed.append((name, list(args[0].shape), list(output.shape)))
        handles.append(live[name].register_forward_hook(hook))
    try:
        with torch.no_grad():
            model(torch.from_numpy(inputs[0:1]))
    finally:
        for h in handles:
            h.remove()
    need(tuple(n for n, _, _ in observed) == OPS, "Full forward operation sequence mismatch")
    ops, parameters = [], {}
    for index, (name, inp, out) in enumerate(observed):
        module = live[name]
        op_id = name.replace(".", "_")
        op = {"op_id": op_id, "module_path": name, "type": type(module).__name__,
              "input_shape_n1": inp, "output_shape_n1": out, "parameters": []}
        if isinstance(module, torch.nn.Conv1d):
            attrs = {"in_channels": module.in_channels, "out_channels": module.out_channels,
                     "kernel_size": module.kernel_size[0], "stride": module.stride[0],
                     "padding": module.padding[0], "padding_mode": module.padding_mode,
                     "dilation": module.dilation[0], "groups": module.groups, "bias": module.bias is not None}
        elif isinstance(module, torch.nn.Linear):
            attrs = {"in_features": module.in_features, "out_features": module.out_features, "bias": module.bias is not None}
        elif isinstance(module, torch.nn.MaxPool1d):
            attrs = {k: getattr(module, k) for k in ("kernel_size", "stride", "padding", "dilation", "ceil_mode", "return_indices")}
        elif isinstance(module, torch.nn.ReLU):
            attrs = {"inplace": module.inplace}
        elif isinstance(module, torch.nn.Flatten):
            attrs = {"start_dim": module.start_dim, "end_dim": module.end_dim, "order": "C; preserve batch"}
        elif isinstance(module, torch.nn.Dropout):
            attrs = {"p": module.p, "inplace": module.inplace, "training": False, "eval_behavior": "identity; no random sampling or scaling"}
        else:
            raise ValueError(f"Unsupported frozen operation {name}")
        op["attributes"] = attrs
        for key, param in module.named_parameters(recurse=False):
            a = fp32(param.detach().cpu().numpy())
            path = f"weights/{name}.{key}.npy"
            parameters[path] = a
            layout = "OIK" if a.ndim == 3 else "OI" if a.ndim == 2 else "O"
            op["parameters"].append({"path": path, "checkpoint_key": f"{name}.{key}",
                                     "name": key, "c_name": f"sv3_{op_id}_{key}", "shape": list(a.shape),
                                     "dtype": "<f4", "layout": layout, "flatten_order": "C",
                                     "element_count": a.size, "logical_tensor_bytes": a.nbytes})
        if isinstance(module, (torch.nn.Conv1d, torch.nn.Linear)):
            need([p["name"] for p in op["parameters"]] == ["weight", "bias"], f"Missing weight/bias: {name}")
        ops.append(op)
    need(len(parameters) == 20 and len(ops) == 25, "Whole-model parameter/op coverage differs")
    return {"model_revision": MODEL_VERSION, "checkpoint_sha256": CHECKPOINT,
            "ops": ops, "parameter_count": sum(a.size for a in parameters.values()),
            "parameter_logical_bytes_fp32": sum(a.nbytes for a in parameters.values()),
            "semantics": "Exact checkpoint; no folding, transpose, quantization or firmware implementation"}, parameters


def figure(value, root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.size": 10, "pdf.fonttype": 42, "font.family": "DejaVu Sans"}):
        fig, ax = plt.subplots(figsize=(7.2, 4.1))
        rows = value["splits"]
        ax.plot([r["s"] for r in rows], [r["kib_fp32"] for r in rows], "k-o", lw=1.6, ms=5, label="FP32 actual tensor payload")
        ax.plot([r["s"] for r in rows], [r["kib_int8_estimated"] for r in rows], color="0.45", linestyle="--", marker="s", lw=1.3, ms=4, label="INT8 estimated / theoretical payload")
        ax.set(xlabel="Canonical split s (learned layers in head)", ylabel="Logical payload per inference (KiB)", xticks=list(range(11)), ylim=(0, 25))
        ax.grid(axis="y", linestyle=":", color="0.8")
        ax.legend(loc="upper right", frameon=False)
        fig.text(0.5, 0.015, "Frozen Week 3 model | N = 1 | No device timing or quantization", ha="center", fontsize=8)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        fig.savefig(root / "tensor_size_vs_split.pdf", metadata={"CreationDate": None, "ModDate": None})
        fig.savefig(root / "tensor_size_vs_split.png", dpi=200, metadata={"Software": "SV3 Week 4 matplotlib"})
        plt.close(fig)


def inventory(root):
    rows = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p == root / "manifest.json":
            continue
        need(not p.is_symlink(), "Week 4 symlinks forbidden")
        row = {"path": p.relative_to(root).as_posix(), "sha256": sha(p), "file_size_bytes": p.stat().st_size}
        if p.suffix == ".npy":
            a = np.load(p, allow_pickle=False)
            row.update(dtype=a.dtype.str, shape=list(a.shape), logical_tensor_bytes=a.nbytes)
        rows.append(row)
    return rows
