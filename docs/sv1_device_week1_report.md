# Báo cáo SV1 tuần 1 — nền tảng firmware cho nRF52840 Dongle

## 1. Mục tiêu

Tuần 1 dựng nền firmware cho thiết bị đầu cuối của SV1 là Nordic nRF52840
Dongle PCA10059. Bốn việc cần làm được:

1. build đúng target của dongle bằng Zephyr trong nRF Connect SDK;
2. tạo gói USB DFU để nạp qua bootloader có sẵn trên dongle;
3. có kênh log qua USB CDC (cổng COM ảo trên máy tính);
4. đo được số chu kỳ CPU bằng bộ đếm DWT, làm cơ sở cho các phép đo thời gian
   ở các tuần sau.

## 2. Phần cứng và môi trường

- Phần cứng: Nordic nRF52840 Dongle PCA10059 revision 2.1.1.
- SDK: nRF Connect SDK v3.4.0 LTS, chứa Zephyr 4.4.0.
- Board target: `nrf52840dongle/nrf52840`; không dùng biến thể `/bare`.
- Công cụ: West 1.5.0, CMake 4.2.1, Ninja 1.13.2, GNU Arm 14.3.0 từ Zephyr
  SDK 1.0.1, chạy trên Windows 11.
- Script build mặc định trỏ tới `D:\ncs\v3.4.0` và toolchain tương ứng; hai
  đường dẫn này truyền lại được qua tham số khi dùng máy khác.

Phiên bản công cụ được ghi trong
[`device/reports/environment_check.txt`](../device/reports/environment_check.txt),
do script kiểm tra môi trường tạo ra.

## 3. Firmware đã viết

Firmware Active ([`device/src/main.c`](../device/src/main.c)) gồm:

- LED xanh `led0` nhấp nháy với chu kỳ khoảng 1 giây (heartbeat);
- console USB CDC ACM; UART0 vật lý bị tắt trong devicetree overlay để log
  không thể rơi sang UART;
- theo dõi tín hiệu DTR mà không chặn vòng lặp chính: khi terminal mở, firmware
  in banner và chạy benchmark; khi terminal vẫn mở, firmware in trạng thái mỗi
  5 giây; đóng rồi mở lại terminal thì benchmark chạy lại;
- benchmark vòng lặp rỗng bằng DWT, in min, max, trung bình, độ lệch và
  `PASS`/`FAIL`.

Sang tuần 2, firmware Active được bổ sung bốn GPIO marker. Benchmark và cách
build không đổi, nhưng kích thước image thay đổi (mục 6).

## 4. Build và nạp DFU

Từ Git root, build pristine và tạo gói DFU:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week1_demo.ps1
```

Script chọn đúng target, gọi West với `--no-sysbuild`, kiểm tra HEX/ELF rồi
dùng `nrfutil nrf5sdk-tools pkg generate` tạo
`device/artifacts/adaptive_split_week1_demo.zip`: application version 1,
hardware version 52, `sd-req=0x00`, không ký. Đây là gói demo cho bootloader
USB của dongle, không phải gói phát hành.

Nạp firmware là bước riêng, chỉ chạy khi chủ động chọn cổng bootloader:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week1_demo.ps1 -Port COMx
```

Khi lập báo cáo không có thao tác nạp nào.

## 5. Cách đo bằng DWT

DWT (Data Watchpoint and Trace) là khối debug của lõi Cortex-M4; thanh ghi
`CYCCNT` của nó đếm số chu kỳ xung nhịp CPU. Firmware bật `TRCENA` trong
`CoreDebug->DEMCR`, đặt `CYCCNT` về 0, bật bộ đếm rồi kiểm tra bộ đếm thực
sự tăng. Benchmark gồm:

- 20 lần warm-up (chạy làm nóng, không lấy số);
- 20 lần đo chính thức, mỗi lần 10.000 vòng lặp NOP có compiler barrier và
  biến `volatile` để compiler không bỏ vòng lặp;
- khóa ngắt trong từng lần đo để ngắt không chen vào khoảng đo;
- lưu 20 kết quả vào mảng tĩnh, tính thống kê bằng số nguyên fixed-point.

Kết quả `PASS` khi `(max − min) / trung bình < 1%`.

## 6. Kết quả

Hồ sơ hoàn thành tuần 1
([`WEEK1_CODE_COMPLETION.md`](../device/reports/WEEK1_CODE_COMPLETION.md))
ghi build pristine exit code 0, không lỗi compiler/linker/devicetree/Kconfig:

| Hạng mục | Kết quả ngày 2026-09-11 |
|---|---|
| Flash | 47.736 B / 1.020 KB (4,57%) |
| RAM | 18.168 B / 256 KB (6,93%) |
| Application payload trong gói DFU | 47.736 B |

`nrfutil pkg display` đọc được một image application và kiểm tra CRC của gói.

Build lại source hiện tại bằng chính `build_week1_demo.ps1` vẫn PASS, với
Flash 49.244 B và RAM 18.296 B vì source đã có thêm marker tuần 2. Hai bộ số
này thuộc hai thời điểm source khác nhau, không mâu thuẫn.

Phần chạy trên dongle thật — LED heartbeat, Windows nhận cổng USB CDC và 20
số đo DWT kèm độ lệch — được hồ sơ tuần 1 ghi là bước còn phải làm. Sang tuần
2, firmware Active đã chạy trên dongle và được quan sát bằng PPK2 (chu kỳ và
marker), nhưng repository chưa lưu log benchmark DWT in ra từ dongle. Vì vậy
báo cáo không đưa ra số đo DWT thực tế.

## 7. File liên quan

- [`device/src/main.c`](../device/src/main.c): firmware Active và benchmark.
- [`device/prj.conf`](../device/prj.conf): GPIO, USB CDC và DWT.
- [`device/app.overlay`](../device/app.overlay): chọn USB CDC làm console,
  tắt UART0.
- [`device/scripts/build_week1_demo.ps1`](../device/scripts/build_week1_demo.ps1):
  build và đóng gói DFU.
- [`device/scripts/flash_week1_demo.ps1`](../device/scripts/flash_week1_demo.ps1):
  nạp DFU với cổng được chỉ định rõ.
- [`device/reports/WEEK1_CODE_COMPLETION.md`](../device/reports/WEEK1_CODE_COMPLETION.md):
  hồ sơ kỹ thuật chi tiết lúc hoàn thành tuần 1.

## 8. Hạn chế

- Vòng lặp rỗng chỉ kiểm tra cơ chế đếm chu kỳ, chưa đại diện cho suy luận DNN.
- Độ ổn định của phép đo phụ thuộc trạng thái hệ thống lúc đo; ngưỡng 1% chỉ
  là tiêu chí kiểm tra cơ chế đo, không phải yêu cầu của bài toán.
- USB CDC và LED làm ngoại vi hoạt động thêm, nên cấu hình Active không dùng
  để đo dòng nền tối thiểu.
- Gói DFU không ký, chỉ dùng cho quy trình demo.
- Đường dẫn NCS/toolchain mặc định trong script là đường dẫn của máy hiện tại.

## 9. Kết luận và việc tiếp theo

Tuần 1 đã có project Zephyr build đúng cho PCA10059, kênh USB CDC, heartbeat,
benchmark DWT và quy trình tạo gói DFU tách khỏi bước nạp. Kết quả chạy trên
dongle chưa được ghi lại trong tuần này.

Tuần 2 sẽ:

- thêm bốn GPIO marker cho các pha HEAD, PROTECTION, TX và WAIT;
- tạo firmware Idle riêng để đo dòng nền mà không mất cấu hình Active;
- đo dòng bằng PPK2, đồng bộ dòng điện với tín hiệu marker;
- giữ dữ liệu raw ở máy cục bộ, sinh summary/hình bằng script tái lập và chỉ
  đưa kết quả đã xử lý lên Git.
