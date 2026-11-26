# SV3 Model/Privacy — báo cáo tuần 11 (16/11–29/11/2026)

Người lập: SV3. Nhánh `dev/ml-sv3`. Viết ngày 21/11/2026, bổ sung ngày 26/11/2026; tuần chưa kết thúc. Tài liệu ngày lẻ nằm ở [`sv3_archive/`](sv3_archive/README.md).

**Lịch dịch một tuần.** Theo tin SV1 ngày 25/11, việc tuần 11 bắt đầu muộn khoảng một tuần, nên từ nay tuần 11 = 23–29/11/2026. Báo cáo này gộp phần chuẩn bị 16–22/11 (mục 1–3) với tuần 11 theo lịch mới (mục 4).

**Tóm tắt.** Tuần này không chạy tấn công nào, không fit, không mở DS2. Việc chính là soạn để SV1 review:
- attack protocol v3, qua ba bản sửa theo phản hồi SV1 và Hướng xử lý ASI bản 2, bản 3;
- bản nháp threat model (Section III);
- phần related work về DCentNet.

Cả ba đều chưa khóa.

## 1. Attack protocol v3: ba bản sửa, chưa khóa

| Bản | Ngày | SHA-256 | Commit | Lý do |
|---|---|---|---|---|
| r1 | 19/11 | `67342cbd8aa06ab66a3109d9b4bcc9bceb7df659434deb2e10d26ffc48a0d2dd` | `699ee1e` | Theo tin SV1 ngày 19/11: phần a (s9, logits), phần b (tấn công ghép, 21 phép đánh giá, có cổng tái lập), phần c (ρ2) |
| r2 | 20/11 | `8fae0a4e5ef9e0618e775264ebbd092f2efef32e0c5e878c0815a4a976be859f` | `8e59123` | Tin SV1 ngày 20/11 mục 3(6), 3(3): ρ2 có đối chứng nhiễu ở s0, so ở cùng macro-F1 (4 mục tiêu), kẻ tấn công thích nghi và ghép; phần d (bacc theo số nhịp k) |
| r3 | 21/11 | `0436b41b4211ab653d04f82a25f80d5331115b2ef566b357939116008b786e82` | `d5c9158` | Hướng xử lý ASI bản 3: nhánh R phải đạt cả Π theo nhịp lẫn Π khi gộp 10 nhịp; báo mức dựng lại ECG ở cùng mức nhiễu; S0 chuẩn là gom 46 mẫu + Rice (S0c) |

Các bản trước không bị sửa. v2 vẫn là bản đã khóa và là bản ghi của lượt thử. Mọi bản v3 đều viết sau khi đã thấy số lượt thử, và điều này được ghi trong file.

Điểm chính của r3:
- **Tấn công ghép** (phần b): edge giữ phần đuôi mô hình nên tự tính được tensor của điểm cắt sâu hơn. Đo cận trên của Π cho s0, S0c, s2, s4, s5, s8, s9, tổng 27 phép.
- **Nhánh R** (phần c) đạt khi có đủ ba điều kiện:
  - Π ≥ 0,5;
  - Π_k10 ≥ 0,5, lấy theo trường hợp xấu nhất trong {bỏ phiếu đa số, bỏ phiếu mềm} × {liên tiếp, rải rác};
  - macro-F1 ≥ 0,5398.

  Áp dụng cho cả S2 + nhiễu lẫn đối chứng S0 + nhiễu.
- Còn chờ SV1 trả lời 6 câu. Quan trọng nhất là định nghĩa S0c kèm SHA; thiếu nó thì các mục S0c không chạy.

## 2. Góp ý Hướng xử lý ASI bản 2 (19/11)

SV3 góp ý bản 2 cho SV1. Các ý được bản 3 tiếp nhận:
- không viết tấn công ghép như một kết quả đã đo;
- tính năng lượng theo cả nhịp 0,8 s;
- ngân sách dữ liệu Y không che được danh tính;
- đối chứng nhiễu ở S0 cho nhánh R.

## 3. Threat model và related work (20/11)

- **Bản nháp Section III bằng tiếng Anh:**
  - edge "trung thực nhưng tò mò";
  - định nghĩa Π;
  - hai cận ngược chiều (theo sức mạnh kẻ tấn công và theo phiên ghi);
  - tấn công ghép;
  - giới hạn.

  Số chính thức để `[DS2]`. Theo Hướng xử lý bản 3, mục ngân sách rò rỉ phải viết lại theo dạng tỉ lệ nhịp xử lý tại chỗ ≥ p. Việc này chưa làm.
- **DCentNet** (BSPC 104:107468, 2025):
  - đã đọc toàn văn bản arXiv và kiểm DOI qua Crossref;
  - có bảng khác biệt, đoạn tiếng Anh cho Section II và dòng Table I.
- **Table I:** bản nháp 11 bài; 6 bài đã đọc toàn văn. Bản nháp giữ cục bộ, chưa đưa vào repo, chờ tìm toàn văn các bài còn lại.

## 4. Review r3 của SV1 và bản sửa 4 (23–29/11)

**Ngày 25/11 SV1 gửi** review r3, tin bổ sung, hướng dẫn tuần 11–24 và định nghĩa S0c v1. Thầy đã duyệt hướng bản 3 và giao SV1 quyết các mục chi tiết. Bản đúng byte của hai tin và gói S0c v1 được lưu ở `ml/provenance/m1-sv1-evidence-20261125/` và `ml/provenance/s0c-v1/`; hướng dẫn tuần 11–24 giữ cục bộ, chỉ ghi SHA-256 trong protocol.

**Kiểm gói S0c v1 (26/11):**
- cả 9 file đúng SHA-256 trong `SHA256SUMS.txt`;
- x của 20 nhịp golden trùng từng bit với `golden/z_s0.npy` của gói A;
- mã tham chiếu tái tạo đủ 20/20 nhịp golden: 46 giá trị, q, scale FP16, byte Rice, giải mã ngược, 360 mẫu khôi phục.

Script và kết quả: `ml/provenance/s0c-v1/sv3_check_20261126/`.

**Attack protocol v3 r4 (26/11, chưa khóa):** sửa r3 theo review, gửi diff r3 → r4 để SV1 xác nhận rồi khóa. Thay đổi chính:
- thêm cách gộp thứ ba "trung bình k tensor"; Π_k10 lấy trường hợp xấu nhất trên {đa số, mềm, trung bình} × {liên tiếp, rải rác} × mọi kẻ tấn công, kể cả kẻ tấn công sạch ρ0;
- kẻ tấn công thích nghi train trên nhiễu sinh mới mỗi epoch;
- gắn S0c v1 bằng SHA-256, chỉ chạy đối chứng C0c;
- tấn công ghép, s9/s10 và S0c vào lượt DS2 riêng tư (tuần 14); cấu hình nhánh R chỉ vào tập hành động khi DS2 cũng đạt;
- quyết R, K và mô hình phụ ngày 13/12.

**Sửa phần dọn docs theo review:** khôi phục nguyên byte 13 tin nhắn vào [`sv3_archive/messages/`](sv3_archive/messages/); ghi trong [`sv3_archive/README.md`](sv3_archive/README.md) cách chạy lại các script kiểm cũ ở commit `d5c9158`.

## 5. Mốc tiếp theo (lịch dịch)

| Ngày | Việc |
|---|---|
| 29/11 | Khóa r4; code, test, smoke trên dữ liệu giả cho phần a–d |
| 06/12 | Kết quả phần a, b, d trên DS1; bảng chi phí từng lớp bản 1 (tiêu chí chọn mô hình push trước khi khảo sát) |
| 07/12 | Gửi SV1 script lượt DS2 chất lượng để chạy thử trên validation |
| 09/12 | Bảng chi phí từng lớp bản 2 (số Coded, P_conn từ lab) |
| 10/12 | Lượt DS2 chất lượng |
| 11/12 | Kết quả nhánh R (phần c) |
| 13/12 | SV1 quyết R, K, mô hình phụ; khóa protocol G5 v2 |

Song song: threat model bản mới theo ngân sách Y; đoạn DCentNet bản mới; related work và Table I.

## 6. Tài liệu chi tiết

| Ngày | Tài liệu |
|---|---|
| 19/11 | [Attack v3 r1](sv3_archive/sv3_m1_attack_v3_review_20261119.md) |
| 20/11 | [Attack v3 r2](sv3_archive/sv3_m1_attack_v3_r2_review_20261120.md); [threat model nháp](sv3_archive/sv3_threat_model_draft_20261120.md); [DCentNet](sv3_archive/sv3_related_dcentnet_diff_20261120.md) |
| 21/11 | [Attack v3 r3](sv3_archive/sv3_m1_attack_v3_r3_review_20261121.md) |
| 26/11 | [Attack v3 r4](sv3_archive/sv3_m1_attack_v3_r4_review_20261126.md) |

Hồ sơ: `ml/provenance/m1-sv1-evidence-20261119/`, `m1-sv1-evidence-20261120/`, `m1-attack-v3-draft-20261119/`, `m1-attack-v3-r2-draft-20261120/`, `m1-attack-v3-r3-draft-20261121/`, `m1-sv1-evidence-20261125/`, `s0c-v1/`, `m1-attack-v3-r4-draft-20261126/`. Các tin nhắn gửi SV1 trong tuần nằm ở [`sv3_archive/messages/`](sv3_archive/messages/) (bảng ở [`sv3_archive/README.md`](sv3_archive/README.md), mục 3).
