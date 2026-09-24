# I1 v2 — đề xuất mang activation đã biến đổi bằng I2/1

**Trạng thái: ĐỀ XUẤT WIRE; CHƯA ĐƯỢC SV2 PHÊ DUYỆT, CHƯA TRIỂN KHAI.** Tài liệu này tách khỏi [I1 v1](i1_device_edge_packet_v1.md). I1 v1 vẫn bắt buộc `flags=0`, `nonce_length=0` và không mang transformed/protected payload. [I2/1](i2_protection_v1.md) chốt phép biến đổi offline; tài liệu này chỉ đề xuất cách đưa nó vào packet Device–Edge khi đã có split activation INT8 thật.

## 1. Version gating và semantics

- Giữ magic `I1PK`, fixed header 32 byte, little-endian, quy tắc length/CRC và thứ tự xác minh envelope của I1 v1. **Đặt `protocol_version=2`**. Parser v1 phải từ chối version 2; parser v2 không được áp dụng metadata offset v1 cho packet v2. Không có fallback sang v1 sau khi thấy flag I2.
- Với `INFERENCE_REQUEST` v2, `flags=0` (tensor thường) hoặc **`flags=0x0002`** (`I2_TRANSFORMED`). Bit `0x0001` mang tên reserved `PROTECTED_PAYLOAD` ở v1 vẫn không được dùng trong đề xuất này, tránh gọi I2 là encryption/authentication. Các bit khác bị từ chối. Response/error v2 có `flags=0`, `nonce_length=0` và metadata 8 byte như mục 9 I1 v1, nhưng `protocol_version=2`.
- V2 phải mang `model_profile_id` tường minh để loại bỏ nhập nhằng `(model_profile_id,split_id)` ở I1 v1; I2 descriptor cũng chứa ID đó và phải khớp. Không dùng input profile MIT-BIH/PTB-XL thay model deployment profile.

## 2. Request metadata và nonce đề xuất

Packet v2 vẫn là `[fixed_header 32][request_metadata][nonce][payload][CRC32 4]`. `metadata_length` là đúng tổng các đoạn sau, không có trailing bytes:

| Metadata offset | Độ dài | Ý nghĩa |
|---:|---:|---|
| 0 | 4 | `model_profile_id:uint32_le`, khác 0, tra registry active |
| 4 | `12 + 4*ndim + quantization_bytes` | Toàn bộ [tensor metadata I1 v1 mục 7–8](i1_device_edge_packet_v1.md), **dịch offset +4**; `split_id`, dtype/layout/shape và quantization lấy từ profile thật |
| Sau tensor metadata | 28 nếu `flags=0x0002`; 0 nếu `flags=0` | [I2 descriptor](i2_protection_v1.md) đúng 28 byte |

Nếu `flags=0x0002`: tensor metadata I1 phải là `INT8`, `NCL`, `ndim=3`, `dimensions=[1,C,L]`, affine quantization được registry cho phép; `element_count=payload_length=C*L<=32768`; I2 descriptor lặp lại `model_profile_id`, `split_id`, dtype/layout/shape và `payload_length`, **mọi bản sao phải khớp từng giá trị**. `nonce_length=12`, field nonce chứa đúng `sender_id:uint32_le || sequence:uint64_le` của I2. Payload là transformed bytes, **chỉ payload không tăng byte**; request tăng 28 byte descriptor + 12 byte nonce so với request cùng tensor metadata v2 không biến đổi. Không có tag; CRC chỉ phát hiện lỗi ngẫu nhiên, không xác thực.

Nếu `flags=0`: không có I2 descriptor, `nonce_length=0`, payload/metadata tensor theo quy tắc I1 v1 và `model_profile_id` thêm ở đầu. `header_length=32+metadata_length+nonce_length`, `total_length=header_length+payload_length+4` như I1 v1. Receiver kiểm giới hạn/overflow trước cấp phát, CRC trước khi tin metadata/request ID, rồi kiểm version/flag/profile. Không chạy tail model nếu I2 validation hoặc unprotect lỗi; sau unprotect mới dequantize với quantization metadata của **kênh gốc**.

## 3. Cần hoàn tất trước khi chấp thuận I1 v2

SV1 và SV2 phải duyệt lại bảng status v2 (unknown model/key, I2 metadata và nonce/retry), giới hạn packet/buffer thực, cache duplicate, transport framing, lỗi trước/sau CRC, response semantics và vector packet v2. Kỳ Anh phải giao registry `(model_profile_id,split_id)` cùng dtype, shape, scale/zero point/axis, activation golden INT8 và tail-output semantics. Không lấy shape input hoặc golden hai Conv FP32 Tuần 3 điền thay. SV1/SV2 chỉ bật v2 sau khi kiểm cross-device encode/decode/unprotect, memory/latency và sign-off; hiện **chưa có I1 v2 implementation hoặc packet PASS**.

Nếu sau này cần bí mật/xác thực thực sự, I2/1 không đáp ứng; cần giao thức/thuật toán AEAD có tag, nonce/key rule và version mới được duyệt. Không thêm MAC/tag ngầm vào payload I2/1 rồi vẫn báo `payload_length=C*L`.
