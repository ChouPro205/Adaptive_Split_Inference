# Protocol NoPeek v1 (M1): bản ứng viên gửi SV1 review

Ngày 05/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: ứng viên, chưa khóa. Chưa chạy pilot, chưa chạy grid, chưa viết runner.**

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Protocol NoPeek v1 | `ml/configs/mitdb_m1_nopeek_protocol_v1.json` | `1e180b45258d4f9c6902aeee8ccfedd5de38f62b9bb4a2f16f9030391b72ebf4` |
| Bản trước (mục `nopeek`) | `ml/configs/mitdb_m1_baseline_protocol_v4.json` | `7f9eb564176f1a14e521c91e464f4fb79eb77b792e6be69fd884374b8b471e18` |
| Checkpoint khởi tạo (gói A) | C5-seed20261101 epoch 4 | `fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c` |
| File khóa checkpoint | `ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json` | `6848b08dc1f4f55d7d66a4e36b719d55c92eabf37b0c6edbbfdd6b921047d0bc` |

Nguồn: bản 1.2 mục 4.5–4.6; bản chốt 03/11 (câu 1, 3, 4, 8, 11); tin review của SV1 ngày 05/11 (mục 4 và 6a–6b). Protocol v4 không bị sửa; file mới thay cho mục `nopeek` của v4 ở giai đoạn NoPeek.

## 1. Giữ nguyên từ protocol v4

- Lưới λ ∈ {0; 0,1; 0,5; 1; 2; 5}, ba seed 20261030, 20261031, 20261101.
- Mọi run khởi tạo từ cùng checkpoint gói A. Epoch 0 phải ra lại đúng confusion validation của A.
- Ngưỡng tiện ích: mọi seed đạt macro-F1 ≥ 0,95 × A. Quy tắc sụp lớp: một lớp chiếm ≥ 99 % dự đoán, hoặc Se V < 0,10.
- Chọn epoch:
  - λ = 0: macro-F1 lớn nhất, tính cả epoch 0.
  - λ > 0: R_n nhỏ nhất trong các epoch ≥ 1 đạt ngưỡng; không epoch nào đạt thì đánh dấu UTILITY_FAIL.
- Chọn λ: λ có mean R_n nhỏ nhất trên tập 512 mẫu validation cố định; hòa thì chọn λ nhỏ hơn.
- Seed triển khai: seed có R_n ở giữa (median).
- Thống kê: mean, SD với ddof = 1, giữ cả số của run sụp.
- DS2 không bao giờ là đầu vào lựa chọn.

## 2. Thay đổi so với v4

| Mục | v4 | Bản ứng viên v1 | Lý do |
|---|---|---|---|
| Tập s | {2, 5, 8}, 54 run | {2, 4, 5, 8}, 72 run | SV1 mục 6a |
| Tham số chạy | Ghi "chọn bằng pilot, cần review", chưa có giá trị | AdamW (β, eps, weight decay như A); batch 256; sampler K-cân bằng và CE không trọng số như C5; dropout bật khi train; LR hằng; 10 epoch cố định, không dừng sớm | Giữ cùng chính sách huấn luyện với A. Grid tuần 8 dùng CE không cân bằng và lr 1e-4 nên lớp hiếm sụp: macro-F1 0,21–0,32, recall S gần 0 |
| Pilot chọn LR | Chưa định nghĩa | LR ∈ {1e-5; 3e-5; 1e-4}; mỗi LR chạy λ = 0 một lần, λ = 5 ở s2 và s8; seed 20261030; 10 epoch; tổng 9 run. Luật chọn ghi trước, xem mục 3 | Bản 1.2 mục 4.5, sửa bắt buộc số 1 |
| Ngưỡng tiện ích | 0,95 × A | So chính xác bằng `Fraction` trên confusion: macro-F1 ≥ 19/20 × A, ngưỡng = 218290747091/404383914000 ≈ 0,5398107 | Tránh lệch do làm tròn số thực sát ngưỡng |
| λ = 0 lặp ở 4 điểm cắt | Không nói | Giữ đủ 72 run. Với mỗi seed, 12 run λ = 0 phải cho checkpoint trùng bit giữa các s; nếu không trùng thì điều tra như lỗi kỹ thuật | Ở λ = 0, dCor không có gradient nên quá trình train không phụ thuộc s (tuần 8 cũng cho số trùng nhau ở cả 3 s). 9 run thừa đóng vai trò kiểm tính tất định |
| Báo trước khi tính Π | Không có | Gửi SV1 đường macro-F1 theo epoch của λ = 0 (epoch 0–10, 3 seed) cùng số λ đạt ngưỡng, trước mọi đánh giá tấn công hay Π | SV1 mục 4 |
| Luật chọn điểm cắt giữa | Không có | Ghi nguyên văn luật s4/s5 của SV1 mục 6a. Luật này dùng kết quả thử tấn công tuần 11, không thuộc phần chọn của grid | SV1 mục 6a |
| ρ1 | Không có | Head và tail của checkpoint (λ chọn, seed triển khai) tại s2 và điểm cắt giữa; s8 chỉ chạy offline. Gói B không trộn với gói A | Bản chốt câu 1 và 4 |
| Lưu checkpoint | Không nói | Lưu đủ epoch 0–10 của mọi run | Khác GPU thì không tái lập được, nên file checkpoint là bằng chứng duy nhất |

## 3. Luật pilot (ghi trước khi chạy)

1. Một LR được coi là **an toàn** khi run λ = 0 của nó đạt ngưỡng tiện ích ở **cả 10 epoch** và không epoch nào bị sụp.
2. Trong các LR an toàn, chọn LR có trung bình (lấy trên s2 và s8) của R_n nhỏ nhất, xét các epoch 1–10 của run λ = 5 có đạt ngưỡng. Run không có epoch nào đạt thì tính R_n = 1. Hòa thì chọn LR nhỏ hơn.
3. Không có LR nào an toàn thì dừng và gửi SV1 toàn bộ đường cong để SV1 quyết trước khi chạy grid.
4. Kết quả pilot không dùng để chọn λ, và các run pilot không tính vào 72 run của grid.

## 4. Cần SV1 quyết

1. **Chính sách fine-tune:** dùng giống A (sampler K-cân bằng, CE không trọng số, AdamW, batch 256), LR hằng, 10 epoch cố định, không dừng sớm. Có đồng ý không?
2. **Pilot:** ba ứng viên LR {1e-5; 3e-5; 1e-4} và luật ở mục 3 có được không? Chạy pilot xong thì bắt đầu grid ngay khi có receipt, hay chờ SV1 xem receipt?
3. **Số run:** giữ 72 run (12 run λ = 0 dùng làm kiểm tính tất định), hay rút còn 63 run (mỗi seed chạy λ = 0 một lần, dùng chung cho cả 4 s)?
4. **Số epoch:** chọn 10 cho mọi λ. Lý do: run triển khai của A có patience 10 và đạt đỉnh ở epoch 4. Có cần dài hơn không?

## 5. Bước tiếp sau review

1. Nếu SV1 sửa, lập protocol v2 kèm diff. Không sửa file này.
2. Viết runner, plan manifest (cấu hình từng run có SHA) và test; smoke trên dữ liệu ngẫu nhiên, không đọc MITDB.
3. Lập file khóa và train authorization (approved_by SV3, thẩm quyền SV1, review evidence là tin review của SV1), ràng buộc protocol, plan và SHA mã nguồn.
4. Chạy pilot, ghi receipt, rồi chạy grid 72 run trên RTX 5060. Ước lượng (chưa đo): khoảng 3 s mỗi epoch theo thời gian chạy lại A, cộng chi phí tính dCor. Pilot khoảng 5–10 phút, grid khoảng 1 giờ.
5. Gửi SV1 đường cong λ = 0 trước khi tính Π. Sau đó chọn λ cho từng s, lập gói B, rồi thử tấn công tuần 11.

Không có số liệu chất lượng mô hình nào trong tài liệu này. Kiểm JSON chỉ xác nhận số run (72) và đẳng thức 19/20 × A = ngưỡng.
