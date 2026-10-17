# Firmware tuần 6 — Device–Edge qua BLE (đang xây dựng)

Ứng dụng riêng cho tuần 6 theo [I1 v2](../../contracts/i1_device_edge_packet_v2.md),
[BLE binding v1](../../contracts/i1_ble_binding_v1.md) và
[nonce/provisioning v1](../../contracts/i2_nonce_provisioning_v1.md). Tiêu chí nghiệm thu:
[kế hoạch tuần 6](../../docs/week6_device_edge_plan.md). Không sửa file tuần 3–5 bị khóa hash.

## Trạng thái hiện tại: khung BLE (skeleton)

- Quảng bá `ASI-SV1` kèm UUID service 128 bit; GATT service `74e40001-…`, `RX` (write /
  write without response, từ chối offset ≠ 0), `TX` (notify + CCCD). Một kết nối, không
  pairing. RX hiện chỉ đếm số lần ghi và số byte.
- Console USB CDC chỉ để điều khiển/debug; in `CONNECTED`, `ATT MTU …`, `DISCONNECTED`.
- **Chưa có**: fragment/reassembly, encoder I1 v2, echo, P1, nonce NVS.

## Hai biến thể build

| Biến thể | Cấu hình | ATT MTU cấu hình | Byte frame mỗi fragment |
|---|---|---:|---:|
| `default` | `prj.conf` | 247 | 236 |
| `mtu23` | `prj.conf` + `overlay-mtu23.conf` | 23 | 12 |

Windows (WinRT) không cho central chọn MTU, nên tiêu chí 4 (ép MTU 23) do Device giới hạn:
ATT MTU = min(`BT_BUF_ACL_RX_SIZE` − 4, `BT_L2CAP_TX_MTU`).

`CONFIG_FLASH_LOAD_SIZE=0xdb000` giới hạn vùng ứng dụng ở `0x1000–0xDC000`, nên image
vượt vùng NVS sẽ lỗi ngay ở linker; `check_week6_build.py` kiểm lại từ ELF/bin/.config/DTS.

## Build (không truy cập thiết bị)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week6.ps1 -ReportDir <thư-mục-mới> -Variant default
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week6.ps1 -ReportDir <thư-mục-mới> -Variant mtu23
```

Script từ chối ghi đè thư mục đã có; ghi log, `*.command.json`, `week6_build_check.json` và
ZIP DFU. Nạp DFU và đo trên dongle là bước riêng, chưa làm.

Kết quả build tĩnh ngày 17/10/2026 (khung BLE + in stack, chưa có head/I1;
build ở `D:\HUST\ASI_week6\20261017-skeleton-r4-<biến thể>`):

| Biến thể | `zephyr.bin` | Kết thúc image | Còn trống trước NVS | RAM tĩnh (linker) | SHA-256 `zephyr.bin` |
|---|---:|---:|---:|---:|---|
| `default` | 139.012 B | `0x22f04` | 758.012 B | 40.588 B | `37ae3230…ed04f` |
| `mtu23` | 137.236 B | `0x22814` | 759.788 B | 35.072 B | `f48bacc1…172f6` |

Kiểm trên dongle bằng `scripts/week6_ble_probe.py` (laptop central + log CDC song song):
xem `D:\HUST\ASI_week6\device-session-20261017\`. Đây là kiểm liên kết của khung, chưa
phải loopback 1000 packet của tiêu chí 3.

Lưu ý khi viết phần truyền: ngay lúc kết nối, MTU là 23; Windows trao đổi lên MTU lớn
khoảng 1 s sau. Phải đọc `bt_gatt_get_uatt_mtu()` ở đầu **mỗi** transfer (binding §4.1).

## Công cụ laptop

Venv riêng `device/host/.venv` (không dùng `ml/.venv`), gói ghim trong
[`requirements-week6-ble.txt`](../scripts/requirements-week6-ble.txt) (`bleak==3.0.2`).
