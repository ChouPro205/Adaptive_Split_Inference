# I1 v2 file service and local TCP bench

Week 7 implements the packet pipeline with a PyTorch reference backend or the
native KV260 root GraphRunner. The source was promoted byte-for-byte from the
saved execution snapshot. The original archive and its receipts remain local.
See the [report](../../../docs/sv2_edge_week7_report.md) and
[portable results](../../../results/week7/edge/README.md).

## Inputs and environment

- Use the authenticated `mitdb-week6-p1-50-20261016-v1` package, manifest SHA256
  `d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36`.
  [SV3 delivery](../../../ml/docs/week6_p1_delivery.md) gives ZIP hashes and release storage.
- HOST reference: the existing Python 3.11 ML environment with NumPy, torch,
  ONNX and ONNX Runtime; GCC for C verification. Keep compiler/runtime environments separate.
- KV260: Python 3.9.9/NumPy 1.21.2 and PetaLinux 2022.1/Vitis AI 2.5, authenticated
  Week 5 deploy, native single-input runner and existing app-local CPU libraries.
- Public vector key `00..1f` is only for offline vectors. Bench/radio key material
  comes from a separate protected file, never from the public vectors.

All commands run from repository root and require NEW output paths. Replace
`<package>`, `<model-package>`, `<deploy>`, `<native-runner>`, `<cpu-ops>` and output
paths with verified local paths. The commands perform real inference; observing
saved results requires only the notebook linked below, without running these.

## Verify the SV3 package on Linux

The immutable verifier compares inventories in WindowsPath order; Linux Path
order differs. This wrapper only reorders the computed inventory in memory using
PureWindowsPath. Hash, size, symlink and generating-source checks remain intact.
It never rewrites the package, its manifest or SV3 source.

Prepare a separate checkout at the generating commit `766a3cfa7e7828ecd00b9eb23cc3e5da4015ced5`,
then call the wrapper from the current checkout (absolute script path when needed):

```bash
python -B edge/server/week7/verify_p1_linux.py --checkout <pinned-checkout> --stage A \
  --package <package> --expected-manifest-sha256 d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36 \
  --compiler gcc --output <new-A.json>
python -B edge/server/week7/verify_p1_linux.py --checkout <pinned-checkout> --stage B \
  --package <package> --expected-manifest-sha256 d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36 \
  --model-package <model-package> --output <new-B.json>
```

A git worktree inside an ignored evidence directory is suitable. Do not reset the
working branch or edit source bindings to satisfy the historical verifier.

## File backend

```bash
python -B edge/server/week7/serve.py --request <request.i1v2.bin> --output <new-case> \
  --backend reference --model-package <model-package> --public-test-key
python -B edge/server/week7/batch.py --package <package> --output <new-reference-50> \
  --serve edge/server/week7/serve.py --backend reference --model-package <model-package>
```

The batch checks the external package anchor and member hashes before consuming
the 50 requests. Each request launches a separate process, authenticates/loads
the model again and writes its log to `vNN.log`. Only the final summary appears
on the terminal; allow several minutes and monitor `summary.json` for progress.
These process times are not tail latency or server throughput measurements.

On KV260, build the [single-input runner](../../runtime/single_input/README.md)
and check CPU implementations using `edge/runtime/check_cpu_libraries.py` before:

```bash
python3 -B edge/server/week7/batch.py --package <package> --output <new-kv260-50> \
  --serve edge/server/week7/serve.py --backend kv260 --deploy <deploy> \
  --runner <native-runner> --cpu-op-dir <cpu-ops>
```

`--repo` may point to a transferred source snapshot containing `contracts/`.
The default resolves the repository from this script's location. Transfer the
codec/registry and Python files together; a native-only snapshot need not include
torch/ONNX or the ML tree. s10 is dequantized identity, without creating a model.
The native subprocess timeout is 4 s including load, not a timing measurement.

## Local TCP bench

```bash
python -B edge/server/week7/socket_service.py --serve edge/server/week7/serve.py \
  --output <new-socket-case> --requests 1 --port 7797 \
  --backend reference --model-package <model-package> --public-test-key
```

The server binds `127.0.0.1`. Wait for LISTENING, then send one complete I1 frame
from a separate TCP client. Read the 32-byte fixed header and use I1 total_length
for framing; no fields are added to I1. One frame per connection. Send bytes,
not HTTP from a browser. The server stops after the configured number of
connections, including malformed attempts; restarting requires a new output.
This HOST smoke exercises s10 identity. It does not establish network KV260
inference, BLE reassembly, duplicate cache, admission control or a persistent service.

## Results and checks

A successful file request records status OK, request/response hashes, five finite
logits and predicted class. Envelope/CRC failures drop silently; valid envelopes
with unsupported semantics produce the specified I1 error. Tail errors/timeouts
map to INFERENCE_FAILED/TIMEOUT. Numeric acceptance is separate from execution.

The batch's exit 0 means 50 requests executed; inspect max_abs_error/class_match
and the report. No numeric threshold for INT8/DPU is invented by this driver.
Input-file/codec tests use protocol fixtures, not hardware evidence:

```bash
python -B contracts/i1v2_ref/test_i1v2.py
python -B edge/tests/test_week7_service.py
python -B edge/tests/test_single_input.py
```

The service tests need the frozen FP32 package for the reference environment.
The adapter tests only need NumPy and g++. They compile a standalone helper,
not GraphRunner. Saved results can be read without rerunning the model using
[the Week 7 notebook](../../../experiments/notebooks/sv2_edge_week7.ipynb).
