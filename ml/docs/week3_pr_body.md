SV1 review found assurance gaps in the v1 verifier: manifest metadata was not independently authenticated, model_version was not pinned, and the required-file set omitted the negative-test script. This update fixes those gates and provides **mitdb-week3-fp32-20260925-v2** as the current release candidate. **Do not merge yet: SV1 package acceptance is PENDING.**

v1 remains immutable and unchanged, with external disposition `SUPERSEDED_PENDING_VERIFIER_HARDENING`. No scientific inconsistency was found. Review r2 also remains unchanged.

- Release verification now requires an independently trusted manifest SHA-256 before JSON parsing.
- `MODEL_NAME` and `MODEL_VERSION` are both pinned to `mitdb_week2_cnn_v1`.
- `scripts/test_week3.py` is mandatory; semantic negative fixtures rebuild file hashes and assert specific errors.
- **27/27** negative cases PASS, including root-of-trust, version, missing-file, dtype/NaN, identity and shape regressions.
- Export and hardened release verifier PASS without `--review`; 20 raw-derived inputs, all five golden tensors, and 1392 C99 parameter bit patterns verified.
- Separate reproduction: 27 identical files, with README/manifest differences for the new ID.
- All **14** scientific payload files remain byte-identical to v1. Only README, manifest and the four scripts changed (six files total); graph/decision/original source blobs also remain identical.

Model: MIT-BIH/1.0.0, epoch 3, FP32, checkpoint SHA-256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`. Confirmed segment remains Conv1 -> ReLU1 -> Conv2 -> ReLU2 -> MaxPool1d; `M_final=P2` after `features.4`, N=1 `(1,16,180)`. Boundary approval is separate from package/device acceptance.

Delivery outside Git under repository artifact policy:

- Package: `ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/` (29 files).
- ZIP: `ml/artifacts/week3/mitdb-week3-fp32-20260925-v2.zip` (1602725 bytes).
- **Trusted manifest SHA-256:** `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`.
- **ZIP SHA-256:** `d5511f8c5ebfb1e9eced4aea2f8e89a20dd142b79987a40f6a3347d33d7481eb`.
- [Manifest](ml/provenance/week3/mitdb-week3-fp32-20260925-v2.manifest.json), [comparison/evidence](ml/provenance/week3/mitdb-week3-fp32-20260925-v2.verification.json), [release report and exact environment/verify commands](ml/docs/week3_release.md).

SV1 currently lacks the pinned environment/torch/package/data. Transfer the whole ZIP and frozen data separately; cloning this PR is insufficient. No receipt or upload is claimed. Use trusted checkout verifier code with the external hash above; do not weaken checks or use `--review` for release acceptance.

SV1 package review and MCU validation **PENDING**; MCU 20/20 **NOT YET TESTED**. SV2 **BLOCKED_ON_SV2_INTERFACE**. Entire Week 3 **NOT DONE**. Same branch `sv3/week3-fp32-handoff`, base `dev/device-sv1`; update existing PR #11 only.
