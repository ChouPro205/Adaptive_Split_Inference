# Attack protocol v3, bản sửa 4 (M1): gửi SV1 xác nhận trước khi khóa

Ngày 26/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa, chưa có code, chưa chạy gì.** DS2 chưa mở.

Bản này sửa r3 (`mitdb_m1_attack_protocol_v3_r3.json`, SHA `0436b41b…`, commit `d5c9158`) theo review của SV1 ngày 25/11. Theo review đó, bản khóa là r4, SV1 xác nhận diff r3 → r4 trong ngày rồi mới khóa. r1, r2, r3 và v2 đã khóa đều giữ nguyên.

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Attack protocol v3 r4 (ứng viên) | `ml/configs/mitdb_m1_attack_protocol_v3_r4.json` | xem `ml/provenance/m1-attack-v3-r4-draft-20261126/SHA256SUMS.txt` |
| r3 (đã review, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v3_r3.json` | `0436b41b4211ab653d04f82a25f80d5331115b2ef566b357939116008b786e82` |
| Review r3 của SV1 (25/11) | `ml/provenance/m1-sv1-evidence-20261125/tra_loi_Ky_Anh_review_r3_va_docs_20261125.txt` | `14a1f67118aff6ac3fc62643bfdf1817a3709d1855fbc0f7bf23d65bb71c4ed8` |
| Tin bổ sung của SV1 (25/11) | `ml/provenance/m1-sv1-evidence-20261125/tin_bo_sung_Ky_Anh_uu_tien_va_S0c_20261125.txt` | `f169a93a9c31968539245e113f697b133d64f1999db00d2069b43ba39f54b60e` |
| Tin SV1 19/11 lúc 22:15 (file gốc) | `ml/provenance/m1-sv1-evidence-20261125/tra_loi_Ky_Anh_gop_y_huong_xu_ly_v2_20261119.txt` | `5a98b20ebf482932c0b1bdcdb01b7f6bb070b9c0aed910ead9b5546ab87832dc` |
| S0c v1: mã tham chiếu | `ml/provenance/s0c-v1/s0c_v1_ref.py` | `323ffabaa255f80de9730279e7d0abee7571125bb61d1c36e871dc113bcaf0a0` |
| S0c v1: golden (npz, json) | `ml/provenance/s0c-v1/s0c_v1_golden20.npz`, `.json` | `2923fe85…9d87`, `23eb93f4…72f9` |
| Kiểm nhận S0c v1 của SV3 | `ml/provenance/s0c-v1/sv3_check_20261126/` | xem `check_result.json` |
| Hướng dẫn tuần 11–24 | bản cục bộ, không đưa vào repo | `d7ecc45b0c9372392cbf587cc2135bb9384ce938aeef4d4045962b558dfbeb8a` |
| Diff r3 → r4 và v2 → r4 | `ml/provenance/m1-attack-v3-r4-draft-20261126/diffs/` | xem `SHA256SUMS.txt` |

## 1. Đối chiếu từng điểm review với r4

| Review 25/11 | Trong r4 |
|---|---|
| 0. Lịch dịch một tuần | Kết quả a, b, d ngày 06/12 (H8); nhánh R ngày 11/12 (H9); quyết định 13/12; trần 1,5 tuần công tính từ lúc khóa |
| 1(1) Cách gộp "trung bình" | Mục `k_beat_vote.aggregators.mean`: trung bình k tensor đã giải lượng tử, không lượng tử lại ở nguồn; đường ghép tính u_s′ từ tensor trung bình. Kẻ tấn công: mọi biến thể của cấu hình, cộng kẻ tấn công sạch ρ0 cùng nguồn (s2 ρ0 của lượt thử cho R2; S0c ρ0 của phần a cho C0c). Π_k10 = 1 − max trên {đa số, mềm, trung bình} × {liên tiếp, rải rác} × kẻ tấn công. Phần d báo thêm đường cách gộp trung bình. Limitation sửa lại: còn lại là kẻ tấn công học trên tập nhiều nhịp |
| 1(2) S0c v1 | `source_bindings.s0c_definition` gắn SHA mã tham chiếu và hai file golden; bỏ nhánh NOT_RUN. Runner phải tái tạo S0c v1 từng bit trên 20 nhịp golden và trên mọi nhịp DS1 của lượt thử trước khi có số S0c |
| 1(3) Chỉ C0c | Bỏ C0 đủ 360 mẫu; C0c cộng nhiễu sau bước 2 (reduce46), rồi bước 3–4; số byte Rice = `len(rice_encode(q))` |
| 1(4) Nhiễu sinh mới | `noise_generator.fresh_training_noise`: mỗi epoch một lần rút mới cho cả tập train của kẻ tấn công, seed theo (cấu hình, α, epoch). Áp dụng cho B-adaptive, A1 thích nghi, B-composite-adaptive (đường ghép tính lại mỗi epoch). Dự phòng ≥ 20 lần rút có sẵn, chỉ khi phép đo thời gian trên dữ liệu giả cho thấy vượt trần; ghi trước lần fit đầu |
| 1(5) DS2 | Mục `official_DS2_privacy_round` (tuần 14, N = 21): phần a, b, d gồm tấn công ghép, s9/s10, S0c, cộng cấu hình R nếu được chọn trên DS1. Luật `DS2_confirmation`: cấu hình chỉ vào tập hành động khi DS2 cũng đạt Π ≥ 0,5, Π_k10 ≥ 0,5, macro-F1 ≥ 0,5398 (điểm ước lượng), báo kèm CI95 |
| 1(6) File gốc tin 20/11 | Ghi chú đổi thành "bản đúng byte của file gốc `…_20261119.txt`, gửi 19/11 lúc 22:15"; thêm bản sao mang tên gốc |
| 2. Bảng quyết định, ràng buộc nguồn | Ngày quyết 13/12; thêm bước xác nhận DS2; hai ràng buộc tin nhắn trỏ tới `docs/sv3_archive/messages/` (đã khôi phục nguyên byte) |
| 3a–c. Dọn docs | Khôi phục 13 tin nhắn; ghi cách chạy lại script kiểm ở `d5c9158`; link `edge/README.md` báo Trung; merge `main` trước khi mở PR |

## 2. Bốn câu cần SV1 xác nhận

1. **Lượt DS2 chất lượng ngày 10/12 nên có thêm S0c** (FP32 trong script của SV3; đường DPU do Trung chạy). S0c là hành động tối thiểu của LUT và mỗi cấu hình chỉ được đánh giá trên DS2 một lần, nên thiếu S0c ở lượt này thì không còn chỗ lấy macro-F1 của S0 chuẩn trên DS2.
2. **Cách gộp trung bình trên đường ghép:** ngoài các kẻ tấn công SV1 liệt kê, r4 áp thêm kẻ tấn công sạch ρ0 ở điểm cắt sâu s′ (chỉ suy luận, không train). Giữ không?
3. **Nhiễu sinh mới theo epoch** cho cả tập train theo thứ tự hàng cố định, không theo batch, để nhiễu của một nhịp không phụ thuộc thứ tự xáo. Được không?
4. **Đường ghép khi train chạy GPU, khi đánh giá chạy CPU** như phần b. Khác biệt chỉ là sai số làm tròn. Được không?

## 3. Đã làm, đã kiểm, chưa làm

- **Đã làm:** viết r4 (JSON hợp lệ, LF); diff r3 → r4 và v2 → r4; lưu bằng chứng SV1 ngày 25/11 và gói S0c v1; khôi phục tin nhắn.
- **Đã kiểm:**
  - gói S0c v1 đúng SHA;
  - x golden trùng gói A từng bit (20/20);
  - mã tham chiếu tái tạo đủ golden (20/20), chạy được ở cả chế độ thường và `-O`;
  - 13 tin nhắn khôi phục trùng SHA của bản ở commit `d5c9158`.
- **Chưa làm:** code, test, smoke cho r4; khóa (file khóa do người dùng cung cấp sau khi SV1 xác nhận).
- Không chạy tấn công, không fit, không mở DS2.
