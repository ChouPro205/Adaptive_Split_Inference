"""Compile the actual firmware C and check all 20 samples x 11 R3 splits."""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from generate_week4_inputs import ALL_SPLIT_MANIFEST, PACKAGE, R3, WEEK4_MANIFEST, generate, sha256
from generate_week3_inputs import check_inventory
from week4_handoff import R4, authenticate_handoff


class Shape(ctypes.Structure):
    _fields_ = [("rank", ctypes.c_uint), ("dims", ctypes.c_uint * 3), ("count", ctypes.c_uint)]


class Result(ctypes.Structure):
    _fields_ = [("values", ctypes.POINTER(ctypes.c_float)), ("shape", Shape)]


class Command(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("sample", ctypes.c_uint), ("split", ctypes.c_uint)]


def host_source_hashes(repo: Path, source_revision: str) -> dict[str, str]:
    sources = [
        "device/src/week4_head.c", "device/src/week4_head.h",
        "device/src/week4_protocol.c", "device/src/week4_protocol.h",
        "device/src/week3_head.c", "device/src/week3_head.h",
        "device/scripts/verify_week4_host.py", "device/scripts/generate_week4_inputs.py",
        "device/scripts/generate_week3_inputs.py", "device/scripts/week4_handoff.py",
        "tools/week4_handoff_auth.py",
        R3 + "/manifest.json", R3 + "/firmware/head_parameters.h",
        "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/firmware/head_parameters.h"]
    source_manifest = repo / (R4 if source_revision == "r4" else R3) / "manifest.json"
    sources.append(source_manifest.relative_to(repo).as_posix())
    sources.extend(e["path"] for e in json.loads(source_manifest.read_text(encoding="utf-8"))["source_files"])
    return {name: sha256(repo / name) for name in sources}


def validate_reuse(report: dict, authentication: dict, source_hashes: dict, generated_hashes: dict) -> None:
    expected = {"status": "PASS", "scope": "HOST_C_ONLY", "threshold_strict": 1e-3,
                "primary_tensors": 220, "reverse_order_tensors": 220, "week3_p2_bitwise_samples": 20,
                "week4_manifest_sha256": WEEK4_MANIFEST, "all_split_manifest_sha256": ALL_SPLIT_MANIFEST,
                "handoff_authentication": authentication, "source_sha256": source_hashes,
                "generated_sha256": generated_hashes, "skips": []}
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"Host verification report is stale or unsupported: {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--report-dir", type=Path, default=Path("D:/HUST/SV3_week4_R4/sv1-integration/host"))
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--source-revision", choices=("r3", "r4"), default="r4")
    parser.add_argument("--expected-source-anchor")
    parser.add_argument("--reuse-report", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    generated = report_dir / "generated"
    manifest, splits, graph, inputs, ids = generate(repo, args.source_revision, args.expected_source_anchor, generated)
    _, _, authentication = authenticate_handoff(repo, args.source_revision, args.expected_source_anchor)
    source_hashes = host_source_hashes(repo, args.source_revision)
    generated_hashes = {str(generated / name): sha256(generated / name) for name in ("week4_graph.h", "week4_inputs.h")}
    if args.reuse_report:
        report = json.loads((report_dir / "week4_host_validation.json").read_text(encoding="utf-8"))
        validate_reuse(report, authentication, source_hashes, generated_hashes)
        print("HOST_C: reuse PASS for complete current source / historical R3 / generated bindings")
        return
    compiler = shutil.which(args.compiler)
    if compiler is None:
        raise RuntimeError("Host compiler missing; cannot report host PASS")
    commands = []
    libraries = []

    def compile_c(name: str, sources: list[str], includes: list[Path]) -> ctypes.CDLL:
        library = report_dir / (name + (".dll" if os.name == "nt" else ".so"))
        command = [compiler, "-std=c99", "-O2", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-shared"]
        if os.name != "nt":
            command.append("-fPIC")
        for include in includes:
            command.extend(["-I", str(include)])
        command.extend([str(repo / source) for source in sources] + ["-o", str(library)])
        subprocess.run(command, check=True)
        commands.append(command)
        dll = ctypes.CDLL(str(library))
        libraries.append(dll)
        return dll

    head = compile_c("week4_head", ["device/src/week4_head.c", "device/src/week4_protocol.c"],
                     [repo / "device/src", generated, repo / R3 / "firmware"])
    head.week4_run_head.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(Result)]
    head.week4_run_head.restype = ctypes.c_int
    head.week4_get_shape.argtypes = [ctypes.c_uint, ctypes.POINTER(Shape)]
    head.week4_get_shape.restype = ctypes.c_int
    head.week4_parse_command.argtypes = [ctypes.c_char_p, ctypes.POINTER(Command)]
    head.week4_parse_command.restype = ctypes.c_int
    golden = [np.load(repo / PACKAGE / s["golden_path"], allow_pickle=False) for s in splits["splits"]]
    rows = []
    primary = [(n, s) for n in range(20) for s in range(11)]
    # Same buffers, reversed sample and split order, with no workspace reset.
    for phase, matrix in (("forward", primary), ("reverse", list(reversed(primary)))):
        for sample, split in matrix:
            pointer = inputs[sample].ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            before = inputs[sample].copy()
            result = Result()
            if head.week4_run_head(split, pointer, ctypes.byref(result)) != 0:
                raise ValueError("Firmware rejected valid sample/split")
            shape = tuple(result.shape.dims[:result.shape.rank])
            expected_shape = tuple(splits["splits"][split]["shape_N1"])
            if shape != expected_shape or result.shape.count != math.prod(shape):
                raise ValueError(f"Shape mismatch sample={sample} split={split}")
            actual = np.ctypeslib.as_array(result.values, shape=(result.shape.count,)).copy().reshape(shape)
            expected = golden[split][sample:sample + 1]
            if actual.shape != expected.shape or not np.isfinite(actual).all():
                raise ValueError("Invalid shape or non-finite result")
            error = float(np.max(np.abs(actual.astype(np.float64) - expected.astype(np.float64))))
            if not error < 1e-3:
                raise ValueError(f"Strict tolerance failed n={sample} s={split}: {error}")
            if not np.array_equal(before.view(np.uint32), inputs[sample].view(np.uint32)):
                raise ValueError("Kernel modified original input")
            if split == 0 and ctypes.addressof(result.values.contents) != pointer_address(pointer):
                raise ValueError("Identity head should alias original input")
            rows.append({"phase": phase, "sample_index": sample, "sample_id": ids[sample], "split": split,
                         "shape": list(shape), "max_abs_error": error, "finite": True, "status": "PASS"})
    # Invalid API calls must not return stale data.
    pointer = inputs[0].ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    for split, source in ((11, pointer), (0xFFFFFFFF, pointer), (0, None), (10, None)):
        result = Result(pointer, Shape())
        if head.week4_run_head(split, source, ctypes.byref(result)) != -1 or bool(result.values):
            raise ValueError("Invalid head call retained an output")
    if head.week4_run_head(0, pointer, None) != -1:
        raise ValueError("Null result must be rejected")
    for split in range(11):
        shape = Shape()
        if head.week4_get_shape(split, ctypes.byref(shape)) != 0 or list(shape.dims[:shape.rank]) != splits["splits"][split]["shape_N1"]:
            raise ValueError("Shape query failed")
    if head.week4_get_shape(11, ctypes.byref(Shape())) != -1 or head.week4_get_shape(0, None) != -1:
        raise ValueError("Invalid shape query accepted")
    valid_commands = 0
    for sample, split in primary:
        for token, kind in (("RUN", 0), ("BENCH", 1)):
            result = Command()
            if head.week4_parse_command(f"{token} {sample} {split}".encode(), ctypes.byref(result)) != 0 or (result.type, result.sample, result.split) != (kind, sample, split):
                raise ValueError("Valid wire command failed")
            valid_commands += 1
    invalid_commands = [b"", b"RUN", b"RUN 0", b"RUN 20 0", b"RUN 0 11", b"RUN -1 0", b"RUN 0 -1",
                        b"BENCH 4294967296 0", b"RUN 0 9999999999999999999", b"RUN 0 0 junk", b"RUN 0 0 ",
                        b"RUN  0 0", b"RUN 0  0", b"TRACE 0 0", b"RUN 0 0\n", None]
    for command in invalid_commands:
        if head.week4_parse_command(command, ctypes.byref(Command())) != -1:
            raise ValueError(f"Invalid command accepted: {command!r}")
    if head.week4_parse_command(b"RUN 0 0", None) != -1:
        raise ValueError("Null command output accepted")
    # Direct compatibility comparison with the unmodified Week 3 C kernels.
    old_package = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    check_inventory(old_package)
    old = compile_c("week3_compat", ["device/src/week3_head.c"], [repo / "device/src", old_package / "firmware"])
    array_arg = np.ctypeslib.ndpointer(dtype=np.float32, flags="C_CONTIGUOUS")
    for name in ("week3_conv1", "week3_conv2", "week3_pool"):
        getattr(old, name).argtypes = [array_arg, array_arg]
        getattr(old, name).restype = None
    old.week3_relu.argtypes = [array_arg, ctypes.c_uint]
    old.week3_relu.restype = None
    old_inputs = np.load(old_package / "inputs.npy", allow_pickle=False)
    if not np.array_equal(inputs.view(np.uint32), old_inputs.view(np.uint32)):
        raise ValueError("R3 input order/bytes differ from Week 3 v2")
    for sample in range(20):
        a = np.empty((16, 360), np.float32)
        b = np.empty_like(a)
        p2 = np.empty((16, 180), np.float32)
        old.week3_conv1(inputs[sample], a)
        old.week3_relu(a, a.size)
        old.week3_conv2(a, b)
        old.week3_relu(b, b.size)
        old.week3_pool(b, p2)
        result = Result()
        head.week4_run_head(2, inputs[sample].ctypes.data_as(ctypes.POINTER(ctypes.c_float)), ctypes.byref(result))
        actual = np.ctypeslib.as_array(result.values, shape=(2880,)).reshape(16, 180)
        if not np.array_equal(actual.view(np.uint32), p2.view(np.uint32)):
            raise ValueError("R3 s=2 differs bitwise from Week 3 C P2")
    mapping = []
    for split in splits["splits"]:
        ops = graph["ops"][:len(split["head_operations"])]
        current = "input (Flash)"
        for op in ops:
            if op["type"] in ("Conv1d", "MaxPool1d", "Linear"):
                current = "B" if current == "A" else "A"
        params = [p for op in ops for p in op["parameters"]]
        mapping.append({"split": split["split_id"], "head_operations": split["head_operations"],
                        "shape": split["shape_N1"], "layout": split["layout"],
                        "output_bytes": 4 * math.prod(split["shape_N1"]), "output_buffer": current,
                        "weights": [p["c_name"] for p in params],
                        "weight_bytes": sum(p["logical_tensor_bytes"] for p in params)})
    maxima = {str(s): max(r["max_abs_error"] for r in rows if r["split"] == s) for s in range(11)}
    report = {"status": "PASS", "scope": "HOST_C_ONLY", "mcu_validation": "PENDING", "mcu_timing": "PENDING",
              "week4_manifest_sha256": WEEK4_MANIFEST, "all_split_manifest_sha256": ALL_SPLIT_MANIFEST,
              "handoff_authentication": authentication,
              "generated_sha256": generated_hashes,
              "compiler": compiler, "compiler_version": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
              "python_version": sys.version, "compile_commands": commands, "threshold_strict": 1e-3,
              "primary_tensors": 220, "reverse_order_tensors": 220, "week3_p2_bitwise_samples": 20,
              "valid_command_checks": valid_commands, "invalid_command_checks": len(invalid_commands) + 1,
              "source_sha256": source_hashes, "max_abs_error_by_split": maxima, "rows": rows, "skips": [], "mapping": mapping}
    (report_dir / "week4_host_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# R3 split mapping and buffer design", "", f"Manifest `{WEEK4_MANIFEST}`; graph: 25 ops.", "",
             "Each row is the complete head prefix, read directly from the accepted split manifest.", "",
             "| s | Head operations | Shape/layout | Output bytes/buffer | Cumulative weights (bytes) |",
             "|---|---|---|---|---|"]
    for m in mapping:
        lines.append(f"| {m['split']} | {', '.join(m['head_operations']) or 'identity input'} | {'x'.join(map(str, m['shape']))} {m['layout']} | {m['output_bytes']} / {m['output_buffer']} | {', '.join(m['weights']) or 'none'} ({m['weight_bytes']}) |")
    lines.extend(["", "Two static activation arrays: A and B, each 5760 FP32 = 23040 bytes; total 46080 bytes.",
                  "Conv/pool/linear alternate A/B. ReLU uses the current array; flatten and eval Dropout preserve it.",
                  "The preceding activation dies after the next materialized operation. Returned data lives until the next call.",
                  "s=0 borrows immutable input; inputs = 20*360*4 = 28800 Flash bytes. Weights = 438612 Flash bytes.",
                  "All splits restart from input. Main stack configured at 4096 bytes; no activation arrays on stack.",
                  "Timing samples = 100*4 = 400 static RAM bytes. Zephyr/USB/stacks are included in linker usage.",
                  "MCU validation, timing and stack high-water are PENDING."])
    (report_dir / "split_mapping.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for split, error in maxima.items():
        print(f"s={split}: max_abs_error={error:.9g} PASS")
    print(f"HOST_C: PASS 220/220 + reverse 220/220; Week 3 P2 bitwise 20/20; SKIP=0; MCU=PENDING")
    print(f"REPORT: {report_dir / 'week4_host_validation.json'}")
    if os.name == "nt":
        import _ctypes
        for library in libraries:
            _ctypes.FreeLibrary(library._handle)


def pointer_address(pointer: ctypes.POINTER(ctypes.c_float)) -> int:
    return ctypes.addressof(pointer.contents)


if __name__ == "__main__":
    main()
