# SV3 Week 3 SV2 interface and split audit 2026-09-30

SV2's new runtime/output decisions are recorded in [interface review](../configs/week3_sv2_interface_review.json). Export remains **BLOCKED_MISSING_EXISTING_SPLIT_MAPPING**. No tail was arbitrarily selected or exported, no new split ID was assigned, and no SV2 RC/final package is claimed. Week 3 remains **NOT DONE**.

## Existing semantics and the missing decision

Fetched repository evidence: `origin/main` at `144413b3c827d5a7a0163e9eab880670fdf91d8b`, `origin/dev/device-sv1` at `fa5c9ddb6dd189264bfb5abce438a7c75098af8b`, and `origin/dev/edge-sv2` at `881f3c1ebfb41425f4ee65ccb3c6f97a03dcc301`. All current contract files were inventoried; the relevant I1/I2/I3 and SV1 handoff rules were searched and read.

- I1 section 8 / split registry sections explicitly leave concrete `(model_profile_id, split_id) -> layer/tensor` mapping DEFERRED. I1 reserves wire split_id 0; synthetic test IDs are not model profiles.
- SV3/SV1 handoff section 1 explicitly defines a local FP32 experiment, not a split_id/model_profile_id. Approved P2 is after `features.4`, but it cannot silently become the only SV2 split.
- The original local roadmap `06_Huong1_Adaptive_Split_Inference_Lo_trinh.docx`, section 0.1, describes head layers 1..s and tail s+1..L, and section 4.1 gives generic `range(L+1)` profiling code whose `layers` list may be flattened further. The assignment `Huong1_Phan_cong_nhom_nghien_cuu.docx`, B2, calls for L+1 compiled models in weeks 4-6. These establish abstract endpoint semantics, not a concrete mapping for this frozen architecture. No profiling or compilation task from Week 4 was executed.
- Frozen architecture counts L=10 learned layers (8 Conv, 2 Linear), while actual inference contains 25 leaf operations. Existing material does not resolve whether each cut is immediately after learned weights or after associated ReLU/Pool operations, nor where Flatten/Dropout belong at a cut. Choosing either convention would invent the missing concrete semantics.

**Required input:** an existing approved mapping/rule tying every valid s/split_id to an exact frozen op endpoint, including how the edge-only/device-only abstract endpoints are represented. A full-model profile is not created just because input shape `(1,1,360)` is known. The user has been asked for the authoritative mapping or source. `valid_splits: null` means unknown, not an approved empty set.

## Actual graph observations, not valid split declarations

All shapes below were observed in eval/inference mode with N=1 for each of the frozen 20 inputs. Dtype is `torch.float32`. Remaining operations for every row are listed explicitly in the [audit JSON](../provenance/week3/sv2-split-audit-20260930.json), ending at `classifier.4` logits `(1,5)`. No row has a split_id.

| Observed source op | Type | Output shape N=1 | Layout |
|---|---|---|---|
| features.0 | Conv1d | (1, 16, 360) | NCL |
| features.1 | ReLU | (1, 16, 360) | NCL |
| features.2 | Conv1d | (1, 16, 360) | NCL |
| features.3 | ReLU | (1, 16, 360) | NCL |
| features.4 | MaxPool1d | (1, 16, 180) | NCL |
| features.5 | Conv1d | (1, 32, 180) | NCL |
| features.6 | ReLU | (1, 32, 180) | NCL |
| features.7 | Conv1d | (1, 32, 180) | NCL |
| features.8 | ReLU | (1, 32, 180) | NCL |
| features.9 | MaxPool1d | (1, 32, 90) | NCL |
| features.10 | Conv1d | (1, 48, 90) | NCL |
| features.11 | ReLU | (1, 48, 90) | NCL |
| features.12 | Conv1d | (1, 48, 90) | NCL |
| features.13 | ReLU | (1, 48, 90) | NCL |
| features.14 | MaxPool1d | (1, 48, 45) | NCL |
| features.15 | Conv1d | (1, 64, 45) | NCL |
| features.16 | ReLU | (1, 64, 45) | NCL |
| features.17 | Conv1d | (1, 64, 45) | NCL |
| features.18 | ReLU | (1, 64, 45) | NCL |
| features.19 | MaxPool1d | (1, 64, 22) | NCL |
| classifier.0 | Flatten | (1, 1408) | NC |
| classifier.1 | Dropout | (1, 1408) | NC |
| classifier.2 | Linear | (1, 32) | NC |
| classifier.3 | ReLU | (1, 32) | NC |
| classifier.4 | Linear | (1, 5) | NC |

Raw model input is `(1,1,360)` NCL. Reference full-model logits were calculated for 20 samples, with combined stored shape `(20,5)` and per-inference shape `(1,5)`. Existing P2 golden matched bit-for-bit. This is graph audit/reference preparation, **not PyTorch-tail or ONNX verification**.

Audit-only local output: `ml/data/week3_sv2_audit_20260930/result/` contains `audit.json` and `reference_logits.npy`. Reference logits SHA-256: `5ce7c1741e8fd096c70ab29484dcfb176224dbad286ea3bc8b99488f1133bcc4`. No handoff manifest, archive or ONNX model has been generated. This folder is not an SV2 RC.

## Recorded SV2 interface

One tail per existing valid split; fixed N=1; no dynamic axes. Tail input `input_activation` is the actual z_s with per-split shape/layout, not universally raw input. Output `logits` is float32 pre-softmax AAMI logits `(1,5)` in class order N/S/V/F/Q; argmax outside graph. Frozen Week 1 preprocessing occurs before head inference, with no refit or second normalization, and none inside tails. Use the same 20 v2 sample IDs and strict error `<1e-3` for every sample/split.

ONNX opset **13**, status **PROVISIONAL_PENDING_GV_CONFIRMATION**. Target runtime **VART**, backend **KV260 DPU**. These target labels are not proof of ONNX loading or hardware numerical compatibility. ONNX tooling is not installed in the current pinned environment; no package install or environment change was made while the split mapping remains unresolved.

## SV1 evidence update

SV1's pinned `device/reports/week3_build.md` records independent official verifier exit 0, `HANDOFF_CHECKS_PASS`, and 27/27 negative rejections on v2. PR #11 was subsequently merged by the repository workflow at `ff7f621706558083b4da5e583cb20268fb6d947e`; earlier v2 release notes remain historical. This audit did not merge anything.

The checked-in full capture at `results/week3/logs/week3_capture_verified.txt` was parsed again against authenticated immutable v2 golden. All 20 sample IDs/results matched the recorded JSON exactly. **MCU P2 20/20 PASS**, worst error **7.152557373046875e-07**, strictly below 1e-3. Firmware source `33a5288e475646c80f14a9cfcd2e797db64c5e41` implements the frozen Conv1/ReLU1/Conv2/ReLU2/MaxPool segment, as recorded in the build evidence; this run rechecked the existing capture and did not reflash hardware.

The initial audit rejected the raw Git capture hash. Investigation established that Git stores 727774 LF bytes, whereas SV1 hashed 732924 CRLF bytes. Restoring only LF to CRLF produces the recorded hash exactly. The parser reads the unchanged Git blob; both identities are recorded:

- Git LF SHA-256: `52b16fa2b222bcefb746e142bc7bc922678e7b4a223f64e2e2061902bd72dfe2`.
- Original CRLF SHA-256: `1e3825300731ac5804c605bb7c007457d8aeb5768e94dab9e16b6ca7503ee051`.

Sample 0 intermediate errors match the report (M1/R1 2.384185791015625e-7; M2/R2 9.5367431640625e-7). The remaining **19 x 4 intermediate tensors were not captured**. Do not claim the contract's full 20 x 5 error table has been measured. Main-thread stack high-water is 544/4096 B; this is not all stacks or total RAM.

## Reproduction and preservation

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/audit_week3_sv2.py --repo-root . --output ml/data/week3_sv2_audit_repeat --compiler C:/msys64/ucrt64/bin/gcc.exe
```

The compiler path is a local MSYS2 example; use a valid host GCC path on another machine. Output must be a new location. Audit runs the full hardened v2 verifier with the independently trusted manifest hash first, observes real graph outputs, and rechecks the pinned SV1 capture. Final run: exit 0, `AUDIT_PASS`, 25 observed ops, `SV1_P2: 20/20 PASS`. Every immutable v2 file remains unchanged. Pre-existing ZIPs/reports were not edited. Frozen checkpoint/model/preprocessing/20 samples were not changed.

## Remaining gates

1. Existing concrete split mapping required before per-split wrappers/export/numerical verification and a review handoff can be completed.
2. Supervisor confirmation of opset 13; all future opset-13 exports stay provisional until then.
3. SV2 independent VART/KV260 loading/execution and required numerical evidence.
4. SV1's missing intermediate 20 x 5 evidence or an explicit contract-scope decision.

No Week 4 profiling, retraining, model changes, quantization or hardware deployment was performed. Work files remain local; no commit, push or new PR was requested/performed for this audit.
