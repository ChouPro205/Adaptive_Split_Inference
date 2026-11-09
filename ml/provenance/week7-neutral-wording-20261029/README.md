# Biên tập cách trình bày review/demo SV3 ngày 29/10/2026

Phạm vi là public prose trong báo cáo, checklist, biểu mẫu và runbook của PR42.
Cách diễn đạt tập trung vào kết quả kỹ thuật và quy trình ghi nhận review/demo.
Vai trò phụ trách giữ nguyên; không thêm chữ ký hoặc kết luận đã thực hiện.

- [Allowlist](allowlist.json) ghi hash khối gốc và câu thay thế, không sao chép
  nội dung cũ vào receipt mới. Base `1fa21ba1f2da671b837d8e28cbb4863b6c6be9b8`.
- [Preservation capture](preservation-before.json) bảo vệ tracked file ngoài
  allowlist, source ML, manifests, evidence lịch sử và các asset cục bộ.
- [Verifier](verify_neutral_wording.py) tái dựng chính xác từng tài liệu từ base
  và allowlist; kiểm links, UTF-8/LF, diff và các source/receipt bindings.

Tests NoPeek 19/19 và reconciliation 18/18, thường và `-O`, tái sử dụng theo
source/receipt/log SHA tại `bed2dfcf86a5d5e323575def5bbbb562f7ee6b51`.
Full-test s2/s5/s8 tái sử dụng [evaluation đã kiểm](../week7-fulltest-20261029/evaluation.json)
tại source `9b363f023204ead01e43a8103d927dff41182c29`: đủ mẫu, PASS_ACCURACY_GATE.
Không chạy lại tests, inference board hoặc training chỉ để biên tập tài liệu.

Receipts/logs, machine statuses, approvals, contracts/registry, manifest, goldens,
weights và thresholds giữ nguyên. Các verifier cũ chứng nhận snapshot gốc; phép
kiểm mới này chứng nhận đúng delta biên tập, không nới gate hoặc relabel receipt.
Receipt trước commit và sau commit lưu riêng, giữ nguyên tested commit của các
bằng chứng tái sử dụng.

Chạy từ repo root bằng môi trường Python có sẵn, chọn output mới:

```text
python -B ml/provenance/week7-neutral-wording-20261029/verify_neutral_wording.py --output .cache/week7-neutral-wording-NEW.json
```

[Hồ sơ full-test và bước thiết kế thí nghiệm tuần 8](../../../docs/sv3_week7_fulltest_review_20261029.md)
ghi tiêu chí chuyển bước. Train dài chỉ bắt đầu sau khi chốt cấu hình và quy tắc
chọn checkpoint theo validation, giữ test frozen cho đánh giá cuối.
