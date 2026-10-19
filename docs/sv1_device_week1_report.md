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

## 10. Phụ lục: nạp DFU và chạy demo Active trên dongle

Gộp từ hướng dẫn `device/week1_dfu_demo_guide.md` cũ (đã xóa ngày 19/10/2026).

1. Đóng Serial Monitor đang mở, cắm PCA10059 vào USB, nhấn **RESET/SW2** (nút ở
   cạnh xa đầu USB, đẩy từ ngoài vào phía đầu USB). LED đỏ sáng mờ dần là Nordic
   USB bootloader đang chạy. Không giữ SW1, không dùng MCUboot, `west flash`,
   `erase` hay `recover`.
2. Liệt kê cổng trước và sau khi nhấn RESET; cổng mới xuất hiện là bootloader:

   ```powershell
   [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
   ```

3. Nạp gói `device\artifacts\adaptive_split_week1_demo.zip` (tạo bằng
   `build_week1_demo.ps1` ở mục 4 nếu chưa có); thành công khi lệnh in
   `DFU succeeded (exit code 0)`:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week1_demo.ps1 -Port COMx
   ```

4. Sau DFU, liệt kê lại cổng: cổng USB CDC của ứng dụng có thể mang số khác cổng
   bootloader. Mở monitor (115200 baud, `Ctrl+]` để thoát). Mỗi lần mở (DTR bật),
   firmware in banner và chạy lại benchmark; sau đó cứ khoảng 5 s in một dòng `STATUS`:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\monitor_week1_demo.ps1 -Port COMy
   ```

   ```text
   ADAPTIVE SPLIT INFERENCE - SV1 WEEK 1 + WEEK 2 MARKERS
   Board: nRF52840 Dongle PCA10059
   CPU: 64 MHz
   USB CDC: READY
   LED heartbeat: RUNNING
   GPIO marker self-test: RUNNING
   GPIO marker self-test: <HEAD|PROTECTION|TX|WAIT> ON
   DWT benchmark: START
   Warm-up runs: 20; measured runs: 20; iterations/run: 10000
   Run 01: ... cycles
   ...
   Run 20: ... cycles
   Min: ... cycles
   Max: ... cycles
   Average: ....... cycles
   Deviation: 0....%
   RESULT: PASS
   ```

Checklist bằng chứng: LED xanh heartbeat chu kỳ khoảng 1 s; banner đúng board và
`USB CDC: READY`; có trạng thái marker self-test (D0–D3 lần lượt chuyển mức nếu
đang quan sát); đủ `Run 01`–`Run 20` sau 20 warm-up; deviation < 1,000 % và log tự
in `RESULT: PASS` (từ 1,000 % trở lên in `RESULT: FAIL`); script build kết thúc bằng
`RESULT: PASS (build + DFU package)`.

Nếu không thấy cổng ứng dụng: chờ 5 s rồi liệt kê lại và xem Device Manager mục
**Ports (COM & LPT)**; cắm thẳng vào cổng USB khác, tránh hub; nếu LED đỏ vẫn sáng
mờ thì thiết bị còn ở bootloader, chạy lại DFU và kiểm exit code; nếu LED xanh nhấp
nháy mà chưa có cổng, đóng chương trình đang giữ cổng rồi rút/cắm lại.
