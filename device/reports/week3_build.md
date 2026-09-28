# SV1 Week 3 FP32 build evidence (2026-09-28)

- Branch: `dev/device-sv1`, after PR #11 merge commit `ff7f621706558083b4da5e583cb20268fb6d947e`.
- Package: `mitdb-week3-fp32-20260925-v2`; trusted manifest SHA-256 `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`.
- Recipient acceptance: official checkout scripts with Python `-B` both exit 0; `HANDOFF_CHECKS_PASS`; 27/27 expected rejections; all 29 files and inventory unchanged.
- Host sample 0: `MIT-BIH:105:197:MLII`; M1/R1 max absolute error `2.384185791015625e-7`, M2/R2 `9.5367431640625e-7`, P2 `4.76837158203125e-7`. See `week3_host_sample0.json`.
- Target: `nrf52840dongle/nrf52840`, NCS v3.4.0, `--no-sysbuild`, separate `device/build-week3` and `overlay-week3.conf`.
- Final build command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week3_head.ps1`, exit 0. Zephyr linker FLASH `84072 B / 1020 KB (8.05%)`, RAM `64248 B / 256 KB (24.51%)`. `arm-zephyr-eabi-size`: text `82484`, data `1584`, bss `62628` bytes. Two static FP32 activation buffers use `46080 B` of the RAM image.
- Final Week 3 DFU ZIP: `device/artifacts/adaptive_split_week3_fp32_v2.zip`, SHA-256 `1862C97AD223573C4492D0A3C0DE2D46B225F4C4573F1CE71C67AA4D65103F02`; `nrfutil nrf5sdk-tools pkg display` passed. HEX SHA-256 `EF5B03AE3B4E0FB7997A427E39E2313ECE01CC712C8645ACD10B98EAA25E0D24`.
- Regression compilation in separate check directories: existing Active PASS (FLASH `49244 B`, RAM `18296 B`); existing Idle PASS (FLASH `19476 B`, RAM `6 KB`). Existing Week 1/2 DFU ZIPs were not replaced.
- Final USB DFU: the present bootloader was independently identified as `nRF52 SDFU USB (COM6)` (`USB\VID_1915&PID_521F`), and `flash_week3_head.ps1 -Port COM6` exited 0 with `Device programmed` and `DFU succeeded`. The application then appeared as `USB Serial Device (COM7)` (`USB\VID_2FE3&PID_0004`). These COM numbers are observations for this run, not fixed settings.

## CDC diagnosis and device measurement

The original 152-byte capture held only the boot banners and `READY`. The original collector failed on its first `SerialPort.Write("TRACE 0\n")` with Windows `IOException: The semaphore timeout period has expired`; it had not received `BEGIN 0 TRACE`. A bounded `BAD\n` probe also timed out on Write with both .NET `SerialPort` and NCS pyserial, including after draining the command banner and trying RTS. The local NCS v3.4.0 CDC ACM driver arms USB OUT when `uart_irq_rx_enable()` is called; `uart_poll_in()` alone does not arm its first OUT transfer. After enabling RX in Week 3 firmware, `BAD\n` wrote in 3 ms and received the expected `ERROR`, confirming both directions.

The first RX fix still lost bytes during a large tensor: the CDC ACM `poll_out` driver drops bytes when its 1024-byte TX FIFO is full without flow control. Enabling its runtime flow control removed those malformed words, and isolated `RUN 0` reached `END P2`/`DONE 0`. A full collector session then stopped at P2 of sample 10 (samples 0–9 completed). Isolated `RUN 10` and `RUN 11` each stopped after 168 P2 data lines with .NET; raw pyserial also stopped around 24.6 KB on `RUN 10`. Thus this was not a PowerShell line reader failure or accumulated collector data. The exact internal USB TX stall mechanism was not established. Pacing each 16-value output line by 5 ms made isolated `RUN 10` finish (`26383` bytes, `DONE 10`) and allowed the complete official capture.

Bounded command results on the detected application COM7:

| Command | Exit | Observed result |
| --- | ---: | --- |
| `diagnose_week3_serial.ps1 -Port COM7 -CommandText BAD` before RX enable | 1 | `.Write()` timed out after 10 s with `IOException: The semaphore timeout period has expired`. |
| `diagnose_week3_pyserial.py --port COM7 --command BAD` before RX enable | 1 | `SerialTimeoutException: Write timeout` after 10 s. |
| `diagnose_week3_serial.ps1 -Port COM7 -CommandText BAD` after RX enable | 0 | 3 ms Write; received `ERROR expected TRACE n or RUN n, 0 <= n < 20`. |
| `diagnose_week3_serial.ps1 -Port COM7 -CommandText 'RUN 10'` with runtime TX flow control | 1 | `ReadLine` timed out after 168 complete P2 data lines. `RUN 11` failed at the same line. |
| `probe_week3_bulk.py --port COM7 --command 'RUN 10'` with runtime TX flow control | 1 | Raw pyserial read stopped at 24591 bytes without `DONE`. |
| `probe_week3_bulk.py --port COM7 --command 'RUN 10'` after line pacing | 0 | Raw pyserial read 26383 bytes and found `DONE 10`. |

The first paced probe file already contained `DONE 10`, but its initial terminal detector required one exact CRLF sequence and falsely exited 1. The detector was corrected and the same probe then exited 0. The final collector and checker results below use the unmodified official capture protocol.

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week3.ps1 -Port COM7` exited 0 with `Captured sample 0` through `Captured sample 19`. The ignored capture is `device/artifacts/week3_capture.txt`, `732924` bytes, SHA-256 `1E3825300731AC5804C605BB7C007457D8AEB5768E94DAB9E16B6CA7503EE051`. The original READY-only capture and failing probe/capture logs remain under ignored `device/artifacts/week3_capture*.txt`.

In a clean ML PowerShell environment, `ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture device/artifacts/week3_capture.txt` exited 0. The checker required the exact 20 P2 tensors, all five sample-0 tensors, 20 ordered `BEGIN`/`DONE` pairs, 20 valid stack readings, finite FP32 values and strict `max_abs_error < 1e-3`. Full bit patterns are decoded, then each `sample_index` is mapped to the v2 `samples.csv` `sample_id`.

| sample_index | sample_id | P2 max absolute error |
| ---: | --- | ---: |
| 0 | MIT-BIH:105:197:MLII | 4.76837158e-7 |
| 1 | MIT-BIH:105:459:MLII | 4.76837158e-7 |
| 2 | MIT-BIH:105:708:MLII | 4.76837158e-7 |
| 3 | MIT-BIH:105:965:MLII | 7.15255737e-7 |
| 4 | MIT-BIH:105:1222:MLII | 4.76837158e-7 |
| 5 | MIT-BIH:105:1479:MLII | 4.76837158e-7 |
| 6 | MIT-BIH:105:1741:MLII | 4.76837158e-7 |
| 7 | MIT-BIH:105:2015:MLII | 7.15255737e-7 |
| 8 | MIT-BIH:105:2287:MLII | 4.76837158e-7 |
| 9 | MIT-BIH:105:2550:MLII | 7.15255737e-7 |
| 10 | MIT-BIH:105:2803:MLII | 5.96046448e-7 |
| 11 | MIT-BIH:105:3052:MLII | 4.76837158e-7 |
| 12 | MIT-BIH:105:3303:MLII | 3.57627869e-7 |
| 13 | MIT-BIH:105:3563:MLII | 4.76837158e-7 |
| 14 | MIT-BIH:105:3835:MLII | 4.76837158e-7 |
| 15 | MIT-BIH:105:4102:MLII | 4.76837158e-7 |
| 16 | MIT-BIH:105:4371:MLII | 4.76837158e-7 |
| 17 | MIT-BIH:105:4635:MLII | 4.76837158e-7 |
| 18 | MIT-BIH:105:4901:MLII | 4.76837158e-7 |
| 19 | MIT-BIH:105:5154:MLII | 3.57627869e-7 |

Sample 0 intermediate max absolute errors: M1 `2.38418579e-7`, R1 `2.38418579e-7`, M2 `9.53674316e-7`, R2 `9.53674316e-7`; its P2 value is in the table. The maximum P2 error over all 20 is `7.15255737e-7`. Zephyr `k_thread_stack_space_get` with `CONFIG_INIT_STACKS=y` measured a main-thread high-water mark of `544/4096 B` during this final capture; this does not include other thread or interrupt stacks. The machine-readable evidence is `week3_mcu_validation.json` with capture SHA-256, every `sample_id`, errors and per-sample stack values. **MCU_20_OF_20: PASS.**
