# Báo cáo công việc Week 1 – firmware nRF52840 Dongle

## 1. Mục tiêu Week 1

Week 1 xây dựng nền tảng firmware cho thiết bị đầu cuối SV1 trên Nordic
nRF52840 Dongle PCA10059. Mục tiêu kỹ thuật là xác nhận môi trường Zephyr,
khả năng build/DFU, kênh log USB CDC và phép đo chu kỳ CPU bằng bộ đếm DWT.

## 2. Phần cứng và môi trường phát triển

- Phần cứng: Nordic nRF52840 Dongle PCA10059 revision 2.1.1.
- SDK: nRF Connect SDK v3.4.0 LTS, chứa Zephyr 4.4.0.
- Board target: `nrf52840dongle/nrf52840`; không dùng biến thể `/bare`.
- Toolchain đã ghi nhận: West 1.5.0, CMake 4.2.1, Ninja 1.13.2 và GNU Arm
  14.3.0 từ Zephyr SDK 1.0.1.
- Hệ thống kiểm tra được ghi nhận là Windows 11; các script build hiện đặt
  đường dẫn mặc định đến `D:\ncs\v3.4.0` và toolchain tương ứng, nhưng cho phép
  truyền lại hai tham số đường dẫn.

Các thông tin môi trường trên có bằng chứng trong
[`device/reports/environment_check.txt`](../device/reports/environment_check.txt)
và script kiểm tra môi trường.

## 3. Công việc đã triển khai

Firmware Active hiện thực các chức năng chính sau:

- LED xanh `led0` heartbeat với chu kỳ đầy đủ khoảng một giây.
- USB CDC ACM làm virtual COM; UART0 vật lý bị tắt trong devicetree overlay.
- Theo dõi DTR không chặn; benchmark chạy khi terminal được kết nối.
- Dùng DWT `CYCCNT` để đo số chu kỳ của workload vòng lặp rỗng.
- In min, max, trung bình, độ lệch và kết quả PASS/FAIL.
- Đóng/mở terminal có thể kích hoạt lại benchmark; khi kết nối được giữ,
  firmware in trạng thái mỗi năm giây.

Sau Week 1, firmware Active được bổ sung GPIO marker Week 2. Thay đổi này giữ
nguyên benchmark và đường build Active mặc định nhưng làm kích thước binary
hiện tại khác số liệu Week 1 lịch sử.

## 4. Quy trình build và DFU

Từ Git root, build pristine và tạo gói DFU bằng:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week1_demo.ps1
```

Script chọn đúng target, gọi West với `--no-sysbuild`, kiểm tra HEX/ELF rồi
tạo `device/artifacts/adaptive_split_week1_demo.zip` bằng `nrfutil
nrf5sdk-tools pkg generate`. Gói DFU là application version 1, hardware
version 52, `sd-req=0x00` và không ký. Đây là artifact demo cho bootloader USB
của dongle, không phải gói phát hành production.

Nạp firmware là thao tác riêng, chỉ được thực hiện khi người dùng chủ động
chọn cổng bootloader:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week1_demo.ps1 -Port COMx
```

Không có thao tác flash trong quá trình lập báo cáo này.

## 5. Phương pháp kiểm thử DWT

Firmware bật `CoreDebug->DEMCR.TRCENA`, reset/bật `DWT->CYCCNT` và kiểm tra bộ
đếm hoạt động. Benchmark thực hiện:

- 20 lần warm-up;
- 20 lần đo chính thức;
- 10.000 iteration cho mỗi lần;
- workload là vòng lặp NOP có compiler barrier và biến `volatile`;
- khóa interrupt chỉ trong từng khoảng đo ngắn;
- lưu 20 kết quả trong mảng tĩnh và tính thống kê fixed-point.

Kết quả chỉ PASS khi độ lệch `(max - min) / average` nhỏ hơn 1%.

## 6. Kết quả

Báo cáo hoàn thiện Week 1 ghi nhận build pristine exit code 0, không có lỗi
compiler/linker/devicetree/Kconfig, với:

- Flash: 47.736 B trên 1.020 KB (4,57%);
- RAM: 18.168 B trên 256 KB (6,93%);
- application payload trong gói DFU: 47.736 B.

Đây là **số liệu ghi nhận trong quá trình thử nghiệm Week 1** tại thời điểm
2026-09-11, trước khi source Active được bổ sung đầy đủ marker Week 2. Báo cáo
lịch sử cũng xác nhận `nrfutil pkg display` đọc được một image application và
kiểm tra CRC.

Khi kiểm tra lại source hiện tại bằng chính `build_week1_demo.ps1`, build
Active vẫn PASS nhưng có Flash 49.244 B và RAM 18.296 B do đã bao gồm phần mở
rộng marker Week 2. Hai bộ số liệu vì vậy phản ánh hai thời điểm source khác
nhau, không phải hai kết quả mâu thuẫn.

Tại thời điểm kết thúc Week 1, việc xác nhận LED, USB enumeration và kết quả
DWT trên dongle thật vẫn được ghi là bước cần thực hiện. Vì vậy báo cáo không
suy diễn thêm kết quả runtime ngoài bằng chứng hiện có.

## 7. File và script liên quan

- [`device/src/main.c`](../device/src/main.c): firmware Active và benchmark.
- [`device/prj.conf`](../device/prj.conf): GPIO, USB CDC và DWT.
- [`device/app.overlay`](../device/app.overlay): chọn USB CDC console, tắt
  UART0 vật lý.
- [`device/scripts/build_week1_demo.ps1`](../device/scripts/build_week1_demo.ps1):
  build và đóng gói DFU.
- [`device/scripts/flash_week1_demo.ps1`](../device/scripts/flash_week1_demo.ps1):
  DFU có tham số cổng rõ ràng.
- [`device/reports/WEEK1_CODE_COMPLETION.md`](../device/reports/WEEK1_CODE_COMPLETION.md):
  hồ sơ kỹ thuật chi tiết tại thời điểm hoàn thành Week 1.

## 8. Hạn chế và lưu ý

- Benchmark vòng lặp rỗng chỉ kiểm tra cơ chế đo DWT, chưa đại diện cho DNN
  inference thực tế.
- Ngưỡng ổn định chịu ảnh hưởng của interrupt và trạng thái hệ thống.
- USB CDC và LED làm tăng hoạt động ngoại vi; cấu hình này không dùng để đo
  dòng nền tối thiểu.
- Gói DFU không ký và chỉ phù hợp quy trình demo hiện tại.
- Đường dẫn NCS/toolchain mặc định trong PowerShell script mang tính cục bộ.

## 9. Kết luận Week 1

Week 1 đã tạo được project Zephyr có thể build cho đúng PCA10059, kênh USB CDC,
heartbeat, phép đo DWT và quy trình tạo gói DFU tách khỏi bước flash. Các thành
phần này là nền tảng để quan sát hoạt động và đo năng lượng ở Week 2.

## 10. Hướng phát triển sang Week 2

- Bổ sung bốn GPIO marker cho các pha HEAD, PROTECTION, TX và WAIT.
- Xây dựng firmware Idle riêng để đo dòng nền mà không làm mất cấu hình Active.
- Thu dữ liệu PPK2 đồng bộ dòng và logic marker.
- Lưu raw cục bộ, sinh summary/hình bằng script tái lập và chỉ đưa kết quả đã
  xử lý lên Git.
