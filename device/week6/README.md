# Firmware tuần 6 — Device–Edge qua BLE

Ứng dụng riêng cho tuần 6 theo [I1 v2](../../contracts/i1_device_edge_packet_v2.md),
[BLE binding v1](../../contracts/i1_ble_binding_v1.md) và
[nonce/provisioning v1](../../contracts/i2_nonce_provisioning_v1.md). Tiêu chí nghiệm thu và
quyết định D1–D6: [kế hoạch tuần 6](../../docs/week6_device_edge_plan.md). Không sửa file tuần 3–5
bị khóa hash (`../src/markers.c`, `../week5/quantization.c` được biên dịch nguyên vẹn).

**Trạng thái 19/10/2026:** đã chạy trên dongle theo [RUNBOOK.md](RUNBOOK.md), cả 8 tiêu chí phía
Device PASS (peer là laptop Windows). Báo cáo: [sv1_device_week6_report.md](../../docs/sv1_device_week6_report.md),
bằng chứng: [results/week6](../../results/week6/README.md).

## Cấu trúc

| File | Vai trò | Kiểm trên host |
|---|---|---|
| `frag.c/.h` | Header fragment 8 B, `transfer_id`, reassembler đúng 8 quy tắc §5 (thêm `rx_busy`) | vi sai với `contracts/i1v2_ref/i1_ble_binding.py` |
| `exchange.c/.h` | Máy trạng thái request §6 (timeout `8000 + n_resp × 30` ms, 2 retry, backoff 250/500 ms, chờ kết nối lại 10 s), phân loại echo §9 / response I1 v2 §8.3, counter §11 | `test_week6_host.py`, `test_week6_sim.py` |
| `nonce_store.c/.h` | Record `PROVISION` 0x4901 / `NONCE_STATE` 0x4902, boot §5, cấp sequence theo khối 1024, provisioning an toàn | so byte với `nonce_reservation.py`, mất điện ngẫu nhiên |
| `packets.c/.h` | Dựng request thường / I2/1 bằng `contracts/i2_ref/i2_reference.c` và `contracts/i1v2_ref/i1v2_codec.c` (biên dịch nguyên vẹn) | golden, vector biên, 50 vector SV3 |
| `sha256.c/.h` | SHA-256 để in hash bằng chứng | so với `hashlib` |
| `ble_link.c/.h` | GATT §2, thread gửi riêng `i1_tx` với 4 credit trả trong callback `bt_gatt_notify_cb`, `-ENOMEM`/`-ENOBUFS` nghỉ 2 ms, callback RX chỉ kiểm header + `memcpy` | cần dongle |
| `nonce_nvs.c/.h` | Zephyr NVS trên `storage_partition` 0xDC000 (4 × 4096 B), hook D2, sentinel DFU, marker P0.15 + biến `__noinit` lúc ghi | cần dongle |
| `main.c` | Console lệnh USB CDC, self-test, `RUN`, provisioning, test nonce | cần dongle |
| `host_test/week6_shim.c` | API phẳng cho ctypes; **không** vào firmware | — |

Bảng vector (`week6_vectors.c/.h`, `week6_build.h`) được sinh lúc build vào thư mục report bởi
`../scripts/generate_week6_vectors.py`, sau khi xác thực manifest gói SV3
`mitdb-week6-p1-50-20261016-v1` (`d0914acb…1c36`): 50 vector P1 thật, 4 golden/biên của
`vectors.json`, 15 vector response. Key `00..1f` chỉ dùng cho self-test (`PUBLIC_TEST_ONLY`).

## Lệnh USB CDC (một lệnh một dòng)

| Lệnh | Việc |
|---|---|
| `HELP`, `STATUS`, `STACK` | Banner (build ID, gói vector), link, nonce, cấu hình §7; stack high-water |
| `SELFTEST ENC` | Encoder trên MCU so golden + biên (4), kiểm response §8.3 (15) |
| `SELFTEST P1` | 50 vector: protect/unprotect/encode với key public, in SHA-256 transformed/request, `n80`, DWT |
| `SELFTEST QUANT` | DWT của `week5_quantize` trên `z = q × scale` |
| `MODE ECHO` / `MODE NORMAL` | Echo stream 0x02 (mặc định) / request I1 stream 0x01 chờ response |
| `RUN <n> MIX`, `RUN <n> PLAIN`, `RUN <n> SIZES=a,b,..` | Chạy n application packet; in `PKT`, `RUN END`, `COUNTERS`, `REASM`, `STACK` |
| `I2 ARM` | Cho phép packet I2/1 trong `RUN` (chỉ khi nonce `READY`; arm sau tiêu chí 7) |
| `STOP` | Dừng `RUN`/`NTEST STRESS` giữa chừng |
| `PROV MODE ON` / `OFF`, `PROV KEY <key_id> <sender_id> <64 hex>`, `PROV ERASE` | Provisioning key bench (§4); không in lại key |
| `NONCE`, `NONCE ALLOC <n>` | Trạng thái nonce; cấp thử n sequence |
| `NTEST STRESS <ms> <reboot> [gap_ms]` | Vòng lặp ghi `NONCE_STATE` liên tục; `reboot=1` → `sys_reboot` sau `<ms>` |
| `NTEST FAILWRITE`, `NTEST READBACK`, `NTEST BOOT <hook>` | Hook D2 |
| `NTEST SENTINEL WRITE` / `READ` | Record sentinel 0x49F0 cho test DFU |
| `CONNPARAM <min> <max>`, `DISCONNECT`, `REBOOT` | Xin connection interval (đơn vị 1,25 ms), ngắt BLE, reset mềm |

Marker GPIO (header đo): P0.13 head (không dùng ở tuần 6), P0.15 protect và ghi Flash,
P0.17 đang gửi BLE, P0.20 đang chờ response.

## Hai biến thể build

| Biến thể | Cấu hình | ATT MTU | Byte frame mỗi fragment |
|---|---|---:|---:|
| `default` | `prj.conf` | 247 | 236 |
| `mtu23` | `prj.conf` + `overlay-mtu23.conf` | 23 | 12 |

Windows (WinRT) không cho central chọn MTU, nên tiêu chí 4 (ép MTU 23) do Device giới hạn:
ATT MTU = min(`BT_BUF_ACL_RX_SIZE` − 4, `BT_L2CAP_TX_MTU`). `CONFIG_FLASH_LOAD_SIZE=0xdb000`
làm linker từ chối image vượt `0xDC000`.

## Build và kiểm trên host (không cần dongle)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week6.ps1 -ReportDir <thư-mục-mới> -Variant default
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week6.ps1 -ReportDir <thư-mục-mới> -Variant mtu23
ml\.venv\Scripts\python.exe -B device\scripts\test_week6_host.py
device\host\.venv\Scripts\python.exe -B device\scripts\test_week6_sim.py
device\host\.venv\Scripts\python.exe -B device\scripts\test_week6_checkers.py
```

`build_week6.ps1` ghi `source.json` (commit, cờ dirty), sinh bảng vector, build, chạy
`check_week6_build.py` (18 kiểm tĩnh, gồm build ID có trong `zephyr.bin`) và đóng gói DFU.
Build ngày 18/10/2026 (cây làm việc dirty, chỉ để kiểm): `default` 333 044 B, kết thúc
`0x524f4`, RAM tĩnh 102 284 B; `mtu23` 331 312 B, `0x51e30`, 96 511 B. Build dùng để nghiệm
thu phải làm lại từ commit sạch (xem runbook).

Lưu ý: ngay lúc kết nối MTU là 23; Windows trao đổi lên MTU lớn khoảng 1 s sau. Firmware đọc
`bt_gatt_get_uatt_mtu()` ở đầu **mỗi** transfer (binding §4.1); công cụ laptop chờ MTU ổn định
trước khi gửi lệnh `RUN`.

## Công cụ laptop

Venv riêng `device/host/.venv` (không dùng `ml/.venv`), gói ghim trong
[`requirements-week6-ble.txt`](../scripts/requirements-week6-ble.txt) (`bleak==3.0.2`).
`../scripts/week6_lab.py` điều khiển dongle qua USB CDC và làm BLE central/echo peer (dùng lại
reassembler/fragmenter của `contracts/i1v2_ref/i1_ble_binding.py`); `../scripts/check_week6.py`
kiểm bằng chứng offline.
