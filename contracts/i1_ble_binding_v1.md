# I1 BLE binding v1 — chuyển frame I1 v2 qua Bluetooth LE GATT

## 1. Trạng thái, phạm vi và vai trò

| Thuộc tính | Giá trị |
|---|---|
| Binding | `I1-BLE/1` (`binding_version=1`), chở frame [I1 v2](i1_device_edge_packet_v2.md) |
| Thiết kế | **APPROVED** — Lê Hải Châu duyệt ngày 15/10/2026 theo quyền trưởng nhóm |
| Triển khai | nRF52840 firmware, công cụ laptop, KV260: **chưa triển khai** |
| Nghiệm thu | [Kế hoạch tuần 6](../docs/week6_device_edge_plan.md); hiện **PENDING** |
| SDK đối chiếu | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 tại `D:\ncs\v3.4.0` (API ở §10 đã kiểm trong header của SDK) |
| Reference/test | [`i1v2_ref/i1_ble_binding.py`](i1v2_ref/i1_ble_binding.py), [`test_i1v2.py`](i1v2_ref/test_i1v2.py) |

Kiến trúc chính thức:

- **nRF52840 Dongle (Device) là BLE peripheral và GATT server.**
- **KV260 (Edge) là BLE central và bên nhận chính thức** khi tích hợp Device–Edge.
- **Laptop Windows là BLE central/echo peer** chỉ để SV1 kiểm thử đường truyền
  tuần 6. Laptop không thay vai trò KV260, không phải gateway và không nằm trên
  đường dữ liệu chính thức. Laptop và KV260 dùng **cùng** GATT, fragment và quy
  tắc của tài liệu này; không có định dạng chỉ dành cho laptop.
- **USB CDC** của dongle chỉ dùng điều khiển/debug (chọn chế độ, in counter,
  provisioning). Dữ liệu đi qua USB CDC không được tính là bằng chứng truyền radio.

Cấu hình tuần 6 có **một kết nối** và **một application request đang chờ** tại
một thời điểm. Liên kết BLE không pairing/mã hóa trong testbed này (§2.4); đây
không phải cấu hình production.

## 2. GATT

### 2.1 UUID và characteristic

Base 128-bit `74e4xxxx-0994-465c-bcd4-b94671a54935` (sinh ngẫu nhiên cho dự án).
Hướng đặt tên theo Device.

| Thành phần | UUID | Thuộc tính | Hướng | Permission (Zephyr) |
|---|---|---|---|---|
| Service `I1 transport` | `74e40001-0994-465c-bcd4-b94671a54935` | Primary | — | — |
| `RX` | `74e40002-0994-465c-bcd4-b94671a54935` | Write Without Response, Write | Central → Device | `BT_GATT_PERM_WRITE` |
| `TX` | `74e40003-0994-465c-bcd4-b94671a54935` | Notify (+ CCCD) | Device → Central | CCCD `BT_GATT_PERM_READ \| BT_GATT_PERM_WRITE` |

Zephyr: `BT_UUID_128_ENCODE(0x74e40001, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)`
(tương tự `...0002`, `...0003`). Không dùng indication, read hay prepared/long
write; write có offset khác 0 bị trả `BT_ATT_ERR_INVALID_OFFSET`.

### 2.2 Advertising và kết nối

- Advertising connectable, tên `ASI-SV1`, UUID service đầy đủ trong advertising
  data; scan response có thể lặp tên. Dừng advertising khi đã có kết nối, bật lại
  khi mất kết nối. `CONFIG_BT_MAX_CONN=1`.
- Central nhận diện Device bằng UUID service + tên, không bằng địa chỉ cố định.
- Device dùng địa chỉ identity static random mặc định (không bật privacy) nên địa
  chỉ ổn định qua reboot; Edge dùng địa chỉ này làm khóa phiên logic (§8).

### 2.3 Sẵn sàng (link ready)

Device chỉ bắt đầu gửi khi: đã kết nối, central đã ghi CCCD bật notification cho
`TX` (`bt_gatt_is_subscribed(..., BT_GATT_CCC_NOTIFY)`), và đọc được ATT MTU
(`bt_gatt_get_uatt_mtu()` khác 0). Central bật notification trước khi ghi `RX`.

### 2.4 Bảo mật liên kết

Không pairing, không bonding, không mã hóa LL trong testbed tuần 6. I2/1 không
thay thế mã hóa. Mọi thiết bị trong vùng phủ sóng có thể quan sát/ghi; chấp nhận
được chỉ vì phạm vi là testbed nội bộ với dữ liệu MIT-BIH công khai.

## 3. Fragment

Mỗi giá trị ATT (một notification `TX` hoặc một write `RX`) là đúng một fragment:

| Offset | Byte | Field | Quy tắc |
|---:|---:|---|---|
| 0 | 1 | `binding_version` | `1` |
| 1 | 1 | `stream` | `0x01` = I1 application, `0x02` = diagnostic echo (§9); giá trị khác bị bỏ |
| 2 | 2 | `transfer_id` (`uint16_le`) | Khác 0, §4.2 |
| 4 | 2 | `offset` (`uint16_le`) | Vị trí byte đầu của fragment trong frame |
| 6 | 2 | `total_length` (`uint16_le`) | Độ dài frame I1; giống nhau ở mọi fragment của một transfer |
| 8 | 1.. | `data` | Ít nhất 1 byte; `offset + len(data) ≤ total_length` |

- Header 8 byte, little-endian. Frame hợp lệ: `36 ≤ total_length ≤ max_frame`;
  `max_frame = 6380` (trần I1 v2) ở cả hai hướng.
- Dung lượng data mỗi fragment theo **ATT MTU thực tế** của kết nối:
  `ATT_MTU − 3 − 8`. Với MTU tối thiểu 23 là 12 byte, nên binding hoạt động khi
  không thương lượng MTU lớn (6380 B → 532 fragment); MTU 247 cho 236 byte
  (28 fragment). Bên gửi có thể gửi fragment ngắn hơn; bên nhận không giả định cỡ
  fragment.
- Fragment chỉ gửi theo thứ tự offset tăng dần, liên tiếp, không chồng lấn.
- Fragment không có CRC riêng; toàn vẹn frame do CRC I1 kiểm sau reassembly.

## 4. Bên gửi

### 4.1 Phân mảnh

Bên gửi đọc ATT MTU khi bắt đầu mỗi transfer và cắt frame thành các fragment
`ATT_MTU − 11` byte data (fragment cuối có thể ngắn hơn). Không gửi frame bị cắt;
frame vượt `max_frame` bị từ chối cục bộ.

### 4.2 `transfer_id`

Mỗi lần truyền một frame (kể cả mỗi lần retry) dùng `transfer_id` mới:
`1, 2, …, 65535, 1, …` (bỏ 0), đếm riêng theo kết nối và hướng, đặt lại khi kết
nối mới. `transfer_id` chỉ thuộc tầng binding; khử trùng ứng dụng dựa trên
`request_id` của I1.

### 4.3 Flow control phía Device (notify)

- Gửi từ **thread riêng** của binding, không gửi từ system workqueue: trong NCS
  3.4.0, `bt_gatt_notify_cb()` gọi từ system workqueue không chờ tài nguyên mà trả
  lỗi, và callback hoàn tất chạy trên system workqueue.
- Credit: semaphore `TX_CREDITS = 4` (không vượt `CONFIG_BT_CONN_TX_MAX`). Lấy một
  credit trước mỗi `bt_gatt_notify_cb()`; callback `func` của notification trả lại
  credit. Chờ credit bằng `k_sem_take(..., K_MSEC(TX_CREDIT_TIMEOUT_MS))`; hết
  thời gian thì hủy transfer (counter `tx_stall`), request vẫn theo cơ chế retry.
- `-ENOMEM`/`-ENOBUFS`: trả credit, `k_sleep(K_MSEC(2))` rồi thử lại trong cùng
  hạn `TX_CREDIT_TIMEOUT_MS`. `-ENOTCONN`: hủy transfer.
- Không `k_busy_wait`, không vòng lặp poll, không `irq_lock()` khi chờ gửi.
- Callback của fragment cuối đánh dấu frame đã giao cho stack; đây là mốc bắt đầu
  timeout response (§6).

### 4.4 Phía central (write without response)

Central (laptop/KV260) ghi `RX` bằng Write Without Response (Windows:
`GattWriteOption.WriteWithoutResponse`; BlueZ: write type `command`) và chờ API
hoàn tất mỗi lần ghi trước khi ghi fragment kế tiếp; Write có response cũng hợp
lệ nhưng chậm hơn. Central phải bật notification, đọc MTU đã thương lượng (Windows
và BlueZ tự thực hiện MTU exchange) và áp dụng cùng công thức `ATT_MTU − 11`.

## 5. Bên nhận và reassembly

Mỗi bên có **một** buffer reassembly cỡ `max_frame` cho mỗi hướng nhận, cấp phát
tĩnh. Quy tắc (reference `Reassembler`):

1. Fragment ≤ 8 byte, `binding_version ≠ 1`, `stream` không được chấp nhận,
   `transfer_id = 0`, `total_length` ngoài `[36, max_frame]` hoặc
   `offset + len(data) > total_length`: bỏ fragment (`malformed_fragment`); nếu
   thuộc transfer đang nhận thì hủy transfer đó.
2. Chưa có transfer: fragment `offset = 0` bắt đầu transfer mới; `offset ≠ 0` bị
   bỏ (`orphan_fragment`); fragment thuộc transfer vừa hoàn tất bị bỏ
   (`duplicate_fragment`).
3. Đang nhận transfer khác: fragment `offset = 0` của `(stream, transfer_id)` mới
   **thay thế** transfer cũ (bên gửi đã bỏ cuộc và retry; `superseded_transfer`);
   fragment khác bị bỏ (`orphan_fragment`).
4. Cùng transfer: `total_length` đổi → hủy. `offset` = số byte đã nhận → nối.
   `offset` nhỏ hơn và byte trùng khớp → bỏ như duplicate; không khớp → hủy
   (`overlap_conflict`). `offset` lớn hơn → hủy (`gap`).
5. Khi đã có ≥ 16 byte: magic phải là `I1PK` và `total_length` trong fixed header
   I1 phải bằng `total_length` của fragment, nếu không hủy
   (`frame_header_mismatch`).
6. Đủ `total_length` byte → giao **nguyên** frame cho tầng trên; không bao giờ
   giao frame thiếu hay ghép từ hai transfer.
7. Không nhận fragment mới trong `REASSEMBLY_TIMEOUT_MS = 2000` → hủy
   (`reassembly_timeout`). Mất kết nối → hủy và quên transfer vừa hoàn tất.
8. Nếu frame hoàn tất trước đó chưa được tầng trên lấy (vi phạm một-request-chờ),
   fragment `offset = 0` mới bị bỏ (`rx_busy`).

Trên Device, callback write của `RX` chạy trong thread RX của Bluetooth: chỉ kiểm
header, `memcpy` tối đa `ATT_MTU − 11` byte vào buffer tĩnh và báo thread ứng dụng
(`k_sem_give`/`k_msgq_put`) khi đủ frame. Không ghi Flash, không gọi
`protect/unprotect`, không log payload trong callback.

ATT trên một kết nối là tin cậy và theo thứ tự; các quy tắc duplicate/thiếu/sai
thứ tự ở trên là phòng thủ để không bao giờ giao sai byte, không phải giả định
rằng radio mất gói.

## 6. Trao đổi ứng dụng, timeout và retry (Device)

Trạng thái mỗi request: `SENDING → WAITING → DONE`, hoặc qua `RETRY_WAIT` quay lại
`SENDING`, hoặc `FAILED`.

- **Timeout response** bắt đầu khi callback hoàn tất của fragment cuối request
  được gọi; dừng khi nhận response hợp lệ theo [I1 v2 §8.3](i1_device_edge_packet_v2.md)
  (hoặc frame echo khớp ở §9). Giá trị mỗi lần thử:
  `T = RESPONSE_TIMEOUT_BASE_MS + n_resp × PER_FRAGMENT_BUDGET_MS`, với `n_resp` là
  số fragment của response mong đợi theo MTU hiện tại (64 B cho inference; bằng
  frame gửi cho echo). Mặc định `8000 + n_resp × 30` ms: inference ở MTU 23 là
  8180 ms; echo 6380 B ở MTU 23 là 23 960 ms.
- **Retry**: hết `T` → chờ backoff rồi gửi lại **nguyên** frame I1 (cùng
  `request_id`, metadata, nonce, transformed bytes; không gọi `protect()` lại,
  không cấp nonce mới) với `transfer_id` mới. Tối đa `MAX_RETRIES = 2` (3 lần
  thử); backoff 250 ms rồi 500 ms. Hết retry → `FAILED`, tính là mất gói.
- **`EDGE_BUSY`**: tính như một lần thử thất bại, retry sau backoff. Các
  `ERROR_RESPONSE` khác là kết quả cuối, không retry.
- **Mất kết nối** khi request chưa xong: lần thử hiện tại thất bại
  (`disconnect_abort`); nếu còn retry, Device gửi lại ngay khi link ready trở lại
  và sau backoff; chờ kết nối lại tối đa `RECONNECT_WAIT_MS = 10000` mỗi lần, quá
  hạn → `FAILED`.
- Response có `request_id` không phải request đang chờ, hoặc tới sau `DONE`, bị bỏ
  (`stale_response`/`duplicate_response`).

**Retry horizon** của một `request_id` (từ lần gửi đầu tới lần retry cuối có thể):
`H = (1 + MAX_RETRIES) × T + Σbackoff + MAX_RETRIES × RECONNECT_WAIT_MS`. Với
inference và mọi MTU ≥ 23, `H ≤ 3 × 8180 + 750 + 20000 = 45 290` ms. Device không
bao giờ gửi lại một `request_id` sau `H`, và không gửi lại request cũ khi đã bắt
đầu request kế tiếp.

## 7. Bảng cấu hình (giá trị bench ban đầu)

Các giá trị dưới đây là **cấu hình bench cần kiểm chứng**, không phải số đo hiệu
năng. Chúng được ghi vào báo cáo mỗi lần chạy; thay đổi phải giữ ràng buộc ở cuối
bảng.

| Tham số | Mặc định | Miền cho phép | Bên |
|---|---:|---|---|
| `RESPONSE_TIMEOUT_BASE_MS` | 8000 | 1000–60000 | Device |
| `PER_FRAGMENT_BUDGET_MS` | 30 | 7–100 | Device |
| `MAX_RETRIES` | 2 | 0–5 | Device |
| Backoff lần thứ k | `250 × 2^(k−1)` ms | gốc 50–5000 | Device |
| `RECONNECT_WAIT_MS` | 10000 | 1000–60000 | Device |
| `REASSEMBLY_TIMEOUT_MS` | 2000 | 200–10000, `< RESPONSE_TIMEOUT_BASE_MS` | Cả hai |
| `TX_CREDITS` | 4 | 1..`CONFIG_BT_CONN_TX_MAX` | Device |
| `TX_CREDIT_TIMEOUT_MS` | 2000 | 100–10000 | Device |
| `max_frame` | 6380 | `≤ 6380` | Cả hai |
| `EDGE_INFERENCE_DEADLINE_MS` | 4000 | `< RESPONSE_TIMEOUT_BASE_MS` | Edge |
| `DUPLICATE_CACHE_TTL_MS` | 60000 | `≥ H_max + 5000` | Edge |
| `DUPLICATE_CACHE_ENTRIES` | 16 | ≥ 2 | Edge |

Ràng buộc bắt buộc: `DUPLICATE_CACHE_TTL_MS ≥ H_max + 5000`, trong đó `H_max` tính
với response 64 B ở MTU 23 (hiện 45 290 + 5000 ≤ 60 000). Test
`test_timer_configuration_covers_retry_horizon` kiểm ràng buộc này trên reference.

## 8. Duplicate cache tại Edge

- Phiên logic = địa chỉ identity BLE của Device (§2.2). Khóa cache =
  `(phiên, request_id)`, không phụ thuộc `transfer_id` hay kết nối, nên retry sau
  khi kết nối lại vẫn trúng cache.
- Fingerprint = SHA-256 của toàn bộ frame request. Cùng khóa, cùng fingerprint:
  đang `IN_PROGRESS` thì gắn vào cùng công việc; đã xong thì gửi lại **đúng bytes**
  response đã cache (kể cả `ERROR_RESPONSE`). Cùng khóa, khác fingerprint:
  `DUPLICATE_CONFLICT`, không inference, không ghi đè entry.
- Tạo entry ở bước B4 của [I1 v2 §7.2](i1_device_edge_packet_v2.md), trước khi
  chạy tail. `EDGE_BUSY` không tạo/giữ entry.
- Hết hạn: `created + DUPLICATE_CACHE_TTL_MS`. Khi đầy: bỏ entry hết hạn trước;
  sau đó bỏ entry `DONE` cũ nhất mà phiên của nó đã gửi `request_id` khác (Device
  không bao giờ retry request cũ); nếu vẫn đầy, request mới nhận `EDGE_BUSY`.
  Không bao giờ bỏ entry `IN_PROGRESS`.
- Bảo đảm: không chạy tail lặp cho retry **trong retry horizon** của Device.
  Không hứa exactly-once vô hạn; duplicate tới sau khi entry bị bỏ có thể được xử
  lý lại, và Device không tạo duplicate như vậy theo §6.
- Cache không phải cơ chế chống replay: không có xác thực.

## 9. Chế độ diagnostic echo (`stream = 0x02`)

Echo là chế độ chẩn đoán đường truyền, **không** phải inference và không thay
response I1.

- Device bật echo bằng lệnh điều khiển qua USB CDC hoặc build cấu hình riêng; ở
  chế độ này Device gửi frame I1 v2 hợp lệ trên `stream 0x02`.
- Peer echo (laptop hoặc KV260 khi chạy diagnostic) reassemble frame `stream 0x02`
  và gửi lại **đúng bytes** đó trên `stream 0x02` với `transfer_id` của mình;
  không parse, không sửa, không chạy inference; nên tự kiểm CRC I1 và ghi log kết
  quả để tách lỗi chiều đi/chiều về. Công cụ echo-only bỏ và đếm frame
  `stream 0x01`.
- Device so sánh frame echo: CRC I1 đúng (counter `crc_fail` nếu sai) và trùng
  từng byte với frame đã gửi (`byte_mismatch` nếu khác). Timeout/retry như §6 với
  `n_resp` bằng số fragment của frame gửi.
- Ở chế độ thường, Device bỏ và đếm frame `stream 0x02`; ở chế độ echo, frame
  `stream 0x01` bị bỏ và đếm. Không lúc nào một frame echo được hiểu là response.

## 10. Đối chiếu NCS 3.4.0

Đã kiểm sự tồn tại và chữ ký trong `D:\ncs\v3.4.0\zephyr\include` (không chép từ
phiên bản khác):

| Mục đích | API / Kconfig |
|---|---|
| Khai báo service | `BT_GATT_SERVICE_DEFINE`, `BT_GATT_CHARACTERISTIC`, `BT_GATT_CCC`, `BT_UUID_128_ENCODE` |
| Thuộc tính | `BT_GATT_CHRC_WRITE_WITHOUT_RESP` (`0x04`), `BT_GATT_CHRC_WRITE`, `BT_GATT_CHRC_NOTIFY` (`0x10`); cờ write `BT_GATT_WRITE_FLAG_CMD` |
| Gửi notify có callback | `bt_gatt_notify_cb(conn, &struct bt_gatt_notify_params{.attr,.data,.len,.func,.user_data})` |
| Subscription, MTU | `bt_gatt_is_subscribed()`, `bt_gatt_get_uatt_mtu()`, `struct bt_gatt_cb.att_mtu_updated` |
| Kết nối, advertising | `BT_CONN_CB_DEFINE`, `bt_le_adv_start()`, `bt_conn_le_data_len_update()`, `bt_conn_le_phy_update()` |
| Request ID ngẫu nhiên | `sys_csrand_get()` |
| Kconfig dự kiến (kiểm khi build tuần 6) | `CONFIG_BT=y`, `CONFIG_BT_PERIPHERAL=y`, `CONFIG_BT_MAX_CONN=1`, `CONFIG_BT_L2CAP_TX_MTU=247`, `CONFIG_BT_BUF_ACL_RX_SIZE=251`, `CONFIG_BT_BUF_ACL_TX_SIZE=251`, `CONFIG_BT_CTLR_DATA_LENGTH_MAX=251`, `CONFIG_BT_CONN_TX_MAX ≥ 4`, `CONFIG_BT_USER_DATA_LEN_UPDATE=y`, `CONFIG_BT_USER_PHY_UPDATE=y` |

Firmware tuần 6 là ứng dụng riêng (như `device/week5/`), không sửa file tuần 3–5
đang bị hash. Ứng dụng có radio không khóa IRQ quanh phép tính head như firmware
debug USB tuần 4–5 ([device/README](../device/README.md)).

## 11. Counter và báo cáo

Mỗi lần chạy ghi: cấu hình §7, MTU, PHY và connection interval quan sát được,
firmware/tool hash, và các counter sau, theo **application packet** (không theo
fragment):

| Counter | Ý nghĩa |
|---|---|
| `planned` | Số application packet dự kiến gửi (mẫu số) |
| `sent_first` | Packet đã gửi lần đầu |
| `retries` | Tổng số lần gửi lại |
| `timeouts` | Số lần thử hết `T` |
| `disconnect_abort`, `tx_stall` | Lần thử bị hủy do mất kết nối / hết credit |
| `completed` | Packet nhận đủ, CRC đúng, bytes khớp (echo) hoặc response hợp lệ |
| `failed` | Packet hết retry; vẫn nằm trong mẫu số |
| `crc_fail`, `byte_mismatch` | Frame nhận về sai CRC / sai byte |
| `duplicate_response`, `stale_response`, `invalid_response` | Response bị bỏ |
| Counter reassembly §5 | Theo lý do |

Tỉ lệ thành công = `completed / planned`. Không loại packet mất khỏi mẫu số và
không dùng số fragment thay số packet.

## 12. Kiểm thử reference

`python -B contracts/i1v2_ref/test_i1v2.py` kiểm trên host: phân mảnh/reassembly
với MTU 23, 24, 185, 247, 517 cho frame 44–6380 B; duplicate, thiếu, mồ côi, chồng
lấn sai, sai header, fragment hỏng, timeout, mất kết nối, retry với `transfer_id`
mới; 400 frame qua mô phỏng link có mất/lặp/đảo fragment không bao giờ giao sai
bytes; và ràng buộc thời gian §7. **Đây không phải bằng chứng radio**: chưa có
phép đo BLE, MTU/throughput thực hay interoperability Windows/KV260.
