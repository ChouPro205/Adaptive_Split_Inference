# Kết quả Edge tuần 10

Xem [báo cáo](../../../docs/sv2_edge_week10_report.md) để đọc phạm vi đo
và trạng thái xác nhận từng lượt. Các bảng là dẫn xuất từ capture đã lưu.

| File | Nội dung |
|---|---|
| `summary.json` | Thống kê offline, first load, warm switch và coverage |
| `warm_switch_samples.csv` | 1.801 quan sát chuyển split, theo ms |
| `lab_summary.json` | Sáu lượt BLE, request, queue, PHY và kết quả kiểm Edge |
| `provenance.json` | SHA receipt, worker/model/plugin và source khi đo |
| `sha256sum_export.txt` | SHA-256 của bốn file dẫn xuất |

Từ repo root, kiểm export bằng `(cd results/week10/edge && sha256sum -c sha256sum_export.txt)`.
[Notebook chỉ đọc](../../../experiments/notebooks/sv2_edge_week10.ipynb) dùng
export này để vẽ lại biểu đồ.

Khi có capture/archives đã bàn giao, xuất kết quả vào thư mục mới trên PC:

```bash
python3 -B edge/export_week10_evidence.py \
  --capture CAPTURE --lab-imports LAB_IMPORTS --output NEW_OUTPUT
```

CAPTURE là hồ sơ benchmark đã giải nén cùng capture_receipt.json.
LAB_IMPORTS chứa thư mục từng lượt và archive/SHA tương ứng. Artifact gốc
và snapshot thực đo được lưu cùng hồ sơ bàn giao. Trạng thái Device/PPK2
được đối chiếu ngoài export Edge.
