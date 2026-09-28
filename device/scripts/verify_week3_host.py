"""Compile the firmware FP32 head on the host and compare sample 0 at each milestone."""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from generate_week3_inputs import TRUSTED_MANIFEST, generate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    package = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    source = repo / "device/src/week3_head.c"
    header = repo / "device/generated/week3_inputs.h"
    generate(package, header)
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("Host GCC is required for sample 0 verification")
    with tempfile.TemporaryDirectory(prefix="sv1_week3_host_") as directory:
        library = Path(directory) / "week3_head.dll"
        command = [compiler, "-std=c99", "-O2", "-ffp-contract=off", "-Wall", "-Wextra",
                   "-Werror", "-shared", "-I", str(package / "firmware"),
                   "-I", str(repo / "device/src"), str(source), "-o", str(library)]
        subprocess.run(command, check=True)
        head = ctypes.CDLL(str(library))
        pointer = np.ctypeslib.ndpointer(dtype=np.float32, flags="C_CONTIGUOUS")
        for name, count in (("week3_conv1", 2), ("week3_conv2", 2), ("week3_pool", 2)):
            function = getattr(head, name)
            function.argtypes = [pointer] * count
            function.restype = None
        head.week3_relu.argtypes = [pointer, ctypes.c_uint]
        head.week3_relu.restype = None
        m0 = np.ascontiguousarray(np.load(package / "inputs.npy", allow_pickle=False)[0, 0])
        m1 = np.empty((16, 360), dtype=np.float32)
        head.week3_conv1(m0, m1)
        actual = {"M1": m1.copy()}
        head.week3_relu(m1, m1.size)
        actual["R1"] = m1.copy()
        m2 = np.empty_like(m1)
        head.week3_conv2(m1, m2)
        actual["M2"] = m2.copy()
        head.week3_relu(m2, m2.size)
        actual["R2"] = m2.copy()
        p2 = np.empty((16, 180), dtype=np.float32)
        head.week3_pool(m2, p2)
        actual["P2"] = p2.copy()
        if os.name == "nt":
            import _ctypes
            _ctypes.FreeLibrary(head._handle)
            del head
    with (package / "samples.csv").open(encoding="utf-8", newline="") as stream:
        sample_id = next(csv.DictReader(stream))["sample_id"]
    errors = {}
    for milestone, tensor in actual.items():
        golden = np.load(package / "golden" / f"{milestone}.npy", allow_pickle=False)[0]
        if tensor.shape != golden.shape or not np.isfinite(tensor).all():
            raise ValueError(f"{milestone}: invalid shape or non-finite result")
        errors[milestone] = float(np.max(np.abs(tensor.astype(np.float64) - golden.astype(np.float64))))
        print(f"{milestone}: shape={tensor.shape} max_abs_error={errors[milestone]:.9g}")
    result = {"handoff_id": package.name, "manifest_sha256": TRUSTED_MANIFEST,
              "sample_index": 0, "sample_id": sample_id, "max_abs_error": errors,
              "threshold": 1e-3, "status": "PASS" if all(error < 1e-3 for error in errors.values()) else "FAIL"}
    report = repo / "device/reports/week3_host_sample0.json"
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"HOST_SAMPLE0: {result['status']}; report={report}")
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
