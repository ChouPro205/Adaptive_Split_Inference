SV1 needs a reproducible FP32 reference before porting the first two convolutions. This change records the explicit SV3 and SV1 approvals for `M_final=P2` after `features.4 MaxPool1d` and provides the exporter, verifier, negative tests, contract updates and hash-pinned evidence for official handoff `mitdb-week3-fp32-20260925-v1`.

The segment is Conv1 → ReLU1 → Conv2 → ReLU2 → MaxPool1d; P2 at N=1 is `(1,16,180)`. Model name/version is `mitdb_week2_cnn_v1`, MIT-BIH/1.0.0, epoch 3, FP32; quantization is `not_applicable`. No retraining, preprocessing change, sample reselection, BatchNorm folding, INT8 or Week 4 work occurred.

### Delivery and artifact policy

**This PR references the complete immutable package; it does not version prohibited model binaries.** The existing policy in `ml/README.md` and `*.pt` ignore rules keeps model artifacts outside Git. Contract section 2 permits transferring the whole directory outside Git; the Week 3 output directory is now explicitly ignored to prevent incomplete commits.

- Actual package: `C:/Users/Admin/Adaptive_Split_Inference/ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/` — 29 files.
- Transfer-ready ZIP: `C:/Users/Admin/Adaptive_Split_Inference/ml/artifacts/week3/mitdb-week3-fp32-20260925-v1.zip` — 1,601,258 bytes, SHA-256 `59a3d5ac9546c754ddeaca6fa3f207c08a8724148f55d8d3b58c32e8ba7b75c3`.
- Package manifest SHA-256: `437a2a7db9f58d5d6896e8f50102c8b9b0a43b585d41c363420a1e9ca7309f2d`.
- Versioned inventory: [manifest copy](ml/provenance/week3/mitdb-week3-fp32-20260925-v1.manifest.json).
- Full location/hash/command/tree evidence: [release report](ml/docs/week3_release.md).

SV1 must receive the whole folder or ZIP separately; cloning this PR alone is insufficient. No upload, receipt, or remote artifact URL is claimed. Raw Week 1 data is external and is required for full input verification.

### Package contents and provenance

The package includes `README.md`, `manifest.json`, `model/checkpoint.pt`, `model/train_config.json`, `model/graph.json`, `model/freeze_decision.json`, original source blobs, `samples.csv`, `inputs.npy`, `weights/conv1.weight.npy`, `weights/conv1.bias.npy`, `weights/conv2.weight.npy`, `weights/conv2.bias.npy`, `firmware/head_parameters.h`, compiler evidence, all `golden/{M1,R1,M2,R2,P2}.npy`, and `scripts/{export_week3,verify_week3,test_week3,week3_common}.py`.

Checkpoint bytes match the unchanged historical full checkpoint:
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Model source commit: `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`.

### Validation

- Official export and packaged verification **without `--review`**: exit 0, HANDOFF_CHECKS_PASS.
- Exactly 20 real, unique sources, unchanged IDs/order; inputs regenerated against raw ECG and frozen Week 1 provenance.
- All five golden tensors recomputed bit-exactly from the actual saved/reloaded inputs in eval mode.
- All 1,392 FP32 parameter bits match the NPY arrays and compiled C99 header (GCC 15.2.0).
- 14 expected negative/rejection cases pass, including missing SV1 consent and immutable overwrite.
- Separate reproduction ID `mitdb-week3-fp32-20260925-v1-repro`: 27 files byte-identical; README/manifest intentionally identify the new location/revision.
- All 15 scientific payload files compared with r2 are unchanged; all r2 files and its manifest remain intact.
- `git diff --check` and `git diff --cached --check`: exit 0. Pre-existing Week 1/2 reports preserved and excluded from this commit.

After receiving the out-of-band package, from repository root:

```powershell
$pkg = 'ml/artifacts/week3/mitdb-week3-fp32-20260925-v1'
& ml/.venv/Scripts/python.exe -B "$pkg/scripts/verify_week3.py" --repo-root . --package $pkg
& ml/.venv/Scripts/python.exe -B "$pkg/scripts/test_week3.py" --repo-root . --package $pkg
```

Use the pinned environment, historical Git commit, Week 1 raw/processed MIT-BIH data and host GCC described in the package README. Export reproduction additionally verifies the recorded historical CUDA run.

### Pending acceptance

SV3 release package: **PASS**. SV1 package review: **PENDING**. SV1 MCU validation: **PENDING**. MCU 20/20: **NOT YET TESTED**. Logical estimates only: 5,568 B parameters (384 + 5,184), 23,040 B largest N=1 intermediate and 46,080 B double buffer; actual firmware Flash/RAM/workspace/stack remain SV1 measurements.

ONNX remains **BLOCKED_ON_SV2_INTERFACE**: no approved opset/runtime/provider, delivery path, tensor names/dimensions, full/tail profile or verification tolerance/procedure. This is independent of the approved SV1 boundary. Entire Week 3 is not DONE.
