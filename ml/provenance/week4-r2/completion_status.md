# r2 completion status before source commit

Full Week 1–3 regression rerun: **PASS, 18/18 commands exit 0**.
See `regressions-complete/summary.json` for exact commands, logs, exit statuses
and preserved hashes. The earlier `regressions/` interruption is historical.
`summary.json`, `final_checks.json`, `receiver_checks.json`, and the original
receipt describe the earlier uncommitted release snapshot; they are retained.

The source commit will be checked without overlays in a fresh local clone,
using the immutable authenticated r2 ZIP and production verifier/test. The
post-commit gate evidence is recorded separately under `committed-checkout/`.
Neither local checkout checks nor ZIP availability establishes SV1 receipt.
SV1 destination/channel and SHA/verifier/log acknowledgement are still missing.
No push, merge, flash, training, dataset downloads or scientific changes.

Source commit: `1ef28806fa5533fa56afafe746ecb5008ae96c34`.
Committed checkout verifier/test: **PASS**; see `committed-checkout/summary.json`.
SV1 receipt: **PENDING**.
