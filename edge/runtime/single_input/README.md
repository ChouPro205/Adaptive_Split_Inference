# Single-input root GraphRunner

This folder originates from the Week 7 saved ARM execution snapshot. The only
subsequent runner change corrects the diagnostic to `samples must be 1`, matching
the existing validation; input handling and inference are unchanged. Unlike the
original Week 5 runner, it reads one FP32 tensor: NCL `[1,C,L]` for s0…s8,
NC `[1,32]` for s9. Only sample index 0
and `--samples 1` are accepted. The Week 5 runner and historical evidence stay intact.

Native KV260 build, matching Vitis AI 2.5 development libraries and g++ C++17:

```bash
bash edge/runtime/single_input/build_tail_runner.sh <new-build-directory>
```

The binary uses the same GraphRunner from the root XIR graph, NCL/NLC conversion,
fix_point/DPU_ROUND, input/output synchronization and final `(1,5)` logits as the
original runtime. App-local Conv1d/MaxPool1d/ReLU libraries are still required.
A child-DPU result never substitutes for the complete tail. s10 is handled by the
Python I1 receiver as identity and is never sent to this binary.

The [file service](../../server/week7/README.md) writes a single-input NPY from the
received packet and invokes this binary. Saved hardware results cover 46 native
tail calls plus four s10 identity requests. This is file transport, not BLE.
Rebuilds have new binary hashes; preserve the original binary/source receipts.
The byte-exact source used for the saved Week 7 results is pinned at commit
`a851a05`. To reproduce the historical evidence export, use that source checkout;
the exporter deliberately rejects a current runner that differs from the measured
snapshot, including diagnostic-only edits.
