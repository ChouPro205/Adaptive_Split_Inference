# KV260 single-connection energy peer

`ble_energy.py` reuses the unchanged Week8 `common.Worker`, `service.Receiver`
and `sv1_log.sv1_row`. It adds an active 2M PHY gate before TX notification,
direct numeric request/PHY logs and a single-session lifecycle. It starts
scanning before Device power, processes 200 requests, waits for Device
disconnect, then stops without reconnecting. There is no MQTT, load generator,
new dispatcher, additional warm-up, model build or firmware operation.

Use matching KV260 PetaLinux 2022.1/Vitis AI 2.5 and Bleak0.22.3. A prepared
session must contain `preparation.json` with the actual service commit and
`expected_backend.json` with authenticated model/worker/plugin pins. Run
`python ble_energy.py --help` for arguments. Evidence outputs refuse overwrite.

- `requests.jsonl`: numeric FP32 logits, original-channel FP16 scale hash,
  Edge monotonic RX-complete and final BlueZ-submit times in ms, connection0.
- `peer.jsonl`: original Week8 row encoding, including FP32/FP16 scale hashes.
- `phy.jsonl`: every successful or rejected Read PHY with actual TX/RX, status,
  handle, connection and monotonic `t_ms`. Raw command records are retained
  separately in `hci_commands.jsonl`.
- `events.jsonl`, `run.json`, `summary.json`, result checksum: provenance and
  execution state. Capture complete does not accept Device reception or PPK2.

A disconnect before 200 rows, retry, error or deadline seals an incomplete
trial and stops. Do not combine trials or call this production replay protection:
nonce high-water remains RAM-only, as in the Week8 bench receiver.

HOST tests: `python -B edge/tests/test_week9_energy.py` (NumPy required). These
tests mock BLE/native execution and cannot certify real PHY or energy results.
