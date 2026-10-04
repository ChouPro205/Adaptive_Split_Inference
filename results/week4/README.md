# SV1 tuần 4 — kiểm chứng MCU và timing R3

[Báo cáo SV1/Châu tuần 4](../../docs/sv1_device_week4_report.md) trình bày mục tiêu, triển khai, kết quả và giới hạn nghiệm thu.

**PASS trên nRF52840 Dongle PCA10059 thật, ngày 2026-10-02 (Asia/Saigon).**
220/220 tensor PASS, chuỗi đổi sample/split 16/16 PASS, 1100/1100 lượt timing hợp lệ.
Sai số lớn nhất `1.43051147e-05` tại sample 6 `MIT-BIH:105:1741:MLII`, s=9; tiêu chí strict `<1e-3`.
Không thay golden, mô hình, precision hoặc tolerance. Tất cả phép tính là FP32, thứ tự C, NCL s0..8 và NC s9..10.

## Hiện vật chính thức

- `logs/week4_capture.txt`: toàn bộ CDC capture thật (220 RUN + 16 RUN đổi thứ tự + 11 BENCH, tổng 247 tensor).
- `week4_mcu_validation.json`: checker, toàn bộ sai số, 1100 cycles, provenance và hashes.
- `week4_errors_20x11.csv`: 220 ca chính thức.
- `week4_timing_1100.csv`: cycles và thời gian từng lượt.
- `week4_timing_summary.csv`: mean/std/p95/min/max từng split.
- `figures/week4_t_dev.png`: đồ thị t_dev(s), số liệu nguyên bản.
- `week4_footprint.json`: ELF/linker footprint và stack main đo thật.

`.gitattributes` trong thư mục này giữ nguyên bytes capture khi Git checkout, tránh đổi hash do CRLF/LF.

## Firmware, input và truy nguồn

ZIP DFU SHA256 `d13facbca1fd7d83b036361eeea3ef33bdff015d62a9476142cfcc6244faf171`; application binary SHA256 `5e6169561f561ee533cc153c1807b7b129d4e1940df54039f0448c726bbd2cae`.
ELF SHA256 `d9a1ef3197705b0aa1d21d64d0420dbea2195dc27c7d36b53ddf89dff107e97c`.
R3 manifest `80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c`; all-split manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.
Input NPY SHA256 `dac1d1e9df849bf4ffa30359384d129586f67ec0703157b692d1344685b78dcc`; checkpoint SHA256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Các SHA256 source đã build, generated headers, weights/header, graph, sample CSV và 11 golden đều nằm trong JSON provenance.
Firmware được build từ tree trước commit kết quả; source hashes và ELF/application/ZIP hashes xác định đúng image đã nạp.
USB DFU `COM6` (VID_1915/PID_521F), ứng dụng `COM7` (VID_2FE3/PID_0004), nhận diện lại thay vì giả định cổng cố định.
NCS 3.4.0, Zephyr 4.4.0, ARM GCC 14.3.0, Python 3.11.9, NumPy 2.4.6, Matplotlib 3.11.2.
Không sửa SB1/SB2, bootloader, cấu hình phần cứng, artifacts R3/R2, venv hoặc bằng chứng tuần 2/3.

## Mapping

| s | Head endpoint | Shape/layout |
|---|---|---|
| 0 | normalized_model_input (identity head) | 1x1x360 NCL |
| 1 | features.1 | 1x16x360 NCL |
| 2 | features.4 | 1x16x180 NCL |
| 3 | features.6 | 1x32x180 NCL |
| 4 | features.9 | 1x32x90 NCL |
| 5 | features.11 | 1x48x90 NCL |
| 6 | features.14 | 1x48x45 NCL |
| 7 | features.16 | 1x64x45 NCL |
| 8 | features.19 | 1x64x22 NCL |
| 9 | classifier.3 | 1x32 NC |
| 10 | classifier.4 | 1x5 NC |

Head luôn chạy từ input gốc; không tái sử dụng activation của lệnh trước.
s0 identity khớp bitwise input; s2 được đối chiếu trực tiếp với P2 của capture MCU tuần 3 đã nghiệm thu; s10 là logits 5 lớp N/S/V/F/Q.
Chuỗi bổ sung, đúng thứ tự: `[(19, 10), (0, 0), (7, 8), (3, 2), (19, 1), (0, 10), (12, 0), (1, 9), (18, 4), (2, 7), (14, 6), (5, 3), (11, 5), (0, 2), (19, 10), (0, 0)]`.

## Phương pháp timing

Một sample cố định: 0, `MIT-BIH:105:197:MLII`. Mỗi split 20 warm-up rồi 100 lượt đo.
DWT CYCCNT phần cứng, Cortex-M4 64 MHz; `time_ms = cycles / 64000000 * 1000`.
SystemCoreClock trong Nordic MDK là 64000000 và cả 11 TIMING frame đều khai báo cùng tần số này.
Không dùng CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC=32768: đây là RTC/tick Zephyr, không phải DWT CPU clock.
IRQ khóa trong từng head call; GPIO, USB, log, chờ lệnh và so sánh golden nằm ngoài khoảng đo.
Sau toàn bộ batch mới in cycles/tensor. Kết quả head được lưu và xuất, không bị compiler bỏ; `-ffp-contract=off`.
s0 được đo thực tế, không gán 0 hoặc trừ baseline. Counts bao gồm dispatch/shape bookkeeping của head API.
Std là sample standard deviation ddof=1 (n−1); p95 là NumPy linear interpolation h=(n−1)*0.95.
Thứ tự số đo và split được giữ nguyên; không thêm delay, sắp xếp hay sửa số liệu để ép tăng.
Mean tích lũy tăng theo s; không phát hiện điểm giảm. Payload không đơn điệu và không dùng để suy thời gian.
Std bằng 0 ở s2..10 vì 100 số đếm cycles của từng split giống hệt nhau khi IRQ bị khóa; số liệu được giữ nguyên.

| s | n | mean (ms) | std (ms) | p95 (ms) |
|---|---:|---:|---:|---:|
| 0 | 100 | 0.005975937 | 0.000050566 | 0.005968750 |
| 1 | 100 | 18.977718750 | 0.000800890 | 18.978515625 |
| 2 | 100 | 234.458281250 | 0.000000000 | 234.458281250 |
| 3 | 100 | 448.941296875 | 0.000000000 | 448.941296875 |
| 4 | 100 | 873.582734375 | 0.000000000 | 873.582734375 |
| 5 | 100 | 1190.511750000 | 0.000000000 | 1190.511750000 |
| 6 | 100 | 1664.525390625 | 0.000000000 | 1664.525390625 |
| 7 | 100 | 1978.064906250 | 0.000000000 | 1978.064906250 |
| 8 | 100 | 2395.608343750 | 0.000000000 | 2395.608343750 |
| 9 | 100 | 2409.012078125 | 0.000000000 | 2409.012078125 |
| 10 | 100 | 2409.063171875 | 0.000000000 | 2409.063171875 |

## Bộ nhớ và giới hạn chứng cứ

Flash `523424/913408 B`, còn `389984 B` trong vùng DFU app `[0x1000,0xe0000)`.
RAM tĩnh `65464/262144 B`, còn `196680 B` theo linker.
Weights const 438612 B + inputs 28800 B trong Flash. Activation A/B tổng 46080 B, timing array 400 B trong RAM.
Stack main khả dụng 4096 B (ELF cấp 4224 B gồm guard/alignment), high-water đo được `616/4096 B` qua 247 lệnh.
Stack UDC/USBD/workqueue/ISR/idle đã cấp nằm trong RAM tĩnh. High-water các stack này và peak RAM tổng runtime chưa đo.
Không quan sát reset, fault, dữ liệu không hữu hạn hoặc lỗi buffer/giao thức trong phiên thu; không thay cho stress test dài hạn.
Build hồi quy tuần 3 đã PASS vì CMake/Kconfig dùng chung; kernel/entry point/bằng chứng tuần 3 không sửa.

## Lệnh tái chạy

Dùng cổng thực tế sau khi nhận diện, không sao chép COM6/COM7 khi cổng đã thay đổi. Ghi mỗi phiên mới vào thư mục work riêng.

```powershell
# Giữ/đổi tên ZIP tuần 4 cũ trước khi tạo ZIP mới; script không ghi đè ZIP hiện có.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week4_head.ps1 -PackageDfu
& ml/.venv/Scripts/python.exe -B device/scripts/summarize_week4_preparation.py --repo-root . --report-dir D:/HUST/SV3_week4_R3/firmware-build
# Nạp ZIP đã đối chiếu: nhấn RESET/SW2 để vào bootloader trước.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week4_head.ps1 -Port COMx
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week4.ps1 -Port COMy -Output D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/week4_capture.txt -Report D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/validation.json -BenchSample 0
& ml/.venv/Scripts/python.exe -B device/scripts/check_week4_capture.py --repo-root . --capture results/week4/logs/week4_capture.txt --report D:/HUST/SV3_week4_R3/mcu-week4-work/recheck.json --bench-sample 0 --mixed-order
# Xuất bộ kết quả mới vào thư mục rỗng; dùng receipt và memory report của build vừa nạp.
& ml/.venv/Scripts/python.exe -B device/scripts/analyze_week4_mcu.py --repo-root . --capture D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/week4_capture.txt --dfu-receipt D:/HUST/SV3_week4_R3/mcu-week4-work/dfu-YYYYMMDD-HHMMSS.json --memory-report D:/HUST/SV3_week4_R3/firmware-build/week4_memory.json --application-port COMy --bench-sample 0 --output-dir D:/HUST/SV3_week4_R3/mcu-week4-work/new-evidence
```

Collector chạy checker sau 220 tensor, rồi sau chuỗi đổi sample/split; chỉ đo BENCH sau cả hai PASS.
Logs prepare/thử nghiệm/DFU và các checkpoint giữ ngoài repo tại `D:/HUST/SV3_week4_R3/mcu-week4-work`.

Checker ban đầu từ chối banner khởi động chuẩn NCS/Zephyr và dừng trước timing.
Đã sửa để chỉ chấp nhận banner này trước READY, rồi thu lại toàn bộ phiên cuối.
18/18 phép thử với capture bị thiếu/trùng/sai định dạng hoặc timing hỏng đều bị từ chối; kiểm tra collector chia chunk cũng PASS.
