# Runbook trên dongle — nghiệm thu tuần 6

Dành cho buổi chạy trên nRF52840 Dongle (PCA10059) với laptop Windows làm BLE central.
Thứ tự bắt buộc theo [kế hoạch tuần 6](../../docs/week6_device_edge_plan.md): self-test P1 →
loopback request thường → negative → nonce (tiêu chí 7) → mới tới packet I2/1 (MTU 23 và 1000
packet chính thức). Mỗi bước ghi vào một thư mục **mới**; công cụ từ chối ghi đè.

Thời gian dự kiến khoảng 1,5–2 giờ. Thao tác tay: **3 lần nhấn RESET** (3 lần DFU) và
**12 lần rút/cắm USB** (bước 7).

## 0. Chuẩn bị (một lần, trước khi cắm dongle)

Mở PowerShell ở Git root `D:\HUST\Adaptive_Split_Inference`:

```powershell
$Py  = "device\host\.venv\Scripts\python.exe"
$Lab = "device\scripts\week6_lab.py"
$Chk = "device\scripts\check_week6.py"
$S   = "D:\HUST\ASI_week6\device-session-20261019"      # thư mục phiên, mỗi bước một thư mục con
$Key = "D:\HUST\ASI_week6\secrets\bench_key_65537.bin"   # key bench, ngoài repo, key_check 4379e570eb84f891
$BuildDefault = "D:\HUST\ASI_week6\20261019-r1-default" # build từ commit sạch (xem build_id trong source.json)
$BuildMtu23   = "D:\HUST\ASI_week6\20261019-r1-mtu23"
```

- Bật Bluetooth của Windows; để laptop gần dongle. Không pair dongle trong Settings.
- Nếu đã sửa code sau khi build: build lại cả hai biến thể vào thư mục mới bằng
  `device\scripts\build_week6.ps1` (cây làm việc phải sạch để `build_id` không có `-dirty`),
  và đổi `$BuildDefault`/`$BuildMtu23`.
- Liệt kê cổng COM bất cứ lúc nào:

```powershell
& $Py -c "from serial.tools import list_ports; [print(p.device, f'{p.vid or 0:04X}:{p.pid or 0:04X}', p.description) for p in list_ports.comports()]"
```

  Bootloader DFU là `1915:521F` ("nRF52 SDFU USB"); ứng dụng tuần 6 là `2FE3:0004`
  ("Adaptive Split Inference SV1"). Số COM chỉ đúng trong phiên đó.

## 1. Nạp bản `default` (RESET lần 1)

Cắm dongle, nhấn nút RESET (SW2) — đèn đỏ thở chậm là bootloader. Dò cổng `1915:521F` rồi:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week6.ps1 -Port COMx -ReportDir $BuildDefault -ReceiptDir "$S\dfu"
```

Kỳ vọng: `DFU completed (default)`; sau vài giây cổng `2FE3:0004` xuất hiện.

## 2. Self-test trên MCU — tiêu chí 1, 2 và DWT của tiêu chí 8

```powershell
& $Py -B $Lab selftest --out "$S\01-selftest-default"
```

Kỳ vọng `RESULT: PASS`: 4 golden/biên đúng từng byte, 15 vector response, **50/50** transformed
khớp Python, 50/50 unprotect đúng byte, có vector chứa `0x80`, 50 request khớp
`request.i1v2.bin`, 50 dòng QUANT. Báo cáo: `check_selftest.json` (DWT protect/unprotect/encode/
quantize theo split, stack high-water).

## 3. Loopback request thường qua BLE (kiểm liên kết, chưa dùng I2/1)

```powershell
& $Py -B $Lab loopback --count 200 --pattern PLAIN --expect-mtu 247 --out "$S\02-plain-200"
```

Kỳ vọng `PASS`, MTU 247, `completed = planned = 200`. Xem `per_size` trong `check_loopback.json`
để biết RTT và goodput thật.

## 4. Negative test chạy riêng — tiêu chí 6

```powershell
& $Py -B $Lab negative --out "$S\03-negative"
& $Py -B $Chk negative --session "$S\03-negative" --output "$S\03-negative\summary.json"
```

19 kịch bản, mỗi kịch bản một run 2 packet riêng (hỏng CRC, sai byte, thiếu/trùng/đảo/hỏng/
mồ côi/thay thế fragment, sai header, timeout reassembly, ngắt kết nối khi nhận và khi gửi,
im lặng một lần và cả 3 lần, response trùng/cũ/sai stream, `EDGE_BUSY`, response không hợp lệ).
Kỳ vọng counter cho từng kịch bản nằm trong `device/scripts/week6_common.py`
(`NEGATIVE_SCENARIOS`) và đã khớp trong mô phỏng `test_week6_sim.py`. Chạy lại một kịch bản:
`--only crc,stale` với `--out` mới.

`disconnect_mid` **tắt radio Bluetooth của laptop** khoảng 1,5 s ngay sau nửa transfer (WinRT
`Windows.Devices.Radios`, tự bật lại) để link rớt bằng supervision timeout. Lý do: buổi lab
19/10/2026 cho thấy sau `BleakClient.disconnect()` Windows còn giữ link radio khoảng 3,2 s, lâu
hơn timeout reassembly 2 s, nên Device chỉ thấy timeout chứ không thấy mất kết nối giữa transfer.
Đừng để app khác dùng Bluetooth trong lúc chạy kịch bản này.

## 5. Provisioning key bench (nonce §4)

```powershell
& $Py -B $Lab provision --key-file $Key --out "$S\04-provision"
```

Kỳ vọng `PROVISION PASS ... key_check=4379e570eb84f891`. Lệnh gửi key được ghi vào log dưới dạng
`<key redacted>`. Nếu báo NVS không mount (`reason=MOUNT`, vùng `0xDC000` chứa dữ liệu cũ):
chạy lại với `--erase-if-unmountable` và thư mục `--out` mới (chỉ xóa khi NVS không mount được).
Nếu báo `STATE_IN_USE`: dongle đã có state đang dùng — **không** provisioning lại; dùng state đó.

## 6. Nonce: hook lỗi (D2) và reset mềm (D1) — tiêu chí 7

```powershell
& $Py -B $Lab nonce-hooks --out "$S\05-nonce-hooks"
& $Py -B $Lab nonce-reboot --cycles 110 --out "$S\06-nonce-soft"
```

`nonce-hooks`: lỗi ghi → FAULT chốt và không ghi thêm; read-back lệch → FAULT; 4 hook boot →
FAULT đúng lý do, 0 lần ghi; reset thật → `READY` lại. `nonce-reboot`: 110 lần `sys_reboot` ở
thời điểm ngẫu nhiên trong vòng lặp ghi `NONCE_STATE`; kỳ vọng không sequence nào lặp/giảm.
`soft_resets_landing_in_nvs_write` trong báo cáo cho biết bao nhiêu lần reset rơi đúng lúc ghi.

## 7. Nonce: ngắt nguồn thật (D1) — 12 lần rút USB

```powershell
& $Py -B $Lab nonce-unplug --cycles 12 --out "$S\07-nonce-power"
```

Mỗi lần công cụ in `RUT USB ...`: rút dongle khỏi cổng USB (Flash đang được ghi liên tục), đợi
khoảng 2 s, cắm lại. Công cụ tự mở lại cổng và chờ banner. Sau đó kiểm gộp cả ba phiên nonce
theo thứ tự thời gian:

```powershell
& $Py -B $Chk nonce --session "$S\05-nonce-hooks" --session "$S\06-nonce-soft" --session "$S\07-nonce-power" --min-soft 100 --min-power 10 --output "$S\nonce-combined.json"
```

Chỉ khi bước 6–7 và bước 8–9 (DFU giữ state) đều PASS mới coi tiêu chí 7 đạt.

## 8. Sentinel DFU, nạp bản `mtu23` (RESET lần 2)

```powershell
& $Py -B $Lab sentinel --op write --out "$S\08-sentinel-write"
```

Nhấn RESET, dò cổng bootloader, nạp `$BuildMtu23` như bước 1, rồi:

```powershell
& $Py -B $Lab sentinel --op read --out "$S\09-sentinel-read-mtu23"
& $Py -B $Chk sentinel --before "$S\08-sentinel-write" --after "$S\09-sentinel-read-mtu23" --output "$S\09-sentinel-check.json"
```

Kỳ vọng: giá trị sentinel không đổi, `NONCE_STATE` vẫn `READY`, `reserved_through` không giảm,
`key_check` không đổi (nonce §8 mục 6).

## 9. MTU 23: đủ 4 cỡ, mỗi cỡ 10 packet — tiêu chí 4 (D3)

```powershell
& $Py -B $Lab loopback --count 40 --pattern SIZES=113,153,6124,6380 --expect-mtu 23 --require-sizes 113,153,6124,6380 --out "$S\10-mtu23-sizes"
```

Công cụ tự gửi `I2 ARM` (packet 153/6124/6380 là I2/1 với key bench). 6380 B là 532 fragment mỗi
chiều. Nếu có timeout vì Windows chọn connection interval dài, chạy lại vào thư mục mới với
`--pre "CONNPARAM 6 12"` (xin 7,5–15 ms; giá trị thật ghi trong log `EVT CONN_PARAM`).

## 10. Nạp lại `default` (RESET lần 3) và kiểm DFU lần hai

Nạp `$BuildDefault` như bước 1, rồi:

```powershell
& $Py -B $Lab sentinel --op read --out "$S\11-sentinel-read-default"
& $Py -B $Chk sentinel --before "$S\08-sentinel-write" --image-before "$S\09-sentinel-read-mtu23" --after "$S\11-sentinel-read-default" --output "$S\11-sentinel-check.json"
```

`--image-before` là phiên chạy trên image bị DFU này thay thế (`mtu23`): kiểm "đã nạp image khác",
`reserved_through` và `key_check` so với phiên đó; giá trị sentinel vẫn so với lần ghi ở bước 8.

## 11. 1000 packet chính thức — tiêu chí 3, 4 (MTU thương lượng), 5 và RTT của tiêu chí 8

```powershell
& $Py -B $Lab loopback --count 1000 --pattern MIX --expect-mtu 247 --require-sizes 113,153,6124,6380 --out "$S\12-official-1000"
```

`MIX`: vector `i % 50`, lượt chẵn request thường, lượt lẻ I2/1, mỗi packet thứ 25 là frame 6380 B
→ có đủ 113, 153, 6124, 6380 B. Kỳ vọng `PASS`: `planned = completed = 1000`,
`crc_fail = byte_mismatch = failed = 0`, peer thấy đúng từng frame (request_id, độ dài, CRC) qua
BLE, sequence I2/1 tăng ngặt. Không trộn negative test vào run này.

## 12. Sau buổi lab

- Đưa các file `check_*.json`, `summary.json`, `nonce-combined.json`, `*-sentinel-check.json` và
  receipt DFU vào `results/week6/` (CSV/JSON đã kiểm, không đưa raw lớn); không sửa receipt tuần 5.
- Viết `docs/sv1_device_week6_report.md`, cập nhật bảng trạng thái của kế hoạch tuần 6.
- Đổi `runtime.nonce_persistence_reboot` chỉ bằng một **revision registry mới** sau khi tiêu chí 7 đạt.
- Commit + PR không có dòng ghi công AI.

## Sự cố thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `application CDC port not found` | Dongle đang ở bootloader (vừa nhấn RESET) hoặc chưa nạp: nạp lại; hoặc rút/cắm USB. |
| Không thấy `ASI-SV1` khi quét | Bật Bluetooth Windows; kiểm `STATUS` (dòng `LINK connected=0`); đóng app BLE khác đang kết nối dongle. |
| `att_mtu_as_expected` FAIL ở bản `default` | Windows chưa nâng MTU (mới kết nối): chạy lại; công cụ đã chờ tới 5 s. |
| Negative `disconnect_*` FAIL vì `failed=1` | Windows kết nối lại chậm hơn `RECONNECT_WAIT_MS` 10 s; chạy lại kịch bản đó (`--only`). |
| `ERROR RUN needs I2/1 packets` | Chưa `I2 ARM` hoặc nonce không `READY`: hoàn tất bước 5–7 trước. |
| Banner `NONCE status=FAULT` sau test hook | Bình thường cho tới khi reboot; `nonce-hooks` tự reboot. Nếu FAULT sau reboot thật: dừng I2, báo trưởng nhóm (state thật có vấn đề, cần cặp key/sender mới). |
