# Báo cáo SV1 tuần 6 — Device–laptop qua BLE, P1 C và nonce trên nRF52840 Dongle

Nghiệm thu kỹ thuật phía Device: **PASS cả 8 tiêu chí** của [kế hoạch tuần 6](week6_device_edge_plan.md) §1,
scope **REAL_MCU + BLE radio**, ngày 19/10/2026 (Asia/Saigon). Peer BLE là laptop Windows 11 (công cụ
`device/scripts/week6_lab.py`, bleak 3.0.2), không phải KV260: phần Edge (SV2) chưa thay laptop.

| Mục | Giá trị |
|---|---|
| Source firmware | commit `afa88870379c03d50db61ad49ed34d39c0305aca`, cây sạch (`dirty=false`) |
| Build | NCS 3.4.0, `nrf52840dongle/nrf52840`; `default` (ATT MTU 247) và `mtu23` (ép MTU 23) |
| Công cụ lab/checker | commit `33cd6ab` (sửa `disconnect_mid`) và `04154b2` (checker sentinel); SHA-256 từng file trong `session.json` mỗi bước |
| Phiên raw | `D:\HUST\ASI_week6\device-session-20261019` (ngoài Git); bằng chứng đã kiểm ở [results/week6](../results/week6/README.md) |
| DFU thật | 3 lần, bootloader `1915:521F` COM6, exit 0: `default` 05:34:23Z, `mtu23` 06:10:09Z, `default` 06:13:31Z (UTC) |
| Nguồn | USB laptop (không phải phiên đo năng lượng PPK2) |

## 1. Kết quả theo tiêu chí

| # | Tiêu chí | Kết quả trên MCU | Bằng chứng |
|---:|---|---|---|
| 1 | P1 C khớp Python 50/50 vector SV3 | **PASS** 50/50 transformed bytes khớp gói `mitdb-week6-p1-50-20261016-v1` (manifest `d0914acb…1c36`); 50/50 request I1 v2 khớp `request.i1v2.bin`; 4 golden encoder + 15 vector response đúng | [selftest_default.json](../results/week6/selftest_default.json), [p1_vectors_50.csv](../results/week6/p1_vectors_50.csv) |
| 2 | Unprotect đúng byte, có `0x80` | **PASS** 50/50 byte-exact; 39/50 vector có `0x80` trong transformed bytes | như trên |
| 3 | 1000 packet hợp lệ qua BLE loopback | **PASS** `planned = completed = 1000`, `crc_fail = byte_mismatch = failed = 0`, 0 retry, 0 timeout, 0 mất kết nối; peer nhận 1000/1000 frame CRC đúng (14 290 fragment mỗi chiều); 125,5 s | [loopback_official_1000_mtu247.json](../results/week6/loopback_official_1000_mtu247.json) |
| 4 | Nhiều fragment, đủ cỡ biên ở MTU thương lượng và MTU 23 | **PASS** MTU 247: 113 (30), 153 (30), 6124 (50), 6380 (40 packet) trong 1000 packet. MTU 23 (bản `mtu23`): mỗi cỡ 10 packet, 40/40, 6380 B = 532 fragment mỗi chiều | như trên, [loopback_mtu23_4sizes_x10.json](../results/week6/loopback_mtu23_4sizes_x10.json) |
| 5 | Đủ counter theo application packet | **PASS** 16 counter §11 + 13 counter reassembly, mẫu số `planned` | [loopback_counters.csv](../results/week6/loopback_counters.csv) |
| 6 | Negative test chạy riêng | **PASS** 19/19 kịch bản, mỗi kịch bản một run 2 packet riêng, counter đúng từng giá trị kỳ vọng | [negative_19_summary.json](../results/week6/negative_19_summary.json) |
| 7 | Nonce qua reboot/mất điện, lỗi ghi, DFU | **PASS** 110 reset mềm (79 lần rơi đúng lúc `nvs_write`) + 12 lần rút USB thật trong lúc ghi; 128 boot, 0 boot không READY, 58 659 sequence quan sát được không lặp/giảm; `FAILWRITE`/`READBACK` → FAULT chốt; 4 hook boot → FAULT, 0 lần ghi; 2 lần DFU (default→mtu23→default) giữ sentinel, `READY`, `reserved_through` không giảm, `key_check` không đổi | [nonce_combined.json](../results/week6/nonce_combined.json), [nonce_hooks.json](../results/week6/nonce_hooks.json), 2 file `sentinel_dfu_*.json` |
| 8 | Build, tài nguyên, DWT, RTT | **PASS** xem §2 | [build_check/](../results/week6/build_check/), [stack_highwater.csv](../results/week6/stack_highwater.csv), [dwt_by_split.csv](../results/week6/dwt_by_split.csv), [loopback_rtt_by_size.csv](../results/week6/loopback_rtt_by_size.csv) |

Thứ tự đúng kế hoạch: packet I2/1 (153/6124/6380 B và các lượt lẻ của `MIX`) chỉ chạy sau khi tiêu chí 7 đạt
(bước 5–7 rồi mới `I2 ARM`), với key bench `key_id=65537`, `sender_id=131073`, `key_check=4379e570eb84f891`.
Key không xuất hiện trong bất kỳ file nào của phiên (quét 163 file, 0 lần trùng); lệnh provisioning được ghi
dưới dạng `<key redacted>`.

## 2. Tài nguyên và thời gian đo được (tiêu chí 8)

**Flash/RAM tĩnh** (`check_week6_build.py`, 18 kiểm tĩnh PASS cả hai bản):

| Bản | `zephyr.bin` | Image kết thúc | Dư trước `0xDC000` | RAM tĩnh |
|---|---:|---|---:|---:|
| `default` | 333 040 B | `0x524f0` | 563 984 B | 102 284 B |
| `mtu23` | 331 304 B | `0x51e28` | 565 720 B | 96 511 B |

**Stack high-water** lúc chạy (byte dùng / cấp phát, lớn nhất qua các run): `main` 2 160/8 192, BT RX
712/1 024 (70 %), `i1_tx` 552/2 048, `sysworkq` 496/2 048, `bt_tx_processor` 356/768, `usbd` 448/1 024,
`udc_nrfx` 320/512, MPSL 320/1 024, idle 64/384.

**DWT ở 64 MHz** (median, đo trên chính 50 vector, n = 4–5 mỗi split): ví dụ split lớn nhất s3 `[1,32,180]`
quantize 8 839 µs, protect 2 765 µs, unprotect 2 370 µs, encode I1 v2 (gồm CRC) 8 979 µs; s10 tương ứng
36 / 138 / 197 / 217 µs. Bảng đủ 11 split ở [dwt_by_split.csv](../results/week6/dwt_by_split.csv).
Quantize đo bằng `week5/quantization.c` trên `z = q × scale` cùng shape (D5), không có head CNN trong firmware.

**RTT loopback** (từ lúc Device bắt đầu gửi tới khi nhận đủ echo, gồm cả hai chiều radio và xử lý trên laptop;
connection interval Windows chọn 45 ms, PHY 2M, Data Length 251):

| MTU | Frame | Fragment/chiều | RTT median | RTT p95 | RTT max |
|---:|---:|---:|---:|---:|---:|
| 247 | 113 B (s10 thường) | 1 | 88,3 ms | 88,3 ms | 133,3 ms |
| 247 | 153 B (s10 I2/1) | 1 | 88,0 ms | 88,0 ms | 88,0 ms |
| 247 | 6124 B (s3 I2/1) | 26 | 152,9 ms | 234,7 ms | 265,0 ms |
| 247 | 6380 B (trần, profile test) | 28 | 155,2 ms | 221,7 ms | 225,5 ms |
| 23 | 113 B | 10 | 126,7 ms | 171,7 ms | 171,7 ms |
| 23 | 153 B | 13 | 156,0 ms | 222,7 ms | 222,7 ms |
| 23 | 6124 B | 511 | 3 976,8 ms | 4 317,8 ms | 4 317,8 ms |
| 23 | 6380 B | 532 | 4 217,7 ms | 4 488,0 ms | 4 488,0 ms |

Ở MTU 247, frame nhỏ bị chặn bởi khoảng hai connection interval (≈ 88 ms); frame 6 KB chỉ thêm khoảng 65 ms.
Ở MTU 23, frame 6 KB chậm khoảng 26 lần nhưng vẫn dưới timeout response của binding §7. Các số này phụ thuộc
connection interval do Windows chọn; KV260/BlueZ sẽ phải đo lại.

## 3. Sự cố trong buổi lab và cách xử lý

1. **Firmware cũ không trả lời CDC.** Dongle cắm vào đang chạy image cũ; nạp bản `default` qua DFU như runbook.
2. **`disconnect_mid` FAIL ở lần chạy negative đầu (18/19).** Device không đếm `reasm.disconnect`, chỉ có
   `reassembly_timeout=1`. Log cho thấy laptop gọi `BleakClient.disconnect()` lúc 14 345 125 ms nhưng Device
   chỉ thấy `DISCONNECTED` lúc 14 348 390 ms: Windows giữ link radio khoảng 3,2 s (lặp lại ở `disconnect_rx`:
   3,16 s), lâu hơn timeout reassembly 2 s. Firmware làm đúng binding (hủy transfer khi hết 2 s, exchange retry
   thành công), nhưng kịch bản chưa kiểm được nhánh "rớt link giữa transfer". **Sửa công cụ, không sửa firmware,
   không nới checker:** `disconnect_mid` tắt radio Bluetooth laptop 1,5 s ngay sau nửa transfer (WinRT
   `Windows.Devices.Radios`); controller laptop kết thúc link ngay với lý do HCI `0x15` (remote device
power off), Device thấy `DISCONNECTED` khoảng 150 ms sau nửa transfer. Lần thử riêng và lần
   chạy lại đủ 19 kịch bản (`03b-negative`) đều PASS với `reasm.disconnect=1`, `reassembly_timeout=0`.
   Mô phỏng `test_week6_sim.py` đã cập nhật và vẫn PASS.
3. **Kiểm sentinel sau DFU lần hai FAIL ở `different_image_flashed`.** Lệnh runbook so phiên ghi sentinel
   (image `default`) với phiên đọc sau khi nạp lại `default`, tức so một image với chính nó. Thêm tham số
   `--image-before` cho checker (so với phiên chạy trên image bị thay, `mtu23`); thêm test dương/âm vào
   `test_week6_checkers.py` (12/12 PASS). Kết quả PASS; file FAIL được giữ lại trong `results/week6/`.

Test host sau các sửa đổi: `test_week6_host.py` 27/27, `test_week6_sim.py` 3/3, `test_week6_checkers.py` 12/12,
`test_week6_lab.py` 4/4.

## 4. Giới hạn và việc tiếp theo

- Peer là laptop Windows, không phải KV260. Tiêu chí của SV2 (BlueZ central, parser I1 v2, reassembly, tail
  DPU) và SV3 (sai số luồng DPU) ở kế hoạch §2.2–2.3 chưa nằm trong báo cáo này.
- Echo (`stream 0x02`) là chẩn đoán, không phải inference; không có kết quả phân loại qua BLE.
- Tiêu chí 7 đạt, nhưng `runtime.nonce_persistence_reboot` trong registry vẫn `NOT_ACCEPTED`. Theo
  [nonce §8](../contracts/i2_nonce_provisioning_v1.md), trạng thái này chỉ đổi bằng một **revision registry mới**.
  Revision đó cần Châu và Trung xác nhận cùng `device_revision = edge_revision`, nên chưa làm trong phiên này.
- Chưa đo năng lượng (PPK2 qua VBUS 5 V, tuần 7). Phiên này cấp nguồn từ USB laptop.
- Hao mòn Flash do stress test: khoảng 58,7 nghìn lần ghi `NONCE_STATE`, nằm trong ước tính D1. Dải sequence
  đã đặt trước tới 60 624 896 trên 2^64, không đáng kể.
