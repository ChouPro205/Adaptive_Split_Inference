# SV3 Week 1 — MIT-BIH Data Protocol

## Scope

This document records the finalized MIT-BIH preprocessing protocol used by SV3 in Week 1.

The official Week 1 requirement is to prepare ECG data, perform beat segmentation and normalization, and split train/validation/test by patient without patient leakage.

Implementation-specific decisions below are project decisions unless explicitly stated otherwise.

---

## 1. Dataset

- Dataset: MIT-BIH Arrhythmia Database
- Sampling frequency: 360 Hz
- Total raw records: 48

### Lead selection

Preferred input lead:

- `MLII`

Selection rule:

- Select MLII by lead name.
- Do not assume MLII is always channel 0.

Special cases:

- Record `114`: `['V5', 'MLII']`, therefore MLII index = 1.
- Record `102`: no MLII → excluded from current MLII-only processed dataset.
- Record `104`: no MLII → excluded from current MLII-only processed dataset.

Final eligible records:

- 46 records

---

## 2. Beat segmentation

Beat center:

- Expert MIT-BIH annotation

Window:

- 360 samples
- 180 samples before annotation
- 180 samples after annotation

Boundary policy:

- Drop beat if the complete 360-sample window is unavailable.
- No padding.

Filtering:

- No additional digital filter.

---

## 3. AAMI class mapping

### N — Normal

Raw annotation symbols:

- `N`
- `L`
- `R`
- `e`
- `j`

Class index:

- `0`

### S — Supraventricular ectopic

Raw annotation symbols:

- `A`
- `a`
- `J`
- `S`

Class index:

- `1`

### V — Ventricular ectopic

Raw annotation symbols:

- `V`
- `E`

Class index:

- `2`

### F — Fusion

Raw annotation symbols:

- `F`

Class index:

- `3`

### Q — Unknown / paced / unclassifiable group

Raw annotation symbols:

- `/`
- `f`
- `Q`

Class index:

- `4`

Annotation symbols outside this mapping are not converted into ML heartbeat samples.

---

## 4. Patient-wise split

Split unit:

- Patient

Target ratio:

- Train: 75%
- Validation: 15%
- Test: 10%

Seed:

- `30`

Eligible patient count:

- 45

Final split:

- Train: 34 patients / 35 records
- Validation: 7 patients / 7 records
- Test: 4 patients / 4 records

Special patient identity:

- Records `201` and `202` belong to the same patient and are assigned together.

Patient leakage is forbidden between all three splits.

The exact split is frozen in:

- `manifests/mitdb_patient_split.csv`

---

## 5. Normalization

Method:

- Global Z-score

Statistics are fitted using:

- TRAIN beats only

Formula:

`x_norm = (x - mean_train) / std_train`

Frozen statistics:

- mean = `-0.2912026352134608`
- std = `0.45653058276514263`

Validation and test use the same TRAIN statistics and do not fit their own statistics.

Statistics are stored in:

- `configs/mitdb_normalization.json`

---

## 6. Processed representation

Each ECG sample:

- Shape: `(360,)`
- X dtype: `float32`
- y dtype: `int64`

Class indices:

- N = 0
- S = 1
- V = 2
- F = 3
- Q = 4

Processed dataset location:

- `data/processed/mitdb/`

The processed dataset is not committed to Git.