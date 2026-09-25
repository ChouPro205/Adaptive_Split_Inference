# SV3 Week 3 review evidence — 2026-09-25

**REVIEW_CHECKS_PASS; NOT A RELEASE. Week 3 remains incomplete.**

This page preserves **historical r2 review evidence**. A separate official ID
has since been created after explicit SV1 approval; see [Week 3 release](week3_release.md).
No r2 package file was changed or relabeled. Pending-state descriptions below
refer to the review stages, not the latest release decision.

Model freeze is confirmed by the SV3 user, conditional on verifiers; all relevant Week 1/2 read-only checks passed.
**Decision at the SV3-only review stage: M_final=P2 was SV3 CONFIRMED; SV1 PENDING.** SV3 explicitly
confirmed output after `features.4 MaxPool1d`, N=1 shape `(1,16,180)`, including
Conv1 → ReLU1 → Conv2 → ReLU2 → MaxPool1d. No explicit SV1 confirmation was found
after fetching origin. This does not authorize release. The r2 evidence below
retains its historical proposal status; r2 has not been modified or relabeled.

Frozen model identifier: `mitdb_week2_cnn_v1`, MIT-BIH/1.0.0, epoch 3.
The existing config calls this `model_name` and records the delivery version
as `model_version=week3-fp32-epoch3`; both fields are preserved unchanged.
The full checkpoint is `model/checkpoint.pt` in the review package, copied
from `ml/data/week2/mitdb_baseline/best_checkpoint.pt`, SHA-256
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Historical validation accuracy is 84.488%, test accuracy 98.221%, and test
recall for S/F/Q is zero. This is the FP32 integration reference, not a claim
of robust five-class clinical performance.

## Review package

- Review ID: `mitdb-epoch3-fp32-review-20260925-r2`.
- Actual local folder: `C:/Users/Admin/Adaptive_Split_Inference/ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2`.
- [Package README](../data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/README.md).
- Manifest raw SHA-256: `24300d18044640c83722073dd692cff540721cdf027d9fe31e29a87e7d480a88`.
- Source commit: `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`.
- Final handoff ID/location: not issued; `ml/artifacts/week3/` does not exist.
- Manifest contains every file except itself; package contains 28 files.

## Verification

All commands below ran with `ml/.venv/Scripts/python.exe -B` from repository root.

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/export_week3.py --repo-root . --decision ml/configs/week3_model_freeze.json --handoff-id mitdb-epoch3-fp32-review-20260925-r2 --review
& ml/.venv/Scripts/python.exe -B ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/scripts/verify_week3.py --repo-root . --package ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2 --review
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3.py --repo-root . --package ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2
& ml/.venv/Scripts/python.exe -B ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/scripts/export_week3.py --repo-root . --decision ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/model/freeze_decision.json --handoff-id mitdb-epoch3-fp32-review-20260925-r2-repro --review
```

All four commands exited 0. Export rechecks the historical CUDA run before loading unchanged checkpoint bytes. Verification regenerates inputs from raw ECG, checks hashes/metadata/source/graph, reruns the exact delivered inputs in PyTorch eval and compares all golden bits. GCC 15.2.0, `-std=c99 -Wall -Wextra -Werror -pedantic`, compiled the header and reproduced all 1392 FP32 parameter bit patterns.

Negative suite passed 12 intended rejections: release of an unconfirmed review, missing bias, changed input/golden/weight even after updating file hashes, wrong sample order, omitted ReLU, changed C representation, wrong dtype, nonfinite golden, revision overwrite, and export without boundary confirmation. Mutations were confined to temporary copies; the real package hashes remained unchanged.

Reproduction created a separate immutable ID ending `-repro`. All 26 files other than README and manifest were byte-identical, including checkpoint, config, source, graph, samples, inputs, header, parameters and golden. README/location and manifest identity correctly describe the new revision.

The first review attempt `mitdb-epoch3-fp32-review-20260925-r1` failed exact golden comparison at M1 (224 FP32 elements; max absolute difference 5.960464477539063e-08). Root cause: input singleton-channel stride changed from `(1440,4,4)` to `(1440,1440,4)` across NPY serialization, changing CPU convolution dispatch. The exporter now canonicalizes arrays and, crucially, loads the actual delivered `inputs.npy` before computing golden. r1 is preserved as failed evidence and must not be handed off. r2 passes without weakening bit equality.

## Graph and logical feasibility

`M0 → conv1 → M1 → relu1 → R1 → conv2 → M2 → relu2 → R2 → pool2 → P2`.

Conv1: `features.0`, 1→16, weight `(16,1,5)`, real bias `(16,)`. Conv2: `features.2`, 16→16, weight `(16,16,5)`, real bias `(16,)`. Both: kernel 5, stride 1, groups 1, dilation 1, zero padding 2 on each side. No BatchNorm or folding. MaxPool: kernel/stride 2, padding 0, dilation 1, ceil_mode=false.

Parameters: Conv1 384 B + Conv2 5184 B = **5568 B** logical Flash. Largest N=1 intermediate: **23040 B**. Two full-size activation buffers: **46080 B** logical RAM, excluding code/stack/workspace/alignment. No MCU memory/build or accuracy acceptance is claimed.

At r2 creation, M_final=P2 after `features.4` was a proposal; N=1 shape `(1,16,180)`. Actual milestones are M0, M1, R1, M2, R2, P2. All five output golden files exist. SV3 has since confirmed this boundary; release still requires explicit SV1 confirmation.

## Sample mapping

Exactly 20 distinct source tuples from the unchanged validation split, selected by numeric record ID, numeric R-peak then lead name. Original metadata row is zero-based. This is a deterministic numerical-debug set; it is not class-balanced or an accuracy evaluation. No refit, re-split or second normalization.

| Index | Sample ID | Patient | Original row |
|---:|---|---|---:|
| 0 | `MIT-BIH:105:197:MLII` | P105 | 0 |
| 1 | `MIT-BIH:105:459:MLII` | P105 | 1 |
| 2 | `MIT-BIH:105:708:MLII` | P105 | 2 |
| 3 | `MIT-BIH:105:965:MLII` | P105 | 3 |
| 4 | `MIT-BIH:105:1222:MLII` | P105 | 4 |
| 5 | `MIT-BIH:105:1479:MLII` | P105 | 5 |
| 6 | `MIT-BIH:105:1741:MLII` | P105 | 6 |
| 7 | `MIT-BIH:105:2015:MLII` | P105 | 7 |
| 8 | `MIT-BIH:105:2287:MLII` | P105 | 8 |
| 9 | `MIT-BIH:105:2550:MLII` | P105 | 9 |
| 10 | `MIT-BIH:105:2803:MLII` | P105 | 10 |
| 11 | `MIT-BIH:105:3052:MLII` | P105 | 11 |
| 12 | `MIT-BIH:105:3303:MLII` | P105 | 12 |
| 13 | `MIT-BIH:105:3563:MLII` | P105 | 13 |
| 14 | `MIT-BIH:105:3835:MLII` | P105 | 14 |
| 15 | `MIT-BIH:105:4102:MLII` | P105 | 15 |
| 16 | `MIT-BIH:105:4371:MLII` | P105 | 16 |
| 17 | `MIT-BIH:105:4635:MLII` | P105 | 17 |
| 18 | `MIT-BIH:105:4901:MLII` | P105 | 18 |
| 19 | `MIT-BIH:105:5154:MLII` | P105 | 19 |

## Artifact inventory

| Artifact | Path | Shape / file bytes | SHA-256 (raw) | Status |
|---|---|---|---|---|
| h | `firmware/head_parameters.h` | N/A / 34591 B | `168b1b6a1e7b79920800120e1e9a35845978debc25202678001aa6bd480f22d8` | REVIEW PASS |
| json | `firmware/host_c_verification.json` | N/A / 209 B | `ec4d4b1daf7fdf3ee6238cf00d59d6eaa42872601503a8eeb283af146d3e47f5` | REVIEW PASS |
| npy | `golden/M1.npy` | [20, 16, 360] / 460928 B | `8cc780759bd335304d5423782c5c9f75ce2bd9300370c0b7fe0de633cccbbe83` | REVIEW PASS |
| npy | `golden/M2.npy` | [20, 16, 360] / 460928 B | `4b7b84482f2641d354754d8daf724a904f7519a3e55654b364230c04f8c58d04` | REVIEW PASS |
| npy | `golden/P2.npy` | [20, 16, 180] / 230528 B | `5b9607815738e1a3a7ccde941e23a01a9ad927326839f38895e1f289e7d72399` | REVIEW PASS |
| npy | `golden/R1.npy` | [20, 16, 360] / 460928 B | `01dc25a4e8eb9e4ad3bcf246dd3e8ed85e06dc0df7af8e78f13b75800f0dc9a6` | REVIEW PASS |
| npy | `golden/R2.npy` | [20, 16, 360] / 460928 B | `5656055b57c370f17d64b5464021e8ad834b5319e01e9eafe8be2a069e0ab6a5` | REVIEW PASS |
| npy | `inputs.npy` | [20, 1, 360] / 28928 B | `dac1d1e9df849bf4ffa30359384d129586f67ec0703157b692d1344685b78dcc` | REVIEW PASS |
| pt | `model/checkpoint.pt` | N/A / 450551 B | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` | REVIEW PASS |
| json | `model/freeze_decision.json` | N/A / 1342 B | `dcc2dc065da318c1e8f3b13d5eb44e65105703287e1322033e26cce6e06e298d` | REVIEW PASS |
| json | `model/graph.json` | N/A / 10736 B | `74b5bab08a153ed751414d722e87ee5fe091e833ad3e8e159c680b87d7314e9d` | REVIEW PASS |
| json | `model/source/ml/configs/mitdb_week2_baseline.json` | N/A / 619 B | `273a563af79126c6ed6762c4bd01a186de055b6dea390688eefcf7522ae2e5e3` | REVIEW PASS |
| py | `model/source/ml/src/mitdb_baseline_model.py` | N/A / 2912 B | `520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14` | REVIEW PASS |
| py | `model/source/ml/src/mitdb_common.py` | N/A / 4052 B | `acd81b4aa9331d90cdb0abdaf16cb1935e9afbd6e34e654ac16dc5f51d236c1d` | REVIEW PASS |
| py | `model/source/ml/src/mitdb_week2_data.py` | N/A / 4619 B | `363f5298e4e723cac19e15e062346f24c808820fe180c292d25372574a2ba907` | REVIEW PASS |
| py | `model/source/ml/src/train_mitdb_baseline.py` | N/A / 13748 B | `a0fa0becf2539be37db9105eccb60d8ded8c25fae04d36fdda04ce6f82446152` | REVIEW PASS |
| py | `model/source/ml/src/week1_common.py` | N/A / 10331 B | `34c3402987e1f8712c844830c6db7a9325ef7a616e9d3dbe5dbb739f2fbc2dba` | REVIEW PASS |
| json | `model/train_config.json` | N/A / 635 B | `1f988328ea46db8537bc46d35b9cb5a0a165f128d2326366495fe26eda23715f` | REVIEW PASS |
| md | `README.md` | N/A / 6136 B | `a64fd4524358692d6e7e40a6c2b985caa5ccd530430256dfb6384fd83ace8c89` | REVIEW PASS |
| csv | `samples.csv` | N/A / 2430 B | `4a6356312d5f62da6b2fdf9e609843d4dea3fc5c20767e201ea21a075e6f227c` | REVIEW PASS |
| py | `scripts/export_week3.py` | N/A / 13434 B | `28b390c32ee598905995fe6c8c4f5c4ba5fc6e2852557da90ac6db9087ef4356` | REVIEW PASS |
| py | `scripts/verify_week3.py` | N/A / 8210 B | `21f902aa60447fdf3308fb20ccab29076746d4daffa78d53e99653191c5d3597` | REVIEW PASS |
| py | `scripts/week3_common.py` | N/A / 19498 B | `e31a4864eca69f456119602fb4ae0b5346167cedc03aa6d20ad328e0897cc93f` | REVIEW PASS |
| npy | `weights/conv1.bias.npy` | [16] / 192 B | `c636d074275bd3554444572472eebb0d4ae96c180be0002a08f34b569dcfefc4` | REVIEW PASS |
| npy | `weights/conv1.weight.npy` | [16, 1, 5] / 448 B | `a49e407cb77b07aafd28b0595dc523af2200f2e0f25e729442a2e3cda758bfca` | REVIEW PASS |
| npy | `weights/conv2.bias.npy` | [16] / 192 B | `67518978200e582715b5bc4505b70895ae0a059d8a7e0af9acffd3f72cd5cd47` | REVIEW PASS |
| npy | `weights/conv2.weight.npy` | [16, 16, 5] / 5248 B | `975561e10768b7c0adfb3d090ec587f44892429c0cee204da0f6905f034f5130` | REVIEW PASS |

NPY file sizes include a 128-byte format header; logical tensor bytes are in graph/manifest.

```text
ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/
  firmware/head_parameters.h
  firmware/host_c_verification.json
  golden/M1.npy
  golden/M2.npy
  golden/P2.npy
  golden/R1.npy
  golden/R2.npy
  inputs.npy
  manifest.json
  model/checkpoint.pt
  model/freeze_decision.json
  model/graph.json
  model/source/ml/configs/mitdb_week2_baseline.json
  model/source/ml/src/mitdb_baseline_model.py
  model/source/ml/src/mitdb_common.py
  model/source/ml/src/mitdb_week2_data.py
  model/source/ml/src/train_mitdb_baseline.py
  model/source/ml/src/week1_common.py
  model/train_config.json
  README.md
  samples.csv
  scripts/export_week3.py
  scripts/verify_week3.py
  scripts/week3_common.py
  weights/conv1.bias.npy
  weights/conv1.weight.npy
  weights/conv2.bias.npy
  weights/conv2.weight.npy
```

## Remaining gates and Git

M_final confirmation is the remaining SV1 release decision. After it is recorded, export a new ID under `ml/artifacts/week3/`, run verification without `--review`, then obtain SV1 device feasibility/output acceptance. Do not edit or relabel this review ID in place.

ONNX remains `BLOCKED_ON_SV2_INTERFACE`: delivery path, opset/runtime/provider, input/output names, fixed/dynamic dimensions, full/tail profile, output semantics, unchanged preprocessing ownership and verification dataset/tolerance/procedure must be agreed. No ONNX was generated.

Kept branch `docs/sv3-week1-week2-reports`, fast-forwarded to `6eb888b` without tracked content changes; pre-existing untracked reports remain intact. No new commit, push or PR while final verification/release gate is blocked. Model artifacts remain local/ignored per repository policy; no force-add. `git diff --check` passed.

## Continuation audit and revalidation

The continuation re-read Git state and all Week 3 source/config/evidence. HEAD
remains `6eb888b4215b9961ee879e4b794fd99ae50e2866` on
`docs/sv3-week1-week2-reports`. No Python/JSON file was truncated: all four source
scripts parsed, and exporter/verifier/common remain byte-identical to r2's
bundled scripts. Only documentation needed repair: Unicode arrows/dashes had
been replaced by question marks during evidence generation. No source,
methodology, checkpoint, preprocessing, selection rule or review package changed.

Revalidation executed:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3.py --repo-root . --package ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2
& ml/.venv/Scripts/python.exe -B ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2/scripts/verify_week3.py --repo-root . --package ml/data/week3_review/mitdb-epoch3-fp32-review-20260925-r2 --review
& ml/.venv/Scripts/python.exe -B ml/scripts/export_week3.py --repo-root . --decision ml/configs/week3_model_freeze.json --handoff-id mitdb-epoch3-fp32-review-20260925-r2-continuation-check1 --review
git diff --check
```

All exited 0: exact 20 samples, source/data hashes, graph/schema, all five golden
milestones, compiled C bit equality and all 12 expected rejections passed again.
The fresh review export, ending `-continuation-check1`, reproduced all 26
non-README/non-manifest files byte-for-byte against r2. Every r2 file and the
manifest hash above were independently checked unchanged. Both pre-existing
Week 1/2 report hashes still match the audit. Whitespace checks also included
the untracked Week 3 files, which ordinary `git diff --check` does not cover.

Both explicit release attempts were correctly refused with exit 1:

- `verify_week3.py` on r2 without `--review`: `Release gate: review package has no confirmed M_final`.
- `export_week3.py` with the current decision and without `--review`: `OPEN_DECISION: M_final requires SV3/SV1 confirmation; no release`.

Neither attempt created `ml/artifacts/week3/`. These are successful rejection
checks, not a release-verifier PASS. No training was run.

`git fetch origin` completed again; the relevant remote branch still points to
`6eb888b`. Searches of the current Edge/contracts/configs/docs and remote history
found no new agreed SV2 ONNX interface. `BLOCKED_ON_SV2_INTERFACE` remains.
No commit, push or PR was created during that revalidation. At that time M_final=P2 remained a proposal only; the later SV3-only confirmation is recorded at the top of this document and in the current freeze config.

## SV3-only boundary confirmation (historical stage)

At this stage the config recorded separate `sv3_confirmation` and `sv1_confirmation`
objects, with aggregate status `SV3_CONFIRMED_SV1_PENDING`. The current release
gate rejects both this state and a generic `CONFIRMED` flag without explicit
SV1 evidence for the same milestone. The scripts bundled in immutable r2 retain
their historical bytes; current source validation has advanced independently.
No final package is issued. After explicit SV1 confirmation, record its evidence,
create a NEW handoff ID under `ml/artifacts/week3/`, and run release verification
without `--review`; preserve r2 as review evidence. No MCU PASS is implied.

Validation after this decision: `test_week3.py` passed the original 12 review
rejections plus 2 one-party-consent regressions (14 total), including raw-derived
inputs, exact golden and compiled C checks. A test-helper name collision found
on the first attempt was corrected before the successful rerun; no model or
package changed. Release export with the current config exits 1 with
`SV1 confirmation PENDING`. All r2 file hashes and its manifest hash remain
unchanged, `ml/artifacts/week3/` is absent, and `git diff --check` passes.
