# Công bố SV3 tuần 8 để review

Gói công bố ngày 30/10/2026: runner/tests/config, 54 run hoàn tất (386 epoch),
metrics, source snapshots, candidate lock và figures. Chỉ review kết quả validation.
Checkpoint vẫn `EXPERIMENT_ONLY_NOT_APPROVED`; chưa đánh giá test, chưa chứng minh privacy.

## Nguồn và bảo toàn

Study chạy tại HEAD nền `d851e8621ee35e3e5da6451ca9c229094d147780`, runner SHA
`b3f505a3d1b7e0ba0fccd2af73d9592f69f67555d1cac377b8fe3a64b99c01fa`.
Các receipts/tests/pilot giữ nguyên bytes/pins theo source hashes thực chạy;
commit công bố không phải commit đã dùng huấn luyện. Snapshot main đã kiểm trực tiếp
`020218418b592c3eed36dbb961e2ee2e38cf72d0` đã merge PR42; nhánh công bố `dev/ml-sv3`.

[Báo cáo gốc](study-report-before-publication.md.txt) giữ bytes/hash trước khi thêm
hướng dẫn công bố và tham chiếu majority-class vào báo cáo hiện hành. Các package
inventories cũ vẫn chứa hash báo cáo gốc; đối chiếu báo cáo đó qua archive, không
relabel receipt cũ thành receipt đã chạy trên commit công bố.

`manifest.json` ràng buộc bytes của gói Git và bản nén IDs. `omitted-local-evidence.json`
ghi hash các mục không chọn: attempt v1 bị ngắt, inventory máy cục bộ, stale lock
và một số log lỗi có đường dẫn cá nhân. Các mục đó giữ nguyên tại nguồn, không
thay bằng log mới. Một receipt cũ nhắc file local-only không có nghĩa file đó có trong Git.

## Kiểm gói sau checkout

Từ repo root, dùng Python 3.11 cho bước nhẹ không cần checkpoint hoặc GPU:

```text
python -B ml/provenance/week8-publication-20261030/verify_publication.py
```

Danh sách 81.094 train/15.388 validation IDs được gzip lossless, không chứa ECG arrays.
Khôi phục đúng bytes để dùng các verifier gốc (không ghi đè nếu nội dung khác):

```text
python -B ml/provenance/week8-publication-20261030/verify_publication.py --hydrate-ids
```

Checkpoint, dữ liệu ECG, baseline và các gói model frozen không đưa vào Git.
Hydrate từ nguồn đã xác thực theo manifest/hashes hiện có, không tự dựng lại dữ liệu
hoặc relabel checkpoint. Khi checkpoint theo `candidate-lock.json` và 54 run đã có
ở đúng artifact root, kiểm full checkpoint bằng môi trường PyTorch của dự án:

```text
python -B ml/provenance/week8-publication-20261030/verify_publication.py --hydrate-ids --full
```

`--full` đọc checkpoint trên CPU và đối soát metadata/metrics/history; không train,
không chạy inference test. Repo Git một mình không phải archive tự chứa toàn bộ weights/data.

SVG do renderer tạo và receipts/results giữ nguyên raw bytes qua quy tắc Git attributes
riêng của tuần 8. SVG dùng binary diff để không sửa whitespace trong vector đã hash;
source/config/docs vẫn được kiểm whitespace thông thường.

## Kiểm chứng và giới hạn

[Review độc lập](independent-review.json): kiểm lại 54 run, 386 epoch, source/hash,
checkpoint/history, 3.508 file lịch sử và 301 file của 52 run đã hoàn tất khi tiếp nhận.
CSV mean/sample SD được tính độc lập; 11/11 tests tổng hợp thường và 11/11 `-O` PASS.
Training tests/pilot cũ được tái sử dụng theo source hashes; không chạy lại grid khi công bố.

Ba candidate theo mean validation CE thấp nhất là s2/lambda5, s5/lambda2, s8/lambda2;
giữ cả ba seed. Accuracy mean đều dưới majority-N 84,5009%; recall S rất thấp,
F/Q bằng 0. Không xem candidate lock như duyệt triển khai hoặc bằng chứng privacy.
Không merge hoặc bật auto-merge; owner/GVHD acceptance được ghi nhận riêng.
