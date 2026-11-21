# Attack protocol v3, bản sửa 3 (M1): gửi SV1 review trước khi khóa

Ngày 21/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa, chưa có code, chưa chạy gì.** DS2 chưa mở.

Bản này thay bản sửa 2 ngày 20/11 (`mitdb_m1_attack_protocol_v3_r2.json`, SHA `8fae0a4e…`, commit `8e59123`). Bản sửa 2 chưa được review hay khóa, và được giữ nguyên làm bản ghi; bản sửa 1 cũng vậy.

Lý do sửa là Hướng xử lý ASI bản 3 ngày 20/11 (file `Huong_xu_ly_ASI_chot_20261120_v3b.docx`, SHA-256 `fca4e0b3c747d788be8fdc36816284d435a233cc72c9079e7e7d67f89c3ff114`, bản cục bộ, không đưa vào repo):
- mục 2 thêm điều kiện bỏ phiếu k nhịp cho nhánh R, và yêu cầu báo mức dựng lại ECG ở cùng mức nhiễu;
- bảng thay đổi đặt "gom 46 mẫu + Rice" làm S0 chuẩn cho mọi phương án gửi S0;
- mục 3 đặt ngân sách Y là tỉ lệ nhịp xử lý tại chỗ.

**v3 được viết sau khi đã thấy Π lượt thử** và kết quả phép thử nén ngày 20/11. 9 cặp v2 giữ nguyên làm bản ghi.

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Attack protocol v3 r3 (ứng viên) | `ml/configs/mitdb_m1_attack_protocol_v3_r3.json` | xem `ml/provenance/m1-attack-v3-r3-draft-20261121/SHA256SUMS.txt` |
| Bản sửa 2 (bị thay, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v3_r2.json` | `8fae0a4e5ef9e0618e775264ebbd092f2efef32e0c5e878c0815a4a976be859f` |
| Bản sửa 1 (bị thay, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v3.json` | `67342cbd8aa06ab66a3109d9b4bcc9bceb7df659434deb2e10d26ffc48a0d2dd` |
| v2 (đã khóa, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v2.json` | `7a174dd9a8ea43003090c32db63db1ed3eae25e9abba8de07d9ec4f6bba019b0` |
| Hướng xử lý ASI bản 3 | bản cục bộ, không đưa vào repo | `fca4e0b3c747d788be8fdc36816284d435a233cc72c9079e7e7d67f89c3ff114` |
| Diff r2 → r3 và v2 → r3 | `ml/provenance/m1-attack-v3-r3-draft-20261121/diffs/` | xem `SHA256SUMS.txt` |

## 1. Các câu hỏi của r2 đã có lời đáp

| Câu hỏi r2 | Lời đáp (ASI bản 3) | Trong r3 |
|---|---|---|
| 1. Giữ checkpoint A hay fine-tune | Mục 2: "giữ checkpoint A" | Bỏ câu hỏi; ghi checkpoint A cố định |
| 2. Bốn mục tiêu macro-F1 | Mục 2: 99, 98, 97, 95 % macro-F1 gốc | Bỏ câu hỏi; giữ cách tìm α (lưới rồi chia đôi trên DS1 validation) |
| Trọng số ngân sách rò rỉ (threat model) | Bảng thay đổi và mục 3: Y = tỉ lệ nhịp xử lý tại chỗ ≥ p | Limitations viết lại; Π, Π_k và mức dựng lại chỉ báo kèm, không làm trọng số |
| Giới hạn công sức | Mục 2: 1,5 tuần công mỗi nhánh | DS1 tuần 12, bàn giao tuần 13, trong 1,5 tuần công của nhánh R |

Câu 3 (5 lần rút nhiễu), câu 4 (lượt DS2) và câu 5 (file gốc tin 20/11) chưa có lời đáp nên được giữ lại.

## 2. Thay đổi so với r2

### 2.1. Luật đạt của nhánh R: thêm Π khi bỏ phiếu k nhịp

Một cấu hình (S2 + ρ2, hoặc đối chứng S0 + nhiễu) **đạt** ở mức nhiễu α khi có đủ ba điều kiện:
1. Π theo nhịp ≥ 0,5;
2. Π_k10 ≥ 0,5, tức Π khi bên nhận gộp 10 nhịp của cùng phiên;
3. macro-F1 ≥ 0,5398.

Cách tính Π_k10 (mục `k_beat_vote` trong JSON):
- Chỉ dùng dự đoán đã lưu, không train thêm.
- Có hai kiểu lấy nhịp:
  - **liên tiếp:** khối 10 nhịp liền nhau;
  - **rải rác:** 200 lần rút 10 nhịp.
- Có hai luật bỏ phiếu:
  - **cứng:** bỏ phiếu đa số;
  - **mềm:** cộng log-xác suất của từng nhịp rồi lấy argmax. Luật này mạnh hơn bỏ phiếu đa số mà không cần train, chỉ cần lưu log-xác suất. Vì vậy r3 yêu cầu mọi kẻ tấn công mới lưu log-xác suất. Lượt thử v2 chỉ lưu argmax nên các cặp v2 chỉ có bỏ phiếu cứng.
- Π_k10 = 1 − max theo mọi biến thể kẻ tấn công × luật bỏ phiếu × kiểu lấy nhịp. Đây là cùng nguyên tắc "lấy kẻ tấn công mạnh nhất" như Π theo nhịp.
- Các giá trị k khác (1, 2, 5, 20, 50, 100) chỉ vẽ đường cong để báo cáo.

**Cần lường trước:** ở S0 chưa có nhiễu, bỏ phiếu 10 nhịp đã cho bacc 0,89–0,91. Muốn Π_k10 ≥ 0,5 thì nhiễu phải làm nhận diện theo từng nhịp gần như ngẫu nhiên, nên khả năng cao cả hai cấu hình đều trượt.

### 2.2. Mức dựng lại ECG ở cùng mức nhiễu

Ở mỗi α_t, cho cả hai cấu hình, r3 báo hai mức dựng lại:
- **Mức sàn không cần train:** với C0c là phép nội suy mà edge vẫn làm; với C0 là chính x có nhiễu; R2 không có mức sàn.
- **A1 thích nghi:** decoder được train trên 5 lần rút nhiễu, đích là x sạch.

Các thước đo là NRMSE, Pearson và lỗi R-peak. Phần này chỉ để báo cáo, không phải điều kiện đạt.

### 2.3. Đối chứng S0 chuyển sang S0c (46 mẫu + Rice)

Gọi S0c là S0 chuẩn mới, "gom 46 mẫu + Rice". r3 thêm các việc sau:
- **Phần a:** B-naive và A1 ở S0c, dưới ρ0. Π(S0c) sẽ là số riêng tư của S0 trong mọi bảng.
- **Phần b:** S0c là thêm một nguồn cho tấn công ghép. Edge nội suy về 360 mẫu rồi chạy C5. Số phép ghép tăng từ 21 lên 27.
- **Phần c:** đối chứng C0c cộng nhiễu lên 46 giá trị đã gom, rồi mới mã hóa.
  - Không cộng nhiễu trước bước gom, vì bước gom có thể làm mất bớt nhiễu, khiến đối chứng yếu hơn mức nó có thể đạt.
  - r3 báo số byte Rice mỗi nhịp ở từng α, vì nhiễu làm dữ liệu khó nén hơn. Số này phục vụ việc so chi phí ở G5, không quyết định gì ở đây.

**Điều kiện:** các mục S0c chỉ chạy khi định nghĩa S0c được ràng buộc bằng SHA-256 trước khi khóa. Định nghĩa gồm cách gom 46 mẫu, biểu diễn số nguyên, tham số Rice và phép nội suy ở edge. Nếu không có, các mục S0c ghi NOT_RUN và phần c dùng đối chứng C0 trên nhịp đủ 360 mẫu như r2.

### 2.4. Bảng quyết định theo ASI bản 3 mục 2

| Kết quả (macro-F1 ≥ 0,5398) | Quyết định cuối tuần 13 |
|---|---|
| Đối chứng S0 + nhiễu đạt cả hai điều kiện Π | Ưu tiên S0 + nhiễu; báo cả hai đường cong |
| Chỉ S2 + ρ2 đạt cả hai | S2 + ρ2 vào tập ứng viên; SV1 đo điện và độ trễ, so với chính sách luân phiên S0/S10 |
| Không cấu hình nào đạt | Kết quả âm cho cơ chế và phạm vi đã thử, kèm Π theo nhịp, Π_k10 và đường cong |

### 2.5. Limitations thêm

- Ngân sách Y là tỉ lệ nhịp xử lý tại chỗ, không che danh tính.
- Bên nhận có thể lấy trung bình nhiều tensor có nhiễu đã căn theo R-peak trước khi phân loại, và cách này khử nhiễu nhanh hơn bỏ phiếu. r3 không thử cách gộp này, nên Π_k vẫn là cận trên.
- Kết quả S0c chỉ đúng cho đúng cách mã hóa S0c được ràng buộc.

## 3. Câu hỏi cho SV1

1. Dùng k = 10, và lấy Π_k10 theo trường hợp xấu nhất trong {bỏ phiếu cứng, bỏ phiếu mềm} × {liên tiếp, rải rác}: có được không?
2. Nhờ gửi định nghĩa S0c của phép thử nén ngày 20/11 (script hoặc file, kèm SHA-256) và đầu ra tham chiếu cho 20 nhịp golden.
3. Đối chứng cộng nhiễu lên 46 giá trị đã gom (C0c), hay lên nhịp đủ trước khi gom? Có chạy thêm C0 đủ 360 mẫu của r2 không? Mặc định là chỉ chạy C0c, để nằm trong giới hạn công sức.
4. Kẻ tấn công thích nghi và A1 thích nghi dùng 5 lần rút nhiễu chuẩn bị sẵn: đủ chưa?
5. B-composite, s9/s10 và S0c có vào lượt chính thức DS2 không? Mặc định là có, theo authorization riêng của lượt đó.
6. Nhờ gửi file gốc tin 20/11. Bản đang ràng buộc chỉ là bản chép lại.

## 4. Khối lượng ước lượng (chưa đo)

| Phần | Khối lượng |
|---|---|
| a | 3 cặp (s9, s10, S0c) × 3 seed B + A1 |
| b | 27 phép ghép, chỉ suy luận |
| c | Tối đa 8 điểm × 7–8 biến thể × 3 seed (khoảng 180 lần fit) + 8 A1 thích nghi; Π_k10 tính lại từ dự đoán đã lưu |
| d | Chỉ tính từ dự đoán đã lưu |

Ở lượt thử, 9 cặp × (3 seed B + A1) chạy hết khoảng 7 phút trên RTX 5060. Như vậy phần chạy máy nằm gọn trong 1,5 tuần công của nhánh R; phần tốn công chủ yếu là viết code và test.

## 5. Đã làm, đã kiểm, chưa làm

- **Đã làm:**
  - viết protocol v3 r3 (JSON hợp lệ, LF);
  - tạo diff r2 → r3 và v2 → r3;
  - ghi SHA-256 vào `SHA256SUMS.txt`.
- **Đã kiểm:**
  - DS1 validation gồm đúng 4 bản ghi (`ml/configs/mitdb_ds1ds2_m1_v3.json`), khớp với "4 bệnh nhân DS1 validation" của phép thử nén;
  - trong mảng của lượt thử v2 chỉ có argmax, không có xác suất (`s0-rho0-base-arrays.npz`).
- **Chưa làm:**
  - code, test, smoke trên dữ liệu giả;
  - khóa: file khóa do người dùng cung cấp sau khi SV1 review;
  - sửa threat model theo Y (việc riêng, làm sau).
- Không chạy tấn công nào, không fit, không mở DS2.
