# Hồ sơ SV2/Edge tuần 7

[Report](../../../docs/sv2_edge_week7_report.md): file pipeline đủ 50 request trên
KV260, 46 tail CPU+DPU +4 s10 identity; numeric review pending. 50 sample/split
pairs chỉ gồm 5 ECG validation khác nhau, không phải accuracy test độc lập.
Đây là thư mục SV2 riêng; không sửa kết quả SV1 ở thư mục cha.

| File | Nội dung |
|---|---|
| `status.json` | Phạm vi/trạng thái, số vector, sai khác lớn nhất |
| `cases.json` | 100 dòng kết quả HOST/KV260 gắn vector/sample/split và hashes |
| `by_split.csv` | Số vector, khớp lớp và max abs theo backend/split |
| `provenance.json` | Archive/build/model/source và inventory hash gốc |
| `p1_host_A.json`, `p1_host_B.json` | Receipt verifier HOST, loại C_build chứa đường dẫn máy |
| `socket.json` | HOST TCP s10 smoke thành công và lượt lỗi còn giữ |
| `sha256sum_export.txt` | Checksum các file export trong Git |

Từ root repo, kiểm file Git mà không cần model hoặc thiết bị:

```bash
(cd results/week7/edge && sha256sum -c sha256sum_export.txt)
```

`provenance.json` lưu hash các file gốc, không khẳng định raw/binary đã được đóng
kèm Git. Report/notebook/README là tài liệu riêng ngoài inventory export. Raw giữ
nguyên tại kho bằng chứng cục bộ dưới `edge/build_vai25/`. Không dùng inventory
nguồn để kiểm file Git vì đó là hai bộ file khác nhau.

Để tái export khi có archive/package/receipts gốc, từ root repo và môi trường
Python có NumPy, dùng output **mới**:

```bash
python -B edge/export_week7_evidence.py --session <original-local-session> \
  --expected-archive-sha256 ca8bea529211e5890b9abf097c41a13632d9bc32f90b0b57b4a2ad12c8ad69bb \
  --output <new-output-directory>
```

Lệnh chỉ đọc/tái kiểm bằng chứng đã lưu; không gọi model. Exporter kiểm input
native thực tế từ packet, root graph, response bytes và source đã công bố khớp
snapshot thực đo. Thay source phải tạo phiên mới; không sửa provenance lịch sử.
