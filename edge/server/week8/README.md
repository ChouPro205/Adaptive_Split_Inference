# Week 8 BLE service and evidence tools

These tools prepare and execute **s2** on the existing KV260 PetaLinux 2022.1 /
Vitis AI 2.5 deployment. They do not change Week 5–7 models, measured binaries,
receipts, contracts, Device firmware or registry. Saved ARM/DPU and BLE runs are documented in
[the Week 8 report](../../../docs/sv2_edge_week8_report.md); HOST tests remain separate.

- `prepare.py`: validate/copy the user-supplied 100-sample NPZ (no pickle), create
  a separate evidence session and source archive with SHA256 inventory.
- `offline.py`: one persistent native process, 100 exact q/scale inputs, all
  predictions/errors saved. It never recalibrates on the test samples.
- `ble_service.py`: Linux aarch64 BlueZ central, BLE echo or actual tail. Pin
  Bleak 0.22.3 for its BlueZ MTU acquisition API. MTU mismatch stops G2 rather
  than pretending a requested MTU was negotiated. Native inference runs outside
  the asyncio event loop. One queued complete frame is allowed; excess is dropped
  and logged as rx_busy. Cache survives reconnect within a service lifetime.
- `service.py`: I1 reference parser/unprotect/dequantize/response, 16-entry / 60 s
  retry cache, session-scoped P1 high-water checks. Same request+bytes returns
  cached bytes; a conflicting duplicate is rejected. This is not authentication
  or durable replay protection. Restarting service ends the RAM cache; do not
  restart mid-request and claim exactly-once semantics across process restarts.
- `summarize.py`: checksum and exact sample/P0/P1 coverage, compare radio logits
  to saved offline results. It cannot prove reception by the Device. G2 remains
  pending its CDC/checker log, actual link settings and human review.
- `ble_service.py --sv1-session`: the 26 October SV1 handoff requires one
  connection for `ONE 0 P0`, `ONE 0 P1`, `PAIRS 0 5`, `PAIRS 0 100` (212 total
  requests). Keeps one worker/cache and writes `one_p0.jsonl`, `one_p1.jsonl`,
  `pairs_5.jsonl`, `pairs_100.jsonl` alongside the original `peer.jsonl`.
  Stage assignment uses agreed request counts; stop on errors/retries and
  reconcile Device logs. Count alone cannot prove sample/command mapping.
- `export_g2.py`: verifies the sealed 212-request session and exports the final
  200 canonical rows for `summarize.py`. Rejects incomplete/error/retry sessions
  or changed connections. It does not declare Device reception or G2 acceptance.
- `review_after_g2.py`: reads sealed radio and two offline runs; verifies backend
  identities and offline FP32 repeatability, exports numeric SV1 logs for all 212
  requests and per-stage files. `tail_us` is a labelled unit conversion from saved
  native `tail_ms`, not a new measurement. Preserves raw logs and flags suspicious
  timing; it does not explain Device clock discrepancies or accept G2.
- `ble_service.py --expect N --hold-after-count`: supplemental trials hold the
  connection after N responses until operator Ctrl+C, peer disconnect, or the
  session deadline. This allows live PHY checks before central disconnection.
  It is separate from `--sv1-session`; do not overwrite the frozen G2 snapshot.
- `supplemental_link.py`: reads the active peer's decimal HCI handle and emits
  correctly ordered LE Read/Set PHY commands; preserves BR/EDR primary PHYs when
  enabling LE 2M with a powered-on kernel 5.15 controller. Checks command status
  separately from actual PHY. Snapshots/restores selected PHYs and exports the
  supplemental logs as numeric FP32/FP16-scale-hash JSONL. `export --trial4
  ACTUAL_FOLDER` additionally exports the final 10 requests under the receiver
  name `supp4_pairs5_2M.jsonl`, preserving raw folder names and checksums.

Log `logits`/`logits_hex_le` use 5 strings, each containing **four float32 bytes
in little-endian order**; `logits_float` is a human-readable copy. `label` is the
index 0..4 (N,S,V,F,Q), ties pick the first. `scale_sha256` hashes original-channel
wire scales (16 float32_le), not the FP16 storage bytes. `t_rx_ms` is monotonic
on Edge when reassembly finishes; it is not a synchronized one-way timestamp.
A downstream SV1 checker must agree on these encodings; do not edit raw logs to
force a PASS. The receiver confirmed import compatibility on 27 October; its original
Week 8 checker/report is not present in the fetched branches at publication.

The four SV1 stage logs use the handoff's additional convention: `ev=request`,
`scale_sha256` hashes 16 FP16 little-endian scales, and `logits` contains the five
numeric FP32 response values. Canonical `peer.jsonl` retains its original FP32
scale hash and adds `scale_fp16_sha256`. `t_tx_done_ms` marks completion of all
BlueZ Write Without Response submissions on the same monotonic clock as RX;
it is not an over-the-air timestamp or an acknowledgement from the dongle.
An OK inference whose send failed is `SEND_FAILED` in the SV1 log.

Reference input SHA256:
`e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5`.
This pins the received file, not an independently authenticated sender manifest.
Reference labels are offline predictions; true-label sampling still needs the
sender's samples.csv/manifest. No NPZ/model/bench key is committed here.

Build worker in a **new** directory with
`bash edge/runtime/persistent/build.sh <new-build>` on matching KV260. Run each
Python entrypoint with `--help`; every evidence output must be a new directory.
Keep key outside the source snapshot/repo. Echo needs no key. Inference without
key can handle P0; P1 returns KEY_UNAVAILABLE.

HOST tests: `python -B edge/tests/test_week8_service.py` (NumPy required).
The HOST helper test does not link VART. Before declaring ARM validation, build
against real Vitis AI 2.5 and compare offline worker outputs to the original
single-input runner on identical inputs.

## Versions and limits

The 212-request G2 service hash is `79a1da1b...`; supplemental held connections
used `a424bc90...`. Full SHA256 and archive pins are exported under
[results/week8/edge](../../../results/week8/edge/README.md). The latter service
is published here; post-run export helpers may differ from captured snapshots.
`edge/export_week8_evidence.py` checks saved hashes and outputs small results.

`--hold-after-count` keeps the connection but stops processing further requests
after the count. Coordinate a new session before sending extra requests.
P1 high-water and retry cache are RAM-only, lost on service restart. The proposed
r2 registry acceptance applies to the Dongle nonce counter, not durable Edge
replay rejection or production authorization. Week9 must Set/Read PHY on every
connect/reconnect and gate measurement on actual TX/RX2M; this service does not
automate that requirement. Prefer serial for long TRACE collection and verify
the collector/file before requests; connection logs are not a full HCI trace.
