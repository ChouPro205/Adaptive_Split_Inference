# SV3 Model/Privacy — báo cáo tuần 11 (16/11–29/11/2026)

Người lập: SV3. Nhánh `dev/ml-sv3`. Viết ngày 21/11/2026, bổ sung ngày 26/11 và 27/11/2026; tuần chưa kết thúc. Tài liệu ngày lẻ nằm ở [`sv3_archive/`](sv3_archive/README.md).

**Lịch dịch một tuần.** Theo tin SV1 ngày 25/11, việc tuần 11 bắt đầu muộn khoảng một tuần, nên từ nay tuần 11 = 23–29/11/2026. Báo cáo này gộp phần chuẩn bị 16–22/11 (mục 1–3) với tuần 11 theo lịch mới (mục 4).

**Tóm tắt.**
- Attack protocol v3 qua năm bản sửa; r5 được SV1 xác nhận và khóa ngày 26/11. Code, test và smoke trên dữ liệu giả xong cùng ngày.
- Ngày 27/11, sau khi SV1 cho phép, chạy phần a, b, d và c trên DS1, mỗi lượt có receipt. Đây là số phát triển, chỉ để cảnh báo sớm. Kết quả: mọi điểm gửi có Π dưới 0,5; không cấu hình nhiễu nào của nhánh R hay C0c đạt. DS2 chưa mở.
- Threat model và đoạn related work về DCentNet qua ba bản nháp. Bản 3 sửa theo tin 27/11 của SV1, chờ SV1 đọc lại.

Mục 1–3 là phần chuẩn bị 16–22/11; mục 4 và 5 là tuần 11 theo lịch mới.

## 1. Attack protocol v3: ba bản sửa đầu (16–22/11)

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

**r5, khóa và code (26/11):**
- SV1 đồng ý nội dung r4 và yêu cầu sửa ba chỗ thành r5:
  - cổng macro-F1 trên DS2 tính tương đối, bằng 19/20 × macro-F1_DS2(A, FP32);
  - "cùng kẻ tấn công" nghĩa là cùng công thức, train lại trên DS2;
  - seed nhiễu cho DS2 dùng part_index 4–7.
- r5 (SHA `9235b795…`, commit `2284ea8`) được SV1 xác nhận và đã khóa (file khóa `b3a89cbb…`, commit `3f6a6de`). File khóa chỉ khóa định nghĩa, chưa cho chạy.
- Code phần a–d, test và smoke trên dữ liệu giả đã xong. Chưa chạy trên MITDB; cần file cho phép chạy.
- Chi tiết ở [r5: khóa và code](sv3_archive/sv3_m1_attack_v3_r5_code_20261126.md).

**Sửa phần dọn docs theo review:** khôi phục nguyên byte 13 tin nhắn vào [`sv3_archive/messages/`](sv3_archive/messages/); ghi trong [`sv3_archive/README.md`](sv3_archive/README.md) cách chạy lại các script kiểm cũ ở commit `d5c9158`.

**Threat model bản 2 và DCentNet bản 2 (27/11, sáng):**
- [Threat model bản 2](sv3_archive/sv3_threat_model_draft_v2_20261127.md), sửa theo review 25/11 mục 4:
  - ngân sách rò rỉ là tỉ lệ nhịp gửi đi ≤ 1 − p, không còn trọng số theo Π;
  - S0 chuẩn là S0c;
  - với S0c, cận ghép được đo chứ không khẳng định;
  - đối chứng C0c, luật đạt có Π_k10 với ba cách gộp và bước xác nhận trên DS2.
- [DCentNet bản 2](sv3_archive/sv3_related_dcentnet_diff_v2_20261127.md), sửa theo review 25/11 mục 5:
  - sửa ô mô hình năng lượng (1,03 %; lệch giữa các ngày do REG0);
  - sửa dòng nén cho đúng với S0c và S1.
- Lúc đó chưa đọc được toàn văn bài IEEE Sensors J 2024, nên chưa chốt dòng Table I.

## 5. Ngày 27/11: cho phép chạy, kết quả DS1, bản 3 của hai tài liệu

**Tin SV1 ngày 27/11** (lưu đúng byte ở `ml/provenance/m1-sv1-evidence-20261127/`, SHA `696f3309…`):
- xác nhận khóa r5 và code: SV1 tự tính lại SHA, chạy lại `verify_lock.py` (6/6 trường hợp sai cố ý bị từ chối);
- đồng ý nhiễu sinh mới mỗi epoch, không dùng phương án dự phòng;
- cho SV3 tự lập file cho phép chạy phần a, b, d, c chỉ trên DS1;
- góp ý threat model bản 2 và DCentNet bản 2.

**File cho phép chạy** (`ml/provenance/m1-attack-v3-run-auth-20261127/`, SHA `6481e9a2…`, commit `e55e82b`):
- gắn SHA của protocol r5, file khóa, plan, receipt code, ba file code, khóa checkpoint và ρ0; `allow_DS2 = false`; nhiễu "fresh";
- `verify_run_authorization.py` gọi chính cổng của runner cho từng phần; thoát mã 0 ở chế độ thường và `-O`; 5 trường hợp sai cố ý × 4 phần đều bị từ chối;
- cổng v3 không ghim được file bằng chứng qua protocol như v2 (tin SV1 có sau r5). Script kiểm ghim đường dẫn và SHA của tin 27/11; điểm này ghi trong trường `gate_note` và báo SV1.

**Kết quả trên DS1** (chi tiết ở [kết quả DS1](sv3_archive/sv3_m1_attack_v3_ds1_results_20261127.md)):
- Phần a, b, d: commit `e55e82b`, 22 phút, mã thoát 0, receipt `e3996a01…` (commit `7dba869`). Π_v3 của S0c 0,075; s0–s8 khoảng 0,068 (tấn công ghép sang s8); s9 0,102; logits s10 0,287. Gộp 10 nhịp thì Π_k10 ≤ 0,063 ở mọi hàng.
- Phần c: commit `7dba869`, khoảng 1 giờ 55 phút, mã thoát 0, receipt `2e571b70…` (commit `30ed99f`). Cả 8 điểm (R2 và C0c ở 4 mục tiêu macro-F1) qua cổng macro-F1 nhưng Π chỉ 0,067–0,078, Π_k10 ≤ 0,006. Không điểm nào đạt; cách đọc khai trước là "neither".
- Số epoch thực chạy của biến thể thích nghi: 16–50; 15 trên 164 lần train dừng trước epoch 20, đều là B-composite-adaptive → s8. Ghi cho mục hạn chế.
- Các số này là số phát triển trên bệnh nhân DS1, không phải kết quả của bài và không chọn tham số nào ngoài α.

**Threat model bản 3 và DCentNet bản 3 (27/11, chiều, chờ SV1 đọc lại):**
- [Threat model bản 3](sv3_archive/sv3_threat_model_draft_v3_20261127.md): câu mở đầu "Leakage budget" viết dạng điều kiện, có chế độ che danh tính nếu nhánh R đạt; nhịp gửi có nhiễu vẫn tính là gửi; "Cost" còn một câu trỏ Section V, câu "virtual queue" chuyển Section IV; số byte S0c ghi đúng nguồn (36,4 B trên DS1 validation).
- [DCentNet bản 3](sv3_archive/sv3_related_dcentnet_diff_v3_20261127.md): đã đọc toàn văn bài IEEE Sensors J 2024 và bài NEWCAS 2023 của cùng nhóm, thêm dòng Table I và hai câu trong đoạn tiếng Anh; câu về bộ nén S1 thành chỗ trống `[K]` tới ngày 13/12; bảng tiếng Việt trích khảo sát S1 ở `results/week11/device/analysis/compression-20261120/` trên main.

## 6. Mốc tiếp theo (lịch dịch)

| Ngày | Việc |
|---|---|
| 29/11 | Khóa r5; code, test, smoke trên dữ liệu giả cho phần a–d (xong 26/11) |
| 06/12 | Kết quả phần a, b, d trên DS1 (xong 27/11); bảng chi phí từng lớp bản 1 (tiêu chí chọn mô hình push trước khi khảo sát) |
| 07/12 | Gửi SV1 script lượt DS2 chất lượng để chạy thử trên validation |
| 09/12 | Bảng chi phí từng lớp bản 2 (số Coded, P_conn từ lab) |
| 10/12 | Lượt DS2 chất lượng |
| 11/12 | Kết quả nhánh R (phần c trên DS1 xong 27/11); bảng quyết định và số ngày công cho H9 |
| 13/12 | SV1 quyết R, K, mô hình phụ; khóa protocol G5 v2 |

Song song: related work và Table I (còn OPEN, ISCC, ENACHI và các bài mới đọc tóm tắt); threat model và DCentNet bản 3 chờ SV1 đọc lại.

## 7. Tài liệu chi tiết

| Ngày | Tài liệu |
|---|---|
| 19/11 | [Attack v3 r1](sv3_archive/sv3_m1_attack_v3_review_20261119.md) |
| 20/11 | [Attack v3 r2](sv3_archive/sv3_m1_attack_v3_r2_review_20261120.md); [threat model nháp](sv3_archive/sv3_threat_model_draft_20261120.md); [DCentNet](sv3_archive/sv3_related_dcentnet_diff_20261120.md) |
| 21/11 | [Attack v3 r3](sv3_archive/sv3_m1_attack_v3_r3_review_20261121.md) |
| 26/11 | [Attack v3 r4](sv3_archive/sv3_m1_attack_v3_r4_review_20261126.md); [r5](sv3_archive/sv3_m1_attack_v3_r5_review_20261126.md); [r5: khóa và code](sv3_archive/sv3_m1_attack_v3_r5_code_20261126.md) |
| 27/11 | [Threat model bản 2](sv3_archive/sv3_threat_model_draft_v2_20261127.md), [bản 3](sv3_archive/sv3_threat_model_draft_v3_20261127.md); [DCentNet bản 2](sv3_archive/sv3_related_dcentnet_diff_v2_20261127.md), [bản 3](sv3_archive/sv3_related_dcentnet_diff_v3_20261127.md); [kết quả DS1](sv3_archive/sv3_m1_attack_v3_ds1_results_20261127.md) |

Hồ sơ: `ml/provenance/m1-sv1-evidence-20261119/`, `m1-sv1-evidence-20261120/`, `m1-attack-v3-draft-20261119/`, `m1-attack-v3-r2-draft-20261120/`, `m1-attack-v3-r3-draft-20261121/`, `m1-sv1-evidence-20261125/`, `s0c-v1/`, `m1-attack-v3-r4-draft-20261126/`, `m1-sv1-evidence-20261126/`, `m1-attack-v3-r5-draft-20261126/`, `m1-attack-v3-r5-lock-20261126/`, `m1-attack-v3-code-20261126/`, `m1-sv1-evidence-20261127/`, `m1-attack-v3-run-auth-20261127/`, `m1-attack-v3-abd-run-20261127/`, `m1-attack-v3-c-run-20261127/`. Các tin nhắn gửi SV1 trong tuần nằm ở [`sv3_archive/messages/`](sv3_archive/messages/) (bảng ở [`sv3_archive/README.md`](sv3_archive/README.md), mục 3).
