# Sửa lỗi evaluator tuần 7 — evidence phiên 26–27/10/2026

Cập nhật hồ sơ **27/10/2026, Asia/Saigon**. Giữ tên thư mục theo phiên bắt đầu
26/10; timestamps thực thi UTC nằm nguyên trong command receipts.

Worktree/branch `exports/sv3-week7-reconcile-20261026` /
`sv3/week7-reconcile-20261026` sạch tại đầu phiên, HEAD ban đầu
`0545b470ebccb577baa8e11c1fff1c502f716b17`. Đã đọc AGENTS.md tại root,
không có hướng dẫn bổ sung ở các ancestor áp dụng cho các file được sửa.
Không reset/rebase; giữ nguyên công việc checkout gốc và receipts cũ.

## Source sửa và phạm vi

Implementation được commit trước khi chạy các lệnh evidence:
**`18e74ab198bd444e6cc0ae5eedaa9969132bd935`**.

- `week7_dpu_accuracy.py`: `validate_split_points()` buộc danh sách không rỗng,
  chỉ int s0…s9, không bool/duplicate. `validate_reference()` kiểm đầy đủ inventory
  bắt buộc trước mọi lần đọc samples/logits/output để đánh giá. Các file bắt buộc
  là `samples.csv`, `reference_fp32.npy`, `inputs_s{s}.npy` và
  `reference_wire_fp32tail_s{s}.npy` cho từng split yêu cầu. Kiểm file tồn tại,
  đường dẫn trong thư mục reference và size/SHA như cũ; không tự sửa inventory.
- CLI dùng `ensure_result_coverage()` trước khi ghi report/chọn exit code:
  không chấp nhận results rỗng hoặc thiếu/trùng/sai split yêu cầu. Output report
  bổ sung `requested_split_points`; giữ nguyên input manifest schema và gate
  `200*(correct_fp32-correct_dpu) < 8544`.
- `test_week7_reconcile.py`: fixture thêm inputs có inventory đúng schema.
  **Mọi output trong tests/reproducer là SYNTHETIC_TEST_ONLY**; small input
  stand-ins chỉ kiểm inventory, không được dùng làm tensor nghiệm thu hoặc inference.

## Kết quả thực sự chạy tại implementation nói trên

Môi trường: `C:/Users/Admin/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe`.

| Lệnh | Kết quả | Receipt |
|---|---|---|
| `python -B ml/scripts/test_week7_reconcile.py` | **18/18**, exit 0, không failure/error/skip | `tests-normal.command.json`, stdout/stderr cùng prefix |
| `python -B -O ml/scripts/test_week7_reconcile.py` | **18/18**, exit 0, không failure/error/skip | `tests-O.command.json` |
| `python -B ml/provenance/week7-evaluator-fix-20261026/verify_reference.py` | PASS reference thật hiện có; không tạo lại inputs hoặc chạy model | `existing-reference.command.json`, `reference-validation.json` |
| `python -B ml/provenance/week7-evaluator-fix-20261026/reproduce_regressions.py` | Cả hai lỗi cũ tái hiện, cả hai được bản sửa từ chối; helper exit 0 | `before-after-regressions.command.json`, `regression-reproduction.json` |
| `git diff --check` | exit 0 | `verification.json`; kiểm lại cả diff staged trước commit hồ sơ |

Các command receipts ghi argv/cwd/commit/source SHA/log SHA/exit/timestamps.
Source bất biến trong từng lệnh. Helper và fixture SHA còn có trong output JSON.
Một RuntimeWarning có sẵn xuất hiện khi test cố ý cấp logit `1e100` không biểu
diễn được ở FP32; case vẫn bị phân loại failure đúng, không nới validation.

Tests mới kiểm invalid split list (rỗng, duplicate, ngoài s0…s9, bool, float,
string, null hoặc sai container); CLI empty split+empty rows; CLI boundary không
ghi report nếu thiếu kết quả split; xóa từng trong 6 inventory entries khi có
2 split; bỏ baseline khỏi inventory rồi thay logits; sửa bytes cùng size/giữ hash,
tăng size và mất file cho mọi required entry; path escape; CLI hợp lệ 1/2 split.
Giữ tests missing/failure, tất cả rows vắng, invalid logits, duplicate/unknown
IDs/split, identity/calibration gates, tie và count gate nghiêm ngặt.

## Tái hiện trước/sau bằng source có pin

`reproduce_regressions.py` lấy nguyên blob evaluator từ commit `0545b47`, chạy
CLI trong temporary fixture. Không sửa code lịch sử hoặc data/reference thật.

| Ca SYNTHETIC_TEST_ONLY | CLI source `0545b47` | CLI source `18e74ab` |
|---|---|---|
| split_points=[] và rows=[] | exit 0, report results=[] | exit 1, ValueError nonempty split list; không tạo report |
| Bỏ reference_fp32.npy khỏi inventory rồi thay baseline | exit 0, PASS_ACCURACY_GATE sai | exit 1, missing required inventory entry; không tạo report |

Các artifact test chỉ tồn tại trong temporary directories và được xóa khi kết
thúc fixture. JSON tái hiện ghi rõ scope synthetic, không phải output DPU thật.

## Reference thật còn nguyên và hợp lệ

`.cache/week7-reconcile/accuracy-8544-delivery/` đã qua `validate_reference()` mới:
**8 file /295.210.600 byte**, SHA/size khớp; 8.544 IDs duy nhất, s2/s5/s8.
Đã đọc shape bằng mmap và đếm lại **8.393 correct FP32** từ logits lưu sẵn,
không chạy model hoặc tạo lại hàng trăm MB inputs.

Manifest SHA-256 vẫn là:
`612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c`.
Manifest còn byte-identical với receipt đã giao; generation commit vẫn
`08e4b4259a2757be7b663b88cc1c98607602d266`. Validation mới thuộc `18e74ab`.
Không đổi source pin/hash trong manifest cũ để ép khớp evaluator mới.

54 file evidence cũ dưới `week7-reconcile-20261026/` được so nguyên raw bytes
với Git blobs tại `0545b47`, tất cả giữ nguyên. Năm file tracked đã sửa của
checkout gốc cũng giữ đúng hash trước phiên. Summary: [verification.json](verification.json).

`week7-reconcile-20261026/validate_delivery.py` là validator của snapshot cũ,
bao gồm điều kiện source khớp `08e4b42`. Sau sửa evaluator, không gán gate đó cho
source mới, không sửa validator/receipt cũ để PASS. Lượt mới dùng evidence ở đây.

## Phần nghiệm thu ngoài nhiệm vụ

Chưa có output DPU thật mới trong nhiệm vụ sửa này. Accuracy DPU full-test và
quantizer/compile lineage vẫn chờ Trung/SV2; numeric acceptance theo nhóm,
xác nhận ML của Kỳ Anh, revision nonce/provisioning của Châu/Trung và demo/GVHD
vẫn cần đúng owner. Không chạy training, flash hoặc phần cứng; không đổi
baseline/dataset/golden/contract/registry. Tuần 7 chưa DONE toàn bộ.
