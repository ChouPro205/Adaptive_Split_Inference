# Persistent multi-split root GraphRunner cache — Week 10 candidate

One ARM process lazily owns ten model contexts (s0…s9). Each context retains its
XIR graph, attrs, root GraphRunner and runner-owned tensor buffers. Only one job
executes at a time. Selecting s10 records the identity route without loading a
model; Python returns the dequantized five logits. No model/binary from earlier
measurements is changed. Real ARM build, resource capacity and timings still
require validation on KV260 PetaLinux 2022.1 / Vitis AI 2.5.

From repository root **on KV260**:

```bash
bash edge/runtime/model_cache/build.sh NEW_BUILD_DIRECTORY
```

The directory must not exist. The build produces `asi-cache-worker` plus the
existing single-input runner as `asi-single-runner` for sequential parity checks,
and saves compiler/source/binary hashes. The native build refuses a non-ARM host.

Internal stdin protocol (not I1/BLE): four uint32 little-endian fields,
`operation, job_id, logical_split, byte_count`. Job IDs strictly increase.
Operation 1 SELECT has zero payload and acknowledges context readiness; operation
2 INFER requires the selected native split and exactly one FP32 NCL/NC tensor.
Stdout has JSON ready/selected/result events; stderr has diagnostics. Errors are
fatal. The Python adapter bounds write/read deadlines, matches job IDs/splits,
poisons the process after failure and never silently restarts it.

`native_select_ms` includes lazy load on a miss; Python `switch_ms` also includes
SELECT IPC. `tail_ms` includes layout/quantization, copies/sync, full root
CPU+DPU execution and final output conversion. Report tail after switching to
expose deferred runtime work. Cache ownership does not guarantee that every
low-level runtime/device allocation is retained; measured execution is required.

Ten live contexts may exhaust target resources. Stop on an actual load failure,
preserve logs, and review cache capacity before changing the policy. There is no
eviction or fallback that would relabel a reload as a hit. An application cache
miss does not mean a cold Linux filesystem cache.
