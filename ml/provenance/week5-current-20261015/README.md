# Receipt tuần 5 cho source hiện tại (15/10/2026)

Receipt của PR25 chứng nhận snapshot `6e1ae146…` (tree `82de1813…`). Thư mục này
là bộ receipt **mới** cho source sau PR #27 và các sửa đổi SV1 ngày 15/10/2026,
tạo bằng logger chính thức `ml/scripts/run_week5_logged_v2.py`.

## Snapshot được chứng nhận

| Mục | Giá trị |
|---|---|
| Commit source | `e50c4717ce2e1b42293637650893c392168c1011` |
| Tree | `83b4c9c90e4ca9b030e50223519d5408c9cbf549` |
| Số file source bị ràng buộc | 199 (mọi file tracked `.py/.c/.h/.ps1`, `contracts/`, `ml/configs/`, `ml/manifests/`) |
| Working tree khi chạy | Sạch |

Commit thêm thư mục này chỉ thêm receipt, kết quả và tài liệu, không đổi file
source nào trong tập trên, nên không tạo tham chiếu vòng. Bất kỳ thay đổi nào sau
này ở tập source đó đều làm `check_receipt()` báo `Tested source drift` hoặc
`Incomplete source provenance` (xem `ml/scripts/test_week5_receipt_scope.py`) và
cần chạy lại receipt.

## Nội dung

| Thư mục/file | Nội dung | Kết quả |
|---|---|---|
| `portable/` | `run_week5_delivery_v2.py`: 13 gate × thường/`-O`, P1 10.000, real 220, accuracy 8.544×11 | 29/29 exit 0; `delivery.json` = BLOCKED đúng thiết kế (registry null-ID lịch sử) |
| `final/` | `approved_real`, `allocation_policy[_O]`, `preflight[_O]`, `sv1_acceptance[_O]` | Exit 0 |
| `final_v3[_O].json` | `verify_week5_delivery_v3.py` trên `final/` và `portable/` | PASS thường và `-O` |
| `extra/` | `test_i1_profile`, `test_week5_receipt_scope`, `edge/tests/test_quantize_tail` (thường/`-O`), parser tuần 5, recheck capture MCU tuần 3/4/5, tamper tuần 4, host C tuần 4, đánh giá theo lớp | Exit 0 |
| `historical-pr25/` | Verifier v3 chạy lại receipt final PR25 trên snapshot `6e1ae146…` dựng lại từ `final-session.zip`, và trên `7ca4160…` | PASS trên `6e1ae146…` (thường/`-O`); FAIL `Incomplete source provenance: quantization` trên `7ca4160…` vì `edge/quantize_tail.py` chưa được ràng buộc |

Output lớn hoặc nhị phân (capture mô phỏng của parser, DLL host C, thư mục tamper)
nằm trong `.cache/` không được commit; receipt tương ứng vẫn ghi lệnh, exit code
và hash log.

## Kiểm lại

Cần checkout ở `D:\HUST\Adaptive_Split_Inference` (receipt ghi đường dẫn tuyệt
đối), tài sản đã hydrate theo `ml/docs/week5_delivery_v2.md`, cùng
`preparation.json` và phiên MCU gốc của SV1:

```powershell
python -B ml/scripts/verify_week5_delivery_v3.py --evidence D:\HUST\Adaptive_Split_Inference\ml\provenance\week5-current-20261015\final --portable D:\HUST\Adaptive_Split_Inference\ml\provenance\week5-current-20261015\portable --registry D:\HUST\Adaptive_Split_Inference\contracts\sv3_week5_approved_registry_v2.json --approval D:\HUST\Adaptive_Split_Inference\contracts\sv3_week5_allocation_approval_v2.json --expected-approval-sha256 a84b5caf89ffb7f8e11be2b308e2d4e1947e4d4f7ed291c47df083d0e15c7a7d --preparation D:/HUST/ASI_week5_prepare/20261009-sv1-prepare01/preparation.json --session D:/HUST/ASI_week5_mcu/20261009-212416 --output <file-mới.json>
```

## Giới hạn

- Kiểm trên Windows, Python 3.11.9, GCC 13.2.0; chưa chạy trên Linux.
- Bằng chứng MCU/DFU/capture là tái sử dụng có xác thực; không nạp, không mở
  COM, không đo mới. Timing, RAM/stack lúc chạy vẫn `NOT_MEASURED`.
- Test Edge dùng stub thay `vai_q_pytorch`; DPU/KV260 chưa chạy.
- Accuracy dùng tail FP32 trên host.
