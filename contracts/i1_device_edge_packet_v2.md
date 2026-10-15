# I1 v2 — packet Device–Edge mang activation INT8 và I2/1

## 1. Trạng thái và nguồn hiện hành

| Thuộc tính | Giá trị |
|---|---|
| Contract ID / `protocol_version` | `I1` / `2` |
| Thiết kế | **APPROVED** — Lê Hải Châu (trưởng nhóm, owner SV1) duyệt ngày 15/10/2026 theo quyền quyết định của trưởng nhóm |
| Triển khai | Device (nRF52840) và Edge (KV260): **chưa triển khai** |
| Nghiệm thu kỹ thuật | Theo dõi riêng trong [kế hoạch tuần 6](../docs/week6_device_edge_plan.md); hiện **PENDING** |
| `FROZEN` | Chưa. Theo quy tắc trạng thái của [I1 v1 §1](i1_device_edge_packet_v1.md), cần thêm xác nhận kỹ thuật của Trung (Edge) và Kỳ Anh (tensor/quantization) sau khi có triển khai |
| Deployment profile | [Approved registry](sv3_week5_approved_registry_v2.json) revision `mitdb-week5-i2-registry-v1-r1`, SHA-256 `79392b6db73cde6d83eadb1f265f14102888ebdbf8ea1b72b6c127c5566eed24` |
| Transport | [I1 BLE binding v1](i1_ble_binding_v1.md) |
| Nonce/key | [I2/1 nonce và provisioning v1](i2_nonce_provisioning_v1.md) |
| Reference/test | [`i1v2_ref/`](i1v2_ref/test_i1v2.py) |

**Tài liệu này là đặc tả I1 dùng cho mọi triển khai mới.** Các tài liệu sau được
giữ nguyên byte vì nằm trong receipt lịch sử và chỉ còn giá trị tham chiếu:
[I1 v1](i1_device_edge_packet_v1.md) (`protocol_version=1`),
[addendum r1](i1_device_edge_packet_v1_addendum_r1.md) và
[đề xuất I1 v2](i1_device_edge_packet_v2_proposal.md). Phần nào không được viết
lại ở đây (định nghĩa enum dtype/layout/scheme, công thức quantization §8.3,
tham số CRC §10.1, quy tắc serialize little-endian §6.3) giữ **nguyên nghĩa**
như I1 v1 và được dẫn theo số mục của I1 v1. Mọi mục OPEN của addendum r1 §6
được đóng tại đây (bảng ở §13).

Phạm vi: testbed nội bộ ASI/MIT-BIH theo registry (`production_authorized=false`,
`external_systems_authorized=false`). Tài liệu không mở rộng phạm vi đó.

## 2. Version gating

- Magic `I1PK`, fixed header 32 byte, little-endian, CRC-32/ISO-HDLC như I1 v1.
- `protocol_version = 2`. Receiver của profile này chỉ chấp nhận version 2.
  Packet version khác có envelope và CRC hợp lệ nhận `UNSUPPORTED_VERSION`;
  receiver **không** parse lại packet đó theo layout v1 và không có fallback
  ngầm giữa v1 và v2 theo bất kỳ hướng nào (kể cả khi thấy hoặc không thấy flag
  I2). Device chỉ chấp nhận response version 2.
- `flags` của `INFERENCE_REQUEST`: `0x0000` (tensor thường) hoặc `0x0002`
  (`I2_TRANSFORMED`). Bit `0x0001` (tên reserved `PROTECTED_PAYLOAD` của v1)
  **không được dùng**; mọi giá trị khác hai giá trị trên nhận
  `UNSUPPORTED_FLAGS`. Response/error: `flags = 0`.
- I2/1 là che giấu có khóa, **không** phải mã hóa hay xác thực. CRC chỉ phát hiện
  lỗi ngẫu nhiên. Không packet nào được mô tả là encrypted/authenticated.

## 3. Frame và fixed header

```text
[fixed_header 32][metadata metadata_length][nonce nonce_length][payload payload_length][crc32 4]
```

Fixed header giữ đúng offset/kiểu của I1 v1 §6.1; chỉ khác giá trị:

| Offset | Field | Giá trị v2 |
|---:|---|---|
| 0 | `magic` | `49 31 50 4b` |
| 4 | `protocol_version` | `0x02` |
| 5 | `message_type` | `0x01` request, `0x02` response, `0x03` error |
| 6 | `flags` (`uint16_le`) | request `0x0000` hoặc `0x0002`; response/error `0` |
| 8 | `header_length` (`uint16_le`) | `32 + metadata_length + nonce_length` |
| 10 | `reserved_0` | 0 |
| 12 | `total_length` (`uint32_le`) | `header_length + payload_length + 4` |
| 16 | `request_id` (`uint32_le`) | khác 0; giữ nguyên qua retry và response |
| 20 | `metadata_length` (`uint32_le`) | §4 hoặc 8 cho response/error |
| 24 | `payload_length` (`uint32_le`) | request `C×L`; response `20`; error `0` |
| 28 | `nonce_length` (`uint16_le`) | `12` nếu `flags=0x0002`, ngược lại `0` |
| 30 | `reserved_1` | 0 |

CRC tính trên byte `[0, total_length−4)` (header, metadata, nonce, payload), ghi
`uint32_le` ở 4 byte cuối; check value `123456789 → 0xcbf43926`. Receiver dùng số
học 64 bit cho mọi đẳng thức độ dài.

## 4. Request metadata

Thứ tự cố định: `model_profile_id`, tensor metadata I1 (I1 v1 §7–8, dịch offset
+4), rồi descriptor I2/1 nếu có. Không có byte thừa. Với profile này mọi
request là `INT8`, `NCL`, `ndim=3`, `[1,C,L]`, `AFFINE_PER_CHANNEL`, axis 1.

| Packet offset | Metadata offset | Byte | Field | Giá trị |
|---:|---:|---:|---|---|
| 32 | 0 | 4 | `model_profile_id` (`uint32_le`) | `1296651265` (`0x4d495401`) |
| 36 | 4 | 2 | `split_id` (`uint16_le`) | wire ID 256..266 (§5) |
| 38 | 6 | 1 | `dtype` | `0x02` INT8 |
| 39 | 7 | 1 | `layout` | `0x01` NCL |
| 40 | 8 | 1 | `ndim` | `3` |
| 41 | 9 | 1 | `quantization_scheme` | `0x02` AFFINE_PER_CHANNEL |
| 42 | 10 | 1 | `quantization_axis` (`int8`) | `1` |
| 43 | 11 | 1 | `reserved_tensor` | `0` |
| 44 | 12 | 4 | `element_count` | `C×L` |
| 48 | 16 | 12 | `dimensions[3]` | `1, C, L` |
| 60 | 28 | 4 | `quant_count` | `C` |
| 64 | 32 | `4C` | `scales[C]` (`float32_le`) | §6 |
| `64+4C` | `32+4C` | `4C` | `zero_points[C]` (`int32_le`) | tất cả `0` |
| `64+8C` | `32+8C` | 28 | descriptor I2/1 (chỉ khi `flags=0x0002`) | [I2/1 §4](i2_protection_v1.md) |

| Đại lượng | Request thường (`flags=0`) | Request I2/1 (`flags=0x0002`) |
|---|---|---|
| `metadata_length` | `32 + 8C` | `60 + 8C` |
| `nonce_offset` | — (`nonce_length=0`) | `92 + 8C` |
| `header_length` = `payload_offset` | `64 + 8C` | `104 + 8C` |
| `crc_offset` | `64 + 8C + C·L` | `104 + 8C + C·L` |
| `total_length` | `68 + 8C + C·L` | `108 + 8C + C·L` |

Nonce (12 byte, chỉ request I2/1) = `sender_id:uint32_le || sequence:uint64_le`
(I2/1 §3). Descriptor lặp lại `model_profile_id`, `split_id`, dtype/layout, `N=1`,
`C`, `L`, `payload_length`; mọi bản sao phải khớp tensor metadata. Payload I2/1 là
transformed bytes, cùng `C×L` byte với tensor gốc; request I2/1 dài hơn request
thường đúng 40 byte (descriptor 28 + nonce 12). Không có tag.

## 5. Split, shape wire và kích thước theo registry

Wire representation luôn là NCL `[1,C,L]`. `s9` và `s10` (shape gốc NC) đi trên
wire là `[1,32,1]` và `[1,5,1]`; Edge reshape `[1,C,1] → [1,C]` khi tail cần NC,
**không đổi thứ tự phần tử**. Logical `s` không xuất hiện trên wire; split ID
logical (ví dụ `10`) bị từ chối `UNSUPPORTED_SPLIT`.

| `s` | `split_id` | `[1,C,L]` | Payload | `total` thường | `total` I2/1 | Fragment I2/1 MTU 23 / 247 | Thực thi |
|---:|---:|---|---:|---:|---:|---:|---|
| 0 | 256 | `[1,1,360]` | 360 | 436 | 476 | 40 / 3 | Device head / Edge tail |
| 1 | 257 | `[1,16,360]` | 5760 | 5956 | 5996 | 500 / 26 | Device head / Edge tail |
| 2 | 258 | `[1,16,180]` | 2880 | 3076 | 3116 | 260 / 14 | Device head / Edge tail |
| 3 | 259 | `[1,32,180]` | 5760 | 6084 | **6124** | 511 / 26 | Device head / Edge tail |
| 4 | 260 | `[1,32,90]` | 2880 | 3204 | 3244 | 271 / 14 | Device head / Edge tail |
| 5 | 261 | `[1,48,90]` | 4320 | 4772 | 4812 | 401 / 21 | Device head / Edge tail |
| 6 | 262 | `[1,48,45]` | 2160 | 2612 | 2652 | 221 / 12 | Device head / Edge tail |
| 7 | 263 | `[1,64,45]` | 2880 | 3460 | 3500 | 292 / 15 | Device head / Edge tail |
| 8 | 264 | `[1,64,22]` | 1408 | 1988 | 2028 | 169 / 9 | Device head / Edge tail |
| 9 | 265 | `[1,32,1]` | 32 | 356 | 396 | 33 / 2 | Device head / Edge tail |
| 10 | 266 | `[1,5,1]` | 5 | 113 | 153 | 13 / 1 | Device-only / empty-tail |

Số fragment theo [BLE binding §3](i1_ble_binding_v1.md): mỗi fragment mang
`ATT_MTU − 11` byte frame. Bảng được sinh và kiểm bởi `i1v2_ref/make_vectors.py`.

**s10 là device-only.** Bình thường Device tự xử lý logits s10 và không gửi gì.
Gửi s10 chỉ dùng cho diagnostic; Edge không tạo, không nạp và không chạy
`tail_s10`, mà trả `SCORE_VECTOR` là chính 5 giá trị sau giải lượng tử (identity,
§8.2). Không giả lập chạy DPU cho s10.

## 6. Quantization trên wire

- Đối xứng INT8: `q ∈ [-127,127]`, `zero_point = 0` cho mọi kênh, axis 1 (kênh),
  `quant_count = C`. `x̂ = q × scale[c]`, không round-trip qua FP16 lần nữa.
- `scales[c]` là giá trị FP16 đã lưu/reload, mở rộng **chính xác** sang
  `float32_le`. Receiver chấp nhận khi và chỉ khi giá trị là FP16 normal dương:
  `2^-14 ≤ scale ≤ 65504` và mantissa FP32 có 13 bit thấp bằng 0. Từ chối 0, âm,
  NaN, ∞, subnormal FP16, > 65504 và giá trị FP32 không biểu diễn được trong FP16.
- **Unprotect trước, kiểm q sau, dequantize cuối.** Nếu `flags=0x0002`, Edge
  đảo I2/1 để lấy lại tensor q; scale/zero point thuộc **kênh gốc**, không thuộc
  vị trí kênh đã hoán vị. Tensor q chứa `q = -128` (byte `0x80`) bị từ chối
  `UNSUPPORTED_QUANTIZATION` (`0x000c`), không dequantize, không chạy tail.
- Quy tắc `-128` chỉ áp dụng cho tensor q. Byte `0x80` hợp lệ trong transformed
  payload, nonce, header, metadata, CRC và mọi phần khác của frame.

## 7. Thứ tự xử lý tại receiver (Edge)

Thứ tự dưới đây là **chuẩn**: khi packet có nhiều lỗi, trả mã của bước đầu tiên
thất bại. Hai reference (`i1v2_reference.py`, `i1v2_codec.c`) cài đúng thứ tự này
và được kiểm chéo.

### 7.1 Stage A — envelope (lỗi → drop im lặng)

1. Frame do binding giao có ít nhất 32 byte và magic `I1PK`.
2. `total_length` bằng độ dài frame nhận và `≤ max_packet` (6380).
3. `header_length = 32 + metadata_length + nonce_length`.
4. `total_length = header_length + payload_length + 4`.
5. CRC khớp.

Lỗi ở stage A: **drop**, không inference, không gửi response (request ID chưa
đáng tin), chỉ tăng counter cục bộ (`CRC_MISMATCH` là mã telemetry cục bộ, không
lên wire). Frame vượt giới hạn binding bị binding drop trước khi tới I1.

### 7.2 Stage B–E — sau CRC (lỗi → `ERROR_RESPONSE` cùng `request_id`)

| Bước | Điều kiện đạt | Mã khi lỗi |
|---:|---|---|
| B1 | `protocol_version = 2` | `UNSUPPORTED_VERSION` |
| B2 | `message_type = 0x01` | `INVALID_MESSAGE_TYPE` |
| B3 | `request_id ≠ 0` (response vẫn mang 0) | `INVALID_REQUEST_ID` |
| B4 | Tra duplicate cache ([binding §8](i1_ble_binding_v1.md)) | `DUPLICATE_CONFLICT` hoặc trả lại response đã cache |
| B5 | `reserved_0 = reserved_1 = 0` | `INVALID_LENGTH` |
| B6 | `flags ∈ {0x0000, 0x0002}` | `UNSUPPORTED_FLAGS` |
| B7 | `nonce_length = 12` nếu I2, `0` nếu thường | `INVALID_NONCE` |
| B8 | `payload_length ≤ 5760` | `PAYLOAD_TOO_LARGE` |
| C1 | `metadata_length ≥ 16` | `INVALID_LENGTH` |
| C2 | `model_profile_id` là profile active (khác 0) | `UNKNOWN_MODEL_PROFILE` |
| C3 | `split_id` thuộc profile | `UNSUPPORTED_SPLIT` |
| C4 | `dtype = INT8` | `UNSUPPORTED_DTYPE` |
| C5 | `layout = NCL` | `UNSUPPORTED_LAYOUT` |
| C6 | `ndim = 3`, `reserved_tensor = 0` | `INVALID_TENSOR_METADATA` |
| C7 | scheme `AFFINE_PER_CHANNEL`, axis `1` | `UNSUPPORTED_QUANTIZATION` |
| C8 | `metadata_length ≥ 32` | `INVALID_LENGTH` |
| C9 | `dimensions = [1,C,L]` của split, `element_count = C×L` | `INVALID_TENSOR_METADATA` |
| C10 | `payload_length = element_count` | `INVALID_LENGTH` |
| C11 | `quant_count = C` | `UNSUPPORTED_QUANTIZATION` |
| C12 | `metadata_length` đúng §4 (không thừa/thiếu) | `INVALID_LENGTH` |
| C13 | Mọi scale hợp lệ (§6), mọi zero point `= 0` | `UNSUPPORTED_QUANTIZATION` |
| D1 | Descriptor: `i2_version=1`, `algorithm_id=1`, dtype 2, layout 1, `N=1`, reserved 0 | `INVALID_I2_DESCRIPTOR` |
| D2 | Descriptor model/split/C/L/`payload_length` khớp tensor metadata | `INVALID_I2_DESCRIPTOR` |
| D3 | `key_id` là key của profile (`65537`) | `KEY_UNAVAILABLE` |
| D4 | Nonce: `sender_id` thuộc sender scope của key (`131073`), `sequence ≠ 0` | `INVALID_NONCE` |
| E1 | Edge có key material đã provision cho `key_id` | `KEY_UNAVAILABLE` |
| E2 | `unprotect()` thành công (lỗi ánh xạ theo §7.3) | theo §7.3 |
| E3 | Tensor q không chứa `-128` | `UNSUPPORTED_QUANTIZATION` |
| F1 | Dequantize, reshape NC nếu cần, chạy tail (s0..s9) hoặc identity (s10) | `INFERENCE_FAILED`, `TIMEOUT` |

Bước D chỉ áp dụng khi `flags=0x0002`. Admission (`EDGE_BUSY`) xảy ra trước F1;
`EDGE_BUSY` không được cache. Receiver không phát hiện được sai key bytes khi
`key_id` đúng, cũng không phát hiện được transformed bytes bị sửa có chủ đích nếu
CRC được tính lại: `unprotect()` khi đó trả tensor sai nhưng đúng shape. Kiểm tra
`-128` ở E3 không phải cơ chế phát hiện sai key.

### 7.3 Ánh xạ lỗi I2/1 → I1 v2

Với thứ tự trên, các lỗi I2 do dữ liệu peer gây ra đã bị chặn ở bước D; mục ánh
xạ dưới đây áp dụng khi `unprotect()` vẫn trả lỗi (phòng thủ):

| Lỗi API I2/1 | Status I1 v2 |
|---|---|
| `INVALID_NONCE` | `INVALID_NONCE` (`0x0014`) |
| `KEY_UNAVAILABLE`, `KEY_SCOPE_MISMATCH` | `KEY_UNAVAILABLE` (`0x0012`) |
| `INVALID_METADATA`, `UNSUPPORTED_VERSION`, `UNSUPPORTED_ALGORITHM`, `LENGTH_MISMATCH`, `PROFILE_MISMATCH` | `INVALID_I2_DESCRIPTOR` (`0x0013`) |
| `SIZE_LIMIT` | `PAYLOAD_TOO_LARGE` (`0x000e`) |
| `INVALID_ARGUMENT`, `INVALID_PROFILE`, `BUFFER_TOO_SMALL` (lỗi cấu hình/cài đặt cục bộ) | `INFERENCE_FAILED` (`0x0009`) + log cục bộ |
| `NONCE_REUSE` | Chỉ ở Device: dừng gửi I2, không lên wire |

`UNSUPPORTED_VERSION` của I2 descriptor **không** ánh xạ sang
`UNSUPPORTED_VERSION` của I1 để tránh nhầm với `protocol_version`.

## 8. Response

### 8.1 Cấu trúc

Response/error dùng `protocol_version=2`, `flags=0`, `nonce_length=0`,
`metadata_length=8` theo I1 v1 §9.1 (`status_code:uint16_le`, `result_type:uint8`,
`result_dtype:uint8`, `result_count:uint32_le`). Response không bị biến đổi I2.

| Loại | `status` | `result_type` | `result_dtype` | `result_count` | Payload | `total_length` |
|---|---|---|---|---:|---|---:|
| `INFERENCE_RESPONSE` | `OK` | `SCORE_VECTOR` (`0x02`) | `FLOAT32` (`0x02`) | 5 | 5 × `float32_le` | 64 |
| `ERROR_RESPONSE` | khác `OK`, có trong §9 | `NONE` | `NONE` | 0 | rỗng | 44 |

### 8.2 Ngữ nghĩa kết quả

- Payload là **logits** của tail theo thứ tự lớp `N, S, V, F, Q` (index 0..4),
  không softmax, không chuẩn hóa thêm. Logit phải hữu hạn; tail cho NaN/∞ thì Edge
  trả `INFERENCE_FAILED`.
- Lớp dự đoán = argmax trên logits thô; nếu bằng nhau chọn **chỉ số nhỏ nhất**.
- s10 diagnostic: logits = `float32(q[c] × scale[c])`, `c = 0..4`, sau unprotect
  (nếu có). Với q nguyên trong `[-127,127]` và scale FP16 normal, phép nhân này
  chính xác trong FP32 nên kết quả bit-exact giữa hai phía.

### 8.3 Device kiểm response

Device chỉ nhận response khi: envelope và CRC đúng; version 2; type `0x02` hoặc
`0x03`; `request_id` đúng request đang chờ; `reserved_*`, `flags`, `nonce_length`
bằng 0; `metadata_length = 8`; với `0x02`: đúng bảng §8.1 và 5 logits hữu hạn; với
`0x03`: status khác `OK` và thuộc §9, các trường kết quả bằng 0, payload rỗng. Mọi
trường hợp khác bị drop và đếm (`invalid_response`, `stale_response`); Device tiếp
tục chờ tới timeout. Device không gửi lỗi ngược lại cho Edge.

## 9. Status code

Các mã `0x0000..0x0010` giữ nguyên I1 v1 §9.2. Bốn mã mới, không trùng enum:

| Tên | Giá trị | Ý nghĩa |
|---|---:|---|
| `UNKNOWN_MODEL_PROFILE` | `0x0011` | `model_profile_id` bằng 0 hoặc không phải profile active |
| `KEY_UNAVAILABLE` | `0x0012` | `key_id` không thuộc profile/scope, hoặc Edge chưa có key material cho `key_id` |
| `INVALID_I2_DESCRIPTOR` | `0x0013` | Descriptor sai version/algorithm/field, hoặc không khớp tensor metadata |
| `INVALID_NONCE` | `0x0014` | `nonce_length` không khớp flags, `sender_id` ngoài scope, hoặc `sequence = 0` |

`CRC_MISMATCH` (`0x0005`) chỉ dùng cho telemetry cục bộ. Giá trị chưa biết bị
Device coi là response không hợp lệ.

## 10. Giới hạn kích thước và buffer

| Đại lượng | Giá trị | Loại |
|---|---:|---|
| `max_payload` | 5760 B | Trần profile (registry) |
| `C` tối đa | 64 | Trần profile |
| Metadata request I2/1 lớn nhất | `60 + 8×64 = 572` B | Suy ra |
| `max_packet` | `104 + 8×64 + 5760 + 4 = 6380` B | Trần thiết kế (registry `protected_budget_bytes`) |
| Request thật lớn nhất của registry | 6124 B (s3 I2/1) | Suy ra từ registry |
| Response / error | 64 / 44 B | Cố định |

Trần 6380 B là giới hạn cấu hình bắt buộc kiểm trước khi cấp phát/copy; nó **không**
phải số RAM đã đo. Chưa có số đo RAM, stack, flash, latency hay throughput nào
của I1 v2 trên nRF52840 hoặc KV260; các số đó thuộc tiêu chí nghiệm thu tuần 6.
Ngân sách RAM dự kiến của Device (chưa đo): buffer TX packet 6380 B (giữ nguyên để
retry), buffer reassembly RX 6380 B, buffer tensor q 5760 B.

## 11. Request ID, retry, duplicate

- `request_id` khác 0, tăng dần, bỏ 0 khi wrap. Sau mỗi lần boot Device khởi tạo
  bộ đếm từ giá trị ngẫu nhiên khác 0 (`sys_csrand_get`) để giảm va chạm với cache
  Edge còn sống sau reboot; va chạm còn lại được bắt bởi `DUPLICATE_CONFLICT`.
- Retry gửi lại **nguyên** packet: cùng `request_id`, metadata, nonce và
  transformed bytes; không gọi `protect()` lại và không cấp nonce mới.
- Timeout, số retry, backoff, duplicate cache và phiên logic theo
  [BLE binding §6–8](i1_ble_binding_v1.md).

## 12. Golden vector và kiểm thử

Vector đầy đủ (hex, kèm negative) trong [`i1v2_ref/vectors.json`](i1v2_ref/vectors.json).
Giá trị tensor và key `00 01 … 1f` là `PUBLIC_TEST_ONLY`, không phải activation
thật hay key vận hành; các ID lấy từ registry.

`plain_s10`: request thường, `request_id=0x101`, split 266, q =
`127,−127,0,1,−1`, scales `0.5,0.25,1,2,0.125`; 113 B, CRC `0x931eeeed`:

```text
49 31 50 4b 02 01 00 00 68 00 00 00 71 00 00 00
01 01 00 00 48 00 00 00 05 00 00 00 00 00 00 00
01 54 49 4d 0a 01 02 01 03 02 01 00 05 00 00 00
01 00 00 00 05 00 00 00 01 00 00 00 05 00 00 00
00 00 00 3f 00 00 80 3e 00 00 80 3f 00 00 00 40
00 00 00 3e 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 7f 81 00 01 ff ed ee 1e
93
```

`i2_s10`: cùng tensor, I2/1 với key public, `key_id=65537`, nonce
`sender=131073, sequence=1`, `request_id=0x102`; 153 B, CRC `0xb9a63ad9`.
Descriptor ở offset 104, nonce ở 132, transformed payload `45 c1 df fb 03` ở 144:

```text
49 31 50 4b 02 01 02 00 90 00 00 00 99 00 00 00
02 01 00 00 64 00 00 00 05 00 00 00 0c 00 00 00
01 54 49 4d 0a 01 02 01 03 02 01 00 05 00 00 00
01 00 00 00 05 00 00 00 01 00 00 00 05 00 00 00
00 00 00 3f 00 00 80 3e 00 00 80 3f 00 00 00 40
00 00 00 3e 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 01 01 02 01 01 54 49 4d
0a 01 01 00 05 00 00 00 01 00 00 00 01 00 01 00
05 00 00 00 01 00 02 00 01 00 00 00 00 00 00 00
45 c1 df fb 03 d9 3a a6 b9
```

Response identity cho request trên: logits `63.5, −31.75, 0, 2, −0.125`, lớp `N`;
64 B, CRC `0x6172b9d6`:

```text
49 31 50 4b 02 02 00 00 28 00 00 00 40 00 00 00
02 01 00 00 08 00 00 00 14 00 00 00 00 00 00 00
00 00 02 02 05 00 00 00 00 00 7e 42 00 00 fe c1
00 00 00 00 00 00 00 40 00 00 00 be d6 b9 72 61
```

`ERROR_RESPONSE` `UNSUPPORTED_QUANTIZATION` cho `request_id=0x102`: 44 B,
`49 31 50 4b 02 03 00 00 28 00 00 00 2c 00 00 00 02 01 00 00 08 00 00 00 00 00 00 00 00 00 00 00 0c 00 00 00 00 00 00 00 bf 27 44 8e`.

Vector biên: `i2_s3_largest_registry_split` (6124 B, có byte `0x80` trong
transformed payload) và `i2_ceiling_c64_payload5760` (6380 B, profile
`PUBLIC_TEST_ONLY` vì registry không có split C=64, payload 5760).

Chạy từ Git root (Python 3.11+, `gcc` trên PATH hoặc biến `CC`):

```powershell
python -B contracts/i1v2_ref/test_i1v2.py
python -B contracts/i1v2_ref/make_vectors.py --check
```

Test gồm: golden ráp độc lập bằng giá trị literal; encoder C và Python khớp từng
byte; 54 negative request trên cả parser C và Python (mọi status do parser sinh
đều được phủ); pipeline unprotect → kiểm `-128` → identity s10; 2 response hợp lệ
và 13 response lỗi; 4000 mẫu fuzz vi sai C/Python; kích thước mọi split; enum không
trùng và bảng ánh xạ I2. Đây là kiểm thử **host**; chưa phải bằng chứng
nRF52840/KV260.

## 13. Các mục OPEN của addendum r1 §6 đã đóng

| Mục OPEN | Quyết định |
|---|---|
| `model_profile_id` trên wire hay theo session (I1 v1 §18.3) | Trên wire, metadata offset 0, `protocol_version=2` |
| Biểu diễn s9, s10 | NCL `[1,32,1]`, `[1,5,1]`; Edge reshape NC không đổi thứ tự |
| Mã khi từ chối `q=-128` | `UNSUPPORTED_QUANTIZATION` (`0x000c`) |
| Response (I1 v1 §18.4) | `SCORE_VECTOR` FLOAT32 5 logits `N,S,V,F,Q`, không softmax, tie → index nhỏ nhất |
| Transport, timeout/retry, duplicate cache | [BLE binding v1](i1_ble_binding_v1.md) |
| `max_packet_bytes` | 6380 B (trần thiết kế, chưa đo RAM) |
| Mã unknown model/key/descriptor/nonce | §9 |
| Nonce bền qua reboot, provisioning | [I2/1 nonce và provisioning v1](i2_nonce_provisioning_v1.md) (thiết kế; chưa triển khai) |

Không còn mục thiết kế nào trong phạm vi này chờ trưởng nhóm chốt. Các việc còn
lại là triển khai và nghiệm thu, theo dõi trong
[kế hoạch tuần 6](../docs/week6_device_edge_plan.md).

## 14. Change control

- Thay đổi offset, size, enum, thứ tự xử lý lỗi hay semantics bắt buộc phải tăng
  `protocol_version` hoặc ra revision có tên, cập nhật vector và reference.
- Đổi model/split/scale/shape cần revision registry mới; không sửa registry đã
  duyệt tại chỗ.
- Nếu cần bí mật hoặc xác thực thật, thiết kế AEAD có tag và version mới; không
  dùng flag `0x0001` để gắn nhãn bảo mật cho I2/1.

| Vai trò | Người | Nội dung | Trạng thái |
|---|---|---|---|
| Trưởng nhóm, owner SV1 | Lê Hải Châu | Duyệt thiết kế I1 v2 | **APPROVED** 15/10/2026 |
| Owner Edge SV2 | Trung | Xác nhận parser/buffer KV260 sau triển khai | Chưa xác nhận |
| ML reviewer SV3 | Kỳ Anh | Xác nhận tensor/quantization/response với activation thật | Chưa xác nhận |
