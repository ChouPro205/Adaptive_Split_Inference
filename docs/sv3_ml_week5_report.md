# Báo cáo tiến độ SV3 Bùi Kỳ Anh tuần 5

**Người thực hiện:** SV3/Bùi Kỳ Anh, phụ trách mô hình, lượng tử hóa tham chiếu và P1.
**Ngày lập báo cáo tổng hợp:** 22/10/2026, múi giờ Asia/Saigon.
**Chốt bằng chứng kỹ thuật:** HEAD PR #25 `6e1ae146f83c59f6804d11c5400518a11de03b6e`,
nghiệm thu và merge ngày 15/10/2026; merge commit `a0fa17c92d1155fdeb25bdc2bf29731f79640e63`.
Phạm vi tuần 5 gồm implementation đầu tháng 10, các lần review/sửa tới 15/10 và
quyết định allocation cuối. Đây là tổng hợp hồ sơ đã có, không phải phiên huấn luyện
hoặc đo phần cứng mới ngày 22/10.

SV3 đã hoàn thành reference INT8/FP16, P1 Python, kiểm khả nghịch, accuracy đủ
8.544 mẫu tại 11 split và hồ sơ bàn giao có xác thực. Allocation testbed đã được
Châu phê duyệt; **FINAL_ACCEPTANCE=PASS, COMPATIBILITY_SV1=PASS** theo PR #25.
Kết quả đó không chứng nhận KV260/DPU, radio, provisioning hoặc nonce runtime.

Quy ước: **YÊU CẦU DỰ ÁN** là tiêu chí nguồn; **QUYẾT ĐỊNH TRIỂN KHAI** là
phương pháp/config đã chốt; **KẾT QUẢ QUAN SÁT** có log/manifest/capture đối chiếu.
`PASS` chỉ áp dụng cho phạm vi đã kiểm; `PENDING` là còn chờ; `BLOCKED` có đầu vào
cản trở cụ thể; `NOT VERIFIED` là chưa đủ bằng chứng. Expected rejection không phải
một dữ liệu sai được chấp nhận.

## 1. Mục tiêu và nguồn yêu cầu

**YÊU CẦU DỰ ÁN.** Hướng dẫn chi tiết A.3, tuần 5 yêu cầu hiện thực P1 Python,
PRNG có khóa và khả nghịch bit-exact trên 10.000 tensor; tuần 6 dành cho C và
50 vector bàn giao. Tuần 5 của SV1 cần kiểm INT8 so với FP32; SV3 cung cấp dữ liệu,
tham chiếu và accuracy. Phạm vi thực thi được cụ thể hóa bằng
[checklist tuần 5 v1.1](sv3_week5_scope_checklist_2026-10-09_v1.1.md),
[decision note](../contracts/sv3_week5_decisions_v1.md) và
[allocation cuối](../contracts/sv3_week5_allocation_v2.md).

| Tài liệu nguồn đã đọc read-only | Phần liên quan | SHA-256 byte thô |
|---|---|---|
| `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx` | A.3 tuần 5–6; A.1 tuần 5 | `75fcd76999af521a568b039c6983414217c59991d37b5591b85d211db927880d` |
| `Huong1_Bao_cao_trien_khai_3SV.docx` | Giai đoạn 1, hàng tuần 5–6 | `60f83fa7c0779d11c888a8a104c5fa55be0c8c8b171f9d72e29cbba9efcc9a90` |

Hash định danh bản tài liệu tham khảo lịch sử; không yêu cầu người nhận tạo lại
DOCX để chạy các gate. Nội dung có thẩm quyền hiện hành nằm ở schema/reference,
contract và hồ sơ phê duyệt có version của repository.

## 2. Đầu vào kế thừa và phạm vi SV3

**QUYẾT ĐỊNH TRIỂN KHAI.** Giữ baseline `mitdb_week2_cnn_v1`, kiến trúc 109.653
tham số, mapping s0..s10, dữ liệu patient-wise và normalization train-only.

| Đầu vào khóa | Giá trị/phạm vi |
|---|---|
| Checkpoint | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` |
| Manifest model FP32 | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` |
| Accuracy chính thức | 8.544 mẫu test frozen, mỗi split s0..s10 |
| Golden kiểm byte/số học | 20 mẫu validation x 11 split = 220 cặp; không dùng thay test accuracy |
| Reference lượng tử | Activation INT8 đối xứng per-sample/per-channel; zero-point=0; scale lưu FP16 |
| Phần tail trong gate host | FP32; chưa tính lượng tử trọng số/input DPU |

SV3 thực hiện Python/reference/verifier và hồ sơ; SV1 cung cấp capture/DFU/MCU;
SV2 chịu trách nhiệm compiler, xmodel và runtime KV260. Không gán thao tác thiết bị
của thành viên khác thành công việc đo mới của SV3.

## 3. Công việc đã làm và các file chính

| Nhóm file từ repo root | Công việc và mục đích |
|---|---|
| `ml/src/quantization.py`, `ml/src/p1.py` | Reference lượng tử và P1 delegate I2/1; giữ thuật toán đã chốt |
| `ml/src/week5_interfaces.py` | Resolve profile/ID tường minh, descriptor, shape, scale và kiểm metadata |
| `ml/scripts/verify_week5_real.py`, `verify_week5_registry_v3.py` | Kiểm q/scale/wire/adapter/approved registry với tensor thật |
| `ml/scripts/evaluate_week5_v2.py`, `week5_common_v2.py` | Accuracy đủ 8.544 x 11 và gate strict; không sửa source lịch sử bị receipt ràng buộc |
| `ml/scripts/test_week5_p1_v2.py` | P1 10.000 ca, provenance v2, số lỗi và public-test-only profiles |
| `ml/scripts/setup_week5_delivery_v2.py`, `run_week5_delivery_v2.py` | Hydrate đúng bytes và chạy portable suite có scope |
| `ml/scripts/verify_week5_delivery_v3.py`, `test_week5_allocation_v3.py` | Kết hợp scientific evidence, approval/registry và compatibility SV1 |
| `ml/manifests/week5_delivery_scope_v2.json` | 569 dependency bắt buộc; tách khỏi audit toàn workspace tác giả |
| `contracts/sv3_week5_allocation_v2.md`, approved registry/approval JSON | Allocation cuối có thẩm quyền, revision và hash độc lập |

Luồng kiểm: head FP32 → INT8/FP16 → protect → unprotect byte-exact → dequantize
theo kênh gốc → adapter NC nếu cần → tail FP32. Scale giữ thứ tự kênh nguồn.

## 4. P1, lượng tử hóa và khả nghịch

**QUYẾT ĐỊNH TRIỂN KHAI.** P1 theo I2/1 dùng IETF ChaCha20, key32/nonce12,
counter 0, permutation và affine modulo 256 theo kênh nguồn. Hệ số nhân lẻ có
nghịch đảo modulo 256. Kiểm vector/RFC và byte mapping ngoài round-trip để tránh
hai lỗi protect/unprotect tự triệt tiêu nhau.

**KẾT QUẢ QUAN SÁT:** 10.000 synthetic tensors và 220 tensor thật đều khôi phục
đúng byte; q, FP16 bits, wire FP32-LE scales, shape và tail được đối chiếu.
Miền tensor lượng tử là [-127,127]; byte 0x80 vẫn hợp lệ trong transformed bytes.
P1 không có MAC/authentication và không tự chứng minh an toàn trước dựng lại.

Chỉ payload activation INT8 giảm 4 lần so với FP32; không suy tỷ lệ đó cho tổng
packet có scale, metadata, nonce, header và CRC.

## 5. Accuracy trên tập test chính thức

Gate đã chốt: `Accuracy_FP32 - Accuracy_INT8 < 0,5 điểm phần trăm` cho từng
split, tương đương `200*(correct_FP32-correct_INT8)<8544`; đúng 0,5 FAIL.

| Đại lượng | Kết quả theo hồ sơ final |
|---|---|
| FP32, mọi split | 8.393/8.544 = 98,232678% |
| Split INT8 kém nhất | s6: 8.388/8.544 = 98,174157% |
| Mức giảm lớn nhất | 0,05852059925093633 điểm phần trăm; nhỏ hơn 0,5 |
| Coverage | 11 split x 8.544 = 93.984 hàng predictions |
| Kết luận | Từng split PASS strict gate; không dùng trung bình qua split |

Nguồn: [báo cáo kỹ thuật tuần 5](../ml/docs/week5_technical_20261009.md),
[compatibility ngày 15/10](../ml/docs/week5_pr25_sv1_20261015.md) và
[PR #25](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/25).
Đây là reference INT8+FP16 với tail FP32, không phải accuracy KV260/DPU hay
full-test chạy trên MCU. Accuracy tổng cao vẫn đi cùng hạn chế các lớp hiếm;
xem [đánh giá theo lớp](../ml/results/week5-per-class-20261015/README.md).

## 6. Review, sửa lỗi và allocation cuối

| Mốc | Công việc/kết luận đúng thời điểm |
|---|---|
| 05–09/10 | P1/quantization/reference/accuracy và bàn giao; Python/ML đạt nhưng allocation chưa được cấp |
| 11–12/10 | Sửa bảo toàn source SV1, setup/header policy và verifier portable; không bỏ kiểm dependency bắt buộc |
| 15/10, trước allocation | Compatibility SV1 PASS; tài liệu trung gian vẫn ghi BLOCKED_ALLOCATION đúng lịch sử |
| 15/10, HEAD `6e1ae14` | Châu phê duyệt allocation, final v3 thường/-O PASS; PR #25 merge |
| Sau PR #27, cùng ngày | Bộ receipt source mới của SV1 được lưu riêng trong `week5-current-20261015`, không gán receipt PR25 cho source khác |

Revision `mitdb-week5-i2-registry-v1-r1`: profile 1296651265; s0..s10 → wire
256..266; key label 65537; sender 131073. s10 là device-only/identity empty-tail,
không có executable `tail_s10`. Registry raw SHA-256:
`79392b6db73cde6d83eadb1f265f14102888ebdbf8ea1b72b6c127c5566eed24`.

Approval do Codex ghi theo ủy quyền của Châu; không phải chữ ký mật mã hoặc
xác nhận Trung/Kỳ Anh tự kiểm toàn bộ file/hash cuối. Runtime provisioning,
nonce persistence/reboot và transport chưa được allocation này nghiệm thu.
Registry/verifier null-ID lịch sử vẫn BLOCKED/2; không sửa chúng để thay lịch sử.

## 7. Deliverables, release và tái lập

| Hồ sơ bàn giao | Nội dung/kết quả |
|---|---|
| [Delivery portable v2](../ml/docs/week5_delivery_v2.md) | Hydrate bốn ZIP gốc, 569 required assets; 29/29 portable children exit 0 |
| [Release tuần 5](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week5-v1-20261005) | Dataset frozen và quantization reference, SHA/size và download verification |
| [Allocation/final v3](../contracts/sv3_week5_allocation_v2.md) | Authority/registry/descriptor, approved real220, accuracy và bốn gate SV1 |
| [Receipt source mới 15/10](../ml/provenance/week5-current-20261015/README.md) | Snapshot source riêng, final v3 thường/-O PASS và historical PR25 checks |

Whole acceptance SV1 theo hồ sơ: 220 primary +16 mixed, oracle236, s0/P2
20/20 bitwise; max FP32 error 1,430511474609375e-05 <1e-3; unexplained mismatch=0.
Ba scale FP16 s10 tại midpoint được giữ phân tích gốc, không sửa golden/ngưỡng.

Môi trường các phiên được pin trong receipt: Python3.11.9, torch2.14.0+cu130,
NumPy2.4.6, CPU deterministic một thread, MKLDNN disabled. Phiên bản GCC theo
từng receipt. Lệnh setup/runner/final CLI đầy đủ ở hai hướng dẫn trên; output
phải mới và checkout phải đúng snapshot được receipt chứng nhận.

## 8. Phối hợp và giới hạn bằng chứng

SV1 có nghiệm thu MCU INT8 tuần 5; SV3 kiểm compatibility bằng capture/DFU và
C accuracy đã được xác thực, không gọi đó là lần nạp/đo mới. Original evidence,
expected hashes, manifests, checkpoint và ZIP/goldens được giữ nguyên.
Phân loại dependency portable không đồng nghĩa đã phục hồi mọi file phụ của
workspace tác giả; các extras không có được ghi rõ trong audit lịch sử.

Receipt tuần 5 chỉ chứng nhận source snapshot đã pin. Source tuần 6/7 hoặc
main mới cần kiểm riêng; không dùng merge hoặc upload để tự suy nghiệm thu.

## 9. Trạng thái nghiệm thu

| Hạng mục | Trạng thái | Giới hạn |
|---|---|---|
| INT8/FP16/reference và accuracy 8.544 x 11 | PASS | Tail FP32 trên host |
| P1 Python 10.000 synthetic +220 tensor thật | PASS | Bit-exact; không kết luận privacy |
| Portable setup/delivery và compatibility SV1 | PASS | Đúng source/assets/receipts đã kiểm |
| Allocation testbed/final v3 | PASS ngày 15/10 | Theo authority versioned; không phải runtime authorization |
| MCU INT8 tuần 5 | PASS theo bằng chứng SV1 | Không phải full-test MCU 8.544 mẫu mới |
| DPU/KV260 và Device–Edge thật | PENDING | Cần backend/runtime/output SV2 |
| Học hiểu của Kỳ Anh/GVHD sign-off | NOT VERIFIED trong phiên tổng hợp | Cần demo/trao đổi thực tế |

## 10. Việc chuyển sang tuần 6–7

Tuần 6 kiểm bản C trên 50 vector thật và bàn giao request/output; SV1 tích hợp
MCU/radio/nonce, SV2 triển khai receiver/tail. Tuần 7 mở dCor/NoPeek offline.
Xem [báo cáo tuần 6](sv3_ml_week6_report.md) và [tuần 7](sv3_ml_week7_report.md).

Phiên lập báo cáo ngày 22/10 chỉ tổng hợp Git, quyết định, code và bằng chứng
đã lưu; không chạy mới training, toàn suite tuần 5, MCU hoặc KV260.
