# Week 7 NoPeek experiment evidence

Accepted source: `6be51e3a5d6be8309ef87720e98ed4305352f467`.
Canonical results: `smoke-final/` and independent optimized-Python repeat
`smoke-final-repeat-O/`. Six experiments per run, each four training steps on
128 authenticated MIT-BIH train samples, then 512 fixed validation samples.
No test evaluation or model selection. `batch_metrics.json` separates CE,
distance correlation R_n, total objective and classification accuracy.
`summary.json` includes per-class metrics, source/data identity, seed,
experimental weight size/hash and final tensor state digest.

Weights live outside Git in `ml/artifacts/week7/<run>/`; they are experiments
and have no deployment profile. Do not overwrite the baseline checkpoint or
assign these weights to the approved registry.

`smoke-r1/` is a failed development run: only selected samples and one local
weight were written before a relative-path metadata error. There is no PASS
summary for it. `smoke-r2/` and `smoke-r3-repeat/` are preliminary successes,
kept for history; final acceptance uses only the final two runs and final tests.
Command logs, failures and the final audit are in
`ml/provenance/week7-nopeek-20261021/`. Full Vietnamese explanation and pending
dependencies: `docs/sv3_ml_week7_report.md` and
`docs/sv3_week7_dependency_checklist.md`.
