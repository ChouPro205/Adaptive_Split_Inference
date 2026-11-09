# SV3 M1 v4: checkpoint baseline C5 đã khóa

Commit `ea04abfcacfb167bbf911ec5fa987aa30b577703` trên `dev/ml-sv3`. File khóa: `ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json`, SHA-256 `6848b08dc1f4f55d7d66a4e36b719d55c92eabf37b0c6edbbfdd6b921047d0bc`.

## Tài sản

- `SV3_M1_V4_GRID_RESULT_20261103.zip` (7.922.636 byte), SHA-256 `5dc88a02077322d976497c7d9bf78b47db43d3d80485c063874349a8088e82a9`. Đây đúng là gói SV1 đã review: 18 checkpoint được chọn, `grid-result.json`, kết quả từng slot, provenance phân tích và `PACKAGE_SHA256SUMS.txt` (564 file). Không có arrays, không có DS2.
- `SV3_M1_V4_GRID_RESULT_20261103.zip.sha256`.

## Checkpoint của cấu hình chọn C5

| Vai trò | Slot | Epoch | SHA-256 |
|---|---|---:|---|
| Triển khai | C5-seed20261101 | 4 | `fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c` |
| Seed | C5-seed20261030 | 17 | `fc60aa7092f81fc53a95a6f7fc83704df51daf631a0f722100ca31e50129408e` |
| Seed | C5-seed20261031 | 23 | `19fe7a4a9136d4f5cbdd7683705b14efd5c7950129d7a6ed9f989111cebf0f8f` |

## Lưu ý

- DS2 chưa mở. DS2 chờ SV2 khóa xmodel s0–s9 (tuần 13), rồi chạy một lượt FP32 và một lượt DPU.
- Chạy lại trên cùng GPU cho checkpoint trùng bit; khác GPU thì ra mô hình khác. Các file checkpoint ở đây là bằng chứng duy nhất của mô hình.
- Kiểm hash và kiểm khóa không phải bằng chứng chất lượng mô hình.

## Kiểm

Giải nén ZIP vào gốc một checkout tại `ea04abf`. Trên Windows nên dùng thư mục có đường dẫn ngắn, vì có đường dẫn sâu.

```
sha256sum -c SV3_M1_V4_GRID_RESULT_20261103.zip.sha256
sha256sum -c PACKAGE_SHA256SUMS.txt
python -B ml/provenance/m1-v4-checkpoint-lock-20261105/verify_checkpoint_lock.py
```
