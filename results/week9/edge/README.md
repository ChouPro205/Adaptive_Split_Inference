# SV2 / Edge tuần 9 — hồ sơ đã kiểm

Xuất bản ngày 09/11/2026 từ hai lượt native Windows trên PC SV2,
GW_TRUNG/role=gateway. Mean MQTT một chiều đạt <20 ms trong mô hình affine;
p95, max và mọi mẫu <20 ms chưa đạt. Không gán thành phép đo PC SV1 nhận.
Xem [báo cáo](../../../docs/sv2_edge_week9_report.md) để biết điều kiện và giới hạn.

| File | Nội dung |
|---|---|
| `summary.json` | Thống kê latency, bounds, calibration, queue và giới hạn |
| `latency_samples.csv` | 2402 bản tin: lower/midpoint/upper, ms và phân loại ngưỡng |
| `mqtt_intervals.csv` | Publish/receive interval, scheduler late, queue length và status |
| `provenance.json` | W10/raw inventory SHA, backend/reference và commit công bố |
| `source_versions.json` | SHA mười file thực đo, so byte với source Git |
| `b5_review.json` | Đối chiếu p1/p2/p4 đã đo với manifest/checker Device |
| `figures/mqtt_latency_cdf.png`, `.pdf` | CDF giữ toàn bộ ngoại lệ, trục x log |
| `sha256sum_export.txt` | SHA của tám file do exporter tạo, gồm hai hình |
| `validation.json` | Kiểm tra HOST khi xuất bản, không phải chạy lại phần cứng |

`sha256sum_export.txt` không bao gồm README và `validation.json` được viết sau
export; các file này được version bằng Git. Không sửa receipt cũ để đổi kết luận.
Trong `b5_review.json`, trạng thái pending trong `edge` là trạng thái raw lúc
capture; `device_status` là kết luận checker Device công bố sau đó. P2 vẫn FAIL.

## Đọc và xác minh chỉ từ Git

Từ repo root trên Linux/WSL, không cần board/raw:

```bash
(cd results/week9/edge && sha256sum -c sha256sum_export.txt)
```

Hoặc mở [notebook chỉ đọc](../../../experiments/notebooks/sv2_edge_week9.ipynb).
Notebook kiểm checksum, đọc CSV/JSON và vẽ từ export; không chạy model hay đo lại.

## Tái tạo khi có artifact gốc

Python HOST cần NumPy/Paho; thêm Matplotlib nếu xuất hình. Từ repo root:

```bash
python3 -B edge/export_week9_evidence.py \
  --session VERIFIED_NATIVE_SESSION --output NEW_OUTPUT \
  --energy-session VERIFIED_ENERGY_SESSION --figures
```

Các placeholder là thư mục artifact nhận qua bàn giao nội bộ, không phải dữ
liệu có sẵn trong Git. Bỏ `--energy-session` nếu chỉ tái tạo MQTT. Output phải
chưa tồn tại; exporter chỉ đọc raw, tính lại vào thư mục tạm, kiểm W10 SHA/CRC,
source/payload/clock/backend và so toàn bộ thống kê với bản đã lưu.
Không tái tạo model hoặc đồng hồ bằng dữ liệu giả khi thiếu artifact.

Source công bố tại `54320ff`, source energy tại `948297f9`; commit công bố
không được mô tả là commit acquisition. [Cấu hình](../../../experiments/configs/sv2_edge_week9.json)
giữ seed, topology, đơn vị và giới hạn; artifact lớn/raw/khóa giữ ngoài Git.
