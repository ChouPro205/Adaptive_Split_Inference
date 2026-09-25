"""Export a new immutable FP32 revision; open boundaries permit review only."""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np

from week3_common import (CONTRACT, SOURCE, CHECKPOINT, FIELDS, check_decision,
    compiler_verify, header, inventory, load_model, need, read_json, repo_imports,
    sha, source_and_data, text, trace, versions, write_json)


def export(repo, decision_path, handoff_id, output_parent=None, review=False, compiler="gcc"):
    repo = repo_imports(repo)
    decision = read_json(decision_path)
    boundary = check_decision(decision, review)
    need(re.fullmatch(r"[a-z0-9_-]+", handoff_id) is not None, "Invalid handoff_id")
    parent = Path(output_parent).resolve() if output_parent else repo / (
        "ml/data/week3_review" if review else "ml/artifacts/week3")
    package = parent / handoff_id
    need(not package.exists(), "Immutable revision already exists; choose a new ID/location")
    if review:
        release_root = repo / "ml/artifacts/week3"
        need(release_root != package and release_root not in package.parents,
             "Review package cannot be placed in release directory")
    # Recompute the selected historical metrics and verify all run/source hashes.
    from verify_week2_baseline import verify as verify_historical
    historical = verify_historical(historical=True)
    source_path = repo / "ml/src/mitdb_baseline_model.py"
    checkpoint_path = repo / decision["checkpoint_path"]
    model, checkpoint = load_model(checkpoint_path, source_path)
    samples, inputs, upstream, identifiers = source_and_data(repo, checkpoint)
    # All decision/source/data gates above run before creating any package files.
    package.mkdir(parents=True, exist_ok=False)
    with (package / "inputs.npy").open("wb") as f:
        np.lib.format.write_array(f, inputs, version=(1, 0), allow_pickle=False)
    # Golden must use the delivered file, including its canonical loaded strides.
    inputs = np.load(package / "inputs.npy", allow_pickle=False)
    graph, parameters, golden = trace(model, inputs, boundary)
    graph["boundary_status"] = "PROPOSAL_ONLY" if review else "CONFIRMED"
    (package / "model").mkdir()
    shutil.copyfile(checkpoint_path, package / "model/checkpoint.pt")
    write_json(package / "model/train_config.json", checkpoint["training_config"])
    write_json(package / "model/freeze_decision.json", decision)
    write_json(package / "model/graph.json", graph)
    source_files = {}
    for relative in (*checkpoint["provenance"]["source_files_sha256"],
                     "ml/src/week1_common.py", "ml/src/mitdb_common.py"):
        blob = subprocess.check_output(["git", "show", f"{SOURCE}:{relative}"], cwd=repo)
        target = package / "model/source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        source_files[relative] = {"path": target.relative_to(package).as_posix(), "sha256": sha(target)}
    for key, array in {**parameters,
                       **{f"golden/{k}.npy": v for k, v in golden.items()}}.items():
        path = package / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            np.lib.format.write_array(f, array, version=(1, 0), allow_pickle=False)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(samples)
    text(package / "samples.csv", stream.getvalue())
    text(package / "firmware/head_parameters.h", header(graph, parameters))
    compiled = compiler_verify(package, graph, parameters, compiler)
    write_json(package / "firmware/host_c_verification.json", compiled)
    for name in ("export_week3.py", "verify_week3.py", "week3_common.py", "test_week3.py"):
        text(package / "scripts" / name, Path(__file__).with_name(name).read_text(encoding="utf-8"))
    manifest = {
        "contract_version": CONTRACT, "handoff_id": handoff_id,
        "release_status": "REVIEW_ONLY_M_FINAL_UNCONFIRMED" if review else "SV3_RELEASE_PACKAGE",
        "model_name": decision["model_name"], "model_version": decision["model_version"],
        "dataset_profile": decision["dataset_profile"], "precision": "fp32",
        "quantization": "not_applicable", "source_commit": SOURCE,
        "sv1_acceptance": {"package_review": "PENDING", "mcu_validation": "PENDING",
                           "mcu_20_of_20": "NOT_YET_TESTED"},
        "checkpoint": {"path": "model/checkpoint.pt", "sha256": CHECKPOINT,
            "size_bytes": checkpoint_path.stat().st_size,
            "type": "full checkpoint dictionary; state_dict + epoch + validation + provenance + config + architecture",
            "selected_epoch": checkpoint["epoch"], "load": "torch.load(weights_only=True, map_location='cpu')"},
        "train_config": {"path": "model/train_config.json", "sha256": sha(package / "model/train_config.json"),
            "origin": "checkpoint.training_config; UTF-8 LF snapshot; identical parsed settings"},
        "framework": "PyTorch", "dependency_versions": versions(),
        "historical_runtime": {k: checkpoint["provenance"][k] for k in
            ("python_version", "torch_version", "cuda_version", "device", "device_name")},
        "seed": checkpoint["provenance"]["seed"], "eval": True,
        "historical_verification": historical, "model_source_files": source_files,
        "upstream": upstream, "week1_dataset_artifacts": identifiers,
        "selection": decision["sample_selection"],
        "preprocessing": ["WFDB physical MLII selected by name at 360 Hz",
            "expert R-peak window [r-180:r+180); drop incomplete boundary windows; unchanged AAMI mapping",
            "Week 1 train-only scalar Z-score, then float32; no refit",
            "select existing val rows using frozen rule; view (20,1,360); no additional transform or second normalization"],
        "graph": "model/graph.json", "M_final": boundary,
        "boundary_status": graph["boundary_status"], "memory": graph["memory"],
        "file_hash_policy": "sha256_raw_bytes", "text_encoding": "UTF-8 LF without BOM",
        "onnx_status": "BLOCKED_ON_SV2_INTERFACE",
    }
    review_flag = " --review" if review else ""
    milestone_table = "\n".join(f"| {k} | {v['hook']} | {v['shape']} | {v['size_bytes']} |"
                                for k, v in graph["milestones"].items())
    state = "REVIEW ONLY: M_final is a proposal, not confirmed by SV3/SV1." if review else (
        "Official SV3 release package. SV1 package review and MCU validation PENDING; MCU 20/20 NOT YET TESTED.")
    recipient_path = "ml/" + ("data/week3_review/" if review else "artifacts/week3/") + handoff_id
    readme = f'''# {handoff_id}

**{state}**

Model `{decision['model_name']}`, version `{decision['model_version']}`, MIT-BIH/1.0.0,
FP32, 10 learned layers (8 Conv1d + 2 Linear), 5 output classes. Checkpoint
`model/checkpoint.pt` is copied unchanged from the historical full checkpoint,
SHA-256 `{CHECKPOINT}`, epoch 3, seed 30, source commit `{SOURCE}`.
Exact config is `model/train_config.json`; historical model/train/helper source
blobs are included in `model/source/`. Dependency versions and historical CUDA
runtime are in `manifest.json`. Golden uses CPU, N=1, one thread, deterministic
algorithms, MKLDNN disabled, `eval()` and inference mode.
Quantization is `not_applicable`: no INT8 scale, zero point, axis, clamp or
requantization parameters are part of this FP32 handoff.

Suggested recipient location, relative to repository root: `{recipient_path}`.
Transfer the entire folder outside Git; raw data is not included. This ID is
immutable: never edit files inside this folder. A changed decision, graph,
checkpoint, input, golden or script requires a new ID and complete export.

## Graph and MCU representation

Executed head: Conv1 (`features.0`) → ReLU (`features.1`) → Conv2 (`features.2`)
{'→ ReLU (`features.3`)' if boundary in ('R2','P2') else ''}
{'→ MaxPool1d (`features.4`)' if boundary == 'P2' else ''}.
`M1`/`M2` are immediately after the effective convolutions. `M_final={boundary}`
{'is only the proposed boundary' if review else 'is the confirmed boundary'}.
Graph records every op, parameter key, actual shape, padding and pool setting.
No BatchNorm, folding, reshape, transpose, residual or other op occurs in this
exported head. Both Conv biases are present and applied before ReLU.

| Milestone | Hook | Delivered shape | Tensor bytes (20 samples) |
|---|---|---|---:|
{milestone_table}

Inputs/activations are NCL `<f4`, C-contiguous; offset `((n*C+c)*L+l)`.
Weights are `(C_out,C_in/groups,K)`; offset `((oc*(C_in/groups)+ic_local)*K+k)`.
Bias index is `oc`. The C99 header uses `static const float` and exact hex-float
literals with `f` suffix. Shape/count constants accompany all four arrays.
`firmware/host_c_verification.json` records host compiler and compiled-bit check;
this is not an nRF52840 firmware build.

Parameter Flash (logical): {graph['memory']['parameter_total_bytes']} bytes.
Per-Conv bytes: {graph['memory']['per_conv_bytes']}.
Largest activation N=1: {graph['memory']['largest_intermediate_bytes_N1']} bytes.
Two full-size ping-pong buffers: {graph['memory']['two_activation_buffers_bytes_N1']} bytes.
Firmware code, alignment, stack and kernel workspace are additional and unmeasured.

## Exactly 20 sources and preprocessing

Use `samples.csv` rows 0–19 in the existing validation split, sorted numerically
by record and R-peak, then lead name. No seed or added exclusion; duplicate source
keys fail. IDs use `MIT-BIH:record_id:r_peak_sample:lead_name`. Original processed
row index and path are recorded; upstream hashes remain under Week 1's normalized
UTF-8/LF text policy, while binary and delivered-file hashes use raw bytes.
This is deterministic kernel debugging data, not a class-balanced accuracy set.

Week 1 selects MLII by name, segments 360 points at expert R-peaks, drops incomplete
windows, applies the existing train-only scalar Z-score and casts to float32.
`inputs.npy` already contains that result: do not normalize it again. Export and
verify reconstruct each selected sample from checksummed raw ECG and compare bits.

## Exact commands (PowerShell, from repository root)

Authenticate the manifest with a digest obtained from trusted repository evidence
or PR, never from the received package. Run the verifier from your trusted checkout
(`ml/scripts/verify_week3.py`) before executing any bundled script.
Release requires `--expected-manifest-sha256` before JSON parsing. Review mode may
omit it for unauthenticated technical checks only; it never grants release eligibility.
Current checks also pin model name/version and require all four scripts. Historical
r2 retains its original scripts/labels and is not relabelled to satisfy these checks.

External requirements: preserved Week 1 raw MIT-BIH and processed arrays/metadata,
the historical Git commit, Week 2 artifacts, pinned `ml/.venv`, and host GCC on PATH.
The repo scientific sources must be tracked and clean. No download/rebuild/train
is performed. The original Week 2 CUDA environment is required for export's
historical metric verification. Tensor verification itself uses CPU.

```powershell
$pkg = '{recipient_path}'
$trustedManifestSha = '<copy the independently trusted digest from versioned release evidence or PR>'
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3.py --repo-root . --package $pkg --expected-manifest-sha256 $trustedManifestSha{review_flag}
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3.py --repo-root . --package $pkg --expected-manifest-sha256 $trustedManifestSha
& ml/.venv/Scripts/python.exe -B "$pkg/scripts/export_week3.py" --repo-root . --decision "$pkg/model/freeze_decision.json" --handoff-id {handoff_id}-repro{review_flag}
```

The third command creates a fresh ID; it refuses overwrite. Input/parameter/golden
bytes must reproduce; ID and location fields intentionally describe the new revision.
{'Omitting --review must fail: no released handoff exists until M_final is confirmed.' if review else ''}

For sample 0 debugging on the PC:

```python
import csv
from pathlib import Path
import numpy as np
p = Path(r"{recipient_path}")
with (p / "samples.csv").open(encoding="utf-8", newline="") as f:
    row = next(csv.DictReader(f))
x0 = np.load(p / "inputs.npy", allow_pickle=False)[0]  # (1,360), already normalized
y0 = np.load(p / "golden/M1.npy", allow_pickle=False)[0]
print(row["sample_id"], x0.shape, y0.shape)
```

Do not copy the `.npy` file header into MCU tensor buffers. SV1 chooses streaming
or storage, retaining sample IDs and exact FP32 values. Debug Conv1 against M1
first, then R1, M2 and trailing milestones. Dump complete MCU arrays without decimal
precision loss, reshape using graph metadata, reject missing/non-finite values,
then compare every element for the same ID/index/milestone. Record each milestone's
`max(abs(MCU-PyTorch))`. At the confirmed M_final every one of 20 samples must be
strictly below `1e-3`; intermediate errors help locate faults. No MCU PASS is claimed.

## Open items

{'M_final awaits SV3/SV1 confirmation; this review cannot pass release verification.' if review else 'SV1 device feasibility and the 20-sample MCU acceptance record remain outstanding.'}
ONNX: BLOCKED_ON_SV2_INTERFACE (path, opset/runtime, tensor names, dimensions,
full/tail profile, output semantics, preprocessing ownership and comparison procedure).
No Week 4 profiling, P1, INT8, privacy attack or controller is included.
'''
    text(package / "README.md", readme)
    manifest["files"] = inventory(package)
    write_json(package / "manifest.json", manifest)
    from verify_week3 import verify
    verify(package, repo, review=review, compiler=compiler,
           expected_manifest_sha256=sha(package / "manifest.json"))
    return package


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--decision", type=Path, required=True)
    p.add_argument("--handoff-id", required=True)
    p.add_argument("--output-parent", type=Path)
    p.add_argument("--review", action="store_true")
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    package = export(a.repo_root, a.decision, a.handoff_id, a.output_parent, a.review, a.compiler)
    print(f"MANIFEST_SHA256: {sha(package / 'manifest.json')}")
    print(f"{'REVIEW_CHECKS_PASS (NOT A RELEASE)' if a.review else 'HANDOFF_CHECKS_PASS'}: {package}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
