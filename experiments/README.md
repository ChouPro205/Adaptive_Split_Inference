# Experiments

Nơi lưu cấu hình thí nghiệm, metadata, dữ liệu đo đã xử lý và kết quả có thể tái lập. Không commit dữ liệu thô hoặc dataset lớn.

## SV2 tuần 5–6

Cấu hình thực thi: [configs/sv2_edge_week6.json](configs/sv2_edge_week6.json).
Notebook chỉ đọc tóm tắt đã kiểm checksum: [sv2_edge_week5_week6.ipynb](notebooks/sv2_edge_week5_week6.ipynb).
Các số tổng hợp nằm tại `results/week5/edge` và `results/week6/edge`; raw giữ cục bộ, không di chuyển evidence gốc.

## SV2 tuần 7

[Cấu hình file pipeline và socket smoke](configs/sv2_edge_week7.json),
[notebook chỉ đọc](notebooks/sv2_edge_week7.ipynb),
[hồ sơ SV2](../results/week7/edge/README.md) và
[báo cáo](../docs/sv2_edge_week7_report.md). Không dùng notebook để chạy lại model.

## SV2 tuần 8

[Cấu hình đã chạy](configs/sv2_edge_week8.json),
[notebook chỉ đọc](notebooks/sv2_edge_week8.ipynb),
[hồ sơ](../results/week8/edge/README.md), [báo cáo](../docs/sv2_edge_week8_report.md).
Notebook đọc export Git, không cần raw/key/board và không chạy thí nghiệm.

## SV2 tuần 9

[Cấu hình](configs/sv2_edge_week9.json), [CSV λ(t) và backend pins](configs/sv2_edge_week9/),
[notebook chỉ đọc](notebooks/sv2_edge_week9.ipynb),
[hồ sơ](../results/week9/edge/README.md), [báo cáo](../docs/sv2_edge_week9_report.md).
Notebook kiểm checksum rồi đọc bảng Git; không cần board, NPZ hay gói W10.
Midpoint/biên và ngoại lệ đều được giữ; mean đạt không có nghĩa p95/max đạt.

Nếu muốn xem bằng JupyterLab, dùng kernel PC/WSL có NumPy/Matplotlib; không cài
lên KV260. Tại repo root, trong môi trường Jupyter riêng đã chuẩn bị:

```bash
python -m jupyterlab --notebook-dir=. --port=8889
```

Giữ terminal server hoạt động, mở URL `http://localhost:8889/lab?...` được in
trong terminal bằng browser; không chia sẻ token. Trong file browser mở
`experiments/notebooks/sv2_edge_week9.ipynb`, chọn kernel Python của môi trường
đó, chạy từng ô bằng Shift+Enter. Các ô chỉ đọc/hiển thị, không gọi inference
hoặc tạo lượt đo. Template không lưu output; nếu muốn lưu kết quả hiển thị,
dùng Save As sang thư mục làm việc cục bộ bị ignore. Việc xem notebook tùy chọn,
không phải điều kiện của báo cáo hoặc W10.
