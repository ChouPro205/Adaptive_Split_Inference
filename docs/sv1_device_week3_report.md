# Báo cáo công việc Week 3 – đầu suy luận FP32 trên nRF52840 Dongle

## 1. Mục tiêu và phạm vi SV1

SV1 nhận gói mô hình MIT-BIH Tuần 3 v2 từ SV3, chạy đoạn `Conv1 → ReLU1 → Conv2 → ReLU2 → MaxPool1d` trên nRF52840 Dongle và so tensor với golden PyTorch. Mốc cuối đã chốt là P2, shape cho một mẫu `(1,16,180)`. Tiêu chí số học là **từng P2 của 20 mẫu** có `max(abs(MCU - PyTorch)) < 1e-3`, dấu `<` nghiêm ngặt. Hợp đồng còn yêu cầu ghi sai số mốc trung gian theo từng mẫu; phạm vi đã thu và phần còn thiếu được nêu ở mục 11.

SV3 sở hữu checkpoint, graph, input/golden, header tham số và provenance của gói bàn giao. SV1 kiểm gói, port đoạn graph sang firmware C, build/nạp dongle, thu và đối chiếu tensor. Giao diện Device–Edge, ONNX/full-tail runtime và phần việc SV2 là quyết định riêng, chưa được phép đo đầu FP32 này xác nhận. [Hợp đồng bàn giao](../contracts/sv3_sv1_week3_model_handoff.md) giữ nguyên các gate chi tiết; mục 11 nêu phần bằng chứng còn thiếu so với cách viết của hợp đồng.

## 2. Phần cứng, công cụ và cấp nguồn

- Thiết bị: Nordic nRF52840 Dongle PCA10059, cắm trực tiếp vào cổng USB laptop trong các lần DFU và thu USB CDC Tuần 3. SW2/RESET đưa dongle vào bootloader USB DFU, quan sát LED đỏ fade. Lần đo này **không dùng PPK2** và không có số liệu dòng điện hoặc năng lượng Tuần 3. Cách cấp nguồn PPK2 5,0 V của [báo cáo Tuần 2](sv1_device_week2_report.md) là phép đo khác; không cấp đồng thời hai nguồn.
- Target: `nrf52840dongle/nrf52840`, NCS v3.4.0 và Zephyr v4.4.0; build `--no-sysbuild` bằng West, GNU Arm 14.3.0 từ Zephyr SDK 1.0.1. Môi trường và phiên bản công cụ gốc có trong [kiểm tra môi trường](../device/reports/environment_check.txt) và [biên bản build](../device/reports/week3_build.md).
- Build Week 3 dùng `device/overlay-week3.conf`, `device/build-week3` và DFU ZIP riêng. Firmware Active/Idle Tuần 1/2 có đường build riêng; biên bản ghi cả hai build hồi quy PASS. Không dùng `west flash`, erase/recover, MCUboot hoặc sửa SB1/SB2 cho lần DFU này.

## 3. Tiếp nhận dữ liệu và gói SV3

Snapshot MIT-BIH Tuần 1 nằm ở `ml/data/raw/mitdb/` và `ml/data/processed/mitdb/`. [Bằng chứng kiểm dữ liệu Tuần 1](../ml/docs/week1_verification.md) ghi đủ 48 record, 144 file `.hea/.dat/.atr`, official `SHA256SUMS.txt` SHA-256 `b61158a96d5f2ca80edfb354a9a66a6324836c390a84e1966dcee2b907d6be43`, required-file tree SHA-256 `09d0f9c2cf19cbcfc8b704681ce388e62ec89832bfed59169e70ac9ea147e46f` và chín file train/val/test kèm processed manifest. Manifest processed có SHA-256 theo **chính sách text UTF-8 chuẩn hóa LF của repo** là `f712c83d46d71ac6af75b7138668d8918eef87a4ddfeab8e8b5310ced2c44a3c`. Hash byte thô trên máy Windows hiện là `63bc21fa51e0e78ae0e3fcbf5aaf60cf5999733f4c861ba916aa26d18dfe6597`; hai giá trị dùng hai chính sách hash khác nhau, không được thay thế cho nhau. Chính sách nằm trong [quy trình dữ liệu](../ml/docs/week1_data_protocol.md) và `ml/src/week1_common.py`.

Gói được nhận là `mitdb-week3-fp32-20260925-v2`: 29 file, không có file ngoài manifest sau nghiệm thu. ZIP ML SHA-256 `d5511f8c5ebfb1e9eced4aea2f8e89a20dd142b79987a40f6a3347d33d7481eb`; trust anchor độc lập cho `manifest.json` là `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`. Các hash ZIP/manifest đã được đọc lại từ file hiện có khi lập báo cáo. [Release SV3](../ml/docs/week3_release.md) và [provenance v2](../ml/provenance/week3/mitdb-week3-fp32-20260925-v2.verification.json) ghi checkpoint SHA-256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`, source commit `8e98a0e4851abc979feb5fd5b97ece612b02cfaa` và lịch sử v1 bị supersede. JSON provenance được tạo trước phép đo MCU nên các trường PENDING trong đó là ảnh chụp lịch sử, không phải trạng thái thiết bị hiện tại.

SV1 đã chạy **hai script từ checkout được review** bằng `ml/.venv/Scripts/python.exe -B`, `--repo-root .`, đúng `--package` v2 và `--expected-manifest-sha256` nêu trên. `verify_week3.py` và `test_week3.py` đều exit 0, `HANDOFF_CHECKS_PASS`; **27/27 expected rejections PASS** và inventory 29 file không đổi. Lần chạy thử thiếu `-B` trước đó tạo `.pyc` là sự kiện lịch sử, không phải lỗi của lệnh nghiệm thu chính thức. PR [#11](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/11) đã merge vào `dev/device-sv1` tại `ff7f621706558083b4da5e583cb20268fb6d947e`. Đây là **SV1 package acceptance PASS**; không suy từ việc PR merge thay cho phép đo dongle.

## 4. Graph và cách đưa input vào firmware

[Quyết định freeze/boundary](../ml/configs/week3_model_freeze.json) và `model/graph.json` trong gói v2 khóa đoạn đầu: M0 `(1,1,360)` → M1/R1/M2/R2 `(1,16,360)` → P2 `(1,16,180)`, NCL `<f4` (FP32), hai Conv kernel 5, padding 2, bias; MaxPool1d kernel/stride 2. M0 trong `inputs.npy` **đã chuẩn hóa** theo pipeline Tuần 1; firmware không chuẩn hóa lần nữa, không chuyển INT8. Trường `measurement_status` trong graph bất biến mô tả lúc xuất gói chưa có build/đo MCU; số đo sau đó nằm trong biên bản thiết bị, không sửa ngược gói.

[`generate_week3_inputs.py`](../device/scripts/generate_week3_inputs.py) xác thực manifest và inventory rồi chuyển đúng 20 hàng `(20,1,360)` thành `static const float week3_inputs[20][360]` dùng literal hexadecimal FP32. Mảng này được biên dịch vào image; firmware chọn `week3_inputs[sample_index]` và dùng hai buffer activation tĩnh. `sample_index` 0–19 ánh xạ theo thứ tự dòng `samples.csv` sang `sample_id` dạng `MIT-BIH:105:<r_peak_sample>:MLII` (20 dòng thuộc split `val`, patient P105). Kết quả JSON giữ cả index lẫn ID; giao thức console in index, rồi checker tra CSV v2 đã xác thực để gắn ID.

[`week3_head.c`](../device/src/week3_head.c) thực hiện Conv1/Conv2 bằng các vòng lặp C FP32, ReLU và MaxPool1d; [`main_week3.c`](../device/src/main_week3.c) điều khiển USB CDC, marker, phát bit FP32 và đo stack. [`CMakeLists.txt`](../device/CMakeLists.txt) lấy trực tiếp `firmware/head_parameters.h` của đúng gói v2. Đây là kernel C của dự án, **không phải** CMSIS-NN, X-CUBE-AI hay ONNX runtime. [Đặc tả I1](../contracts/i1_device_edge_packet_v1.md) còn đánh dấu model artifact/ONNX/TFLite/CMSIS-NN cho deployment là `DEFERRED`; không thấy X-CUBE-AI trong tài liệu văn bản hiện có của repo. Nếu kế hoạch/đề cương ngoài repo yêu cầu một thư viện cụ thể, cần xin thầy xác nhận, không tự đổi cách triển khai hay tuyên bố đã đáp ứng.

## 5. Kiểm trên host và build firmware

[`verify_week3_host.py`](../device/scripts/verify_week3_host.py) biên dịch cùng kernel C và so mẫu 0 với golden v2. Năm max absolute error: M1 `2.384185791015625e-7`, R1 `2.384185791015625e-7`, M2 `9.5367431640625e-7`, R2 `9.5367431640625e-7`, P2 `4.76837158203125e-7`; `HOST_SAMPLE0: PASS`. [JSON host](../device/reports/week3_host_sample0.json) ghi cùng kết quả.

[`build_week3_head.ps1`](../device/scripts/build_week3_head.ps1) exit 0, tạo HEX và DFU ZIP riêng. Image cuối theo Zephyr linker dùng **84.072 B Flash / 1020 KB** (8,05%) và **64.248 B RAM / 256 KB** (24,51%); `size`: text 82.484 B, data 1.584 B, bss 62.628 B. Hai buffer FP32 `16×360×4` dùng tổng **46.080 B** RAM tĩnh. Đây là số của image, khác phép quét high-water của main stack ở mục 8. ZIP DFU `device/artifacts/adaptive_split_week3_fp32_v2.zip` có SHA-256 **`1862c97ad223573c4492d0a3c0de2d46b225f4c4573f1ce71c67aa4d65103f02`**; HEX SHA-256 `ef5b03ae3b4e0fb7997a427e39e2313ece01cc712c8645acd10b98eaa25e0d24`. Bằng chứng chi tiết ở [biên bản build/đo](../device/reports/week3_build.md).

## 6. DFU và chẩn đoán USB CDC trên dongle

Trong lần nạp cuối, cổng bootloader được xác định lại là `nRF52 SDFU USB (COM6)`, VID:PID `1915:521F`; script [`flash_week3_head.ps1`](../device/scripts/flash_week3_head.ps1) báo `Device programmed`, `DFU succeeded (exit code 0)`. Ứng dụng sau nạp xuất hiện ở `USB Serial Device (COM7)`, VID:PID `2FE3:0004`, rồi in `READY WEEK3 mitdb-week3-fp32-20260925-v2 P2 1x16x180`. COM6/COM7 chỉ là cổng quan sát trong phiên này; lần tái kiểm tra phải phát hiện lại.

Capture ban đầu dài 152 B chỉ có boot banner và `READY`. Collector lỗi ngay `.Write("TRACE 0\n")` với `IOException: The semaphore timeout period has expired`; **chưa nhận `BEGIN 0 TRACE`**. Probe lệnh ngắn `BAD\n` bằng .NET `SerialPort` và NCS pyserial đều timeout khi Write. Đọc mã CDC ACM NCS v3.4.0 cho thấy `uart_poll_in()` không tự khởi phát USB OUT đầu tiên; sau khi bật `uart_irq_rx_enable()`, lệnh ngắn Write xong trong 3 ms và nhận phản hồi `ERROR`, xác nhận cả hai chiều.

Lần sửa nhận đầu tiên vẫn mất byte khi phát tensor lớn vì `poll_out` có thể bỏ byte lúc TX FIFO đầy nếu không bật flow control. Firmware bật chờ FIFO qua `uart_configure()`; `RUN 0` hoàn tất, nhưng phiên collector dừng tại P2 mẫu 10. Chạy riêng `RUN 10` và `RUN 11` vẫn dừng sau 168 dòng P2; pyserial đọc byte thô cũng dừng khoảng 24,6 KB ở `RUN 10`. Kết quả này loại trừ giả thuyết chỉ do PowerShell `ReadLine` hoặc tổng số byte đã đọc trong một phiên. Sau khi nghỉ 5 ms mỗi dòng 16 giá trị, probe `RUN 10` nhận đủ `DONE 10` (26.383 B) và collector hoàn tất 20 mẫu. **Cơ chế stall TX nội bộ chính xác của NCS chưa được cô lập hoàn toàn.** Các phép thử, exit code và lần probe báo sai vì kỳ vọng CRLF quá chặt đều có trong [biên bản thiết bị](../device/reports/week3_build.md); không quy lỗi cho gói SV3.

## 7. Cách thu và kiểm bit tensor

[`collect_week3.ps1`](../device/scripts/collect_week3.ps1) gửi `TRACE 0` rồi `RUN 1` đến `RUN 19`, đọc liên tục đến từng `DONE`, exit 0 và in `Captured sample 0` đến `Captured sample 19`. Mẫu 0 chứa đủ M1/R1/M2/R2/P2; các mẫu còn lại chứa P2. Firmware in **toàn bộ mỗi phần tử** bằng tám chữ số hex của bit FP32, không làm tròn sang số thập phân. P2 mỗi mẫu có 2.880 phần tử; mỗi tensor M1/R1/M2/R2 mẫu 0 có 5.760 phần tử.

[`check_week3_capture.py`](../device/scripts/check_week3_capture.py) xác thực lại inventory v2, giải mã bit thành FP32, kiểm hữu hạn, số phần tử/shape, đủ tập tensor, 20 cặp `BEGIN`/`DONE` theo thứ tự, 20 dòng stack và ánh xạ index/ID; sau đó so từng phần tử với golden cùng hàng. Capture cuối tại `device/artifacts/week3_capture.txt` dài **732.924 B**, SHA-256 **`1e3825300731ac5804c605bb7c007457d8aeb5768e94dab9e16b6ca7503ee051`**. Checker exit 0; [JSON kết quả](../device/reports/week3_mcu_validation.json) lưu hash capture và từng phép so.

Bản lưu trong `results/week3/` gồm [capture đã xác minh](../results/week3/logs/week3_capture_verified.txt), [JSON so sánh](../results/week3/week3_mcu_validation.json) và [biên bản build/đo](../results/week3/week3_build.md). Cả ba bản lưu đều trùng byte với file gốc tương ứng trong `device/`; SHA-256 của capture bản lưu là **`1e3825300731ac5804c605bb7c007457d8aeb5768e94dab9e16b6ca7503ee051`**. Phiên thu COM7 ngày 29/09 chỉ lặp lại P2, không thuộc capture được checker xác nhận và không được dùng làm căn cứ cho kết luận 20/20 PASS.

## 8. Kết quả 20 mẫu trên MCU

| `sample_index` | `sample_id` | P2 max absolute error | `< 1e-3` |
| ---: | --- | ---: | :---: |
| 0 | MIT-BIH:105:197:MLII | 4.76837158e-7 | PASS |
| 1 | MIT-BIH:105:459:MLII | 4.76837158e-7 | PASS |
| 2 | MIT-BIH:105:708:MLII | 4.76837158e-7 | PASS |
| 3 | MIT-BIH:105:965:MLII | 7.15255737e-7 | PASS |
| 4 | MIT-BIH:105:1222:MLII | 4.76837158e-7 | PASS |
| 5 | MIT-BIH:105:1479:MLII | 4.76837158e-7 | PASS |
| 6 | MIT-BIH:105:1741:MLII | 4.76837158e-7 | PASS |
| 7 | MIT-BIH:105:2015:MLII | 7.15255737e-7 | PASS |
| 8 | MIT-BIH:105:2287:MLII | 4.76837158e-7 | PASS |
| 9 | MIT-BIH:105:2550:MLII | 7.15255737e-7 | PASS |
| 10 | MIT-BIH:105:2803:MLII | 5.96046448e-7 | PASS |
| 11 | MIT-BIH:105:3052:MLII | 4.76837158e-7 | PASS |
| 12 | MIT-BIH:105:3303:MLII | 3.57627869e-7 | PASS |
| 13 | MIT-BIH:105:3563:MLII | 4.76837158e-7 | PASS |
| 14 | MIT-BIH:105:3835:MLII | 4.76837158e-7 | PASS |
| 15 | MIT-BIH:105:4102:MLII | 4.76837158e-7 | PASS |
| 16 | MIT-BIH:105:4371:MLII | 4.76837158e-7 | PASS |
| 17 | MIT-BIH:105:4635:MLII | 4.76837158e-7 | PASS |
| 18 | MIT-BIH:105:4901:MLII | 4.76837158e-7 | PASS |
| 19 | MIT-BIH:105:5154:MLII | 3.57627869e-7 | PASS |

Max P2 toàn bộ là **`7.152557373046875e-7`**, thấp hơn ngưỡng nghiêm ngặt `1e-3`; checker in **`MCU_20_OF_20: PASS`**. Mẫu 0 có M1 `2.384185791015625e-7`, R1 `2.384185791015625e-7`, M2 `9.5367431640625e-7`, R2 `9.5367431640625e-7`, P2 `4.76837158203125e-7`. Với `CONFIG_INIT_STACKS=y`, `k_thread_stack_space_get()` báo **main-thread peak 544/4096 B** trong capture cuối. Số này không bao gồm stack của thread khác hoặc interrupt, không phải linker RAM và không phải phép đo năng lượng.

## 9. Revision và hiện vật bằng chứng

- PR #11 merge commit: `ff7f621706558083b4da5e583cb20268fb6d947e`.
- Firmware đã kiểm trên thiết bị: `33a5288e475646c80f14a9cfcd2e797db64c5e41`; commit bổ sung hash firmware vào [biên bản kỹ thuật](../device/reports/week3_build.md): `f1624f43fc68ef1472005b9edb2b5fc450cb1443`.
- [Guide build/DFU/capture](../device/week3_fp32_guide.md), [JSON host mẫu 0](../device/reports/week3_host_sample0.json), [JSON MCU 20 mẫu](../device/reports/week3_mcu_validation.json), [firmware Week 3](../device/src/main_week3.c) và [kernel C](../device/src/week3_head.c) là các điểm đối chiếu trong Git.
- `device/artifacts/adaptive_split_week3_fp32_v2.zip`, `device/artifacts/week3_capture.txt`, các log chẩn đoán, `device/build-week3/`, `device/generated/`, ZIP ML và dữ liệu MIT-BIH ở ngoài Git. Không `git add -f` chúng. Có thể kiểm file hiện có bằng `Get-FileHash -Algorithm SHA256 -LiteralPath <đường-dẫn>` rồi đối chiếu hash ở mục 3, 5 và 7. Đường dẫn ở đây tính từ repo root.

Không chèn ảnh terminal của phiên COM7 lặp lại: ảnh chỉ ghi tiến độ thu, không thể hiện dongle hoặc phép so số học. Bảng sai số, JSON và capture đã xác minh là minh chứng cho kết quả P2; báo cáo này không cần ảnh bổ sung để kết luận mục tiêu số học Tuần 3.

## 10. Tái kiểm tra capture và chạy lại trên dongle

Nếu chỉ cần kiểm lại **capture đã có**, không cần flash lại. Từ repo root, trong PowerShell sạch cho ML:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\device\artifacts\week3_capture.txt
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture device/artifacts/week3_capture.txt
```

Checker cần gói v2 và các golden ở đúng vị trí local, và sẽ cập nhật `device/reports/week3_mcu_validation.json`. Để thu **một capture mới** trên dongle đã chạy đúng firmware Week 3, đóng terminal đang giữ CDC, phát hiện cổng ứng dụng hiện tại bằng `[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object`, rồi chạy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week3.ps1 -Port COMy
```

Thay `COMy` bằng cổng ứng dụng vừa xác định; sau đó chạy checker ở trên. Nếu cần nạp lại image, [guide](../device/week3_fp32_guide.md) hướng dẫn đóng terminal, nhấn SW2, xác nhận LED đỏ fade, xác định **lại** cổng bootloader rồi dùng `flash_week3_head.ps1 -Port COMx`; phát hiện lại cổng ứng dụng sau DFU. Không cố định COM6/COM7 từ lần đo trước và không dùng `west flash`.

## 11. Giới hạn và kết luận

Mục tiêu số học SV1 tại **P2 của đủ 20 mẫu đã PASS** trên PCA10059 với gói v2 và firmware FP32 nêu trên. Đây là kết quả đo tensor đầy đủ, không suy từ dòng `READY` hoặc thông báo DFU. Chưa có số liệu PPK2/năng lượng cho workload này. Phần SV2 vẫn `BLOCKED_ON_SV2_INTERFACE`; chưa có bằng chứng tích hợp Edge/ONNX hay thực thi bằng CMSIS-NN/X-CUBE-AI.

Mục 6 của [hợp đồng bàn giao](../contracts/sv3_sv1_week3_model_handoff.md) còn yêu cầu bảng sai số **mỗi mốc cho từng mẫu**. Capture hiện có chỉ có năm mốc của mẫu 0 và P2 của 19 mẫu còn lại; vì vậy bảng **20 × 5** chưa được chứng minh. Cần SV1/thầy xác nhận phạm vi biên bản hoặc thu thêm `TRACE` cho 19 mẫu, rồi đối chiếu đủ M1/R1/M2/R2 theo từng `sample_id` nếu quy cách chi tiết vẫn áp dụng. Không dùng `MCU_20_OF_20: PASS` ở P2 để tuyên bố tự động PASS cho phần chưa đo hoặc cho toàn bộ dự án.

## 12. Chuyển sang Tuần 4

Kết quả P2 FP32 20/20 cùng Flash/RAM của image là mốc tham chiếu cho công việc tiếp theo. Theo [audit mô hình](../ml/docs/week3_audit.md), phần profiling các điểm cắt thuộc Tuần 4 và chưa được thực hiện trong phép đo này. Trước khi dùng P2 cho truyền Device–Edge, các bên cần chốt profile giao diện I1/SV2; trạng thái hiện tại vẫn `BLOCKED_ON_SV2_INTERFACE`. Đồng thời xử lý khoảng thiếu bảng 20 × 5 nêu trên theo yêu cầu hợp đồng, không chuyển kết quả P2 thành kết luận cho các mốc hoặc điểm cắt chưa đo.
