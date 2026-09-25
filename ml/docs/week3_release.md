# SV3 Week 3: v2 release candidate after SV1 review

Current candidate: **mitdb-week3-fp32-20260925-v2**. PR [#11](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/11) is OPEN, not merged; base `dev/device-sv1`, head `sv3/week3-fp32-handoff`. SV1 package acceptance and MCU validation remain PENDING. Overall Week 3: **NOT DONE**.

## v1 status and preserved evidence

`mitdb-week3-fp32-20260925-v1` was internally released, then superseded after SV1 found verifier assurance gaps. Its external disposition is **SUPERSEDED_PENDING_VERIFIER_HARDENING**. No scientific tensor inconsistency was found. The v1 directory, ZIP and versioned historical evidence remain unchanged; no embedded status was edited. Review r2 also remains byte-identical and is not relabelled.

The earlier report incorrectly said 15 scientific payload files. Computing `len(r2_payload_identical_files)` from the [historical verification JSON](../provenance/week3/mitdb-week3-fp32-20260925-v1.verification.json) gives **14**. The earlier PR-creation 403 is historical: PR #11 now exists. Do not create another PR or merge it.

## Corrections and regression evidence

| SV1 finding | Correction | Regression and expected rejection |
|---|---|---|
| Manifest not independently authenticated | Release `verify()` and CLI require an external expected SHA-256; authenticate raw bytes before parsing those same bytes | Missing anchor rejected; metadata-only mutation, mutation plus rebuilt inventory, and invalid JSON all reject at manifest hash gate |
| model_version not pinned | Authoritative `MODEL_NAME = MODEL_VERSION = mitdb_week2_cnn_v1`; `check_decision` pins both, then manifest must agree | Version changed in both manifest/decision with rebuilt inventory and test-controlled anchor rejects `Frozen model_version mismatch` |
| Missing mandatory test script | Required file set includes `scripts/test_week3.py` | Deletion plus rebuilt inventory/test anchor rejects `Missing required package files` |
| Dtype/NaN tests hit stale hashes | Independent test-only inventory builder records actual corrupted bytes and NPY metadata; semantic fixtures get explicit test-controlled anchors | Wrong dtype rejects `Wrong tensor dtype`; NaN rejects `Non-finite tensor` |
| Insufficient identity/shape regressions | Explicit identity presence/format and tensor-shape gates | Duplicate ID/source, missing identity value/column, malformed ID and wrong input/golden shapes each assert their specific rejection |
| Documentation discrepancies | Count derived from JSON, PR status corrected, recipient paths relative, v1 supersession external | File/hash comparison and generated evidence below |

Semantic fixtures deliberately receive a new test-controlled anchor to isolate inner validation. Root-of-trust fixtures retain the original independent anchor. Production never derives an expected hash from the received package. Exporter's internal validation uses the digest of bytes it just generated; recipients must instead use this versioned evidence or the trusted PR.

Review mode may omit the external hash for **unauthenticated technical checks only** (`manifest_authenticated=false`, `release_eligible=false`). If supplied, the hash is checked before parsing. Current review still enforces frozen identity and required scripts. Legacy r2 keeps its historical version label/scripts and historical PASS evidence; it is not claimed to pass the hardened current verifier. Do not use `--review` to accept a release package.

Mandatory-file audit against contract section 3: explicit required set covers README, checkpoint/config/graph/freeze, CSV/input, four actual Conv parameter arrays, C header/evidence and all four scripts. Manifest is opened and externally authenticated first. Six source blobs are required by their frozen source-key set and matched against Git; five golden files and the complete tensor set are required by the traced graph. No BN or extra parameter file is needed for this graph.

## Candidate identity and transport

- Package: `ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/` (29 files; 2726226 total bytes).
- ZIP: `ml/artifacts/week3/mitdb-week3-fp32-20260925-v2.zip` (1602725 bytes).
- Checkpoint SHA-256: `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
- Manifest SHA-256 (external trust anchor): `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`.
- ZIP SHA-256: `d5511f8c5ebfb1e9eced4aea2f8e89a20dd142b79987a40f6a3347d33d7481eb`.
- [Exact manifest copy](../provenance/week3/mitdb-week3-fp32-20260925-v2.manifest.json) and [verification/comparison evidence](../provenance/week3/mitdb-week3-fp32-20260925-v2.verification.json).

Model name/version `mitdb_week2_cnn_v1`, MIT-BIH/1.0.0, epoch 3, FP32, seed 30, quantization `not_applicable`. Historical source commit `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`. No retraining, preprocessing change or sample reselection. Historical validation/test accuracy remains 84.488%/98.221%; test S/F/Q recall remains zero.

Independent SV3 and SV1 boundary confirmations remain in [freeze decision](../configs/week3_model_freeze.json). Segment: Conv1 -> ReLU1 -> Conv2 -> ReLU2 -> MaxPool1d, ending at `P2` after `features.4`; N=1 shape `(1,16,180)`. Boundary confirmation does not establish package or device acceptance.

## All differences versus v1

Exactly six files changed, with old/new SHA-256 values in the comparison evidence; no file added or removed:

- `README.md`
- `manifest.json`
- `scripts/export_week3.py`
- `scripts/test_week3.py`
- `scripts/verify_week3.py`
- `scripts/week3_common.py`

The other 23 files are byte-identical, including graph, freeze decision, six original source snapshots and C compiler evidence. All 14 selected scientific payload files are byte-identical:

- `firmware/head_parameters.h`
- `golden/M1.npy`
- `golden/M2.npy`
- `golden/P2.npy`
- `golden/R1.npy`
- `golden/R2.npy`
- `inputs.npy`
- `model/checkpoint.pt`
- `model/train_config.json`
- `samples.csv`
- `weights/conv1.bias.npy`
- `weights/conv1.weight.npy`
- `weights/conv2.bias.npy`
- `weights/conv2.weight.npy`

All 20 CSV identities/order and all NPY/checkpoint bytes are unchanged. Review r2 directory was compared with the pre-work hash snapshot; v1 ZIP still hashes to `59a3d5ac9546c754ddeaca6fa3f207c08a8724148f55d8d3b58c32e8ba7b75c3`.

## Verification performed

All commands completed with exit 0 using the pinned environment and host GCC, without `--review`:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/export_week3.py --repo-root . --decision ml/configs/week3_model_freeze.json --handoff-id mitdb-week3-fp32-20260925-v2
& ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/scripts/verify_week3.py --repo-root . --package ml/artifacts/week3/mitdb-week3-fp32-20260925-v2 --expected-manifest-sha256 0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469
& ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/scripts/test_week3.py --repo-root . --package ml/artifacts/week3/mitdb-week3-fp32-20260925-v2 --expected-manifest-sha256 0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469
& ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/scripts/export_week3.py --repo-root . --decision ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/model/freeze_decision.json --handoff-id mitdb-week3-fp32-20260925-v2-repro
```

The hardened source suite also passed on immutable v1 before v2 export. Export includes the historical Week 2 CUDA metric/provenance check. Release verification returned `HANDOFF_CHECKS_PASS`, externally authenticated manifest, 20 raw-derived inputs and all five recomputed golden tensors. Complete negative suite: **27/27 expected rejections**, each matching its expected reason; original package unchanged.

GCC 15.2.0 compiled the header with `-std=c99 -Wall -Wextra -Werror -pedantic`; all **1392 FP32 parameter bit patterns** matched. Reproduction `mitdb-week3-fp32-20260925-v2-repro`: **27 identical files**; only README and manifest differ for the new ID and dependent hashes. Reproduction manifest SHA-256: `234ec090939875d8eedd5bfbf0eb94f2fb715bfc8ff43d2fb75ca976ad5decb1`. Every ZIP member was checked against package bytes. Whitespace checks run before commit and on the staged changes.

## SV1 runtime blocker and recipient commands

SV1's machine currently lacks the pinned environment/torch/package/data. This blocks independent execution on that machine; it does not justify weakening verification. Receive the whole ZIP separately: repository policy excludes generated model binaries, and cloning PR #11 does not deliver them. No upload or SV1 receipt is claimed.

Required: Python **3.11.9**, torch **2.14.0+cu130**, numpy **2.4.6**, pandas **3.0.5**, scipy **1.17.1**, wfdb **4.3.1**, plus the pinned requirements and host GCC (validated with 15.2.0). Full verification uses CPU but still requires the recorded torch build; export reproduction additionally requires the historical CUDA runtime. Do not substitute CPU-build version metadata or bypass dependency checks.

Receive/preserve the frozen Week 1 `ml/data/raw/mitdb/` (48 records and checksum manifest), `ml/data/processed/mitdb/` (train/val/test arrays, metadata and processed manifest), tracked configs, normalization and patient manifest. The historical Git object and clean tracked scientific sources are required. Export also needs historical Week 2 artifacts in `ml/data/week2/mitdb_baseline/`. Do not regenerate or refit data to work around missing files. The verifier checks their hashes and regenerates the 20 selected inputs from raw ECG.

```powershell
# From repository root, using an installed Python 3.11.9.
py -3.11 -c "import sys; assert sys.version_info[:3] == (3,11,9), sys.version"
py -3.11 -m venv ml/.venv
& ml/.venv/Scripts/python.exe -m pip install -r ml/requirements-gpu-cu130.txt
& ml/.venv/Scripts/python.exe -m pip check
# GCC must be on PATH. Local MSYS2 example only, adapt to your installation:
$env:PATH = 'C:/msys64/ucrt64/bin;' + $env:PATH
gcc --version
git cat-file -e '8e98a0e4851abc979feb5fd5b97ece612b02cfaa^{commit}'
$pkg = 'ml/artifacts/week3/mitdb-week3-fp32-20260925-v2'
$trustedManifestSha = '0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469'
$trustedZipSha = 'd5511f8c5ebfb1e9eced4aea2f8e89a20dd142b79987a40f6a3347d33d7481eb'
if ((Get-FileHash "$pkg.zip" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $trustedZipSha) { throw 'ZIP SHA mismatch' }
# Extract only after ZIP authentication, into an empty recipient location.
Expand-Archive -LiteralPath "$pkg.zip" -DestinationPath ml/artifacts/week3
# Use trusted checkout code before executing bundled scripts.
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3.py --repo-root . --package $pkg --expected-manifest-sha256 $trustedManifestSha
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3.py --repo-root . --package $pkg --expected-manifest-sha256 $trustedManifestSha
```

If the package is already extracted, skip `Expand-Archive`; never overwrite an immutable revision. These are recipient setup instructions, not a claim that SV1 has executed them. The independently trusted hashes above are copied literally, not calculated from the received manifest as the expected value.

## Pending device and SV2 work

SV1 package acceptance: **PENDING**. MCU validation: **PENDING**. MCU 20/20: **NOT YET TESTED**. SV1 must record all 20 per-sample P2 errors strictly below `1e-3`, intermediate errors, firmware commit and actual Flash/RAM/workspace/stack. Logical estimates remain 5568 B parameters, 23040 B largest N=1 activation, 46080 B two buffers; these are not device measurements.

SV2: **BLOCKED_ON_SV2_INTERFACE** (delivery path, runtime/opset, tensor names/dimensions, full/tail semantics, preprocessing ownership and verification procedure). Overall Week 3: **NOT DONE**. PR #11 must remain unmerged pending SV1 review.

PR description delivery: the GitHub connector returned HTTP 403 on update. The existing Git credentials successfully updated PR #11 through the GitHub API; a read-back confirmed the body exactly matches `ml/docs/week3_pr_body.md`, state OPEN and merged=false. No new PR or merge action was taken.
