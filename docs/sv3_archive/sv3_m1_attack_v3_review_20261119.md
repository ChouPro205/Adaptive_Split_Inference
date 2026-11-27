# Attack protocol v3 (M1): bản gửi SV1 review trước khi khóa

Ngày 19/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa, chưa có code, chưa chạy gì.** DS2 chưa mở. Theo mục 4 tin SV1 ngày 19/11, v3 đổi định nghĩa "tấn công mạnh nhất", nên phải gửi SV1 review trước khi khóa.

**v3 được viết sau khi đã thấy Π lượt thử.** Lúc viết, SV3 và SV1 đã thấy toàn bộ 9 cặp v2 (Π, CI, bacc, bacc theo phiên, chỉ số A1). 9 cặp v2 giữ nguyên làm bản ghi: không chạy lại, không sửa.

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Attack protocol v3 (ứng viên) | `ml/configs/mitdb_m1_attack_protocol_v3.json` | xem `ml/provenance/m1-attack-v3-draft-20261119/SHA256SUMS.txt` |
| Bản trước (v2, đã khóa, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v2.json` | `7a174dd9a8ea43003090c32db63db1ed3eae25e9abba8de07d9ec4f6bba019b0` |
| Receipt lượt thử v2 (ràng buộc attacker và dự đoán mà phần b đọc) | `ml/provenance/m1-attack-v2-trial-20261113/receipt.json` | `b2861c71cbf4a39007a202ca37156d9c047b4cf217f36a197defda2082d900ed` |
| Tin SV1 ngày 19/11 (bản chép đúng từng byte) | `ml/provenance/m1-sv1-evidence-20261119/tra_loi_Ky_Anh_Pi_thu_va_review_20261119.txt` | `1a9b2183ebf8e37a087064657a9a7af5036d185cee4a2ec0936fd149fec854cf` |
| Tin rà soát của SV3 ngày 14/11 | `docs/sv3_review_after_trial_message_sv1_20261114.txt` | `9061adbbaf7aa8f0cab5bf6cef9b0fbad90662c6a9c97671b5e8c63c8ebe991f` |
| Diff dòng v2 → v3 | `ml/provenance/m1-attack-v3-draft-20261119/diffs/protocol-v2-v3.diff` | xem `SHA256SUMS.txt` |

v3 kế thừa nguyên mọi phần của v2 mà nó không nêu lại: threat model, A1, B-naive, z_s, công thức Π, bootstrap, chia dữ liệu, mô hình tấn công, kết quả kiểm năng lực. Vì vậy diff dòng chủ yếu cho thấy các phần mới. Danh sách thay đổi đầy đủ, kèm nguồn, nằm trong trường `changes_from_v2`.

## 1. Thay đổi so với v2

| # | Nội dung | Nguồn |
|---|---|---|
| 1 | **Phần a:** B-naive và A1 ở s9 và s10 (logits), chỉ ρ0, dữ liệu và luật như lượt thử, kiến trúc cơ bản. Số ở s10 gọi là Π_logits, không phải Π(s10) của tập hành động | SV1 19/11 mục 4(a), 5 |
| 2 | **Phần b:** biến thể B-composite cho ρ0. Π_v3(s, ρ0) = 1 − max theo biến thể, gồm B-naive ở s và B-composite s → s′ với mọi s′ > s đã có kẻ tấn công. Không train thêm | SV1 19/11 mục 2, 4(b) |
| 3 | **Phần c:** đặc tả ρ2 (nhiễu Gauss theo kênh ở s2, checkpoint A giữ nguyên), kèm đối chứng: cùng mức nhiễu lên tín hiệu thô rồi gửi ở s0. Quét 5 mức, báo Π và macro-F1 ở mỗi mức; chỉ DS1 | SV1 19/11 mục 3, 4(c) |
| 4 | Π(s10) của tập hành động = 1 theo cấu tạo; số đo ở s10 là cận trên cho các s < 10 | SV1 19/11 mục 5 |
| 5 | Limitations: tái định danh tập đóng trong cùng phiên, và chiều của từng cận | SV1 19/11 mục 7 |
| 6 | Chi tiết thực thi của mục 2 và 3: phép tính composite, cổng tái lập, bộ sinh nhiễu và seed | Để mục 2 và 3 chính xác |

## 2. Các chỗ mình đã chọn, cần SV1 xem

**Logits là logits nào (phần a).** Dùng đầu ra FP32 của toàn bộ checkpoint A, lượng tử như mọi s khác, tức đúng tensor 15 B danh nghĩa trong table_iii. Logits INT8 của KV260 (bội của 0,125) không bị tấn công. Bỏ một biến thể chỉ có thể làm Π cao hơn, nên mọi Π vẫn là cận trên. Điểm này ghi trong Limitations.

**B-composite không khớp tuyệt đối (phần b).** Ở s0, edge nhận deq(q(x)), không phải x. Kẻ tấn công s8 lại được train trên z_s8 tính từ x. Vì vậy "Π(s0) ≤ 0,068" (tin 19/11 mục 2) là giả thuyết để phần b đo, chưa phải sự thật. v3 cố định phép tính như sau:
- lấy u_s;
- chạy các op cố định `OPS[CUTS[s]:CUTS[s′]]` của checkpoint A;
- lượng tử rồi giải lượng tử bằng hàm registry v2;
- chuẩn hóa bằng thống kê của phần train phía kẻ tấn công tại s′;
- áp kẻ tấn công của s′.

**Cổng tái lập (phần b).** Trước khi có bất kỳ số composite nào, kẻ tấn công nạp lại phải cho dự đoán trên u_s′ thật trùng từng phần tử với `pred_seed*` đã lưu trong lượt thử. Nếu lệch thì dừng và báo. Mình đã kiểm cả 29 file đầu ra của lượt thử vẫn khớp SHA trong receipt (0 lệch).

**Tổ hợp composite (phần b).** Nguồn s ∈ {0, 2, 4, 5, 8, 9}, đích s′ ∈ {2, 4, 5, 8, 9, 10}, s′ > s: 21 phép đánh giá, chỉ suy luận. s1, s3, s6, s7 không đo, nên không nêu Π cho các s này. ρ1 không có composite, vì mỗi s là một checkpoint riêng và chưa có kẻ tấn công ở s′ sâu hơn của checkpoint đó.

**Đặc tả ρ2 (phần c).**
- Nhiễu: e ~ N(0, (α·σ_c)²), cộng lên z_s2 trên thiết bị trước khi lượng tử. σ_c là std theo kênh của z_s2 sạch trên DS1 train, tính một lần và ghi SHA trước mọi lần đánh giá có nhiễu.
- Các mức: α ∈ {0,1; 0,25; 0,5; 1; 2}.
- Đối chứng: cùng α nhân với std của x, cộng lên x rồi gửi ở s0.
- Tiện ích: macro-F1 fixed4 trên DS1 validation, tính bằng Fraction trên confusion cộng qua 3 lần rút nhiễu. Ngưỡng là 19/20 × A, cùng ngưỡng đã chặn ρ1.
- Riêng tư: B-naive (3 seed) train và test trên tensor có nhiễu, dùng dữ liệu và luật chia như lượt thử.
- Cách đọc đã khai trước:
  - Nếu có α cho Π ≥ 0,5 mà vẫn đạt ngưỡng tiện ích: báo SV1 ngay.
  - Gắn cờ "bị s0 có nhiễu lấn át" khi đối chứng đạt Π và macro-F1 không thấp hơn s2 + ρ2.
  - Các trường hợp còn lại: báo hai đường cong riêng tư – tiện ích.

**Chiều của các cận (Limitations).**
- Theo sức mạnh kẻ tấn công: Π đo được là cận trên của Π trong cùng phiên.
- Theo yếu tố phiên: Adv trong cùng phiên là cận trên của Adv khác phiên, tức Π trong phiên là cận dưới của Π khác phiên.
- Vì vậy kết quả âm được phát biểu cho bài toán tái định danh tập đóng trong cùng phiên.

Ở mục 7, tin 19/11 viết "Π trong cùng phiên là cận trên của khả năng liên kết". v3 ghi theo Adv để không lẫn với Π.

## 3. Câu hỏi cho SV1

1. Hiểu "cùng mức nhiễu" là cùng α so với std của chính từng kênh có được không? z_s2 và x nằm ở hai không gian khác nhau, nên không dùng chung một σ tuyệt đối được.
2. ρ2 giữ checkpoint A cố định, hay fine-tune tail có nhiễu cho từng α? Giữ cố định thì rẻ và vừa 1 tuần. Fine-tune thì sát Abuadbba 2020 và ý P2 cũ hơn, nhưng tốn hơn.
3. Khi lượt chính thức DS2 được phép chạy, B-composite và s9/s10 có vào lượt đó không? Bản nháp này mặc định là có, theo authorization riêng của lượt đó.
4. Năm mức α như trên có được không?

## 4. Đã làm, đã kiểm, chưa làm

- Đã làm:
  - viết protocol v3 (JSON hợp lệ) và diff v2 → v3;
  - chép tin SV1 ngày 19/11 đúng từng byte vào provenance;
  - kiểm 29 file đầu ra của lượt thử v2 khớp receipt b2861c71.
- Chưa làm:
  - code (runner phần a/b, script ρ2), test, smoke trên dữ liệu giả;
  - khóa: file khóa do người dùng cung cấp sau khi SV1 review.
- Không chạy tấn công nào, không fit, không mở DS2.
