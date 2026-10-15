# I1 v1 — addendum r1: deployment profile theo approved registry

| Thuộc tính | Giá trị |
|---|---|
| Áp dụng cho | [I1 v1](i1_device_edge_packet_v1.md), `protocol_version=1`, trạng thái `REVIEW_CANDIDATE` |
| Revision registry | `mitdb-week5-i2-registry-v1-r1` |
| Nguồn | [approved registry](sv3_week5_approved_registry_v2.json) SHA-256 `79392b6db73cde6d83eadb1f265f14102888ebdbf8ea1b72b6c127c5566eed24`; [approval](sv3_week5_allocation_approval_v2.json) SHA-256 `a84b5caf89ffb7f8e11be2b308e2d4e1947e4d4f7ed291c47df083d0e15c7a7d`; [allocation](sv3_week5_allocation_v2.md) |
| Ngày | 15/10/2026 (Asia/Saigon) |

Addendum này điền các mục I1 v1 còn ghi TBD/DEFERRED bằng quyết định đã có
trong registry đã duyệt. Nó **không** đổi byte, field, enum, CRC hay golden
vector của I1 v1. File I1 v1 được giữ nguyên vì nội dung của nó nằm trong các
receipt lịch sử (mọi file `contracts/*` đều được logger băm). Khi I1 v1 và
addendum khác nhau ở mục deployment, addendum này là nguồn hiện hành; wire format
vẫn theo I1 v1. Mục nào chưa có quyết định được ghi rõ là **OPEN** ở mục 6.

## 1. Logical split, wire split và model profile

- **Logical split `s` (0..10)** là chỉ số điểm cắt của mô hình theo manifest
  all-split `a6d16809…` và theo bảng `split_op_counts` của firmware. `s` chỉ dùng
  trong công cụ (ví dụ lệnh `RUN n s`), **không** xuất hiện trên wire.
- **Wire `split_id`** (`uint16_le`, metadata offset 0 của I1 v1 và offset 8 của
  descriptor I2/1) được cấp tường minh từng hàng: `s → 256+s`. Không suy wire ID
  từ `s` bằng công thức khi không có registry; công cụ test dùng ID khác chỉ là
  `PUBLIC_TEST_ONLY`.
- **`model_profile_id` = 1296651265 (`0x4D495401`)** định danh model
  `mitdb_week2_cnn_v1`, checkpoint
  `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`. Wire
  `split_id` chỉ có nghĩa trong cặp `(model_profile_id, split_id)`.
- I1 v1 **không có** field `model_profile_id` (mục 18.3 của I1 v1). Hai đầu phải
  nạp cùng revision registry trước packet đầu tiên; packet v1 tự nó không chứng
  minh thuộc profile nào. Registry chỉ lên kế hoạch I1 v2 (`packet_planning`,
  `DESIGN_ONLY`), nên quyết định ở mục 18.3 vẫn mở.
- Key label `65537` và sender `131073` chỉ dùng cho I2/1. I1 v1 vẫn bắt buộc
  `flags=0`, `nonce_length=0`, không mang payload đã biến đổi.

| `s` | Wire `split_id` | Head endpoint | Shape gốc | Layout gốc | Thực thi |
|---:|---:|---|---|---|---|
| 0 | 256 | normalized_model_input (identity head) | `[1,1,360]` | NCL | Device head / Edge tail |
| 1 | 257 | features.1 | `[1,16,360]` | NCL | Device head / Edge tail |
| 2 | 258 | features.4 | `[1,16,180]` | NCL | Device head / Edge tail |
| 3 | 259 | features.6 | `[1,32,180]` | NCL | Device head / Edge tail |
| 4 | 260 | features.9 | `[1,32,90]` | NCL | Device head / Edge tail |
| 5 | 261 | features.11 | `[1,48,90]` | NCL | Device head / Edge tail |
| 6 | 262 | features.14 | `[1,48,45]` | NCL | Device head / Edge tail |
| 7 | 263 | features.16 | `[1,64,45]` | NCL | Device head / Edge tail |
| 8 | 264 | features.19 | `[1,64,22]` | NCL | Device head / Edge tail |
| 9 | 265 | classifier.3 | `[1,32]` | NC | Device head / Edge tail |
| 10 | 266 | classifier.4 (logits) | `[1,5]` | NC | Device-only / empty-tail |

## 2. Device-only / empty-tail (`s=10`)

`s=10` là logits FP32 5 lớp theo thứ tự `N,S,V,F,Q` (nhãn của MIT-BIH, mục 16
I1 v1), đã tính xong trên Device. Registry ghi `edge_tail_executable=false`,
`reference_tail=identity/empty-tail`: Edge **không** có `tail_s10` và không chạy
mô hình cho split này; nếu nhận tensor `s=10`, tail tham chiếu là phép đồng
nhất trên logits đã giải lượng tử. Cách mã hóa response cho trường hợp này (và
cho các split khác) vẫn theo mục 18.4 I1 v1, chưa chốt (mục 6).

## 3. Tensor metadata cho activation INT8

Các giá trị dưới đây áp dụng cho mọi split của profile, theo mục 7–8 I1 v1:

| Field I1 v1 | Giá trị |
|---|---|
| `dtype` | `INT8` (`0x02`) |
| `quantization_scheme` | `AFFINE_PER_CHANNEL` (`0x02`), `quantization_version=ncl-int8-fp16-v1-review` |
| `quantization_axis` | `1` (trục kênh) |
| `quant_count` | `C` |
| `scales[C]` | `float32_le`, đúng bằng giá trị FP16 đã lưu được mở rộng sang FP32: hữu hạn, dương, `2^-14 ≤ scale ≤ 65504`; kênh toàn 0 có scale `1.0`. Không gửi scale FP32 thô hay FP16 trên wire v1 |
| `zero_points[C]` | `int32_le = 0` |
| `element_count`, `payload_length` | `C×L` byte, không vượt 5760 |
| `layout`, `ndim`, `dimensions` | `s=0..8`: `NCL`, 3, `[1,C,L]`. `s=9,10`: xem mục 6 (OPEN) |

Với `NCL`, `metadata_length = 12 + 4×3 + 4 + 8×C = 28 + 8×C` byte. Trần đã duyệt
cho cả Device và Edge: payload 5760 B, `C ≤ 64`, mảng scale FP16 128 B, mảng
scale FP32-LE 256 B, metadata lượng tử theo kênh đầy đủ 516 B
(`4 + 8×64`). Từ đó packet I1 v1 lớn nhất của profile là
`32 + (24 + 516) + 0 + 5760 + 4 = 6336` B; ngân sách 6380 B của I1 v2 trong
registry bằng con số này cộng 4 B `model_profile_id`, 28 B descriptor I2 và
12 B nonce. Đây là cận suy ra từ trần đã duyệt; registry vẫn ghi packet buffer,
parser và transport là `NOT_ACCEPTED`.

## 4. Miền giá trị INT8

- Kiểu `INT8` của I1 v1 vẫn là số bù hai với miền lưu trữ `[-128,127]`.
- Profile lượng tử hóa đã duyệt là **đối xứng**:
  `q = clamp(round_half_even(x / s), -127, 127)`, `z = 0`,
  `x̂ = q × s`. Bên tạo không bao giờ sinh `q = -128`; bên nhận phải **từ chối**
  tensor lượng tử chứa `q = -128` (không giải lượng tử, không chạy tail).
- Quy tắc này chỉ áp dụng cho **giá trị của tensor lượng tử** theo profile: sau
  khi đảo I2/1 (nếu có) và trước khi giải lượng tử. Byte `0x80` vẫn hợp lệ trong
  payload đã biến đổi I2/1, nonce, header, metadata, CRC và toàn bộ frame.

| Thành phần | Vị trí | Hành vi |
|---|---|---|
| Producer C trên MCU | `device/week5/quantization.c` | Clip `[-127,127]` trước làm tròn |
| Producer/consumer tham chiếu | `ml/src/quantization.py` | Clip `[-127,127]`; giải lượng tử từ chối `-128` |
| Consumer C | `week5_dequantize()` trong `device/week5/quantization.c` | Từ chối `-128` và scale ngoài `[0x0400, 0x7bff]` |
| I2/1 | `contracts/i2_ref/` | Biến đổi mọi byte 0..255, kể cả `0x80` |
| Codec I1 | Chưa có triển khai | — |
| Kiểm tra | `device/scripts/test_i1_profile.py`, `device/scripts/test_week5_quantization_c.py`, `ml/scripts/test_week5_quantization.py` | Biên `±127`, từ chối `-128`, độ dài payload, scale hợp lệ |

## 5. Các mục TBD/DEFERRED của I1 v1 đã có quyết định

| Mục I1 v1 | Quyết định hiện hành |
|---|---|
| 7.4 mapping `split_id` | Bảng mục 1 |
| 8 quantization deployment | Mục 3 và 4 |
| 12 `max_payload_bytes` | 5760 B (trần profile đã duyệt) |
| 18.1–18.2 model, version, checkpoint, split, dtype/shape/layout, quantization, `max_tensor_bytes` | Mục 1 và 3; dataset profile là MIT-BIH (mục 16 I1 v1) |
| 18.5 ML deployment golden | 220 tensor INT8/scale FP16 tham chiếu của `ml/artifacts/week5/quantization20/manifest.json` (anchor `8e20ed05…`), ngoài Git |
| 22 model/split registry | Đã có registry revision chung hai phía |

## 6. Còn OPEN (addendum này không quyết định)

- Mục 18.3: mang `model_profile_id` trên wire (I1 v2) hay ràng buộc theo
  session/transport cho I1 v1.
- Biểu diễn `s=9,10` (shape gốc NC) trong I1 v1: I1 v1 không có layout NC,
  còn I2/1 dùng `i2_shape_NCL = [1,C,1]`. Cần Châu và Trung chọn, ví dụ `NCL`
  với `L=1`, trước khi gửi hai split này qua I1.
- Mã trạng thái khi Edge từ chối `q = -128` (gợi ý `UNSUPPORTED_QUANTIZATION`
  `0x000c`, chưa được duyệt).
- Mục 18.4 response (`CLASS_ID` hay `SCORE_VECTOR`), transport binding,
  timeout/retry, duplicate cache, chấp thuận `max_packet_bytes`.
- I1 v2, cấp phát key, nonce bền qua reboot và truyền P1: `NOT_ACCEPTED` theo
  registry.
