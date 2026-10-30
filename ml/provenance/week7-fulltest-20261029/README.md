# SV3 tuần 7 — receipt tiếp nhận full-test ngày 29/10/2026

Phạm vi: review output SV2 đã lưu từ KV260 và chạy evaluator accuracy frozen.
Không train, không chạy inference board mới, không sửa contracts/registry hoặc
thay xác nhận cá nhân/owner/GVHD.

- [Báo cáo kết quả và phần còn chờ](../../../docs/sv3_week7_fulltest_review_20261029.md).
- [Evaluation](evaluation.json): evaluator tại source `9b363f023204ead01e43a8103d927dff41182c29`;
  PASS_ACCURACY_GATE cho s2/s5/s8; đủ 8.544 mẫu mỗi split, không missing/failure.
- [Artifact review](artifact-review.json): hashes, raw input/row/runner/log/command
  và lineage quantize → compile → runtime đã kiểm trên dữ liệu nhận.
- [Summary gốc SV2](sv2-summary.json) và [receipt SV2 nhận reference](sv2-reference-receipt.json)
  giữ nguyên bytes và trạng thái lịch sử của chúng.
- [Preservation capture](preservation-before.json): hashes trước sửa, chỉ cho phép
  chèn banner trạng thái vào hai tài liệu; các tracked file khác và asset cũ giữ nguyên.
- [Verifier mới](verify_fulltest_receipt.py): kiểm lại toàn gói, evaluator, exact
  document insertions, source bindings, links, Git ancestry và preservation.

ZIP raw không đưa vào Git. Bản lưu cục bộ bị ignore:
`.cache/week7-fulltest-received-20261029/` gồm `gui_sv3_fulltest.zip`,
`gui_sv3_fulltest.zip.sha256.txt`, `summary.json`.
SHA ZIP `e6f86a848c9d107ea300b9cf26ed07d59e2caf866a7b057b3c3bda7af08fbcf3`.
Khi tái lập, khôi phục đúng các bytes này và reference frozen đã pin, rồi chạy từ
repo root với Python của môi trường ML có sẵn và output directory mới:

```text
python -B ml/provenance/week7-fulltest-20261029/verify_fulltest_receipt.py --output-dir .cache/week7-fulltest-verification-NEW
```

Verifier không thực thi script/binary từ ZIP. Receipt sinh mới ghi checked_head,
verifier SHA và preservation; giữ receipt trước commit cho đúng candidate đã kiểm,
receipt sau commit lưu riêng. Không gán receipts cũ cho HEAD mới.

Source tests NoPeek 19/19 và reconciliation 18/18, thường và `-O`, tái sử dụng tại
`bed2dfcf86a5d5e323575def5bbbb562f7ee6b51` với receipt/log/source hashes đã đối chiếu.
Các verifier host/editorial cũ giữ nguyên để chứng nhận snapshot gốc; banner và
hồ sơ full-test mới được kiểm bằng verifier mới này, không nới gate cũ.

Giữ gate strict drop <0,5 điểm phần trăm; tối thiểu 8.351 correct và đủ mẫu mỗi
split. Không đổi manifest, calibration/test, thresholds, goldens hoặc approval.
PASS accuracy không chứng minh privacy, chất lượng mọi lớp hoặc nghiệm thu nonce.
