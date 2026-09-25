"""FP32 handoff for the explicitly approved historical MIT-BIH checkpoint.

Review packages exercise real tensors but cannot pass the release gate while
the SV3/SV1 output boundary is unconfirmed. No training or dataset writes.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

import numpy as np
import torch

CONTRACT = "w3-sv1-handoff-v1"
SOURCE = "8e98a0e4851abc979feb5fd5b97ece612b02cfaa"
CHECKPOINT = "9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90"
MODEL_HASH = "520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14"
MODULES = (("conv1", "features.0", "M1"), ("relu1", "features.1", "R1"),
           ("conv2", "features.2", "M2"), ("relu2", "features.3", "R2"),
           ("pool2", "features.4", "P2"))
RULE = "sort_numeric_record_id_then_numeric_r_peak_sample_then_lead_name_take_first_20"
FIELDS = ("sample_index", "sample_id", "dataset_profile", "split", "patient_id",
          "record_id", "r_peak_sample", "lead_name", "lead_index", "source_metadata_path",
          "source_row_index", "original_symbol", "aami_class", "class_index")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    def reject(value):
        raise ValueError(f"Non-finite JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def write_json(path, value):
    text(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def safe_path(root, relative):
    need(isinstance(relative, str) and relative and "\\" not in relative, "Invalid package path")
    need(not PurePosixPath(relative).is_absolute() and ":" not in relative
         and all(x not in ("", ".", "..") for x in relative.split("/")), "Unsafe package path")
    p = (Path(root) / relative).resolve()
    need(Path(root).resolve() in p.parents, "Package path escapes root")
    return p


def fp32(value):
    # Canonical singleton strides matter to CPU convolution dispatch as well.
    a = np.array(value, dtype="<f4", order="C", copy=True)
    need(np.isfinite(a).all(), "Non-finite FP32 tensor")
    return a


def same_bits(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes(order="C") == b.tobytes(order="C")


def tensor_info(a):
    return {"shape": list(a.shape), "dtype": "<f4", "layout": "NCL",
            "element_count": a.size, "size_bytes": a.nbytes, "flatten_order": "C",
            "offset": "((n*C+c)*L+l)"}


def load_model(checkpoint_path, source_path):
    need(sha(checkpoint_path) == CHECKPOINT, "Frozen checkpoint hash mismatch")
    need(sha(source_path) == MODEL_HASH, "Frozen model source hash mismatch")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    need(checkpoint["epoch"] == 3 and checkpoint["provenance"]["source_git_sha"] == SOURCE,
         "Checkpoint epoch/source mismatch")
    spec = importlib.util.spec_from_file_location("week3_frozen_model", source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.MitdbBaselineCNN(checkpoint["training_config"]["dropout"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    need(not any(m.training for m in model.modules()), "Model is not entirely in eval mode")
    need(not any(isinstance(m, torch.nn.modules.batchnorm._BatchNorm) for m in model.modules()),
         "Unexpected BatchNorm: exporter requires a new reviewed representation")
    return model, checkpoint


def check_decision(decision, review):
    need(decision["schema_version"] == 1 and decision["checkpoint_sha256"] == CHECKPOINT
         and decision["source_commit"] == SOURCE and decision["model_source_sha256"] == MODEL_HASH
         and decision["selected_epoch"] == 3 and decision["dataset_profile"] == "MIT-BIH/1.0.0"
         and decision["model_name"] == "mitdb_week2_cnn_v1", "Freeze identity mismatch")
    need(decision["model_freeze"]["status"] == "confirmed_conditional_on_verifiers"
         and bool(decision["model_freeze"]["evidence"]), "Model freeze has not been confirmed")
    selection = decision["sample_selection"]
    need(selection["split"] == "val" and selection["rule"] == RULE
         and selection["count"] == 20 and selection["seed"] is None, "Unsupported sample rule")
    boundary = decision["boundary"]
    if review:
        need(boundary["status"] == "OPEN_DECISION" and boundary["M_final"] is None
             and boundary["proposal"] == "P2", "Review requires an explicitly open boundary")
        return "P2"
    need(boundary["status"] != "SV3_CONFIRMED_SV1_PENDING",
         "SV1 confirmation PENDING; SV3 confirmation alone cannot authorize release")
    need(boundary["status"] == "CONFIRMED" and bool(boundary["confirmation"]),
         "OPEN_DECISION: M_final requires SV3/SV1 confirmation; no release")
    for party in ("sv3", "sv1"):
        confirmation = boundary.get(party + "_confirmation", {})
        need(confirmation.get("status") == "CONFIRMED"
             and confirmation.get("M_final") == boundary["M_final"]
             and bool(confirmation.get("authority")) and bool(confirmation.get("evidence")),
             f"Explicit {party.upper()} confirmation for M_final required; no release")
    need(boundary["M_final"] in ("M2", "R2", "P2"), "Unsupported confirmed boundary")
    need(boundary["M_final"] == "P2" and boundary.get("module_path") == "features.4"
         and boundary.get("operation") == "MaxPool1d" and boundary.get("shape_N1") == [1, 16, 180]
         and boundary.get("segment") == ["Conv1", "ReLU1", "Conv2", "ReLU2", "MaxPool1d"],
         "Approved Week 3 boundary must be P2 after features.4 with shape (1,16,180)")
    return boundary["M_final"]


def repo_imports(repo):
    import sys
    repo = Path(repo).resolve()
    sys.path.insert(0, str(repo / "ml/src"))
    from week1_common import ML_ROOT
    need(ML_ROOT.resolve() == repo / "ml", "Imported Week 1 helpers from wrong checkout")
    from verify_week2_baseline import verification_provenance_gate
    verification_provenance_gate()
    return repo


def source_and_data(repo, checkpoint):
    """Validate frozen source blobs and Week 1 bindings, select and rederive 20 rows."""
    repo = repo_imports(repo)
    from mitdb_week2_data import load_week1_splits
    from mitdb_common import load_signal_and_annotations, iter_valid_beats, validate_raw_files
    from week1_common import artifact_sha256, configured_path
    provenance = checkpoint["provenance"]
    need(provenance["source_git_sha"] == SOURCE, "Source commit differs")
    for relative, digest in provenance["source_files_sha256"].items():
        blob = subprocess.check_output(["git", "show", f"{SOURCE}:{relative}"], cwd=repo)
        need(hashlib.sha256(blob).hexdigest() == digest, f"Historical source mismatch: {relative}")
    config, identifiers, arrays = load_week1_splits()
    need(identifiers == provenance["dataset_artifacts"], "Frozen Week 1 provenance differs")
    metadata_path = configured_path(config, "processed_dir") / "val_metadata.csv"
    with metadata_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    keys = [(int(r["record_id"]), int(r["r_peak_sample"]), r["lead_name"]) for r in rows]
    need(len(set(keys)) == len(keys), "Duplicate Week 1 source identities")
    indices = sorted(range(len(rows)), key=lambda i: keys[i])[:20]
    need(len(indices) == 20, "Fewer than 20 real samples")
    samples = []
    for i, source_index in enumerate(indices):
        r = rows[source_index]
        samples.append({"sample_index": str(i),
                        "sample_id": f"MIT-BIH:{r['record_id']}:{r['r_peak_sample']}:{r['lead_name']}",
                        "dataset_profile": "MIT-BIH/1.0.0", "split": "val",
                        **{k: r[k] for k in ("patient_id", "record_id", "r_peak_sample", "lead_name", "lead_index")},
                        "source_metadata_path": metadata_path.relative_to(repo).as_posix(),
                        "source_row_index": str(source_index),
                        **{k: r[k] for k in ("original_symbol", "aami_class", "class_index")}})
    inputs = fp32(arrays["val"][0][indices, None, :])
    # Raw checksums and annotation-centred regeneration; never normalize processed X again.
    raw_dir, _ = validate_raw_files(config)
    normalization = read_json(configured_path(config, "normalization"))
    for record_id in sorted({r["record_id"] for r in samples}):
        _, signal, annotations, lead_index = load_signal_and_annotations(raw_dir, record_id, config)
        selected = {int(r["r_peak_sample"]): r for r in samples if r["record_id"] == record_id}
        found = set()
        for beat, peak, symbol, aami, label in iter_valid_beats(signal, annotations, config):
            if peak not in selected:
                continue
            r = selected[peak]
            need(r["original_symbol"] == symbol and r["aami_class"] == aami
                 and int(r["class_index"]) == label and int(r["lead_index"]) == lead_index,
                 "Raw annotation/lead metadata mismatch")
            actual = fp32((beat - normalization["mean"]) / normalization["std"])
            need(same_bits(actual, inputs[int(r["sample_index"]), 0]), "Raw-derived input bits differ")
            found.add(peak)
        need(found == set(selected), "Missing raw annotation for selected sample")
    paths = [repo / "ml/configs/mitdb_week1_config.json", configured_path(config, "patient_manifest"),
             configured_path(config, "normalization"),
             configured_path(config, "processed_dir") / "processed_manifest.json", metadata_path]
    upstream = [{"path": p.relative_to(repo).as_posix(), "sha256": artifact_sha256(p),
                 "hash_policy": "sha256_utf8_lf_normalized", "source_commit": SOURCE} for p in paths]
    return samples, inputs, upstream, identifiers


def trace(model, inputs, boundary):
    """Observe the approved source's real forward execution; retain only head milestones."""
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.mkldnn.enabled = False
    end = [m[2] for m in MODULES].index(boundary) + 1
    selected = MODULES[:end]
    observed, collected, handles = [], {m[2]: [] for m in selected}, []
    live = dict(model.named_modules())
    def make_hook(op_id, name, milestone):
        def hook(op, args, output):
            source, dest = fp32(args[0].detach().numpy()), fp32(output.detach().numpy())
            observed.append((op_id, name, milestone, source.shape, dest.shape))
            collected[milestone].append(dest.copy())
        return hook
    for op_id, name, milestone in selected:
        handles.append(live[name].register_forward_hook(make_hook(op_id, name, milestone)))
    try:
        with torch.inference_mode():
            for i in range(len(inputs)):
                model(torch.from_numpy(inputs[i:i+1]))
    finally:
        for handle in handles:
            handle.remove()
    need(len(observed) == len(inputs) * end, "Unexpected execution count")
    need(all([x[:3] for x in observed[i*end:(i+1)*end]] == list(selected)
             for i in range(len(inputs))), "First-two-Conv execution order differs")
    golden = {key: fp32(np.concatenate(value)) for key, value in collected.items()}
    milestones = {"M0": {**tensor_info(inputs), "path": "inputs.npy", "hook": "features.0 input"}}
    ops, parameters, previous = [], {}, "M0"
    for op_id, name, milestone, _, _ in observed[:end]:
        op = live[name]
        a = golden[milestone]
        milestones[milestone] = {**tensor_info(a), "path": f"golden/{milestone}.npy", "hook": name + " output"}
        metadata = {"op_id": op_id, "type": type(op).__name__, "module_path": name,
                    "input": previous, "output": milestone, "input_tensor": milestones[previous],
                    "output_tensor": milestones[milestone], "checkpoint_keys": [], "parameters": []}
        if isinstance(op, torch.nn.Conv1d):
            metadata["attributes"] = {"in_channels": op.in_channels, "out_channels": op.out_channels,
                "groups": op.groups, "kernel_size": op.kernel_size[0], "stride": op.stride[0],
                "padding": {"left": op.padding[0], "right": op.padding[0], "mode": op.padding_mode},
                "dilation": op.dilation[0], "bias": "present" if op.bias is not None else "absent",
                "bias_order": "after weighted sum, before following ReLU", "folded": False,
                "input_length": milestones[previous]["shape"][-1], "output_length": a.shape[-1]}
            for key, value in op.named_parameters(recurse=False):
                tensor = fp32(value.detach().numpy())
                path = f"weights/{op_id}.{key}.npy"
                parameters[path] = tensor
                metadata["checkpoint_keys"].append(name + "." + key)
                metadata["parameters"].append({"path": path, "checkpoint_key": name + "." + key,
                    "name": key, "c_name": f"sv3_{op_id}_{key}", "shape": list(tensor.shape),
                    "original_shape": list(tensor.shape), "dtype": "<f4", "element_count": tensor.size,
                    "size_bytes": tensor.nbytes, "flatten_order": "C",
                    "layout": "C_out,C_in/groups,K" if key == "weight" else "C_out",
                    "offset": "((oc*(C_in/groups)+ic_local)*K+k)" if key == "weight" else "oc",
                    "mapping": "checkpoint tensor unchanged; no fold"})
        elif isinstance(op, torch.nn.ReLU):
            metadata["attributes"] = {"inplace": op.inplace}
        elif isinstance(op, torch.nn.MaxPool1d):
            metadata["attributes"] = {"kernel_size": op.kernel_size, "stride": op.stride,
                "padding": op.padding, "dilation": op.dilation, "ceil_mode": op.ceil_mode,
                "return_indices": op.return_indices}
        else:
            raise ValueError(f"Unsupported head operation: {name}")
        ops.append(metadata)
        previous = milestone
    graph = {"ops": ops, "milestones": milestones, "M_final": boundary,
             "batchnorm": "absent", "folding": "none", "reshape": "absent", "transpose": "absent",
             "residual": "absent", "other_ops": "absent in exported segment",
             "inference": {"eval": True, "device": "cpu", "batch_size": 1,
                           "torch_threads": 1, "deterministic_algorithms": True, "mkldnn": False}}
    largest = max(x["size_bytes"] // len(inputs) for x in milestones.values())
    graph["memory"] = {"parameter_total_bytes": sum(a.nbytes for a in parameters.values()),
        "per_conv_bytes": {o["op_id"]: sum(p["size_bytes"] for p in o["parameters"])
                           for o in ops if o["type"] == "Conv1d"},
        "largest_intermediate_bytes_N1": largest,
        "persistent_parameter_flash_bytes_logical": sum(a.nbytes for a in parameters.values()),
        "two_activation_buffers_bytes_N1": 2 * largest,
        "measurement_status": "logical sizes only; no MCU build, stack or workspace measurement"}
    return graph, parameters, golden


def header(graph, parameters):
    lines = ["/* Generated FP32 reference. C99; C-order; no BatchNorm folding. */",
             "#ifndef SV3_HEAD_PARAMETERS_H", "#define SV3_HEAD_PARAMETERS_H", ""]
    for op in graph["ops"]:
        for p in op["parameters"]:
            a = parameters[p["path"]]
            name = p["c_name"]
            lines.append(f"enum {{ {name.upper()}_COUNT = {a.size}, {name.upper()}_RANK = {a.ndim} }};")
            for i, size in enumerate(a.shape):
                lines.append(f"enum {{ {name.upper()}_DIM_{i} = {size} }};")
            lines.append(f"static const float {name}[{name.upper()}_COUNT] = {{")
            values = [float(v).hex() + "f" for v in a.flat]
            lines.extend("    " + ", ".join(values[i:i+6]) + "," for i in range(0, len(values), 6))
            lines.extend(["};", ""])
    return "\n".join(lines + ["#endif", ""])


def compiler_verify(package, graph, parameters, compiler="gcc"):
    content = (package / "firmware/head_parameters.h").read_text(encoding="utf-8")
    need(content == header(graph, parameters), "Header contents or shape/count constants differ")
    ordered = [p for op in graph["ops"] for p in op["parameters"]]
    for p in ordered:
        match = re.search(r"static const float " + p["c_name"] + r"\[[^]]+\] = \{(.*?)\};", content, re.S)
        need(match is not None, "Missing C parameter array")
        literals = [x.strip() for x in match.group(1).split(",") if x.strip()]
        need(all(re.fullmatch(r"-?0x[0-9a-f]+\.[0-9a-f]+p[+-][0-9]+f", x) for x in literals),
             "Non-C99-hex-float literal")
        parsed = fp32([float.fromhex(x[:-1]) for x in literals]).reshape(p["shape"])
        need(same_bits(parsed, parameters[p["path"]]), "Header literal FP32 bits differ")
    executable = shutil.which(compiler)
    need(executable is not None, f"C compiler unavailable: {compiler}")
    with tempfile.TemporaryDirectory(prefix="sv3_week3_c_") as tmp:
        root = Path(tmp)
        shutil.copyfile(package / "firmware/head_parameters.h", root / "head_parameters.h")
        code = ['#include <stdint.h>', '#include <stdio.h>', '#include <string.h>',
                '#include "head_parameters.h"', 'int main(void) {',
                'if (sizeof(float) != 4) return 2;', 'uint32_t bits;']
        for p in ordered:
            code.append(f'for (unsigned i=0; i<{p["element_count"]}; ++i) {{ '
                        f'memcpy(&bits, &{p["c_name"]}[i], 4); printf("%08x\\n", (unsigned)bits); }}')
        text(root / "verify.c", "\n".join(code + ['return 0;', '}']))
        command = [executable, "-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "verify.c", "-o", "verify.exe"]
        subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
        actual = subprocess.check_output([str(root / "verify.exe")], text=True).splitlines()
        expected = [f"{int(v):08x}" for p in ordered for v in parameters[p["path"]].view("<u4").flat]
        need(actual == expected, "Compiled C header FP32 bits differ")
    return {"compiler": subprocess.check_output([executable, "--version"], text=True).splitlines()[0],
            "flags": "-std=c99 -Wall -Wextra -Werror -pedantic", "fp32_elements": len(expected),
            "status": "PASS", "target": "host; not nRF52840 firmware"}


def inventory(package):
    entries = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path == package / "manifest.json":
            continue
        relative = path.relative_to(package).as_posix()
        item = {"path": relative, "size_bytes": path.stat().st_size, "sha256": sha(path),
                "format": path.suffix.lstrip("."), "dtype": None}
        if path.suffix == ".npy":
            with path.open("rb") as f:
                version = np.lib.format.read_magic(f)
            a = np.load(path, allow_pickle=False)
            need(a.dtype.str == "<f4" and a.flags.c_contiguous and np.isfinite(a).all(),
                 f"Invalid NPY tensor: {relative}")
            item.update(dtype="<f4", shape=list(a.shape), npy_version=list(version),
                        element_count=a.size, tensor_size_bytes=a.nbytes)
        elif path.suffix != ".pt":
            value = path.read_bytes()
            value.decode("utf-8")
            need(b"\r" not in value and not value.startswith(b"\xef\xbb\xbf"),
                 f"Text must be UTF-8 LF without BOM: {relative}")
        entries.append(item)
    return entries


def versions():
    import platform
    return {"python": platform.python_version(), **{name: importlib.metadata.version(name)
            for name in ("torch", "numpy", "pandas", "wfdb", "scipy")}}
