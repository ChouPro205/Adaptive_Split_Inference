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

The collector sends `TRACE 0` followed by `RUN 1` through `RUN 19`. The firmware sends every FP32 element as eight hexadecimal bit digits. The checker maps sample indices through the v2 `samples.csv`, checks full tensors and reports P2 max absolute error for each `sample_id`. It writes `device/reports/week3_mcu_validation.json` and prints `MCU_20_OF_20: PASS` only when all 20 P2 errors are strictly below `1e-3`. Sample 0 intermediate errors are also reported. Keep the capture and report as measurement evidence.

## Current status

Host sample 0 and the Week 3 build/DFU package passed on 2026-09-28. No COM port was present on the build machine at that time; USB DFU and all MCU measurements remain pending.
