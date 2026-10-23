# ECG full-tail runner — Vitis AI 2.5

This implementation creates `vitis::ai::GraphRunner` from the complete XIR graph.
It executes all required CPU and DPU partitions, if the installed Vitis AI CPU
runtime supports those operators. It never substitutes a child-DPU result.

`tail_runner.cpp` reads the authenticated 20-sample FP32 NPY, selects samples in
frozen order, converts NCL to NLC only when the runtime shape explicitly requires
it, and uses the input tensor's signed INT8 fix point and `DPU_ROUND` metadata.
Other layouts/rounding modes are rejected. Output must be finite final `(1,5)`
logits. Runtime INT8 output is dequantized; its raw INT8 values are also retained.
The root runner is loaded once per split. There is no latency benchmark here.

## Build and run on KV260

Use a new output directory, with a native aarch64 C++17 compiler and development
headers/libraries for XIR, VART, GraphRunner and glog matching Vitis AI 2.5:

```bash
bash build_tail_runner.sh /path/to/new/bin
/path/to/new/bin/asi-tail-runner --help
python3 -B run_tail_models.py --deploy /path/to/verified/bundle \
  --runner /path/to/new/bin/asi-tail-runner --split 9 --samples 1 \
  --output /path/to/new/smoke_s9
```

`--all --samples 1` attempts one sample for each split; `--all --samples 20`
attempts 200 cases. A split failure is logged and does not erase earlier results
or prevent the batch from attempting the remaining splits. Each invocation
requires a NEW output directory. Run on the board; the Python driver rejects
x86_64. No `sudo`, model rebuild, flash or runtime package installation occurs.

The deploy directory is the existing B3-verified Week 5 bundle with `release/`,
`golden/`, `reference/`, `sha256sum_bundle.txt`, and
`hash_check_dang_dung.txt` pointing to the saved independent host checksum anchor.
The driver rechecks bundle hashes before executing models and records model,
input, reference, binary and driver SHA-256, commands, exit codes and per-case
comparisons. Reports are written outside the immutable bundle inventory.

## Results and acceptance

- Exit 1: input/runtime failure, timeout, or failure against supplied criterion.
- Exit 2: requested execution completed but formal numeric acceptance is pending
  (also normal for one-split smoke runs).
- Exit 0: all 10 splits × 20 samples completed and passed the supplied criterion.

`summary.json` contains each split's execution result and numeric status.
`sN/runner.log` includes the stage reached, runtime input/output metadata and
final logits. `sN/logits.json` is written only after successful completion;
`.partial` is evidence of an interrupted/failed run, never a success result.
`sN/comparison.csv` reports FP32-reference errors and class agreement.
`status.json` distinguishes execution from acceptance. A later split failure
must not be hidden by averaging errors over the batch.

Without `--criterion`, comparisons are descriptive, never correctness PASS.
`criterion_draft.json` is an intentionally incomplete proposal. Copy it outside
the source tree, agree thresholds/scope with the team, then record actual approval
and revision. The driver supports max absolute error plus minimum class agreement
and first-index argmax ties in N/S/V/F/Q order. It checks that approval is declared
and fields are valid; this is not cryptographic verification of a person's approval.
Supply the resulting file with `--criterion /path/to/approved.json`. Smoke results
or comparisons on the 20 calibration-reuse samples do not establish independent
test accuracy, profiling readiness or overall project acceptance.

## Verification limits

The source has been compiled against the actual Vitis AI 2.5 container headers
and libraries on x86_64, and its input parsing/conversion is checked on host.
That is an API/build check, not ARM compilation or a KV260 execution result.
Actual native build, CPU kernel support, root execution and logits require board
logs. Unsupported `conv1d`/`maxpool1d`/`relu` CPU kernels may block the frozen graphs;
keep those failures instead of omitting nodes or changing weights.

## Missing conv1d / maxpool1d / relu CPU implementations

`cpu_ops/` supplies three float32 CPU operators missing from the stock 2.5
image in the reported board run. Weights use OKI layout. The wrappers accept only
the observed frozen ECG attributes: group 1, bias, kernel 5 / stride 1 /
dilation 1 / padding 2 for Conv1d, and floor kernel 2 / stride 2 / no padding for
MaxPool1d. ReLU preserves the tensor shape and replaces negative values with zero. They keep the graph's surrounding fix/dequantize/transpose ops intact.

On the board, or using the same ARM SDK/toolchain as the runner:

```bash
bash build_cpu_ops.sh /path/to/new/cpu_ops_build
python3 -B check_cpu_libraries.py --models /path/to/verified/bundle/release/models \
  --cpu-op-dir /path/to/new/cpu_ops_build --output /path/to/new/preflight.json
python3 -B run_tail_models.py --deploy /path/to/verified/bundle \
  --runner /path/to/existing/asi-tail-runner --all --samples 1 \
  --cpu-op-dir /path/to/new/cpu_ops_build --output /path/to/new/smoke
```

The driver sets `LD_LIBRARY_PATH` for the runner child only and records hashes
of all three libraries in `run.json`. No files are installed in `/usr/lib`, no
`ldconfig`, sudo or model rewrite is needed. A new source package/build/output
must be used, leaving old receipts and failed-run logs unchanged.

Before inference the driver reads selected graphs and load-checks every required
CPU implementation, recording `cpu_libraries.json` and `cpu_library_preflight.log`.
A missing library blocks execution and lists all missing implementations.
A load pass does not establish numerical or full-tail acceptance.

Verification: the numerical kernels are compared to PyTorch over all eight
frozen convolution channel/length configurations and odd/even pooling lengths.
The actual plugin entry points were built/loaded with Vitis AI 2.5 on x86_64 and
called using real s7 op metadata with synthetic test values; outputs matched
PyTorch. Those are CPU unit/ABI checks, not aarch64 or full-tail KV260 acceptance.

API reference: [AMD root GraphRunner 2.5](https://docs.amd.com/r/2.5-English/ug1414-vitis-ai/create_graph_runner).

## Week 6 profiling and saved hardware evidence

Actual saved KV260 execution now covers 200 Week 5 cases and 5000 Week 6
steady-state measurements. See [Week 5 report](../../docs/sv2_edge_week5_report.md)
and [Week 6 report](../../docs/sv2_edge_week6_report.md); numeric acceptance
remains separate. The host-only descriptions above describe the earlier API
and kernel checks, not the limit of the subsequently collected board evidence.

Build the profiler on the board, using a NEW output directory:

```bash
bash build_tail_profiler.sh /path/to/new/profile_build
python3 -B profile_tail_models.py --help
```

Run with the authenticated Week 5 deploy, original on-board 200-case result
folder, existing app-local CPU libraries and new output:

```bash
python3 -B profile_tail_models.py --deploy /path/to/verified/deploy \
  --runner /path/to/new/profile_build/asi-tail-profiler \
  --cpu-op-dir /path/to/existing/cpu_ops_build \
  --week5-results /path/to/original/golden_200 \
  --all --loads 5 --warmup 20 --repeats 100 --output /path/to/new/profile
```

Each load is a new process: filesystem caching is uncontrolled. Timings split
XIR deserialization, root runner creation, tensor setup, first inference and
steady-state prepare/input sync/root execute+wait/output read. `tail_total_ms`
excludes model loading. JSON/log serialization is outside timed calls.
`execute_wait_ms` includes the complete CPU/DPU root graph, not DPU-only time.
s10 is an empty tail, not a measured zero-latency model. The driver checks
model/input/plugin hashes and compares measured logits bit-exactly against the
previously saved Week 5 outputs; this is regression, not independent accuracy.

For portable small results use `python3 -B edge/export_weekly_evidence.py --help`
from the repository root. Raw receipts stay immutable outside Git; reports and
exported inventories document their hashes. The measurement source was not yet
committed when executed; source/binary hashes, rather than the later commit date,
identify the executed implementation. Host profiling checks:

```bash
python3 -B edge/tests/test_profile_tools.py
```
