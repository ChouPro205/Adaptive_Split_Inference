# SV3 Week 2 candidate baseline

This is one candidate 1D-CNN for the frozen Week 1 MIT-BIH processed data. It
does not freeze the architecture for Week 3. No preprocessing, patient split,
normalization, or test distribution was changed.

## Verify the preserved historical run

From the repository root in the Week 1 Python 3.11 environment, run these
steps in order. The Week 1 commands are read-only; the Week 1 orchestrator is
not used here because it rebuilds processed artifacts.

```powershell
$py = '.\ml\.venv\Scripts\python.exe'
& $py -B ml/src/verify_mitdb_integrity.py
& $py -B ml/src/audit_mitdb_preprocessing.py
& $py -B ml/src/verify_mitdb_normalization.py
& $py -B ml/src/verify_mitdb_processed.py
& $py -B ml/src/verify_ptbxl_normalization.py
& $py -B ml/src/verify_ptbxl.py
& $py -B ml/src/test_week2_baseline.py
& $py -B ml/src/test_week2_provenance.py --verify-historical-artifacts
& $py -B ml/src/verify_week2_baseline.py --historical
```

The pre-training test requires only Week 1 data and the committed Week 2
source/config. The post-run verifier requires generated artifacts. Training
requires the six scientific source/config files in the current policy to
be tracked and unchanged relative to HEAD. Unrelated untracked files do not
block a run.

PR #7 adds `ml/src/week1_common.py` and `ml/src/mitdb_common.py` to the four
original paths. `SCIENTIFIC_SOURCE_FILES` in the training module is the single
definition reused by both gates. Both reject dirty helpers before training,
artifact loading or evaluation. The negative test commits a copy of current
source in an isolated temporary Git repository, checks both clean gates, adds
a harmless comment to each helper in turn, and requires exit 1 with the exact
provenance error from both gates. It restores bytes in `finally`, checks Git
diffs, and confirms the real helpers never changed. Its optional artifact check
verifies a copy of the historical evidence from that clean candidate snapshot.

The existing run from `8e98a0e4851abc979feb5fd5b97ece612b02cfaa` still has
only four recorded source hashes, `scientific_sources_clean=true`, and
**`worktree_dirty=true`**. These historical values are intentionally preserved,
not retrospectively upgraded to six-file coverage. `--historical` is limited
to that commit: it verifies the four original hashes against Git, checks the
unchanged model/data/config and both helpers against the historical commit,
and checks evaluation-function ASTs for unchanged computation. It separately
enforces today's six-file clean-worktree gate. The changed training-file hash
is not passed off as a historical match. Default verification requires all six
recorded hashes for a future run.

No new training run is needed for this review. The training entry point now
refuses to overwrite an existing Week 2 manifest. Any future approved run must
use a separate checkout/evidence location; the historical manifest and local
artifacts must be retained. The training/verification command table below is
evidence from the historical implementation, not an instruction to overwrite it.

The run reads `ml/configs/mitdb_week2_baseline.json`, the authoritative
`ml/configs/mitdb_week1_config.json`, its patient manifest and normalization
file, and the hash-bound processed files under `ml/data/processed/mitdb/`.
`X` remains `(N, 360)` float32 until it is viewed as `(N, 1, 360)` by the
model; `y` is int64 with `N/S/V/F/Q = 0/1/2/3/4`. The split arrays are loaded
by their existing names and checked against the Week 1 manifest and metadata.
The loader neither fits statistics nor assigns a new split.

## Candidate network and selection

A counted layer is a learned `Conv1d` or `Linear` module. ReLU, max pooling,
flattening, and dropout are operations outside this count. There are eight
5-tap convolutions with channels `1→16→16→32→32→48→48→64→64`, four 2:1 max
pools after each pair of convolutions, then `1408→32→5` linear layers. The
network uses standard convolutions, ReLU and max pooling and has no large
dense hidden layer. The FP32 mathematical weight footprint is parameter count
times four; serialized files also include PyTorch format overhead.

Training uses seed 30, deterministic PyTorch settings, CUDA when available
with CPU fallback, AdamW at 0.001 with weight decay 0.0001, batch size 256,
CrossEntropyLoss, and ReduceLROnPlateau (factor 0.5, patience 4). No class
weighting, augmentation, or replacement sampler is used. Training stops after
10 epochs without a strict improvement in validation accuracy, or after 40
epochs. The best checkpoint is chosen by validation accuracy. Test data is
evaluated once, after selection, and never influences the saved checkpoint.

## Run artifacts

The ignored local directory `ml/data/week2/mitdb_baseline/` contains:

- `training_config.json`: exact hyperparameter snapshot;
- `architecture.json`: ordered learned layers, parameter count and FP32 bytes;
- `history.json`: loss, accuracy, learning rate, and validation class metrics
  for every epoch;
- `best_state_dict.pt`: model tensors alone;
- `best_checkpoint.pt`: model tensors, selected epoch, validation metrics,
  config and source/dataset provenance;
- `metrics.json`: selected train/validation and final test metrics, confusion
  matrices, per-class precision/recall/F1, footprint, file sizes and SHA-256.

The versioned `ml/provenance/week2_run_manifest.json` is generated by training
and records output paths, file hashes/sizes, source commit and file hashes,
Week 1 artifact identifiers, and headline metrics. The repository's existing
`.gitignore` excludes `data/` and `*.pt`; the selected state dict and full
checkpoint remain local. The small run manifest and this documentation are
versioned evidence. Reproduce and verify from the committed implementation
and the preserved Week 1 data to obtain local weights.
The post-run verifier recomputes exact predictions on the device type recorded
by training. A CUDA run requires CUDA for exact confusion-matrix verification;
CPU floating-point kernels can change a borderline predicted class even when
the same FP32 state dict loads successfully.

The accepted candidate has 10 learned layers, 109,653 trainable parameters,
and a mathematical FP32 footprint of 438,612 bytes (0.418293 MiB). Overall
accuracy does not establish clinically useful five-class generalization;
very small test F/Q supports make those estimates uncertain. Do not tune this
candidate against the observed test result.

## Verified run from the implementation commit

Scientific source commit:
`8e98a0e4851abc979feb5fd5b97ece612b02cfaa`. The four scientific
source/config files were tracked and unchanged relative to that commit at run
time. The broader worktree was dirty because unrelated and evidence files were
untracked; the run records this separately. CPython 3.11.9, PyTorch
2.14.0+cu130, CUDA 13.0, and NVIDIA GeForce RTX 5060 were used.

| Scientific file | SHA-256 used by the run |
|---|---|
| `ml/configs/mitdb_week2_baseline.json` | `273a563af79126c6ed6762c4bd01a186de055b6dea390688eefcf7522ae2e5e3` |
| `ml/src/mitdb_baseline_model.py` | `520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14` |
| `ml/src/mitdb_week2_data.py` | `363f5298e4e723cac19e15e062346f24c808820fe180c292d25372574a2ba907` |
| `ml/src/train_mitdb_baseline.py` | `a0fa0becf2539be37db9105eccb60d8ded8c25fae04d36fdda04ce6f82446152` |

The Week 1 processed manifest SHA-256 is
`f712c83d46d71ac6af75b7138668d8918eef87a4ddfeab8e8b5310ced2c44a3c`.
All individual train/validation/test hashes are in the versioned Week 2 run
manifest. No Week 1 processed artifact changed.

Training ran 13 epochs and selected epoch 3 using validation accuracy alone.
Selected-epoch train accuracy was 97.706%; validation accuracy was 84.488%,
macro F1 0.304669 and weighted F1 0.808288; test accuracy was **98.221%**
(8392/8544), macro F1 0.382595 and weighted F1 0.985740. The serialized
state dict is 445,495 bytes, SHA-256
`f9d5763da844ab5ccdfc36a0899e0763501431c423f51ef1ce4e06e14769453f`.
The full checkpoint is 450,551 bytes, SHA-256
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Serialization metadata accounts for the size above the mathematical FP32
footprint.

Test confusion matrix, true classes by row and predictions by column, both
ordered N, S, V, F, Q:

```text
N  8020  67   8  0  7
S    13   0   0  0  0
V    48   3 372  1  2
F     0   0   1  0  0
Q     2   0   0  0  0
```

Test recall is **zero for S, F, and Q**. Validation likewise has only 4/1493
S, 0/11 F, and 0/5 Q correct. The test split has 8102/8544 N-class beats,
so the overall 98.221% accuracy must not be read as robust five-class or
clinical performance.

### Verification evidence

With `$py = '.\ml\.venv\Scripts\python.exe'`, each command below exited 0:

| Command | Exit | Result |
|---|---:|---|
| `$py -B ml/src/check_env.py` | 0 | PASS |
| `$py -B ml/src/verify_mitdb_integrity.py` | 0 | PASS |
| `$py -B ml/src/inspect_mitdb.py` | 0 | PASS |
| `$py -B ml/src/test_segmentation.py` | 0 | PASS |
| `$py -B ml/src/audit_mitdb_preprocessing.py` | 0 | PASS |
| `$py -B ml/src/verify_mitdb_normalization.py` | 0 | PASS |
| `$py -B ml/src/verify_mitdb_processed.py` | 0 | PASS |
| `$py -B ml/src/test_week1_negative.py` | 0 | PASS, 34/34 cases |
| `$py -O ml/src/verify_mitdb_integrity.py` | 0 | PASS |
| `$py -O ml/src/verify_mitdb_processed.py` | 0 | PASS |
| `$py -B ml/src/verify_ptbxl_normalization.py` | 0 | PASS |
| `$py -B ml/src/verify_ptbxl.py` | 0 | PASS |
| `$py -B ml/src/test_week2_baseline.py` | 0 | PASS, 3 tests |
| `$py -B ml/src/train_mitdb_baseline.py --config mitdb_week2_baseline.json` | 0 | PASS, epoch 3 selected |
| `$py -B ml/src/verify_week2_baseline.py` | 0 | PASS, hashes, source, weights, metrics and confusion matrix |
| `git diff --check` | 0 | PASS |

An initial post-run verifier attempt failed because CPU inference changed one
borderline N prediction relative to the recorded GPU run. The verifier was
corrected to use the recorded device, included in the implementation commit,
and the full read-only Week 1 → pre-test → training → post-verification sequence
was rerun successfully from that commit. No model or training setting changed.

## I2/I3 interface status

`contracts/I2_SV3_provisional_interface.md` is an approval draft with open
cryptographic choices marked `BLOCKED_ON_GV_APPROVAL`.
`contracts/I3_SV3_input.md` records SV3's consulted input and open schema
decisions. Neither document implements P1 or fixes the final shared LUT.

The I2 team-review target is INT8 activation bytes in NCL layout with N=1,
length-preserving protection, byte-exact reversal, and model/split/profile,
shape and size validation. The Week 2 model remains FP32. Algorithm, PRNG,
key/nonce, derivation, wire metadata, protection errors and normative Python/C
vectors remain provisional. Current I1 v1 still has `flags=0`, protected
payload disabled and `nonce_length=0`; activation protection needs a separately
approved I1 revision coordinated with its owners.
