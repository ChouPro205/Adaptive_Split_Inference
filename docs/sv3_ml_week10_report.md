# SV3 Model/Privacy — báo cáo tuần 10 (09/11–15/11/2026)

Người lập: SV3. Nhánh `dev/ml-sv3`. Báo cáo tổng hợp, viết ngày 21/11/2026 từ các tài liệu ngày lẻ đã chuyển vào [`sv3_archive/`](sv3_archive/README.md) và các hồ sơ trong `ml/provenance/`.

**Tóm tắt.**
- Khóa và chạy NoPeek v2: 9 run pilot và 72 run grid.
- Giao gói A cho SV2 (mốc M2).
- Khóa attack protocol v2 trước khi chạy, rồi chạy lượt thử tấn công trên 22 bệnh nhân DS1.

Kết quả lượt thử: không điểm cắt nào đạt Π ≥ 0,5, và NoPeek gần như không nâng được Π. Đây là lượt thử trên bệnh nhân đã có trong tập huấn luyện, chỉ để cảnh báo sớm. DS2 chưa mở.

## 1. PR #44 vào main (09/11)

PR #44 được squash-merge vào `main` thành commit `f4db84c`, gồm checkpoint C5 đã khóa, gói A ứng viên, script DS2, NoPeek v1 và protocol tấn công v1. Ngày 11/11, commit đó được merge lại vào `dev/ml-sv3` (`450664b`), và PR #47 đồng bộ `dev/ml-sv3` lên `main`.

## 2. NoPeek v2: khóa, pilot và grid (11–12/11)

- **Protocol v2** sửa theo tin SV1 ngày 09/11 (`ml/configs/mitdb_m1_nopeek_protocol_v2.json`, SHA-256 `83cce64defefa979abcf8c31cc27daf9ae81604caae911acf0901cba3783cf35`):
  - tắt TF32 cho mọi run và mọi lượt đánh giá;
  - pilot chọn được LR an toàn thì chạy grid ngay.

  File khóa: `ml/provenance/m1-nopeek-v2-lock-20261112/`.
- **Pilot** gồm 9 run và chọn LR 3e-5. **Grid** gồm 72 run (4 điểm cắt × 6 λ × 3 seed), chạy ngày 12/11 từ 20:30 đến 21:21, tất cả exit 0.
- **Kiểm:**
  - mọi run có epoch 0 ra đúng confusion validation của A;
  - checkpoint của mọi epoch nạp lại khớp confusion đã ghi;
  - với λ = 0, kết quả trùng từng bit giữa 4 điểm cắt.
- **Lựa chọn theo luật đã khóa** (R_n càng nhỏ thì tương quan giữa đặc trưng và input càng thấp):

| Điểm cắt | λ | Seed | Epoch | R_n | macro-F1 | R_n ở λ = 0 |
|---|---:|---:|---:|---:|---:|---:|
| s2 | 2 | 20261101 | 3 | 0,9095 | 0,5590 | 0,9649 |
| s4 | 1 | 20261031 | 3 | 0,8661 | 0,5419 | 0,9553 |
| s5 | 1 | 20261030 | 2 | 0,9241 | 0,5451 | 0,9629 |
| s8 | 5 | 20261031 | 5 | 0,5690 | 0,5741 | 0,8024 |

  Không run nào bị sụp lớp. Checkpoint của 81 run đăng Release ngày 13/11, trước khi chạy tấn công (`ml/provenance/m1-nopeek-v2-release-20261113/`).

## 3. Giao gói A cho SV2, mốc M2 (12/11)

- File `SV3_M1_V4_PACKAGE_A_20261105.zip` (59 file), SHA-256 `0b4294b54d2cb3211564725ad1c636f9d30739d3e705b0f0c2fc33b147e83e29`, đăng ở Release `sv3-m1-v4-package-a-20261112`. Đây đúng là gói dựng ngày 05/11, không sửa byte nào.
- Gói gồm input chuẩn hóa và golden z_s s0–s9 của 1.000 nhịp calibration, checkpoint C5 kèm file khóa, cùng dự đoán tham chiếu.
- Bản ghi giao: `ml/provenance/m1-v4-package-a-delivery-20261112/`.

## 4. Attack protocol v2 và lượt thử tấn công (13/11)

- **Protocol v2** sửa theo tin SV1 ngày 09/11 và 13/11 (`ml/configs/mitdb_m1_attack_protocol_v2.json`, SHA-256 `7a174dd9a8ea43003090c32db63db1ed3eae25e9abba8de07d9ec4f6bba019b0`):
  - N = 22 cho lượt thử và N = 21 cho lượt chính thức;
  - CI95 bằng bootstrap theo khối 10 nhịp trong từng bệnh nhân;
  - kẻ tấn công B chạy 3 seed;
  - kiểm năng lực kẻ tấn công ở s0 trước khi chạy.

  Protocol được khóa trước khi chạy: file khóa `ml/provenance/m1-attack-v2-lock-20261113/`, SHA-256 `205ec6db98a75e2730cc2877021b4f48881550c96673acc8ba744bc2c421f8ba`.
- **Lượt thử trên DS1** (N = 22; receipt `b2861c71…`; 9 cặp chạy hết khoảng 7 phút trên RTX 5060):
  - Kiểm năng lực ở s0 cho bacc 0,8256 ≥ 0,80, nên giữ kiến trúc cơ bản.
  - Π theo ρ0 (chưa bảo vệ) và ρ1 (NoPeek):

| Điểm cắt | s0 | s2 | s4 | s5 | s8 |
|---|---:|---:|---:|---:|---:|
| Π (ρ0) | 0,183 | 0,100 | 0,081 | 0,076 | 0,068 |

  - ρ1 cho Π gần như bằng ρ0 ở mọi điểm cắt (s2: 0,101).
  - Tấn công tái tạo A1 ở s2 cho Pearson 0,999.
  - Bỏ phiếu theo phiên 10 nhịp ở s0 cho bacc 0,89–0,91.
  - SV1 tính lại độc lập 9/9 cặp và khớp.
- **Cách đọc:** không cấu hình nào đạt Π_min = 0,5. Π giảm dần theo độ sâu của điểm cắt, nhiều khả năng vì kẻ tấn công ở tầng nông yếu hơn, chứ không phải vì tầng nông riêng tư hơn. Giả thuyết này được đưa vào attack v3 (tấn công ghép) ở tuần 11.

## 5. Rà soát sau lượt thử (14/11)

Gửi SV1 bản rà soát sau lượt thử. Các ý chính:
- Ghép số năng lượng tuần 9 với Π lượt thử: các điểm cắt giữa không còn lý do tồn tại.
- Π(s0) = 0,183 không dùng làm mốc được, vì kẻ tấn công ở s0 yếu.
- Đề xuất ba phép kiểm trên DS1, cần attack protocol v3:
  - (a) tấn công s9 và logits;
  - (b) kẻ tấn công ở s0 tự tính z_s sâu hơn;
  - (c) đối chứng "nhiễu trên tín hiệu thô gửi ở s0" khi có ρ2.
- Nêu giới hạn của bài toán nhận diện trong cùng một bản ghi.
- Đề nghị thêm MobiTrust và DCentNet vào Table I.

## 6. Tài liệu chi tiết

| Ngày | Tài liệu |
|---|---|
| 11/11 | [NoPeek v2, bản sẵn sàng khóa](sv3_archive/sv3_m1_nopeek_v2_review_20261111.md) |
| 13/11 | [Attack protocol v2 và code tấn công](sv3_archive/sv3_m1_attack_v2_review_20261113.md) |

Hồ sơ: `ml/provenance/m1-sv1-evidence-20261111/`, `m1-nopeek-v2-code-20261111/`, `m1-nopeek-v2-lock-20261112/`, `m1-nopeek-v2-run-20261112/`, `m1-nopeek-v2-release-20261113/`, `m1-v4-package-a-delivery-20261112/`, `m1-v4-package-a-release-20261112/`, `m1-attack-v2-code-20261113/`, `m1-attack-v2-lock-20261113/`, `m1-attack-v2-trial-20261113/`. Các tin nhắn gửi SV1, SV2 trong tuần được gỡ khỏi cây thư mục và vẫn còn trong lịch sử Git (xem [`sv3_archive/README.md`](sv3_archive/README.md), mục 3).
