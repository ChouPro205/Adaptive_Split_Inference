# SV2 / Edge tuần 8 — hồ sơ tổng hợp

Dữ liệu dẫn xuất từ các phiên KV260 ngày 26–27/10/2026; exporter không chạy
inference hoặc sửa raw. G2 được SV1 xác nhận PASS qua review do SV2 tiếp nhận
ngày 27/10; registry TC7 còn chờ delta r2 và xác nhận chung.

| File | Nội dung |
|---|---|
| `summary.json` | 212 request, G2 200, bổ sung 21, offline repeat và thống kê timing |
| `requests.csv` | 233 request đã xử lý; có trial, P0/P1, sample index, đơn vị ms |
| `offline.csv` | 100 kết quả KV260 so với nhãn tham chiếu; không phải accuracy độc lập |
| `provenance.json` | Anchor archive, checksum kiểm lại, hash source/model/worker, root receipt |
| `source_versions.json` | Hai SHA service trước/sau patch giữ kết nối |
| `sha256sum_export.txt` | Checksum năm file export ở trên |
| `publication.json`, `validation.json` | Commit chứa hai source service thực đo và kiểm tra HOST khi xuất bản |
| `registry_r2_review.json` | Review kỹ thuật delta r2 và 9 checksum evidence; không sửa registry hay thay xác nhận PR |
| `sv1_review.json` | Kết luận receiver review được SV1 gửi qua SV2; nguồn và giới hạn tách riêng |

`sha256sum_export.txt` kiểm bytes của năm file exporter tạo, không bao gồm README
, ghi nhận receiver review, publication, validation và registry review. Không viết lại receipt lịch sử để cập nhật trạng thái.
SV1 review không thay raw; report/PR Device và delta r2 đã nhận qua PR39 trong lần fetch cuối, vẫn chờ xác nhận chính thức.

## Tái tạo từ raw cục bộ

Python HOST có NumPy, từ repo root; thay `NEW_OUTPUT` bằng thư mục chưa tồn tại:

```bash
python -B edge/export_week8_evidence.py \
  --session edge/build_vai25/ket_qua_hien_tai/week8/g2 --output NEW_OUTPUT
```

Exporter pin NPZ và ba archive bằng SHA-256, đối chiếu extracted bytes với
archive/ZIP, kiểm result inventories, mẫu/q/scale/logits/sequence/backend/source.
Không ghi đè output. Raw, NPZ, model, binary, btsnoop, ZIP và khóa không đưa vào Git.
Nhận archive gốc qua kênh bàn giao nội bộ đã thống nhất, giữ checksum trong provenance;
checkout source không tự cung cấp đầy đủ raw để chạy lại exporter hoặc DPU.

Trên checkout chỉ có export, kiểm bằng Python/sha256sum tại thư mục này hoặc mở
[notebook chỉ đọc](../../../experiments/notebooks/sv2_edge_week8.ipynb).
Xem [báo cáo](../../../docs/sv2_edge_week8_report.md) để phân biệt G2 bit-match,
87/100 agreement với reference, thông số link do Device xác nhận và TC7 còn chờ.
