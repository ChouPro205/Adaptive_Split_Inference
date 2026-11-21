# Attack protocol v3, bản sửa 2 (M1): gửi SV1 review trước khi khóa

Ngày 20/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa, chưa có code, chưa chạy gì.** DS2 chưa mở.

Bản này thay bản nháp v3 ngày 19/11 (`mitdb_m1_attack_protocol_v3.json`, SHA `67342cbd…`, commit `699ee1e`). Bản nháp đó chưa được review hay khóa, và được giữ nguyên làm bản ghi. Lý do sửa là tin SV1 ngày 20/11:
- mục 3(6) thêm ba luật cho ρ2;
- mục 3(3) cần thêm phép đo tái định danh theo số nhịp k.

**v3 được viết sau khi đã thấy Π lượt thử.** 9 cặp v2 giữ nguyên làm bản ghi: không chạy lại, không sửa.

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Attack protocol v3 r2 (ứng viên) | `ml/configs/mitdb_m1_attack_protocol_v3_r2.json` | xem `ml/provenance/m1-attack-v3-r2-draft-20261120/SHA256SUMS.txt` |
| Bản nháp v3 r1 (bị thay, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v3.json` | `67342cbd8aa06ab66a3109d9b4bcc9bceb7df659434deb2e10d26ffc48a0d2dd` |
| v2 (đã khóa, không sửa) | `ml/configs/mitdb_m1_attack_protocol_v2.json` | `7a174dd9a8ea43003090c32db63db1ed3eae25e9abba8de07d9ec4f6bba019b0` |
| Tin SV1 ngày 20/11 (**bản chép từ nội dung dán vào phiên làm việc, không phải bản byte của file SV1 gửi**) | `ml/provenance/m1-sv1-evidence-20261120/tra_loi_Ky_Anh_gop_y_ASI_v2_20261120_transcription.txt` | `5a98b20ebf482932c0b1bdcdb01b7f6bb070b9c0aed910ead9b5546ab87832dc` |
| Góp ý của SV3 về ASI bản 2 (19/11) | `docs/sv3_huong_xu_ly_v2_review_message_sv1_20261119.txt` | `66e2cf64b74517fd4f667d52534a027afa7330e08ac115730c6076ce920b3987` |
| Diff r1 → r2 và v2 → r2 | `ml/provenance/m1-attack-v3-r2-draft-20261120/diffs/` | xem `SHA256SUMS.txt` |

## 1. Thay đổi so với bản nháp r1

Các phần a (s9 và logits) và b (B-composite, 21 phép đánh giá, cổng tái lập) giữ nguyên như r1. Riêng phần b có thêm một việc: lưu dự đoán composite để phần d dùng.

### Phần c viết lại: ρ2 và đối chứng s0 + nhiễu

**Hai cấu hình.** Checkpoint A giữ nguyên, nhiễu Gauss được cộng trước khi lượng tử:
- R2[α]: nhiễu N(0, (α·σ_c)²) theo kênh, cộng lên z_s2;
- C0[α]: nhiễu N(0, (α·σ_x)²), cộng lên x rồi gửi ở s0.

σ tính trên DS1 train và ghi SHA trước mọi lần đánh giá có nhiễu. α chỉ dùng để chỉnh từng cấu hình, **không dùng để so hai cấu hình với nhau** (mục 3(6)).

**So ở cùng macro-F1.**
- Có 4 mục tiêu t ∈ {0,99; 0,98; 0,97; 0,95} × F1_A. Mục tiêu cuối chính là ngưỡng 0,5398.
- Với mỗi cấu hình và mỗi mục tiêu: quét α trên lưới thô {0,05 … 4}, rồi chia đôi 8 bước theo log α, chỉ dùng DS1 validation, để tìm α_t lớn nhất còn đạt t.
- Π được tính tại các α_t đó. Như vậy có tối đa 8 điểm riêng tư, mỗi cấu hình ít nhất 4 mức.

**Kẻ tấn công.** Kẻ tấn công biết cơ chế, checkpoint, α và σ. Π lấy theo biến thể mạnh nhất trong ba loại:
- **B-naive:** train trên một lần rút nhiễu;
- **B-adaptive:** train với nhiễu sinh lại theo phân phối đã biết, xoay vòng 5 lần rút đã chuẩn bị sẵn qua các epoch;
- **B-composite-adaptive:** edge tính u_s′ từ tensor có nhiễu, với mọi s′ ∈ {2, 4, 5, 8, 9, 10} sâu hơn điểm nguồn. Kẻ tấn công ở s′ được train trên chính chuỗi đó, có nhiễu.

Mỗi điểm có 7 biến thể (R2) hoặc 8 biến thể (C0), mỗi biến thể 3 seed.

**Luật vào tập hành động, khai trước.** Một cấu hình đạt khi Π ≥ 0,5 và macro-F1 ≥ 0,5398. Khi đó:
- C0 đạt ở α nào đó: **s0 + nhiễu vào tập hành động thay cho s2 + ρ2**, dù R2 cho kết quả gì.
- Chỉ R2 đạt: đường R đạt, s2 + ρ2 vào tập hành động (ASI bản 2, mục 3.3).
- Không cấu hình nào đạt: không thêm hành động. Báo bảng so ở cùng macro-F1 và hai đường cong (macro-F1, Π) làm kết quả âm.

SV1 quyết hai đường R và K vào cuối tuần 13 theo đúng các luật này.

### Phần d mới: tái định danh theo số nhịp k

- Chỉ dùng dự đoán đã lưu, không train. Với mỗi s đo được dưới ρ0, lấy biến thể đang quyết định Π_v3; dòng chính là s0.
- k ∈ {1, 2, 5, 10, 20, 50, 100}. Có hai cách lấy nhịp:
  - **liên tiếp:** khối k nhịp liền nhau, bỏ khối cuối thiếu;
  - **rải rác:** 200 lần rút k nhịp không hoàn lại, mô phỏng chính sách chỉ offload một phần nhịp.
- Bỏ phiếu đa số (hòa thì chọn nhãn nhỏ nhất), tính bacc cân bằng theo bệnh nhân, rồi Adv_k.
- Số này chỉ để thảo luận, không phải Π và không là luật quyết định. Nó đỡ cho câu trong threat model "ngân sách rò rỉ không che danh tính".

### Limitations thêm

Ngân sách rò rỉ (mục 3(3)) có một độ lệch về thước đo:
- Π đo tái định danh, còn asset của ngân sách là nội dung lâm sàng từng nhịp, thứ mà chỉ số tái tạo A1 đo.
- Với số lượt thử, hai cách cho trọng số gần như nhau: ở mọi s < 10, Π ≈ 0,07 và Pearson ≈ 0,99.
- Dù vậy threat model phải nói rõ ngân sách dùng trọng số nào.
- Vì Π là cận trên, 1 − Π là cận dưới của mức rò rỉ mỗi nhịp.

## 2. Câu hỏi cho SV1

Câu "cùng α" của r1 đã có lời đáp trong mục 3(6) ("so ở cùng macro-F1"), nên bỏ.

1. ρ2 giữ checkpoint A cố định, hay fine-tune tail có nhiễu cho từng α? Nếu fine-tune, các op mà tấn công ghép dùng cũng đổi theo.
2. Bốn mục tiêu macro-F1 {0,99; 0,98; 0,97; 0,95} × F1_A, tìm α bằng lưới rồi chia đôi trên DS1 validation: có được không?
3. Kẻ tấn công thích nghi dùng 5 lần rút nhiễu chuẩn bị sẵn cho phần train phía kẻ tấn công: đủ chưa?
4. B-composite và s9/s10 có vào lượt chính thức DS2 không? Bản nháp mặc định là có, theo authorization riêng của lượt đó.
5. Nhờ bạn gửi file gốc của tin 20/11. Bản đang ràng buộc chỉ là bản chép lại.

## 3. Ước lượng thời gian chạy (chưa đo)

| Phần | Khối lượng |
|---|---|
| a, b, d | Vài giờ trong ngày đầu sau khi khóa |
| c, phần tiện ích | Chỉ suy luận trên DS1 validation |
| c, phần riêng tư | Tối đa 8 điểm × 7–8 biến thể × 3 seed, khoảng 180 lần fit |

Ở lượt thử, 9 cặp × (3 seed B + A1) chạy hết khoảng 7 phút. Phần c còn tốn thêm ở phép tính composite trên CPU cho 5 lần rút nhiễu, nên vẫn nằm trong giới hạn 1 tuần.

## 4. Đã làm, đã kiểm, chưa làm

- Đã làm:
  - viết protocol v3 r2 (JSON hợp lệ);
  - kiểm ngưỡng: 19/20 × 11488986689/20219195700 = 218290747091/404383914000 (0,5398);
  - viết diff r1 → r2 và v2 → r2;
  - chép tin SV1 ngày 20/11 vào provenance, kèm ghi chú rõ đây là bản chép.
- Chưa làm:
  - code, test, smoke trên dữ liệu giả;
  - khóa: file khóa do người dùng cung cấp sau khi SV1 review.
- Không chạy tấn công nào, không fit, không mở DS2.
