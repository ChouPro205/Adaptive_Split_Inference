# SV3 Week 3 confirmed split handoff 2026-10-01

## 1. CONFIRMED SPLIT MAP

The team-authoritative confirmation relayed by the user on 2026-10-01 supersedes the deferred/provisional status from 2026-09-30. The requested filename [week3_sv2_interface_review.json](../configs/week3_sv2_interface_review.json) is retained, but its current status and opset status are **CONFIRMED**. Historical [config](../provenance/week3/history/sv2-interface-review-20260930.json), [audit text](../provenance/week3/history/sv2-split-audit-20260930.md), and [audit evidence](../provenance/week3/sv2-split-audit-20260930.json) remain preserved. [Current contract](../../contracts/sv3_sv2_week3_fp32.md).

Frozen model/version: `mitdb_week2_cnn_v1`, MIT-BIH/1.0.0, epoch 3. Checkpoint SHA-256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`. L=10 weighted layers: 8 Conv1d + 2 Linear. ReLU belongs to the prior weighted layer; pooling to the prior even Conv. Flatten/Dropout(eval) prepare learned layer 9. Parameter-free operations do not increment s.

| s / reference split_id | Head endpoint | z_s N=1 | Layout | Tail starts |
|---|---|---|---|---|
| 0 | normalized_model_input (identity head) | (1, 1, 360) | NCL | features.0 |
| 1 | features.1 | (1, 16, 360) | NCL | features.2 |
| 2 | features.4 | (1, 16, 180) | NCL | features.5 |
| 3 | features.6 | (1, 32, 180) | NCL | features.7 |
| 4 | features.9 | (1, 32, 90) | NCL | features.10 |
| 5 | features.11 | (1, 48, 90) | NCL | features.12 |
| 6 | features.14 | (1, 48, 45) | NCL | features.15 |
| 7 | features.16 | (1, 64, 45) | NCL | features.17 |
| 8 | features.19 | (1, 64, 22) | NCL | classifier.0 |
| 9 | classifier.3 | (1, 32) | NC | classifier.4 |
| 10 | classifier.4 | (1, 5) | NC | identity |

All activations use float32, little-endian `<f4`, C-order. Head input is the frozen normalized x; each tail input is its head output z_s. s=0 is identity head/full tail; s=10 is full head/identity tail, `edge_compute_required=false` and no ONNX. Full head operation lists, weighted-layer indices and remaining tail operations are recorded per split in the config and manifest. This reference mapping does not change I1 packet wire IDs; wire split_id=0 remains reserved.

## 2. PYTORCH HEAD/TAIL CONSISTENCY

Deterministic CPU eval/inference, N=1, one thread, MKLDNN disabled. Wrappers reuse the exact frozen module objects/weights. Full-model reference is evaluated using the original `model.forward`, separately from the sequential split path. No new preprocessing, no retraining and inactive Dropout. All **220 head/tail cases** match full-model logits, including 20 full-head/identity cases at s=10. The delivered saved/reloaded z_s files were independently rechecked through the tails.

| s | Samples | Worst PyTorch error |
|---|---|---:|
| 0 | 20/20 PASS | 0 |
| 1 | 20/20 PASS | 0 |
| 2 | 20/20 PASS | 0 |
| 3 | 20/20 PASS | 0 |
| 4 | 20/20 PASS | 0 |
| 5 | 20/20 PASS | 0 |
| 6 | 20/20 PASS | 0 |
| 7 | 20/20 PASS | 0 |
| 8 | 20/20 PASS | 0 |
| 9 | 20/20 PASS | 0 |
| 10 | 20/20 PASS | 0 |

## 3. GOLDEN ACTIVATIONS

Paths below are relative to `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/`. Every array contains the same 20 sample_index/sample_id rows in original order; no sample reselection. `samples.csv` SHA-256 is `4a6356312d5f62da6b2fdf9e609843d4dea3fc5c20767e201ea21a075e6f227c`. z_s0 is the exact original normalized input file; z_s2 is byte-identical to accepted SV1 P2 golden. z_s10 equals reference_logits byte-for-byte. Each array was regenerated from the exact checkpoint and checked bitwise.

| File | Shape | SHA-256 raw bytes |
|---|---|---|
| `golden/reference_logits.npy` | (20, 5) | `5ce7c1741e8fd096c70ab29484dcfb176224dbad286ea3bc8b99488f1133bcc4` |
| `golden/z_s0.npy` | (20, 1, 360) | `dac1d1e9df849bf4ffa30359384d129586f67ec0703157b692d1344685b78dcc` |
| `golden/z_s1.npy` | (20, 16, 360) | `01dc25a4e8eb9e4ad3bcf246dd3e8ed85e06dc0df7af8e78f13b75800f0dc9a6` |
| `golden/z_s10.npy` | (20, 5) | `5ce7c1741e8fd096c70ab29484dcfb176224dbad286ea3bc8b99488f1133bcc4` |
| `golden/z_s2.npy` | (20, 16, 180) | `5b9607815738e1a3a7ccde941e23a01a9ad927326839f38895e1f289e7d72399` |
| `golden/z_s3.npy` | (20, 32, 180) | `afe72a5e26572060420a93f19ae0ce4a3bc686a90ef1607d4108df7b2bbbd94d` |
| `golden/z_s4.npy` | (20, 32, 90) | `a45a5032e8682d2734642d2842659aac44fd0de208804f660faec7cc357cef16` |
| `golden/z_s5.npy` | (20, 48, 90) | `b713e53387e5e43ba9f8abf0cd0905b108208cf29082669dfd1be706857a706e` |
| `golden/z_s6.npy` | (20, 48, 45) | `a8b92d72c20fa4df5a3e651c87c0335bd7fecbc0657e7310bf6d4589700e8ba8` |
| `golden/z_s7.npy` | (20, 64, 45) | `f1a9300d387aed0abb5ad5d2ff5f08167f162f66e5017e252b9de92053926e60` |
| `golden/z_s8.npy` | (20, 64, 22) | `fda1e8ebc1828134b60daf75d5f60c50f4fa42ca3a9d9db83a66f3ffe0110829` |
| `golden/z_s9.npy` | (20, 32) | `2f6bd177be2a2f8f5aed60b85d65755520f538bfdbeeda0fe77f99206ca056bb` |

## 4. ONNX EXPORT

Exactly ten ONNX files. All pass ONNX checker with full_check, actual I/O inspection and FP32 initializer inspection. Opset **13 CONFIRMED**, fixed N=1, no dynamic axes, no external weight data. Input name `input_activation`, output name `logits`, output float32 `(1,5)`; pre-softmax class order N/S/V/F/Q. Softmax/argmax and preprocessing are absent. s=9 is rank-2 NC; earlier inputs are NCL. No tail_10.onnx exists.

| s | File | Input shape | Bytes | SHA-256 |
|---|---|---|---:|---|
| 0 | `models/tail_0.onnx` | (1, 1, 360) | 441852 | `ffa1cbe02e7b9af405177816cc7edfe9870f61287553ce748f09a1f8bed572cf` |
| 1 | `models/tail_1.onnx` | (1, 16, 360) | 441209 | `4940b21a5101a08b341cbd2b9c191dec0ea21d9c121f08a65062688e0764e9d3` |
| 2 | `models/tail_2.onnx` | (1, 16, 180) | 435609 | `981527fa3d7d37d6b2c4e14b09328221bdf2e1dabbbe0c03506847e64a296355` |
| 3 | `models/tail_3.onnx` | (1, 32, 180) | 424980 | `2f27e2bfb1d7c72c0f98150e299392b6dbe985603be9f1820ded1f2945387874` |
| 4 | `models/tail_4.onnx` | (1, 32, 90) | 403951 | `dd481202cfbfec74ee399df4d0f2693060124cfa26d46a75d33262a2c0bc0f7e` |
| 5 | `models/tail_5.onnx` | (1, 48, 90) | 372783 | `872a26240b566c2c7f66ecfb056987788155cd297e65520f24776f670ea6b501` |
| 6 | `models/tail_6.onnx` | (1, 48, 45) | 326089 | `80a4fff1033b0530936eb1b77f5f9e67469acbccf89755e446a24ad5870c686d` |
| 7 | `models/tail_7.onnx` | (1, 64, 45) | 264140 | `c5181d7fffbd0093e473d67ea042b0c599c0c2e38b1f3319ca3c462a9058a3b0` |
| 8 | `models/tail_8.onnx` | (1, 64, 22) | 181557 | `d108d29c3c79c467ca5830bf4ecda8980d30faddfcad9a6087b5ec2115c99725` |
| 9 | `models/tail_9.onnx` | (1, 32) | 907 | `d2de785a18a069ff483e2408beb4b95abde4284fba3276f69dc0c0f32c22fb2f` |

The exporter explicitly selects TorchScript `dynamo=False` and opset 13 rather than relying on the current default exporter; its deprecation warning is recorded in the run output and is not a numerical failure. Fixed shapes and explicit export parameters follow [PyTorch ONNX API](https://docs.pytorch.org/docs/2.14/onnx.html). The verifier explicitly selects [ONNX Runtime CPUExecutionProvider](https://onnxruntime.ai/docs/api/python/api_summary.html), sequential execution, one intra/inter-op thread and ORT_ENABLE_BASIC. This is local FP32 reference verification, not hardware acceptance.

## 5. FP32 ONNX VERIFICATION

**200/200 PASS**, strict max_abs_error < 1e-3 for each individual case versus original full-model PyTorch logits. No averaging of failures. [Full per-sample/split record](../provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.numerical.json) includes ONNX-vs-full, PyTorch-tail-vs-full and ONNX-vs-PyTorch-tail errors.

| s | Samples | Worst ONNX-vs-full error |
|---|---|---:|
| 0 | 20/20 PASS | 2.6226043701171875e-06 |
| 1 | 20/20 PASS | 2.384185791015625e-06 |
| 2 | 20/20 PASS | 2.6226043701171875e-06 |
| 3 | 20/20 PASS | 2.0265579223632812e-06 |
| 4 | 20/20 PASS | 2.0265579223632812e-06 |
| 5 | 20/20 PASS | 2.1457672119140625e-06 |
| 6 | 20/20 PASS | 1.9073486328125e-06 |
| 7 | 20/20 PASS | 1.9073486328125e-06 |
| 8 | 20/20 PASS | 1.9073486328125e-06 |
| 9 | 20/20 PASS | 9.5367431640625e-07 |

Global maximum **2.6226043701171875e-06**. All tied locations: `[{"s": 0, "sample_index": 16, "sample_id": "MIT-BIH:105:4371:MLII"}, {"s": 2, "sample_index": 16, "sample_id": "MIT-BIH:105:4371:MLII"}]`. PyTorch-tail maxima are zero throughout. s=10 has 20/20 identity PASS and no ONNX comparison.

17/17 reason-specific negative/rejection tests PASS: missing external anchor; changed manifest metadata with/without rebuilt inventory; wrong model version; wrong endpoint; missing test script/tail; forbidden tail_10; altered identity; activation shape/dtype/NaN/value; ONNX opset/input-name/weight mutations; immutable overwrite. Semantic fixtures rebuild hashes and use test-controlled anchors; manifest-authentication tests retain the original external anchor. Source package unchanged after all tests.

## 6. SV3 TO SV2 HANDOFF

- ID: `mitdb-week3-sv2-fp32-20261001-v1`.
- Package: `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/`.
- Manifest SHA-256: `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.
- Archive: `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1.zip`, 4507827 bytes.
- Archive SHA-256: `b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7`.
- Inventory: **41 files**, 6239715 bytes uncompressed.
- [Versioned exact manifest](../provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.manifest.json) and [verification summary](../provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.verification.json).

Immutable SV1 v2 remains unchanged. Its model name/version, checkpoint, original architecture, train/freeze configuration, preprocessing and 20 sample identities are unchanged. The new package contains the full original checkpoint and architecture for SV2's PyTorch/Vitis AI flow, plus the confirmed split contract and reconstruction wrappers.

The bundle verifier first authenticates raw manifest bytes against an independent expected hash before parsing; it then checks the required file set, file inventory, source/checkpoint/config bindings, all golden bits, graph I/O and all numerics. The package's original SV1 manifest and pinned input/sample hashes bind the exact source data without requiring the raw dataset on the recipient for this FP32 handoff check. Export additionally ran the full original raw-derived SV1 verifier before copying any scientific payload.

Reproduction ID `mitdb-week3-sv2-fp32-20261001-v1-repro`: **39 files identical**, only README and manifest differ for the new ID. Reproduction manifest SHA-256 `84067252c782e1c5f934aa0c26dfc85b68a3ee0f14af98e53d6f4d5a815029a3`. All ten ONNX binaries and twelve golden files reproduced byte-for-byte. Every ZIP entry was compared with the package bytes. Package/ZIP are outside Git under existing model artifact policy; no remote upload or SV2 receipt is claimed.

Exact inventory:

```text
mitdb-week3-sv2-fp32-20261001-v1/
  README.md
  evidence/numerical_verification.json
  evidence/source_provenance.json
  golden/reference_logits.npy
  golden/z_s0.npy
  golden/z_s1.npy
  golden/z_s10.npy
  golden/z_s2.npy
  golden/z_s3.npy
  golden/z_s4.npy
  golden/z_s5.npy
  golden/z_s6.npy
  golden/z_s7.npy
  golden/z_s8.npy
  golden/z_s9.npy
  manifest.json
  model/checkpoint.pt
  model/freeze_decision.json
  model/mitdb_baseline_model.py
  model/sv1_v2_manifest.json
  model/sv2_interface.json
  model/train_config.json
  models/tail_0.onnx
  models/tail_1.onnx
  models/tail_2.onnx
  models/tail_3.onnx
  models/tail_4.onnx
  models/tail_5.onnx
  models/tail_6.onnx
  models/tail_7.onnx
  models/tail_8.onnx
  models/tail_9.onnx
  requirements/requirements-core.txt
  requirements/requirements-gpu-cu130.txt
  requirements/requirements-week3-onnx.txt
  samples.csv
  scripts/export_week3_sv2.py
  scripts/test_week3_sv2.py
  scripts/verify_week3_sv2.py
  scripts/week3_common.py
  scripts/week3_sv2_common.py
```

Recipient setup and verification, from repository root after receiving the entire ZIP:

```powershell
# Python 3.11.9; existing environment uses torch 2.14.0+cu130.
py -3.11 -c "import sys; assert sys.version_info[:3] == (3,11,9), sys.version"
py -3.11 -m venv ml/.venv
& ml/.venv/Scripts/python.exe -m pip install -r ml/requirements-gpu-cu130.txt -r ml/requirements-week3-onnx.txt
& ml/.venv/Scripts/python.exe -m pip check
$pkg = 'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1'
$trustedManifestSha = 'a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6'
$trustedZipSha = 'b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7'
if ((Get-FileHash "$pkg.zip" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $trustedZipSha) { throw 'ZIP SHA mismatch' }
# Extract into an empty destination; skip if already extracted. Never overwrite a revision.
Expand-Archive -LiteralPath "$pkg.zip" -DestinationPath ml/artifacts/week3
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3_sv2.py --package $pkg --expected-manifest-sha256 $trustedManifestSha
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3_sv2.py --package $pkg --expected-manifest-sha256 $trustedManifestSha
```

All prior installed dependencies were constrained to their existing versions during ONNX installation. New pinned packages: ONNX 1.23.1, ONNX Runtime 1.30.0, protobuf 7.36.2, ml_dtypes 0.6.0, flatbuffers 25.12.19. pip check PASS. No training environment package version was changed.

### Verifier cache fix (immutable v1 remains unchanged)

Use the updated verifier/test in a **trusted repository checkout**, not copied
into v1. The commands above still use v1's independently published manifest
hash. Updated SV2 entry points disable bytecode writes even without `-B`.
Inventory exempts only CPython cache filenames corresponding to delivered
sources directly under `scripts/__pycache__/` and `model/__pycache__/`;
unrecognized files, orphan caches and symlinks are not exempt. The shared frozen
model loader executes the source bytes it hash-authenticated, never a `.pyc`.

Workaround for the original bundled v1 verifier: verify the ZIP hash, extract
into a **new empty destination**, and use `python -B` starting with the first
run. `-B` does **not** delete old cache and does **not** prevent reading existing
bytecode. Do not repair/re-hash v1 in place or insert changed scripts into it.
Shipping fixed scripts or a changed README requires a new revision ID and new
manifest/ZIP hashes; this cache fix does not itself publish a revision.

`.cpython-312.pyc` is evidence of CPython 3.12 cache generation; v1 pins Python
**3.11.9**. This environment mismatch is independent of the inventory bug. Use
all exact `dependency_versions` in the manifest; the version gate is unchanged.

Commands run successfully (exit 0):

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/export_week3_sv2.py --repo-root . --handoff-id mitdb-week3-sv2-fp32-20261001-v1 --compiler C:/msys64/ucrt64/bin/gcc.exe
& ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/scripts/verify_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6
& ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/scripts/test_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6
& ml/.venv/Scripts/python.exe -B ml/scripts/export_week3_sv2.py --repo-root . --handoff-id mitdb-week3-sv2-fp32-20261001-v1-repro --compiler C:/msys64/ucrt64/bin/gcc.exe
```

The GCC path above is the author's local toolchain example. SV2 standalone FP32 verification does not invoke GCC or require a GPU/raw dataset. Re-export uses the trusted repository checkout and needs preserved SV1 v2, Week 1 data and host GCC. The shipped PyTorch wrappers/code/checkpoint are sufficient for SV2 to reconstruct tails; bundled scripts/README explain this separately from export provenance verification.

## 7. SV1 STATUS

The user's initial status (full intermediate trace only at sample 0) was correct for the earlier evidence. The refreshed repository now includes PR #15 at `bd64c3859e9ce8493e7115285cfbb3dc1f8f3859`: full TRACE 0..19 capture, CSV and JSON table. This task re-ran the checked-in capture checker in 20x5 mode against unchanged SV1 v2, writing a separate local report rather than modifying SV1 evidence. **100/100 tensors and all 20 ordered sample IDs verified**; results match the recorded JSON and capture SHA-256 exactly.

- Independent SV1 package verifier/test: recorded PASS, including 27/27 negative checks.
- P2 20/20: PASS; worst 7.152557373046875e-07.
- Full 20x5 trace gap: now filled by actual repository evidence and rechecked.
- Worst M1/R1: 4.76837158203125e-7; M2/R2: 9.5367431640625e-7.
- Capture: `results/week3/logs/week3_capture_20x5.txt`, SHA-256 `72c7b6a2ba554f7e6d242a49e20065a4b56a3967108206a9a4d8845f1e795606`.
- [Recorded 20x5 JSON](../../results/week3/week3_mcu_validation_20x5.json), [CSV table](../../results/week3/week3_milestone_errors_20x5.csv), [SV1 report](../../docs/sv1_device_week3_report.md).

This is revalidation of SV1's existing hardware capture, not a new device run performed by SV3. No intermediate trace was fabricated and the immutable v2 package was not altered.

## 8. EXTERNAL SV2 GATES

**PENDING:** Vitis AI/operator compatibility, quantization, compiling each applicable tail to xmodel, target DPU compatibility, VART/KV260 execution and independent reporting. No SV2 ACCEPTED, VART PASS, KV260 PASS, INT8 PASS or XMODEL PASS is claimed. The FP32 reference <1e-3 criterion does not automatically govern INT8/DPU numerical/accuracy degradation. SV2 records that separately under project quantization/device criteria. Opset 13 and mapping themselves are now confirmed; the earlier GV-provisional label is historical.

## 9. GIT

Branch: `sv3/week3-sv2-fp32-handoff`, based on current main `bd64c3859e9ce8493e7115285cfbb3dc1f8f3859`. Source commit: `dd1d4562062202c6721a03a81a7f2cfa29867c00`. The generated provenance pins that commit and raw hashes of all bundled scripts. A following evidence commit adds this report, the exact manifest copy, complete numerical results and verification summary. Generated binaries/ZIPs and pre-existing user ZIPs/reports remain outside commits. Whitespace validation: `git diff --check`, staged check and branch diff check. No merge or new PR is performed by this work.

## 10. OVERALL WEEK 3 STATUS

**NOT DONE.** SV3's confirmed FP32 reference package is complete and locally verified; SV1 full evidence has now been independently rechecked from the repository. Required external SV2 validation remains pending. No Week 4 profiling, retraining, preprocessing change, INT8 conversion, xmodel compilation or hardware deployment was performed.
