# Hướng dẫn USB DFU và chạy demo Active SV1 trên PCA10059

## 1. Vào USB DFU bootloader

1. Đóng Serial Monitor nếu đang mở.
2. Cắm nRF52840 Dongle PCA10059 vào USB.
3. Nhấn nút **RESET/SW2** ở cạnh xa đầu USB; đẩy nút từ ngoài vào phía đầu USB.
4. Xác nhận LED đỏ chạy hiệu ứng sáng mờ dần: Nordic USB bootloader đang chạy.

Không giữ SW1 và không dùng quy trình MCUboot. Không dùng `west flash`,
`erase` hoặc `recover`.

## 2. Tìm cổng COM của bootloader

Chạy trước và sau khi nhấn RESET; cổng mới xuất hiện là cổng bootloader:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
```

## 3. Nạp firmware bằng script DFU

Từ thư mục gốc của repository, nhập cổng bootloader vừa tìm rồi chạy script:

```powershell
$BootloaderPort = Read-Host 'Cổng COM của bootloader'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week1_demo.ps1 -Port $BootloaderPort
```

Script chỉ gọi `nrfutil nrf5sdk-tools dfu usb-serial` với gói
`device\artifacts\adaptive_split_week1_demo.zip`. Thành công khi lệnh kết
thúc bằng `DFU succeeded (exit code 0)`.

Nếu gói ZIP chưa tồn tại, tạo lại từ thư mục gốc trước khi nạp:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week1_demo.ps1
```

## 4. Tìm lại cổng COM của firmware

Sau DFU, chờ Windows nhận lại thiết bị rồi chạy:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
```

Cổng ứng dụng USB CDC có thể mang số COM khác cổng bootloader. Không tái sử
dụng số cổng cũ nếu chưa kiểm tra.

## 5. Mở Serial Monitor

Nhập cổng ứng dụng vừa tìm; không dùng lại cổng bootloader nếu Windows đã gán
một số COM khác:

```powershell
$ApplicationPort = Read-Host 'Cổng COM của ứng dụng USB CDC'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\monitor_week1_demo.ps1 -Port $ApplicationPort
```

Baud rate mặc định là 115200. Nhấn `Ctrl+]` để thoát. Khi DTR được bật,
firmware in banner và chạy benchmark; đóng rồi mở lại monitor sẽ chạy lại.

Log dự kiến:

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

`RESULT: PASS` chỉ xuất hiện khi deviation thực tế nhỏ hơn 1.000%. Nếu từ
1.000% trở lên, firmware in `RESULT: FAIL`. Sau đó cứ khoảng 5 giây có dòng
`STATUS` để mở monitor muộn vẫn có nội dung trình diễn.

## Checklist bằng chứng

- [ ] LED xanh heartbeat liên tục, một chu kỳ bật/tắt khoảng 1 giây.
- [ ] Có banner đúng board PCA10059 và USB CDC READY.
- [ ] Có trạng thái GPIO marker self-test; nếu đang quan sát D0–D3, các marker
      HEAD, PROTECTION, TX và WAIT lần lượt chuyển mức.
- [ ] Có đủ `Run 01` đến `Run 20` sau 20 warm-up.
- [ ] Deviation nhỏ hơn 1.000% và log tự in `RESULT: PASS`.
- [ ] Script build kết thúc bằng `RESULT: PASS (build + DFU package)`.

Số liệu Week 1 lịch sử 47,736 B Flash và 18,168 B RAM được giữ trong
[báo cáo SV1/Device Week 1](../docs/sv1_device_week1_report.md). Source Active
hiện có thêm marker Week 2 nên kích thước build có thể khác; dùng báo cáo linker
của lần build hiện tại làm kết quả kiểm tra.

## Nếu không thấy COM ứng dụng

1. Chờ 5 giây, chạy lại lệnh liệt kê COM và kiểm tra Device Manager mục
   **Ports (COM & LPT)**.
2. Rút/cắm lại dongle trực tiếp vào cổng USB khác, tránh hub và kiểm tra cáp/
   đầu nối.
3. Nếu LED đỏ vẫn fade, thiết bị còn ở bootloader: chạy lại đúng lệnh DFU và
   kiểm tra exit code.
4. Nếu LED xanh heartbeat nhưng chưa thấy COM, đóng chương trình đang giữ COM,
   rút/cắm lại và kiểm tra lại Device Manager.
5. Không dùng `west flash`, không erase/recover và không ghi đè bootloader.
