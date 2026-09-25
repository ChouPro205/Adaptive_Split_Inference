# Week 3 SV3 to SV1 official FP32 release

**SV3 RELEASE PACKAGE: PASS. Entire Week 3 is not DONE.**

| Acceptance | Status |
|---|---|
| SV3 boundary | CONFIRMED |
| SV1 boundary | CONFIRMED (explicit approval relayed authoritatively by user) |
| SV3 release package | PASS |
| SV1 package review | PENDING |
| SV1 MCU validation | PENDING |
| MCU 20/20 | NOT YET TESTED |
| SV2 ONNX | BLOCKED_ON_SV2_INTERFACE |

## Identity and delivered bytes

- Contract: `w3-sv1-handoff-v1`; handoff ID: `mitdb-week3-fp32-20260925-v1`.
- Model name/version: `mitdb_week2_cnn_v1` / `mitdb_week2_cnn_v1`; epoch 3; MIT-BIH/1.0.0.
- Precision `fp32`; quantization `not_applicable`; no INT8 scale/zero-point/axis/clamp/requantization.
- Full checkpoint dictionary, unchanged bytes: `model/checkpoint.pt`.
- Actual delivered checkpoint SHA-256: `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` (450551 bytes).
- Model source commit: `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`.
- Manifest raw SHA-256: `437a2a7db9f58d5d6896e8f50102c8b9b0a43b585d41c363420a1e9ca7309f2d`.
- Package: `C:/Users/Admin/Adaptive_Split_Inference/ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/`.
- File count: 29; total file bytes: 2717936.
- [Versioned manifest copy](../provenance/week3/mitdb-week3-fp32-20260925-v1.manifest.json) (byte-identical to package manifest).
- [Verification summary](../provenance/week3/mitdb-week3-fp32-20260925-v1.verification.json).
- [Local package README](../artifacts/week3/mitdb-week3-fp32-20260925-v1/README.md).

The current release uses `model_version=mitdb_week2_cnn_v1` exactly as the authoritative release request specifies. Historical r2 used a delivery-version label `week3-fp32-epoch3`; only release metadata changed, not the frozen model, checkpoint or scientific tensors. Source hashes inside the checkpoint retain their original historical four-file provenance; the six-file current source gate remains enforced.

## Boundary and graph

Both confirmations are recorded separately with authority and verbatim evidence in [freeze decision](../configs/week3_model_freeze.json). SV1 explicitly approved P2 as the output of features.4 MaxPool1d and the complete five-op port scope. Boundary approval does not establish package acceptance or device measurements.

`M0 -> features.0 Conv1d -> M1 -> ReLU1 -> R1 -> features.2 Conv1d -> M2 -> ReLU2 -> R2 -> features.4 MaxPool1d -> P2 = M_final`.

| Operation | Parameters | N=1 output |
|---|---|---|
| Conv1, features.0 | 1 to 16 channels; weight (16,1,5); bias (16,) | (1,16,360) |
| ReLU1, features.1 | inplace=false | (1,16,360) |
| Conv2, features.2 | 16 to 16 channels; weight (16,16,5); bias (16,) | (1,16,360) |
| ReLU2, features.3 | inplace=false | (1,16,360) |
| MaxPool1d, features.4 | kernel/stride 2; padding 0; dilation 1; ceil_mode=false | (1,16,180) |

Both Conv: kernel 5, stride 1, zero padding 2 left/right, dilation 1, groups 1, real bias. No BatchNorm and no BN folding. Graph metadata is regenerated from actual checkpoint execution, not copied from prose. Parameters are `<f4` C-order; Conv weights use (C_out,C_in/groups,K), activations NCL.

## Samples, golden and C header

Exactly the original r2 20 real source samples and ordering are preserved. `samples.csv`, `inputs.npy`, all four parameter arrays, `head_parameters.h`, checkpoint/train config and all five golden files are byte-identical to r2 (15 files). Each input was independently checked against checksummed raw ECG plus frozen Week 1 preprocessing. No refit, resplit, second normalization, retraining or tuning occurred.

Golden milestones: M1, R1, M2, R2, P2. Export saves inputs.npy, reloads that exact file, then computes golden in eval/inference mode on CPU, batch 1, one thread, MKLDNN disabled. The r1 serialization/stride fix remains intact. The host C99 compiler verified all 1392 FP32 parameter bits against NPY arrays; GCC 15.2.0 used `-std=c99 -Wall -Wextra -Werror -pedantic`.

## Commands and exit statuses

Commands ran from repository root using the pinned Python 3.11 environment. No command below uses --review.

| Command | Exit | Result |
|---|---:|---|
| `ml/.venv/Scripts/python.exe -B ml/scripts/export_week3.py --repo-root . --decision ml/configs/week3_model_freeze.json --handoff-id mitdb-week3-fp32-20260925-v1` | 0 | HANDOFF_CHECKS_PASS |
| `ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/scripts/verify_week3.py --repo-root . --package ml/artifacts/week3/mitdb-week3-fp32-20260925-v1` | 0 | HANDOFF_CHECKS_PASS; release_eligible=true |
| `ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/scripts/test_week3.py --repo-root . --package ml/artifacts/week3/mitdb-week3-fp32-20260925-v1` | 0 | 14 expected rejections; real package unchanged |
| `ml/.venv/Scripts/python.exe -B ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/scripts/export_week3.py --repo-root . --decision ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/model/freeze_decision.json --handoff-id mitdb-week3-fp32-20260925-v1-repro` | 0 | HANDOFF_CHECKS_PASS for separate reproduction ID |
| `ml/.venv/Scripts/python.exe -B -` (inline byte comparison, r2 preservation and ZIP round-trip audit) | 0 | 27 reproduced files identical; 15 payload files identical to r2; archive entries equal package |
| `git diff --check` | 0 | No whitespace errors |
| `git diff --cached --check` | 0 | Staged text files pass whitespace checks |
| `ml/.venv/Scripts/python.exe -B -` (initial pre-commit source/bundle audit) | 1 | Decision JSON raw formatting differed; audit assumption corrected below |
| `ml/.venv/Scripts/python.exe -B -` (corrected canonical decision/source and staged-policy audit) | 0 | Source scripts match bundle bytes, canonical decision matches, reports unchanged, only 14 allowed text files staged |

The initial pre-commit check compared raw source-config formatting with the
exporter's documented JSON serialization. Source uses compact arrays; the
package uses `json.dumps(indent=2, ensure_ascii=False)` with UTF-8/LF. Comparing
the canonical serialization proved the exact delivered bytes match. No package,
approval value or verifier was changed to resolve this audit-only mismatch.

Exporter includes the historical Week 2 CUDA verifier: checkpoint/config/source/Week 1 provenance and recorded validation/test metrics were rechecked without training. Earlier full read-only Week 1/2 results remain in [audit](week3_audit.md).

Negative tests cover: missing SV1 confirmation; missing real bias; changed input, golden and weight despite rehashed inventory; wrong sample order; omitted intermediate ReLU; changed C representation; wrong dtype; non-finite golden; immutable revision overwrite; missing boundary approval; SV3-only consent; and a generic approval flag without explicit SV1 evidence. The last two remain active after approval via isolated in-memory negative fixtures.

Reproduction ID `mitdb-week3-fp32-20260925-v1-repro`: all 27 non-README/non-manifest files are byte-identical. README and manifest differ only as expected for the new ID/location and dependent hashes. Review r2 remains unchanged, including manifest SHA-256 `24300d18044640c83722073dd692cff540721cdf027d9fe31e29a87e7d480a88`; it is not relabeled or used as the release directory.

## Logical resource estimates

| Resource | Bytes |
|---|---:|
| Conv1 parameters | 384 |
| Conv2 parameters | 5184 |
| Total parameters / logical persistent Flash | 5568 |
| Largest N=1 intermediate | 23040 |
| Two full-size activation buffers | 46080 |

These are logical estimates only. Actual nRF52840 image Flash/RAM, alignment, kernel workspace, stack and measurements must come from SV1. No device latency, energy or 20/20 PASS is claimed.

## Out-of-band transfer and Git policy

`.gitignore` excludes *.pt, and ml/README.md intentionally excludes generated model artifacts. The Week 3 directory is now explicitly ignored to prevent accidentally committing a partial package. Contract section 2 permits transferring the entire directory outside Git. This PR versions only source/config/docs and small manifest/evidence copies; it does not contain checkpoint/input/weight/golden binaries.

Transfer the whole `mitdb-week3-fp32-20260925-v1/` folder unchanged, or transfer and extract the prepared ZIP:

- Actual ZIP: `C:/Users/Admin/Adaptive_Split_Inference/ml/artifacts/week3/mitdb-week3-fp32-20260925-v1.zip`.
- [Local ZIP](../artifacts/week3/mitdb-week3-fp32-20260925-v1.zip), 1601258 bytes.
- ZIP SHA-256: `59a3d5ac9546c754ddeaca6fa3f207c08a8724148f55d8d3b58c32e8ba7b75c3`.
- Every ZIP entry was compared byte-for-byte with the official directory. ZIP metadata is outside the package manifest; the external archive hash pins the complete transport file.
- No transfer service or remote artifact URL is defined by the repo. No upload or receipt by SV1 is claimed. SV1 must receive the entire folder/ZIP separately; cloning the PR is insufficient.

The largest package file is 460928 bytes, below GitHub's 100 MiB regular-file limit ([official GitHub documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)). Size is not the reason for out-of-band delivery; the repository artifact policy is.

After receipt, validate archive/manifest hashes and run:

```powershell
$pkg = 'ml/artifacts/week3/mitdb-week3-fp32-20260925-v1'
& ml/.venv/Scripts/python.exe -B "$pkg/scripts/verify_week3.py" --repo-root . --package $pkg
```

The repository checkout needs the preserved historical commit and the external Week 1 MIT-BIH raw/processed data for full input verification. Package README lists exact dependencies and how to debug sample_index=0 at M1, then progress through the other milestones. SV1 must compare all 20 samples at P2 with strict max(abs(MCU-PyTorch)) < 1e-3 and record intermediate errors.

## SV2 and remaining work

Rechecked origin and Edge/contracts: no approved ONNX opset/runtime/provider, delivery path, input/output naming, dimensions, full/tail semantics or verification tolerance/procedure. ONNX remains BLOCKED_ON_SV2_INTERFACE. No unofficial export was invented.

Remaining: SV1 package review, nRF52840 execution, all 20 MCU/PyTorch comparisons, actual firmware resource measurements, and SV2 interface/export verification. Entire Week 3 is not complete.

## Artifact inventory

| Artifact | Path | Shape / file bytes | SHA-256 (raw) | Status |
|---|---|---|---|---|
| h | `firmware/head_parameters.h` | N/A / 34591 | `168b1b6a1e7b79920800120e1e9a35845978debc25202678001aa6bd480f22d8` | PASS |
| json | `firmware/host_c_verification.json` | N/A / 209 | `ec4d4b1daf7fdf3ee6238cf00d59d6eaa42872601503a8eeb283af146d3e47f5` | PASS |
| npy | `golden/M1.npy` | [20, 16, 360] / 460928 | `8cc780759bd335304d5423782c5c9f75ce2bd9300370c0b7fe0de633cccbbe83` | PASS |
| npy | `golden/M2.npy` | [20, 16, 360] / 460928 | `4b7b84482f2641d354754d8daf724a904f7519a3e55654b364230c04f8c58d04` | PASS |
| npy | `golden/P2.npy` | [20, 16, 180] / 230528 | `5b9607815738e1a3a7ccde941e23a01a9ad927326839f38895e1f289e7d72399` | PASS |
| npy | `golden/R1.npy` | [20, 16, 360] / 460928 | `01dc25a4e8eb9e4ad3bcf246dd3e8ed85e06dc0df7af8e78f13b75800f0dc9a6` | PASS |
| npy | `golden/R2.npy` | [20, 16, 360] / 460928 | `5656055b57c370f17d64b5464021e8ad834b5319e01e9eafe8be2a069e0ab6a5` | PASS |
| npy | `inputs.npy` | [20, 1, 360] / 28928 | `dac1d1e9df849bf4ffa30359384d129586f67ec0703157b692d1344685b78dcc` | PASS |
| pt | `model/checkpoint.pt` | N/A / 450551 | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` | PASS |
| json | `model/freeze_decision.json` | N/A / 2430 | `d69f0bf0887a965c806984716f556fb444ef2db64c7b6f0d708156d8e1b3a004` | PASS |
| json | `model/graph.json` | N/A / 10732 | `ba25cc2d9225ae8f87a656179c79cddb0d9a96413104a36990d46eea15dccc60` | PASS |
| json | `model/source/ml/configs/mitdb_week2_baseline.json` | N/A / 619 | `273a563af79126c6ed6762c4bd01a186de055b6dea390688eefcf7522ae2e5e3` | PASS |
| py | `model/source/ml/src/mitdb_baseline_model.py` | N/A / 2912 | `520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14` | PASS |
| py | `model/source/ml/src/mitdb_common.py` | N/A / 4052 | `acd81b4aa9331d90cdb0abdaf16cb1935e9afbd6e34e654ac16dc5f51d236c1d` | PASS |
| py | `model/source/ml/src/mitdb_week2_data.py` | N/A / 4619 | `363f5298e4e723cac19e15e062346f24c808820fe180c292d25372574a2ba907` | PASS |
| py | `model/source/ml/src/train_mitdb_baseline.py` | N/A / 13748 | `a0fa0becf2539be37db9105eccb60d8ded8c25fae04d36fdda04ce6f82446152` | PASS |
| py | `model/source/ml/src/week1_common.py` | N/A / 10331 | `34c3402987e1f8712c844830c6db7a9325ef7a616e9d3dbe5dbb739f2fbc2dba` | PASS |
| json | `model/train_config.json` | N/A / 635 | `1f988328ea46db8537bc46d35b9cb5a0a165f128d2326366495fe26eda23715f` | PASS |
| md | `README.md` | N/A / 6251 | `ee700987f3df3e57286bafbd1581feede9152616ccaa0bba161e6d22fee39964` | PASS |
| csv | `samples.csv` | N/A / 2430 | `4a6356312d5f62da6b2fdf9e609843d4dea3fc5c20767e201ea21a075e6f227c` | PASS |
| py | `scripts/export_week3.py` | N/A / 13877 | `db3ca6abde22df10a3f3b1f020fcd9135b34805cdfff6736ffe3699ba4c255e6` | PASS |
| py | `scripts/test_week3.py` | N/A / 7292 | `fde7fcffbfd103b4194406eb015b93b5c3deca8fd0b237ddebe487defc9cd89d` | PASS |
| py | `scripts/verify_week3.py` | N/A / 8595 | `383eaac60f03deae3ba10201d114319646a7751bb101f6d410651b06d637bba0` | PASS |
| py | `scripts/week3_common.py` | N/A / 20408 | `2f9f29cbc7e4c67a7fb74151238cf82456d81ab97ff1e65d30fc5f98a534cb25` | PASS |
| npy | `weights/conv1.bias.npy` | [16] / 192 | `c636d074275bd3554444572472eebb0d4ae96c180be0002a08f34b569dcfefc4` | PASS |
| npy | `weights/conv1.weight.npy` | [16, 1, 5] / 448 | `a49e407cb77b07aafd28b0595dc523af2200f2e0f25e729442a2e3cda758bfca` | PASS |
| npy | `weights/conv2.bias.npy` | [16] / 192 | `67518978200e582715b5bc4505b70895ae0a059d8a7e0af9acffd3f72cd5cd47` | PASS |
| npy | `weights/conv2.weight.npy` | [16, 16, 5] / 5248 | `975561e10768b7c0adfb3d090ec587f44892429c0cee204da0f6905f034f5130` | PASS |

Manifest does not hash itself. Its external hash is given above. NPY file size includes the 128-byte format header; tensor logical sizes are separate.

```text
mitdb-week3-fp32-20260925-v1/
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
  scripts/test_week3.py
  scripts/verify_week3.py
  scripts/week3_common.py
  weights/conv1.bias.npy
  weights/conv1.weight.npy
  weights/conv2.bias.npy
  weights/conv2.weight.npy
```
