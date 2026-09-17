# Week 1 review traceability

| Review item | Classification | Implementation | Verification |
|---|---|---|---|
| P0 PTB-XL pipeline | [EXPLICIT] | `ptbxl_week1_config.json`; downloader; patient/SCP manifest builder; train-only per-lead normalization; strict verifier | 21,799 records, 18,869 patients, `(1000,12)`, fixed lead order, 61,007 SCP assignments, no leakage, 43,601 files checksummed |
| P0 MIT-BIH integrity | [EXPLICIT] | v1.0.0 metadata, official 48-record list, `.hea/.dat/.atr` completeness, pinned official checksum manifest hash | 48 records and 144 files match PhysioNet SHA-256 |
| P0 false PASS prevention | [EXPLICIT] | common non-empty/count/file requirements and explicit exceptions | negative suite covers empty MIT/PTB-XL, missing record/header/data/annotation, wrong checksum |
| P0 no critical `assert` | [EXPLICIT] | all Week 1 invariants use explicit `require(...)`/exceptions | source scan has no Python `assert`; normal and `python -O` negative results match |
| P1 config source of truth | [EXPLICIT] | dataset configs plus shared MIT/PTB helpers | config SHA-256 is printed and bound into normalization/processed/run manifests |
| P1 reproducible environment | [EXPLICIT] | environment config, CPU/GPU requirement selectors, version-aware checker, Windows/Linux instructions | Python/package/CUDA tensor checks pass on the recorded machine |
| P1 provenance | [EXPLICIT] | `run_week1_verification.py` and JSON run manifest | UTC, Git state, commands, versions, dataset/config/checksum/artifact hashes, exit statuses |
| P2 integration contract | [EXPLICIT, non-blocking for Week 1] | data-side contract in `week1_data_contract.md` | shapes/layouts/units/normalization/labels fixed; ONNX and quantization explicitly deferred |

The implementation intentionally does not include a 1D-CNN, privacy attack,
ONNX export, split-model deployment, or quantization.
