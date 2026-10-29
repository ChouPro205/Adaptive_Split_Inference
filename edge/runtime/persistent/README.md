# Persistent s2 root GraphRunner

`tail_worker.cpp` creates the full root GraphRunner once, preserving the input
conversion, DPU rounding, synchronization and CPU fallback of the single-input
runner. It reads repeated fixed-size NCL tensors over stdin. It only supports s2;
it does not implement dynamic model switching or the Week 10 model cache.

Protocol: u32 little-endian byte length (11520), then 2880 float32_le values in
NCL [1,16,180]. Stdout contains JSON lines (ready, then logits/tail_ms). Stderr is
captured separately. A timeout faults/kills the worker, requiring investigation
and a new session. This protocol is internal PC/ARM process communication and
does not change I1/BLE. On host little-endian is required.

Build: `bash edge/runtime/persistent/build.sh NEW_BUILD_DIR`. No old binary,
model or source receipt is overwritten. Saved ARM evidence confirms three-sample parity, two 100-sample offline runs
and BLE requests; see [the Week8 report](../../../docs/sv2_edge_week8_report.md).
HOST tests do not execute VART/DPU.

Measured worker source and binary SHA256 are recorded in the Week8 provenance.
Do not rebuild into the saved build directory or alter historical receipts.
