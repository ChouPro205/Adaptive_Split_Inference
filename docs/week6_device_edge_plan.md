# Kế hoạch tuần 6 — Device–Edge qua BLE

Ngày lập: 15/10/2026. Người duyệt thiết kế: Lê Hải Châu (trưởng nhóm, SV1). Tài
liệu này theo dõi **triển khai và nghiệm thu**; thiết kế đã chốt nằm ở:

- [I1 v2](../contracts/i1_device_edge_packet_v2.md) — packet, thứ tự lỗi, response.
- [I1 BLE binding v1](../contracts/i1_ble_binding_v1.md) — GATT, fragment, timeout/retry, cache.
- [I2/1 nonce và provisioning v1](../contracts/i2_nonce_provisioning_v1.md) — NVS, dải sequence, key.
- [Reference/test host](../contracts/i1v2_ref/test_i1v2.py) và [vector](../contracts/i1v2_ref/vectors.json).

Trạng thái hiện tại: thiết kế APPROVED; mọi hạng mục dưới đây **chưa chạy** trên
nRF52840, laptop BLE hoặc KV260. Không mục nào được đánh dấu ACCEPTED trước khi
có bằng chứng theo đúng tiêu chí.

Cập nhật SV3 ngày 16/10/2026: [gói 50 vector P1 và output semantics](../ml/docs/week6_p1_delivery.md) đã bàn giao A+B với bằng chứng host mới. Các tiêu chí trên thiết bị và KV260 bên dưới chưa được thay bằng kết quả host.

## 1. Tiêu chí nghiệm thu tuần 6

| # | Tiêu chí | Bằng chứng tối thiểu |
|---:|---|---|
| 1 | P1 C trên MCU khớp Python **50/50** vector từ gói bàn giao chính thức của SV3 (§2.3) | Capture USB CDC gồm 50 dòng, mỗi dòng hash transformed bytes của C so với giá trị Python trong gói; firmware hash; script kiểm offline exit 0 |
| 2 | Unprotect khôi phục **đúng byte** tensor lượng tử của cả 50 vector | So sánh byte-exact q gốc ↔ q sau `unprotect()`; ít nhất một vector có `0x80` trong transformed bytes |
| 3 | **1000 application packet hợp lệ** qua BLE loopback (dongle → BLE → laptop → trả nguyên frame → dongle) được nhận/trả đủ, CRC đúng 100%, bytes khớp 100% | Log counter §11 binding với `planned = 1000`, `completed = 1000`, `crc_fail = byte_mismatch = failed = 0`; log CRC phía laptop |
| 4 | Có packet nhiều fragment và kích thước biên | Trong 1000 packet có ít nhất: 113 B (s10 thường), 153 B (s10 I2/1), 6124 B (s3 I2/1 lớn nhất của registry), 6380 B (trần, profile test); mỗi cỡ chạy ở MTU đã thương lượng **và** ở cấu hình ép MTU 23 |
| 5 | Báo đủ `planned/sent/received/timeout/retry/duplicate/crc_fail/byte_mismatch/failed` | Báo cáo theo application packet; mẫu số là `planned`; không bỏ packet mất; không dùng số fragment thay số packet |
| 6 | Negative test chạy **tách riêng**, không trộn vào 1000 packet hợp lệ | Lần chạy riêng: frame hỏng CRC, fragment thiếu/trùng/sai thứ tự (do công cụ laptop chèn), mất kết nối giữa transfer, timeout, retry; kết quả đúng hành vi binding §5–6 |
| 7 | Kiểm thử reboot/mất điện cho nonce **trước** khi nghiệm thu truyền I2/1 | Theo [nonce §8](../contracts/i2_nonce_provisioning_v1.md) mục 1–6: không sequence nào lặp/giảm qua ≥ 100 lần reset, kể cả ngắt nguồn lúc ghi; lỗi ghi → dừng; DFU giữ state |
| 8 | Bằng chứng build và đo tài nguyên/latency trên MCU | Log build NCS 3.4.0, ELF/map: Flash, RAM tĩnh, image kết thúc trước `0xDC000`; stack high-water đo lúc chạy; DWT cycle cho quantize, protect, encode, mỗi transfer; RTT loopback theo cỡ frame |

Quy tắc chung:

- Software loopback hoặc USB CDC không thay cho truyền radio ở tiêu chí 3–4.
- Echo là diagnostic (`stream 0x02`), không phải inference response; tiêu chí 3
  không cần DPU/tail.
- Timeout/retry dùng cấu hình bench ở binding §7 và được ghi lại; đó là cấu hình,
  không phải kết quả đo. Mọi số latency/throughput chỉ lấy từ phép đo của lần chạy.
- Packet I2/1 trong loopback chỉ dùng key test của bench (không phải key public của
  vector, không phải key vận hành) và chỉ sau khi tiêu chí 7 đạt; trước đó loopback
  dùng request thường (`flags=0`).
- Kết quả tuần 6 có receipt/bằng chứng mới; không sửa receipt tuần 5. Receipt
  [tuần 5](../ml/provenance/week5-current-20261015/README.md) chứng nhận snapshot
  `3caf40a` (verifier v3 PASS thường/`-O` ngày 15/10/2026); trên source có file
  tuần 6, verifier v3 trả `FAIL: Incomplete source provenance` đúng thiết kế, vì
  vậy kiểm lịch sử phải chạy trên snapshot đó.

## 2. Đầu vào còn thiếu theo người

### 2.1 Châu (SV1, Device)

| Hiện vật | Tiêu chí bàn giao |
|---|---|
| Ứng dụng firmware `device/week6/` (BLE peripheral theo binding, encoder I1 v2, chế độ echo, P1 C port, nonce NVS) | Build NCS 3.4.0 `nrf52840dongle/nrf52840`, không sửa file tuần 3–5 bị hash; encoder chạy trên MCU tạo đúng từng byte các golden I1 v2 trong `vectors.json` |
| Công cụ echo laptop (Windows, BLE central) | Dùng đúng UUID/fragment/MTU của binding; trả nguyên frame; ghi log CRC và counter; có chế độ chèn lỗi cho tiêu chí 6 |
| Script thu và kiểm bằng chứng tuần 6 | Kiểm offline 50 vector P1, counter loopback, phân bố cỡ frame; exit code rõ ràng |
| Key test cho bench (sinh ngoài repo) và provisioning qua USB CDC | Không commit/log key; chỉ ghi `key_id`, `sender_id`, `key_check` |
| Revision registry cấp cặp key/sender dự phòng | **Chỉ cần nếu** state nonce mất/hỏng; trước đó không cần |

### 2.2 Trung (SV2, Edge KV260)

| Hiện vật | Tiêu chí bàn giao |
|---|---|
| Xác nhận KV260 làm BLE central: bộ chuyển Bluetooth LE trên USB được image KV260 nhận, BlueZ quét thấy `ASI-SV1`, kết nối, bật notification, đọc MTU | Log `bluetoothctl`/script; phiên bản BlueZ và kernel |
| Parser/encoder I1 v2 trên Edge | Đạt mọi vector `golden`, `request_negative`, `pipeline`, `response` trong `contracts/i1v2_ref/vectors.json` với đúng mã lỗi và đúng thứ tự §7 |
| Reassembly BLE và duplicate cache | Đạt quy tắc binding §5, §8; cấu hình TTL thỏa ràng buộc §7 |
| Đường xử lý sau giải lượng tử | Unprotect trước, từ chối `q=-128`, dequantize theo kênh gốc, reshape NC cho s9; s10 trả identity, không có `tail_s10` |
| Tail s0..s9 chạy được trên KV260 | Danh sách xmodel/fallback từ `compile_all_splits.sh` có provenance hợp lệ (không synthetic), kèm sai số hoặc accuracy đo trên KV260; trước khi có, Edge trả `INFERENCE_FAILED` thay vì giả kết quả |
| File key Edge (ngoài repo) | Đối chiếu `key_check` với Device; không commit/log key |
| Xác nhận kỹ thuật I1 v2 và binding | Ký bảng xác nhận trong I1 v2 §14 sau khi các mục trên đạt |

### 2.3 Kỳ Anh (SV3, ML)

| Hiện vật | Tiêu chí bàn giao |
|---|---|
| **Gói 50 vector P1** chính thức (đã nêu "theo lịch tuần 6" trong handoff tuần 5) | 50 tensor q INT8 thật lấy từ model/checkpoint đã duyệt, phủ cả 11 split (s0..s10), mỗi vector có: split ID wire, `[1,C,L]`, scale FP16 bits, descriptor 28 B, nonce 12 B dùng `sender_id=131073` và sequence riêng, transformed bytes từ `ml/src/p1.py`, key test công khai ghi rõ `PUBLIC_TEST_ONLY`; manifest có SHA-256 từng file và lệnh tái lập; ít nhất một vector có `0x80` trong transformed bytes |
| Xác nhận ngữ nghĩa response | Logits 5 lớp thứ tự `N,S,V,F,Q`, không softmax; tie → index nhỏ nhất; khớp tail tham chiếu |
| Đánh giá sai số luồng DPU (phối hợp Trung) | Accuracy/sai số khi tail chạy qua lượng tử DPU so với tail FP32 trên tập test chính thức, không đổi gate tuần 5 |

## 3. Hiện vật đã có và tái sử dụng được

| Hiện vật | Vị trí | Dùng cho |
|---|---|---|
| Registry/approval đã duyệt | `contracts/sv3_week5_approved_registry_v2.json`, `..._approval_v2.json` | ID, shape, trần buffer |
| I2/1 reference Python/C + vector | `contracts/i2_ref/` | Port P1 C lên MCU |
| P1 Python và kiểm 10 000 round-trip | `ml/src/p1.py`, `ml/scripts/test_week5_p1_v2.py` | Sinh vector 50 của SV3 |
| Lượng tử hóa C đã nghiệm thu trên MCU | `device/week5/quantization.c` | Tạo q và scale trên Device |
| 220 tensor INT8 + scale FP16 tham chiếu | `ml/artifacts/week5/quantization20/` (ngoài Git, hydrate theo `ml/docs/week5_delivery_v2.md`) | Nguồn tensor thật cho loopback và kiểm cỡ frame |
| Head 11 split trên MCU (tuần 4–5) | `device/src/week4_head.c`, `device/week5/` | Sinh activation trên Device |
| I1 v2 reference, BLE reference, mô hình nonce, vector | `contracts/i1v2_ref/` | Golden cho firmware, công cụ laptop, KV260 |
| Script lượng tử/biên dịch tail | `edge/quantize_tail.py`, `edge/compile_all_splits.sh` | Chuẩn bị tail DPU (chưa chạy trên KV260) |

**SV3 đã bàn giao:** [50 vector P1 và output semantics host](../ml/docs/week6_p1_delivery.md), có manifest và Python/C logs; chưa thay nghiệm thu MCU tiêu chí 1–2.

**Chưa được bàn giao:** bất kỳ firmware BLE, công cụ echo
laptop, parser I1 v2 trên KV260, xmodel tail đã chạy trên KV260; key bench và state
nonce trên Flash; mọi số đo RAM/stack/latency của tuần 6.

## 4. Thứ tự thực hiện

1. SV1: firmware BLE + echo với request thường; tiêu chí 3–6 và 8 (phần truyền).
2. SV3 bàn giao gói 50 vector → SV1 port P1 C; tiêu chí 1–2.
3. SV1: NVS nonce + provisioning bench; tiêu chí 7; sau đó loopback có I2/1.
4. SV2: KV260 central + parser theo vector; thay laptop bằng KV260 ở chế độ echo,
   rồi chế độ inference khi tail sẵn sàng.
