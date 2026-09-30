"""Confirmed Week 3 FP32 split reference; no device/quantization acceptance."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np
import onnx
import onnxruntime as ort
import torch
from torch import nn

from week3_common import CHECKPOINT, MODEL_NAME, MODEL_VERSION, SOURCE, MODEL_HASH, FIELDS
from week3_common import fp32, load_model, need, read_json, safe_path, same_bits, sha

SV1_MANIFEST = "0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469"
INPUT_SHA = "dac1d1e9df849bf4ffa30359384d129586f67ec0703157b692d1344685b78dcc"
SAMPLES_SHA = "4a6356312d5f62da6b2fdf9e609843d4dea3fc5c20767e201ea21a075e6f227c"
P2_SHA = "5b9607815738e1a3a7ccde941e23a01a9ad927326839f38895e1f289e7d72399"
TOLERANCE = 1e-3
OPSET = 13
CONTRACT = "sv3-sv2-week3-fp32-v1"
SHAPES = ((1,1,360), (1,16,360), (1,16,180), (1,32,180), (1,32,90),
          (1,48,90), (1,48,45), (1,64,45), (1,64,22), (1,32), (1,5))
CUTS = (0, 2, 5, 7, 10, 12, 15, 17, 20, 24, 25)
OPS = tuple([f"features.{i}" for i in range(20)] + [f"classifier.{i}" for i in range(5)])
PREPROCESSING = "Exact frozen Week 1 preprocessing before head; no refit, second normalization or preprocessing inside tails"
TARGET = {"runtime": "VART", "backend": "KV260 DPU", "acceptance": "PENDING_SV2_INDEPENDENT_VALIDATION",
          "responsibility": "SV2: Vitis AI compatibility, quantization, xmodel compile and VART/KV260 execution",
          "int8_criterion": "Separate project quantization/device criteria; FP32 <1e-3 does not apply automatically"}


def split_map():
    return [{"split_id": s, "weighted_layers_in_head": list(range(1, s+1)),
             "head_endpoint": OPS[CUTS[s]-1] if s else "normalized_model_input (identity head)",
             "head_operations": list(OPS[:CUTS[s]]),
             "input_semantics": "normalized model input x",
             "activation_semantics": "pre-softmax logits" if s == 10 else f"z_s{s}: output of authoritative head_{s}",
             "shape_N1": list(SHAPES[s]), "dtype": "float32", "numpy_dtype": "<f4",
             "layout": "NCL" if s < 9 else "NC", "flatten_order": "C",
             "tail_start": OPS[CUTS[s]] if s < 10 else None,
             "tail_operations": list(OPS[CUTS[s]:]),
             "tail_type": "identity" if s == 10 else "full_model" if s == 0 else "remaining_frozen_ops",
             "onnx_required": s < 10, "edge_compute_required": s < 10,
             "onnx_path": f"models/tail_{s}.onnx" if s < 10 else None,
             "golden_path": f"golden/z_s{s}.npy", "input_tensor_name": "input_activation" if s < 10 else None,
             "output_tensor_name": "logits", "tail_output_type": "logits",
             "output_shape_N1": [1,5], "output_dtype": "float32"} for s in range(11)]


def configure():
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.mkldnn.enabled = False


def wrappers(model, s):
    """Reuse exact frozen modules; slicing changes neither parameters nor ops."""
    need(type(s) is int and 0 <= s <= 10, "Invalid authoritative split")
    leaves = [(n,m) for n,m in model.named_modules() if n and not list(m.children())]
    need(tuple(n for n,_ in leaves) == OPS, "Frozen operation order mismatch")
    modules = [m for _,m in leaves]
    head = nn.Sequential(*modules[:CUTS[s]]).eval()
    tail = nn.Sequential(*modules[CUTS[s]:]).eval()
    need(not any(m.training for m in model.modules()), "Frozen model must remain eval")
    return head, tail


def load_frozen(package):
    model, checkpoint = load_model(package / "model/checkpoint.pt", package / "model/mitdb_baseline_model.py")
    need(read_json(package / "model/train_config.json") == checkpoint["training_config"], "Training config differs")
    return model


def samples(package):
    need(sha(package / "samples.csv") == SAMPLES_SHA, "Frozen sample identities/order mismatch")
    with (package / "samples.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        need(reader.fieldnames == list(FIELDS), "Sample schema mismatch")
        rows = list(reader)
    need(len(rows) == 20 and [r["sample_index"] for r in rows] == list(map(str, range(20))), "20 ordered samples required")
    return rows


def error(actual, expected):
    need(actual.shape == expected.shape and actual.dtype == expected.dtype == np.dtype("float32"), "Output shape/dtype mismatch")
    need(np.isfinite(actual).all() and np.isfinite(expected).all(), "Non-finite output")
    return float(np.max(np.abs(actual.astype(np.float64) - expected.astype(np.float64))))


def references(model, inputs):
    configure()
    need(inputs.shape == (20,1,360), "Frozen input shape mismatch")
    with torch.inference_mode():
        full = fp32(np.concatenate([model(torch.from_numpy(inputs[i:i+1])).numpy() for i in range(20)]))
        activations, errors = {}, {}
        for s in range(11):
            head, tail = wrappers(model, s)
            values, differences = [], []
            for i in range(20):
                z = head(torch.from_numpy(inputs[i:i+1]))
                need(tuple(z.shape) == SHAPES[s], f"Observed split shape differs: s={s}")
                y = tail(z)
                differences.append(error(y.numpy(), full[i:i+1]))
                need(differences[-1] < TOLERANCE, f"PyTorch head/tail mismatch: s={s}, sample={i}")
                values.append(z.numpy().copy())
            activations[s], errors[s] = fp32(np.concatenate(values)), differences
    return full, activations, errors


def onnx_info(path, s):
    graph = onnx.load(str(path), load_external_data=False)
    need(all(t.data_location != onnx.TensorProto.EXTERNAL for t in graph.graph.initializer), "External ONNX weights forbidden")
    onnx.checker.check_model(graph, full_check=True)
    need([(o.domain,o.version) for o in graph.opset_import] == [("",OPSET)], "ONNX opset mismatch")
    need(len(graph.graph.input) == len(graph.graph.output) == 1, "ONNX input/output count mismatch")
    def tensor(value):
        t = value.type.tensor_type
        need(t.elem_type == onnx.TensorProto.FLOAT, "ONNX I/O must be FP32")
        need(all(d.HasField("dim_value") and not d.dim_param for d in t.shape.dim), "Dynamic ONNX dimensions forbidden")
        return {"name": value.name, "shape": [d.dim_value for d in t.shape.dim], "dtype": "float32"}
    inp, out = tensor(graph.graph.input[0]), tensor(graph.graph.output[0])
    need(inp == {"name":"input_activation", "shape":list(SHAPES[s]), "dtype":"float32"}, "ONNX input contract mismatch")
    need(out == {"name":"logits", "shape":[1,5], "dtype":"float32"}, "ONNX output contract mismatch")
    need(all(n.domain in ("", "ai.onnx") and n.op_type in {"Conv","Relu","MaxPool","Flatten","Gemm","Identity"}
             for n in graph.graph.node), "Unexpected ONNX operator; no softmax/argmax/preprocessing allowed")
    need(all(t.data_type == onnx.TensorProto.FLOAT for t in graph.graph.initializer), "ONNX weights must be FP32")
    return {"split_id":s, "path":f"models/tail_{s}.onnx", "sha256":sha(path), "size_bytes":path.stat().st_size,
            "opset":OPSET, "input":inp, "output":out, "operators":[n.op_type for n in graph.graph.node],
            "checker":"PASS", "ir_version":graph.ir_version}


def numerics(package, model, full, identities):
    rows, summaries, identity_rows = [], [], []
    models = []
    with torch.inference_mode():
        for s in range(11):
            z = np.load(package / f"golden/z_s{s}.npy", allow_pickle=False)
            _, tail = wrappers(model,s)
            if s < 10:
                path = package / f"models/tail_{s}.onnx"
                models.append(onnx_info(path,s))
                options = ort.SessionOptions()
                options.intra_op_num_threads = options.inter_op_num_threads = 1
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
            split_rows = []
            for i,row in enumerate(identities):
                # Verify the actual serialized activations, including loaded strides.
                pt = tail(torch.from_numpy(z[i:i+1])).numpy()
                pt_error = error(pt, full[i:i+1])
                need(pt_error < TOLERANCE, f"Saved activation/PyTorch tail mismatch: s={s}, sample={i}")
                record = {"sample_index":i, "sample_id":row["sample_id"], "split_id":s,
                          "pytorch_tail_max_abs_error":pt_error}
                if s < 10:
                    predicted = session.run(["logits"], {"input_activation":z[i:i+1]})[0]
                    record["onnx_max_abs_error"] = error(predicted, full[i:i+1])
                    record["onnx_vs_pytorch_tail_max_abs_error"] = error(predicted, pt)
                    need(record["onnx_max_abs_error"] < TOLERANCE, f"ONNX FP32 tolerance failure: s={s}, sample={i}")
                    record["status"] = "PASS"
                    rows.append(record)
                else:
                    record.update(onnx_max_abs_error=None, status="PASS_IDENTITY_NO_ONNX")
                    identity_rows.append(record)
                split_rows.append(record)
            summary = {"split_id":s, "samples":20, "pytorch_worst":max(r["pytorch_tail_max_abs_error"] for r in split_rows),
                       "onnx_worst":max(r["onnx_max_abs_error"] for r in split_rows) if s < 10 else None}
            summaries.append(summary)
    return {"status":"FP32_REFERENCE_PASS_NOT_HARDWARE_ACCEPTANCE", "tolerance_strict":TOLERANCE,
            "runtime":"ONNX Runtime CPUExecutionProvider", "ort_optimization":"ORT_ENABLE_BASIC",
            "torch_mode":"eval; CPU; N=1; one thread; deterministic; MKLDNN disabled",
            "comparisons":len(rows), "rows":rows, "s10_identity_rows":identity_rows, "per_split":summaries,
            "global_worst":max(rows, key=lambda r:r["onnx_max_abs_error"]), "onnx_models":models}


def inventory(package):
    result = []
    for p in sorted(package.rglob("*")):
        if not p.is_file() or p == package / "manifest.json":
            continue
        relative = p.relative_to(package).as_posix()
        need(not p.is_symlink(), "Package symlinks forbidden")
        row = {"path":relative, "sha256":sha(p), "size_bytes":p.stat().st_size}
        if p.suffix == ".npy":
            a = np.load(p,allow_pickle=False)
            need(a.dtype.str == "<f4", f"Wrong tensor dtype: {relative}")
            need(a.flags.c_contiguous and np.isfinite(a).all(), f"Non-finite or non-contiguous tensor: {relative}")
            row.update(shape=list(a.shape),dtype=a.dtype.str)
        elif p.suffix not in (".pt", ".onnx"):
            b = p.read_bytes()
            b.decode("utf-8")
            need(b"\r" not in b and not b.startswith(b"\xef\xbb\xbf"), f"Text must be UTF-8 LF: {relative}")
        result.append(row)
    return result


def authenticate(package, expected):
    need(isinstance(expected,str) and len(expected)==64 and all(c in "0123456789abcdef" for c in expected),
         "Independently trusted manifest SHA-256 required")
    raw = (package / "manifest.json").read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, "Manifest SHA-256 mismatch")
    def reject(v):
        raise ValueError(f"Non-finite JSON constant: {v}")
    manifest = json.loads(raw.decode("utf-8"),parse_constant=reject)
    for row in manifest["files"]:
        path = safe_path(package,row["path"])
        need(path.is_file() and sha(path)==row["sha256"] and path.stat().st_size==row["size_bytes"],
             f"File hash/size mismatch: {row['path']}")
    need(manifest["files"] == inventory(package), "Inventory differs")
    return manifest


def versions():
    return {"python":platform.python_version(), **{n:importlib.metadata.version(n) for n in
            ("torch","numpy","onnx","onnxruntime","protobuf","ml_dtypes","flatbuffers")}}
