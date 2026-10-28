# SV3 tuần 7 — evidence host mới, 28/10/2026

Phạm vi: tái kiểm host trên `dev/ml-sv3`, tiếp nối `4e027b2`, main GitHub
`02ad8c83297d5bee9298342b2bd4e4ff406922ac`, merge `32ea846` giữ bốn commit.
Source/docs được commit trước commands; `git_commit` trong từng receipt định
danh revision thực chạy. Commit evidence sau chỉ bổ sung outputs; không sửa
receipt hay gán pin mới. Kiểm HEAD bàn giao lưu riêng ở
`.cache/week7-host-final-20261028/`.

| Lệnh qua `ml/scripts/log_week7_command.py` | Receipt/output mới |
|---|---|
| `python -B ml/scripts/test_week7_nopeek.py` | [nopeek-normal.command.json](delivery/nopeek-normal.command.json), stdout/stderr cùng prefix |
| `python -O -B ml/scripts/test_week7_nopeek.py` | [nopeek-O.command.json](delivery/nopeek-O.command.json) |
| `python -B ml/scripts/test_week7_reconcile.py` | [reconcile-normal.command.json](delivery/reconcile-normal.command.json) |
| `python -O -B ml/scripts/test_week7_reconcile.py` | [reconcile-O.command.json](delivery/reconcile-O.command.json) |
| `python -B ml/scripts/demo_week7_nopeek.py --output <new>/demo.json` | [demo.command.json](delivery/demo.command.json), [demo.json](delivery/demo.json) |
| `python -B ml/provenance/week7-evaluator-fix-20261026/verify_reference.py` | [reference.command.json](delivery/reference.command.json), stdout JSON; không chạy inference |
| `python -B ml/scripts/package_week7_reference.py --output .cache/week7-sv2-handoff-20261028-r1` | [package.command.json](delivery/package.command.json), [handoff-receipt.json](handoff-receipt.json) |
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
và verification. Lượt chạy demo chuẩn bị/kiểm thử không xác nhận Kỳ Anh học hiểu/đã demo/đã ký ML.

Lượt đầu tại `0544558` được giữ nguyên ở thư mục này: reconciliation 18/18
thường/`-O`; NoPeek chỉ chạy 16 tests, lỗi setUpClass vì thiếu
`ml/data/week2/mitdb_baseline/best_checkpoint.pt`. Không gọi hai lượt đó PASS.
[Hydration receipt](hydration.json) ghi bổ sung đúng đường dẫn trước đó không tồn
tại bằng bytes checkpoint frozen trong gói Week 3 (SHA `9b8be076…1f90`), không
sửa file/array đã có. Lượt đầy đủ sau hydration nằm riêng ở `validated/`;
preservation kiểm toàn inventory ban đầu và đúng một file checkpoint mới này.

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

Lượt `validated/` tại `9b08aa7`: NoPeek 19/19 thường và -O, reconciliation
18/18 thường và -O, demo/reference PASS. Packaging đã kiểm member ZIP nhưng
exit 1 trước khi ghi receipt do xử lý relative path. Giữ ZIP/lượt lỗi đó;
source sửa resolve path rồi chạy output mới hậu tố r1 và receipts `delivery/`.

Kết quả delivery tại **`6326082eba9cdb64c96f95e61d95abab37b40ada`**:
NoPeek **19/19 +19/19 -O**, reconciliation **18/18 +18/18 -O**, không skip,
exit 0. Demo/reference/package đều exit 0. Verifier receipt tại `337a9e7` kiểm
pins/logs/source, preservation, links và diff; kết quả [verification.json](verification.json).
ZIP mới 295.225.733 byte, SHA-256
`74775bf3ea3c6fde306e601315c32b8293d3db74fc12975515b503c406fd3429`.
Kiểm HEAD bàn giao trong `.cache/week7-host-final-20261028/` là lượt mới riêng,
không thay git_commit hoặc kết quả các receipts tracked ở đây.

[Source drift so execution tuần 7](source-drift.json): PR38 chỉ đổi thông báo
`samples must be 1`, predicate giữ nguyên. Không gọi audit source-exact cũ là
PASS cho runner blob mới; checksum export PR40 và phần source/tests SV3 được
kiểm theo phạm vi riêng. Verifier kiểm 74 file evidence lịch sử nguyên raw
bytes và 51 artifact/array ban đầu, cộng một checkpoint mới có hydration receipt.
