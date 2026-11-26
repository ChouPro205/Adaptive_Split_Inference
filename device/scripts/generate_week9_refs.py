#!/usr/bin/env python3
"""Week 9 host references (W9-D6): q/scale of the 50 W8-D3 samples (set_index 0..49) at every s.

The dongle path is reproduced on the host: device/week9/host_test/dev_shim.c + device/week7/head_fast.c
(bit-identical to week 4, TC7 of week 7) + device/week5/quantization.c, gcc with the firmware's
numerics flags (-ffp-contract=off -fno-fast-math), the same steps as dev_cycle.c dev_head(). Gates:
the shape and payload bytes (int8 + FP16 scale) of every s equal results/week5/device/tensor_sizes.csv,
and at s=2 the q/scale SHA-256 equal samples.csv of the W8-D3 set (computed there by another shim).
The tail is not run (week 9 part A has no tail), so neither PyTorch nor ml/.venv is needed.

Writes into a new --output directory:
  refs.csv       per (sample, split): identity, shape, bytes, q/scale SHA-256 (550 rows)
  manifest.json  sources, set, checks, SHA-256 of every output and source
refs.csv is deterministic (manifest.json records time and git state).
Host evidence only: not MCU evidence (that is VERIFY ALL on the dongle, TC2).
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\generate_week9_refs.py --samples <W8-D3 dir> --output <new dir>
"""
from __future__ import annotations

import argparse
import csv
import ctypes as ct
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week9_common as w9  # noqa: E402

ROOT = w9.ROOT
w8 = w9.w8
WEEK7 = ROOT / "device" / "week7"
WEEK9 = ROOT / "device" / "week9"
SHIM = WEEK9 / "host_test" / "dev_shim.c"
R3_FIRMWARE = ROOT / "ml" / "results" / "week4-r3" / "firmware"
# Same anchors as build_week7.ps1 .. build_week9.ps1 (results/week4 + week5 acceptance).
ANCHORS = {
    R3_FIRMWARE / "head_parameters.h": "3f811758ca6fc6a8fdefa74ff50ccb48031c006e9a12b617604dad033657487b",
    ROOT / "device" / "generated" / "week4_graph.h": "b91b5cd664cae32f03e49b91669bb337fbea950c575d2b0a0da8959818d37b6c",
}
SOURCES = [SHIM, WEEK7 / "head_fast.c", WEEK7 / "head_fast.h", ROOT / "device" / "src" / "week4_head.c",
           ROOT / "device" / "src" / "week4_head.h", ROOT / "device" / "week5" / "quantization.c",
           ROOT / "device" / "week5" / "quantization.h", w9.TENSOR_SIZES, *ANCHORS]
Q_CAPACITY, SCALE_CAPACITY = 8192, 256


def build_shim(directory: Path, samples: Path, plan: Path | None = None) -> ct.CDLL:
    """dev_shim.c as a shared library (plan: also week9_plan.h, -DWEEK9_SHIM_PLAN)."""
    cc = os.environ.get("CC") or shutil.which("gcc")
    if not cc:
        raise SystemExit("gcc not found (set CC)")
    out = directory / ("dev_shim.dll" if os.name == "nt" else "dev_shim.so")
    cmd = [cc, "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
           "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
           "-I", str(WEEK7), "-I", str(ROOT / "device" / "src"), "-I", str(ROOT / "device" / "generated"),
           "-I", str(ROOT / "device" / "week5"), "-I", str(R3_FIRMWARE), "-I", str(samples)]
    if plan is not None:
        cmd += ["-DWEEK9_SHIM_PLAN", "-I", str(plan)]
    cmd += ["-o", str(out), str(SHIM), str(WEEK7 / "head_fast.c"), str(ROOT / "device" / "week5" / "quantization.c")]
    subprocess.run(cmd, check=True)
    lib = ct.CDLL(str(out))
    lib.shim_set_sha256.restype = ct.c_char_p
    lib.shim_sample_id.restype = ct.c_char_p
    lib.shim_sample_id.argtypes = [ct.c_uint]
    lib.shim_head_quant.argtypes = [ct.c_uint, ct.c_uint, ct.c_char_p, ct.c_uint, ct.c_char_p, ct.c_uint,
                                    ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint)]
    if plan is not None:
        lib.shim_plan_sha256.restype = ct.c_char_p
        lib.shim_plan_splits.restype = ct.POINTER(ct.c_uint8)
    return lib


def head_quant(lib: ct.CDLL, n: int, split: int) -> tuple:
    """(channels, length, q bytes, FP16 LE scale bytes) of sample n at split, from the C path."""
    q = ct.create_string_buffer(Q_CAPACITY)
    scale = ct.create_string_buffer(SCALE_CAPACITY)
    c, length = ct.c_uint(), ct.c_uint()
    status = lib.shim_head_quant(n, split, q, Q_CAPACITY, scale, SCALE_CAPACITY, ct.byref(c), ct.byref(length))
    if status != 0:
        raise SystemExit(f"C head/quantization failed at n={n} s={split}: {status}")
    return c.value, length.value, q.raw[:c.value * length.value], scale.raw[:2 * c.value]


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sources = [p.relative_to(ROOT).as_posix() for p in (Path(__file__).resolve(), HERE / "week9_common.py", SHIM)]
    return {"head": run("rev-parse", "HEAD"), "status_of_generator_sources": run("status", "--short", "--", *sources)}


def generate(samples: Path, output: Path) -> dict:
    if output.exists():
        raise SystemExit("Use a new output directory")
    for path, digest in ANCHORS.items():
        if w8.w7.sha256_file(path) != digest:
            raise SystemExit(f"R3 input {path} differs from the week 4/5 anchor")
    sample_set = w8.load_set(samples)   # authenticates the W8-D3 set
    sizes = w9.tensor_sizes()
    work = Path(tempfile.mkdtemp(prefix="week9_refs_"))
    lib = build_shim(work, samples)
    rows, size_ok, s2_ok = [], [], []
    for n in range(w9.ROUNDS):
        sample = sample_set.samples[n]
        for s in range(w9.SPLITS):
            c, length, q, scale = head_quant(lib, n, s)
            row = {"set_index": n, "sample_id": sample.sample_id, "split": s, "channels": c, "length": length,
                   "bytes_q": len(q), "bytes_scale": len(scale), "bytes_payload": len(q) + len(scale),
                   "q_sha256": w9.sha256_hex(q), "scale_sha256": w9.sha256_hex(scale)}
            size_ok.append((c, length, len(q) + len(scale)) == sizes[s])
            if s == w8.SPLIT:
                s2_ok.append((row["q_sha256"], row["scale_sha256"]) == (sample.q_sha256, sample.scale_sha256))
            rows.append(row)
    checks = {
        "shim_ids_equal_set": all(lib.shim_sample_id(n).decode() == sample_set.samples[n].sample_id
                                  for n in range(w9.ROUNDS)),
        "shim_set_sha256": lib.shim_set_sha256().decode() == sample_set.set_sha256,
        "rows_550": len(rows) == w9.CYCLES,
        "shape_bytes_equal_tensor_sizes": len(size_ok) == w9.CYCLES and all(size_ok),
        "s2_equal_w8d3_samples_csv": len(s2_ok) == w9.ROUNDS and all(s2_ok),
    }
    output.mkdir(parents=True)
    with (output / "refs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=w9.REFS_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    checks["csv_reads_back"] = len(w9.read_refs_csv(output / "refs.csv")) == w9.CYCLES
    status = "PASS" if all(checks.values()) else "FAIL"
    manifest = {
        "schema": "week9-refs/1",
        "status": status,
        "decision": "W9-D6",
        "samples_dir": str(samples),
        "set_sha256": sample_set.set_sha256,
        "samples": f"W8-D3 set_index 0..{w9.ROUNDS - 1}",
        "splits": list(range(w9.SPLITS)),
        "path": "dev_shim.c + week7/head_fast.c + week5/quantization.c, gcc -O2 -ffp-contract=off -fno-fast-math",
        "bytes_payload_by_split": {str(s): sizes[s][2] for s in range(w9.SPLITS)},
        "checks": checks,
        "outputs_sha256": {"refs.csv": w8.w7.sha256_file(output / "refs.csv")},
        "sources_sha256": {p.relative_to(ROOT).as_posix(): w8.w7.sha256_file(p) for p in SOURCES},
        "git": git_state(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory (samples-20261023-c)")
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    args = parser.parse_args()
    manifest = generate(args.samples.resolve(), args.output.resolve())
    for name, ok in manifest["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"outputs_sha256={json.dumps(manifest['outputs_sha256'])}")
    print(f"RESULT: {manifest['status']}")
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
