# Lưu trữ tài liệu SV3 (`docs/sv3_archive/`)

Ngày 21/11/2026, thư mục `docs/` được dọn để chỉ còn báo cáo tuần của SV3 theo tên `sv3_ml_weekN_report.md`. Các tài liệu ngày lẻ (review, protocol, hồ sơ đối chiếu) được chuyển nguyên byte vào thư mục này. Các file tin nhắn `.txt` được gỡ khỏi cây thư mục; bản gốc vẫn còn trong lịch sử Git.

**Nội dung không đổi.** Mọi file chuyển ở đây có SHA-256 đúng như trước khi chuyển (cột SHA-256 dưới đây, tính trên bytes tại commit `d5c9158`). Các hồ sơ đã ràng buộc file theo đường dẫn cũ (receipt, file khóa, `SHA256SUMS.txt`, protocol, file verification trong `ml/provenance/`) không được sửa. Khi một hồ sơ trỏ tới đường dẫn cũ, tra bảng dưới để tìm đường dẫn mới; SHA-256 trong hồ sơ vẫn kiểm được trên file mới.

**Hai hệ quả đã biết:**

- Liên kết tương đối bên trong các file đã chuyển (ví dụ `../ml/...`) giờ lệch một cấp thư mục. Không sửa để giữ nguyên SHA. Mở đường dẫn đích từ gốc repo, bỏ bớt một `../`.
- Báo cáo tuần 5, 7, 8 có liên kết tới tài liệu đã chuyển; các báo cáo này cũng không sửa vì đã có SHA trong hồ sơ. Liên kết đúng nằm ở mục "Tài liệu chi tiết" của từng báo cáo tuần và trong bảng dưới.

Xem lại một file đã gỡ: `git show d5c9158:<đường dẫn cũ>`.

## 1. Đổi tên báo cáo tuần

| Đường dẫn cũ | Đường dẫn mới | SHA-256 |
|---|---|---|
| `docs/SV3_ML_week1_report.md` | [`docs/sv3_ml_week1_report.md`](../sv3_ml_week1_report.md) | `20a94b1bdaa65d10133b09466a388d5926ff5ee7aeb2c5d15b6282f713b7bbff` |
| `docs/SV3_ML_week2_report.md` | [`docs/sv3_ml_week2_report.md`](../sv3_ml_week2_report.md) | `50b5bbdb83c761e20719ba42e32230867fb2981590a51be553bc293e84963e60` |

## 2. Tài liệu chuyển vào thư mục này

| Đường dẫn cũ | File trong thư mục này | SHA-256 |
|---|---|---|
| `docs/sv3_attack_protocol_threat_model_draft_20261105.md` | [`sv3_attack_protocol_threat_model_draft_20261105.md`](sv3_attack_protocol_threat_model_draft_20261105.md) | `4fa82322b524d3f8d2c0711e9efbc9268c2bd42d68ef54efe491502f1574ad68` |
| `docs/sv3_m1_attack_v2_review_20261113.md` | [`sv3_m1_attack_v2_review_20261113.md`](sv3_m1_attack_v2_review_20261113.md) | `ce083282acc80f3c90e85234c7ff660b6aea6e97d71b9e9f9ce99e727ab74c6f` |
| `docs/sv3_m1_attack_v3_r2_review_20261120.md` | [`sv3_m1_attack_v3_r2_review_20261120.md`](sv3_m1_attack_v3_r2_review_20261120.md) | `24aa67e2ac7a18723ca57ac4a770b43f623744c90c7d4ce7f27a48bffec214e5` |
| `docs/sv3_m1_attack_v3_r3_review_20261121.md` | [`sv3_m1_attack_v3_r3_review_20261121.md`](sv3_m1_attack_v3_r3_review_20261121.md) | `7f3bafee5e07c336d1cf34bc462eba4e90931861e70abdbd0638574938af3d53` |
| `docs/sv3_m1_attack_v3_review_20261119.md` | [`sv3_m1_attack_v3_review_20261119.md`](sv3_m1_attack_v3_review_20261119.md) | `efb482ce012a7e6b30dc7714d1d4800ca9c5293e8a6a3be24a8c2a07f17639f1` |
| `docs/sv3_m1_audit_20261030.md` | [`sv3_m1_audit_20261030.md`](sv3_m1_audit_20261030.md) | `192cc03ee0429878221dc2ed2e4fe5273987b87d5762f822232284c7c6fde5ae` |
| `docs/sv3_m1_nopeek_v1_review_20261105.md` | [`sv3_m1_nopeek_v1_review_20261105.md`](sv3_m1_nopeek_v1_review_20261105.md) | `163fab23f3f28f7dffb170995d9d166eb50eec4bb80a652c451215ee0f4483fa` |
| `docs/sv3_m1_nopeek_v2_review_20261111.md` | [`sv3_m1_nopeek_v2_review_20261111.md`](sv3_m1_nopeek_v2_review_20261111.md) | `3995d291f153e2767fdf2290d7e67c045be2a509263d2e749a948c7397b63fc2` |
| `docs/sv3_m1_sources_20261030.md` | [`sv3_m1_sources_20261030.md`](sv3_m1_sources_20261030.md) | `b37ccf2b4c9c02ec64582df53d6711490650d458cdfc86db9e1bdc90c7c949e9` |
| `docs/sv3_m1_traceability_20261030.md` | [`sv3_m1_traceability_20261030.md`](sv3_m1_traceability_20261030.md) | `056a72041d55b8d73837aec404f80fa00b9515846bc214e12d2c49ac718f017e` |
| `docs/sv3_m1_v2_decisions_20261030.md` | [`sv3_m1_v2_decisions_20261030.md`](sv3_m1_v2_decisions_20261030.md) | `14fd9d8311ec5cc65bf50b7b047e5e8dcf05d4ef3b303a5946dbe3591d8920e1` |
| `docs/sv3_m1_v2_review_20261030.md` | [`sv3_m1_v2_review_20261030.md`](sv3_m1_v2_review_20261030.md) | `e8c4902cdcd321f3d392c2af43c837fc82a11cdd7a268ef99ad7f2dd0e68a929` |
| `docs/sv3_m1_v3_review_20261030.md` | [`sv3_m1_v3_review_20261030.md`](sv3_m1_v3_review_20261030.md) | `0ce3b2a8cb5ddc08e86df1bf6807856d9a5617c7406b99d29a3e3f5829a75e4e` |
| `docs/sv3_m1_v4_grid_result_20261103.md` | [`sv3_m1_v4_grid_result_20261103.md`](sv3_m1_v4_grid_result_20261103.md) | `b676be339321bf32e278d207956c8226027874b02cf9800bde6e92098a0ff15c` |
| `docs/sv3_m1_v4_review_20261103.md` | [`sv3_m1_v4_review_20261103.md`](sv3_m1_v4_review_20261103.md) | `b193d1a917af409f1e3ffbf791c67db1e6905aab803cf352ec586ba3353a2d2c` |
| `docs/sv3_ml_week3_linux_fp32_fix_report.md` | [`sv3_ml_week3_linux_fp32_fix_report.md`](sv3_ml_week3_linux_fp32_fix_report.md) | `649048ac7ec5bfa6032788bd80169a590b52d42b5c1b49bffcf3fc09691c0a46` |
| `docs/sv3_ml_week3_linux_fp32_review_v2_report.md` | [`sv3_ml_week3_linux_fp32_review_v2_report.md`](sv3_ml_week3_linux_fp32_review_v2_report.md) | `78e2c49367bd4b78334de2898b26478dffa2ce3287e05a9ba508520df7a8ffa9` |
| `docs/sv3_related_dcentnet_diff_20261120.md` | [`sv3_related_dcentnet_diff_20261120.md`](sv3_related_dcentnet_diff_20261120.md) | `a7fbd83ea71aaa663153b0ecab17d4eb46f86359492a5d518b68119627fcc669` |
| `docs/sv3_sv2_week3_linux_fp32_handoff.md` | [`sv3_sv2_week3_linux_fp32_handoff.md`](sv3_sv2_week3_linux_fp32_handoff.md) | `8ca6b9d5746acd36cc0e2fae9fe0edb39155b40824f57e96c63f7314ead779a1` |
| `docs/sv3_threat_model_draft_20261120.md` | [`sv3_threat_model_draft_20261120.md`](sv3_threat_model_draft_20261120.md) | `0ab42a6a4233920a484db6ac059204ad5c6e285fdb2dafd302fb48086616d5c9` |
| `docs/sv3_week5_scope_checklist_2026-10-09_v1.1.md` | [`sv3_week5_scope_checklist_2026-10-09_v1.1.md`](sv3_week5_scope_checklist_2026-10-09_v1.1.md) | `7f9fa55f7156c26b58284987e8a4f7d30d216cd19a2df31f0923c212f8a29e49` |
| `docs/sv3_week7_demo_guide.md` | [`sv3_week7_demo_guide.md`](sv3_week7_demo_guide.md) | `fb40b953076520e0b53cfb40f272af9969faa16a16268a4d083638bf314cb9e9` |
| `docs/sv3_week7_dependency_checklist.md` | [`sv3_week7_dependency_checklist.md`](sv3_week7_dependency_checklist.md) | `003b03a156f3c9a3a8576448b4b7a3dc66fec980d6c6b451325595cafbe4b52b` |
| `docs/sv3_week7_fulltest_review_20261029.md` | [`sv3_week7_fulltest_review_20261029.md`](sv3_week7_fulltest_review_20261029.md) | `0e343109dbd77e2e989d5bc9d82f559048601db4e908402a2b2b909ae7aa832d` |
| `docs/sv3_week7_host_update_20261028.md` | [`sv3_week7_host_update_20261028.md`](sv3_week7_host_update_20261028.md) | `3680d1688fcc957f4aee80cc6a5e530525d768d423386c0cedf7bdc2cad62d9b` |
| `docs/sv3_week7_ml_i1v2_confirmation_draft.md` | [`sv3_week7_ml_i1v2_confirmation_draft.md`](sv3_week7_ml_i1v2_confirmation_draft.md) | `b6a157e6b5b3f6b1779ff8991c3716af319e5e9d53657f7143e13dacb5855d09` |
| `docs/sv3_week7_reconciliation_20261026.md` | [`sv3_week7_reconciliation_20261026.md`](sv3_week7_reconciliation_20261026.md) | `86f87b091db9b93f7cb70e383355d6fd50e4814c84cafd8640e6730669430483` |
| `docs/sv3_week7_sv2_handoff_20261028.md` | [`sv3_week7_sv2_handoff_20261028.md`](sv3_week7_sv2_handoff_20261028.md) | `67e7347f495ed4399780ad4f237b8f82bfa67522968240d06fbc6b166dcefb0e` |
| `docs/sv3_week8_protocol_approved_joint_v1.md` | [`sv3_week8_protocol_approved_joint_v1.md`](sv3_week8_protocol_approved_joint_v1.md) | `050c793d351dd7580f6f43659e6cf5c500e7bcbb0ab63e0287ac6388db2d8a1b` |
| `docs/sv3_week8_protocol_v1.md` | [`sv3_week8_protocol_v1.md`](sv3_week8_protocol_v1.md) | `5fedfeda416a2f56ab8b707888308dc5d2415d4054c95129bb8560fb4b1d05fa` |

## 3. Tin nhắn gỡ khỏi cây thư mục

Các tin nhắn này đã gửi cho thành viên nhóm. Bản gốc xem bằng `git show d5c9158:<đường dẫn cũ>`.

| Đường dẫn cũ | SHA-256 |
|---|---|
| `docs/sv3_huong_xu_ly_v2_review_message_sv1_20261119.txt` | `66e2cf64b74517fd4f667d52534a027afa7330e08ac115730c6076ce920b3987` |
| `docs/sv3_m1_attack_v2_trial_message_sv1_20261113.txt` | `12c8c294b5dc5afd56dc748e8df5cbd56ba3ff3ed59567b72706c88a4e2107bc` |
| `docs/sv3_m1_attack_v3_message_sv1_20261119.txt` | `b3b3745d4684a5016d7b3dd11cd82e746e23a1f07affcf37a432747a9421d73b` |
| `docs/sv3_m1_attack_v3_r2_message_sv1_20261120.txt` | `c787c59d5f36ad2a36eff9b6d0e28eddac05d745d70a8585d6de2d03051b830c` |
| `docs/sv3_m1_attack_v3_r3_message_sv1_20261121.txt` | `59e036116718e6d00e0d06074d29601aeb973403ee9156082b204d9077345fdf` |
| `docs/sv3_m1_nopeek_v2_grid_message_sv1_20261112.txt` | `19dff03bc9839c77cfa51dd3ea39634e163c3e2ef3f5e61a94b0f4284a8efd68` |
| `docs/sv3_m1_nopeek_v2_pilot_message_sv1_20261112.txt` | `a1e23a87d326be372b2ebd7696f7827a92bd9c05955f9ee1c73c08ede725ccc7` |
| `docs/sv3_m1_v3_message_sv1_sv2_20261030.txt` | `556057f5eeda515a3da4e0d8d11f07c8d3fa5e824d2a194c1a808d150460b2db` |
| `docs/sv3_m1_v4_grid_message_sv1_20261103.txt` | `2c8a82314ead2aef60a7ee24e801f3b5bb5497989433e4046f45ce651131c3f7` |
| `docs/sv3_m1_v4_message_sv1_20261103.txt` | `0f92d0b05349fc0012d5e5978c4822590a0efbd7e54c7837f1e0de60db9b9381` |
| `docs/sv3_m1_v4_message_sv1_20261103_r2.txt` | `c23e5924327ce1550cb966ea4e234bd0d385993c0674dbc4e82dcc6c5db01d45` |
| `docs/sv3_m1_v4_package_a_message_sv2_20261112.txt` | `e4d88fd8ecd7c48e57b256d2c22d9e24fd5b69014dd15e0de5fa565ced96c30e` |
| `docs/sv3_review_after_trial_message_sv1_20261114.txt` | `9061adbbaf7aa8f0cab5bf6cef9b0fbad90662c6a9c97671b5e8c63c8ebe991f` |
