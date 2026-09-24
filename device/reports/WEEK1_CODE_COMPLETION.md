# Báo cáo hoàn thiện code SV1 Tuần 1

Thời điểm kiểm tra: 2026-09-11 (Asia/Saigon)

## Phạm vi và file

Đã sửa:

- `device/src/main.c`
- `device/prj.conf`
- `device/README.md`

Đã tạo:

- `device/app.overlay`
- `device/scripts/build_week1_demo.ps1`
- `device/scripts/flash_week1_demo.ps1`
- `device/scripts/monitor_week1_demo.ps1`
- `device/week1_dfu_demo_guide.md`
- `device/reports/WEEK1_CODE_COMPLETION.md`

Đã đọc/kiểm tra nhưng không cần sửa: `device/CMakeLists.txt`, `.gitignore`,
các báo cáo môi trường, script môi trường, board DTS và sample USB CDC ACM trong
NCS v3.4.0. Không sửa phần `edge`, `ml`, `contracts`, PPK2 hay Tuần 2.
Hai gói base cũ trong `device/artifacts` được giữ nguyên.

## Firmware

- LED heartbeat lấy chân từ devicetree alias `led0`, toggle mỗi 500 ms
  (chu kỳ đầy đủ khoảng 1 giây), vẫn chạy khi chưa mở terminal.
- Console là node `board_cdc_acm_uart` của PCA10059 qua USB CDC ACM; UART0
  vật lý bị disable trong overlay.
- Dùng USB device stack mới đúng sample NCS v3.4.0:
  `CONFIG_USB_DEVICE_STACK_NEXT=y` và
  `CONFIG_CDC_ACM_SERIAL_INITIALIZE_AT_BOOT=y`.
- Theo dõi DTR không chặn; khi terminal chuyển sang connected, firmware chờ
  100 ms, in banner và chạy benchmark. Đóng/mở lại terminal sẽ chạy lại.
- DWT bật bằng `CoreDebug->DEMCR.TRCENA`, reset/bật `DWT->CYCCNT`; phép đo
  không dùng uptime/tick. Interrupt chỉ bị khóa trong từng đoạn đo ngắn.
- Vòng lặp benchmark dùng NOP/compiler barrier, function pointer, biến
  `volatile`; có 20 warm-up và đúng 20 mẫu trong mảng `static volatile`.
- Tính min/max/sum bằng số nguyên, average và
  `(max-min)/average*100` ở fixed-point 3 chữ số. PASS chỉ khi deviation
  thực tế nhỏ hơn 1.000%.
- Sau benchmark, LED tiếp tục chạy và trạng thái được in lại mỗi 5 giây.
- Không có cấp phát động trong source ứng dụng.

## Target và build

- Board thật: Nordic nRF52840 USB Dongle PCA10059 revision 2.1.1.
- Target: `nrf52840dongle/nrf52840`.
- Không dùng target `/bare`; không có cấu hình DK/PCA10056.
- SDK: `D:\ncs\v3.4.0` (NCS v3.4.0 LTS, Zephyr 4.4.0).
- Build directory: `D:\HUST\Adaptive_Split_Inference\device\build`.

Lệnh build thực tế do script chạy:

```powershell
west build --no-sysbuild -p always -b nrf52840dongle/nrf52840 -d D:\HUST\Adaptive_Split_Inference\device\build D:\HUST\Adaptive_Split_Inference\device
```

`--no-sysbuild` chỉ áp dụng cho lệnh này vì cấu hình West cục bộ mặc định
bật sysbuild, nhằm giữ output tại `build\zephyr`.

Kết quả build pristine cuối:

- Exit code: **0**
- Compiler/linker/devicetree/Kconfig error: **không có**
- Flash: **47,736 B / 1,020 KB (4.57%)**
- RAM: **18,168 B / 256 KB (6.93%)**
- IDT_LIST: **0 B / 32 KB (0.00%)**

## Artifact

HEX:

- Path: `D:\HUST\Adaptive_Split_Inference\device\build\zephyr\zephyr.hex`
- File size: **134,394 bytes**
- SHA-256: `5F0B8FEF0C30F501305D599A0DF1EF371644303785FF5BCF1633F4A207E4D8A4`
- Intel HEX bắt đầu tại địa chỉ `0x1000`, phù hợp layout bootloader tích hợp
  của target PCA10059.

DFU ZIP:

- Path: `D:\HUST\Adaptive_Split_Inference\device\artifacts\adaptive_split_week1_demo.zip`
- File size: **48,265 bytes**
- SHA-256: `3FDFCBCFC6E17814C878D4B678F95809064C1C38E9D29754A06312A519E64FDA`
- `nrfutil pkg display`: 1 image loại application, app size 47,736 B,
  application version 1, hardware version 52, `sd_req=0x00`, CRC boot
  validation.
- Gói không ký, đúng với bootloader Nordic signature-less của dongle cho demo;
  không phải gói phát hành production.

## Kiểm tra tĩnh và hậu build

- `CMakeCache.txt` và `build_info.yml` xác nhận
  `nrf52840dongle/nrf52840` và đúng board DTS của dongle.
- Devicetree sinh ra chọn `board_cdc_acm_uart`, class
  `zephyr,cdc-acm-uart`, UDC enabled và UART0 disabled.
- Kconfig sinh ra xác nhận GPIO, SERIAL, CONSOLE, UART_LINE_CTRL,
  USB_DEVICE_STACK_NEXT, CDC auto-init và CORTEX_M_DWT đều bật.
- ELF chứa banner, PCA10059, USB CDC READY, 20-run format, deviation,
  RESULT và status định kỳ.
- Source audit xác nhận function pointer, `static inline`, DWT CYCCNT,
  20 warm-up, 20 measurement, mảng tĩnh/volatile và ngưỡng PASS động.
- Cả ba script PowerShell đã qua parser không lỗi.
- `.gitignore` loại `device/build` và `device/artifacts/*.zip`; build
  output và DFU ZIP không được stage/commit.
- `nrfutil nrf5sdk-tools pkg display` đọc gói thành công.
- Không chạy `west flash`, erase, recover hay thao tác ghi dongle.

## Git

- Git root: `D:\HUST\Adaptive_Split_Inference`.
- Branch: `dev/device-sv1`.
- Git identity đã có sẵn; local commit dùng message
  `feat(device): complete week 1 PCA10059 demo firmware`.
- Chỉ source/config/script/docs/report của nhiệm vụ được stage; build và
  artifact không được commit. Không tạo remote và không push.

## Bắt buộc chờ board thật

Chưa được phép tuyên bố “Tuần 1 hoàn thành hoàn toàn” cho tới khi thực hiện
trên PCA10059 thật:

1. Vào Nordic USB DFU bootloader và nạp ZIP qua cổng bootloader.
2. Xác nhận LED xanh heartbeat thực tế.
3. Xác nhận Windows enumerate cổng USB CDC ứng dụng.
4. Mở terminal, thu đủ 20 số đo DWT, kiểm tra deviation thực tế và
   `RESULT: PASS/FAIL`.

Không có thao tác nạp board trong phiên hoàn thiện code này.
