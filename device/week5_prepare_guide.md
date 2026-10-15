# SV1 Week 5: prepared firmware and later Dongle acceptance

This is an independent Zephyr application in `device/week5/`. It uses the
unchanged accepted Week 4 FP32 kernels, R3 parameters and normalized 20 inputs.
Only cut activations are quantized: symmetric INT8 per sample/channel over L,
stored little-endian binary16 scale, nearest ties-to-even, no hardware FP16.
s0 preserves normalized input; s9/s10 keep NC and add L=1 only for quantization.
I1 v1 scales remain FP32; this USB text stream is a debug acceptance protocol.
P1 C, radio and Device–Edge integration are later work.

No build/preparation script flashes, opens COM or measures a device. Offline
fixtures begin `SIMULATED HOST WEEK5`, and their reports keep MCU PENDING.
Golden quantization must match SV3 bytes exactly. Head C is tested separately
with strict FP32 `<1e-3` and exact quantization against Python on its actual
activation. Differences from the original goldens are explained in the report.
Accuracy uses all 8544 frozen test samples, N=1, unchanged standard FP32 head
and frozen tail, actual C quantization/dequantization; it does not certify MCU.

## Reproduce preparation without a device

From repo root, choose new absolute evidence and build output directories
outside the repository. Clear `PYTHONHOME`/`PYTHONPATH` only in this process.
Use the actual installed host GCC, NCS 3.4.0/Zephyr 4.4.0 toolchain paths.

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
$sv1Evidence = 'D:\HUST\ASI_week5_prepare\NEW_RUN\checks'
$sv1Build = 'D:\HUST\ASI_week5_prepare\NEW_RUN\firmware'
& ml/.venv/Scripts/python.exe -m pip install -r device/scripts/requirements-week5-collector.txt
foreach ($stage in @('baseline','host','accuracy','regression','capture-tests','tools-check')) {
    & ml/.venv/Scripts/python.exe -B device/scripts/run_week5_preparation.py --stage $stage --output $sv1Evidence
    if ($LASTEXITCODE -ne 0) { throw "Preparation failed: $stage" }
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File device/scripts/build_week5_head.ps1 -ReportDir $sv1Build
if ($LASTEXITCODE -ne 0) { throw 'Build/audit/package failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/run_week5_preparation.py --stage memory-audit --output $sv1Evidence --build-report $sv1Build
if ($LASTEXITCODE -ne 0) { throw 'Final ELF/map audit failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/run_week5_preparation.py --stage package-tests --output $sv1Evidence --build-report $sv1Build
if ($LASTEXITCODE -ne 0) { throw 'Package corruption tests failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/summarize_week5_preparation.py --output $sv1Build --evidence $sv1Evidence
if ($LASTEXITCODE -ne 0) { throw 'Preparation evidence incomplete/stale' }
```

Every command has a command/exit-code receipt and log; output refuses reuse
that could overwrite prior accepted builds. The build uses
`nrf52840dongle/nrf52840 --no-sysbuild`, USB CDC RX IRQ arming, RTS/CTS TX
backpressure and 5 ms worker pacing. No golden output or full dataset is built
into the firmware. Static q capacity 5760 B; scale capacity 128 B; kernel
activation buffers 46080 B; one copy of 438612 B FP32 parameters in Flash.
Main stack 4096 B, no application heap. Audit checks actual ELF/map/config/DTS,
HEX records and application bounds `[0x1000,0xe0000)`; static allocation does
not measure runtime stack, RAM or timing.

`preparation.json` binds source/tool hashes, generated headers, model/checkpoint,
manifests, build identity, ELF/HEX/ZIP and application bytes. Code changes after
validation invalidate the associated evidence; rerun affected gates in a new
directory. After committing/pushing identical tested source on dev/device-sv1,
`summarize_week5_preparation.py --output <build> --refresh-git` records the final
SHA, verifies committed content and remote branch, and leaves artifact hashes
unchanged. Never merge main before actual Dongle acceptance.

## Later session: connect, identify ports, preflight, flash, capture

The following is an instruction sequence for a later session; it was not run
during preparation. Use the exact prepared `preparation.json` path.

1. Connect the PCA10059 and press RESET to enter its existing Nordic USB DFU
   bootloader (pulsing red LED). List present ports in Device Manager, or:

   ```powershell
   Get-PnpDevice -PresentOnly -Class Ports | Select-Object FriendlyName,InstanceId
   ```

   Confirm the bootloader USB identity `VID_1915&PID_521F` and record its current
   `COM<number>`. Port names can change; COM6/COM7 are not assumed. Close other
   terminals holding the port. Do not erase/recover or use `west flash`.

2. Read-only preflight:

   ```powershell
   & ml/.venv/Scripts/python.exe -B device/scripts/verify_week5_package.py --preparation '<absolute preparation.json>'
   ```

   Stop on any hash/source/package mismatch. Check ZIP SHA256 against the
   report and verify the correct Week 5 source SHA is checked out.

3. Separately flash through the verified Nordic application ZIP. Substitute
   the actual bootloader port and a new receipt directory:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File device/scripts/flash_week5_head.ps1 -Port COM<number> -Preparation '<absolute preparation.json>' -ReceiptDir '<new absolute DFU receipt directory>'
   ```

   This script checks ZIP, HEX, ELF, application, generated headers and source
   hashes before DFU, and records its real port/command/exit code.

4. Rediscover the application CDC port after reboot. Its product is
   `Adaptive Split Inference SV1`, PID `0004`; confirm the Week 5 banner with
   the source/package identity before collecting. The collector validates this
   banner automatically. Keep the bootloader port distinct from the application
   port; they may be assigned different COM numbers.

5. Collect 20 samples x 11 splits plus 16 mixed sample/split transitions:

   ```powershell
   & ml/.venv/Scripts/python.exe -B device/scripts/collect_week5.py --port COM<number> --preparation '<absolute preparation.json>' --capture '<new absolute capture.txt>' --report '<new absolute MCU report.json>'
   ```

   Each RUN outputs original-shape FP32 hex words, NCL INT8 byte hex and FP16
   scale bit patterns. The shared streaming checker verifies IDs, anchors,
   ordering, shapes/counts, strict FP32 error, s0 bitwise and exact Python
   quantization on the actual MCU activation. It rejects resets, duplicates,
   truncation, corrupt payload/scales and unexpected data. A timeout preserves
   partial capture and cannot create a PASS report.

6. Recheck the saved real capture without serial access:

   ```powershell
   & ml/.venv/Scripts/python.exe -B device/scripts/check_week5_capture.py --capture '<capture.txt>' --collection-receipt '<capture.receipt.json>' --report '<new MCU recheck.json>'
   ```

   The receipt binds real collection to the firmware and raw capture hash.
   `--simulated` is only for labelled offline fixtures and always reports MCU
   PENDING. Preserve any explained golden differences; do not alter golden
   files, thresholds or MCU output to force a match.

Flash remains NOT_RUN and MCU validation, device timing, runtime RAM/stack
remain PENDING until the corresponding real later steps are performed. This
application prepares numerical acceptance; it currently has no BENCH command
and does not claim device timing or runtime stack measurements.
