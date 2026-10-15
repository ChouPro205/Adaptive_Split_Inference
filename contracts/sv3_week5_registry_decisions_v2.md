# PR25 F2 — quyết định allocation còn chờ

CURRENT WEEK=5; REVIEW_STATUS=PENDING; TECHNICAL_STATUS=BLOCKED.
Châu phê duyệt allocation; Châu/Trung xác nhận cùng revision hai phía.
Registry triển khai `sv3_week5_ml_registry_v1.json` tiếp tục giữ ID null.

| Quyết định | Giá trị để xác nhận | Người xác nhận | Trạng thái |
|---|---|---|---|
| Model/version/checkpoint | `mitdb_week2_cnn_v1` / cùng version / `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` | Châu, Trung | PENDING |
| model_profile_id | Proposal `0x4D495401` = 1296651265 | Châu allocation; Trung namespace | PENDING; chưa áp |
| Mapping s→wire ID | Proposal s0..s10 → 256..266; từng hàng tường minh, không lấy test s+1 | Châu, Trung | PENDING |
| key_id | uint32 khác 0; public nhãn của key, không đưa key thật vào repo | Châu, Trung | PENDING |
| Sender scope | sender_ids, key_id, nonce lifecycle/reboot/retry, tuple được phép | Châu, Trung | PENDING |
| Buffer Device | payload thực tối đa 5760 B, C tối đa 64; firmware hiện có quantized[5760], FP16 scale[128] | Châu | PENDING deployment |
| Buffer Edge | payload/channel capacity và scale FP32 LE tối đa 256 B; bộ đệm packet do I1 review riêng | Trung | PENDING |
| Revision chung | revision/registry SHA256; device_revision=edge_revision; bằng chứng namespace ngoài repo | Châu, Trung | PENDING |

I2 32768 B là trần contract. Nó không chứng minh MCU có buffer 32768 B.
Verifier sau approval buộc profile ceiling không vượt capacity hai phía.
Giới hạn thực 5760 B/C64 và quyết định packet/transport không được nhập nhằng.

Đã tìm trên tree PR được pin `a2847117ac285bf16c572a56f48dbe39facd6b08`
và main `cfdfca1025ab5f707b46197b4c5dae868d38d473`: contracts, docs,
ml/configs, device (JSON/Markdown/Python/C/header). Registry FP32
`ml/configs/week3_sv2_interface_review.json` CONFIRMED điểm cắt, không cấp I1 IDs.
Chưa thấy allocation deployment collision trong repo. I2 vectors (`0x10203040`,
split 7; model 2, split 1), P1 `0x575435`/s+1 và interface test 101+7*s là
PUBLIC_TEST_ONLY. Kết quả tìm kiếm không chứng minh namespace ngoài repo không
collision, cũng không phải approval proposal. Không có evidence reviewer chứa
discussion/review được cung cấp để suy ra quyết định bên ngoài.

## Sau quyết định

Chuẩn bị file registry được Châu/Trung duyệt, giữ nguyên model/shape/reference.
Thêm `status=APPROVED`, `revision`, `sender_scope` gồm `sender_ids`, `key_id`,
`nonce_lifecycle`; `buffer_limits` gồm `device` và `edge`, mỗi phía có
`payload_bytes`, `channels`. Điền từng wire ID được cấp, không tự áp proposal.

Approval JSON schema `week5-registry-approval/1` có `decision=APPROVED`,
`approved_by=["Châu","Trung"]`, `registry_sha256`, `revision`,
`device_revision`, `edge_revision`. SHA256 approval phải lấy độc lập từ người
phê duyệt. Verifier kiểm binding đó, mapping/descriptor và toàn bộ 220 real-tail:

```powershell
python -B ml/scripts/verify_week5_registry_v2.py --registry approved-registry.json --approval approval.json --expected-approval-sha256 <SHA256-từ-Châu-Trung> --output ml/provenance/registry-acceptance-new.json
```

Execution vẫn dùng public test key để kiểm toán học; không nghiệm thu key thật,
nonce lifecycle, I1 transport hoặc MCU/DPU deployment. Test fixture approval
trong unit tests được ghi PUBLIC_TEST_ONLY và không phải quyết định allocation.
