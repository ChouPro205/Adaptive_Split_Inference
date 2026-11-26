# SV2 Week 9: Poisson queue and calibrated MQTT gateway

The measured publisher, dispatcher, BLE hook, clock analyzer and native Windows
receiver are published byte-for-byte from the acquisition snapshots. Runtime
bundles and raw results stay outside Git. New preparation/export helpers do not
pretend to be the commit that originally executed the measurements.

This release measures **KV260 publication-loop timestamp to the entry of the
GW_TRUNG callback on the SV2 PC**. The receiver is a gateway, not the SV1 PC.
The reporting criterion is mean application one-way latency below 20 ms;
percentiles, maxima, uncertainty and outliers are also reported. This does not
assert that every message, p95, or all project acceptance criteria passed.

## Implementation and dependencies

| File | Purpose |
|---|---|
| `queue_sim.py` | Piecewise Poisson arrivals from CSV; one FIFO, one native worker |
| `telemetry.py` | 100 ms MQTT status, QoS 0, retained=false, TCP_NODELAY; ACK diagnostic |
| `oneway.py` | Four-timestamp calibration, affine feasibility and one-way bounds |
| `native_receiver.py` | Windows preflight/capture/stop/export with a local source manifest |
| `prepare_runtime.py` | Fresh portable bundle, reference/backend pins and source hashes |
| `ble_service.py`, `phy_gate.py` | Shared FIFO and active Set/Read 2M before notify on each connection |
| `analyze.py` | Earlier queue/ACK summary; not the final one-way acceptance analysis |
| `trace_check.py` | btsnoop integrity/presence audit; not proof of actual link settings |

`receive_state.py` is the earlier ACK-only receiver; its historical SV1 label
does not describe the final acquisition. `week9_shell.sh` preserves the original
local bench pointers/address for source identity. Use the explicit paths and
native receiver below for portable reproduction; do not infer a receiver role
or network address from those historical helpers.

`week9` imports the existing Week 8 worker, receiver and HCI parser, and the
canonical codecs from `contracts/`. Do not make independent protocol copies in
the source tree or alter Week 8 evidence. The bundle copies dependencies for
deployment, with hashes, without changing the canonical source.

The real backend is the pinned s2 root GraphRunner CPU+DPU, PetaLinux 2022.1 /
Vitis AI 2.5; no model rebuild, fake weights or reference-result lookup. The
foreground and background jobs share a FIFO; at most eight background jobs and
one foreground job wait, excluding the active job. Background overflow is
logged as a drop. A 20-input warm-up happens before queue timing/publication.

On KV260, use the previously validated Python 3.9 runtime/NumPy/Bleak environment.
MQTT requires Paho 2.1.0. Windows acquisition used Python 3.11.9/Paho 2.1.0;
host publication used Python 3.11.9/NumPy 2.4.6. The optional figures need
Matplotlib 3.10.7. Do not upgrade the compiler or board runtime to view results.

## Reproduce publication without a board

From the repository root, with the original runtime session and raw bundle
obtained through the project artifact handoff:

```bash
python3 -B edge/export_week9_evidence.py --session SESSION_DIR --output NEW_OUTPUT
```

`SESSION_DIR` contains `preparation_windows.json`, `sha256sum_prepare.txt`, the
saved `analysis_hien_tai.txt`, received board/Windows data, and W10 review ZIP.
The exporter checks the archive anchor and every sealed input, reruns the pinned
analyzer into a temporary directory, and compares the saved JSON and per-message
bounds. Output must not exist. It never executes a model, accesses SSH/BLE or
modifies original evidence. Optional B5 context is described by `--help`.

If only Git is available, verify `results/week9/edge/sha256sum_export.txt`, read
the CSV/JSON exports or open the read-only notebook. A Git checkout does not
contain the raw captures, reference NPZ, xmodel, plugins, worker binary or key.

## Prepare a new acquisition (not needed to read this report)

Restore the authenticated 100-sample integration NPZ and the pinned native
backend first. From the repository root:

```bash
python3 -B edge/server/week9/prepare_runtime.py \
  --reference VERIFIED_REFERENCE_NPZ --output NEW_BUNDLE_DIR
```

The helper reads `experiments/configs/sv2_edge_week9.json`, creates a fresh
bundle, and pins the actual reference SHA. The same model/worker/plugin hashes
are in `experiments/configs/sv2_edge_week9/expected_backend.json`. Generated
configs are relative to their bundle; shared configs contain no user-specific
absolute paths. Deployed files must pass `sha256sum -c sha256sum_prepare.txt`.

The reproduced topology is:

```text
KV260 publisher :1892 -> reverse SSH -> PC/WSL broker :1891
Windows GW_TRUNG :1891 -> local PC/WSL broker :1891
Windows clock probes :1906 -> SSH -> KV260 clock server :1896
```

Use a private local broker mapping, TCP_NODELAY and the existing network setup;
do not expose an unauthenticated broker to the LAN or change firewall settings
as a workaround. The historical run used PC Wi-Fi and wired KV260; record the
actual route for every new capture.

On the board, after restoring its validated Python environment and unpacking
the fresh bundle, start a clock server in a dedicated terminal (UART preferred):

```bash
python3 -B BUNDLE_DIR/oneway.py clock-server --port 1896 \
  --output NEW_CLOCK_DIR --stop-file NEW_STOP_FILE
```

Use a different fresh stop-file path for every clock session. Keep the server
running through preflight and both captures. It reads monotonic time, not NTP.

Extract `windows_receiver.zip` into a fresh directory on the **same SV2 PC**.
Use native Windows Python, not WSL, with Paho 2.1.0 in a separate venv. In
PowerShell in the extracted directory, after the clock SSH tunnel is ready:

```powershell
.\venv\Scripts\python.exe -B .\native_receiver.py probe --seconds 30
.\venv\Scripts\python.exe -B .\native_receiver.py receive --kind idle
```

Only start the board publisher after `GATEWAY_ONEWAY_READY receiver=GW_TRUNG`.
On the board, from its bundle directory, explicitly supply the authenticated
worker, deployment and CPU-op paths:

```bash
python3 -B source/edge/server/week9/queue_sim.py --config config_idle.json \
  --output NEW_IDLE_OUTPUT --worker VERIFIED_WORKER \
  --deploy VERIFIED_DEPLOY --cpu-ops VERIFIED_CPU_OPS
```

After publisher completion, in another Windows PowerShell at the extracted
receiver directory, request a clean receiver stop:

```powershell
.\venv\Scripts\python.exe -B .\native_receiver.py stop --kind idle
```

Repeat with `varying` and `config_varying.json`, then `native_receiver.py export`.
Wait for `ONEWAY_RECEIVER_SAVED`/exit 0; do not interrupt the log pipeline.
Only after both receivers are sealed, create the board stop file to close its
clock receipt. Keep run/source/clock identity mappings and receive checksums.

Preflight requires a feasible affine clock and an engineering alignment budget
of 5 ms. That budget is not a project acceptance threshold. The final analysis
must still verify every probe, callback coverage, full payload and source
receipt. Never delete probes or use RTT/2 to make a run pass. Physical clock
accuracy beyond the software model is not independently certified.

## Tests and result scope

From the repository root, in a host environment with NumPy and Paho:

```bash
python3 -B edge/tests/test_week9_queue.py
python3 -B edge/tests/test_week9_oneway.py
python3 -B edge/tests/test_week9_native.py
python3 -B edge/tests/test_week9_export.py
```

The snapshot/BLE mock test uses the authenticated NPZ if locally available;
otherwise it explicitly skips that case. These are host tests, not evidence of
radio, DPU, physical clock accuracy or energy acceptance. Raw real-device
evidence and the report are linked from `results/week9/edge/README.md`.

No I1/I2/registry bytes change. The existing I4 status topic is retained;
`dpu_utilization_ratio=null` means not instrumented, not a measured utilization.
The BLE hook is published with its tests, but the final queue/MQTT runs did not
exercise foreground BLE or reconnect. The separate energy service and B5
history do not replace that integration test.
