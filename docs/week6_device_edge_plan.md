# Kế hoạch tuần 6 — Device–Edge qua BLE

Ngày lập: 15/10/2026. Người duyệt thiết kế: Lê Hải Châu (trưởng nhóm, SV1). Tài
liệu này theo dõi **triển khai và nghiệm thu**; thiết kế đã chốt nằm ở:

- [I1 v2](../contracts/i1_device_edge_packet_v2.md) — packet, thứ tự lỗi, response.
- [I1 BLE binding v1](../contracts/i1_ble_binding_v1.md) — GATT, fragment, timeout/retry, cache.
- [I2/1 nonce và provisioning v1](../contracts/i2_nonce_provisioning_v1.md) — NVS, dải sequence, key.
- [Reference/test host](../contracts/i1v2_ref/test_i1v2.py) và [vector](../contracts/i1v2_ref/vectors.json).

Trạng thái hiện tại: thiết kế APPROVED. Ngày 19/10/2026 cả 8 tiêu chí §1 **PASS trên
nRF52840 với laptop Windows làm BLE peer** ([báo cáo SV1 tuần 6](sv1_device_week6_report.md),
[bằng chứng](../results/week6/README.md)). Các hạng mục KV260 của SV2 (§2.2) và đánh giá DPU
của SV3 chưa chạy; chưa thay laptop bằng KV260.

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

## 4. Quyết định triển khai D1–D6 (trưởng nhóm chốt 18/10/2026)

Các quyết định dưới đây cụ thể hóa cách chạy tiêu chí 4, 6, 7 và nguồn dữ liệu; chúng
**không** đổi contract (I1 v2, binding v1, nonce v1) và không đổi tiêu chí ở §1.

| # | Quyết định | Cách thực hiện trong firmware/công cụ |
|---|---|---|
| D1 | Reset cho tiêu chí 7 = **≥ 100 reset mềm tự động + 10–20 lần ngắt nguồn thật**, báo cáo tách riêng hai loại. Nút RESET của dongle vào bootloader nên không dùng làm reset ứng dụng. | `NTEST STRESS <ms> 1`: vòng lặp đặt trước một khối mới rồi cấp một sequence ở mỗi vòng (mỗi sequence đều đi sau một lần ghi `NONCE_STATE`), timer gọi `sys_reboot` ở thời điểm ngẫu nhiên. P0.15 (`MARKER_PROTECTION`) lên cao trong lúc `nvs_write`; biến `__noinit` cho biết reset mềm có rơi vào lúc ghi (`boot_in_write`, chỉ là thống kê). Mặc định 110 chu kỳ (`week6_lab.py nonce-reboot`) và 12 lần rút USB (`nonce-unplug`). Ước tính hao mòn: khoảng 60–70 nghìn lần ghi 48 B, dưới 10 % tuổi thọ 10 000 chu kỳ xóa của 4 trang. |
| D2 | Test "record hỏng/xóa → FAULT" và "lỗi ghi → dừng" **giả lập ở lớp lưu trữ**, không hủy state thật, nên không cần cặp `key_id`/`sender_id` dự phòng. | `NTEST FAILWRITE` (không gọi `nvs_write`, trả `-EIO`), `NTEST READBACK` (ghi thật, đọc lại bị lệch), `NTEST BOOT <hook>` với hook `STATE_CRC`, `STATE_MISSING`, `PROVISION_CORRUPT`, `KEY_MISMATCH` (chạy lại logic boot với hook đọc, đếm số lần ghi phải bằng 0), rồi `REBOOT` thật để kiểm state còn nguyên. |
| D3 | 1000 packet chính thức ở **MTU thương lượng 247**; ở **MTU 23** chạy đủ 4 cỡ bắt buộc, **mỗi cỡ 10 packet**, có counter đầy đủ. | `RUN 1000 MIX` (bản `default`) và `RUN 40 SIZES=113,153,6124,6380` (bản `mtu23`). Nếu MTU 23 quá chậm trên Windows: `CONNPARAM 6 12` xin connection interval ngắn hơn; giá trị quan sát được ghi trong log. |
| D4 | Frame 6380 B là **profile test**, chỉ dùng ở echo, không phải request của registry. | Metadata giống vector `i2_ceiling_c64_payload5760` (model 1, split 1, `[1,64,90]`), payload là q thật 5760 B của vector s3 đầu tiên, scale thật C=64 của vector s7 đầu tiên; transform bằng key bench + nonce từ allocator. |
| D5 | Nguồn tensor = **50 vector P1 thật của SV3** nhúng vào firmware; không nhúng head tuần 4–5 vào firmware tuần 6. | `build_week6.ps1` xác thực manifest `d0914acb…1c36` (hash từng file, đúng inventory) rồi sinh bảng; DWT quantize đo bằng `week5/quantization.c` trên `z = q × scale` cùng shape (`SELFTEST QUANT`). |
| D6 | Key bench sinh ngoài repo bằng `secrets.token_bytes(32)`; chỉ log `key_id`, `sender_id`, `key_check`. | `D:\HUST\ASI_week6\secrets\bench_key_65537.bin` (ACL chỉ tài khoản hiện tại), `key_check = 4379e570eb84f891`, cặp `65537/131073`. Provisioning qua USB CDC ở `PROV MODE ON`; firmware không in lại key. |

Chốt thêm hai khóa an toàn:

- Firmware từ chối `RUN` có packet I2/1 cho tới khi có lệnh `I2 ARM` (chỉ thành công khi
  nonce `READY`); operator chỉ arm sau khi tiêu chí 7 đạt.
- `PROV KEY` từ chối mọi trường hợp có thể làm sequence bắt đầu lại: state đã có
  `reserved_through > 0` (`STATE_IN_USE`), state hỏng/lạ, hoặc còn key mà mất state
  (`STATE_UNREADABLE`). `PROV ERASE` chỉ được phép khi NVS không mount được.

## 5. Trạng thái chuẩn bị ngày 18/10/2026 và kết quả trên dongle ngày 19/10/2026

Bảng dưới là trạng thái chuẩn bị trên host ngày 18/10/2026 (số Flash/RAM ở dòng đầu là của build
trước `afa8887`; build dùng trong lab là `20261019-r1`, xem báo cáo). Dòng cuối cập nhật ngày 19/10/2026.

| Hạng mục | Trạng thái | Bằng chứng host |
|---|---|---|
| Firmware `device/week6/` đầy đủ (fragment/reassembly, sender thread + 4 credit, máy trạng thái timeout/retry, echo, response §8.3, P1, NVS nonce, provisioning, hook D2, sentinel DFU, DWT, counter §11) | Build PASS cả `default` và `mtu23` (NCS 3.4.0, không cảnh báo) | `default`: `zephyr.bin` 333 044 B, image kết thúc `0x524f4` < `0xDC000`, RAM tĩnh 102 284 B; `mtu23`: 331 312 B, `0x51e30`, 96 511 B (`check_week6_build.py`, 18 kiểm tĩnh) |
| Module C thuần của firmware so với reference | PASS 27/27 | `device/scripts/test_week6_host.py`: reassembly vi sai với Python reference (300 chuỗi lỗi ngẫu nhiên), timeout/retry/backoff/horizon, phân loại echo/response 15 vector, nonce: record khớp byte, 400 boot mất điện ngẫu nhiên không lặp sequence, lỗi ghi chốt FAULT, provisioning từ chối tái dùng; packet: golden, 2 vector biên, **50 vector SV3 khớp từng byte** (transformed, round-trip, request) |
| Kịch bản negative (tiêu chí 6) | PASS 19/19 trong mô phỏng | `test_week6_sim.py`: state machine C của firmware nối với peer thật của `week6_lab.py`, đồng hồ ảo; thêm 1000 packet MIX không lỗi và MTU 23 |
| Checker offline + test âm | PASS 10/10 | `test_week6_checkers.py`: capture đúng → PASS, mỗi capture bị sửa → FAIL |
| Key bench (D6) | Đã sinh, ngoài repo | chỉ `key_check` được ghi |
| Chạy trên dongle (tiêu chí 1–8) | **PASS 8/8** ngày 19/10/2026, peer laptop Windows | [báo cáo](sv1_device_week6_report.md), [results/week6](../results/week6/README.md); `runtime.nonce_persistence_reboot` chờ revision registry mới (Châu + Trung) |

## 6. Thứ tự thực hiện

1. SV1: firmware BLE + echo với request thường; tiêu chí 3–6 và 8 (phần truyền).
2. SV3 bàn giao gói 50 vector → SV1 port P1 C; tiêu chí 1–2.
3. SV1: NVS nonce + provisioning bench; tiêu chí 7; sau đó loopback có I2/1.
4. SV2: KV260 central + parser theo vector; thay laptop bằng KV260 ở chế độ echo,
   rồi chế độ inference khi tail sẵn sàng.
