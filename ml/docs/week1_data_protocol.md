# SV3 Week 1 ECG data protocol

## Requirement classification

- [EXPLICIT] The project member guide assigns Week 1 to the PyTorch
  environment, MIT-BIH and PTB-XL acquisition, preprocessing, beat
  segmentation, normalization, and patient-wise train/validation/test splits.
- [EXPLICIT] The acceptance review requires pinned versions, sources, licenses,
  checksums, strict completeness, non-zero failure exits, no critical `assert`,
  PTB-XL 12-lead/SCP handling, and run provenance.
- [DERIVED] Separate configs are authoritative for each dataset because their
  representations are materially different.
- [ASSUMPTION] No written scope reduction excluding PTB-XL was found.

Official project sources used for this classification are under
`ml/docs/project_sources/requirements/` and
`ml/docs/project_sources/review/`. Reference papers are not treated as project
requirements.

## MIT-BIH v1.0.0 — preserved protocol

Source: `https://physionet.org/files/mitdb/1.0.0/`

DOI: `10.13026/C2F305`

License: Open Data Commons Attribution License v1.0

The official 48-record list is frozen in
`manifests/mitdb_expected_records.txt`. Every `.hea`, `.dat`, and `.atr` file is
checked against the pinned official PhysioNet `SHA256SUMS.txt` before use.

The existing verified methodology is unchanged:

- sampling rate 360 Hz;
- select `MLII` by lead name, never by assumed channel index;
- record 114 uses channel 1; records 102 and 104 are excluded because MLII is
  absent;
- beat centre is the expert annotation;
- 360-sample window: 180 before and 180 after;
- incomplete boundary windows are dropped; no padding and no added filter;
- AAMI mapping: `N,L,R,e,j -> N`; `A,a,J,S -> S`; `V,E -> V`; `F -> F`;
  `/,f,Q -> Q`;
- class indices `N=0, S=1, V=2, F=3, Q=4`;
- patient-wise 75/15/10 split, seed 30; records 201 and 202 share one patient;
- global scalar Z-score fitted only on train beats.

Frozen train statistics remain:

- mean `-0.2912026352134608`;
- standard deviation `0.45653058276514263`.

## PTB-XL v1.0.3 — Week 1 protocol

Source: `https://physionet.org/files/ptb-xl/1.0.3/`

DOI: `10.13026/kfzx-aw45`

License: Creative Commons Attribution 4.0 International

### Sampling and representation

- [EXPLICIT] The review requires an explicit choice of 100 Hz or 500 Hz and all
  12 leads.
- [DERIVED] Week 1 uses the official 100 Hz waveforms (`filename_lr`). They
  retain the complete 10-second morphology and all 12 leads while reducing raw
  storage/I/O by 5× relative to 500 Hz. This is a data-preparation decision, not
  a model/deployment decision.
- Each record has shape `(1000, 12)` in WFDB time-major layout.
- Lead order is verified exactly as
  `I, II, III, AVR, AVL, AVF, V1, V2, V3, V4, V5, V6`.
- No beat segmentation and no single-lead reduction are applied.

### Labels and split

- `scp_codes` is parsed as a non-empty multi-label dictionary of SCP code to
  likelihood. Every code must exist in `scp_statements.csv`.
- The committed manifest stores labels as canonical sorted JSON, preserving
  likelihood values instead of collapsing them to one class.
- [EXPLICIT] Patient leakage is forbidden and official recommended folds are
  permitted when documented.
- [DERIVED] Use official `strat_fold` 1–8 for train, 9 for validation, and 10
  for test. PTB-XL v1.0.3 assigns all records from each patient to one fold;
  the verifier independently enforces that property.

### Normalization

- [EXPLICIT] Week 1 includes normalization.
- [DERIVED] Fit a global Z-score independently for each of the 12 leads using
  train records only. This preserves the multi-lead structure and avoids
  validation/test leakage.
- The raw WFDB files remain the source of truth; only the small statistics JSON
  is committed. Downstream loading applies `(x - mean[lead]) / std[lead]` and
  casts to `float32`.

## Integrity and config binding

`configs/mitdb_week1_config.json` and `configs/ptbxl_week1_config.json` are the
sources of truth. Verifiers bind generated artefacts to SHA-256 hashes of the
active config, split manifest, normalization file, official checksum manifest,
and processed outputs. Empty directories, missing records/files, changed
checksums, leakage, invalid labels, shape/lead mismatches, and stale config
bindings all terminate with a non-zero exit code under both normal Python and
`python -O`.

PTB-XL acquisition validates the pinned official checksum manifest first, then
checksums `ptbxl_database.csv`, `scp_statements.csv`, and `LICENSE.txt` before
metadata is parsed. Metadata-derived paths reject absolute, empty, dot, parent,
drive-qualified, and unsupported components; resolved destinations must remain
inside the configured raw directory. Cached waveforms are re-hashed rather
than trusted based on existence or size.
