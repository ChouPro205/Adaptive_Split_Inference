# Kế hoạch riêng cho prose lịch sử — chưa thực hiện

Nguồn inventory chỉ đọc: inventory audit cục bộ ngày 28/10, không đưa vào repo:
`REVIEW.txt`, `history-wording-inventory.json`, `history-prose-bindings.json`,
`history-latest-main-confirmation.json` và `pr41-snapshot.json`.
Audit ngày 28/10 ghi 8 dòng prose cũ trong 5 file ngoài 11 dòng của đợt này.

| Hồ sơ và line tại snapshot đã rà | Hướng xử lý riêng nếu cần công bố trung tính |
|---|---|
| `contracts/sv3_week5_allocation_v2.md`: 5,44 | Raw SHA được pin trong 92 dòng receipts theo inventory; tạo bản trình bày/version mới dẫn nguồn, giữ contract và approval gốc. |
| `docs/sv3_ml_week5_report.md`: 126 | Đánh giá bản công bố/version mới cùng chủ tài liệu; không đổi snapshot hoặc gán người thực thi thành Kỳ Anh. |
| `docs/sv3_week5_scope_checklist_2026-10-09_v1.1.md`: 114,211,217 | Được pin trong baseline audit tuần 7; giữ nguyên, tạo bản trình bày mới với source map khi có yêu cầu. |
| `docs/sv3_week7_dependency_checklist.md`: 19 trên `bed2dfc`, 11 trên main audit | Giữ đoạn snapshot cũ trong đợt này; đề xuất phụ lục/version công bố mới và dẫn revision nguồn. |
| `ml/docs/week5_technical_20261009.md`: 194 | Được pin trong baseline audit tuần 7; giữ nguyên bản kỹ thuật và tạo bản trình bày mới nếu cần. |

Không sửa các file trên ngoài đúng hai dòng allowlisted của checklist trong
đợt này. Không thay attribution Cline trong lịch sử. Giữ `.codex`, PATH/cwd,
tool IDs trong receipts, metadata người ghi, archived AGENTS, manifest, logs,
snapshot PR body và Git history: chúng ghi nguồn gốc thực thi, không phải
prose quảng bá cần xóa. `recorded_by` trong approval tuần 5 và
`expected_approval` trong `week5_registry_acceptance_v3.py` giữ nguyên; không
đổi hash hoặc gate để làm đẹp trạng thái. Bản trình bày mới phải dẫn bản gốc,
revision và evidence, tách nội dung biên tập khỏi nguồn thực thi đã frozen.

Việc chỉnh cách diễn đạt không thay thế khai báo AI theo chính sách nơi nộp bài.
