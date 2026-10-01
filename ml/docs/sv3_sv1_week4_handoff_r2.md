# SV3 → SV1 Week 4 handoff — revision r2

Revision r2 sửa PR #17 ngày 2026-10-01. Bằng chứng và receipt mới nằm trong
`ml/provenance/week4-r2/`. Output cũ `ml/results/week4/` và gói tuần 3 giữ
nguyên để truy vết; verifier hiện tại nhận schema 2.

**Ba gate riêng:** offline local, checkout chứa bản sửa đã commit, SV1 nhận
bàn giao. Đọc kết quả thực từ `summary.json`, `receiver_checks.json` và
`deliverables.json`; không suy SV1 đã nhận từ ZIP local. Snapshot nhận được
kiểm trong clone mới với source sửa overlay, không dataset, checkpoint duplicate
hoặc DOCX. Gate checkout bản sửa đã commit vẫn pending đến khi commit/rerun.
Local commit được người dùng cho phép ở bước hoàn tất; không push/merge/flash.
Xem `ml/provenance/week4-r2/completion_status.md` và evidence hậu commit.
Chưa có địa chỉ đích/kênh truyền SV1 được cấu hình.

## Gói cần chuyển

ZIP: `ml/artifacts/week4/mitdb-sv1-week4-fp32-20261001-r2.zip`.
Đường dẫn máy tạo:
`C:\Users\Admin\Adaptive_Split_Inference\ml\artifacts\week4\mitdb-sv1-week4-fp32-20261001-r2.zip`.

ZIP giữ đường dẫn tương đối từ repo root, chứa toàn bộ:

| Thành phần | Đường dẫn |
|---|---|
| All-split source authenticated | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/` |
| Checkpoint/source/config | `model/` trong gói all-split |
| Sample IDs/order | `samples.csv` trong gói all-split |
| Input/golden/logits | `golden/z_s0.npy` … `z_s10.npy`, `reference_logits.npy` |
| ONNX opset 13 | `models/tail_0.onnx` … `tail_9.onnx` |
| Output mới | `ml/results/week4-r2/` |
| 20 weights/bias arrays | `ml/results/week4-r2/weights/` |
| C99 full header | `ml/results/week4-r2/firmware/head_parameters.h` |
| Graph/profile/figure/evidence | JSON/CSV/PDF/PNG và manifest trong output r2 |

SHA ZIP, size, inventory và hai anchors phát hành ngoài ZIP trong
`ml/provenance/week4-r2/deliverables.json`. Chuyển receipt qua trusted
checkout/kênh độc lập, không lấy anchor từ manifest vừa nhận. Generated
weights/header/checkpoint/ONNX/ZIP nằm ngoài Git theo policy repo.

Trust anchors r2 đã tạo và kiểm local (phải lấy từ trusted checkout này):

- Week 4 manifest: `940371931c3138da2c8757ee2d847ed1fe22e2504fd790e25509b7f54c00fa67`.
- ZIP: `0ac95f9855484659ea1d8c988dd77d7a4635427169a7bdc8ed1884fef19f1140`.
- ZIP size: 5.658.710 bytes.

## Nhận và kiểm tra

Dùng repo chứa code r2 và environment pin trong requirements. C99 compiler
có thể khác GCC tác giả nhưng vẫn phải compile và kiểm đúng parameter bits.
PowerShell từ repo root:

```powershell
$receipt = Get-Content -Raw ml/provenance/week4-r2/deliverables.json | ConvertFrom-Json
$zip = 'ml/artifacts/week4/mitdb-sv1-week4-fp32-20261001-r2.zip'
if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $receipt.archive_sha256) {
    throw 'ZIP SHA-256 mismatch'
}
# Staging mới trước; không ghi đè gói immutable hiện có.
Expand-Archive -Path $zip -DestinationPath week4-received-staging
# Đối chiếu receipt rồi đặt hai thư mục vào đường dẫn repo như bảng trên.
$anchor = $receipt.week4_manifest_sha256
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4.py --repo-root . --output-dir ml/results/week4-r2 --expected-manifest-sha256 $anchor --compiler gcc
if ($LASTEXITCODE -ne 0) { throw 'Week 4 verifier failed' }
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week4.py --repo-root . --output-dir ml/results/week4-r2 --expected-manifest-sha256 $anchor --compiler gcc
if ($LASTEXITCODE -ne 0) { throw 'Week 4 tests failed' }
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 $receipt.week3_manifest_sha256
if ($LASTEXITCODE -ne 0) { throw 'All-split verifier failed' }
```

SV1 trả ZIP SHA, manifest SHA, exit status/logs và đường dẫn nhận qua kênh nhóm.
Tạo ZIP local không đồng nghĩa đã chuyển/nhận. Reproduce riêng vào thư mục mới:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/profile_week4.py --repo-root . --output-dir ml/results/week4-new-repro --compiler gcc
```

## Chính sách r2

- Source UTF-8 hash `sha256-utf8-lf-v1`: chỉ normalize CRLF/CR → LF, không
  trim. Raw manifest và artifact/binary vẫn raw SHA + size.
- Checkpoint lấy từ gói đã authenticate; không cần duplicate tuần 2.
- `ml/configs/week4_requirement_references.json` lưu hashes DOCX lịch sử;
  DOCX là tham khảo, không phải input tính toán.
- Reproduction so bytes weights/header/graph/profile/PDF/PNG và FP32 bitwise
  golden. Manifest tái tạo verify riêng và so invariant khoa học. Git metadata,
  generation command và compiler provenance có thể khác.
- Evidence GCC tác giả vẫn authenticate. Compiler local chạy thật; count,
  status/flags/target phải đúng và 109.653 parameter bits khớp. Report local
  nằm trong kết quả verifier, không ghi đè evidence tác giả.
- `release_week4.py` từ chối overwrite revision; giữ logs, kiểm snapshot nhận,
  tạo ZIP, kiểm bytes sau giải nén/receipt. Revision tiếp phải chọn ID mới.

## Semantics và phạm vi không đổi

Frozen model `mitdb_week2_cnn_v1`, epoch 3; checkpoint SHA
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Không train/tải dataset, đổi preprocessing hoặc quantize.

Canonical L=10, s=0..10: 8 Conv1d + 2 Linear. ReLU/Pool theo learned layer
trước; s2=P2; Flatten/Dropout(eval) thuộc head từ s9; s10 logits `(1,5)`.
NCL ở s0..8, NC ở s9..10; `<f4`, C-contiguous. Input normalized dùng trực tiếp.
Giữ 20 IDs/order; `z[i:i+1]` cho N=1. Conv weights OIK, Linear OI, bias O.
INT8 profile chỉ ước lượng numel × 1, không có INT8 thật.

SV1 chốt s → I1 wire IDs, port head, kiểm Flash/RAM/DFU, chạy MCU strict FP32
`<1e-3`, rồi đo timing. Không có firmware/timing all-split mới trong sửa PR này.
SV2 Vitis AI/xmodel/VART/KV260 acceptance pending riêng, không chặn SV1 FP32.