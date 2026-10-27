# SV3 tuần 7 — evidence host mới, 28/10/2026

Phạm vi: tái kiểm host trên `dev/ml-sv3`, tiếp nối `4e027b2`, main GitHub
`02ad8c83297d5bee9298342b2bd4e4ff406922ac`, merge `32ea846` giữ bốn commit.
Source/docs được commit trước commands; `git_commit` trong từng receipt định
danh revision thực chạy. Commit evidence sau chỉ bổ sung outputs; không sửa
receipt hay gán pin mới. Kiểm HEAD bàn giao lưu riêng ở
`.cache/week7-host-final-20261028/`.

| Lệnh qua `ml/scripts/log_week7_command.py` | Receipt/output mới |
|---|---|
| `python -B ml/scripts/test_week7_nopeek.py` | [nopeek-normal.command.json](nopeek-normal.command.json), stdout/stderr cùng prefix |
| `python -O -B ml/scripts/test_week7_nopeek.py` | [nopeek-O.command.json](nopeek-O.command.json) |
| `python -B ml/scripts/test_week7_reconcile.py` | [reconcile-normal.command.json](reconcile-normal.command.json) |
| `python -O -B ml/scripts/test_week7_reconcile.py` | [reconcile-O.command.json](reconcile-O.command.json) |
| `python -B ml/scripts/demo_week7_nopeek.py --output <new>/demo.json` | [demo.command.json](demo.command.json), [demo.json](demo.json) |
| `python -B ml/provenance/week7-evaluator-fix-20261026/verify_reference.py` | [reference.command.json](reference.command.json), stdout JSON; không chạy inference |
| `python -B ml/scripts/package_week7_reference.py --output .cache/week7-sv2-handoff-20261028` | [package.command.json](package.command.json), [handoff-receipt.json](handoff-receipt.json) |
| `capture_state.py` | [capture.command.json](capture.command.json), [github-refs.json](github-refs.json), [source-review.json](source-review.json), [environment.json](environment.json), [preservation-before.json](preservation-before.json) |
| `verify_host.py --tested-commit <receipt commit> --output <new>/verification.json` | [verification.json](verification.json); source/log/hash/links/diff/preservation |

[PR snapshot connector](github-prs.json) kiểm PR34 đã merge và PR40 còn mở,
head `8d962095`. [main r2](main-r2.json) pending và [SV1 r2](sv1-r2.json)
CONFIRMED là exact Git blob tại pin ghi trong source-review. Xác nhận Trung→Châu
do SV1 ghi, không comment PR. [Edge summary](edge-summary.json) và
[provenance](edge-provenance.json) thuộc PR40 chưa tích hợp; 5 checksum export
được so với Git blobs, không gọi là đọc raw board hoặc phép chạy mới.

Các tests reconciliation dùng **SYNTHETIC_TEST_ONLY**. Suite NoPeek có kiểm
update trên fixture toán; demo người dùng là forward/backward **không optimizer
step** và không thay checkpoint. Smoke/train dài/attacks/board không chạy.
Warnings nếu có giữ trong stderr; số test, exit và kết quả thực tế xem receipts
và verification. Demo Codex không xác nhận Kỳ Anh học hiểu/đã demo/đã ký ML.

Manifest frozen vẫn SHA
`612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c`, generation
`08e4b42`, không tạo lại. Bằng chứng cũ hai thư mục 26/10 so nguyên raw bytes với
`4e027b2`; baseline source/config/mapping và ignored arrays/artifacts trong phạm
vi inventory được đối chiếu sau thực thi. Không gán audit 2.441 file lịch sử cho
checkout mới. ZIP/reference lớn giữ ignored; gói READY_FOR_TRANSFER_NOT_SENT.

Kết luận DPU full-test: **INCOMPLETE_NO_ACCEPTANCE** cho tới khi Trung cung cấp
25.632 output thật có provenance/artifacts. G2 200/200 đã có là kiểm đường truyền
so cùng backend; 87/100 agreement không là accuracy độc lập. Gate strict
`200*(8393-correct_dpu) < 8544`, ≥8.351 correct và đủ 8.544 mẫu/split.

[Phụ lục hiện hành/owner](../../../docs/sv3_week7_host_update_20261028.md),
[bàn giao Trung](../../../docs/sv3_week7_sv2_handoff_20261028.md),
[runbook GVHD](../../../docs/sv3_week7_demo_guide.md).
