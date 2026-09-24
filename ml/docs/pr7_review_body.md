## Scope

SV3 Week 2 only: candidate 1D-CNN on the fixed Week 1 patient-wise MIT-BIH
data. This review patch strengthens provenance and clarifies I2. It preserves
the historical run and scientific methodology. No Week 3 architecture freeze
or export is included.

## Formal Week 2 acceptance

- 10 learned layers (Conv1d/Linear counting convention).
- 109,653 trainable parameters.
- FP32 mathematical footprint: 438,612 bytes (0.418293 MiB).
- Historical test accuracy: 98.221%; selected epoch: 3, using validation only.

## Verification commands and results

Run from the repository root with `$py = '.\ml\.venv\Scripts\python.exe'`.

| Command | Exit | Result |
|---|---:|---|
| `& $py -B ml/src/verify_mitdb_integrity.py` | 0 | PASS |
| `& $py -B ml/src/audit_mitdb_preprocessing.py` | 0 | PASS |
| `& $py -B ml/src/verify_mitdb_normalization.py` | 0 | PASS |
| `& $py -B ml/src/verify_mitdb_processed.py` | 0 | PASS; no patient overlap |
| `& $py -B ml/src/verify_ptbxl_normalization.py` | 0 | PASS |
| `& $py -B ml/src/verify_ptbxl.py` | 0 | PASS |
| `& $py -B ml/src/test_week2_baseline.py` | 0 | PASS; 3 tests |
| `& $py -B ml/src/test_week2_provenance.py --verify-historical-artifacts` | 0 | PASS; four intended gate rejections and historical artifact verification in a clean candidate snapshot |
| `& $py -B ml/src/verify_week2_baseline.py --historical` | 0 | PASS from committed review source |
| `git diff --check` | 0 | PASS |

For each of `week1_common.py` and `mitdb_common.py`, the automated test adds a
harmless uncommitted comment in an isolated Git snapshot. Child commands
`test_week2_provenance.py --gate train` and `--gate verify` each exit 1 with
`ERROR: Scientific source/config differs from HEAD: ml/src/<helper>.py`.
These are expected rejections, not failed test runs. Both helpers are restored
and their Git diffs are clean; real working-tree helpers are never modified.
No training job is launched by these tests.

## Artifact/provenance evidence

Historical implementation: `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`.
The unchanged `ml/provenance/week2_run_manifest.json` records
`scientific_sources_clean=true`, **`worktree_dirty=true`**, and four source
hashes. None of this is retroactively changed.

The strengthened current policy uses one shared six-file list, adding
`ml/src/week1_common.py` and `ml/src/mitdb_common.py`. Both current gates reject
dirty helpers. Explicit `--historical` mode retains four-hash historical truth,
checks historical Git blobs, verifies unchanged evaluation functions, and
separately enforces the current six-file clean gate. Default verification
requires six hashes for future evidence. Training refuses to overwrite an
existing Week 2 manifest. No new training was needed for this review.

Local state dict: 445,495 bytes, SHA-256
`f9d5763da844ab5ccdfc36a0899e0763501431c423f51ef1ce4e06e14769453f`.
Local checkpoint: 450,551 bytes, SHA-256
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
All dataset/artifact identifiers remain in the historical manifest. Binary
artifacts remain local under the repository's existing ignore policy.

## Scientific limitations

Validation accuracy is 84.488%. Test recall for S/F/Q is zero. The test split
contains 8102 N beats out of 8544, with only 13 S, 1 F and 2 Q beats. Overall
accuracy 98.221% meets the formal Week 2 threshold but does not demonstrate
robust five-class clinical generalization. There was no tuning against test.

## I2 status

I2 remains **PROVISIONAL / NOT COMPLETE**. Team-review target activation is
INT8, layout NCL = [N,C,L], N=1, with byte-length-preserving protection and
byte-exact round trip. Input validation must cover dtype/layout, N, shape,
element/byte count, model/split profiles and contract/version compatibility;
malformed or mismatched inputs are rejected.

These are new target interface constraints; the Week 2 baseline remains FP32.
FP32 remains the reference model/output for the later Week 3 handoff.
Exact P1 algorithm, PRNG, key format/provisioning, nonce format/reuse,
derivation/domain separation, permutation and affine generation, wire metadata,
protection-specific errors, normative vectors and Python/C equivalence remain
unresolved. Implementation is deferred to the scheduled Week 5/6 work.

## I1 status

Protected payload is NOT enabled in current I1 v1. `PROTECTED_PAYLOAD` remains
reserved/disabled; sender flags remain 0 and `nonce_length` remains 0. No I2
metadata is inserted into v1. A protection-capable packet revision or approved
protocol-version change must be coordinated separately with the I1 owners.

## Scope boundary

No P1 implementation, ONNX/C-header export, split profiling, Week 3 work,
Device/Edge packet changes, retraining, test-set tuning, or merge is included.
Final project approval remains with the reviewers/GV.
