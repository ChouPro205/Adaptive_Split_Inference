# SV3 Machine Learning — Week 1

Week 1 is limited to reproducible ECG data acquisition, integrity checking,
patient-wise splitting, preprocessing, normalization, and verification. It does
not train the Week 2 1D-CNN, run privacy attacks, or export deployment models.

## Reproducible environment

Supported Python: `>=3.11,<3.12`. The verified machine used Python 3.11.9 on
Windows NT build 26200, PyTorch 2.14.0+cu130, CUDA runtime 13.0, and an NVIDIA
GeForce RTX 5060. CPU execution is also supported.

Windows PowerShell, CPU:

```powershell
py -3.11 -m venv ml\.venv
.\ml\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ml\requirements-cpu.txt
python -B ml\src\check_env.py --mode cpu
```

Windows PowerShell, tested CUDA 13.0 build:

```powershell
py -3.11 -m venv ml\.venv
.\ml\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ml\requirements-gpu-cu130.txt
python -B ml\src\check_env.py --mode gpu
```

Linux equivalent:

```bash
python3.11 -m venv ml/.venv
source ml/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r ml/requirements-cpu.txt  # or requirements-gpu-cu130.txt
python -B ml/src/check_env.py --mode auto
```

For CUDA, the installed NVIDIA driver must support the CUDA 13.0 runtime
embedded in the selected PyTorch wheel. `ml/requirements.txt` is retained as
the full Windows/GPU environment snapshot from the verified machine;
`requirements-core.txt` plus the CPU/GPU selector files are the clearer setup
paths for a new environment.

## Dataset acquisition and verification

MIT-BIH is pinned to PhysioNet v1.0.0. PTB-XL is pinned to PhysioNet v1.0.3,
and Week 1 intentionally downloads/uses the official 100 Hz waveforms only.
Both downloaders are resumable at the file level: existing non-empty files are
retained unless `--overwrite` is given. Retained files are never trusted merely
because they are non-empty: PTB-XL metadata is checksummed before parsing and
every selected waveform is checksummed during acquisition; the strict verifier
then independently checks the complete required file set.

The PTB-XL manifest verifier requires exactly one row for every canonical
`ecg_id`; duplicate, missing, unexpected, or metadata-mismatched rows fail.
Config and repository-text hashes normalize line endings to LF, while raw ECG
and binary artefacts retain raw-byte SHA-256. This keeps config/provenance
bindings stable across Windows and Linux checkouts.

```powershell
python -B ml/src/download_mitdb.py
python -B ml/src/verify_mitdb_integrity.py

python -B ml/src/download_ptbxl.py
python -B ml/src/build_ptbxl_manifest.py
python -B ml/src/compute_ptbxl_normalization.py
python -B ml/src/verify_ptbxl_normalization.py
python -B ml/src/verify_ptbxl.py
```

## MIT-BIH preprocessing and verification

```powershell
python -B ml/src/inspect_mitdb.py
python -B ml/src/test_segmentation.py
python -B ml/src/audit_mitdb_preprocessing.py
python -B ml/src/build_mitdb_manifest.py
python -B ml/src/compute_mitdb_normalization.py
python -B ml/src/verify_mitdb_normalization.py
python -B ml/src/build_mitdb_processed.py
python -B ml/src/verify_mitdb_processed.py
python -O ml/src/verify_mitdb_processed.py
```

Run all positive and negative checks and generate provenance:

```powershell
python -B ml/src/run_week1_verification.py
```

The negative suite uses temporary directories/hard links and never modifies
the real raw datasets. It covers empty, missing-record/file, cached-metadata
corruption, malformed PTB-XL manifests, and waveform checksum failures under
normal Python and `python -O`. Manifest cases also require the specific
validator failure reason, so an unrelated later hash failure cannot satisfy the
test:

```powershell
python -B ml/src/test_week1_negative.py
```

Raw ECG, processed arrays, environments, checkpoints, and model artefacts are
ignored by Git. Configs, split manifests, normalization statistics, small hash
metadata, documentation, and `ml/provenance/week1_run_manifest.json` are
versioned.

See `docs/week1_data_protocol.md`, `docs/week1_data_contract.md`, and
`docs/week1_verification.md` for the frozen Week 1 decisions and evidence.

## Week 2 MIT-BIH candidate baseline

The Week 2 1D-CNN training command, fixed-split data contract, artifacts, and
observed per-class limitations are documented in `docs/week2_baseline.md`.
This is a candidate baseline; architecture freezing remains outside Week 2.

## Week 3 FP32 handoff to SV1

The separately approved Week 3 reference uses that unchanged checkpoint with
`M_final=P2` after `features.4 MaxPool1d`. See [release evidence](docs/week3_release.md)
for the official immutable ID, manifest/archive hashes, commands and acceptance
status. Release verification passed; SV1 package review and MCU validation are
pending. ONNX remains blocked on the SV2 interface.

Complete generated packages under `ml/artifacts/week3/` stay outside Git under
the existing model-artifact policy. Transfer the whole folder (or its documented
ZIP) as permitted by the handoff contract, and verify all files at the receiving
side. Versioned source/config/docs and small manifest/evidence copies live in
`ml/scripts/`, `ml/configs/`, `ml/docs/` and `ml/provenance/week3/`. A Git checkout
alone does not deliver the checkpoint, inputs, parameters or golden tensors.
