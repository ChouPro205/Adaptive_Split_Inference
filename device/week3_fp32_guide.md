# SV1 Week 3 FP32 head on nRF52840 Dongle

The accepted package is `ml/artifacts/week3/mitdb-week3-fp32-20260925-v2`. Its independently trusted `manifest.json` SHA-256 is `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`. The firmware uses its `firmware/head_parameters.h` and embeds the exact already normalized `inputs.npy` values. It computes `Conv1 -> ReLU1 -> Conv2 -> ReLU2 -> MaxPool1d`, ending at P2 `(1,16,180)` in FP32. There is no second normalization or INT8 conversion.

## Host comparison and build

From the repository root in a PowerShell session without NCS `PYTHONHOME` or `PYTHONPATH`:

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& ml/.venv/Scripts/python.exe -B device/scripts/verify_week3_host.py --repo-root .
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week3_head.ps1
```

The host script compiles the same C head used by Zephyr and checks sample 0 at M1, R1, M2, R2 and P2 against the v2 golden tensors. The build script repeats that check, builds a pristine `nrf52840dongle/nrf52840` image with `overlay-week3.conf`, and creates `device/artifacts/adaptive_split_week3_fp32_v2.zip`. Build files stay in `device/build-week3`; generated input constants stay in `device/generated`. The existing Active and Idle build targets are separate.

## USB DFU and capture

1. Close any terminal holding the dongle. Record ports with `[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object`.
2. Press RESET/SW2 on the PCA10059 to enter its Nordic USB DFU bootloader. The red LED fades. Record ports again and identify the newly appearing bootloader COM port.
3. Flash only the Week 3 ZIP through the bootloader port:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week3_head.ps1 -Port COMx
   ```

   Replace `COMx` with the bootloader port. Do not use `west flash`, erase, recover, MCUboot or the Week 1 ZIP.
4. After DFU, locate the application USB CDC COM port again; it can differ from the bootloader port. Capture one full sample 0 trace and the remaining 19 P2 tensors:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week3.ps1 -Port COMy
   Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
   & ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture device/artifacts/week3_capture.txt
   ```

The collector sends `TRACE 0` followed by `RUN 1` through `RUN 19` and reads continuously until each `DONE`. The firmware sends every FP32 element as eight hexadecimal bit digits, with a 5 ms pause after each 16-element line to keep USB CDC output draining. The checker maps sample indices through the v2 `samples.csv`, checks full tensors and ordered command completion, and reports P2 max absolute error for each `sample_id`. It writes `device/reports/week3_mcu_validation.json` and prints `MCU_20_OF_20: PASS` only when all 20 P2 errors are strictly below `1e-3`. Sample 0 intermediate errors and the measured main-thread stack high-water mark are also reported. Keep the capture and report as measurement evidence.

## Current status

On 2026-09-28, the Week 3 build and USB DFU succeeded on a connected PCA10059. The complete 20-sample capture passed the checker (`MCU_20_OF_20: PASS`); the maximum P2 error was `7.15255737e-7`, and the measured main-thread stack peak was `544/4096 B`. See [the build and measurement report](reports/week3_build.md) for the actual ports, image hashes, diagnostics and each `sample_id` result. The final DFU ZIP SHA-256 is `1862C97AD223573C4492D0A3C0DE2D46B225F4C4573F1CE71C67AA4D65103F02`.
