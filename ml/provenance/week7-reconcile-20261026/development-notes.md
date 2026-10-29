# Ghi chú phát triển audit ngày 26/10/2026

Giữ nguyên các lượt chưa hoàn tất; chỉ `delivery-*` là tập lệnh giao cuối tại
commit `08e4b4259a2757be7b663b88cc1c98607602d266`.

- Lượt đầu gọi Python hệ thống thiếu NumPy. Chuyển sang môi trường đã có của
  dự án `ml/.venv/Scripts/python.exe`; không cài hoặc sửa môi trường cũ.
- Khi chụp root diff bằng subprocess Python từ worktree mới, safe.directory
  chỉ áp dụng worktree, nên truy cập Git root bị từ chối. Không đổi Git config;
  chụp hash trực tiếp 5 file sửa mà Git root đã liệt kê trong lệnh đọc trước đó.
- Audit sơ bộ so nhầm hash receipt gốc với receipt export đã bỏ C_build và
  serialize lại JSON. Dừng `ValueError: Receipt hash differs` trước khi ghi
  output. Đọc exporter xác định đúng hai miền hash; sửa audit, không sửa receipt.
  Lượt thử này có traceback trong transcript tool, chưa có command receipt.
- `published-audit-with-inputs.command.json`: exit 1. Verifier tuần 6 yêu cầu
  toàn bộ current source bằng generating source; dừng tại edge/quantize_tail.py
  do main kế thừa source SV2 mới. Giữ gate và log lỗi nguyên trạng. Audit mới
  kiểm inventory immutable cùng 199 historical Git blobs, không gọi verifier
  đó là PASS trên main mới và không sửa matcher/target để giả kết quả.
- `.cpp/.hpp` checkout có CRLF do Git attributes; bytes source đo được khớp Git
  blobs, không khớp raw checkout. Audit ghi cả hai SHA và boolean, không sửa
  source/checksum lịch sử.
- `reconcile-tests` đạt 9/9 nhưng có ResourceWarning vì CSV chưa đóng rõ ràng.
  Đã sửa helper đọc CSV dùng context manager; các lượt `delivery-tests` và
  `delivery-tests-O` kiểm lại source cuối. Không xóa log cũ.
- Các lượt prepare trước `delivery-accuracy-prepare` nằm ở thư mục .cache mới
  riêng, không ghi đè. Chỉ bộ `accuracy-8544-delivery` được chỉ định để tiếp nhận
  output; manifest/source pin rõ trong receipt final.
- Validator hồ sơ lần đầu nối thừa `.txt` vào log basename vốn đã có hậu tố,
  dừng FileNotFoundError trước khi ghi PASS. Đã sửa path ghép và chạy lại; kết
  quả cuối nằm trong delivery-validation.json. Traceback ban đầu giữ ở transcript,
  không có receipt lệnh riêng cho lượt thử helper này.

Không có lần chạy board, flash, training dài, BLE hoặc gửi liên hệ cho người khác.
