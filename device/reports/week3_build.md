# SV1 Week 3 FP32 build evidence (2026-09-28)

- Branch: `dev/device-sv1`, after PR #11 merge commit `ff7f621706558083b4da5e583cb20268fb6d947e`.
- Package: `mitdb-week3-fp32-20260925-v2`; trusted manifest SHA-256 `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`.
- Recipient acceptance: official checkout scripts with Python `-B` both exit 0; `HANDOFF_CHECKS_PASS`; 27/27 expected rejections; all 29 files and inventory unchanged.
- Host sample 0: `MIT-BIH:105:197:MLII`; M1/R1 max absolute error `2.384185791015625e-7`, M2/R2 `9.5367431640625e-7`, P2 `4.76837158203125e-7`. See `week3_host_sample0.json`.
- Target: `nrf52840dongle/nrf52840`, NCS v3.4.0, `--no-sysbuild`, separate `device/build-week3` and `overlay-week3.conf`.
- Build: exit 0. Zephyr linker FLASH `83016 B / 1020 KB (7.95%)`, RAM `64248 B / 256 KB (24.51%)`. `arm-zephyr-eabi-size`: text `81428`, data `1584`, bss `62628` bytes.
- Week 3 DFU ZIP: `device/artifacts/adaptive_split_week3_fp32_v2.zip`, SHA-256 `E7FF6D546E26DCB580342844586219918A6B99C594CEE9DB79EA52333C791500`; `nrfutil nrf5sdk-tools pkg display` passed. HEX SHA-256 `A2C6F2C97924B56AAB2714FD1DA4691ABB000689BF4F6724CB3C5054FDF16247`.
- Regression compilation in separate check directories: existing Active PASS (FLASH `49244 B`, RAM `18296 B`); existing Idle PASS (FLASH `19476 B`, RAM `6 KB`). Existing Week 1/2 DFU ZIPs were not replaced.
- Device validation: PENDING. `[System.IO.Ports.SerialPort]::GetPortNames()` returned no ports on this machine. No USB DFU, full MCU tensor, stack high-water mark or 20/20 result is claimed.
