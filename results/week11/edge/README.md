# Kết quả Edge tuần 11

Các bảng dưới đây được xuất từ hồ sơ đã lưu. Phạm vi và cách diễn giải
nằm trong [báo cáo tuần 11](../../../docs/sv2_edge_week11_report.md).

| File | Nội dung |
|---|---|
| `summary.json`, `memory.csv` | Stress KV260 và 103 mốc lấy mẫu RAM |
| `burst_summary.json`, `wait_by_q.csv` | Queue KV260, số job và thời gian chờ theo độ sâu q |
| `echo_summary.json`, `echo_checks.csv` | Kiểm full/ACK trên HOST, kích thước và SHA theo ca |
| `package_a_summary.json` | Kết quả T1 CPU, SHA C5 và SHA checkpoint cũ bị từ chối |
| `provenance.json`, `sha256sum_export.txt` | Nguồn, định danh lần đo và checksum của export |

## SV2 TỰ LÀM — kiểm và tái tạo trên HOST

Từ repo root, chạy `(cd results/week11/edge && sha256sum -c sha256sum_export.txt)`.
[Notebook](../../../experiments/notebooks/sv2_edge_week11.ipynb) đọc trực
tiếp các bảng này. Raw log, capture, checkpoint và tensor được giữ cùng hồ
sơ đo gốc. Export CSV chuẩn hóa xuống dòng LF để kiểm được sau checkout.

Khi có các bản capture đã niêm, tái tạo export vào thư mục mới:

```bash
python3 -B edge/export_week11_evidence.py \
  --stress STRESS_ANALYSIS --stress-capture STRESS_CAPTURE \
  --burst BURST_ANALYSIS --burst-capture BURST_CAPTURE \
  --echo ECHO_OUTPUT --t1-receipt T1_PROVENANCE_JSON --t1-log T1_LOG \
  --output NEW_OUTPUT
```

Hai thư mục capture chứa `shell.sha256` và `raw/`. Log T1 có file mã
thoát cùng tên với đuôi `.exit_code.txt`. Export lưu SHA của inventory và
source để đối chiếu với capture gốc.
