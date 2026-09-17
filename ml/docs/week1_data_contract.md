# Week 1 data contract (pre-model)

This document fixes only the data-side contract needed before model work. ONNX
opset, tensor names, split points, quantization scale/zero-point, and generated
headers remain Week 2/3 decisions and are deliberately not implemented here.

## MIT-BIH

- One sample is one annotation-centred MLII beat.
- Stored `X` layout: `(N, 360)`; future model view: `(N, C=1, L=360)`.
- Signal unit before normalization: physical WFDB signal (mV).
- Normalization: global Z-score, one scalar mean/std fitted on train beats only.
- Stored dtype: `float32`; target dtype: `int64`.
- Class order: `N=0, S=1, V=2, F=3, Q=4`.
- Metadata binds each row to patient, record, R-peak sample, raw annotation,
  AAMI class, and selected lead index.

## PTB-XL

- One sample is a complete 10-second, 12-lead record at 100 Hz.
- WFDB/on-disk layout: `(L=1000, C=12)`; future model view: `(N, C=12, L=1000)`.
- Lead order: `I, II, III, AVR, AVL, AVF, V1, V2, V3, V4, V5, V6`.
- Signal unit before normalization: mV.
- Normalization: per-lead global Z-score, fitted only on official folds 1–8.
- Intended normalized dtype: `float32`; raw WFDB files remain authoritative.
- Labels: multi-label SCP dictionary `code -> likelihood`, serialized as
  canonical sorted JSON in the patient manifest. No forced single-class label.
- Split: official `strat_fold` 1–8 train, 9 validation, 10 test.

Every downstream consumer must verify the corresponding config hash,
normalization hash, and manifest hash before using an artefact.
