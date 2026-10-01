"""Export a NEW immutable SV3 FP32 reference package for confirmed splits 0..10."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import torch

from week3_common import need, read_json, sha, text, write_json
from week3_sv2_common import (CHECKPOINT, CONTRACT, MODEL_NAME, MODEL_VERSION, OPSET,
    PREPROCESSING, SOURCE, SV1_MANIFEST, TARGET, TOLERANCE, inventory, load_frozen,
    numerics, references, samples, split_map, versions, wrappers)
from verify_week3_sv2 import SCRIPTS, verify


def export(repo, handoff_id, output_parent=None, compiler="gcc"):
    repo = Path(repo).resolve()
    need(re.fullmatch(r"[a-z0-9_-]+",handoff_id), "Invalid handoff ID")
    parent = Path(output_parent).resolve() if output_parent else repo / "ml/artifacts/week3"
    package = parent / handoff_id
    need(not package.exists(), "Immutable revision already exists; choose a new ID")
    config = read_json(repo / "ml/configs/week3_sv2_interface_review.json")
    need(config["status"]=="CONFIRMED" and config["splits"]==split_map() and config["opset"]==13
         and config["opset_status"]=="CONFIRMED", "Authoritative confirmed interface required")
    # Original raw-derived Week 1 checks run on the unchanged SV1 package first.
    from verify_week3 import verify as verify_sv1
    original = repo / "ml/artifacts/week3/mitdb-week3-fp32-20260925-v2"
    before = {p.relative_to(original).as_posix():sha(p) for p in original.rglob("*") if p.is_file()}
    sv1_result = verify_sv1(original,repo,compiler=compiler,expected_manifest_sha256=SV1_MANIFEST)
    package.mkdir(parents=True,exist_ok=False)
    for name in ("models","golden","model","scripts","evidence","requirements"):
        (package / name).mkdir()
    for name in ("checkpoint.pt","train_config.json","freeze_decision.json"):
        shutil.copyfile(original / "model" / name, package / "model" / name)
    shutil.copyfile(original / "model/source/ml/src/mitdb_baseline_model.py", package / "model/mitdb_baseline_model.py")
    shutil.copyfile(original / "manifest.json",package / "model/sv1_v2_manifest.json")
    shutil.copyfile(original / "samples.csv",package / "samples.csv")
    shutil.copyfile(original / "inputs.npy",package / "golden/z_s0.npy")
    write_json(package / "model/sv2_interface.json",config)
    model = load_frozen(package)
    identities = samples(package)
    full, activations, direct_errors = references(model,np.load(package / "golden/z_s0.npy",allow_pickle=False))
    for s, z in activations.items():
        if s:
            np.save(package / f"golden/z_s{s}.npy",z,allow_pickle=False)
    np.save(package / "golden/reference_logits.npy",full,allow_pickle=False)
    for s in range(10):
        _, tail = wrappers(model,s)
        delivered = np.load(package / f"golden/z_s{s}.npy",allow_pickle=False)
        with torch.inference_mode():
            torch.onnx.export(tail,(torch.from_numpy(delivered[0:1]),),str(package / f"models/tail_{s}.onnx"),
                              opset_version=13,dynamo=False,external_data=False,
                              input_names=["input_activation"],output_names=["logits"],
                              dynamic_axes=None,export_params=True,keep_initializers_as_inputs=False)
    evidence = numerics(package,model,full,identities)
    evidence["direct_head_tail_worst"] = {str(s):max(v) for s,v in direct_errors.items()}
    write_json(package / "evidence/numerical_verification.json",evidence)
    for name in SCRIPTS:
        text(package / "scripts" / name, Path(__file__).with_name(name).read_text(encoding="utf-8"))
    for name in ("requirements-week3-onnx.txt","requirements-core.txt","requirements-gpu-cu130.txt"):
        text(package / "requirements" / name,(repo / "ml" / name).read_text(encoding="utf-8"))
    # Export reproduction uses checkout code, raw data and the unchanged SV1 v2
    # package. Recipient verification is self-contained after dependency setup.
    provenance = {"model_source_commit":SOURCE, "checkpoint_sha256":CHECKPOINT,
                  "sv1_handoff_id":original.name, "sv1_manifest_sha256":SV1_MANIFEST,
                  "sv1_raw_derived_verifier":sv1_result,
                  "exporter_source_sha256":{n:sha(package / "scripts" / n) for n in SCRIPTS},
                  "working_tree_base_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip(),
                  "authority":"Team confirmation relayed by user 2026-10-01", "no_training":True}
    write_json(package / "evidence/source_provenance.json",provenance)
    manifest = {"contract_version":CONTRACT,"handoff_id":handoff_id,
                "status":"SV3_FP32_REFERENCE_HANDOFF_SV2_ACCEPTANCE_PENDING",
                "model_name":MODEL_NAME,"model_version":MODEL_VERSION,"checkpoint_sha256":CHECKPOINT,
                "source_commit":SOURCE,"dataset_profile":"MIT-BIH/1.0.0","selected_epoch":3,
                "splits":split_map(),"opset":OPSET,"opset_status":"CONFIRMED","precision":"fp32",
                "batch_size":1,"dynamic_axes":None,"preprocessing":PREPROCESSING,
                "class_order":["N","S","V","F","Q"],"output_semantics":"pre-softmax AAMI logits; argmax outside graph",
                "tolerance_strict":TOLERANCE,"downstream":TARGET,"samples":identities,
                "dependency_versions":versions(),"onnx_models":evidence["onnx_models"],
                "onnx_exporter":"torch.onnx.export(dynamo=False), native opset 13, embedded FP32 parameters",
                "file_hash_policy":"SHA-256 raw bytes; external manifest hash required"}
    rows = "\n".join(f"| {r['split_id']} | {r['head_endpoint']} | {r['shape_N1']} | {r['layout']} | {r['tail_start']} |" for r in split_map())
    text(package / "README.md",f'''# {handoff_id}

SV3 FP32 reference handoff. Team-confirmed mapping and opset 13. SV2 independent
acceptance PENDING; no VART/KV260/INT8/xmodel PASS is claimed.

Exact model/version {MODEL_NAME}, MIT-BIH/1.0.0, epoch 3. Checkpoint raw SHA-256:
{CHECKPOINT}. Full checkpoint, original model source, training/freeze configs and
confirmed interface are in model/. No retraining or preprocessing changes.

| s | Head endpoint | N=1 activation | Layout | Tail starts |
|---|---|---|---|---|
{rows}

s counts weighted layers only. ReLU stays with the preceding weighted layer;
MaxPool with the preceding even Conv. Flatten/Dropout(eval) prepare layer 9.
s=0 is identity head/full tail; s=10 is full head/identity tail, no ONNX file.
These reference IDs do not redefine I1 wire IDs (wire split_id=0 remains reserved).

models/tail_0.onnx through tail_9.onnx have fixed N=1, FP32 input_activation
and logits output (1,5), pre-softmax class order N/S/V/F/Q. No dynamic axes,
normalization, softmax or argmax. Golden arrays stack 20 samples; feed ONE row
with its batch dimension preserved, e.g. z[i:i+1]. NCL feature maps are C-order;
s=9/10 vectors use NC. samples.csv is byte-identical to SV1 v2. z_s0 is the
already normalized frozen input; z_s2 is byte-identical to accepted P2 golden.

golden/z_s0.npy ... z_s10.npy and reference_logits.npy preserve the same 20 IDs
and ordering. evidence/numerical_verification.json records all 200 FP32 ONNX
comparisons and 20 identity cases; each error is strictly <1e-3. Error maxima
are recorded individually, never averaged. ONNX Runtime CPU is the local
reference verifier; it is not VART or DPU execution.

## Verify after receiving the entire folder or archive

Use Python 3.11.9, the recorded torch 2.14.0+cu130 build and dependencies in
requirements/ (see manifest versions). Torch reference inference uses CPU.
From a trusted repository checkout, install requirements then authenticate
using the manifest hash published OUTSIDE this package in versioned evidence:

```powershell
& ml/.venv/Scripts/python.exe -m pip install -r ml/requirements-gpu-cu130.txt -r ml/requirements-week3-onnx.txt
$pkg = 'ml/artifacts/week3/{handoff_id}'
$trustedSha = '<copy independently trusted manifest SHA-256 from release evidence>'
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3_sv2.py --package $pkg --expected-manifest-sha256 $trustedSha
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3_sv2.py --package $pkg --expected-manifest-sha256 $trustedSha
```

Use trusted checkout verifier code before executing bundled code. Verification
requires no raw dataset: it pins z_s0 and samples bytes to the frozen SV1 v2
hashes, authenticates its original manifest, reconstructs every head/tail from
the checkpoint and checks every saved activation/logit/ONNX result. It does not
refit data or weaken checks to accommodate missing dependencies.

The updated trusted-checkout entry points disable bytecode writes themselves.
Inventory ignores only CPython cache names adjacent to delivered Python sources
in scripts/ and model/; unexpected files and symlinks are still rejected. The
frozen model loader executes hash-authenticated source, never cached bytecode.

For the original immutable SV2 v1, prefer the updated verifier in a trusted
repository checkout, pointing --package at the UNCHANGED v1 directory and using
its independently published manifest SHA-256. Do not copy patched scripts into
v1 or rebuild its manifest. A workaround with original v1 scripts is to extract
the authenticated ZIP into a NEW empty directory and run python -B from the
first invocation, using the exact manifest-pinned environment. -B prevents new
cache writes; it does NOT delete old caches or prevent Python reading them.
A .cpython-312.pyc indicates Python 3.12, not the pinned Python 3.11.9; fixing
inventory does not waive the dependency-version gate. Delivering changed
scripts/README requires a NEW revision ID and new manifest/archive hashes.

For PyTorch reconstruction add scripts/ to sys.path, then use
week3_sv2_common.load_frozen(Path(package)) and wrappers(model,s), which return
the eval head and tail using unchanged original modules. Dropout is inactive.
Full-model logits always come from the original model.forward, independently
of the sequential wrappers used for the split path.

To reproduce with a NEW ID, use checkout ml/scripts/export_week3_sv2.py with
--repo-root . --handoff-id <new-id> --compiler <host-gcc>. Export additionally
requires the untouched SV1 v2 package and frozen Week 1 raw/processed data to
run the original hardened verifier first. Existing IDs are never overwritten.

## SV2 ownership and remaining gates

SV2 checks Vitis AI operator compatibility, quantizes, compiles each applicable
tail to .xmodel for its DPU, runs VART/KV260 and reports independent results.
The FP32 <1e-3 gate must NOT be applied automatically to INT8/DPU outputs;
quantization accuracy/degradation uses separate project criteria.

No device deployment, quantization, profiling, Week 4 work or final external
acceptance is included. Keep this entire revision immutable; changes require a
new handoff ID. Large/generated binaries are delivered outside Git.
''')
    manifest["files"] = inventory(package)
    write_json(package / "manifest.json",manifest)
    verify(package,sha(package / "manifest.json"))
    after = {p.relative_to(original).as_posix():sha(p) for p in original.rglob("*") if p.is_file()}
    need(before==after,"SV1 immutable v2 changed")
    return package


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root",type=Path,required=True)
    p.add_argument("--handoff-id",required=True)
    p.add_argument("--output-parent",type=Path)
    p.add_argument("--compiler",default="gcc")
    args = p.parse_args()
    package = export(args.repo_root,args.handoff_id,args.output_parent,args.compiler)
    print(f"SV2_FP32_EXPORT_PASS: {package}")
    print(f"MANIFEST_SHA256: {sha(package / 'manifest.json')}")
