# SV3 M1 v4: gói A (mốc M2)

Gói A của baseline M1 v4, giao cho SV2 (cc SV1) sau khi SV2 xác nhận calibration ngày 12/11/2026. Biên bản giao: `ml/provenance/m1-v4-package-a-delivery-20261112/delivery.json` trên nhánh `dev/ml-sv3`, ở commit mà tag này trỏ tới.

## Tài sản

- `SV3_M1_V4_PACKAGE_A_20261105.zip` (68.975.743 byte), SHA-256 `0b4294b54d2cb3211564725ad1c636f9d30739d3e705b0f0c2fc33b147e83e29`. Giải nén ra thư mục `m1-v4-package-a-20261105-v1/` gồm 59 file; `manifest.json` có SHA-256 `f005b3ea4e2440186bce4218c537b12f3b54fe734631c56a90c2378748aedf2f` và liệt kê SHA của từng file còn lại.
- `SV3_M1_V4_PACKAGE_A_20261105.zip.sha256`.

Đây đúng là gói dựng ngày 05/11/2026, không sửa byte nào. `manifest.json`, `README.md` và `calibration/rule.json` vẫn ghi "chờ SV2 xác nhận" vì được viết trước khi SV2 xác nhận; biên bản giao ghi lại việc xác nhận đó.

## Nội dung

| Thư mục / file | Nội dung |
|---|---|
| `model/checkpoint.pt` | Checkpoint C5-seed20261101 epoch 4, SHA-256 `fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c`; kèm bản sao file khóa (`6848b08d…`) |
| `model/` | Mã kiến trúc, cấu hình slot, `architecture.json` (điểm cắt, shape, layout của s0–s10), `model_graph.json` |
| `data/normalization.json` | Normalization fit trên train DS1 (`1ae60f3f…`) |
| `calibration/` | 1.000 nhịp train DS1 chọn bằng `np.linspace` → làm tròn → bỏ trùng như `edge/quantize_tail.py`; `z_s0.npy` là input đã chuẩn hóa, `z_s0.npy` … `z_s9.npy` là golden z_s; `samples.csv` là sample ID theo đúng thứ tự |
| `golden/`, `samples.csv` | Bộ kiểm 20 nhịp train DS1: z_s0–z_s10 và `reference_logits.npy` |
| `firmware/head_parameters.h`, `weights/` | Header và tham số FP32 cho bước D1 của SV1 |

Không có DS2: arrays và dự đoán FP32 + INT8/FP16 làm sau khi SV2 khóa xmodel s0–s9 ở tuần 13.

## Đã kiểm trước khi phát hành

CPU, chế độ thường và `-O`: lệnh `verify` của gói qua; dãy chỉ số calibration tính lại theo quy tắc của SV2 khớp; `calibration/z_s0` trùng từng bit với input đã chuẩn hóa; z_s0–z_s9 của 1.000 nhịp và z_s0–z_s10 cùng logits của 20 nhịp tính lại từ checkpoint trùng từng bit. File zip dựng hai lần ra cùng byte.

Các kiểm này xác nhận gói nhất quán và tái tạo được, không phải bằng chứng chất lượng mô hình hay nghiệm thu phần cứng. SV2 gửi receipt (SHA khớp, z_s tính lại khớp golden) trước khi lượng tử và compile.
