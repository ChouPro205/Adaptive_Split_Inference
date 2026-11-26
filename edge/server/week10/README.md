# Week 10 offline I1 service and model cache candidate

This adds runnable preparation, a persistent multi-split backend, a stateful I1
receiver, smoke/parity/benchmark commands and a checksum-verifying analyzer. The
transport here is **offline I1 frames**, not a BLE service. Hardware execution,
cache capacity and the <50 ms observation must be checked on KV260; HOST tests
do not establish them. Week 8/9 runtime evidence and I1/I2 contracts stay intact.

Python 3.9+ and NumPy on the board; the existing host observation venv is suitable
for preparation/tests/analysis. Quantization/ML dependencies and MQTT are not
needed. Models/plugins remain the authenticated VAI 2.5 baseline.

From repository root, HOST preparation (all output paths must be new):

```bash
python3 -B edge/server/week10/prepare.py --repo REPO --package AUTHENTICATED_50_PACKET_DIR \
  --bundle WEEK5_BUNDLE --output NEW_SESSION
python3 -B edge/server/week10/prepare.py --verify SESSION
```

Preparation verifies the packet manifest anchor, the full Week 5 bundle inventory
anchor and compile manifest, and every model. It copies source/codec/input bytes,
records actual Git/source state, creates deploy tar/SHA, and optionally creates
`--pointer FILE` only after success. `--verify` preserves existing files. Failed
preparations are retained and must not be reused as successful bundles.

On KV260 after source transfer/hash checks and the native build:

```bash
python3 -B source/edge/server/week10/bench.py --mode smoke --session SESSION \
  --worker BUILD/asi-cache-worker --deploy VERIFIED_WEEK5_DEPLOY --cpu-ops VERIFIED_PLUGINS \
  --output NEW_SMOKE
python3 -B source/edge/server/week10/bench.py --mode parity --session SESSION \
  --worker BUILD/asi-cache-worker --single-runner BUILD/asi-single-runner \
  --deploy VERIFIED_WEEK5_DEPLOY --cpu-ops VERIFIED_PLUGINS --output NEW_PARITY
python3 -B source/edge/server/week10/bench.py --mode benchmark --session SESSION \
  --worker BUILD/asi-cache-worker --deploy VERIFIED_WEEK5_DEPLOY --cpu-ops VERIFIED_PLUGINS \
  --baseline COMPLETE_PARITY --cycles 100 --warmup 20 --output NEW_BENCHMARK
```

Use explicit absolute paths for SESSION/BUILD/outputs. Smoke defaults to
s9,s2,s5,s2,s10; `--splits 0,1,2,3,4,5,6,7,8,9` checks ten live contexts.
Parity finishes all single-input processes **before** opening the cache worker.
It processes all 50 original public P1 vectors in source sequence order and
compares five logits bit-for-bit with the same inputs/models/plugins on the
single-input backend. Those vectors cover 46 native tails and four s10 identity
requests from only five validation ECGs, not independent test accuracy.

Benchmark requires complete successful parity with the same backend identity.
It creates fresh P0 request IDs from authenticated original q/scales, retaining
source hashes. It records first loads, >=20 warm-ups/model, ascending/descending
switch cycles, same-split controls and s10 diagnostics separately. No nonce/key
from an operational bench is read. The public vector key is offline-only.

The Receiver preserves I1 validation/duplicate ordering, conflict/TTL/bounds and
session RAM P1 high-water checks. The response cache is separate from native
model contexts. This is not durable replay protection across process restarts.
Backend `infer(split, values)` serializes calls and verifies model/plugin hashes
before worker startup. s10 checks identity explicitly. Timeouts fault the worker;
the run retains incomplete raw rows/logs and seals a failure summary.

After transfer, on HOST (no model execution):

```bash
python3 -B edge/server/week10/analyze.py --run SEALED_RESULT --output NEW_ANALYSIS
python3 -B -m unittest discover -s edge/tests -p 'test_week10*.py'
```

Analyzer verifies inventory/plan/raw/counter/PID mapping, reports first loads
and warm switches by observed directed pair, and preserves failures. It reports
whether **all observed** eligible warm switches were <50 ms. Project acceptance
remains pending review; it does not assume the PDF specified max/mean/p95 or that
sequential cycles cover all 90 directed pairs. RAM is native VmRSS in KiB sampled
outside SELECT/INFER timing. It is not the Week 11 10,000-switch leak test.

The separate BLE lab captured FIFO and multi-split sessions on KV260. See the
[report](../../../docs/sv2_edge_week10_report.md) for the Edge evidence and
Device/PPK2 review status. The lab setup and its inputs are distributed with
the team handoff.
