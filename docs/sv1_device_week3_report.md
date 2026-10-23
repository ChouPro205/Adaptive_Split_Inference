# Báo cáo SV1 tuần 3 — đầu suy luận FP32 trên nRF52840 Dongle

## 1. Mục tiêu và phân công

Tuần 3, SV1 nhận gói mô hình MIT-BIH tuần 3 (bản v2) từ SV3, chạy đoạn đầu
`Conv1 → ReLU1 → Conv2 → ReLU2 → MaxPool1d` trên nRF52840 Dongle và so tensor
với golden do PyTorch tạo ra. Mốc cuối đã chốt là **P2**, shape của một mẫu là
`(1,16,180)`. Trong tài liệu tuần 3–4, P2 là tên mốc tensor sau `MaxPool1d`
đầu tiên (tương ứng split `s=2` ở tuần 4), không phải chế độ bảo vệ P2 của kế
hoạch nghiên cứu.

Tiêu chí số học: với **từng mẫu trong 20 mẫu**, P2 phải có
`max(abs(MCU − PyTorch)) < 1e-3` (dấu `<` nghiêm ngặt). Phiên bổ sung ngày
30/09/2026 thu thêm đủ năm mốc của cả 20 mẫu để lập bảng 20 × 5 theo hợp đồng
(mục 7).

SV3 sở hữu checkpoint, graph, input/golden, header tham số và provenance của
gói. SV1 kiểm gói, chuyển đoạn graph sang C, build/nạp dongle, thu và đối
chiếu tensor. Giao diện Device–Edge, ONNX/tail và phần việc của SV2 là quyết
định riêng, không được phép đo này xác nhận. Các gate chi tiết nằm trong
[hợp đồng bàn giao](../contracts/sv3_sv1_week3_model_handoff.md).

## 2. Phần cứng, công cụ và nguồn

- Dongle PCA10059 cắm trực tiếp vào cổng USB laptop khi nạp DFU và thu USB
  CDC. Nhấn SW2/RESET để vào bootloader USB DFU (LED đỏ sáng mờ dần).
- Tuần này **không dùng PPK2**, không có số liệu dòng điện hay năng lượng. Cách
  cấp nguồn 5,0 V của [tuần 2](sv1_device_week2_report.md) là phép đo khác;
  không cấp đồng thời hai nguồn.
- Target `nrf52840dongle/nrf52840`, NCS v3.4.0, Zephyr v4.4.0, West với
  `--no-sysbuild`, GNU Arm 14.3.0 từ Zephyr SDK 1.0.1. Phiên bản công cụ ghi
  trong [kiểm tra môi trường](../device/reports/environment_check.txt) và
  [biên bản build](../device/reports/week3_build.md).
- Build tuần 3 dùng `device/overlay-week3.conf`, thư mục `device/build-week3`
  và ZIP DFU riêng. Hai build hồi quy Active/Idle của tuần 1–2 đều PASS. Không
  dùng `west flash`, erase/recover, MCUboot và không sửa SB1/SB2.
- Ghi chú bổ sung ngày 15/10/2026 (kiểm lại `.config` và ELF đã nạp): overlay
  tuần 3 không bật `CONFIG_FPU`, nên image tuần 3 tính FP32 bằng thư viện số
  thực mềm (`__aeabi_fmul`, `__addsf3`). Tuần 4 bật FPU phần cứng; P2
  của hai image vẫn trùng từng bit (xem [báo cáo tuần 4](sv1_device_week4_report.md)).
  Tuần 3 không đo thời gian nên khác biệt này không ảnh hưởng số liệu đã báo cáo.

## 3. Tiếp nhận dữ liệu và gói của SV3

Snapshot MIT-BIH tuần 1 nằm ở `ml/data/raw/mitdb/` và
`ml/data/processed/mitdb/`. [Bằng chứng kiểm dữ liệu tuần 1](../ml/docs/week1_verification.md)
ghi đủ 48 record, 144 file `.hea/.dat/.atr`, `SHA256SUMS.txt` chính thức có
SHA-256 `b61158a96d5f2ca80edfb354a9a66a6324836c390a84e1966dcee2b907d6be43`,
SHA-256 cây file bắt buộc
`09d0f9c2cf19cbcfc8b704681ce388e62ec89832bfed59169e70ac9ea147e46f`, cùng chín
file train/val/test và processed manifest.

Processed manifest có hai giá trị hash theo hai chính sách khác nhau, không
thay thế cho nhau:

| Chính sách | SHA-256 |
|---|---|
| Text UTF-8 chuẩn hóa LF của repo | `f712c83d46d71ac6af75b7138668d8918eef87a4ddfeab8e8b5310ced2c44a3c` |
| Byte thô trên máy Windows hiện tại | `63bc21fa51e0e78ae0e3fcbf5aaf60cf5999733f4c861ba916aa26d18dfe6597` |

Chính sách hash nằm trong [quy trình dữ liệu](../ml/docs/week1_data_protocol.md)
và `ml/src/week1_common.py`.

Gói nhận là `mitdb-week3-fp32-20260925-v2`, gồm 29 file, không có file ngoài
manifest:

| Thành phần | Giá trị |
|---|---|
| ZIP ML (SHA-256) | `d5511f8c5ebfb1e9eced4aea2f8e89a20dd142b79987a40f6a3347d33d7481eb` |
| Trust anchor của `manifest.json` (SHA-256) | `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469` |
| Checkpoint (SHA-256) | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` |
| Source commit của gói | `8e98a0e4851abc979feb5fd5b97ece612b02cfaa` |

Các hash ZIP/manifest được đọc lại từ file khi lập báo cáo.
[Release SV3](../ml/docs/week3_release.md) và
[provenance v2](../ml/provenance/week3/mitdb-week3-fp32-20260925-v2.verification.json)
ghi thêm lịch sử bản v1 đã bị thay thế. JSON provenance được tạo trước phép đo
MCU, nên các trường `PENDING` trong đó là ảnh chụp lúc xuất gói, không phải
trạng thái thiết bị hiện tại.

SV1 chạy hai script kiểm gói của checkout đã review bằng
`ml/.venv/Scripts/python.exe -B`, với `--repo-root .`, `--package` trỏ tới gói
v2 và `--expected-manifest-sha256` như trên. `verify_week3.py` và
`test_week3.py` đều exit 0, in `HANDOFF_CHECKS_PASS`; **27/27 trường hợp phải
bị từ chối đều bị từ chối** và inventory 29 file không đổi. (Một lần chạy thử
trước đó thiếu `-B` đã tạo file `.pyc`; đó không phải lệnh nghiệm thu chính
thức.) PR [#11](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/11)
được merge vào `dev/device-sv1` tại `ff7f621706558083b4da5e583cb20268fb6d947e`.
Đây là **SV1 package acceptance PASS** — kiểm gói, chưa phải phép đo trên dongle.

## 4. Graph và cách đưa input vào firmware

[Quyết định freeze/boundary](../ml/configs/week3_model_freeze.json) và
`model/graph.json` của gói v2 khóa đoạn đầu: M0 `(1,1,360)` → M1/R1/M2/R2
`(1,16,360)` → P2 `(1,16,180)`, layout NCL (mẫu–kênh–chiều dài), kiểu `<f4`
(FP32 little-endian); hai lớp Conv kernel 5, padding 2, có bias; MaxPool1d
kernel/stride 2. M0 trong `inputs.npy` **đã chuẩn hóa** theo pipeline tuần 1,
nên firmware không chuẩn hóa lại và không chuyển sang INT8. Trường
`measurement_status` trong graph mô tả lúc xuất gói chưa có build/đo MCU; số đo
sau đó nằm trong biên bản thiết bị, không sửa ngược vào gói.

[`generate_week3_inputs.py`](../device/scripts/generate_week3_inputs.py) xác
thực manifest và inventory, rồi chuyển đúng 20 hàng `(20,1,360)` thành mảng
`static const float week3_inputs[20][360]` viết bằng literal hexadecimal FP32,
nên giữ nguyên từng bit. Mảng này được biên dịch vào image; firmware chọn
`week3_inputs[sample_index]` và dùng hai buffer activation tĩnh.
`sample_index` 0–19 ánh xạ theo thứ tự dòng `samples.csv` sang `sample_id` dạng
`MIT-BIH:105:<r_peak_sample>:MLII` (20 dòng thuộc split `val`, bệnh nhân P105).
Console chỉ in index; checker tra `samples.csv` đã xác thực để gắn ID, và JSON
kết quả giữ cả hai.

[`week3_head.c`](../device/src/week3_head.c) thực hiện Conv1/Conv2 bằng vòng
lặp C FP32, ReLU và MaxPool1d; [`main_week3.c`](../device/src/main_week3.c)
điều khiển USB CDC, marker, in bit FP32 và đo stack.
[`CMakeLists.txt`](../device/CMakeLists.txt) lấy trực tiếp
`firmware/head_parameters.h` của gói v2. Đây là kernel C của dự án, **không
phải** CMSIS-NN, X-CUBE-AI hay ONNX runtime. [Đặc tả I1](../contracts/i1_device_edge_packet_v1.md)
vẫn ghi model artifact/ONNX/TFLite/CMSIS-NN cho triển khai là `DEFERRED`, và
tài liệu trong repo không nhắc X-CUBE-AI. Nếu kế hoạch ngoài repo yêu cầu một
thư viện cụ thể, cần xin thầy xác nhận trước khi đổi cách triển khai.

## 5. Kiểm trên host và build firmware

[`verify_week3_host.py`](../device/scripts/verify_week3_host.py) biên dịch
chính kernel C đó trên máy tính và so mẫu 0 với golden v2:

| Mốc | Sai số tuyệt đối lớn nhất |
|---|---:|
| M1 | `2.384185791015625e-7` |
| R1 | `2.384185791015625e-7` |
| M2 | `9.5367431640625e-7` |
| R2 | `9.5367431640625e-7` |
| P2 | `4.76837158203125e-7` |

Kết quả `HOST_SAMPLE0: PASS`, lưu trong [JSON host](../device/reports/week3_host_sample0.json).

[`build_week3_head.ps1`](../device/scripts/build_week3_head.ps1) exit 0, tạo
HEX và ZIP DFU riêng. Theo linker Zephyr, image dùng **84.072 B Flash / 1020 KB**
(8,05%) và **64.248 B RAM / 256 KB** (24,51%); `size` cho text 82.484 B, data
1.584 B, bss 62.628 B. Hai buffer FP32 `16×360×4` chiếm tổng **46.080 B** RAM
tĩnh. Đây là kích thước image, khác với mức dùng stack đo lúc chạy ở mục 7.

| Hiện vật | SHA-256 |
|---|---|
| ZIP DFU `device/artifacts/adaptive_split_week3_fp32_v2.zip` | **`1862c97ad223573c4492d0a3c0de2d46b225f4c4573f1ce71c67aa4d65103f02`** |
| HEX | `ef5b03ae3b4e0fb7997a427e39e2313ece01cc712c8645acd10b98eaa25e0d24` |

Chi tiết trong [biên bản build/đo](../device/reports/week3_build.md). Bổ sung
ngày 15/10/2026: script build từ chối ghi đè `device/build-week3` và ZIP trên
(trước đó script xóa ZIP cũ khi build lại); build lại phải dùng
`-BuildDir`/`-DfuZipPath` mới.

## 6. Nạp DFU và xử lý lỗi USB CDC

Ở lần nạp cuối, cổng bootloader được xác định lại là `nRF52 SDFU USB (COM6)`,
VID:PID `1915:521F`; [`flash_week3_head.ps1`](../device/scripts/flash_week3_head.ps1)
báo `Device programmed` và `DFU succeeded (exit code 0)`. Sau khi nạp, ứng dụng
xuất hiện ở `USB Serial Device (COM7)`, VID:PID `2FE3:0004`, và in
`READY WEEK3 mitdb-week3-fp32-20260925-v2 P2 1x16x180`. COM6/COM7 chỉ là cổng
của phiên này; lần sau phải phát hiện lại.

Trước khi thu được dữ liệu, có hai lỗi USB CDC phải xử lý:

1. **Không gửi được lệnh xuống dongle.** Capture ban đầu chỉ dài 152 B, gồm
   boot banner và `READY`. Collector lỗi ngay ở `.Write("TRACE 0\n")` với
   `IOException: The semaphore timeout period has expired` và chưa nhận được
   `BEGIN 0 TRACE`. Lệnh ngắn `BAD\n` gửi bằng .NET `SerialPort` hay pyserial
   của NCS đều timeout. Đọc mã CDC ACM của NCS v3.4.0 cho thấy `uart_poll_in()`
   không tự khởi động lần nhận USB OUT đầu tiên. Sau khi firmware gọi
   `uart_irq_rx_enable()`, lệnh ngắn ghi xong trong 3 ms và nhận phản hồi
   `ERROR`, chứng tỏ cả hai chiều đã thông.
2. **Mất dữ liệu khi gửi tensor lớn lên máy tính.** `poll_out` bỏ byte khi FIFO
   truyền đầy nếu không bật flow control. Firmware bật cơ chế chờ FIFO qua
   `uart_configure()`; `RUN 0` hoàn tất, nhưng phiên thu dừng tại P2 của mẫu 10.
   Chạy riêng `RUN 10` và `RUN 11` vẫn dừng sau 168 dòng P2; pyserial đọc byte
   thô cũng dừng khoảng 24,6 KB ở `RUN 10`, nên lỗi không nằm ở `ReadLine` của
   PowerShell hay ở tổng lượng dữ liệu đã đọc. Khi nghỉ 5 ms sau mỗi dòng 16 giá
   trị, `RUN 10` nhận đủ `DONE 10` (26.383 B) và collector thu xong 20 mẫu.
   **Cơ chế treo TX bên trong NCS chưa được cô lập hoàn toàn**; cách khắc phục
   hiện tại là giới hạn tốc độ in.

Các lần thử, exit code và một lần probe báo sai do kỳ vọng CRLF quá chặt đều
ghi trong [biên bản thiết bị](../device/reports/week3_build.md). Lỗi thuộc
đường USB CDC của firmware, không do gói của SV3.

## 7. Thu và kiểm bit tensor

**Phiên lịch sử (28/09/2026).** [`collect_week3.ps1`](../device/scripts/collect_week3.ps1)
gửi `TRACE 0` rồi `RUN 1` đến `RUN 19`, đọc liên tục đến từng `DONE`, exit 0 và
in `Captured sample 0` đến `Captured sample 19`. Mẫu 0 có đủ M1/R1/M2/R2/P2;
các mẫu còn lại chỉ có P2. Firmware in **mọi phần tử** dưới dạng tám chữ số hex
của bit FP32, không làm tròn sang thập phân. P2 mỗi mẫu có 2.880 phần tử; mỗi
tensor M1/R1/M2/R2 có 5.760 phần tử.

[`check_week3_capture.py`](../device/scripts/check_week3_capture.py) xác thực
lại inventory v2, giải mã bit thành FP32, kiểm giá trị hữu hạn, số phần tử và
shape, đủ tập tensor, 20 cặp `BEGIN`/`DONE` đúng thứ tự, 20 dòng stack và ánh
xạ index/ID; sau đó so từng phần tử với golden cùng hàng. Capture lịch sử
`device/artifacts/week3_capture.txt` dài **732.924 B**, SHA-256
**`1e3825300731ac5804c605bb7c007457d8aeb5768e94dab9e16b6ca7503ee051`**; checker
exit 0 và [JSON kết quả lịch sử](../device/reports/week3_mcu_validation.json)
lưu hash capture cùng từng phép so P2.

`results/week3/device/` lưu bản sao [capture đã xác minh](../results/week3/device/logs/week3_capture_verified.txt),
[JSON so sánh](../results/week3/device/week3_mcu_validation.json) và
[biên bản build/đo](../results/week3/device/week3_build.md), trùng byte với bản gốc
trong `device/`. Phiên thu COM7 ngày 29/09 chỉ lặp lại P2, không thuộc capture
đã được checker xác nhận và không dùng làm căn cứ cho kết luận 20/20.

**Phiên bổ sung 20 × 5 (30/09/2026).** Collector chạy `-FullTrace`, xác nhận
banner trên COM7 rồi gửi `TRACE 0` đến `TRACE 19`, chỉ gửi mẫu tiếp theo sau khi
nhận đúng `DONE` của mẫu trước. [Capture mới](../results/week3/device/logs/week3_capture_20x5.txt)
dài **4.702.276 B**, SHA-256
**`72c7b6a2ba554f7e6d242a49e20065a4b56a3967108206a9a4d8845f1e795606`**.
Checker chế độ `20x5` (Python của `ml/.venv`) kiểm 100/100 tensor theo thứ tự
M1/R1/M2/R2/P2, 20 khung lệnh, 20 dòng stack, bit FP32, số phần tử/shape, giá
trị hữu hạn và ánh xạ sang `samples.csv`. Kết quả ở
[CSV sai số](../results/week3/device/week3_milestone_errors_20x5.csv) và
[JSON kiểm chứng](../results/week3/device/week3_mcu_validation_20x5.json). Mọi phép
trừ dùng float64 sau khi giải mã FP32. Phiên này không build hay nạp lại
firmware.

Lưu ý tái lập (bổ sung ngày 15/10/2026): hai capture tuần 3 được lưu LF trong
Git nhưng SHA-256 ở trên là của bản CRLF gốc. Trước đây hash chỉ khớp trên máy
đặt `core.autocrlf=true`; nay `.gitattributes` buộc checkout trả về CRLF
(`results/week3/device/logs/*.txt text eol=crlf`), nên hash khớp trên mọi máy.

## 8. Kết quả 20 mẫu trên MCU

Bảng P2 dưới đây thuộc **phiên lịch sử** `TRACE 0; RUN 1..19`; phiên này chưa
có bốn mốc trung gian của mẫu 1..19.

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

Sai số P2 lớn nhất của phiên lịch sử là **`7.152557373046875e-7`**, thấp hơn
ngưỡng `1e-3`; checker in **`MCU_20_OF_20: PASS`**. Mẫu 0 có M1
`2.384185791015625e-7`, R1 `2.384185791015625e-7`, M2 `9.5367431640625e-7`,
R2 `9.5367431640625e-7`, P2 `4.76837158203125e-7`. Với `CONFIG_INIT_STACKS=y`,
`k_thread_stack_space_get()` cho mức dùng stack lớn nhất của luồng main là
**544/4096 B**. Con số này không gồm stack của luồng khác hay ngắt, không phải
RAM linker và không liên quan năng lượng.

### Phiên bổ sung: đủ 20 mẫu × 5 mốc

Mỗi ô là `max(abs(MCU − PyTorch))` của đúng `sample_index` và mốc tương ứng,
đơn vị **× 10⁻⁷**, làm tròn để dễ đọc; [CSV](../results/week3/device/week3_milestone_errors_20x5.csv)
giữ giá trị float64 đầy đủ. P2 đạt khi sai số thực của **từng mẫu** `< 1e-3`.

| Index | `sample_id` | M1 | R1 | M2 | R2 | P2 | P2 đạt |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | :---: |
| 0 | MIT-BIH:105:197:MLII | 2.38418579 | 2.38418579 | 9.53674316 | 9.53674316 | 4.76837158 | PASS |
| 1 | MIT-BIH:105:459:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 2 | MIT-BIH:105:708:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 3 | MIT-BIH:105:965:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 7.15255737 | 7.15255737 | PASS |
| 4 | MIT-BIH:105:1222:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 4.76837158 | 4.76837158 | PASS |
| 5 | MIT-BIH:105:1479:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 6 | MIT-BIH:105:1741:MLII | 2.38418579 | 2.38418579 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 7 | MIT-BIH:105:2015:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 7.15255737 | 7.15255737 | PASS |
| 8 | MIT-BIH:105:2287:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 9 | MIT-BIH:105:2550:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 7.15255737 | 7.15255737 | PASS |
| 10 | MIT-BIH:105:2803:MLII | 4.76837158 | 4.76837158 | 5.96046448 | 5.96046448 | 5.96046448 | PASS |
| 11 | MIT-BIH:105:3052:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 4.76837158 | 4.76837158 | PASS |
| 12 | MIT-BIH:105:3303:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 3.57627869 | PASS |
| 13 | MIT-BIH:105:3563:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 7.15255737 | 4.76837158 | PASS |
| 14 | MIT-BIH:105:3835:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 7.15255737 | 4.76837158 | PASS |
| 15 | MIT-BIH:105:4102:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 16 | MIT-BIH:105:4371:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 17 | MIT-BIH:105:4635:MLII | 2.38418579 | 2.38418579 | 4.76837158 | 4.76837158 | 4.76837158 | PASS |
| 18 | MIT-BIH:105:4901:MLII | 4.76837158 | 4.76837158 | 7.15255737 | 7.15255737 | 4.76837158 | PASS |
| 19 | MIT-BIH:105:5154:MLII | 4.76837158 | 4.76837158 | 4.76837158 | 4.76837158 | 3.57627869 | PASS |
| **Max** | **20 mẫu** | **4.76837158** | **4.76837158** | **9.53674316** | **9.53674316** | **7.15255737** | **20/20** |

Giá trị max chính xác: M1/R1 `4.76837158203125e-7`, M2/R2 `9.5367431640625e-7`,
P2 `7.152557373046875e-7`. Checker báo **100/100 tensor hợp lệ** và
**P2 20/20 PASS**; mức dùng stack main lớn nhất vẫn là `544/4096 B`. Đây là
phép thu tensor mới trên dongle; số Flash `84072 B` và RAM linker `64248 B`
vẫn lấy từ [biên bản build trước đó](../results/week3/device/week3_build.md), không
phải số đo của một lần build lại ngày 30/09.

## 9. Revision và hiện vật bằng chứng

- Merge commit PR #11: `ff7f621706558083b4da5e583cb20268fb6d947e`.
- Firmware đã chạy trên thiết bị: `33a5288e475646c80f14a9cfcd2e797db64c5e41`;
  commit bổ sung hash firmware vào [biên bản kỹ thuật](../device/reports/week3_build.md):
  `f1624f43fc68ef1472005b9edb2b5fc450cb1443`.
- Trong Git: [lệnh build/DFU/capture](#13-phụ-lục-build-và-nạp-lại-firmware-tuần-3),
  [JSON host mẫu 0](../device/reports/week3_host_sample0.json),
  [JSON MCU 20 mẫu](../device/reports/week3_mcu_validation.json),
  [firmware tuần 3](../device/src/main_week3.c) và [kernel C](../device/src/week3_head.c).
- Phiên bổ sung 20 × 5: [capture USB CDC](../results/week3/device/logs/week3_capture_20x5.txt),
  [CSV sai số](../results/week3/device/week3_milestone_errors_20x5.csv) và
  [JSON xác minh](../results/week3/device/week3_mcu_validation_20x5.json).
- Ngoài Git (không `git add -f`): `device/artifacts/adaptive_split_week3_fp32_v2.zip`,
  `device/artifacts/week3_capture.txt`, các log chẩn đoán, `device/build-week3/`,
  `device/generated/`, ZIP ML và dữ liệu MIT-BIH. Kiểm một file bằng
  `Get-FileHash -Algorithm SHA256 -LiteralPath <đường-dẫn>` rồi đối chiếu với
  hash ở mục 3, 5 và 7 (đường dẫn tính từ repo root).

Báo cáo không chèn ảnh terminal của phiên COM7 lặp lại, vì ảnh chỉ cho thấy
tiến độ thu, không thể hiện phép so số học. Bằng chứng là bảng sai số, JSON và
capture đã xác minh.

## 10. Kiểm lại capture và chạy lại trên dongle

Kiểm lại **capture đã có**, không cần nạp lại. Từ repo root, trong PowerShell
sạch cho ML:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\results\week3\device\logs\week3_capture_verified.txt
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture results/week3/device/logs/week3_capture_verified.txt --mode legacy --report-output $env:TEMP/week3_legacy_recheck.json
```

Checker cần gói v2 và golden ở đúng vị trí local; `--report-output` ghi kết quả
ra ngoài, không đụng JSON lịch sử. Từ 15/10/2026, checker và collector từ chối
ghi đè file đã có, nên mỗi lần chạy cần tên file mới. Kiểm lại
**phiên bổ sung 20 × 5**:

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture results/week3/device/logs/week3_capture_20x5.txt --mode 20x5 --report-output $env:TEMP/week3_20x5_recheck.json --csv-output $env:TEMP/week3_20x5_recheck.csv --port COM7
```

Thu **một capture 20 × 5 mới** trên dongle đang chạy đúng firmware tuần 3: đóng
terminal đang giữ cổng CDC, tìm cổng ứng dụng hiện tại bằng
`[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object`, rồi chạy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week3.ps1 -Port COMy -FullTrace -Output .\device\artifacts\week3_capture_20x5_new.txt
```

Thay `COMy` bằng cổng vừa tìm, sau đó chạy checker chế độ `20x5` trên file mới.
Nếu cần nạp lại image, làm theo [phụ lục](#13-phụ-lục-build-và-nạp-lại-firmware-tuần-3): đóng
terminal, nhấn SW2, xác nhận LED đỏ sáng mờ dần, xác định **lại** cổng
bootloader rồi chạy `flash_week3_head.ps1 -Port COMx`, sau đó tìm lại cổng
ứng dụng. Không cố định COM6/COM7 và không dùng `west flash`.

## 11. Giới hạn và kết luận

P2 của đủ 20 mẫu **PASS** trên PCA10059 với gói v2 và firmware FP32 nêu trên.
Phiên bổ sung kiểm đủ 20 × 5 tensor thật trên dongle, hoàn tất bảng sai số theo
mục 6 của hợp đồng. Kết luận dựa trên capture đủ khung, bit FP32 và đối chiếu
golden đúng mẫu, không suy từ dòng `READY` hay thông báo DFU.

Phạm vi kết luận chỉ là đoạn đầu FP32 đến P2 trên 20 mẫu đã đo; đây là kiểm
tính đúng số học, không phải đánh giá accuracy phân loại. Chưa có số liệu
PPK2/năng lượng cho workload này. Phía SV2 vẫn `BLOCKED_ON_SV2_INTERFACE`;
chưa có bằng chứng tích hợp Edge/ONNX hay chạy bằng CMSIS-NN/X-CUBE-AI.

## 12. Chuyển sang tuần 4

P2 FP32 20/20, bảng sai số 20 × 5 và Flash/RAM của image là mốc tham chiếu cho
tuần 4. Theo [audit mô hình](../ml/docs/week3_audit.md), profiling các điểm cắt
thuộc tuần 4 và chưa làm trong phép đo này. Trước khi dùng P2 cho truyền
Device–Edge, các bên cần chốt profile giao diện I1/SV2; trạng thái hiện tại vẫn
là `BLOCKED_ON_SV2_INTERFACE`.

## 13. Phụ lục: build và nạp lại firmware tuần 3

Gộp từ hướng dẫn `device/week3_fp32_guide.md` cũ (đã xóa ngày 19/10/2026).

Gói đã nghiệm thu là `ml/artifacts/week3/mitdb-week3-fp32-20260925-v2`, `manifest.json`
SHA-256 `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`. Firmware dùng
`firmware/head_parameters.h` của gói và nhúng nguyên `inputs.npy` đã chuẩn hóa; không chuẩn
hóa lần hai, không chuyển INT8. Từ repo root, trong PowerShell không có `PYTHONHOME`/`PYTHONPATH` của NCS:

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& ml/.venv/Scripts/python.exe -B device/scripts/verify_week3_host.py --repo-root .
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week3_head.ps1
```

Script host biên dịch chính kernel C của Zephyr và so mẫu 0 ở M1, R1, M2, R2, P2 với golden v2.
Script build lặp lại phép kiểm đó, build pristine `nrf52840dongle/nrf52840` với
`overlay-week3.conf` và tạo `device/artifacts/adaptive_split_week3_fp32_v2.zip`; build ở
`device/build-week3`, hằng số input ở `device/generated`. Hai vị trí này giữ đúng image đã nạp và
đo nên script từ chối ghi đè. Build lại phải chọn đường dẫn mới, ví dụ
`-BuildDir D:\HUST\week3-rebuild\build -DfuZipPath D:\HUST\week3-rebuild\week3.zip`, rồi so HEX
SHA-256 với HEX đã nghiệm thu ở mục 5 trước khi nạp. Hash ZIP đổi mỗi lần đóng gói dù HEX giống
hệt (quan sát ngày 15/10/2026).

Nạp và thu một capture mới:

1. Đóng terminal đang giữ dongle; liệt kê cổng; nhấn RESET/SW2 (LED đỏ sáng mờ dần), liệt kê lại để
   tìm cổng bootloader mới xuất hiện.
2. Chỉ nạp ZIP tuần 3, không dùng `west flash`, erase, recover, MCUboot hay ZIP tuần 1:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week3_head.ps1 -Port COMx
   ```

3. Tìm lại cổng CDC của ứng dụng (có thể khác cổng bootloader), thu dấu vết đủ của mẫu 0 và P2 của
   19 mẫu còn lại, rồi kiểm:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\collect_week3.ps1 -Port COMy -Output .\device\artifacts\week3_capture_new.txt
   Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
   & ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture device/artifacts/week3_capture_new.txt --report-output $env:TEMP/week3_mcu_recheck.json
   ```

Collector gửi `TRACE 0` rồi `RUN 1`..`RUN 19`, đọc liên tục tới từng `DONE`; firmware in mỗi phần
tử FP32 bằng 8 chữ số hex, nghỉ 5 ms sau mỗi dòng 16 phần tử để USB CDC kịp thoát dữ liệu. Checker
in `MCU_20_OF_20: PASS` chỉ khi cả 20 sai số P2 nhỏ hơn hẳn `1e-3`. Collector và checker từ chối
ghi đè file đã có, nên mỗi lần chạy cần tên file mới.
