# I2/1 — hoán vị kênh và affine masking cho activation INT8

**Trạng thái: QUY CÁCH KỸ THUẬT ĐƯỢC SV1 CHỐT; triển khai Device–Edge và xác nhận SV2/SV3 chưa hoàn tất.** Owner định dạng chung: SV1 (Châu); bên tạo activation/tham chiếu Python: SV3 (Kỳ Anh); bên nhận và khôi phục trước tail model: SV2 (Trung). Phiên bản thuật toán/descriptor là `I2/1`, độc lập với `protocol_version` của I1. Tài liệu thay thế bản đề xuất `I2_SV3_provisional_interface.md` trong PR #7; không tuyên bố GV đã duyệt một wire protocol mới.

## 1. Bản đồ hợp đồng và hiện trạng repository

| Hợp đồng / hiện vật | Bên tạo → nhận; định dạng/phiên bản | Đã chốt; điểm còn thiếu và ảnh hưởng |
|---|---|---|
| [I1 v1](i1_device_edge_packet_v1.md) | SV1 Device → SV2 Edge; packet `I1PK`, `protocol_version=1` | Header, CRC, enum và tensor metadata đã mô tả; `flags=0`, `nonce_length=0`, `PROTECTED_PAYLOAD` bị cấm. Chưa có deployment profile, transport hay parser; **không được gửi output I2 qua I1 v1**. |
| **I2/1** (tài liệu này) | SV1/SV3 tạo transform; SV2 đảo transform; INT8 NCL, descriptor 28 B + nonce 12 B, cùng số byte activation | Thuật toán/byte và vector chốt ở đây. Chưa có activation thật, key cấp phát, nonce bền qua reboot, tích hợp firmware/Edge hay đường truyền. |
| [I3](I3_SV3_input.md) | SV3 góp số đo → owner LUT chung; schema `lut.json` vẫn `OPEN` | Chưa có `Pi(s,rho)` hay đơn vị/chỉ số `rho`. I2/1 là **một** cơ chế cố định, không tự tạo giá trị `rho`/LUT hoặc số đo riêng tư. |
| [Dữ liệu ML Tuần 1](../ml/docs/week1_data_contract.md) và [quy trình](../ml/docs/week1_data_protocol.md) | Dữ liệu → SV3; MIT-BIH `(N,1,360)` hoặc PTB-XL `(N,12,1000)`, FP32 model input | Đây là input model, **không phải** activation split. Không suy C/L hay scale/zero point I2 từ các shape đó. |
| [Baseline Tuần 2](../ml/docs/week2_baseline.md) | SV3 PyTorch; ứng viên MIT-BIH FP32 | PR #7 đã vào `main`; checkpoint được mô tả là file local bị ignore, kiến trúc chưa khóa cho Tuần 3. Chưa có quantized split activation/profile. Phần I2 trong báo cáo là ảnh chụp lịch sử của PR #7, không còn là trạng thái mới nhất. |
| [Bàn giao Tuần 3](sv3_sv1_week3_model_handoff.md) | SV3 → SV1; hai Conv FP32 và 20 golden | Quy cách gói đã chốt nhưng hiện vật chưa giao. I2/1 **không đổi** phép thử FP32, checkpoint, shape hoặc ngưỡng `1e-3`. |
| [Device](../device/README.md), [mã build](../device/CMakeLists.txt), [Edge](../edge/README.md), [ML source](../ml/src/mitdb_baseline_model.py) | nRF52840 demo/console; Edge chưa có parser; baseline có 8 Conv1d | Chưa có P1, I1 codec, tail deployment hay integration test trên thiết bị. `20` lần đo vòng lặp Device không phải 20 golden ML. |

Các `.docx` yêu cầu dự án được bản I2 cũ dẫn dưới `ml/docs/project_sources/requirements/` **không có trong Git tree hiện tại**; không suy thêm yêu cầu từ file chưa đọc được. Những quyết định dưới đây do SV1 chốt theo ủy quyền hiện tại, bám mục tiêu P1 đã ghi trong bản I2 cũ. [RFC 8439 §2.3](https://www.rfc-editor.org/rfc/rfc8439.html#section-2.3) là nguồn thuật toán ChaCha20 block; [Nordic nRF52840 Product Specification](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/keyfeatures_html5.html) xác nhận RAM 256 kB. 32 KiB là **giới hạn I2 tự chọn**, không phải RAM còn trống đã đo.

## 2. Mục tiêu và quyết định bắt buộc

**Mục tiêu duy nhất:** biến đổi đảo ngược bit-exact các **byte activation đã lượng tử hóa** bằng hoán vị kênh và affine masking, để nghiên cứu chi phí/khả năng triển khai P1. Đây là **che giấu có khóa**, không phải mã hóa bảo mật, không có tính bí mật được chứng minh, MAC, phát hiện sửa đổi hoặc chống replay trước đối thủ chủ động. Dùng ChaCha20 **chỉ để sinh byte điều khiển**, không XOR ChaCha20 như stream cipher và không dùng Poly1305. `key_id`/nonce/profile trong metadata không được xác thực; CRC của I1 (nếu có trong revision sau) cũng không xác thực. Nếu yêu cầu confidentiality/integrity thực, phải thiết kế AEAD riêng, có tag/overhead và version mới; không gắn nhãn bảo mật cho I2/1.

| Lựa chọn chốt | Lý do ngắn; hệ quả SV1 / SV2 / SV3 |
|---|---|
| INT8 two's complement, NCL `[1,C,L]`, C-contiguous; I2 nhận **byte q** đã lượng tử hóa | Giữ ranh giới với FP32 Tuần 3 và I1 quantization. SV3 phải cấp split profile/scale/zero point và byte q; SV1/SV2 không lượng tử hóa lại trong I2. |
| IETF ChaCha20 block, key 32 B, nonce 12 B, counter bắt đầu 0 | Hai ngôn ngữ có thuật toán/word order công khai và vector độc lập [RFC 8439](https://www.rfc-editor.org/rfc/rfc8439.html#section-2.3.2); SV1/SV2/SV3 dùng cùng dòng byte, không dùng PRNG runtime mặc định. |
| Affine modulo 256 với hệ số lẻ theo **kênh nguồn**, rồi hoán vị Fisher–Yates có rejection sampling | Hệ số lẻ luôn có nghịch đảo modulo 256; SV2 phục hồi từng byte đúng; bias modulo không làm lệch phép chọn permutation. |
| `C<=256`, `1<=C*L<=32768` B, `N=1` | Giới hạn buffer/stack kiểm được trên nRF52840. SV1 cần input và output riêng, C implementation không cấp phát động; SV3 chọn split vừa giới hạn; SV2 từ chối oversize trước cấp phát. Không tuyên bố đã đo RAM thật. |
| Không tag; transformed payload dài đúng `C*L` B | Chỉ **payload tensor** giữ nguyên số byte. Descriptor 28 B và nonce 12 B là overhead ngoài payload; packet/transport thêm overhead khác. SV2 không thể phát hiện sai key hoặc byte bị sửa chỉ bằng `unprotect()`. |

## 3. API, profile, key và nonce

```text
protect(activation_bytes, descriptor28, nonce12, key32, active_profile)
    -> transformed_bytes | I2_ERROR
unprotect(transformed_bytes, descriptor28, nonce12, key32, active_profile)
    -> activation_bytes | I2_ERROR
```

[`i2_reference.py`](i2_ref/i2_reference.py) và [`i2_reference.h`](i2_ref/i2_reference.h) hiện thực cùng chữ ký logic; C nhận thêm độ dài input/descriptor/nonce/key, con trỏ output và capacity. `active_profile` lấy từ registry cục bộ, **không tin** giá trị khai trong descriptor: `(model_profile_id:uint32, split_id:uint16, C:uint16, L:uint32, key_id:uint32, max_payload_bytes:uint32)`; tất cả ID khác 0, max không vượt 32768. SV3 giao phần model/split và quantization của registry cùng checkpoint; SV1/SV2 hoàn thiện phần key/buffer rồi nạp **cùng revision** trước khi chạy. Split không có profile bị từ chối, không đoán shape từ payload. I2/1 chỉ hỗ trợ một mức transform, không suy `rho` của I3.

Mỗi hàng registry deployment phải gắn `model_profile_id`, `model_name/version`, checkpoint hash, `split_id`, tên layer/tensor xuất activation, dtype `INT8`, layout `NCL`, shape `[1,C,L]`, quantization scheme, scale/zero point/axis theo [I1 mục 8](i1_device_edge_packet_v1.md), và `max_payload_bytes`. **Kỳ Anh cung cấp** giá trị mô hình/tensor và bằng chứng lượng tử hóa; **Châu và Trung cùng gán** `key_id`, sender scope, giới hạn buffer thực và xác nhận hai registry byte/giá trị tương đương. Chưa có một hàng registry thực trong repository; vector synthetic bên dưới không phải split profile để triển khai.

Key thật là 32 byte ngẫu nhiên từ CSPRNG, cấp phát qua kênh tin cậy **ngoài** I2/I1, không commit vào repo/log/test. `key_id` khác 0 là nhãn public tra một key duy nhất; registry buộc key với sender và các `(model_profile_id,split_id)` được phép. Đổi key phải cấp `key_id` mới; không dùng key test vector trong vận hành. Cơ chế lưu/provision key trên nRF52840 và KV260 chưa triển khai, nên chưa có bảo đảm bí mật key trên thiết bị.

Nonce là đúng 12 byte: `sender_id:uint32_le || sequence:uint64_le`. `sender_id` được cấp **duy nhất trên mỗi key**; mỗi thông điệp mới tăng `sequence` đơn điệu, bắt đầu từ 1 khi vận hành. SV1 phải lưu bền `next_sequence` **trước khi phát** hoặc lưu bền điểm cuối của một dải sequence đã cấp rồi chỉ dùng các số trong dải; sau reboot bỏ toàn bộ số chưa dùng của dải cũ. Cách cấp dải cần xét độ bền Flash/điện năng thực, hiện chưa triển khai. Nếu không bảo đảm qua reboot/crash, ngừng gửi và rotate key/ID. Hết `uint64` thì ngừng và rotate. Không tái sử dụng `(key_id,nonce)` cho một transform mới, kể cả đổi split/model; retry cùng request phải phát lại **nguyên** metadata, nonce và transformed bytes, không gọi `protect()` lần nữa. Vector synthetic có thể dùng sequence 1 và key công khai. Receiver dùng cache theo key/sender/sequence để xử lý duplicate hợp lệ theo transport, nhưng **không gọi đó là chống replay an toàn** vì không có xác thực. Hàm transform thuần không lưu counter, nên trách nhiệm phát hiện nonce reuse thuộc lớp cấp nonce; nếu phát hiện, trả `NONCE_REUSE` và không phát packet. Sai key bytes với `key_id` đúng có thể cho output rác mà không báo lỗi.

## 4. Descriptor I2/1 và thứ tự byte

Descriptor là đúng **28 byte**, tách khỏi nonce 12 byte và payload; mọi số đa byte little-endian. Không serialize C struct trực tiếp. Hai phía kiểm tra mọi field và registry **trước khi** dùng output.

| Offset | Byte | Trường | Giá trị/ràng buộc |
|---:|---:|---|---|
| 0 | 1 | `i2_version` | `1` |
| 1 | 1 | `algorithm_id` | `1` = `CHACHA20_PERMUTE_AFFINE256` |
| 2 | 1 | `dtype` | `2` = INT8 (cùng mã số enum I1, không biến descriptor thành I1) |
| 3 | 1 | `layout` | `1` = NCL |
| 4 | 4 | `model_profile_id` | `uint32_le`, khác 0, phải khớp registry |
| 8 | 2 | `split_id` | `uint16_le`, khác 0, chỉ có nghĩa cùng model profile |
| 10 | 2 | `N` | `uint16_le = 1` |
| 12 | 2 | `C` | `uint16_le`, 1..256 |
| 14 | 2 | `reserved` | 0; giá trị khác 0 bị từ chối |
| 16 | 4 | `L` | `uint32_le`, khác 0 |
| 20 | 4 | `key_id` | `uint32_le`, khác 0, khớp key registry/profile |
| 24 | 4 | `payload_length` | `uint32_le = C*L`, 1..32768 |

Offset input/output NCL (vì N=1): `channel*L + sample`. Một byte `0x80` biểu diễn INT8 -128 nhưng số học affine làm trên **unsigned residue 128**; byte đầu ra được lưu nguyên 0..255, diễn giải lại two's complement sau đảo transform. Không có scale/zero point trong I2 descriptor; chúng nằm trong split profile/I1 quantization metadata tương ứng và **không biến đổi** theo kênh đã hoán vị. SV2 đảo I2 trước, rồi mới áp dụng quantization metadata trên kênh gốc.

## 5. Thuật toán bit-exact

1. Kiểm độ dài key/nonce/descriptor; version/algorithm/dtype/layout/reserved/ID; `N=1`, `1<=C<=256`, `L>=1`, tích 64-bit `C*L<=min(32768,profile.max_payload_bytes)`, `payload_length=input_length=C*L`, profile/key scope và output capacity. Từ chối trước khi ghi output. C yêu cầu input/output **không overlap**.
2. Dùng [RFC 8439 §2.3 ChaCha20 block](https://www.rfc-editor.org/rfc/rfc8439.html#section-2.3) với key 32 B, nonce 12 B và block counter 0,1,2,...; nối block 64 byte tạo dòng byte. Word state, output và mỗi nhóm 4 byte bên dưới đều little-endian. **Không** XOR dòng này với tensor.
3. Lấy **C byte đầu** theo thứ tự kênh nguồn `s=0..C-1`: `a[s] = byte | 1` (số lẻ 1..255). Lấy **C byte tiếp**: `b[s] = byte` (0..255). Không lấy đan xen a/b.
4. Đặt `p[i]=i`. Với `i=C-1` giảm đến 1, lấy lần lượt 4 byte thành `r:uint32_le`. Đặt `m=i+1`, `limit=2^32-(2^32 mod m)`; nếu `r>=limit`, bỏ **đúng 4 byte đó** và lấy tiếp. Sau đó `j=r mod m`, hoán đổi `p[i]`/`p[j]`. `p[out_channel]` là **kênh nguồn**.
5. `protect`: với `s=p[o]`, mỗi `l=0..L-1`, `out[o*L+l] = (a[s]*in[s*L+l] + b[s]) mod 256`.
6. `unprotect`: tạo lại cùng `a,b,p` từ key/nonce; với `s=p[o]`, tìm nghịch đảo duy nhất `ainv[s]` sao cho `a[s]*ainv[s] mod 256 = 1`; `out[s*L+l] = ainv[s]*(in[o*L+l]-b[s]) mod 256`. Output là **đúng byte q ban đầu** nếu key/descriptor/nonce/payload đúng. Không có phép toán float trong I2.

Nếu nhiều trường cùng sai, ưu tiên lỗi theo thứ tự: con trỏ/kiểu đối số, độ dài nonce, độ dài key, profile cục bộ và giới hạn của nó, độ dài descriptor, version, algorithm, field descriptor, giới hạn tensor, độ dài input, đối chiếu model/split/shape, key scope, output capacity, rồi overlap C. Cả hai reference áp dụng thứ tự này cho phần API tương ứng; lớp registry/cấp nonce có thể từ chối sớm hơn **trước khi gọi** transform.

Độ phức tạp O(C*L+C), không cần buffer tensor thứ ba; C reference dùng mảng kênh và ChaCha block cỡ nhỏ trên stack. Không đưa key hoặc state PRNG vào metadata. Trường nonce/key ID public và không có tag.

## 6. Lỗi và khả năng phát hiện

| Lỗi API | Điều kiện, xử lý |
|---|---|
| `INVALID_ARGUMENT`, `INVALID_NONCE`, `KEY_UNAVAILABLE` | Null/overlap C, nonce không 12 B, key không 32 B; không ghi output. |
| `INVALID_PROFILE`, `PROFILE_MISMATCH`, `KEY_SCOPE_MISMATCH` | Registry sai/thiếu, shape/model/split sai, key ID không thuộc profile; reject. Unknown model/split ở registry được lớp tích hợp phân loại riêng, không giả định một profile mặc định. |
| `INVALID_METADATA`, `UNSUPPORTED_VERSION`, `UNSUPPORTED_ALGORITHM` | Độ dài/field descriptor sai, version/algorithm không hỗ trợ; không fallback. |
| `SIZE_LIMIT`, `LENGTH_MISMATCH`, `BUFFER_TOO_SMALL` | Vượt giới hạn 32768/profile, tích/độ dài không khớp, output thiếu capacity; reject trước biến đổi. |
| `NONCE_REUSE` | Lớp cấp nonce phát hiện sequence đã dùng hoặc không lưu bền được; dừng gửi/rotate key. Không thể được phát hiện chỉ từ hàm transform thuần. |

Sửa một byte transformed payload hoặc dùng sai key bytes **không bắt buộc tạo lỗi**: có thể trả một tensor byte khác nhưng đúng shape. Đây là giới hạn bản chất do không có authentication. Không được coi test round-trip là bằng chứng bảo mật.

## 7. Vector chuẩn và mã kiểm tra

Các vector [JSON](i2_ref/vectors.json) dùng key public `00 01 ... 1f`, không liên quan model/activation thật. Byte input và output là hex, không phải chuỗi số thập phân INT8. Descriptor là 28 B, nonce là 12 B; không có tag.

| ID | `C,L`; descriptor hex; nonce hex | Input hex → transformed hex |
|---|---|---|
| `three_channels_extreme_int8` | `3,4`; `0101020140302010070001000300000004000000040302010c000000`; `010000000100000000000000` | `80ff00017f05fe64643210aa` → `eb6c6b6a86889b3dffad6ba5` |
| `one_channel` | `1,5`; `01010201020000000100010001000000050000000200000005000000`; `020000000100000000000000` | `0080ff7f01` → `6beb0080d6` |

Vector lỗi trong JSON: version 2 → `UNSUPPORTED_VERSION`; algorithm 2 → `UNSUPPORTED_ALGORITHM`; dtype 1 → `INVALID_METADATA`; shape >32768 B → `SIZE_LIMIT`; model profile khác → `PROFILE_MISMATCH`; key ID khác → `KEY_SCOPE_MISMATCH`; input thiếu byte → `LENGTH_MISMATCH`; nonce 11 B → `INVALID_NONCE`; output C thiếu capacity → `BUFFER_TOO_SMALL`. Thử sửa một byte transformed output hoặc dùng sai key bytes phải cho plaintext **khác** mà không hứa báo lỗi. [`test_i2.py`](i2_ref/test_i2.py) kiểm cả Python/C theo hai vector, các lỗi, nhiều shape và [RFC 8439 ChaCha20 block vector](https://www.rfc-editor.org/rfc/rfc8439.html#section-2.3.2). Chạy từ Git root: `python -B contracts/i2_ref/test_i2.py` với Python 3.11+ và host `gcc` trên PATH; test tự biên dịch C vào thư mục tạm. **Đây chỉ là kiểm thử trên host, chưa phải nRF52840/KV260.**

## 8. Ranh giới I1 và việc triển khai

[I1 v1](i1_device_edge_packet_v1.md) giữ nguyên `protocol_version=1`, `flags=0`, `nonce_length=0`, không chấp nhận `PROTECTED_PAYLOAD`. [Đề xuất I1 v2 riêng](i1_device_edge_packet_v2_proposal.md) định nghĩa cách mang descriptor/nonce/INT8 và version gating; đó là **đề xuất wire**, chưa phải I1 v2 được Trung phê duyệt hoặc triển khai. Trước khi truyền thật, SV1/SV2 phải chốt transport, parser, buffer, model/split registry, quantization, response semantics, retry và kiểm interoperability trên thiết bị. Nếu yêu cầu bảo mật mật mã, thay I2/1 bằng thiết kế AEAD/tag có version mới thay vì mở flag cho phép biến đổi này dưới tên encryption.

SV3 phải cung cấp split activation INT8 thật, profile/quantization và Python export/vector bổ sung từ model thực; SV1 port C vào firmware với key/nonce state và đo RAM/latency; SV2 port/kiểm C hoặc implementation độc lập ở Edge, đảo transform trước dequantize/tail. Không tuyên bố phần nào hoàn thành chỉ từ host reference. I3 vẫn cần định nghĩa `rho`/đơn vị và **số đo thật** trước khi tạo LUT; Tuần 3 vẫn nghiệm thu FP32 và 20 golden theo hợp đồng riêng.
