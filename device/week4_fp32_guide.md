# Week 4 R3 all-split FP32 firmware

This target uses the authenticated R3 graph/parameters in `ml/results/week4-r3`
and the immutable all-split package `mitdb-week3-sv2-fp32-20261001-v1`.
Its separate `CONFIG_APP_WEEK4_HEAD` selection and `main_week4.c` leave the
Week 3 entry point and accepted Week 3 evidence intact.

The official measurement remains **R3, 02/10/2026 (Asia/Saigon)**. Main now
contains the R4 inventory fix from PR #18. `week4_handoff.py` authenticates
all 21 current ML source bindings with the R4 anchor and all 21 historical
R3 bindings from Git commit `c793c06385198accc964e0e60988d7e7a7e9b566`.
It checks 27 R3/R4 payload files byte for byte (26 scientific files plus
the host C report), every reused-file binding and immutable v1. It also
requires identical scientific manifest fields. Headers, weights and the
firmware banner continue to identify R3; this workflow does not create an
R4 MCU measurement.

After PR #22 (`e6d3e8cc40323227d0f15a4bb4091957f2498744`), SV1 also accepts
the complete reviewed trio `verify_week3_sv2.py`, `test_week3_sv2.py` and
`test_week3_sv2_cache.py` from source commit
`add8503d58c6f707a35b4502bf98aff91109c1cd`. Each path binds both its original
R4 hash and its verified PR22 hash; all three updates must be present together.
The proof records these updates separately in `verified_current_source_updates`.
The original R4 trio remains supported. Partial updates, other source changes,
changed manifest bindings and substitution into historical R3/R4 checks fail.
The R4 manifest/release and measured R3 data remain unchanged. Device and ML
use `tools/week4_handoff_auth.py` as their shared authentication policy.
The current ML entry point is `ml/scripts/verify_week4_current.py`; its default
mode authenticates the current checkout before running the pinned R4 numerical
engine. `--source-mode historical` reports only the fixed historical snapshot.
The original `verify_week4.py` remains immutable. See
[current verification commands](../ml/docs/week4_current_verification.md).

Obtain both releases using the trusted receipt/bundle instructions for
[R3](../ml/docs/sv3_sv1_week4_handoff_r3.md) and
[R4](../ml/docs/sv3_sv1_week4_handoff_r4.md). Keep the historical source commit
in local Git history; a shallow clone may need the authenticated R3 bundle.
Hydrate each ZIP separately with the official `release_week4.hydrate()` API:

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "ml/scripts")
from release_week4 import hydrate
for revision, folder in (("r3", "D:/HUST/SV3_week4_R3"),
                         ("r4", "D:/HUST/SV3_week4_R4")):
    delivery = Path(folder)  # receipts/ZIPs authenticated against trusted source first
    receipt = json.loads((delivery / "deliverables.json").read_text(encoding="utf-8"))
    hydrate(Path("."), delivery / f"mitdb-sv1-week4-fp32-20261001-{revision}.zip",
            receipt["archive_sha256"], receipt["archive_size_bytes"], receipt["files"])
```

R3 and R4 stay in `ml/results/week4-r3` and `ml/results/week4-r4`.
Hydration rejects different existing bytes before writing any member.
Also obtain the authenticated Week 3 SV1 v2 package for P2 comparison
using the [Week 3 guide](week3_fp32_guide.md). Ignored binaries are never
added to Git.

Offline recheck on the integrated checkout (reports outside the repo):

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
$sv1CheckDir = 'D:\HUST\SV3_week4_R4\sv1-integration\manual-recheck'
New-Item -ItemType Directory -Force -Path $sv1CheckDir | Out-Null
$sv1R4Anchor = '3ca39030081c6b53a5191f927ead6fdc84cdeba1c69766bbdbc9f1cb9ca3d49a'
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4_current.py --repo-root . --expected-manifest-sha256 $sv1R4Anchor --compiler C:/msys64/ucrt64/bin/gcc.exe
if ($LASTEXITCODE -ne 0) { throw 'Current ML checkout verification failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/generate_week4_inputs.py --repo-root . --source-revision r4 --expected-source-anchor $sv1R4Anchor
if ($LASTEXITCODE -ne 0) { throw 'Handoff authentication failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/verify_week4_host.py --repo-root . --source-revision r4 --expected-source-anchor $sv1R4Anchor --report-dir "$sv1CheckDir/host" --compiler C:/msys64/ucrt64/bin/gcc.exe
if ($LASTEXITCODE -ne 0) { throw 'Host validation failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/check_week4_capture.py --repo-root . --source-revision r4 --expected-source-anchor $sv1R4Anchor --capture results/week4/logs/week4_capture.txt --report "$sv1CheckDir/capture.json" --bench-sample 0 --mixed-order
if ($LASTEXITCODE -ne 0) { throw 'Capture recheck failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/test_week4_handoff.py
if ($LASTEXITCODE -ne 0) { throw 'Compatibility regression failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/test_week4_capture.py --repo-root . --capture results/week4/logs/week4_capture.txt --work-dir "$sv1CheckDir/tamper"
if ($LASTEXITCODE -ne 0) { throw 'Capture tamper regression failed' }
```

Only the child process environment loses NCS Python overrides. Keep the
pinned venv/packages and system PATH. `--source-revision r3` is available
for a checkout containing all original R3 source bindings; it rejects the
current R4 checkout. An anchor for a different revision is always rejected.
The checker retains the R3 banner/anchor and authenticates the original
accepted report, compiled sources, generated headers and available old
ELF/ZIP. Its new report records current R4 authentication separately from
the 02/10 measurement provenance. Missing ignored historical binaries are
reported as unavailable; they do not establish validation of a new image.

From the repository root, build and optionally create a Nordic USB DFU ZIP:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week4_head.ps1 -PackageDfu
```

The script authenticates R3 and compiles the actual C kernels with host GCC
before comparison against all 20 x 11 golden tensors. It also checks reversed
execution order, invalid arguments/commands, and bitwise P2 compatibility with
the unmodified Week 3 C kernels. `-ReuseHostValidation` accepts an existing
PASS report only when the recorded source/generated SHA-256 values still match.
Both modes use the same Python authentication and reuse gate, including
revision anchors, complete source bindings, reverse-order/P2 counts and
strict tolerance. Old reports missing this authentication are rejected.
Neither mode runs ML numerical gates, flash commands, or serial access.

The script builds `nrf52840dongle/nrf52840` with existing NCS v3.4.0,
`--no-sysbuild`, `prj.conf` and `overlay-week4.conf`. It also builds the original
Week 3 target into a separate regression directory because CMake/Kconfig are
shared. Build/generated files stay ignored; reports/logs now default to
`D:\HUST\SV3_week4_R4\sv1-integration\new-build` (`-ReportDir` can override this).
The wrapper requires fresh build directories and never rebuilds into the
accepted `device/build-week4`. Use `-BuildDir` to choose another fresh
directory inside `device` and `-Compiler` for the verified host compiler.

Outputs:

- `device/build-week4-r3-recheck/zephyr/zephyr.elf`, `.hex`, `.map`, `linker.cmd`.
- `device/build-week4-r3-recheck-week3-regression/zephyr/zephyr.elf` (original Week 3 source).
- External `generated/week4_inputs.h` and `week4_graph.h`; the wrapper installs
  missing R3 headers into `device/generated` and requires identical existing headers.
- `device/artifacts/adaptive_split_week4_r3_recheck_fp32.zip` with `-PackageDfu`.
- External `week4_host_validation.json`, `split_mapping.md`, `week4_memory.json`
  and build/ELF inspection logs.

Offline collector verification (text chunking only, no SerialPort or MCU data):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\test_week4_collector.ps1
```

The historical `summarize_week4_preparation.py` report belongs to the original
R3 build. For integrated rechecks use the new host report, isolated-build
memory report and capture report described above; keep the old receipt intact.

Packaging refuses to overwrite an existing Week 4 ZIP. Keep the accepted
`adaptive_split_week4_r3_fp32.zip` intact. Any new build/package is an
unflashed R3 payload rebuild authenticated against current R4 ML source;
MCU validation/timing for that new image remain PENDING.

Weights are `static const` FP32 (438612 bytes). Two 5760-float static arrays
alternate for Conv/Pool/Linear, with ReLU in place and Flatten/eval Dropout
preserving the current activation. Total activation RAM is 46080 bytes;
20 exact normalized inputs occupy 28800 bytes in Flash. Every call starts from
the original input. A returned activation is valid until the next call;
the C API is single-threaded and callers must not use its workspace as input.

The direct Nordic USB DFU configuration starts at `0x1000` after the MBR.
Week 4 explicitly limits Flash to `0xdf000` bytes, ending before the onboard
bootloader at `0xe0000`. The board's MCUboot slot partitions are inactive in
this configuration. Memory inspection verifies the actual linker bounds,
every HEX data address, all 20 read-only weight arrays, buffers and stack
allocations. This static report does not measure runtime stack/USB peaks.

## CDC commands and wire format

`RUN n s` selects sample `n=0..19` and split `s=0..10`. `BENCH n s` selects the
same head with 20 warm-ups and 100 measurements. Invalid/overlong commands
are rejected; an overlong line is discarded through its newline.

Split boundaries come from the accepted manifest, not PyTorch layer counts:

| s | Head endpoint | Output shape | Layout |
|---|---|---|---|
| 0 | Identity normalized input | 1x1x360 | NCL |
| 1 | features.1 | 1x16x360 | NCL |
| 2 | features.4 = Week 3 P2 | 1x16x180 | NCL |
| 3 | features.6 | 1x32x180 | NCL |
| 4 | features.9 | 1x32x90 | NCL |
| 5 | features.11 | 1x48x90 | NCL |
| 6 | features.14 | 1x48x45 | NCL |
| 7 | features.16 | 1x64x45 | NCL |
| 8 | features.19 | 1x64x22 | NCL |
| 9 | classifier.3 | 1x32 | NC |
| 10 | classifier.4 logits (N,S,V,F,Q) | 1x5 | NC |

The banner pins the R3 manifest hash. Each command emits:

```text
BEGIN <n> <sample_id> <s> RUN|BENCH
[TIMING <n> <sample_id> <s> warmup=20 measured=100 cpu_hz=<Hz> irq=locked baseline=raw]
[CYCLES <n> <s> <iteration 0..99> <raw cycles>]
TENSOR <n> <sample_id> <s> FP32 <NCL|NC> <rank> <dimensions...> <numel>
<8-digit FP32 hexadecimal words in C order; at most 16 per line>
END <n> <s>
[STACK main_peak_bytes=<measured high-water> main_size_bytes=<size>]
DONE <n> <s> RUN|BENCH
```

Bracketed lines appear for timing/stack reporting, not literally with brackets.
For BENCH, IRQs are locked for each head call only. DWT reads bracket the C API;
GPIO marker writes, command parsing, warm-up and output are outside the timed
interval. All printing starts after the whole measurement batch. Counts include
head dispatch/bookkeeping and identity handling at s=0; no baseline subtraction
or fabricated zero is used. A 32-bit counter wraps after about 67 seconds at
64 MHz, so one head invocation must take less than a wrap interval.

USB retains Week 3 runtime RTS/CTS backpressure, RX interrupt enable to arm
initial USB OUT, and a 5 ms drain pause per 16 tensor words. Timing output
is paced too. The checker enforces finite FP32 and strict max error `<1e-3`.

## Accepted dongle results

The real PCA10059 run on 2026-10-02 passed 220/220 tensors, 16 mixed-order
commands and 1100 timing measurements. Maximum error was 1.43051147e-5;
all 20 P2 outputs matched the accepted Week 3 MCU capture bitwise.
Main stack high-water was 616/4096 bytes. Other thread stack high-water and
overall runtime RAM peak remain unmeasured.
See [the official results](../results/week4/README.md), including hashes,
timing statistics, footprint and the complete measured capture.

## Repeating the dongle stage

For a new run, enter the existing Nordic USB DFU bootloader and use the
existing packaging/DFU procedure, selecting the Week 4 ZIP explicitly.
Do not use the Week 3 flash script unchanged: it is pinned to the Week 3 ZIP.

The separate DFU script verifies the package/ELF and compiled-source hashes
against preparation evidence, then writes a DFU receipt/log outside the repo:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week4_head.ps1 -Port COMx
```

After application CDC appears, run this explicit collector with its application
port `COMy`. It captures/checks all 220 tensors, then checks 16 interleaved
sample/split RUN commands, before all 11 split benchmarks on sample 0.
Timing starts only after both validation checkpoints PASS. The capture drains
continuously and preserves partial data on failures. Use a fresh external work
directory, and publish only a fully validated final run:

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week4.ps1 -Port COMy -Output D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/week4_capture.txt -Report D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/validation.json -BenchSample 0
```

`analyze_week4_mcu.py` publishes a fully checked capture, 20x11 errors, all 1100
cycles, mean/sample std/p95, plot, footprint and source/input/firmware hashes to
`results/week4`. It takes `--capture`, `--dfu-receipt`, `--memory-report`,
`--application-port` and optional `--output-dir`; it refuses to overwrite a
nonempty evidence directory. It rechecks the copied final capture.
Choose fresh filenames for reruns; the collector retains existing evidence.
To recheck a saved real capture without opening a port:

```powershell
& ml/.venv/Scripts/python.exe -B device/scripts/check_week4_capture.py --repo-root . --capture results/week4/logs/week4_capture.txt --report D:/HUST/SV3_week4_R3/mcu-week4-work/recheck.json --bench-sample 0 --mixed-order
```

The collector uses existing .NET SerialPort, so it needs no pyserial dependency.
Collector `-NoTiming` and checker omitting `--bench-sample` handle the 220 RUN
tensors plus 16 mixed commands and leave MCU timing PENDING (use `--mixed-order`
to check the mixed sequence). Checker `--bench-sample n` checks 100 ordered nonzero cycle counts
for every split, including s=0, and records raw cycles/mean/min/max plus CPU Hz.
The initial SDK/Zephyr boot banners are accepted before READY only; repeated
READY or unexpected output during a command is rejected. s0 must preserve input
bits, and s2 is also checked against the accepted real Week 3 MCU P2 capture.
`test_week4_capture.py --capture <real file> --work-dir <external folder>` verifies
that truncated, duplicated, malformed and corrupted versions cannot yield PASS.
