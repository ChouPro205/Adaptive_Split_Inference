"""Read-only FP32 diagnostic on authenticated v1; never rewrites golden data."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import argparse
import json
import os
import platform
import hashlib
from pathlib import Path
import numpy as np
import torch
from week3_common import read_json, same_bits
from week3_sv2_common import authenticate, configure, error, load_frozen, numerics, references, samples, versions


def dense_probe(package, anchor):
    authenticate(package, anchor)
    configure()
    model = load_frozen(package)
    z8 = np.load(package / "golden/z_s8.npy", allow_pickle=False)
    z9 = np.load(package / "golden/z_s9.npy", allow_pickle=False)
    flat = z8.reshape(20, -1)
    layer = model.classifier[2]
    weight, bias = layer.weight.detach().numpy(), layer.bias.detach().numpy()
    with torch.inference_mode():
        pre = np.concatenate([layer(torch.from_numpy(flat[i:i+1])).numpy() for i in range(20)])
    hashes = {name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in
              (("flattened_input", flat), ("weight", weight), ("bias", bias))}
    relu = np.maximum(pre, np.float32(0))
    # Isolate the last Linear with the same serialized s9 on both platforms.
    with torch.inference_mode():
        last = np.concatenate([model.classifier[4](torch.from_numpy(z9[i:i+1])).numpy() for i in range(20)])
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as profile:
        with torch.inference_mode(): layer(torch.from_numpy(flat[0:1]))
    return {"platform": platform.platform(), "operand_sha256": hashes,
            "linear1_pre_relu": pre.tolist(), "relu_vs_saved_s9": measure(relu, z9),
            "linear2_from_delivered_s9": last.tolist(), "cpu_ops": [e.key for e in profile.key_averages()],
            "torch_build": torch.__config__.show()}


def measure(actual, expected):
    distance = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
    index = np.unravel_index(int(np.argmax(distance)), distance.shape)
    return {"shape": list(actual.shape), "expected_shape": list(expected.shape),
            "dtype": actual.dtype.str, "expected_dtype": expected.dtype.str,
            "finite": bool(np.isfinite(actual).all() and np.isfinite(expected).all()),
            "same_bits": same_bits(actual, expected),
            "different_bit_elements": int(np.count_nonzero(actual.view(np.uint32) != expected.view(np.uint32))),
            "max_abs_error_float64": float(distance[index]), "max_index": list(map(int, index)),
            "actual_at_max": float(actual[index]), "delivered_at_max": float(expected[index])}


def differences(actual, saved, path=""):
    if type(actual) != type(saved):
        return [{"path": path, "actual": actual, "saved": saved}]
    if isinstance(actual, dict):
        if actual.keys() != saved.keys():
            return [{"path": path, "actual_keys": list(actual), "saved_keys": list(saved)}]
        return [r for k in actual for r in differences(actual[k], saved[k], f"{path}/{k}")]
    if isinstance(actual, list):
        if len(actual) != len(saved):
            return [{"path": path, "actual_len": len(actual), "saved_len": len(saved)}]
        return [r for i, (a, b) in enumerate(zip(actual, saved)) for r in differences(a, b, f"{path}/{i}")]
    return [] if actual == saved else [{"path": path, "actual": actual, "saved": saved}]


def diagnose(package, anchor):
    manifest = authenticate(package, anchor)
    model = load_frozen(package)
    configure()
    inputs = np.load(package / "golden/z_s0.npy", allow_pickle=False)
    original = np.load(package / "golden/reference_logits.npy", allow_pickle=False)
    full, activations, direct = references(model, inputs)
    # The first dense layer's reference uses the exact delivered s8 and frozen
    # weights. Float64 is a diagnostic oracle, not a replacement model/backend.
    flat = np.load(package / "golden/z_s8.npy", allow_pickle=False).reshape(20, -1)
    linear = model.classifier[2]
    weight = linear.weight.detach().numpy()
    bias = linear.bias.detach().numpy()
    dense64 = np.maximum(flat.astype(np.float64) @ weight.astype(np.float64).T + bias.astype(np.float64), 0)
    saved9 = np.load(package / "golden/z_s9.npy", allow_pickle=False)
    ops = []
    with torch.inference_mode():
        for index, module in enumerate(model.classifier):
            source = torch.from_numpy(np.load(package / "golden/z_s8.npy", allow_pickle=False)[0:1])
            for previous in list(model.classifier)[:index]:
                source = previous(source)
            result = module(source)
            ops.append({"path": f"classifier.{index}", "type": type(module).__name__,
                        "input_shape": list(source.shape), "input_stride": list(source.stride()),
                        "output_shape": list(result.shape)})
    identities = samples(package)
    # Deliberately compare all 200 ORT results to delivered Windows logits.
    evidence = numerics(package, model, original, identities)
    evidence["direct_head_tail_worst"] = {str(s): max(v) for s, v in direct.items()}
    linux_evidence = numerics(package, model, full, identities)
    linux_evidence["direct_head_tail_worst"] = {str(s): max(v) for s, v in direct.items()}
    saved = read_json(package / "evidence/numerical_verification.json")
    return {"package": str(package), "anchor": anchor, "platform": platform.platform(),
            "machine": platform.machine(), "cpu": platform.processor(), "versions": versions(),
            "manifest_versions": manifest["dependency_versions"], "torch_build": torch.__config__.show(),
            "torch_parallel": torch.__config__.parallel_info(),
            "backend": {"device": "cpu", "threads": torch.get_num_threads(),
                        "deterministic": torch.are_deterministic_algorithms_enabled(),
                        "mkldnn": torch.backends.mkldnn.enabled,
                        "environment": {k: os.environ.get(k) for k in ("MKL_CBWR", "MKL_ENABLE_INSTRUCTIONS", "ATEN_CPU_CAPABILITY", "OMP_NUM_THREADS")}},
            "activations": {str(s): measure(activations[s], np.load(package / f"golden/z_s{s}.npy", allow_pickle=False)) for s in range(11)},
            "logits": measure(full, original), "dense_operations": ops,
            "dense64_oracle": {"recomputed_max_abs_error": float(np.max(np.abs(activations[9].astype(np.float64) - dense64))),
                               "delivered_max_abs_error": float(np.max(np.abs(saved9.astype(np.float64) - dense64)))},
            "onnx_vs_original_reference": evidence,
            "evidence_recomputed_vs_saved_differences": differences(linux_evidence, saved)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--dense-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps((dense_probe if args.dense_only else diagnose)(args.package.resolve(), args.expected_manifest_sha256), indent=2, allow_nan=False))
