# Báo cáo SV1 tuần 6 — Device–laptop qua BLE, P1 C và nonce trên nRF52840 Dongle

Nghiệm thu kỹ thuật phía Device: **PASS cả 8 tiêu chí** tuần 6 ([phụ lục A](#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-d1d6)),
scope **REAL_MCU + BLE radio**, ngày 19/10/2026 (Asia/Saigon). Peer BLE là laptop Windows 11 (công cụ
`device/scripts/week6_lab.py`, bleak 3.0.2), không phải KV260: phần Edge (SV2) chưa thay laptop.

| Mục | Giá trị |
|---|---|
| Source firmware | commit `afa88870379c03d50db61ad49ed34d39c0305aca`, cây sạch (`dirty=false`) |
| Build | NCS 3.4.0, `nrf52840dongle/nrf52840`; `default` (ATT MTU 247) và `mtu23` (ép MTU 23) |
| Công cụ lab/checker | commit `33cd6ab` (sửa `disconnect_mid`) và `04154b2` (checker sentinel); SHA-256 từng file trong `session.json` mỗi bước |
| Phiên raw | `D:\HUST\ASI_week6\device-session-20261019` (ngoài Git); bằng chứng đã kiểm ở [results/week6/device](../results/week6/device/README.md) |
| DFU thật | 3 lần, bootloader `1915:521F` COM6, exit 0: `default` 05:34:23Z, `mtu23` 06:10:09Z, `default` 06:13:31Z (UTC) |
| Nguồn | USB laptop (không phải phiên đo năng lượng PPK2) |

## 1. Kết quả theo tiêu chí

| # | Tiêu chí | Kết quả trên MCU | Bằng chứng |
|---:|---|---|---|
| 1 | P1 C khớp Python 50/50 vector SV3 | **PASS** 50/50 transformed bytes khớp gói `mitdb-week6-p1-50-20261016-v1` (manifest `d0914acb…1c36`); 50/50 request I1 v2 khớp `request.i1v2.bin`; 4 golden encoder + 15 vector response đúng | [selftest_default.json](../results/week6/device/selftest_default.json), [p1_vectors_50.csv](../results/week6/device/p1_vectors_50.csv) |
| 2 | Unprotect đúng byte, có `0x80` | **PASS** 50/50 byte-exact; 39/50 vector có `0x80` trong transformed bytes | như trên |
| 3 | 1000 packet hợp lệ qua BLE loopback | **PASS** `planned = completed = 1000`, `crc_fail = byte_mismatch = failed = 0`, 0 retry, 0 timeout, 0 mất kết nối; peer nhận 1000/1000 frame CRC đúng (14 290 fragment mỗi chiều); 125,5 s | [loopback_official_1000_mtu247.json](../results/week6/device/loopback_official_1000_mtu247.json) |
| 4 | Nhiều fragment, đủ cỡ biên ở MTU thương lượng và MTU 23 | **PASS** MTU 247: 113 (30), 153 (30), 6124 (50), 6380 (40 packet) trong 1000 packet. MTU 23 (bản `mtu23`): mỗi cỡ 10 packet, 40/40, 6380 B = 532 fragment mỗi chiều | như trên, [loopback_mtu23_4sizes_x10.json](../results/week6/device/loopback_mtu23_4sizes_x10.json) |
| 5 | Đủ counter theo application packet | **PASS** 16 counter §11 + 13 counter reassembly, mẫu số `planned` | [loopback_counters.csv](../results/week6/device/loopback_counters.csv) |
| 6 | Negative test chạy riêng | **PASS** 19/19 kịch bản, mỗi kịch bản một run 2 packet riêng, counter đúng từng giá trị kỳ vọng | [negative_19_summary.json](../results/week6/device/negative_19_summary.json) |
| 7 | Nonce qua reboot/mất điện, lỗi ghi, DFU | **PASS** 110 reset mềm (79 lần rơi đúng lúc `nvs_write`) + 12 lần rút USB thật trong lúc ghi; 128 boot, 0 boot không READY, 58 659 sequence quan sát được không lặp/giảm; `FAILWRITE`/`READBACK` → FAULT chốt; 4 hook boot → FAULT, 0 lần ghi; 2 lần DFU (default→mtu23→default) giữ sentinel, `READY`, `reserved_through` không giảm, `key_check` không đổi | [nonce_combined.json](../results/week6/device/nonce_combined.json), [nonce_hooks.json](../results/week6/device/nonce_hooks.json), 2 file `sentinel_dfu_*.json` |
| 8 | Build, tài nguyên, DWT, RTT | **PASS** xem §2 | [build_check/](../results/week6/device/build_check/), [stack_highwater.csv](../results/week6/device/stack_highwater.csv), [dwt_by_split.csv](../results/week6/device/dwt_by_split.csv), [loopback_rtt_by_size.csv](../results/week6/device/loopback_rtt_by_size.csv) |

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
36 / 138 / 197 / 217 µs. Bảng đủ 11 split ở [dwt_by_split.csv](../results/week6/device/dwt_by_split.csv).
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
   `test_week6_checkers.py` (12/12 PASS). Kết quả PASS; file FAIL được giữ lại trong `results/week6/device/`.

Test host sau các sửa đổi: `test_week6_host.py` 27/27, `test_week6_sim.py` 3/3, `test_week6_checkers.py` 12/12,
`test_week6_lab.py` 4/4.

## 4. Giới hạn và việc tiếp theo

- Peer là laptop Windows, không phải KV260. Hạng mục của SV2 (BlueZ central, parser I1 v2, reassembly, tail
  DPU) và SV3 (sai số luồng DPU) ở [phụ lục A.3](#a3-hạng-mục-còn-mở-của-sv2-và-sv3) chưa nằm trong báo cáo này.
- Echo (`stream 0x02`) là chẩn đoán, không phải inference; không có kết quả phân loại qua BLE.
- Tiêu chí 7 đạt, nhưng `runtime.nonce_persistence_reboot` trong registry vẫn `NOT_ACCEPTED`. Theo
  [nonce §8](../contracts/i2_nonce_provisioning_v1.md), trạng thái này chỉ đổi bằng một **revision registry mới**.
  Revision đó cần Châu và Trung xác nhận cùng `device_revision = edge_revision`, nên chưa làm trong phiên này.
- Chưa đo năng lượng (PPK2 qua VBUS 5 V, tuần 7). Phiên này cấp nguồn từ USB laptop.
- Hao mòn Flash do stress test: khoảng 58,7 nghìn lần ghi `NONCE_STATE`, nằm trong ước tính D1. Dải sequence
  đã đặt trước tới 60 624 896 trên 2^64, không đáng kể.

## Phụ lục A. Tiêu chí nghiệm thu và quyết định D1–D6

Gộp từ kế hoạch tuần 6 `docs/week6_device_edge_plan.md` (lập 15/10/2026, đã xóa ngày 19/10/2026 sau khi
hoàn tất). Thiết kế đã chốt nằm ở [I1 v2](../contracts/i1_device_edge_packet_v2.md),
[I1 BLE binding v1](../contracts/i1_ble_binding_v1.md),
[I2/1 nonce và provisioning v1](../contracts/i2_nonce_provisioning_v1.md) và
[reference/vector](../contracts/i1v2_ref/vectors.json).

### A.1. Tám tiêu chí

| # | Tiêu chí | Bằng chứng tối thiểu |
|---:|---|---|
| 1 | P1 C trên MCU khớp Python **50/50** vector từ gói chính thức của SV3 | Capture USB CDC 50 dòng, mỗi dòng hash transformed bytes của C so với giá trị Python trong gói; firmware hash; script kiểm offline exit 0 |
| 2 | Unprotect khôi phục **đúng byte** tensor lượng tử của cả 50 vector | So byte-exact q gốc ↔ q sau `unprotect()`; ít nhất một vector có `0x80` trong transformed bytes |
| 3 | **1000 application packet hợp lệ** qua BLE loopback (dongle → BLE → laptop → trả nguyên frame → dongle), CRC đúng 100 %, bytes khớp 100 % | Counter binding §11 với `planned = completed = 1000`, `crc_fail = byte_mismatch = failed = 0`; log CRC phía laptop |
| 4 | Có packet nhiều fragment và kích thước biên | Trong 1000 packet có 113 B (s10 thường), 153 B (s10 I2/1), 6124 B (s3 I2/1 lớn nhất registry), 6380 B (trần, profile test); mỗi cỡ chạy ở MTU thương lượng **và** ép MTU 23 |
| 5 | Báo đủ `planned/sent/received/timeout/retry/duplicate/crc_fail/byte_mismatch/failed` | Theo application packet, mẫu số `planned`; không bỏ packet mất; không dùng số fragment thay số packet |
| 6 | Negative test chạy **tách riêng** | Frame hỏng CRC, fragment thiếu/trùng/sai thứ tự, mất kết nối giữa transfer, timeout, retry; đúng hành vi binding §5–6 |
| 7 | Reboot/mất điện cho nonce **trước** khi truyền I2/1 | [Nonce §8](../contracts/i2_nonce_provisioning_v1.md) mục 1–6: không sequence nào lặp/giảm qua ≥ 100 lần reset, kể cả ngắt nguồn lúc ghi; lỗi ghi → dừng; DFU giữ state |
| 8 | Build và đo tài nguyên/latency trên MCU | Build NCS 3.4.0, ELF/map: Flash, RAM tĩnh, image kết thúc trước `0xDC000`; stack high-water lúc chạy; DWT quantize/protect/encode/transfer; RTT theo cỡ frame |

Quy tắc chung: software loopback hay USB CDC không thay cho radio ở tiêu chí 3–4; echo (`stream 0x02`) là
chẩn đoán, không phải inference; timeout/retry là cấu hình bench của binding §7, mọi số latency chỉ lấy từ
phép đo; packet I2/1 chỉ dùng key bench và chỉ sau khi tiêu chí 7 đạt; không sửa receipt tuần 5.

### A.2. Quyết định D1–D6 (trưởng nhóm chốt 18/10/2026)

Các quyết định cụ thể hóa cách chạy tiêu chí 4, 6, 7; không đổi contract.

| # | Quyết định | Thực hiện |
|---|---|---|
| D1 | Tiêu chí 7 = **≥ 100 reset mềm tự động + 10–20 lần ngắt nguồn thật**, báo cáo tách riêng. Nút RESET vào bootloader nên không dùng làm reset ứng dụng | `NTEST STRESS <ms> 1`: mỗi vòng đặt trước một khối mới rồi cấp một sequence; timer gọi `sys_reboot` ngẫu nhiên. P0.15 lên cao lúc `nvs_write`; biến `__noinit` cho biết reset có rơi vào lúc ghi. Ước tính 60–70 nghìn lần ghi 48 B, dưới 10 % tuổi thọ 4 trang |
| D2 | "Record hỏng → FAULT" và "lỗi ghi → dừng" **giả lập ở lớp lưu trữ**, không hủy state thật | `NTEST FAILWRITE`, `NTEST READBACK`, `NTEST BOOT <hook>` (`STATE_CRC`, `STATE_MISSING`, `PROVISION_CORRUPT`, `KEY_MISMATCH`, đếm số lần ghi phải bằng 0), rồi `REBOOT` thật |
| D3 | 1000 packet ở **MTU 247**; ở **MTU 23** đủ 4 cỡ, **mỗi cỡ 10 packet** | `RUN 1000 MIX` (bản `default`), `RUN 40 SIZES=113,153,6124,6380` (bản `mtu23`); `CONNPARAM 6 12` nếu Windows chọn interval quá dài |
| D4 | Frame 6380 B là **profile test**, chỉ dùng ở echo | Metadata như vector `i2_ceiling_c64_payload5760` (`[1,64,90]`), payload q thật 5760 B của vector s3 đầu, scale thật C=64 của vector s7 đầu; key bench + nonce từ allocator |
| D5 | Nguồn tensor = **50 vector P1 thật của SV3** nhúng vào firmware | `build_week6.ps1` xác thực manifest `d0914acb…1c36` rồi sinh bảng; DWT quantize bằng `week5/quantization.c` trên `z = q × scale` |
| D6 | Key bench sinh ngoài repo bằng `secrets.token_bytes(32)`; chỉ log `key_id`, `sender_id`, `key_check` | `D:\HUST\ASI_week6\secrets\bench_key_65537.bin` (ACL chỉ tài khoản hiện tại), `key_check = 4379e570eb84f891`, cặp `65537/131073` |

Hai khóa an toàn: firmware từ chối `RUN` có I2/1 cho tới `I2 ARM` (chỉ thành công khi nonce `READY`);
`PROV KEY` từ chối mọi trường hợp có thể làm sequence bắt đầu lại (`STATE_IN_USE`, state hỏng/lạ,
`STATE_UNREADABLE`), `PROV ERASE` chỉ được phép khi NVS không mount được.

### A.3. Hạng mục còn mở của SV2 và SV3

| Người | Hạng mục | Tiêu chí bàn giao |
|---|---|---|
| Trung (SV2) | KV260 làm BLE central | Bộ chuyển BLE USB được image nhận, BlueZ quét thấy `ASI-SV1`, kết nối, bật notification, đọc MTU; log `bluetoothctl`/script, phiên bản BlueZ và kernel |
| Trung | Parser/encoder I1 v2 trên Edge | Đạt mọi vector `golden`, `request_negative`, `pipeline`, `response` trong `contracts/i1v2_ref/vectors.json` đúng mã lỗi và thứ tự §7 |
| Trung | Reassembly BLE và duplicate cache | Quy tắc binding §5, §8; TTL thỏa §7 |
| Trung | Xử lý sau giải lượng tử | Unprotect trước, từ chối `q=-128`, dequantize theo kênh gốc, reshape NC cho s9; s10 trả identity |
| Trung | Tail s0..s9 trên KV260 | xmodel/fallback từ `compile_all_splits.sh` có provenance thật, kèm sai số/accuracy đo trên KV260; trước đó Edge trả `INFERENCE_FAILED` |
| Trung | Key Edge và xác nhận kỹ thuật | Đối chiếu `key_check` với Device, không commit/log key; ký bảng xác nhận I1 v2 §14 |
| Kỳ Anh (SV3) | Đánh giá sai số luồng DPU (cùng Trung) | Accuracy/sai số tail qua lượng tử DPU so với tail FP32 trên tập test chính thức, không đổi gate tuần 5 |

Gói 50 vector P1 và xác nhận ngữ nghĩa response của SV3 đã bàn giao ngày 16/10/2026
([week6_p1_delivery.md](../ml/docs/week6_p1_delivery.md)). Thứ tự còn lại: KV260 central + parser theo
vector, thay laptop bằng KV260 ở chế độ echo, rồi chế độ inference khi tail sẵn sàng.

## Phụ lục B. Firmware `device/week6/`

Gộp từ `device/week6/README.md` (đã xóa ngày 19/10/2026). Ứng dụng Zephyr riêng; không sửa file tuần 3–5
bị khóa hash (`../src/markers.c`, `../week5/quantization.c` được biên dịch nguyên vẹn).

| File | Vai trò | Kiểm trên host |
|---|---|---|
| `frag.c/.h` | Header fragment 8 B, `transfer_id`, reassembler đúng 8 quy tắc binding §5 (thêm `rx_busy`) | vi sai với `contracts/i1v2_ref/i1_ble_binding.py` |
| `exchange.c/.h` | Máy trạng thái request §6 (timeout `8000 + n_resp × 30` ms, 2 retry, backoff 250/500 ms, chờ kết nối lại 10 s), phân loại echo §9 / response I1 v2 §8.3, counter §11 | `test_week6_host.py`, `test_week6_sim.py` |
| `nonce_store.c/.h` | Record `PROVISION` 0x4901 / `NONCE_STATE` 0x4902, boot §5, cấp sequence theo khối 1024, provisioning an toàn | so byte với `nonce_reservation.py`, mất điện ngẫu nhiên |
| `packets.c/.h` | Dựng request thường / I2/1 bằng `contracts/i2_ref/i2_reference.c` và `contracts/i1v2_ref/i1v2_codec.c` (biên dịch nguyên vẹn) | golden, vector biên, 50 vector SV3 |
| `sha256.c/.h` | SHA-256 để in hash bằng chứng | so với `hashlib` |
| `ble_link.c/.h` | GATT §2, thread gửi `i1_tx` với 4 credit trả trong callback `bt_gatt_notify_cb`, `-ENOMEM`/`-ENOBUFS` nghỉ 2 ms, callback RX chỉ kiểm header + `memcpy` | trên dongle |
| `nonce_nvs.c/.h` | Zephyr NVS trên `storage_partition` 0xDC000 (4 × 4096 B), hook D2, sentinel DFU, marker P0.15 + biến `__noinit` lúc ghi | trên dongle |
| `main.c` | Console USB CDC, self-test, `RUN`, provisioning, test nonce | trên dongle |
| `host_test/week6_shim.c` | API phẳng cho ctypes; **không** vào firmware | — |

Bảng vector (`week6_vectors.c/.h`, `week6_build.h`) được `../scripts/generate_week6_vectors.py` sinh lúc
build vào thư mục report, sau khi xác thực manifest gói SV3; key `00..1f` chỉ dùng cho self-test
(`PUBLIC_TEST_ONLY`). Hai biến thể: `default` (`prj.conf`, ATT MTU 247, 236 B frame/fragment) và `mtu23`
(`prj.conf` + `overlay-mtu23.conf`, MTU 23, 12 B). WinRT không cho central chọn MTU nên Device tự giới hạn:
ATT MTU = min(`BT_BUF_ACL_RX_SIZE` − 4, `BT_L2CAP_TX_MTU`). `CONFIG_FLASH_LOAD_SIZE=0xdb000` làm linker từ
chối image vượt `0xDC000`. Ngay lúc kết nối MTU là 23, Windows nâng lên khoảng 1 s sau; firmware đọc
`bt_gatt_get_uatt_mtu()` ở đầu mỗi transfer.

Lệnh USB CDC (một lệnh một dòng):

| Lệnh | Việc |
|---|---|
| `HELP`, `STATUS`, `STACK` | Banner (build ID, gói vector), link, nonce, cấu hình §7; stack high-water |
| `SELFTEST ENC` / `P1` / `QUANT` | Encoder so golden + biên (4) và response §8.3 (15); 50 vector P1 với DWT; DWT `week5_quantize` |
| `MODE ECHO` / `MODE NORMAL` | Echo stream 0x02 (mặc định) / request stream 0x01 chờ response |
| `RUN <n> MIX`, `RUN <n> PLAIN`, `RUN <n> SIZES=a,b,..` | n application packet; in `PKT`, `RUN END`, `COUNTERS`, `REASM`, `STACK` |
| `I2 ARM`, `STOP` | Cho phép I2/1 (chỉ khi nonce `READY`); dừng `RUN`/`NTEST STRESS` (lệnh duy nhất nhận được trong lúc `RUN`) |
| `PROV MODE ON`/`OFF`, `PROV KEY <key_id> <sender_id> <64 hex>`, `PROV ERASE` | Provisioning key bench; không in lại key |
| `NONCE`, `NONCE ALLOC <n>` | Trạng thái nonce; cấp thử n sequence |
| `NTEST STRESS <ms> <reboot> [gap_ms]`, `NTEST FAILWRITE`, `NTEST READBACK`, `NTEST BOOT <hook>`, `NTEST SENTINEL WRITE`/`READ` | Stress ghi `NONCE_STATE`, hook D2, sentinel 0x49F0 cho test DFU |
| `CONNPARAM <min> <max>`, `DISCONNECT`, `REBOOT` | Xin connection interval (đơn vị 1,25 ms), ngắt BLE, reset mềm |

Marker GPIO: P0.13 head (không dùng ở tuần 6), P0.15 protect và ghi Flash, P0.17 đang gửi BLE, P0.20 chờ
response. Công cụ laptop dùng venv riêng `device/host/.venv` với gói ghim trong
[`requirements-week6-ble.txt`](../device/scripts/requirements-week6-ble.txt) (`bleak==3.0.2`), không dùng `ml/.venv`.

Build và kiểm trên host (không cần dongle; cây làm việc phải sạch để `build_id` không có `-dirty`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week6.ps1 -ReportDir <thư-mục-mới> -Variant default
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week6.ps1 -ReportDir <thư-mục-mới> -Variant mtu23
ml\.venv\Scripts\python.exe -B device\scripts\test_week6_host.py
device\host\.venv\Scripts\python.exe -B device\scripts\test_week6_sim.py
device\host\.venv\Scripts\python.exe -B device\scripts\test_week6_checkers.py
device\host\.venv\Scripts\python.exe -B device\scripts\test_week6_lab.py
```

`build_week6.ps1` ghi `source.json` (commit, cờ dirty), sinh bảng vector, build, chạy `check_week6_build.py`
(18 kiểm tĩnh) và đóng gói DFU.

## Phụ lục C. Quy trình chạy lại trên dongle

Gộp từ `device/week6/RUNBOOK.md` (đã xóa ngày 19/10/2026). Khoảng 1,5–2 giờ; thao tác tay 3 lần nhấn RESET
và 12 lần rút/cắm USB. Thứ tự bắt buộc: self-test → loopback thường → negative → nonce → mới tới I2/1.
Mỗi bước ghi vào thư mục **mới**; công cụ từ chối ghi đè. Bật Bluetooth Windows, không pair dongle trong
Settings, không để app khác dùng Bluetooth. Bootloader là `1915:521F`, ứng dụng là `2FE3:0004`; số COM chỉ
đúng trong phiên đó. Từ Git root:

```powershell
$Py  = "device\host\.venv\Scripts\python.exe"
$Lab = "device\scripts\week6_lab.py"
$Chk = "device\scripts\check_week6.py"
$S   = "D:\HUST\ASI_week6\device-session-<ngày>"
$Key = "D:\HUST\ASI_week6\secrets\bench_key_65537.bin"
$BuildDefault = "D:\HUST\ASI_week6\20261019-r1-default"
$BuildMtu23   = "D:\HUST\ASI_week6\20261019-r1-mtu23"
& $Py -c "from serial.tools import list_ports; [print(p.device, f'{p.vid or 0:04X}:{p.pid or 0:04X}', p.description) for p in list_ports.comports()]"
```

| Bước | Lệnh | Kỳ vọng |
|---|---|---|
| 1. Nạp `default` (RESET lần 1) | `powershell -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\flash_week6.ps1 -Port COMx -ReportDir $BuildDefault -ReceiptDir "$S\dfu"` | `DFU completed (default)` |
| 2. Self-test (tc 1, 2, 8) | `& $Py -B $Lab selftest --out "$S\01-selftest-default"` | `RESULT: PASS` |
| 3. Loopback thường | `& $Py -B $Lab loopback --count 200 --pattern PLAIN --expect-mtu 247 --out "$S\02-plain-200"` | 200/200, MTU 247 |
| 4. Negative (tc 6) | `& $Py -B $Lab negative --out "$S\03-negative"` rồi `& $Py -B $Chk negative --session "$S\03-negative" --output "$S\03-negative\summary.json"` | 19/19; chạy lại một kịch bản: `--only crc,stale` với `--out` mới |
| 5. Provisioning | `& $Py -B $Lab provision --key-file $Key --out "$S\04-provision"` | `key_check=4379e570eb84f891`; `reason=MOUNT` → thêm `--erase-if-unmountable`; `STATE_IN_USE` → **không** provisioning lại |
| 6. Nonce hook + reset mềm | `& $Py -B $Lab nonce-hooks --out "$S\05-nonce-hooks"`; `& $Py -B $Lab nonce-reboot --cycles 110 --out "$S\06-nonce-soft"` | PASS |
| 7. Rút USB thật | `& $Py -B $Lab nonce-unplug --cycles 12 --out "$S\07-nonce-power"`: mỗi lần in `RUT USB` thì rút, đợi 2 s, cắm lại, đợi khoảng 10 s | rồi `& $Py -B $Chk nonce --session "$S\05-nonce-hooks" --session "$S\06-nonce-soft" --session "$S\07-nonce-power" --min-soft 100 --min-power 10 --output "$S\nonce-combined.json"` PASS |
| 8. Sentinel + nạp `mtu23` (RESET lần 2) | `& $Py -B $Lab sentinel --op write --out "$S\08-sentinel-write"`; nạp `$BuildMtu23`; `& $Py -B $Lab sentinel --op read --out "$S\09-sentinel-read-mtu23"`; `& $Py -B $Chk sentinel --before "$S\08-sentinel-write" --after "$S\09-sentinel-read-mtu23" --output "$S\09-sentinel-check.json"` | sentinel, `READY`, `reserved_through`, `key_check` giữ nguyên |
| 9. MTU 23 (tc 4) | `& $Py -B $Lab loopback --count 40 --pattern SIZES=113,153,6124,6380 --expect-mtu 23 --require-sizes 113,153,6124,6380 --out "$S\10-mtu23-sizes"` | 40/40; nếu timeout thêm `--pre "CONNPARAM 6 12"` |
| 10. Nạp lại `default` (RESET lần 3) | `& $Py -B $Lab sentinel --op read --out "$S\11-sentinel-read-default"`; `& $Py -B $Chk sentinel --before "$S\08-sentinel-write" --image-before "$S\09-sentinel-read-mtu23" --after "$S\11-sentinel-read-default" --output "$S\11-sentinel-check.json"` | PASS (`--image-before` = phiên trên image bị DFU thay thế) |
| 11. 1000 packet (tc 3, 4, 5, 8) | `& $Py -B $Lab loopback --count 1000 --pattern MIX --expect-mtu 247 --require-sizes 113,153,6124,6380 --out "$S\12-official-1000"` | 1000/1000, 0 lỗi |
| 12. Công bố | `device\host\.venv\Scripts\python.exe -B device\scripts\publish_week6_results.py --session $S --build-default $BuildDefault --build-mtu23 $BuildMtu23 --out results\week6\device` | thư mục kết quả + `manifest.json` |

`MIX`: vector `i % 50`, lượt chẵn request thường, lượt lẻ I2/1, mỗi packet thứ 25 là frame 6380 B.
`disconnect_mid` tắt radio Bluetooth laptop khoảng 1,5 s ngay sau nửa transfer (xem §3).

| Sự cố | Xử lý |
|---|---|
| `application CDC port not found` | Dongle đang ở bootloader hoặc chưa nạp: nạp lại, hoặc rút/cắm USB |
| Không thấy `ASI-SV1` khi quét | Bật Bluetooth; kiểm `STATUS` (`LINK connected=0`); đóng app BLE khác |
| `att_mtu_as_expected` FAIL ở `default` | Windows chưa nâng MTU: chạy lại (công cụ đã chờ tới 5 s) |
| `disconnect_*` FAIL vì `failed=1` | Windows kết nối lại chậm hơn 10 s: chạy lại kịch bản đó với `--only` |
| `ERROR RUN needs I2/1 packets` | Chưa `I2 ARM` hoặc nonce không `READY`: làm xong bước 5–7 |
| `NONCE status=FAULT` sau test hook | Bình thường tới khi reboot. FAULT sau reboot thật: dừng I2, báo trưởng nhóm (cần cặp key/sender mới) |
| Firmware cũ không trả lời lệnh CDC | Nạp lại bản tuần 6 qua DFU (bước 1) |
