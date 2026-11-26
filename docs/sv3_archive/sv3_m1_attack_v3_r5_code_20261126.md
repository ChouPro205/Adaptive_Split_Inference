# Attack protocol v3 r5 (M1): khóa và code cho phần a–d

Ngày 26/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái:** r5 đã khóa. Code, test và smoke trên dữ liệu giả đã xong. **Chưa chạy gì trên MITDB**, vì cần file cho phép chạy. DS2 chưa mở.

## 1. Khóa r5

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Protocol r5 | `ml/configs/mitdb_m1_attack_protocol_v3_r5.json` | `9235b795ec53b9d4c79e90cad4f1114c260e05b8070c67a62fc23be656ca82fb` |
| File khóa (commit `3f6a6de`) | `ml/provenance/m1-attack-v3-r5-lock-20261126/m1_attack_v3_r5_protocol_lock.json` | `b3a89cbb07c23ca05671c3d8e95435a2de86d810775e80ec0d077c94d0eafff3` |
| Tin xác nhận của SV1 | `ml/provenance/m1-sv1-evidence-20261126/tra_loi_Ky_Anh_r5_xac_nhan_khoa_20261126.txt` | `54db34d1fa1f69fafa52a92ad471ddbed334afef148ecdd3b06c5c59b63161c2` |

File khóa chỉ khóa định nghĩa: `allow_attack_runs = false`, `allow_DS2 = false`. Trong file có ghi các yêu cầu của SV1 cho run manifest:
- DS2 dùng đúng phương án nhiễu của DS1, chỉ thay part_index 0 bằng 7.
- Ghi số epoch thực chạy của từng biến thể.
- Ở epoch 1, ghi độ lệch GPU − CPU.

## 2. Code

| File | Nội dung |
|---|---|
| `ml/scripts/attack_m1_v3.py` | S0c dạng vector (kiểm trùng bit với mã tham chiếu), phần a (s9, s10, S0c), phần b (27 cặp ghép, cổng tái lập, Π_v3), phần d (gộp k nhịp dưới ρ0), các hàm gộp k nhịp dùng chung với phần c, plan, preflight, cổng cho phép chạy, smoke |
| `ml/scripts/noise_m1_v3.py` | Phần c: tính σ, luồng nhiễu SeedSequence, tìm α theo macro-F1 (lưới thô, chia đôi theo log α 8 bước), các biến thể B_naive, B_adaptive, B_composite_adaptive và A1_adaptive, cùng Π, Π_k10 và tái tạo; smoke; đo thời gian |
| `ml/scripts/test_attack_m1_v3.py` | 34 test, không đọc mảng MITDB |
| `ml/manifests/mitdb-attack-m1-v3/plan-manifest.json` | Plan, xem SHA trong receipt |

Các quy tắc kế thừa v2 không chép lại mà gọi thẳng code v2 trong `attack_m1_v2.py`: thiết lập train, kiến trúc, chia theo thời gian, Π, bootstrap. Code v2 không sửa.

Cách code làm theo protocol:
- **S0c:** cách tính dạng vector phải trùng bit với `s0c_v1_ref.py` trên 20 nhịp golden và trên mọi nhịp DS1 của lượt chạy. Phải trùng ở 6 thứ: giá trị rút gọn, q, scale FP16, giá trị giải lượng tử, x_c và byte Rice. Lệch bất kỳ chỗ nào thì dừng trước khi có số S0c. Kiểm 1.000 nhịp mất khoảng 2 giây, nên 50.995 nhịp mất khoảng 100 giây.
- **Phần b:**
  - Trước mọi số ghép, kẻ tấn công nạp lại phải tái lập đúng từng phần tử dự đoán đã lưu: của lượt thử v2 (file được đối chiếu với receipt `b2861c71`) hoặc của phần a.
  - Đường ghép chạy trên CPU, theo batch khi s′ ≤ 8 và từng nhịp một khi s′ ≥ 9.
  - Test kiểm rằng đường ghép từ x trùng bit với `observed` của v2 ở s2, s5, s9, s10.
- **Gộp k nhịp:**
  - Chế độ liên tiếp bỏ khối cuối thiếu. Chế độ rải rác dùng `SeedSequence([20261120, 4, pair_key, k])` với 200 lần rút cho mỗi bệnh nhân.
  - Ba cách gộp: đa số (hòa thì lấy nhãn nhỏ nhất), mềm (cộng log-xác suất), trung bình (cộng dồn float64 rồi ép về float32, không lượng tử lại ở nguồn).
  - CI95 của chế độ liên tiếp là bootstrap theo khối, 2000 lần lấy lại, seed 20261105. Của chế độ rải rác là phân vị 2,5 và 97,5 trên các lần rút.
  - pair_key: phần d dùng 0–7 (s0c là 0) và ghi trong plan. Phần c bắt đầu từ 8, ghi trong run manifest trước lần rút đầu tiên.
- **Phần c:**
  - Nhiễu sinh mới mỗi epoch cho toàn bộ tập train theo thứ tự hàng cố định.
  - Các mô hình của cùng một điểm train song song theo từng epoch, nên nhiễu mỗi epoch chỉ rút một lần. Test kiểm rằng cách train này cho đúng lịch sử và trọng số như `v2.fit`.
  - Đường ghép khi train chạy trên GPU, khi kiểm và test chạy trên CPU.
  - Mọi α được làm tròn về lưới 1e-6 trước khi dùng, để α luôn khớp với alpha_key.
  - Luồng nhiễu DS2 (part_index 4–7) có khai báo nhưng code từ chối dùng.

## 3. Đã kiểm

Lệnh, mã thoát và log nằm ở `ml/provenance/m1-attack-v3-code-20261126/` (`receipt.json`, `SHA256SUMS.txt`, `logs/`).
- `prepare` thoát với mã 0. `preflight` thoát với mã 0 ở cả chế độ thường và `-O`:
  - số nhịp chia DS1 khớp protocol (50.995 / 1.681 / 24.839 / 24.475);
  - 15 file kết quả ρ0 của lượt thử v2 khớp receipt.
- Test: 34 test v3 cộng 27 test v2, thoát với mã 0 ở cả chế độ thường và `-O`.
- Smoke phần a, b, d (nhịp tổng hợp, checkpoint A):
  - S0c trùng bit trên 20 nhịp golden và 3.200 nhịp tổng hợp;
  - cổng tái lập đạt;
  - chạy lại một cặp ghép và một bảng k nhịp cho kết quả y hệt.
- Smoke phần c:
  - tìm α, chạy một điểm R2 và một điểm C0c;
  - chạy lại điểm C0c cho kết quả y hệt;
  - phương án dự phòng R = 20 chạy được.
- Đo thời gian phần c trên mảng ngẫu nhiên đúng kích thước thật: xem `timing_part_c_random_arrays` trong receipt.

Số của smoke và phép đo thời gian đến từ dữ liệu tổng hợp. Chúng không nói gì về MITDB và không dùng để chọn tham số.

## 4. Đề xuất phương án nhiễu

Theo phép đo thời gian, nhiễu sinh mới mỗi epoch nằm trong trần của nhánh R, nên không cần phương án dự phòng. Phương án này sẽ ghi vào run manifest trước lần fit đầu. Lượt DS2 làm đúng như DS1.

## 5. Còn lại

- File cho phép chạy (`M1_ATTACK_V3_RUN_AUTHORIZATION`): gắn protocol, file khóa, plan và bằng chứng SV1, nêu các phần được chạy, `allow_DS2 = false`. Người dùng cung cấp.
- Script lượt DS2 chất lượng (S0c, macro-F1 DS2 của A FP32): gửi SV1 trước 07/12.
- Kết quả phần a, b, d trên DS1 ngày 06/12; phần c ngày 11/12.
