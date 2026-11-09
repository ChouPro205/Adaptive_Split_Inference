# Bằng chứng ứng viên M1 v2

Trạng thái: `PASS_CANDIDATE_AUDIT_NOT_LOCKED_NOT_REVIEWED`. Chưa có review độc lập của SV1/SV2 đối với v2, chưa khóa M1/protocol.

- `sv1-response-user-relayed.txt`: đủ chín câu do người dùng chuyển trong phiên; không là chữ ký nghiệm thu hoặc xác nhận SHA.
- `external-review-comparison.json`: SHA raw của review bên ngoài và 18 phép đối chiếu feasibility/zero-F/F-range. Raw nguồn có đường dẫn máy giữ trong audit local ngoài Git.
- `receipt.json`: 31 child argv, exit code và SHA log từ lượt audit cuối; 39 core tests mỗi chế độ, 13 tamper case mỗi chế độ, 19 file tái tạo khớp bytes. Collapse/model utility không được đánh giá trong lượt này.
- `protocol-assets-tests-receipt.json`: bảy kiểm thử assets/protocol mỗi chế độ; giữ các mẫu Q và năm output; không chạy model.
- `protocol-assets-preflight.json`: xác minh candidate protocol/512 IDs dCor/weights/register mà không cấp quyền train.
- `preservation.json`: so before/after 3.527 file có sẵn trong worktree và 339 file local frozen; HEAD/branch/index/status cũ được giữ. Snapshot gốc nằm local; checksum tham chiếu trong receipt.
- `v1-checksums.json`: 49 entries và gói review v1 còn nguyên, không đổi checksum hoặc ghi lại bằng chứng cũ.
- `key-hashes.json`, `new-files.txt`, `SHA256SUMS.txt`: nhận dạng và allowlist toàn bộ hiện vật mới; không tự stage/commit.

Đọc báo cáo `docs/sv3_m1_v2_review_20261030.md` và bảng đối chiếu chín câu. Protocol ứng viên duy nhất là `ml/configs/mitdb_m1_protocol_candidate_v2.json`. Quy tắc B đang là giả định chờ xác nhận; không tự thêm điều kiện C. Các giá trị LR/epoch/seed/trial budget là đề xuất cho review, không phải thông số đã duyệt.

Arrays tại `ml/data/processed/mitdb-ds1ds2-m1-v2` bị Git ignore. CSV gzip chứa đầy đủ 33.649 tổ hợp. Reviewer chạy verifier/tests chỉ đọc; muốn build lại phải dùng đích mới, không ghi đè các output đã có. Dữ liệu, nguồn và hồ sơ v1/r2 giữ nguyên.
