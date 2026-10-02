# PR #17 remediation — 2026-10-01, r2

## Findings → implementation/evidence

| Finding | Fix | Evidence |
|---|---|---|
| 1: CRLF source SHA | Schema 2, explicit UTF-8/LF source hashing; binaries/raw manifest unchanged | `receiver_checks.json`: production CRLF PASS, content corruption rejected |
| 2: missing handoff binaries | Complete all-split + Week 4 ZIP; inventory, sizes, independent anchors | `deliverables.json`; receiver acknowledgement still pending |
| 3: Git metadata reproduction | Scientific byte comparison + separately verified manifest invariants | `test_week4.txt`, `receiver_test_week4.txt`; changed branch/commit metadata passes |
| 4: duplicate checkpoint/DOCX | Packaged authenticated checkpoint; versioned historical DOCX reference list | Receiver clone has no dataset, duplicate checkpoint or DOCX; export/verify/tests pass |
| 5: compiler version | Authenticate author's evidence; validate invariants and compile local parameter bits | `verification.json`; compiler provenance difference fixture passes; bad count/status rejected |

Paths in this table are relative to `ml/provenance/week4-r2/`.

Core production sources: `week4_common.py`, `profile_week4.py`,
`verify_week4.py`, `test_week4.py`. New `release_week4.py` runs release gates,
keeps subprocess exit statuses/log SHA, checks source overlays in a fresh clone,
creates ZIP outside Git, tests extraction bytes and retains historical hashes.

Local compiler actually executed: GCC 15.2. Alternate compiler provenance was
simulated in a regression fixture while local compile still ran. No claim that
GCC 13.2 was independently executed on this machine.

SV2 production verifier/tests run with installed ONNX/ORT, not mocked numerical
results. Week 4 test has 21 expected rejections plus reproduction, metadata
portability, line-ending normalization/content rejection and monotonic cases.

## Revision policy

Old `ml/results/week4/`, old manifests/receipts and all Week 3 packages are
preserved, not silently rehashed. Old documentation is marked superseded.
Small r2 graph/profile/manifest/figures/evidence are versioned; generated
weights/header and ZIP are ignored. Do not stage unrelated pre-existing
untracked exports or ZIP files.

Frozen model, mapping, opset 13, sample IDs/order, preprocessing, FP32 bits and
strict MCU tolerance are unchanged. No training, downloads, firmware changes,
flash, merge or push. Local completion commits are explicitly authorized.

## Completion update

Full historical rerun: **18/18 PASS**, see
`../provenance/week4-r2/regressions-complete/summary.json`. The INCOMPLETE
statements below describe the preserved earlier attempt. Source/evidence commits
and actual committed-checkout checks are handled in the completion phase; see
`../provenance/week4-r2/completion_status.md` and post-commit evidence.

## Remaining acceptance (historical pre-completion snapshot)

Final local validation: `final_checks.json` records 69 receipt/ZIP files,
20 weights, 26 scientific files byte-identical to the original output,
syntax/JSON checks, `git diff --check` exit 0 and saved capture 100/100 PASS.
Historical package/firmware hashes are unchanged. The additional full Week 1–3
runner completed seven gates successfully but stopped before producing a
summary; it is **INCOMPLETE**, not a suite PASS. See
`regressions/interruption.json`. Separately, SV1/SV2 production verifier/tests
in `commands.json` all completed with exit 0.

1. Review and commit the fixes/new small r2 artifacts/evidence. Run production
   verifier/test from a checkout of that commit with the authenticated ZIP.
   Current receiver evidence is a fresh clone with source overlays, not a
   committed-fix checkout; this gate remains **PENDING**.
2. Transfer ZIP through the team's agreed channel and publish receipt/trust
   anchors independently. Obtain SV1 SHA/exit status/log acknowledgement.
   Local packaging does not establish official SV1 receipt: **PENDING**.
3. SV1 handles port/build Flash/RAM/DFU, actual MCU all-split verification and
   timing. SV2 hardware acceptance remains separate. Neither is fabricated by
   offline FP32 tests.

See `sv3_sv1_week4_handoff_r2.md` for receiver commands and full file mapping.