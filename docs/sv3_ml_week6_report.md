# Báo cáo tiến độ SV3 Bùi Kỳ Anh tuần 6

**Người thực hiện:** SV3/Bùi Kỳ Anh, phụ trách P1, vector và ngữ nghĩa output ML.
**Ngày lập báo cáo tổng hợp:** 22/10/2026, múi giờ Asia/Saigon.
**Chốt bằng chứng SV3:** 16/10/2026; implementation `766a3cfa7e7828ecd00b9eb23cc3e5da4015ced5`,
delivery `f3675848a0c8a4d90f912cf173d97dda58a59aef`, PR #30 merge cùng ngày.
**Cập nhật tiếp nhận Device:** bằng chứng SV1 ngày 19/10 tại PR #32, ghi tách
khỏi kết quả host ngày 16/10. Không ghi đây là thao tác phần cứng do SV3 thực hiện.

SV3 hoàn thành gói 50 vector P1 thật, kiểm Python/C và luồng output I1 v2 trên
host; **A+B HOST PASS**. SV1 sau đó dùng đúng gói và đạt protect/unprotect 50/50
trên MCU, BLE loopback 1.000/1.000 với laptop. KV260/DPU vẫn cần bằng chứng riêng.

Quy ước: **YÊU CẦU DỰ ÁN**, **QUYẾT ĐỊNH TRIỂN KHAI**, **KẾT QUẢ QUAN SÁT**
được phân biệt; `PASS` chỉ cho phạm vi có evidence, `PENDING` là còn chờ,
`BLOCKED` có dependency cụ thể, `NOT VERIFIED` chưa có bằng chứng. Negative run
exit1 đúng kỳ vọng không được gọi là một command dương PASS exit0.

## 1. Mục tiêu và nguồn yêu cầu

**YÊU CẦU DỰ ÁN.** Hướng dẫn chi tiết A.3, tuần 6 giao P1 C tối ưu Cortex-M,
bàn giao SV1/SV2 kèm 50 vector; C và Python phải giống hệt trên 50 vector.
Thực thi reuse C reference I2/1 hiện hành, kiểm trên bộ vector thật mới và giao
đủ nguồn/vector để SV1 tích hợp lên MCU; không tuyên bố host C thay đo Cortex-M.

| Tài liệu nguồn đã đọc read-only | Phần liên quan | SHA-256 byte thô |
|---|---|---|
| `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx` | A.3 tuần 6; A.1 tuần 6 | `75fcd76999af521a568b039c6983414217c59991d37b5591b85d211db927880d` |
| `Huong1_Bao_cao_trien_khai_3SV.docx` | Giai đoạn 1, hàng tuần 6 | `60f83fa7c0779d11c888a8a104c5fa55be0c8c8b171f9d72e29cbba9efcc9a90` |

Yêu cầu byte/shape/scale/output được cụ thể hóa trong [I2/1](../contracts/i2_protection_v1.md),
[I1 v2](../contracts/i1_device_edge_packet_v2.md) và
[BLE binding](../contracts/i1_ble_binding_v1.md). Bảng xác nhận kỹ thuật của
thành viên và runtime registry là các đầu việc riêng, không suy từ PR merge.

## 2. Đầu vào kế thừa và phạm vi

**QUYẾT ĐỊNH TRIỂN KHAI.** Giữ model/version `mitdb_week2_cnn_v1`, checkpoint
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` và
mapping s0..s10 đã chốt ở tuần 5. Nền triển khai là `af31ea784700cea1633b5c6290536a5208d052da`
(PR #29). Không train lại, thay checkpoint hoặc generator/golden lịch sử.

| Đầu vào | Giá trị/phạm vi |
|---|---|
| Model manifest | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` |
| Quantization source manifest | `8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd` |
| Nguồn vector | 220 cặp validation thật tuần 5, chọn 50 cặp có định danh/provenance |
| Registry | Profile1296651265; wire256..266; key label65537; sender131073 |
| Key trong vector | Public `00..1f`, PUBLIC_TEST_ONLY; nonce sequence1..50 cố định |

Gói host không cấp key bench/vận hành, không provision/flash MCU và không thực
thi KV260 thay SV1/SV2. Các khóa an toàn/runtime trên Device thuộc firmware SV1.

## 3. Công việc đã làm và các file chính

| File/nhóm từ repo root | Công việc và mục đích |
|---|---|
| `ml/scripts/week6_p1.py`, `generate_week6_p1.py` | Xác thực nguồn rồi sinh 50 vector, descriptor/nonce/request/hash/output |
| `ml/scripts/verify_week6_p1.py` | Kiểm gói, Python round-trip và so C reference với chính bộ 50 mới |
| `ml/scripts/verify_week6_output.py` | Parser → unprotect → dequantize → adapter → frozen tail/identity → response |
| `ml/scripts/test_week6_p1.py` | 16 package regressions, thiếu/sửa file bị từ chối |
| `ml/scripts/package_week6_p1.py` | Đóng ZIP có thể tái sinh exact, từ chối ghi đè |
| `ml/provenance/week6-p1-20261016/` | Command/source/log/result hashes, reproduction, preservation và publication |
| `ml/docs/week6_p1_package_readme.md` | Hướng dẫn đọc từng vector; tài liệu kỹ thuật bổ trợ, không thay báo cáo ở root docs |

Phân bố: s0..s5 mỗi split 5 vector; s6..s10 mỗi split 4 vector, tổng 50.
Giữ nguyên q và FP16 scale của nguồn; không tính lại scale hay thay tensor synthetic.

## 4. Kết quả P1 Python/C trên host

**KẾT QUẢ QUAN SÁT:**

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Vector thật/coverage | 50 vector, đủ 11 split | `final/p1_50.json` |
| Python round-trip | 50/50 byte-exact | Như trên |
| C protect so Python | 50/50 byte-exact | Như trên, compiler receipt |
| C unprotect so q gốc | 50/50 byte-exact | Như trên |
| Transformed có 0x80 | 39/50 vector, xuất hiện tự nhiên | Như trên |
| Descriptor/nonce | 28 B/12 B; sequence1..50 không trùng | Gói/manifest và verifier |
| Package regressions | 16/16 thường và 16/16 `-O` | `final/command-index.json` và logs |
| Thiếu/sửa file | CLI exit1 đúng kỳ vọng | Hai negative runs riêng |

Xem [kết quả 50 vector](../ml/provenance/week6-p1-20261016/final/p1_50.json).
Đây là C host GCC, không phải bằng chứng thời gian/năng lượng trên Cortex-M.

## 5. Ngữ nghĩa output và sai số

Luồng trên host: request I1 v2 → kiểm metadata/CRC → unprotect → kiểm q →
dequantize theo scale kênh gốc → tail đúng split → response 5 raw logits N,S,V,F,Q.
Không thêm Softmax/LogSoftmax/Sigmoid. Với s9, chuyển wire `[1,32,1]` về NC
`[1,32]`; với s10 không gọi tail callback, trả identity logits FP32.

| Kiểm tra | Kết quả |
|---|---|
| Tail s0..s9 | 46 vector qua frozen reference tails |
| Identity s10 | 4 vector, không tạo/nạp tail_s10 |
| Tie policy | 3 ca hòa riêng, chọn index nhỏ nhất; không gộp vào 50 vector thật |
| Output cùng q trước/sau P1 | Byte-identical; max abs quan sát so frozen quantized logits=0 |
| Sai số quantized so FP32 lớn nhất trong bộ này | 0,059641361236572266; chỉ chẩn đoán, không phải gate DPU |

Nguồn: [output_50.json](../ml/provenance/week6-p1-20261016/final/output_50.json).
50 vector/220 validation pairs không phải tập test accuracy. Sai số requantize
đầu vào và trọng số DPU cần đánh giá riêng trên backend thật và test frozen.

## 6. Hồi quy, bảo toàn và review

| Nhóm | Kết quả đúng scope |
|---|---|
| I2/I1 v2 | 5/5 và 23/23 tests, thường/-O; vector golden check đạt |
| Quantization/interfaces/allocation v3/registry v2 lịch sử | 6/7/7/5 tests, từng suite thường/-O |
| Registry hiện hành với tensor thật | 220/220 |
| P1 round-trip mới | 10.000 byte-exact |
| Tái sinh gói/ZIP | 406/406 file hashes khớp, ZIP bytes khớp |
| Bảo toàn | 210 source bindings, 569 dependencies và bốn ZIP gốc không đổi |

Có **27 command final exit0**; hai CLI negative runs riêng exit1 đúng kỳ vọng.
Lỗi typo SHA nền ở lượt sinh đầu được giữ log; sửa pin theo Git rồi chạy lại,
không sửa anchor hay receipt lịch sử để hợp code. Implementation và commit thêm
evidence tách riêng nhằm tránh provenance tự tham chiếu.

Môi trường: Python3.11.9, torch2.14.0+cu130, NumPy2.4.6, ONNX1.23.1,
ORT1.30.0; CPU eval N=1 deterministic một thread, MKLDNN disabled.
GCC MSYS2 15.2.0, C99 `-O2 -Wall -Wextra -Werror -pedantic` theo receipt.

## 7. Release và cách nghiệm thu

[Release tuần 6](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week6-p1-v1-20261016)
đã upload và tải lại hai ZIP cùng sidecar SHA-256; không commit ZIP/model/dataset.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `mitdb-week6-p1-50-20261016-v1.zip` | 412045 | `2afbab35b601ac14128c32018d6dc1d39afd1991759a7a0fd9ad2051d923359a` |
| `sv3-week6-p1-handoff-20261016-v1.zip` | 1714357 | `40294b39c3863d9b5c72a807e971662bebfbcf38bb6246c20d4b6c1ec84a84cd` |

Manifest vector: `d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36`.
Người nhận xác thực version/hash trước dùng; hydrate đúng dependencies nếu thiếu,
rồi chạy verifier P1/output/package với output mới. Lệnh và đường dẫn đầy đủ ở
[hướng dẫn bàn giao](../ml/docs/week6_p1_delivery.md); không tạo key bench từ public key vector.

## 8. Tiếp nhận của SV1/SV2 và cập nhật sau bàn giao

Ngày 16/10, SV3 chỉ kết luận A+B host PASS. Ngày 19/10,
[SV1 tuần 6](sv1_device_week6_report.md)/[PR #32](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/32)
cung cấp bằng chứng MCU dùng đúng manifest trên: protect/unprotect50/50,
39 vector chứa0x80, 1.000/1.000 BLE loopback và 19/19 negative scenarios.
Nonce stress có reset/mất điện/DFU. Đây là kết quả SV1, peer laptop Windows,
chưa phải inference KV260. Review SV3 sau đó xác thực 29 file manifest SV1.

Chưa có receipt SV2 chạy gói P1 tuần 6 hoặc output DPU trong các hồ sơ đã đọc;
không suy rằng SV2 chưa nhận qua kênh ngoài GitHub. I1 v2 §14 còn hàng xác nhận
ML của Kỳ Anh và parser/buffer của Trung; runtime nonce registry vẫn cần revision
đúng thẩm quyền dù bằng chứng Device đã có.

## 9. Trạng thái nghiệm thu

| Hạng mục | Trạng thái | Giới hạn |
|---|---|---|
| Gói 50 vector P1 và C/Python | PASS | Host A, không thay timing Cortex-M |
| Tensor/quantization/response | PASS kỹ thuật host | Host B; xác nhận chính thức của người phụ trách còn riêng |
| Release/reproduction/preservation | PASS | Đúng commit/source/artifact pins |
| P1 trên MCU/BLE/nonce kiểm thử | PASS theo evidence SV1 ngày 19/10 | Laptop peer; không phải DPU hoặc end-to-end classifier |
| Receipt SV2 và KV260 accuracy/runtime | PENDING | Cần output và provenance backend thật |
| Revision nonce runtime registry | PENDING | Châu/Trung xử lý theo change control |
| Privacy attack/GVHD sign-off/học hiểu | NOT VERIFIED trong phạm vi này | Không suy từ host test hoặc merge |

## 10. Việc chuyển sang tuần 7

SV3 mở hàm distance correlation, bộ kiểm chứng gradient và chạy thử NoPeek
offline, giữ nguyên baseline tích hợp; xem [báo cáo tuần 7](sv3_ml_week7_report.md).
Đánh giá sai số DPU phối hợp SV2 vẫn là đầu việc riêng, không chặn toán dCor.

Phiên tổng hợp ngày 22/10 không chạy lại 27 command, không flash/đo MCU hoặc
KV260; số liệu giữ nguyên và dẫn tới đúng hồ sơ lịch sử đã kiểm.
