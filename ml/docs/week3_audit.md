# SV3 Week 3 pre-freeze audit — 2026-09-25

**Week 3 is NOT DONE. Model freeze confirmed by SV3 in-session, with verification
conditions now satisfied. M_final=P2 is SV3/SV1 CONFIRMED; the official SV3
package is released and verified. Device acceptance and ONNX remain pending.**
This document preserves the pre-implementation audit below. The subsequent
[review evidence](week3_review_evidence.md) records the implemented exporter,
verifier and real review artifacts. The subsequent [official release](week3_release.md)
records the new immutable handoff and authoritative SV1 approval.
No model, preprocessing, training setting, or historical evidence was
changed. No Week 4 work, split profiling, P1, INT8, attack or controller was run.

## A. Requirements and ownership

The local project DOCX sources were read from `project_sources/requirements/`
using `word/document.xml`. They are ignored local sources, not new Git files.

| Source | Week 3 requirement |
|---|---|
| `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx`, SV3 Week 3 row (continued across source pages) | Freeze architecture and learned-layer count L; export C header for SV1 and ONNX for SV2; both load the model and all three agree on 20 samples. |
| Same guide, SV1 Week 3 row | Port first two convolutions, load SV3 header, compare 20 samples with PyTorch; maximum absolute FP32 error strictly below `1e-3`. |
| `Huong1_Bao_cao_trien_khai_3SV.docx`, Week 3 row | Accuracy >=98%, freeze architecture and L; SV1 ports two Conv layers. Week 4 all-split profiling is outside this audit. |
| [SV1 handoff contract](../../contracts/sv3_sv1_week3_model_handoff.md), sections 2–6 | Immutable revision, exact checkpoint/config/source, execution graph, effective FP32 weights/bias, C99 hex-float header, 20 unique real sources, aligned inputs/golden, file manifest, exporter and verifier. |
| Same contract, sections 4 and 7 | SV3/SV1 confirm `M_final` and device feasibility. These approvals do not follow from a successful Week 2 verifier. |

SV1 depends on the verified package before porting and comparing outputs.
SV2 independently needs ONNX interface decisions and verification against the
same frozen model. ONNX does not block an otherwise approved SV1 package.

Raw-byte hashes of the two directly used Week 3 requirement documents:

- Detailed member guide: `75fcd76999af521a568b039c6983414217c59991d37b5591b85d211db927880d`.
- Three-member implementation report: `60f83fa7c0779d11c888a8a104c5fa55be0c8c8b171f9d72e29cbba9efcc9a90`.

## B. State at the pre-implementation audit

This table is the **pre-implementation snapshot**, before the user's conditional
freeze confirmation. Current artifact status is in the linked review evidence.

`READY` below means candidate evidence exists and was inspected; it does not
mean approved for a Week 3 release.

| Item | Status | Evidence / remaining condition |
|---|---|---|
| Dataset profile | READY / OPEN_DECISION | Candidate uses MIT-BIH/1.0.0; Week 3 choice awaits model freeze. |
| Architecture | READY / OPEN_DECISION | Actual source and loaded checkpoint agree: 8 Conv1d + 2 Linear, channels `1→16→16→32→32→48→48→64→64`, four pools, `1408→32→5` classifier. |
| Learned-layer count L | READY | Candidate L=10 by Conv1d/Linear counting convention; distinct from input sequence length 360 and 5 output classes. |
| Historical checkpoint | READY | Both `best_checkpoint.pt` and `best_state_dict.pt` exist locally; raw hashes and sizes match committed provenance. |
| Checkpoint source commit | READY | `8e98a0e4851abc979feb5fd5b97ece612b02cfaa` exists in Git; historical verifier checks source blobs. |
| Train config | READY | Config source, saved `training_config.json`, and checkpoint `training_config` agree. |
| Preprocessing provenance | READY | Week 1 loader verifies config, patient/processed manifests, normalization and every processed array/metadata hash against checkpoint provenance. No refit or second normalization. |
| Conv1 graph | READY (candidate) | Runtime hook on loaded eval model: `features.0`, details below. Frozen Week 3 `model/graph.json` MISSING. |
| Conv2 graph | READY (candidate) | Runtime hook on loaded eval model: `features.2`, details below. |
| BN status | READY (candidate) | No BatchNorm modules in model; no BN parameters or folding. BN eps/running statistics/gamma/beta not applicable. |
| ReLU/pooling order | READY (candidate) | Observed `features.0→features.1→features.2→features.3→features.4`. |
| Weight/bias | READY in checkpoint / MISSING export | Both convolutions have real weight and bias. No placeholder or zero bias generated. |
| Model freeze | OPEN_DECISION | Need SV3/GV model-freeze confirmation. |
| M_final | OPEN_DECISION | Contract requires SV3/SV1 confirmation. Pool output is an available candidate boundary, not approved. |
| Exactly 20 samples | MISSING | No selected CSV or delivered input. Section 5 explicitly delegates selection to SV3; see reproducible rule proposal below. |
| Golden outputs | MISSING / BLOCKED | Await model freeze and confirmed graph boundary. |
| C header | MISSING / BLOCKED | Await model freeze; no C compilation/bit round-trip PASS claimed. |
| Week 3 manifest | MISSING | Week 2 provenance exists; it is not a Week 3 manifest. |
| Week 3 export script | MISSING / BLOCKED | Implementation follows the model-freeze gate in the user's request. |
| Week 3 verify script | MISSING / BLOCKED | No package to verify; Week 2 PASS does not satisfy this gate. |
| ONNX for SV2 | BLOCKED | `BLOCKED_ON_SV2_INTERFACE`; details below. |

## C. Model-freeze gate and historical evidence

Initial finding was `Need SV3/GV model-freeze confirmation.` The user subsequently
answered `Xác nhận freeze candidate này nếu verifier PASS`. The unchanged
Week 1/2 verifiers passed; the decision is recorded in
[`week3_model_freeze.json`](../configs/week3_model_freeze.json). The user separately
confirmed that `M_final` has **not** been agreed. No SV1 approval is inferred.

Candidate: `mitdb_week2_cnn_v1`, seed 30, selected epoch 3. Loaded with
`torch.load(..., map_location="cpu", weights_only=True)` and strict
`load_state_dict`; `model.eval()` plus inference on a real normalized validation
row produced finite logits. The diagnostic row was not published as a handoff
sample. The read-only historical verifier also reproduced validation/test
metrics on the recorded CUDA device.

| Artifact | Actual local path | Bytes | SHA-256 (raw bytes) | Status |
|---|---|---:|---|---|
| Full checkpoint | `ml/data/week2/mitdb_baseline/best_checkpoint.pt` | 450551 | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` | PASS, historical candidate |
| State dict | `ml/data/week2/mitdb_baseline/best_state_dict.pt` | 445495 | `f9d5763da844ab5ccdfc36a0899e0763501431c423f51ef1ce4e06e14769453f` | PASS, historical candidate |
| Saved train config | `ml/data/week2/mitdb_baseline/training_config.json` | 661 | `52cc1cb425ecdee5ec0996f8dcf3cad3a7cfc8cf1407427835e6a712875a525c` | PASS |

The full checkpoint contains state tensors, epoch, validation, provenance,
training config and architecture. It is not a serialized model object.
Historical runtime: CPython 3.11.9, PyTorch 2.14.0+cu130, CUDA 13.0,
NVIDIA GeForce RTX 5060. The current environment check matches the pinned
dependencies. Historical provenance remains four source hashes with
`scientific_sources_clean=true` and `worktree_dirty=true`; today's verifier
separately enforces the six-file clean-source gate.

Recomputed validation accuracy: `0.8448791265921497`; test accuracy:
`0.9822097378277154`. Historical test macro F1 is `0.382595` and S/F/Q recall
is zero, as documented in [Week 2 baseline](week2_baseline.md). These limitations
are visible for the freeze decision, not grounds to tune against test data.
At the initial audit there was no repository sign-off promoting the candidate;
the later explicit in-session confirmation supplies the model-freeze authority.

Upstream text hashes use `sha256_utf8_lf_normalized`; NPY/raw dataset hashes
use `sha256_raw_bytes`, following the unchanged Week 1 policy:

| Upstream | SHA-256 |
|---|---|
| `ml/configs/mitdb_week1_config.json` | `f5d050686b9d4816052631380b81f0c4671faf1dc648f1d9c02b4c3dc3be0b54` |
| `ml/manifests/mitdb_patient_split.csv` | `27b07a0a4fcaac010291fd088c702e9eea1899ed73c6cef618404bafd3c116fe` |
| `ml/configs/mitdb_normalization.json` | `37d42ff2cbacc44f268046a62c392d2b9676c2c49936ac4188207745edd2d48c` |
| `ml/data/processed/mitdb/processed_manifest.json` | `f712c83d46d71ac6af75b7138668d8918eef87a4ddfeab8e8b5310ced2c44a3c` |

## D. Candidate first-two-Conv execution evidence (initial audit)

The following comes from hooks during real checkpoint inference, not module
name guessing. It is a candidate audit only, not a frozen Week 3 graph.

| Executed module | Operation | N=1 input → output | Parameter keys / shapes |
|---|---|---|---|
| `features.0` | Conv1d 1→16 | `(1,1,360)→(1,16,360)` | `features.0.weight (16,1,5)`; `features.0.bias (16,)` |
| `features.1` | ReLU, not inplace | `(1,16,360)→(1,16,360)` | None |
| `features.2` | Conv1d 16→16 | `(1,16,360)→(1,16,360)` | `features.2.weight (16,16,5)`; `features.2.bias (16,)` |
| `features.3` | ReLU, not inplace | `(1,16,360)→(1,16,360)` | None |
| `features.4` | MaxPool1d | `(1,16,360)→(1,16,180)` | kernel=2, stride=2, padding=0, dilation=1, ceil_mode=false |

Both Conv modules: kernel=5, stride=1, padding left/right=2/2 with `zeros`
mode, dilation=1, groups=1, bias present, FP32 NCL activations. Weight logical
layout is `(out_channel,in_channel_per_group,kernel)`. Bias adds per output
channel after the weighted sum, before the following ReLU. No BN, reshape,
transpose or residual occurs in this five-op segment.

Candidate Conv1: 80 weight + 16 bias elements = 384 bytes.
Candidate Conv2: 1280 weight + 16 bias elements = 5184 bytes.
Total: 1392 FP32 elements = **5568 bytes**, the logical persistent parameter
Flash requirement before linker/alignment overhead. Largest observed tensor
in this segment: **23040 bytes** for N=1; input is 1440 bytes and pool output
is 11520 bytes. Two separate full-size activation buffers would require
`2 * 23040 = 46080` logical bytes; this is a possible buffer plan, not measured
MCU RAM, stack, kernel workspace or a firmware build result.

If this candidate is approved, contract `M1` corresponds to Conv1 output and
`M2` to Conv2 output. Intervening ReLU and any included trailing ReLU/pool need
separate golden milestones. `M_final` and the final milestone list remain OPEN.

Section 5 authorizes SV3 to choose a deterministic 20-source rule. Proposed
rule after model approval: existing `val` split, sort real processed metadata
by numeric `record_id`, numeric `r_peak_sample`, then `lead_name`; take the
first 20 distinct source tuples, preserving their original array-row mapping.
No class selection, new split, seed, normalization or new scientific exclusion.
Duplicate source keys or invalid provenance must fail rather than silently
substitute samples. At this initial audit the rule had not produced files;
it has since produced the verified review set documented in
[review evidence](week3_review_evidence.md), without changing the rule.

## E. SV2 interface blockers

`BLOCKED_ON_SV2_INTERFACE`. Searches of `edge/`, `contracts/`, ML docs/configs
and local project requirements found the ONNX deliverable requirement, but no
approved export interface. `edge/README.md` has no implementation;
`week1_data_contract.md` explicitly defers ONNX choices.

SV2/SV3 must settle: delivery path; supported opset/runtime/provider; input and
output names; fixed/dynamic batch and other dimensions; full-model versus tail
profile and version; output semantics/class order; owner/location of the
unchanged Week 1 preprocessing; verification inputs, tolerances and runtime.
The model's current logits and input view are inspectable but do not themselves
approve a shared ONNX interface. No ONNX path or verification PASS is invented.

## F. Verification and Git delivery

Commands use `ml/.venv/Scripts/python.exe` from repository root, never the
Week 1 runner that regenerates artifacts. Current verification results:

| Command argument(s) | Result |
|---|---|
| `-B ml/src/check_env.py` | PASS |
| `-B ml/src/verify_mitdb_integrity.py` | PASS |
| `-B ml/src/inspect_mitdb.py` | PASS |
| `-B ml/src/test_segmentation.py` | PASS |
| `-B ml/src/audit_mitdb_preprocessing.py` | PASS |
| `-B ml/src/verify_mitdb_normalization.py` | PASS |
| `-B ml/src/verify_mitdb_processed.py` | PASS; all processed rows checked against raw annotations |
| `-B ml/src/verify_ptbxl_normalization.py` | PASS, 17418 training records |
| `-B ml/src/verify_ptbxl.py` | PASS, 21799 records, 43601 file checksums, no patient leakage |
| `-B ml/src/test_week1_negative.py` | PASS, 34/34 expected rejections; real raw datasets unchanged |
| `-B -O ml/src/verify_mitdb_integrity.py` | PASS |
| `-B -O ml/src/verify_mitdb_processed.py` | PASS |
| `-B ml/src/test_week2_baseline.py` | PASS, 3 tests |
| `-B ml/src/test_week2_provenance.py --verify-historical-artifacts` | PASS, clean gates, four intended rejections, historical artifact verification, real helpers unchanged |
| `-B ml/src/verify_week2_baseline.py --historical` | PASS, CUDA validation/test recomputation |
| Week 3 export/verify | Review checks PASS; release BLOCKED by boundary decision. See review evidence for commands, 12 negative cases and reproduction. |

`git fetch origin` succeeded. Kept `docs/sv3-week1-week2-reports`, which already
contains integrated Week 1/2. Fast-forwarded `f08ccb5` to
`6eb888b4215b9961ee879e4b794fd99ae50e2866` (`origin/dev/device-sv1`). Both tree
hashes were `fb8e4ba3874eb0e3ae1c74135343f73118a5bef0`, so this changed ancestry
without changing tracked file contents or losing ML commits. No merge conflict.

The existing untracked reports are preserved, not included in this delivery:

- `reports/SV3_ML_week1_report.md`: raw SHA-256 `d5bf9f2545aa2d861a92350f469f72c2352b3fe1ab78af39494d76f5e9579269`.
- `reports/SV3_ML_week2_report.md`: raw SHA-256 `1695d6b9a2746f42a5a3a208b012571c74279c4f2eafecc19a3bf6a667afe8d7`.

At the review stage there was no new commit, push or PR because the release
gate was still open. The later release commit/push and PR permission blocker are
recorded in [release evidence](week3_release.md). `.gitignore` and `ml/README.md` keep model artifacts/checkpoints outside
Git; the handoff contract allows transferring the complete package outside Git.
No force-add, force-push or direct push to `dev/device-sv1` was performed.

At the review stage the final handoff directory was absent. After explicit SV1
approval, `ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/` was exported and
release-verified. See the release report for its complete tree and hashes.
A separate review revision now exists at
`ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/`; its graph boundary
is expressly `PROPOSAL_ONLY`. It cannot pass release verification. The historical
paths above are not a released handoff location.

Boundary approvals and SV3 release verification are now complete. Remaining
gates: SV1 package review, nRF52840 validation and measured firmware resources;
resolve SV2 ONNX interface separately. The current contract records completed
SV3 deliverables without claiming MCU acceptance.
