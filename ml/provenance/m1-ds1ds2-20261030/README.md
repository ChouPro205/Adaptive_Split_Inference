# Hồ sơ kiểm ứng viên M1

Trạng thái: `PASS_CANDIDATE_AUDIT_NOT_LOCKED_NOT_REVIEWED`.

Đọc `docs/sv3_m1_audit_20261030.md` từ repo root. `receipt.json` ghi runtime, exit code, lý do lỗi mong đợi và SHA log cho 25 child commands. `reproducibility.json` phải có 16 giá trị true. Tests thường/-O đều 20/20. Mười tamper case mỗi chế độ phải exit khác 0 và có đúng thông báo semantic, kể cả khi hashes đã cập nhật.

`historical-data-check.json` đối chiếu binary/text frozen trên hai checkout với manifest lịch sử; `preservation.json` kiểm 3.477 file và index/HEAD ban đầu. Inventory đầy đủ before/after giữ local ngoài Git; bản gzip đi kèm local review ZIP, không chép log lịch sử vào tài liệu mới.

`new-files.txt` là allowlist file mới, không phải lệnh stage/commit. `SHA256SUMS.txt` băm raw bytes những file đó, trừ chính checksum; `key-hashes.json` chứa các khóa dữ liệu quan trọng. `pdf-sources.json`, `teacher-sources.json`, `project-source-bindings.json` ghi nguồn/locator/hash. Tất cả không có chữ ký nghiệm thu thay thành viên.

Chạy lại verifier/tests theo báo cáo; producer không ghi đè output. Arrays nằm trong `ml/data/processed/mitdb-ds1ds2-m1-v1-r2`, Git-ignored, không đưa vào gói source nhỏ. Reviewer có raw đúng hash và môi trường dự án có thể rebuild vào đích mới. Hai dòng DS2 chưa có dự đoán, không phải kết quả model.
