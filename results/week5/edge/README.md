# Hồ sơ SV2/Edge tuần 5

Thư mục riêng của SV2, không sửa/xuất đè kết quả Device cùng tuần ở thư mục cha.
Đọc [báo cáo](../../../docs/sv2_edge_week5_report.md).

Git giữ summary/profile nhỏ, status gốc, checksum và hash từng file nguồn.
Raw/log/binary/model và archive gốc giữ cục bộ trong output `edge/build_vai25/`,
không commit. `source_files.json` là manifest nguồn, không phải danh sách file
được đóng kèm; chỉ `sha256sum_export.txt` dùng kiểm file Git.

```bash
(cd results/week5/edge && sha256sum -c sha256sum_export.txt)
```

Tái export từ hồ sơ gốc đã xác thực bằng `python3 -B edge/export_weekly_evidence.py --help`.
Cung cấp --week5, --week6, --transfer, hai expected SHA256 độc lập trong báo cáo,
và --output-root mới (ví dụ /tmp/asi_export_review). Công cụ không overwrite.
README này là tài liệu diễn giải thêm sau export, không nằm trong inventory export.
