# Kiểm chứng biên tập sau review SV1 — 29/10/2026

Chỉ thay 11 dòng prose trong 8 tài liệu từ revision đã rà
`bed2dfcf86a5d5e323575def5bbbb562f7ee6b51`; không đổi số liệu, thresholds,
sample/split IDs, commands, commit pins, trạng thái hoặc kết luận khoa học.
Kỳ Anh phê duyệt push và đưa bản cập nhật lên PR để review. Việc Kỳ Anh tự
chạy lại, xác nhận ML và demo với GVHD được ghi nhận riêng sau khi thực hiện.

- [Allowlist chính xác câu trước/sau](allowlist.json).
- [Kiểm chứng riêng](verify_editorial.py), [raw preservation trước sửa](preservation-before.json)
  và [receipt biên tập](verification.json). Receipt pin SHA của 8 tài liệu
  trong working tree trước commit; không tự nhận đã kiểm commit chưa tồn tại.
- [Kế hoạch prose cũ](historical-prose-plan.md): chưa sửa các hồ sơ frozen.

Lệnh kiểm chứng mới (output mới, không ghi đè receipt):

```powershell
python -B ml/provenance/week7-editorial-20261029/verify_editorial.py --output .cache/editorial-recheck-20261029.json
```

Kiểm toàn bộ bytes còn lại so với HEAD đã rà bằng allowlist và SHA aggregate
của các file tracked cũ ngoài 8 tài liệu; kiểm riêng source/scripts/configs,
manifests, provenance cũ, baseline/reference/weights/archive cục bộ và receipts
cuối `bed2dfc`. Aggregate là SHA-256 của danh sách đã sort gồm path và raw SHA.
File mới chỉ nằm trong thư mục kiểm chứng này. Nội dung sửa và file mới dùng
UTF-8 không BOM, LF; kiểm links/anchors và `git diff --check`.

Trước khi sửa README `week7-host-20261028`, đã kiểm các reference đường dẫn
và tìm exact raw SHA `23007b7250731bfa7999a8eeda6f3b233a4fef4229f4451314c34a29519a7a41`
trong tracked source/docs/contracts và `.cache`: không có pin SHA trực tiếp.
`verification.json` cũ liệt kê links, không pin bytes README này. Không có lý do
cập nhật receipts/manifests cũ chỉ vì README nằm trong `ml/provenance`.

Giữ nguyên [verifier host lịch sử](../week7-host-20261028/verify_host.py)
và toàn bộ receipts/logs cũ, gồm failed runs. Gate prefix từ `BASE4e027b2`
chứng nhận snapshot trước biên tập; không áp dụng PASS đó cho tài liệu mới,
không bỏ/nới gate, không relabel receipt. Phép kiểm mới đối chiếu chính xác
11 thay đổi được phép với `bed2dfc` và toàn bộ phần còn lại.

Tái sử dụng `.cache/week7-host-final-20261028/`: NoPeek 19/19 thường và `-O`,
reconciliation 18/18 thường và `-O`, demo, reference và verification tại đúng
`bed2dfc`; kiểm lại receipt SHA, log SHA và source binding theo commit đó.
Không chạy lại ML/training/board trong đợt biên tập. Evidence tracked `delivery/`
vẫn thuộc `6326082eba9cdb64c96f95e61d95abab37b40ada`, verifier cũ thuộc
`337a9e7`; các pins lịch sử không chuyển sang revision biên tập.

Main đã kiểm ngày 29/10 là `91827d3d9b7b1914d0330e71c2f9e7514840f802`;
PR40 đã merge tại commit này ngày 28/10. Merge-base của nhánh SV3 và main
vẫn là `02ad8c83297d5bee9298342b2bd4e4ff406922ac`; không đồng bộ main bằng
thay đổi source trong đợt này. Các docs/receipts ghi PR40 còn mở là snapshot
lịch sử. Registry r2 trên main hiện vẫn `PENDING_EDGE_CONFIRMATION`, với
`edge_SV2=PENDING`; không sửa hoặc ký thay registry.

DPU full-test/numeric acceptance vẫn `INCOMPLETE_NO_ACCEPTANCE` theo phạm vi
evidence đã đối soát; gói vẫn `READY_FOR_TRANSFER_NOT_SENT`. Chờ output thật đủ
8.544 mẫu mỗi split s2/s5/s8 và provenance; baseline 8.393/8.544, tối thiểu
8.351 correct, strict drop <0,5 điểm phần trăm. Xác nhận cá nhân/GVHD vẫn
`NOT_ATTESTED`. Không tự xác nhận thay owner; không merge hoặc bật auto-merge.
