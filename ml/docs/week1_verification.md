# SV3 Week 1 verification evidence

Final orchestrated run: `2026-09-17T17:02:29Z` to
`2026-09-17T17:07:44Z` (local date 2026-09-18). Machine-readable evidence is
in `ml/provenance/week1_run_manifest.json`; overall exit status was `0` and all
19 recorded commands returned `0`.

## Environment

- CPython 3.11.9 on Windows NT 10.0 build 26200;
- PyTorch 2.14.0+cu130, CUDA runtime 13.0;
- NVIDIA GeForce RTX 5060, CUDA available;
- NumPy 2.4.6, pandas 3.0.5, SciPy 1.17.1, Matplotlib 3.11.2,
  WFDB 4.3.1, scikit-learn 1.9.1;
- version constraints and CPU/CUDA tensor sanity checks: PASS.

Environment config SHA-256:
`a5e201eec25bea5eac9ebfc71792917bc6552fcf774b0faee514388d4e026a01`.

## MIT-BIH v1.0.0

Integrity:

- official records: 48/48;
- required `.hea/.dat/.atr` files: 144/144;
- official checksum-manifest SHA-256:
  `b61158a96d5f2ca80edfb354a9a66a6324836c390a84e1966dcee2b907d6be43`;
- required-file tree SHA-256:
  `09d0f9c2cf19cbcfc8b704681ce388e62ec89832bfed59169e70ac9ea147e46f`;
- all official file checksums matched.

The preserved preprocessing audit remains unchanged:

- 48 records found, 46 MLII records processed;
- 102/104 missing MLII; record 114 uses MLII channel 1;
- raw annotations 108,144; ignored 3,066; boundary-dropped 52;
- valid beats 105,026;
- AAMI counts: N 90,320; S 2,781; V 7,229; F 802; Q 3,894;
- accounting `108144 - 3066 - 52 = 105026`: PASS.

Patient split and processed artefacts:

| Split | Patients | Records | Beats / X shape |
|---|---:|---:|---:|
| train | 34 | 35 | `(81094, 360)` |
| validation | 7 | 7 | `(15388, 360)` |
| test | 4 | 4 | `(8544, 360)` |

- X `float32`; y `int64`;
- train/validation/test patient intersections are empty;
- train-only mean/std remain
  `-0.2912026352134608` / `0.45653058276514263`;
- normalized train mean/std are approximately
  `-9.6210e-11` / `0.999999999635`;
- every processed metadata row and normalized waveform was cross-checked
  against raw annotations/signals;
- every processed artefact hash matched `processed_manifest.json`;
- normal Python and `python -O` produced the same PASS results.

MIT-BIH config SHA-256:
`f5d050686b9d4816052631380b81f0c4671faf1dc648f1d9c02b4c3dc3be0b54`.

## PTB-XL v1.0.3

- selected source: official 100 Hz records;
- records/patients: 21,799 / 18,869;
- waveform shape: `(1000, 12)`;
- lead order: `I, II, III, AVR, AVL, AVF, V1, V2, V3, V4, V5, V6`;
- 61,007 SCP label assignments parsed; every code was in
  `scp_statements.csv`;
- split: train 17,418 records / 15,023 patients; validation 2,183 / 1,942;
  test 2,198 / 1,904;
- all patient intersections are empty;
- required files checksummed: 43,601;
- official checksum-manifest SHA-256:
  `b7224b92b341511ec3ceb13dc6652079b2c36a06504bcb49506f157f51dc695d`;
- required-file tree SHA-256:
  `b4863f3c13d7ccdd31244944d8cd1e1ed3e98ff2877d7ca5b154cbf471170242`.

Per-lead normalization was fitted and independently recomputed across 17,418
train records / 17,418,000 time values per lead. Mean and standard deviation in
the verified lead order are stored in `configs/ptbxl_normalization.json`; both
runs matched at absolute tolerance `1e-12`.

PTB-XL config SHA-256:
`92100295ea3c33984a8930f59a65ff56b428130a975788d91eb87c7860e6333c`.

## Negative tests

All 14 expected-failure cases returned exit code `1`, printed an explicit
error, and did not print `STATUS: PASS`:

- empty MIT-BIH directory under Python and `python -O`;
- empty PTB-XL directory under Python and `python -O`;
- MIT-BIH missing record, missing `.hea`, missing `.dat`, missing `.atr`, and
  wrong SHA-256 under Python and `python -O`.

Temporary hard links/copies were used; real raw data was not modified.

## Scope confirmation

No 1D-CNN was trained. No privacy attack, ONNX export, model deployment,
quantization, or Week 2 implementation was added. No `device/`, `edge/`, or
`contracts/` file was changed.
