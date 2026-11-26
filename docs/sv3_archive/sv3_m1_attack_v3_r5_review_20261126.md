# Attack protocol v3, bản sửa 5 (M1): ba chỗ sửa trước khi khóa

Ngày 26/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa, chưa có code, chưa chạy gì.** DS2 chưa mở.

SV1 đồng ý nội dung r4 (`mitdb_m1_attack_protocol_v3_r4.json`, SHA `7b2b1271…`, commit `1fd830f`) và yêu cầu sửa ba chỗ thành r5 (tin 26/11, mục 2). SV1 hẹn: nếu diff r4 → r5 chỉ gồm ba chỗ này, cộng `changes_from_revision_4` và `supersedes_draft`, thì xác nhận trong ngày và khóa r5 luôn. r1–r4 và v2 đã khóa giữ nguyên.

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Attack protocol v3 r5 (ứng viên) | `ml/configs/mitdb_m1_attack_protocol_v3_r5.json` | xem `ml/provenance/m1-attack-v3-r5-draft-20261126/SHA256SUMS.txt` |
| r4 (không sửa) | `ml/configs/mitdb_m1_attack_protocol_v3_r4.json` | `7b2b1271c292ca9003dfb5e6e2980d032f3af371dee289e41967bb48d5675200` |
| Tin SV1 ngày 26/11 | `ml/provenance/m1-sv1-evidence-20261126/tra_loi_Ky_Anh_r4_20261126.txt` | `eafcebf68feb42a44d1981d4d1b7094f412b82610880013601e2ccf01fc84489` |
| Diff r4 → r5 và v2 → r5 | `ml/provenance/m1-attack-v3-r5-draft-20261126/diffs/` | xem `SHA256SUMS.txt` |

## 1. Các khóa JSON thay đổi giữa r4 và r5

So theo khóa (không theo dòng):

| Thay đổi | Khóa | Nội dung |
|---|---|---|
| Sửa | `revision` | 4 → 5 |
| Sửa | `supersedes_draft.*` | trỏ tới r4 (SHA `7b2b1271…`, commit `1fd830f`) |
| Thêm | `changes_from_revision_4` | danh sách ba chỗ sửa, cùng lời đáp của SV1 cho 4 câu của r4 |
| Sửa | `part_c….action_set_rules_declared_before_run.DS2_confirmation` | (a) cổng macro-F1 trên DS2 là 19/20 × macro-F1_DS2(A, FP32), mẫu số từ lượt chất lượng 10/12, tính bằng Fraction, metric fixed4, báo kèm số tuyệt đối và CI95; Π, Π_k10 giữ nguyên. (b) "cùng kẻ tấn công" nghĩa là cùng công thức (biến thể, kiến trúc, thiết lập train, seed, cách gộp, α chọn trên DS1) nhưng train lại trên phần attacker-train của 21 bệnh nhân DS2 |
| Thêm | `part_c….noise_generator.DS2` | (c) part_index 4 (utility DS2), 5 (attacker-validation DS2), 6 (test DS2), 7 (nhiễu train sinh mới mỗi epoch trên DS2) |
| Thêm | `official_DS2_privacy_round.DS2_macro_F1_rule` | mọi cổng macro-F1 trên DS2 tính tương đối theo A trên DS2, cho mọi hành động và mọi đường chạy |

Không khóa nào khác đổi.

## 2. Lời đáp 4 câu của r4

Theo đúng yêu cầu "diff chỉ gồm ba chỗ", danh sách `questions_for_SV1` để nguyên như r4. Lời đáp được ghi trong `changes_from_revision_4` và sẽ được làm khi viết code:
1. S0c có trong lượt DS2 chất lượng 10/12 (FP32 trên CPU). Script phải tái tạo S0c v1 trùng bit trên 20 nhịp golden và trên 9.523 nhịp DS1 validation (macro-F1 0,568057), và xuất macro-F1 DS2 của A FP32 làm mẫu số.
2. Giữ kẻ tấn công sạch ρ0 ở s′ trên đường ghép.
3. Nhiễu sinh mới theo epoch: run manifest ghi số epoch thực chạy của từng biến thể.
4. Đường ghép GPU khi train, CPU khi đánh giá: ở epoch 1 ghi max |GPU − CPU| của u_s′ trên một batch và tỉ lệ giá trị lượng tử ở s′ bị lệch (chỉ báo).

## 3. Kèm trong cùng đợt

`edge/README.md`: sửa link bàn giao FP32 tuần 3 sang `docs/sv3_archive/sv3_sv2_week3_linux_fp32_handoff.md`, theo đồng ý của Trung; Trung review dòng này.
