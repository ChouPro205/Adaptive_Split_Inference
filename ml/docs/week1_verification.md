# SV3 Week 1 — MIT-BIH Verification Summary

## 1. Raw dataset audit

Total records:

- 48

Sampling frequency:

- 360 Hz for all 48 records

Signal length:

- 650000 samples for all 48 records

Records containing MLII:

- 46

Records without MLII:

- 102
- 104

Special MLII channel:

- Record 114: MLII is channel index 1

---

## 2. Preprocessing audit

Raw annotations in processed MLII records:

- 108144

Ignored annotations:

- 3066

Boundary-dropped valid AAMI beats:

- 52

Final valid beats:

- 105026

Consistency:

`108144 - 3066 - 52 = 105026`

Status:

- PASS

---

## 3. Global AAMI class counts

- N: 90320
- S: 2781
- V: 7229
- F: 802
- Q: 3894

Total:

- 105026

---

## 4. Patient-wise split verification

Eligible patients:

- 45

Train:

- 34 patients
- 35 records
- 81094 beats

Validation:

- 7 patients
- 7 records
- 15388 beats

Test:

- 4 patients
- 4 records
- 8544 beats

Leakage checks:

- train ∩ validation = empty
- train ∩ test = empty
- validation ∩ test = empty

Status:

- PASS

---

## 5. Normalization verification

Train-only normalization parameters:

- mean = -0.2912026352134608
- std = 0.45653058276514263

After normalization:

### Train

- mean ≈ -9.62e-11
- std ≈ 0.9999999996

### Validation

- mean ≈ -0.2587103347
- std ≈ 1.1056936625

### Test

- mean ≈ -0.4544693434
- std ≈ 1.0416752841

Validation and test are not expected to have mean 0 and std 1 because both use TRAIN statistics.

Status:

- PASS

---

## 6. Final processed artefact verification

Train:

- X shape: `(81094, 360)`
- y shape: `(81094,)`

Validation:

- X shape: `(15388, 360)`
- y shape: `(15388,)`

Test:

- X shape: `(8544, 360)`
- y shape: `(8544,)`

Data types:

- X: `float32`
- y: `int64`

Checks:

- all values finite
- labels match metadata
- all accepted samples contain exactly 360 ECG values
- no patient leakage
- TRAIN normalization mean ≈ 0
- TRAIN normalization std ≈ 1

Final verification status:

- PASS