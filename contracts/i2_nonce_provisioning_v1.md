# I2/1 nonce và provisioning trên nRF52840 — thiết kế v1

## 1. Trạng thái và phạm vi

| Thuộc tính | Giá trị |
|---|---|
| Thiết kế | **APPROVED** — Lê Hải Châu duyệt ngày 15/10/2026 theo quyền trưởng nhóm |
| Triển khai firmware, ghi Flash, provision key | **Chưa thực hiện**. Lượt thiết kế này không ghi Flash và không provision key |
| Persistence/reboot/mất điện | `NOT_ACCEPTED` (registry `runtime.nonce_persistence_reboot`) cho tới khi có kiểm thử ở §8 |
| Áp dụng | Device SV1, key label `65537`, sender `131073`, profile `1296651265`, revision `mitdb-week5-i2-registry-v1-r1` |
| Reference model | [`i1v2_ref/nonce_reservation.py`](i1v2_ref/nonce_reservation.py) (host, không phải driver NVS) |

Tài liệu cụ thể hóa lifecycle nonce đã có trong [I2/1 §3](i2_protection_v1.md) và
registry (`sender_scope.nonce_lifecycle`): nonce =
`sender_id:uint32_le || sequence:uint64_le` (12 byte); sequence bắt đầu từ 1;
không dùng lại nonce cho transform mới trong cùng key, kể cả khi đổi split; retry
gửi lại nguyên bytes; reboot bỏ phần chưa dùng của dải đã đặt trước; lỗi
persistence hoặc hết counter thì dừng.

## 2. Bản đồ bộ nhớ thực tế và vùng lưu

Kiểm từ `nrf52840dongle_nrf52840.dts` của NCS 3.4.0 và build hiện có:

| Vùng | Địa chỉ | Kích thước | Ghi chú |
|---|---|---:|---|
| Nordic MBR | `0x00000–0x00FFF` | 4 KiB | Có sẵn trên dongle |
| Ứng dụng (build hiện tại) | từ `0x01000` | — | `CONFIG_FLASH_LOAD_OFFSET=0x1000`, `USE_DT_CODE_PARTITION=n`, không MCUboot, nạp qua USB DFU của Nordic |
| `mcuboot`/`image-0`/`image-1` (DTS) | `0x01000–0xDBFFF` | — | Phân vùng DTS cho phương án MCUboot; dự án không dùng MCUboot |
| **`storage_partition`** | **`0xDC000–0xDFFFF`** | **16 KiB** | Nhãn DTS `storage_partition`, 4 trang × 4096 B |
| Nordic USB bootloader | `0xE0000–0xFBFFF` | 112 KiB | Không ghi |
| Không phân vùng trong DTS | `0xFC000–0xFDFFF` | 8 KiB | Không dùng |
| Settings MBR/bootloader | hai trang cuối Flash | 8 KiB | Không ghi |

Kích thước `zephyr.bin` đã build: Active 49 244 B, tuần 3 84 072 B, tuần 4
523 424 B, tuần 5 524 180 B (kết thúc khoảng `0x80F94`). Firmware tuần 6 thêm
Bluetooth nên sẽ lớn hơn; giới hạn bắt buộc:

- **Image phải kết thúc trước `0xDC000`**, tức `zephyr.bin ≤ 0xDC000 − 0x1000 =
  897 024 B`. Script build tuần 6 phải kiểm giới hạn này từ ELF/map và từ chối
  đóng gói nếu vượt.
- Bootloader USB của Nordic có bảo toàn vùng `0xDC000–0xDFFFF` khi DFU hay không
  là **chưa kiểm chứng** trên dongle của dự án; kiểm bằng sentinel ở §8 trước khi
  coi state là bền qua DFU.

**Quyết định:** dùng Zephyr NVS trên `storage_partition` (4 sector × 4096 B),
mount bằng `PARTITION_DEVICE(storage_partition)` và
`PARTITION_OFFSET(storage_partition)` (các macro `FIXED_PARTITION_*` đã deprecated
trong Zephyr 4.4). Header là `<zephyr/kvss/nvs.h>`; `<zephyr/fs/nvs.h>` chỉ còn là
header deprecated.

Kconfig: `CONFIG_FLASH=y`, `CONFIG_FLASH_MAP=y`, `CONFIG_FLASH_PAGE_LAYOUT=y`,
`CONFIG_NVS=y`, `CONFIG_NVS_DATA_CRC=y`, **`CONFIG_NVS_INIT_BAD_MEMORY_REGION=n`**
(không tự khởi tạo lại vùng hỏng). Khi dùng SoftDevice Controller, NCS mặc định
`CONFIG_SOC_FLASH_NRF_RADIO_SYNC_MPSL`, nên ghi/xóa Flash được xếp vào timeslot
không xung đột radio; lệnh ghi có thể chặn thread gọi, nên chỉ gọi từ thread ứng
dụng, không từ ISR, callback Bluetooth hay system workqueue.

## 3. Record lưu trữ

Hai record NVS, mỗi record ghi nguyên khối (NVS chỉ coi record hợp lệ khi ATE đã
ghi xong). Mọi số little-endian; CRC là CRC-32/ISO-HDLC trên các byte đứng trước,
ngoài CRC dữ liệu của `CONFIG_NVS_DATA_CRC`.

`PROVISION` — NVS ID `0x4901`, 52 B:

| Offset | Byte | Field |
|---:|---:|---|
| 0 | 4 | magic `I2KY` |
| 4 | 1 | `record_version = 1` |
| 5 | 3 | reserved 0 |
| 8 | 4 | `key_id` |
| 12 | 4 | `sender_id` |
| 16 | 32 | key material |
| 48 | 4 | CRC-32 của byte 0..47 |

`NONCE_STATE` — NVS ID `0x4902`, 36 B:

| Offset | Byte | Field |
|---:|---:|---|
| 0 | 4 | magic `I2NS` |
| 4 | 1 | `record_version = 1` |
| 5 | 3 | reserved 0 |
| 8 | 4 | `key_id` |
| 12 | 4 | `sender_id` |
| 16 | 8 | `reserved_through` (`uint64`): mọi sequence `≤` giá trị này có thể đã được dùng |
| 24 | 8 | `key_check` = 8 byte đầu của ChaCha20 block 0 với key và nonce 12 byte 0 |
| 32 | 4 | CRC-32 của byte 0..31 |

`key_check` gắn state với đúng key material mà không lộ key; nonce toàn 0 không
bao giờ là nonce transform vì `sender_id ≠ 0`. Với key public `00..1f`,
`key_check = 39fd2b7dd9c5196a`.

## 4. Provisioning

1. Key 32 byte sinh ngoài thiết bị bằng CSPRNG của máy bench (ví dụ
   `secrets.token_bytes(32)`), lưu trong file ngoài repository với quyền đọc hạn
   chế; không commit, không đưa vào log, vector hay issue.
2. `key_id`/`sender_id` phải là cặp đã cấp trong registry đang duyệt (hiện
   `65537`/`131073`); firmware từ chối cặp khác.
3. Truyền key vào dongle qua USB CDC ở **chế độ provisioning** bật tường minh
   (không qua BLE, không qua I1). Firmware không echo key; chỉ in `key_id`,
   `sender_id`, `key_check`.
4. Nếu NVS không mount được vì `storage_partition` chứa dữ liệu không phải NVS
   (dongle chưa từng dùng vùng này), operator có thể ra lệnh xóa toàn bộ
   `storage_partition` trong chế độ provisioning. Đây là bước khởi tạo có chủ
   đích, không bao giờ tự chạy khi boot.
5. Firmware ghi `NONCE_STATE` với `reserved_through = 0` trước, rồi `PROVISION`,
   đọc lại và so sánh cả hai. Provisioning chỉ thành công khi cả hai khớp.
6. Edge nhận cùng key qua kênh tin cậy ngoài băng (sao chép thủ công, SSH), lưu
   file quyền hạn chế; hai bên đối chiếu `key_check`, không đối chiếu key.
7. Provisioning lại sau khi state mất/hỏng hoặc khi hết counter phải dùng **key
   mới và cặp `key_id`/`sender_id` mới** do registry revision mới cấp; chỉ đổi nhãn
   `key_id` là không đủ. Registry hiện chưa có cặp dự phòng, nên sự cố đó cần trưởng
   nhóm cấp revision mới trước khi bật lại I2.

Mất điện giữa bước 5: chỉ có `NONCE_STATE` mới, `PROVISION` cũ hoặc thiếu → boot
báo `STATE_KEY_MISMATCH`/`UNPROVISIONED`; chưa có sequence nào được dùng với key
mới nên provisioning lại cùng key là an toàn khi `reserved_through` vẫn bằng 0.

## 5. Boot và cấp sequence

Boot:

1. Mount NVS. Lỗi mount → I2 tắt (`FAULT`). Không tự format.
2. Đọc `PROVISION`. Thiếu → `UNPROVISIONED`: chỉ cho request thường (`flags=0`).
3. Đọc `NONCE_STATE`. Thiếu, sai CRC/magic/version/reserved, khác
   `key_id`/`sender_id`, `key_check` không khớp key, hoặc cặp ID ngoài registry →
   `FAULT`: I2 tắt cho tới khi provisioning hợp lệ theo §4. Firmware **không** tự
   tạo state mới.
4. Đặt trong RAM `next = reserved_through + 1`, `limit = reserved_through`. Phần
   chưa dùng của dải trước reboot bị bỏ.

Cấp sequence (`allocate()`, giữ `k_mutex`, chỉ thread gửi I1 gọi):

1. Nếu đã `FAULT` → dừng, không phát I2 (lỗi chốt tới reboot).
2. Nếu `next > limit`: nếu `reserved_through > 2^64 − 1 − 1024` → `EXHAUSTED`,
   dừng. Ngược lại ghi `NONCE_STATE` với `reserved_through + 1024`, đọc lại và so
   sánh. `nvs_write()` trả số âm, trả 0 (không ghi gì, bất thường vì giá trị luôn
   tăng) hoặc đọc lại khác → `FAULT`, dừng. Thành công → `limit = reserved_through`
   mới.
3. Trả `next`, tăng `next`. Nonce = `sender_id || sequence`.

Sequence chỉ được dùng **sau** khi giới hạn chứa nó đã được commit. Mỗi transform
mới (mọi split) gọi `allocate()` đúng một lần; retry dùng lại packet đã lưu và
không gọi `allocate()`/`protect()`.

| Thời điểm mất điện / lỗi | Sau reboot | Hệ quả |
|---|---|---|
| Trước khi record mới commit | Đọc giới hạn cũ; không sequence nào vượt giới hạn cũ từng được dùng | An toàn |
| Sau commit, trước khi dùng | Đọc giới hạn mới; `next` vượt mọi giá trị có thể đã dùng | Bỏ tối đa 1024 sequence |
| Giữa lúc dùng dải | Như trên | An toàn, bỏ phần còn lại |
| Lỗi ghi/đọc lại | Không reboot: `FAULT` chốt, I2 dừng | Không phát I2 |
| Hai lời gọi đồng thời | `k_mutex` tuần tự hóa | Không trùng sequence |
| Hết counter | `EXHAUSTED` | Dừng tới khi provisioning key/sender mới |

Tuổi thọ (ước lượng, chưa đo): mỗi lần đặt trước ghi khoảng 36 + 4 (CRC dữ liệu)
+ 8 (ATE) byte; 4 trang × 10 000 chu kỳ xóa (theo datasheet nRF52840) cho cỡ hàng
triệu lần đặt trước, mỗi lần 1024 sequence.

## 6. Bảo mật và giới hạn

- Key nằm dạng rõ trong Flash nội. Firmware dự án không cấu hình APPROTECT và
  trạng thái APPROTECT của dongle chưa được kiểm; kể cả khi bật, dự án không coi đó
  là bảo vệ key. NVS **không** bảo đảm bí mật key.
- Không chống rollback có chủ đích: kẻ ghi lại được bản Flash cũ có thể làm lặp
  nonce. Thiết kế chỉ chống lặp nonce do reboot, mất điện và lỗi ghi thông thường.
- Ghi đè `storage_partition` một phần (ví dụ do DFU) có thể làm NVS trả record cũ
  hơn; đó là lý do giới hạn kích thước image và kiểm sentinel DFU ở §8 là bắt buộc.
- I2/1 vẫn chỉ là che giấu có khóa; nonce đúng không biến nó thành mã hóa.

## 7. Request ID

`request_id` không cần lưu bền: Device khởi tạo từ `sys_csrand_get()` (khác 0)
mỗi lần boot, tăng dần và bỏ 0 khi wrap ([I1 v2 §11](i1_device_edge_packet_v2.md)).

## 8. Kiểm thử bắt buộc trước khi bật truyền I2/1

Reference host (`test_i1v2.py`, lớp `NonceReservationTests`) đã kiểm: layout
record; sequence bắt đầu 1; reboot bỏ dải chưa dùng; 300 chu kỳ reboot với mất
điện ngẫu nhiên trước/sau commit không lặp sequence; lỗi ghi chốt dừng; state
thiếu/hỏng/khác key không bị khởi tạo lại; ID ngoài registry; hết counter. Đây là
mô hình, **không** chứng minh hành vi Flash thật.

Trên dongle (chưa thực hiện):

1. Build kiểm image kết thúc trước `0xDC000`.
2. Provision bằng key test riêng cho bench (không phải key public của vector).
3. Ít nhất 100 lần reset (nút RESET/ngắt nguồn USB) xen giữa các lần cấp, kể cả
   ngắt nguồn trong lúc ghi `NONCE_STATE` (kích hoạt bằng lệnh test có GPIO marker
   để canh thời điểm); log mọi sequence đã phát qua USB CDC; kiểm không có
   sequence nào lặp hoặc giảm.
4. Mô phỏng lỗi ghi (build test trả lỗi từ lớp lưu trữ) → I2 dừng, không phát.
5. Xóa/hỏng record → `FAULT`, không tự khởi tạo.
6. DFU một image mới rồi kiểm `NONCE_STATE` và một record sentinel còn nguyên.

Chỉ sau khi 1–6 đạt mới được đổi `runtime.nonce_persistence_reboot` trong một
revision registry mới; tài liệu này không tự đổi trạng thái đó.
