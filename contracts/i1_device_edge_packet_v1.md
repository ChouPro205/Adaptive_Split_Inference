# I1 Device–Edge Packet Contract

## 1. Metadata tài liệu

| Thuộc tính | Giá trị |
|---|---|
| Contract ID | `I1` |
| Protocol version | `1` |
| Trạng thái | `REVIEW_CANDIDATE` |
| Owner Device/SV1 | Châu |
| Owner Edge/SV2 | Trung |
| ML metadata reviewer | Kỳ Anh |
| Cập nhật lần cuối | 2026-09-22 |

### Quy tắc trạng thái

- `DRAFT`: đang được thiết kế hoặc review; implementation không được coi là
  tương thích chính thức chỉ dựa trên tài liệu này.
- `REVIEW_CANDIDATE`: phần wire protocol đã được Device/Edge chấp thuận nhưng
  deployment profile hoặc xác nhận ML vẫn chưa hoàn tất. Trạng thái này chưa
  cho phép coi contract là frozen.
- `FROZEN`: wire format và các giới hạn bắt buộc đã được Châu và Trung xác
  nhận. Các mục tensor/quantization còn liên quan phải có xác nhận của Kỳ Anh.
  Không được chuyển sang trạng thái này nếu thiếu xác nhận của Châu hoặc Trung.
- `DEPRECATED`: phiên bản vẫn được nhận diện để migration nhưng không dùng cho
  triển khai mới; tài liệu thay thế phải được chỉ rõ khi chuyển trạng thái.

Trong tài liệu này, **MUST/MUST NOT** là bắt buộc để tương thích, **SHOULD/SHOULD
NOT** là khuyến nghị chỉ được bỏ qua khi có lý do được ghi lại, và **MAY** là
tùy chọn. Trạng thái hiện tại là `REVIEW_CANDIDATE`: Châu và Trung đã chấp
thuận phần Device–Edge hiện có theo xác nhận của project lead; các ràng buộc
deployment ML chưa đủ để chuyển sang `FROZEN`.

## 2. Cơ sở từ repository và giới hạn bằng chứng

Những kết luận sau được dùng để thiết kế contract:

- [`README.md`](../README.md) phân công Device/SV1 cho nRF52840 Dongle,
  Edge/SV2 cho KV260 và ML/SV3 cho mô hình, lượng tử hóa, protection.
- [`device/README.md`](../device/README.md) và firmware hiện tại xác nhận target
  `nrf52840dongle/nrf52840`, NCS 3.4.0/Zephyr 4.4.0 và USB CDC ACM hiện được
  dùng làm console. Đây **không** phải bằng chứng rằng USB CDC đã được chọn làm
  transport I1.
- Báo cáo firmware hiện tại ghi nhận 256 KB RAM; source ứng dụng hiện không cấp
  phát động. Số liệu này chưa đủ để chốt buffer I1 vì chưa có tensor split thực
  tế.
- [`edge/README.md`](../edge/README.md) nói rõ phía KV260 chưa có parser/server
  implementation trong giai đoạn hiện tại.
- [`ml/docs/week1_data_contract.md`](../ml/docs/week1_data_contract.md) chốt
  tensor dữ liệu đầu vào trước model cho MIT-BIH và PTB-XL, nhưng chủ động hoãn
  ONNX opset, tensor name, split point, quantization scale/zero point và header
  deployment.
- [`ml/README.md`](../ml/README.md),
  [`ml/docs/week1_requirements_traceability.md`](../ml/docs/week1_requirements_traceability.md)
  và [`ml/docs/week1_verification.md`](../ml/docs/week1_verification.md) xác
  nhận phần ML hiện tại không train 1D-CNN, không export model deployment,
  không có ONNX, split-model deployment hoặc quantization.

Không tìm thấy quyết định repository nào chốt transport I1, model/split ID,
tensor trung gian, quantization, response inference, timeout/retry hoặc giới
hạn packet. Hai shape input `(N, 1, 360)` và `(N, 12, 1000)` **không** phải
intermediate activation và không được gán cho `split_id`. Không có mâu thuẫn
kỹ thuật trực tiếp giữa tài liệu Device, Edge và ML về I1; các quyết định
deployment nói trên chưa được triển khai.

## 3. Mục tiêu và phạm vi

I1 định nghĩa packet tầng ứng dụng để trao đổi tensor trung gian giữa Device
nRF52840 và Edge KV260:

- `INFERENCE_REQUEST` đi từ Device tới Edge.
- `INFERENCE_RESPONSE` và `ERROR_RESPONSE` đi từ Edge về Device.
- Packet I1 độc lập với transport. BLE, USB CDC, UART hay TCP nếu được chọn sẽ
  có binding/framing riêng và MUST chuyển đúng chuỗi byte I1.

I1 không định nghĩa:

- thuật toán lựa chọn split point;
- kiến trúc hoặc nội bộ mô hình ML;
- GPIO marker D0–D3/PPK2;
- driver, MTU, framing, reconnect hoặc flow control của transport;
- giao diện người dùng.

## 4. Thuật ngữ và trách nhiệm

- **Device** MUST chọn một `request_id`, serialize từng field, kiểm tra giới
  hạn trước khi đóng gói, tính CRC, gửi request, quản lý timeout/retry và chỉ
  nhận response có `request_id` phù hợp.
- **Edge** MUST parse có giới hạn, kiểm tra magic/version/length/CRC trước khi
  tạo tensor, xác minh tensor theo profile của `split_id`, dequantize khi cần,
  chạy tail model đúng một lần về mặt logic và tạo response.
- **ML owner** MUST xác nhận profile của từng `split_id`: dtype, shape, layout,
  quantization và ý nghĩa output. ML owner không chịu trách nhiệm transport.
- **Transport binding** là tài liệu riêng quy định cách chuyển một packet I1
  hoàn chỉnh qua BLE/USB CDC/UART/TCP hoặc transport khác.
- **Model profile** là định danh bất biến cho đúng model, version, dataset
  profile và semantics output.
- **Split profile** là cấu hình được hai đầu cài đặt giống nhau, ánh xạ tuple
  `(model_profile_id, split_id)` tới layer/tensor và các ràng buộc cụ thể.
- Không bên nào được đoán shape, dtype, layout hoặc quantization từ payload.
  Packet và split profile MUST cung cấp đủ thông tin và MUST khớp nhau.

## 5. Message type và flag

### 5.1 `message_type`

| Tên | Giá trị | Hướng | Ý nghĩa |
|---|---:|---|---|
| `INFERENCE_REQUEST` | `0x01` | Device → Edge | Tensor trung gian để chạy tail model. |
| `INFERENCE_RESPONSE` | `0x02` | Edge → Device | Kết quả thành công cho request. |
| `ERROR_RESPONSE` | `0x03` | Edge → Device | Lỗi có thể gắn an toàn với request. |

v1 không định nghĩa `PING`/`PONG`. Receiver MUST trả `INVALID_MESSAGE_TYPE` cho
giá trị chưa biết nếu packet có envelope và CRC hợp lệ; nếu không thể tin cậy
`request_id`, receiver MUST drop như quy định tại mục 10.3.

### 5.2 `flags`

| Bit/mask | Tên | Quy tắc v1 |
|---|---|---|
| `0x0001` | `PROTECTED_PAYLOAD` | Reserved cho cơ chế protection tương lai; MUST bằng 0 trong contract hiện tại. |
| `0xfffe` | `RESERVED_FLAGS` | MUST bằng 0 khi gửi. |

Giá trị hợp lệ hiện tại của toàn bộ `flags` là `0x0000`. Receiver v1 MUST trả
`UNSUPPORTED_FLAGS` sau khi CRC hợp lệ nếu có bit khác 0. Việc sau này kích hoạt
`PROTECTED_PAYLOAD` cần một revision đã được duyệt hoặc tăng protocol version;
không được tự suy diễn thuật toán từ bit này.

## 6. Binary frame layout chung

Một packet có cấu trúc logic:

```text
[fixed_header: 32 B]
[message_metadata: metadata_length B]
[nonce: nonce_length B]
[payload: payload_length B]
[crc32: 4 B]
```

### 6.1 Fixed header

| Offset | Size | Field | Type | Required | Description |
|---:|---:|---|---|---|---|
| 0 | 4 | `magic` | `byte[4]` | MUST | ASCII `I1PK`, bytes `49 31 50 4b`. |
| 4 | 1 | `protocol_version` | `uint8` | MUST | `0x01` cho tài liệu này. |
| 5 | 1 | `message_type` | `uint8` enum | MUST | Bảng tại mục 5.1. |
| 6 | 2 | `flags` | `uint16_le` | MUST | Hiện phải bằng 0. |
| 8 | 2 | `header_length` | `uint16_le`, byte | MUST | `32 + metadata_length + nonce_length`. Đồng thời là offset bắt đầu payload. |
| 10 | 2 | `reserved_0` | `uint16_le` | MUST | Sender ghi 0; receiver v1 từ chối giá trị khác 0 bằng `INVALID_LENGTH`. |
| 12 | 4 | `total_length` | `uint32_le`, byte | MUST | Toàn bộ packet, gồm CRC 4 byte. |
| 16 | 4 | `request_id` | `uint32_le` | MUST | ID khác 0, giữ nguyên giữa request, retry và response. |
| 20 | 4 | `metadata_length` | `uint32_le`, byte | MUST | Độ dài metadata ngay sau fixed header. |
| 24 | 4 | `payload_length` | `uint32_le`, byte | MUST | Độ dài payload; trong response cũng là `result_length`. |
| 28 | 2 | `nonce_length` | `uint16_le`, byte | MUST | Hiện phải bằng 0; vị trí nonce được xác định ở mục 6.2. |
| 30 | 2 | `reserved_1` | `uint16_le` | MUST | Sender ghi 0; receiver v1 từ chối giá trị khác 0 bằng `INVALID_LENGTH`. |

Không được gửi trực tiếp một C struct vì compiler có thể chèn padding, thay đổi
alignment hoặc dùng native endianness. Sender MUST serialize từng byte/field;
receiver MUST đọc bằng hàm load little-endian không yêu cầu con trỏ aligned.

### 6.2 Ranh giới và bất biến độ dài

Với `FIXED_HEADER_BYTES = 32` và `CRC_BYTES = 4`:

```text
metadata_offset = 32
nonce_offset    = 32 + metadata_length
payload_offset  = header_length
crc_offset      = header_length + payload_length

header_length = 32 + metadata_length + nonce_length
total_length  = header_length + payload_length + 4
crc_offset    = total_length - 4
```

Receiver MUST dùng phép cộng/nhân có kiểm tra overflow (khuyến nghị biến trung
gian 64 bit) và từ chối packet nếu bất kỳ đẳng thức nào sai. Không được cộng
các field do peer cung cấp trong `uint16`/`uint32` rồi mới kiểm tra.

Trình tự parse tối thiểu:

1. Đọc đúng 32 byte fixed header vào buffer nhỏ.
2. Kiểm tra `magic`, các độ dài tối thiểu và giới hạn cấu hình trước khi cấp
   phát hay đọc phần còn lại.
3. Tính các offset bằng số học checked; xác minh các đẳng thức ở trên.
4. Đọc/stream đúng `total_length - 32` byte còn lại.
5. Xác minh CRC trước khi tin `request_id` hoặc nội dung metadata.
6. Sau CRC mới kiểm tra version, type, flags và metadata theo message type.

### 6.3 Byte order và kiểu số

- Mọi integer đa byte, kể cả signed integer và CRC, dùng **little-endian**.
- `int8` dùng two's complement; `int32` dùng two's complement 32 bit.
- `float32` là IEEE 754 binary32, serialized theo bit pattern 32 bit
  little-endian. Receiver MUST từ chối scale là NaN, infinity, `+0` hoặc `-0`.
- nRF52840 và KV260 không được phụ thuộc native representation: dùng helper
  kiểu `sys_get_le16/sys_put_le16`, `sys_get_le32/sys_put_le32` hoặc phép dịch
  tương đương. Với float, copy bit pattern qua `uint32` bằng `memcpy`, sau đó
  encode/decode little-endian; không type-pun qua con trỏ không aligned.

Little-endian là quyết định v1 đã được giữ nguyên từ phần Device–Edge được
chấp thuận. Quy tắc vẫn độc lập với native endianness của CPU.

## 7. Tensor contract cho `INFERENCE_REQUEST`

`message_metadata` của request bắt đầu tại packet offset 32.

### 7.1 Tensor metadata prefix và dimensions

| Metadata offset | Size | Field | Type | Required | Description |
|---:|---:|---|---|---|---|
| 0 | 2 | `split_id` | `uint16_le` | MUST | `0` reserved; `1..65535` do split registry của active `model_profile_id` gán. |
| 2 | 1 | `dtype` | `uint8` enum | MUST | Bảng mục 7.2. |
| 3 | 1 | `layout` | `uint8` enum | MUST | Bảng mục 7.3. |
| 4 | 1 | `ndim` | `uint8` | MUST | Từ 1 đến `MAX_NDIM_V1 = 8`. |
| 5 | 1 | `quantization_scheme` | `uint8` enum | MUST | Bảng mục 8.1. |
| 6 | 1 | `quantization_axis` | `int8` | MUST | `-1` nếu none/per-tensor; axis hợp lệ nếu per-channel. |
| 7 | 1 | `reserved_tensor` | `uint8` | MUST | Sender ghi 0; receiver từ chối giá trị khác 0. |
| 8 | 4 | `element_count` | `uint32_le` | MUST | Phải bằng tích tất cả dimensions. |
| 12 | `4 * ndim` | `dimensions` | `uint32_le[ndim]` | MUST | Thứ tự đúng theo `layout`; mỗi dimension khác 0. |
| `12 + 4 * ndim` | biến đổi | `quantization_metadata` | theo scheme | Conditional | Cấu trúc chính xác tại mục 8.2. |

`metadata_length` MUST bằng đúng độ dài suy ra từ `ndim` và
`quantization_scheme`; không cho phép trailing byte trong metadata v1.

### 7.2 `dtype`

| Tên | Giá trị | Byte/phần tử | Payload representation |
|---|---:|---:|---|
| `FLOAT32` | `0x01` | 4 | IEEE 754 binary32 little-endian. |
| `INT8` | `0x02` | 1 | Two's complement. |
| `UINT8` | `0x03` | 1 | Unsigned. |

Enum trên là khả năng wire-format của v1, không khẳng định model đã sử dụng cả
ba kiểu. Giá trị khác MUST bị từ chối bằng `UNSUPPORTED_DTYPE`.

### 7.3 `layout`

| Tên | Giá trị | `ndim` | Thứ tự dimensions; phần tử cuối biến thiên nhanh nhất |
|---|---:|---:|---|
| `FLAT` | `0x00` | 1 | `[elements]` |
| `NCL` | `0x01` | 3 | `[batch, channel, length]` |
| `NLC` | `0x02` | 3 | `[batch, length, channel]` |
| `NCHW` | `0x03` | 4 | `[batch, channel, height, width]` |
| `NHWC` | `0x04` | 4 | `[batch, height, width, channel]` |

Payload luôn C-contiguous/row-major theo dimensions khai báo; dimension cuối
biến thiên nhanh nhất. Layout thực tế của mỗi split vẫn là
`DEFERRED – chưa được triển khai trong phần ML hiện tại`. Giá trị layout chưa
biết MUST bị từ chối bằng `UNSUPPORTED_LAYOUT`; receiver không được fallback
sang `FLAT`.

### 7.4 Tính kích thước và validation

Receiver MUST:

1. Kiểm tra `1 <= ndim <= 8` trước khi đọc dimensions.
2. Kiểm tra rank đúng với `layout` và mọi dimension khác 0.
3. Tính `calculated_elements = product(dimensions[i])` bằng checked multiply;
   trước mỗi phép nhân kiểm tra giới hạn `uint32` và giới hạn payload cục bộ.
4. Yêu cầu `element_count == calculated_elements`.
5. Tính `expected_payload_length = element_count * bytes_per_element` bằng
   checked multiply.
6. Yêu cầu `payload_length == expected_payload_length`, đồng thời không vượt
   `max_payload_bytes` đã được hai bên chốt.
7. Yêu cầu metadata packet khớp profile cục bộ của tuple
   `(active_model_profile_id, split_id)`. `split_id` chưa biết trong active
   profile trả `UNSUPPORTED_SPLIT`; profile biết nhưng metadata sai trả
   `INVALID_TENSOR_METADATA`.

Mapping `split_id` và dtype/shape/layout cụ thể chưa có trong repository; xem
mục Open decisions.

## 8. Quantization contract

### 8.1 `quantization_scheme`

| Tên | Giá trị | Dtype hợp lệ | Ý nghĩa |
|---|---:|---|---|
| `NONE` | `0x00` | `FLOAT32` | Payload đã là giá trị thực; không có quantization metadata. |
| `AFFINE_PER_TENSOR` | `0x01` | `INT8`, `UINT8` | Một `scale` và một `zero_point` cho toàn tensor. |
| `AFFINE_PER_CHANNEL` | `0x02` | `INT8`, `UINT8` | Một cặp tham số cho mỗi phần tử trên `quantization_axis`. |

Kết hợp dtype/scheme khác bảng trên MUST bị từ chối bằng
`UNSUPPORTED_QUANTIZATION`.

### 8.2 Encoding metadata

Đặt `q_offset = 12 + 4 * ndim` tính từ đầu tensor metadata.

- `NONE`: `quantization_axis = -1`; không có byte sau dimensions;
  `metadata_length = q_offset`.
- `AFFINE_PER_TENSOR`: `quantization_axis = -1`; tại `q_offset` là `scale`
  (`float32_le`, 4 byte), tiếp theo là `zero_point` (`int32_le`, 4 byte);
  `metadata_length = q_offset + 8`.
- `AFFINE_PER_CHANNEL`: `0 <= quantization_axis < ndim`; tại `q_offset` là
  `quant_count` (`uint32_le`, 4 byte), tiếp theo là
  `scales[quant_count]` (`float32_le`), rồi
  `zero_points[quant_count]` (`int32_le`);
  `metadata_length = q_offset + 4 + 8 * quant_count`.

Với per-channel, `quant_count` MUST bằng
`dimensions[quantization_axis]`. Mọi scale MUST hữu hạn và lớn hơn 0. Mỗi
zero point MUST nằm trong miền dtype: `[-128, 127]` cho `INT8` hoặc `[0, 255]`
cho `UINT8`.

### 8.3 Công thức

Với giá trị thực `x`, scale `s > 0`, zero point `z`, miền dtype
`[q_min, q_max]`:

```text
q = clamp(round_ties_to_even(x / s) + z, q_min, q_max)
x_reconstructed = (q - z) * s
```

Per-tensor dùng cùng `(s, z)` cho mọi phần tử. Per-channel chọn `(s[c], z[c])`
theo chỉ số trên `quantization_axis`. `round_ties_to_even` là làm tròn về số
nguyên gần nhất, trường hợp đúng nửa chọn số chẵn; sender không được thay bằng
truncate hoặc round-away-from-zero.

Encoding wire trên được giữ nguyên từ phần Device–Edge đã chấp thuận. Scheme,
axis và tham số của từng split là
`DEFERRED – chưa được triển khai trong phần ML hiện tại`. Tensor payload luôn
chứa giá trị `q` khi dùng affine; Edge MUST dequantize theo chính metadata đã
xác minh và profile, không dùng ngầm scale/zero point khác.

## 9. Response và error handling

### 9.1 Response metadata

Cả `INFERENCE_RESPONSE` và `ERROR_RESPONSE` dùng metadata đúng 8 byte:

| Metadata offset | Size | Field | Type | Required | Description |
|---:|---:|---|---|---|---|
| 0 | 2 | `status_code` | `uint16_le` enum | MUST | `OK` chỉ hợp lệ với `INFERENCE_RESPONSE`; lỗi dùng `ERROR_RESPONSE`. |
| 2 | 1 | `result_type` | `uint8` enum | MUST | Kiểu logic của kết quả. |
| 3 | 1 | `result_dtype` | `uint8` enum | MUST | Kiểu scalar trong payload kết quả. |
| 4 | 4 | `result_count` | `uint32_le` | MUST | Số scalar kết quả. |

Với response, fixed-header `payload_length` chính là `result_length` tính bằng
byte. `metadata_length` MUST bằng 8 và `nonce_length` hiện MUST bằng 0.

| `result_type` | Giá trị | `result_dtype` | Quy tắc |
|---|---:|---|---|
| `NONE` | `0x00` | `NONE (0x00)` | `result_count = 0`, `payload_length = 0`. |
| `CLASS_ID` | `0x01` | `INT32 (0x01)` | Một class ID: count 1, payload 4 byte little-endian. |
| `SCORE_VECTOR` | `0x02` | `FLOAT32 (0x02)` | Count > 0, payload gồm `count` binary32 little-endian. |

Mọi tổ hợp khác bị xem là `INVALID_LENGTH` hoặc `INVALID_TENSOR_METADATA`.
Response payload thực tế (`CLASS_ID` hay `SCORE_VECTOR`, thứ tự class) là
`DEFERRED – chưa được triển khai trong phần ML hiện tại`; v1 không thêm
confidence hoặc latency vì repository chưa có nguồn dữ liệu/định nghĩa cho
các field đó.

`ERROR_RESPONSE` MUST dùng `result_type = NONE`, `result_dtype = NONE`,
`result_count = 0`, `payload_length = 0`. Không gửi chuỗi lỗi tùy ý trên wire;
diagnostic chi tiết thuộc log cục bộ để parser và RAM vẫn có giới hạn rõ ràng.

### 9.2 `status_code`

| Tên | Giá trị | Ý nghĩa |
|---|---:|---|
| `OK` | `0x0000` | Inference thành công. |
| `UNSUPPORTED_VERSION` | `0x0001` | Version không được hỗ trợ. |
| `INVALID_MESSAGE_TYPE` | `0x0002` | Message type không hợp lệ cho hướng truyền. |
| `INVALID_LENGTH` | `0x0003` | Độ dài, offset, reserved field hoặc result length sai. |
| `INVALID_TENSOR_METADATA` | `0x0004` | Rank, dimension, count hoặc profile không khớp. |
| `CRC_MISMATCH` | `0x0005` | CRC sai; xem quy tắc drop tại mục 10.3. |
| `UNSUPPORTED_SPLIT` | `0x0006` | Edge không có profile/model cho `split_id`. |
| `UNSUPPORTED_DTYPE` | `0x0007` | Dtype chưa hỗ trợ. |
| `EDGE_BUSY` | `0x0008` | Request chưa được nhận vào xử lý do thiếu tài nguyên tạm thời. |
| `INFERENCE_FAILED` | `0x0009` | Tail model lỗi sau khi request hợp lệ được nhận. |
| `TIMEOUT` | `0x000a` | Tác vụ nội bộ Edge đã nhận nhưng hết hạn; không phải timeout chờ cục bộ ở Device. |
| `UNSUPPORTED_LAYOUT` | `0x000b` | Layout chưa hỗ trợ. |
| `UNSUPPORTED_QUANTIZATION` | `0x000c` | Scheme/axis/parameter quantization chưa hỗ trợ. |
| `DUPLICATE_CONFLICT` | `0x000d` | Cùng `request_id` nhưng fingerprint request khác. |
| `PAYLOAD_TOO_LARGE` | `0x000e` | Vượt giới hạn đã cấu hình. |
| `UNSUPPORTED_FLAGS` | `0x000f` | Có flag không được hỗ trợ. |
| `INVALID_REQUEST_ID` | `0x0010` | `request_id` bằng 0 hoặc không hợp lệ theo binding. |

Các giá trị chưa biết MUST được xử lý như lỗi không tương thích; không được coi
là `OK`.

## 10. CRC32

### 10.1 Tham số

I1 sử dụng **CRC-32/ISO-HDLC** (còn gọi CRC-32/IEEE):

| Tham số | Giá trị |
|---|---|
| Width | 32 |
| Polynomial (normal) | `0x04c11db7` |
| Polynomial (reflected implementation) | `0xedb88320` |
| Init | `0xffffffff` |
| RefIn | `true` |
| RefOut | `true` |
| XorOut | `0xffffffff` |
| Check value cho ASCII `123456789` | `0xcbf43926` |
| Byte order trên wire | `uint32_le` |

CRC được tính trên mọi byte từ packet offset 0 tới `crc_offset - 1`, nghĩa là
fixed header, metadata, nonce và payload. Bốn byte field CRC ở cuối **không**
tham gia phép tính.

Lựa chọn này khớp `crc32_ieee()`/`crc32_ieee_update()` có trong Zephyr 4.4.0
của môi trường repository và `zlib.crc32()` trên Python/Linux. Với Zephyr,
`crc32_ieee_update()` bắt đầu bằng seed `0` và nhận kết quả lần trước khi xử lý
chunk kế tiếp; giá trị trả về đã có semantics Init/XorOut như bảng trên.

### 10.2 Validation

Receiver MUST đọc CRC wire bằng little-endian, tự tính CRC trên đúng phạm vi và
so sánh equality 32 bit. CRC chỉ phát hiện lỗi truyền ngẫu nhiên; CRC **không**
là MAC, chữ ký hay authentication và không chống sửa đổi có chủ đích.

### 10.3 Packet không đủ tin cậy

- Sai magic, fixed header bị thiếu, độ dài không thể dùng để xác định packet,
  packet bị truncate, hoặc CRC mismatch: Edge MUST drop, ghi diagnostic cục bộ
  nếu phù hợp và MUST NOT chạy inference.
- Trong các trường hợp trên, Edge MUST NOT gửi `ERROR_RESPONSE` theo
  `request_id` lấy từ packet vì ID chưa đáng tin. `CRC_MISMATCH` tồn tại cho
  telemetry cục bộ hoặc binding tương lai có một kênh request ID đáng tin độc
  lập; I1 v1 độc lập transport không phát response đó.
- Nếu envelope và CRC hợp lệ nhưng version/type/metadata sai, Edge MUST gửi
  `ERROR_RESPONSE` cùng `request_id`, trừ khi transport đã mất kết nối.
- Với version chưa hỗ trợ, Edge chỉ trả `UNSUPPORTED_VERSION` nếu packet vẫn
  tuân theo envelope v1 đủ để kiểm tra length và CRC; nếu không, drop.

## 11. Nonce và bảo vệ dữ liệu

Contract hiện tại chưa có AEAD/MAC hoặc thuật toán protection được chọn. Do đó:

- Sender MUST đặt `flags = 0`, `nonce_length = 0` và không ghi byte nonce.
- `nonce_offset` vẫn là `32 + metadata_length`; khi length bằng 0, payload bắt
  đầu ngay tại offset này.
- Không được dùng `request_id` thay nonce và không được tuyên bố packet được mã
  hóa/xác thực.
- Nếu protection được bổ sung, tài liệu được duyệt MUST quy định thuật toán,
  key scope, nonce length, tag location, associated data và failure behavior.
  Device dự kiến là bên sinh nonce; nonce MUST không lặp lại trong cùng key và
  độ dài/chu kỳ key. Cơ chế cụ thể là
  `DEFERRED – chưa được triển khai trong phần ML hiện tại`.
- Nếu nonce xuất hiện trong revision tương lai, CRC bao phủ nonce như mọi byte
  trước CRC. Điều này không biến CRC thành authentication.

Field nonce được giữ trong envelope để mở rộng có version, không phải bằng
chứng rằng protection đã tồn tại.

## 12. Kích thước tối đa và fragmentation

- `max_payload_bytes`: **TBD – Châu và Trung đo RAM/buffer với tensor thật**.
- `max_packet_bytes`: **TBD – Châu và Trung chốt**; phải thỏa
  `max_packet_bytes >= 32 + max_metadata_bytes + max_nonce_bytes +
  max_payload_bytes + 4`.
- Wire fields có thể biểu diễn tới `uint32`, nhưng đó không phải quyền gửi
  packet cỡ đó. Mỗi implementation MUST có giới hạn cấu hình hữu hạn và kiểm
  tra trước khi cấp phát/copy.
- I1 v1 **không hỗ trợ fragmentation ở tầng ứng dụng**. Không có fragment ID,
  offset hoặc reassembly state trong packet.
- Transport binding MUST chuyển hoặc reassemble nguyên một chuỗi byte I1 theo
  đúng thứ tự. Nếu MTU nhỏ hơn packet, fragmentation thuộc binding/transport.
- Nếu tensor vượt giới hạn, Device MUST NOT gửi packet bị cắt. Nó phải chọn
  split/profile khác hoặc báo lỗi cục bộ. Edge MUST từ chối packet vượt giới
  hạn bằng `PAYLOAD_TOO_LARGE` chỉ sau khi có thể xác minh CRC bằng streaming;
  nếu không thể xác định/tiêu thụ packet an toàn thì drop kết nối/frame theo
  binding.

Cho tới khi các giới hạn được chốt, implementation chỉ là prototype và không
được quảng bá là tương thích `FROZEN`.

## 13. Timeout, retry và idempotency

- Timeout response tại Device bắt đầu khi byte cuối của packet request đã được
  transport binding nhận để gửi thành công. Timeout dừng khi Device nhận đủ
  một packet response có CRC hợp lệ và `request_id` phù hợp.
- Giá trị timeout và số retry mặc định là
  **TBD – Châu và Trung benchmark rồi chốt trong transport binding**.
- Mỗi retry MUST gửi lại cùng chuỗi byte ứng dụng, gồm cùng `request_id`,
  payload và nonce nếu protection sau này được bật. Retry không tạo request
  logic mới.
- `request_id` MUST khác 0. Device SHOULD dùng bộ đếm 32 bit tăng đơn điệu,
  bỏ qua 0 khi wrap, và MUST không tái sử dụng ID trong thời gian Edge còn có
  thể giữ cache duplicate cho cùng logical transport session.
- Edge MUST khóa duplicate theo `(logical_session, request_id)`. Request đầu
  tiên được nhận hợp lệ tạo trạng thái `IN_PROGRESS`; duplicate không được
  enqueue hay chạy tail inference lần nữa.
- Nếu response đã có, Edge MUST trả lại response đã cache. Nếu request còn
  `IN_PROGRESS`, Edge MUST gắn lần nhận duplicate vào cùng công việc/response,
  không khởi chạy công việc mới.
- Edge SHOULD lưu fingerprint ít nhất gồm `total_length` và CRC của request;
  nếu có thể, so sánh byte hoặc hash mạnh hơn. Cùng ID nhưng fingerprint khác
  MUST trả `DUPLICATE_CONFLICT` và không inference.
- `EDGE_BUSY` nghĩa là request chưa được nhận vào inference và không tạo entry
  hoàn tất; Device MAY retry cùng packet sau backoff theo binding.
- Cache lifetime MUST bao phủ toàn bộ retry horizon:
  `(response_timeout * (1 + max_retries)) + margin`. Các giá trị và dung lượng
  cache là `TBD – Trung chốt cùng Châu`.

## 14. Quy trình xử lý chuẩn

1. Device xác nhận active `model_profile_id`, rồi chọn `request_id` mới và
   split profile đã cấu hình.
2. Device serialize fixed header và tensor metadata từng field.
3. Device append/stream tensor payload đúng row-major layout.
4. Device tính CRC trên mọi byte trước CRC, append CRC little-endian và gửi.
5. Edge kiểm tra magic và length bằng số học checked, không dựng tensor.
6. Edge stream/đọc phần còn lại và kiểm tra CRC.
7. Edge kiểm tra version/type/flags, tensor metadata và split profile.
8. Edge dequantize nếu scheme yêu cầu.
9. Edge chạy tail model đúng một lần về mặt logic.
10. Edge trả response cùng `request_id`; Device xác minh CRC và ID trước khi
    nhận kết quả.

## 15. Implementation notes

Các ghi chú này không thay đổi wire format.

### 15.1 nRF52840 / Device

- Nên giữ fixed header trong buffer 32 byte và serialize metadata bằng buffer
  tĩnh có giới hạn; không cần dựng một bản sao toàn packet.
- Có thể cập nhật CRC theo từng chunk bằng `crc32_ieee_update(0, first, len)`
  rồi truyền kết quả vào lần update tiếp theo; payload có thể được stream từ
  buffer tensor.
- Dùng helper little-endian của Zephyr hoặc helper cục bộ đã unit-test. Không
  cast buffer nhận/gửi sang C struct.
- Firmware hiện có `CONFIG_MAIN_STACK_SIZE=4096` và không cấp phát động trong
  source ứng dụng. Buffer I1 phải được budget riêng; số RAM build hiện tại
  không chứng minh một tensor cụ thể sẽ vừa.
- USB CDC hiện là console. Không được trộn binary packet với log text trên cùng
  stream nếu chưa có binding phân kênh/framing rõ ràng.

### 15.2 KV260 / Edge

- Đọc fixed header trước, áp dụng hard limit trước khi reserve/allocate, rồi có
  thể tính CRC incremental khi nhận metadata/payload.
- Chỉ tạo NumPy/PyTorch tensor hoặc buffer accelerator sau khi CRC, size,
  dtype, shape, layout, quantization và split profile đều hợp lệ.
- Không dùng `reinterpret_cast`/packed struct phụ thuộc alignment. Decode scalar
  theo little-endian rồi mới tạo view/tensor.
- Duplicate cache và queue admission phải xảy ra trước tail inference để retry
  không tạo inference lặp.

## 16. MIT-BIH input profile

Profile này mô tả **model input trước khi có model**, không mô tả payload I1 tại
một split point.

| Thuộc tính | Giá trị đã xác nhận | Trạng thái | Nguồn |
|---|---|---|---|
| Dataset | MIT-BIH Arrhythmia Database v1.0.0 | Frozen cho dữ liệu Week 1 | [`mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json) |
| Một sample | Một nhịp ECG tâm tại expert annotation, lấy lead `MLII` theo tên | Frozen cho dữ liệu Week 1 | [`week1_data_protocol.md`](../ml/docs/week1_data_protocol.md), [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| Sampling rate | `360 Hz` | Đã xác minh | [`mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Cửa sổ | `360` mẫu: 180 mẫu trước và 180 mẫu sau annotation; boundary thiếu bị drop, không pad, không thêm filter | Frozen cho dữ liệu Week 1 | [`mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json), [`week1_data_protocol.md`](../ml/docs/week1_data_protocol.md) |
| Stored `X` | `(N, 360)`, NumPy `float32` | Đã tạo và xác minh | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`build_mitdb_processed.py`](../ml/src/build_mitdb_processed.py) |
| Model input view | `(N, C=1, L=360)` | Đã chốt như input contract; model chưa triển khai | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| Model input layout | `N,C,L` | Suy ra trực tiếp từ input view đã ghi; không phải split layout | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| Input dtype sau chuẩn hóa | `float32` | Đã tạo và xác minh | [`mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Đơn vị trước chuẩn hóa | mV, physical WFDB signal | Frozen cho dữ liệu Week 1 | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| Chuẩn hóa | Global scalar Z-score, fit chỉ trên train beats | Frozen cho dữ liệu Week 1 | [`mitdb_normalization.json`](../ml/configs/mitdb_normalization.json), [`compute_mitdb_normalization.py`](../ml/src/compute_mitdb_normalization.py) |
| Mean | `-0.2912026352134608` | Đã tái kiểm tra | [`mitdb_normalization.json`](../ml/configs/mitdb_normalization.json), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Standard deviation | `0.45653058276514263` | Đã tái kiểm tra | [`mitdb_normalization.json`](../ml/configs/mitdb_normalization.json), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Class order | `N=0`, `S=1`, `V=2`, `F=3`, `Q=4` | Frozen cho data labels | [`mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json), [`week1_data_protocol.md`](../ml/docs/week1_data_protocol.md) |
| Label dtype | `int64` | Đã tạo và xác minh | [`mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json), [`build_mitdb_processed.py`](../ml/src/build_mitdb_processed.py) |

Công thức preprocessing đã chốt là:

```text
x_normalized = (x_mV - (-0.2912026352134608)) / 0.45653058276514263
```

Class order trên là thứ tự label của dataset MIT-BIH. Nó không tự động trở
thành tail-model output order cho tới khi deployment profile được Kỳ Anh xác
nhận.

## 17. PTB-XL input profile

Profile này cũng chỉ mô tả model input trước model; không phải intermediate
activation I1.

| Thuộc tính | Giá trị đã xác nhận | Trạng thái | Nguồn |
|---|---|---|---|
| Dataset | PTB-XL v1.0.3, official 100 Hz waveform (`filename_lr`) | Frozen cho dữ liệu Week 1 | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json), [`week1_data_protocol.md`](../ml/docs/week1_data_protocol.md) |
| Một sample | ECG hoàn chỉnh 10 giây, 12 lead | Frozen cho dữ liệu Week 1 | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) |
| Sampling rate | `100 Hz` | Đã xác minh | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Số mẫu/lead | `1000` | Đã xác minh | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json), [`verify_ptbxl.py`](../ml/src/verify_ptbxl.py) |
| Lead count/order | 12 lead: `I, II, III, AVR, AVL, AVF, V1, V2, V3, V4, V5, V6` | Đã xác minh | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| WFDB/on-disk view | `(L=1000, C=12)`, time-major | Đã xác minh | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) |
| Model input view | `(N, C=12, L=1000)` | Đã chốt như input contract; model chưa triển khai | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| Model input layout | `N,C,L` | Đã ghi trong config; không phải split layout | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) |
| Input dtype sau chuẩn hóa | `float32` | Đã xác minh | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json), [`verify_ptbxl_normalization.py`](../ml/src/verify_ptbxl_normalization.py) |
| Đơn vị trước chuẩn hóa | mV | Frozen cho dữ liệu Week 1 | [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) |
| Chuẩn hóa | Global Z-score độc lập theo từng lead, fit trên official train folds 1–8 | Đã tạo và xác minh | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json), [`compute_ptbxl_normalization.py`](../ml/src/compute_ptbxl_normalization.py) |
| Label | Multi-label SCP dictionary `code -> likelihood`, canonical sorted JSON; không ép thành single class | Frozen cho data labels | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) |

Mean/std dưới đây theo đúng thứ tự lead trong bảng trên. Mỗi lead dùng
`x_normalized[lead] = (x_mV[lead] - mean[lead]) / std[lead]`.

| Lead | Mean | Standard deviation | Nguồn |
|---|---:|---:|---|
| `I` | `-0.0017299623952233304` | `0.1608335430732975` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `II` | `-0.001494536341715472` | `0.16422381775196612` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `III` | `0.00023504449420140209` | `0.16707484940117887` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `AVR` | `0.001592923642209214` | `0.13945091040235202` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `AVL` | `-0.0009303669766907764` | `0.141941278935629` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `AVF` | `-0.0006051070731427245` | `0.14472921395354096` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `V1` | `0.0001626885980020646` | `0.2346849547768334` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `V2` | `-0.0009458444712366485` | `0.3368574368424479` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `V3` | `-0.0015536168905729672` | `0.33358520037760553` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `V4` | `-0.0013555500057411815` | `0.2983687235838964` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `V5` | `-0.0008047675393271324` | `0.27323134363532264` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |
| `V6` | `-0.00240096285451834` | `0.28038450025068645` | [`ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) |

PTB-XL hiện không có một `class_order` single-label: manifest giữ nguyên SCP
multi-label và likelihood. Contract không được chuyển representation này thành
class index nếu deployment profile chưa quy định phép biến đổi.

## 18. ML deployment và split profile

### 18.1 Trạng thái implementation ML hiện tại

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Kiến trúc 1D-CNN | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`ml/README.md`](../ml/README.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Model đã train/checkpoint | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`ml/README.md`](../ml/README.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Model artifact/ONNX/TFLite/CMSIS-NN | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`week1_requirements_traceability.md`](../ml/docs/week1_requirements_traceability.md) |
| Model deployment/version/profile | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`ml/README.md`](../ml/README.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Split point và activation metadata | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| Quantization | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`week1_requirements_traceability.md`](../ml/docs/week1_requirements_traceability.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| Tail-model output/logits/probability | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | [`ml/README.md`](../ml/README.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| ML deployment golden activation | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | Không có model/split deployment; xem [`week1_verification.md`](../ml/docs/week1_verification.md) |

### 18.2 Deployment profile cần điền trước khi `FROZEN`

| Field | Value | Status | Source |
|---|---|---|---|
| `model_profile_id` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`ml/README.md`](../ml/README.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| `model_name` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`ml/README.md`](../ml/README.md) |
| `model_version` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_verification.md`](../ml/docs/week1_verification.md) |
| `dataset_profile` | Input profiles MIT-BIH v1.0.0 và PTB-XL v1.0.3 đã có; profile dùng cho deployment chưa được chọn | `DEFERRED` | Mục 16–17; [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `split_id` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `layer_name` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `tensor_name` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `dtype` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `rank` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `shape` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `layout` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `quantization_scheme` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_requirements_traceability.md`](../ml/docs/week1_requirements_traceability.md) |
| `scale` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `zero_point` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md) |
| `quantization_axis` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_requirements_traceability.md`](../ml/docs/week1_requirements_traceability.md) |
| `max_tensor_bytes` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | Không có activation; xem [`week1_verification.md`](../ml/docs/week1_verification.md) |
| `tail_output_type` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`ml/README.md`](../ml/README.md), [`week1_verification.md`](../ml/docs/week1_verification.md) |
| `tail_output_dtype` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_verification.md`](../ml/docs/week1_verification.md) |
| `tail_output_shape` | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | `DEFERRED` | [`week1_verification.md`](../ml/docs/week1_verification.md) |
| `class_order` | MIT-BIH input labels có order ở mục 16; tail output order chưa tồn tại. PTB-XL là multi-label SCP, không có single-class order. | `DEFERRED` | [`week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) |

Một row hoàn chỉnh của bảng này phải tồn tại cho từng tuple
`(model_profile_id, split_id)` trước deployment. Shape input ở mục 16–17 MUST
NOT được copy sang bảng này trừ khi model/layer thật chứng minh activation tại
split có đúng shape đó.

### 18.3 `BLOCKING REVIEW ITEM` – nhận diện model profile

Wire format v1 hiện chỉ mang `split_id`; packet không mang `model_profile_id`,
`model_id` hoặc `model_version`. Vì vậy một `split_id` có thể bị hiểu nhầm sau
khi đổi model, và Edge không thể tự phát hiện packet thuộc model sai chỉ từ
packet. Đây là blocker trước `FROZEN` và trước mọi inference deployment, không
phải lý do thay đổi âm thầm wire format đã được Trung duyệt.

Quy tắc bắt buộc trong khi item này còn mở:

- `split_id` chỉ có nghĩa trong tuple `(model_profile_id, split_id)`; không được
  dùng như ID toàn cục độc lập với model.
- Device/Edge MUST NOT chạy I1 inference nếu chưa có cùng active
  `model_profile_id` và cùng profile registry.
- Edge MUST đối chiếu split, dtype, rank, shape, layout và quantization với
  active profile. Split không tồn tại trả `UNSUPPORTED_SPLIT`; metadata sai trả
  `INVALID_TENSOR_METADATA` hoặc status chuyên biệt hiện có.
- Input profile MIT-BIH/PTB-XL không thay thế active deployment profile.

Phương án ưu tiên để loại bỏ ambiguity lâu dài là thêm
`model_profile_id: uint32_le` tại request-metadata offset 0, dịch prefix hiện
tại thêm 4 byte (`split_id` chuyển sang metadata offset 4). Đây là thay đổi
wire không tương thích, tối thiểu 4 byte, cần tăng `protocol_version`, cập nhật
mọi metadata offset/length, định nghĩa status cho unknown model profile và
regenerate protocol golden vector; Trung phải re-approve nếu chọn phương án
này. Phương án không đổi wire là binding/session phải chọn một
`model_profile_id` bất biến trước packet đầu tiên và đóng session khi đổi
profile; phương án này cần được mô tả chính xác trong transport binding. Châu,
Trung và Kỳ Anh phải chọn một trong hai trước `FROZEN`.

### 18.4 Tail-model response contract

Wire response ở mục 9 giữ nguyên và hỗ trợ `CLASS_ID` hoặc `SCORE_VECTOR`,
nhưng ML semantics hiện là
`DEFERRED – chưa được triển khai trong phần ML hiện tại`:

- Không có bằng chứng tail model trả logits, probabilities hay class index.
- Không có output dtype, shape hoặc class order deployment.
- MIT-BIH dataset label order ở mục 16 không được tự động coi là tail output.
- PTB-XL giữ multi-label SCP likelihood; không được tự collapse thành một
  `CLASS_ID`.

Trước deployment, Kỳ Anh MUST điền `tail_output_type`, dtype, shape, phép biến
đổi logits/probabilities (nếu có) và output class/code order; Trung MUST ánh xạ
đúng profile đó vào response codec.

### 18.5 Phân biệt input, activation và golden data

- `(N, 1, 360)` và `(N, 12, 1000)` là model input views.
- Intermediate activation phải xuất phát từ model/layer/split cụ thể và hiện
  chưa tồn tại trong repository.
- Mục 19 chỉ là Protocol golden vector. Repository chưa có
  `ML deployment golden tensor`, nên contract không tạo tensor giả cho mục
  đích kiểm thử model.

## 19. Protocol golden vector

Đây là **Protocol golden vector** cho wire-format v1, không phải ML golden
tensor. `split_id = 1` và tensor nhỏ trong vector là dữ liệu synthetic chỉ để
kiểm thử codec/CRC; chúng không đại diện model hoặc activation thật.

### 19.1 Field values

| Field | Giá trị |
|---|---|
| `magic` | `I1PK` |
| `protocol_version` | `1` |
| `message_type` | `INFERENCE_REQUEST (0x01)` |
| `flags` | `0` |
| `header_length` | `56` |
| `reserved_0`, `reserved_1` | `0`, `0` |
| `total_length` | `64` |
| `request_id` | `0x01020304` |
| `metadata_length` | `24` |
| `payload_length` | `4` |
| `nonce_length` | `0` |
| `split_id` | `1` (synthetic) |
| `dtype` | `INT8 (0x02)` |
| `layout` | `FLAT (0x00)` |
| `ndim` | `1` |
| `quantization_scheme` | `AFFINE_PER_TENSOR (0x01)` |
| `quantization_axis` | `-1` |
| `reserved_tensor` | `0` |
| `element_count` | `4` |
| `dimensions` | `[4]` |
| `scale` | `0.5` (`00 00 00 3f`) |
| `zero_point` | `-1` (`ff ff ff ff`) |
| Quantized payload | `[-3, -1, 1, 3]` = `fd ff 01 03` |
| Dequantized values | `[-1.0, 0.0, 1.0, 2.0]` |
| CRC-32/ISO-HDLC | `0xf2cccb26`, wire bytes `26 cb cc f2` |

### 19.2 Toàn bộ packet (64 byte)

```text
49 31 50 4b 01 01 00 00 38 00 00 00 40 00 00 00
04 03 02 01 18 00 00 00 04 00 00 00 00 00 00 00
01 00 02 00 01 01 ff 00 04 00 00 00 04 00 00 00
00 00 00 3f ff ff ff ff fd ff 01 03 26 cb cc f2
```

Decode MUST thu được đúng các field ở bảng trên, tensor quantized 4 phần tử và
giá trị dequantized tương ứng.

### 19.3 Mã kiểm tra độc lập

Đoạn Python sau tái tạo packet, không cần file raw hay file tạm:

```python
import struct
import zlib

header = struct.pack(
    "<4sBBHHHIIIIHH",
    b"I1PK", 1, 1, 0, 56, 0, 64, 0x01020304, 24, 4, 0, 0,
)
metadata = struct.pack(
    "<HBBBBbBIIfi",
    1, 2, 0, 1, 1, -1, 0, 4, 4, 0.5, -1,
)
payload = struct.pack("<bbbb", -3, -1, 1, 3)
covered = header + metadata + payload
crc = zlib.crc32(covered) & 0xFFFFFFFF
packet = covered + struct.pack("<I", crc)

assert len(header) == 32
assert len(metadata) == 24
assert len(packet) == 64
assert crc == 0xF2CCCB26
assert packet.hex(" ") == (
    "49 31 50 4b 01 01 00 00 38 00 00 00 40 00 00 00 "
    "04 03 02 01 18 00 00 00 04 00 00 00 00 00 00 00 "
    "01 00 02 00 01 01 ff 00 04 00 00 00 04 00 00 00 "
    "00 00 00 3f ff ff ff ff fd ff 01 03 26 cb cc f2"
)
```

### 19.4 Negative CRC test

Đổi byte tại packet offset 56 (payload đầu tiên) từ `fd` thành `fc`, nhưng giữ
CRC wire `26 cb cc f2`. CRC tính lại là `0x4a70ac43`, khác CRC lưu
`0xf2cccb26`; Edge MUST drop packet, không inference và không gửi response dựa
trên `request_id` chưa đáng tin.

## 20. Compatibility và change control

- Lần tích hợp metadata ML này không thay đổi fixed header, tensor metadata,
  response metadata, enum, CRC hay protocol golden vector đã được Trung duyệt.
- Nếu chọn thêm `model_profile_id` trên wire theo mục 18.3, thay đổi đó MUST
  dùng protocol version mới và cần Trung re-approve trước implementation.
- Mọi thay đổi không tương thích về offset, size, semantics bắt buộc, CRC hoặc
  công thức metadata MUST tăng `protocol_version`.
- Receiver MUST từ chối unknown `message_type`, flag, dtype, layout,
  quantization scheme, result type và status theo quy tắc tương ứng; không được
  tự fallback sang enum 0.
- Reserved field MUST bằng 0 khi gửi. v1 từ chối reserved field khác 0 thay vì
  bỏ qua để tránh hai đầu diễn giải khác nhau.
- Sửa wording, ví dụ hoặc implementation note không đổi wire semantics MAY giữ
  version.
- Sau khi `FROZEN`, mọi thay đổi wire format cần Châu và Trung duyệt. Mọi thay
  đổi split profile/tensor metadata cần Kỳ Anh xác nhận và Châu/Trung cập nhật
  implementation tương ứng.
- Việc thêm enum/flag chỉ giữ nguyên version nếu bản `FROZEN` đã quy định rõ
  cơ chế capability negotiation cho extension đó. Contract hiện chưa có cơ
  chế này, vì vậy mặc định phải tăng version.
- Device và Edge SHOULD lưu version/profile trong test fixture và chạy golden
  vector hai chiều trước khi merge thay đổi liên quan I1.

## 21. Acceptance checklist và sign-off

- [ ] Châu xác nhận khả năng pack/unpack trên nRF52840.
- [ ] Trung xác nhận parser và giới hạn buffer trên KV260.
- [ ] Kỳ Anh xác nhận dtype/shape/layout/quantization.
- [ ] Encode trên Device và decode trên Edge cho kết quả giống nhau.
- [ ] Golden packet có CRC đúng.
- [ ] Packet bị sửa một byte bị từ chối.
- [ ] Unknown version bị từ chối đúng status khi envelope vẫn xác minh được.
- [ ] Oversized payload bị từ chối an toàn.
- [ ] Duplicate request không gây inference lặp ngoài ý muốn.
- [ ] Hai phía chốt transport binding riêng.
- [ ] Contract được chuyển từ `REVIEW_CANDIDATE` sang `FROZEN`.

| Vai trò | Người xác nhận | Ngày | Trạng thái |
|---|---|---|---|
| Device/SV1 owner | Châu | — | Chưa xác nhận |
| Edge/SV2 owner | Trung | — | `APPROVED – theo xác nhận của project lead` |
| ML metadata reviewer | Kỳ Anh | — | `READY FOR REVIEW` |

## 22. Open decisions

| Vấn đề | Trạng thái | Owner | Tác động | Điều kiện đóng |
|---|---|---|---|---|
| Nhận diện `model_profile_id` | `BLOCKING REVIEW ITEM` | Kỳ Anh + Châu + Trung | Packet-only parser không phân biệt được cùng `split_id` của hai model/version; chưa thể `FROZEN`. | Chọn explicit field trong protocol version mới và Trung re-approve, hoặc chốt binding/session profile bất biến theo mục 18.3. |
| Model, version và split registry | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | Kỳ Anh | Không có mapping `(model_profile_id, split_id) -> layer/tensor`; không được chạy inference I1. | Có model artifact/version và registry được Kỳ Anh xác nhận, Châu/Trung import cùng một revision. |
| Activation dtype/rank/shape/layout | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | Kỳ Anh | Không thể validate hoặc tính kích thước payload thật. | Điền một deployment-profile row hoàn chỉnh cho từng split và cung cấp golden activation. |
| Quantization deployment | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | Kỳ Anh | Chưa chọn `NONE`, per-tensor hay per-channel; Device/Edge không được giả định scale/zero point. | Chốt scheme, dtype, scale, zero point, axis và xác nhận round/clamp mục 8 cho từng split. |
| Tail-model output | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | Kỳ Anh + Trung | Chưa thể chọn `CLASS_ID`/`SCORE_VECTOR` hoặc diễn giải response payload. | Chốt output type/dtype/shape, logits/probability transform và class/code order; Trung xác nhận response codec. |
| Transport binding ban đầu | `OPEN` | Châu + Trung | Chưa có framing/MTU/reconnect/logical-session definition; USB CDC hiện chỉ là console. | Có binding riêng được hai bên duyệt và chứng minh chuyển nguyên packet I1. |
| `max_payload_bytes`/`max_packet_bytes` | `BLOCKED BY ML PROFILE` | Châu + Trung | Không thể hard-limit buffer hoặc chứng minh vừa RAM Device/Edge. | Có `max_tensor_bytes`, sau đó benchmark/budget RAM và chốt hai constant. |
| Timeout/retry/backoff | `OPEN` | Châu + Trung | Chưa có giá trị interoperable hoặc retry horizon để sizing cache. | Benchmark end-to-end trên binding đã chọn và chốt timeout, retry count, backoff. |
| Duplicate-cache capacity/session scope | `OPEN` | Trung | Chưa chốt lifetime/capacity; retry có thể bị thực thi lại sau eviction. | Chốt logical-session identity, fingerprint, capacity và lifetime bao phủ retry horizon. |
| Nonce/protection | `DEFERRED – chưa được triển khai trong phần ML hiện tại` | Kỳ Anh + Châu + Trung | v1 chỉ có CRC, không có confidentiality/authentication. | Chốt threat model; nếu cần protection, định nghĩa AEAD/MAC, key/nonce/tag và protocol version tương ứng. |
| Device implementation sign-off | `OPEN` | Châu | Contract chưa thể `FROZEN` dù phần protocol đã được chấp thuận về thiết kế. | Châu hoàn tất checklist pack/unpack, limits và cross-device vector rồi ký bảng sign-off. |

## 23. Nguồn dữ liệu và tài liệu tham chiếu trong repository

| Nguồn | Thông tin được dùng trong contract |
|---|---|
| [`ml/README.md`](../ml/README.md) | Phạm vi Week 1; xác nhận chưa train 1D-CNN, chưa export deployment model; môi trường và pipeline tổng quát. |
| [`ml/docs/week1_data_contract.md`](../ml/docs/week1_data_contract.md) | Input views, dtype/label, lead order, multi-label semantics; ONNX/tensor name/split/quantization được hoãn. |
| [`ml/docs/week1_data_protocol.md`](../ml/docs/week1_data_protocol.md) | Sampling, segmentation, class mapping, normalization và split policy của MIT-BIH/PTB-XL. |
| [`ml/docs/week1_requirements_traceability.md`](../ml/docs/week1_requirements_traceability.md) | Xác nhận integration chỉ là pre-model và không có 1D-CNN/ONNX/split deployment/quantization. |
| [`ml/docs/week1_verification.md`](../ml/docs/week1_verification.md) | Bằng chứng shape/dtype/statistics/integrity đã verify và phạm vi chưa triển khai. |
| [`ml/configs/mitdb_week1_config.json`](../ml/configs/mitdb_week1_config.json) | MIT-BIH sampling/window/class order/dtype và frozen normalization values. |
| [`ml/configs/mitdb_normalization.json`](../ml/configs/mitdb_normalization.json) | Mean/std MIT-BIH cùng binding tới train set/config/manifest. |
| [`ml/configs/ptbxl_week1_config.json`](../ml/configs/ptbxl_week1_config.json) | PTB-XL duration/rate/shape/leads/layout/input dtype/label và train folds. |
| [`ml/configs/ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json) | Mean/std chính xác cho 12 lead theo đúng lead order. |
| [`ml/src/build_mitdb_processed.py`](../ml/src/build_mitdb_processed.py) | Construction và validation thực tế của `X float32`, `y int64`. |
| [`ml/src/compute_mitdb_normalization.py`](../ml/src/compute_mitdb_normalization.py) | Cách fit global train-only scalar Z-score MIT-BIH. |
| [`ml/src/compute_ptbxl_normalization.py`](../ml/src/compute_ptbxl_normalization.py) | Cách fit train-only per-lead Z-score PTB-XL. |
| [`ml/src/verify_ptbxl_normalization.py`](../ml/src/verify_ptbxl_normalization.py) | Xác minh independent output `float32`, lead count/order và statistics. |
| [`ml/provenance/week1_run_manifest.json`](../ml/provenance/week1_run_manifest.json) | Provenance của 19 lệnh Week 1 thành công và hashes nguồn/artifact. |

Không có model/checkpoint metadata, ONNX, TFLite, CMSIS-NN, deployment
manifest, Week 2/3 ML document hoặc quantization artifact trong tree ML hiện
tại. Vì vậy contract không dẫn nguồn hay tạo giả các artefact này.
