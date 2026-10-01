# r2 completion status — committed checkout accepted

Full Week 1–3 regression rerun: **PASS, 18/18 commands exit 0**.
See `regressions-complete/summary.json` for exact commands, logs, exit statuses
and preserved hashes. The earlier `regressions/` interruption is historical.
`summary.json`, `final_checks.json`, `receiver_checks.json`, and the original
receipt describe the earlier uncommitted release snapshot; they are retained.

The source commit was checked without overlays in a fresh local clone,
using the immutable authenticated r2 ZIP and production verifier/test: PASS.
Post-commit gate evidence is recorded under `committed-checkout/`.
Evidence HEAD `416820f84dca5f26497233ef69b3b159153c47eb` also passed
production verifier/test in a separate clean checkout.
Neither local checkout checks nor ZIP availability establishes SV1 receipt.
SV1 destination/channel and SHA/verifier/log acknowledgement are still missing.
No push, merge, flash, training, dataset downloads or scientific changes.

Source commit: `1ef28806fa5533fa56afafe746ecb5008ae96c34`.
Committed checkout verifier/test: **PASS**; see `committed-checkout/summary.json`.
SV1 receipt: **PENDING**.
