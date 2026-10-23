# SV2 / Edge — Vitis AI 2.5

Luồng hiện tại dùng Docker `xilinx/vitis-ai:2.5.0` và conda `vitis-ai-pytorch`
để lượng tử hóa, compile và kiểm graph tail ECG trên PC. Runtime mục tiêu của
KV260 là PetaLinux 2022.1 / Vitis AI 2.5. Build thành công chưa chứng minh
full-tail inference hoặc accuracy trên thiết bị.

## Các file đang dùng

| File | Chức năng |
|---|---|
| `quantize_tail.py` | Nạp checkpoint, tách tail, dry-run/calibration/export XIR |
| `build_and_audit_models.py` | Audit model có sẵn hoặc batch calib/export/compile 10 split |
| `tests/test_quantize_tail.py` | Kiểm FP32/golden và quy tắc đầu vào; quantizer dùng stub |
| `tests/test_build_and_audit_models.py` | Kiểm cô lập lỗi từng split và lưu exit code |
| [`runtime/`](runtime/README.md) | Source C++ root GraphRunner, build riêng và driver chạy golden trên KV260 |
| `build_vai25/` | Output cục bộ bị Git ignore; mở README ở đây để chọn kết quả |

Script batch của setup cũ đã được loại bỏ. Dùng `build_and_audit_models.py` cho công việc mới.

## Đầu vào và luồng xử lý

```text
checkpoint + golden activations đã xác thực
  → quantize_tail.py: calib → test/export
  → vai_c_xir với KV260 arch của container 2.5
  → XIR inspection + summary + model hashes
```

- Package: `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/`.
- Checkpoint: `model/checkpoint.pt`; script đối chiếu SHA-256 trước khi nạp.
- Batch dùng 20 mẫu trong mỗi `golden/z_sN.npy`, khai báo đúng nguồn `val`.
- Không cần dữ liệu train/raw bên ngoài package cho luồng batch này.
- Arch: `/opt/vitis_ai/compiler/arch/DPUCZDX8G/KV260/arch.json`.
- Giữ nguyên bytes package, sample order và preprocessing.

ONNX bàn giao phục vụ kiểm hợp đồng FP32; không đưa FP32 ONNX trực tiếp vào
`vai_c_xir`. Kiểm trên bộ calibration không thay thế accuracy trên test độc lập.
CLI `quantize_tail.py` bắt buộc chỉ định `--output_dir` để không tạo output ngầm.

## Audit model đã có — không rebuild

Chạy trong container 2.5, checkout mount tại `/workspace/asi`. Lệnh mở container
cần dùng UID/GID của host và Bash entrypoint để tránh tạo file thuộc root.
Các khối dưới chạy phần có thể lỗi trong shell con, giữ terminal mở và lưu log.

```bash
set +e +u
set +o pipefail
export BUILD_ROOT='/workspace/asi/edge/build_vai25/ket_qua_hien_tai'
export REPORT_DIR="$BUILD_ROOT/week4/kiem_tra_model"
ASI_REPORT_INDEX=2
while [ -e "$REPORT_DIR" ]; do
  export REPORT_DIR="$BUILD_ROOT/week4/kiem_tra_model_lan_$ASI_REPORT_INDEX"
  ASI_REPORT_INDEX=$((ASI_REPORT_INDEX + 1))
done
ASI_STEP_LOG="$(mktemp /tmp/asi_edge_audit_XXXXXX.log)"
(
  set -Ee -o pipefail
  source /opt/vitis_ai/conda/etc/profile.d/conda.sh
  conda activate vitis-ai-pytorch
  set -u
  cd /workspace/asi
  python -B edge/build_and_audit_models.py audit --models "$BUILD_ROOT/compiled" --output "$REPORT_DIR"
) 2>&1 | tee "$ASI_STEP_LOG"
ASI_LAST_STATUS=${PIPESTATUS[0]}
printf 'Exit=%s | Log=%s | Report=%s\n' "$ASI_LAST_STATUS" "$ASI_STEP_LOG" "$REPORT_DIR"
```

## Batch mới — calib, export, compile đủ 10 split

Chạy trong cùng container 2.5. Output mới có timestamp; không ghi đè model/log cũ.

```bash
set +e +u
set +o pipefail
export BUILD_ROOT='/workspace/asi/edge/build_vai25/ket_qua_hien_tai'
export REPORT_DIR="$BUILD_ROOT/week4/bien_dich_tu_dong"
ASI_REPORT_INDEX=2
while [ -e "$REPORT_DIR" ]; do
  export REPORT_DIR="$BUILD_ROOT/week4/bien_dich_tu_dong_lan_$ASI_REPORT_INDEX"
  ASI_REPORT_INDEX=$((ASI_REPORT_INDEX + 1))
done
ASI_STEP_LOG="$(mktemp /tmp/asi_edge_batch_XXXXXX.log)"
(
  set -Ee -o pipefail
  source /opt/vitis_ai/conda/etc/profile.d/conda.sh
  conda activate vitis-ai-pytorch
  set -u
  cd /workspace/asi
  python -B edge/build_and_audit_models.py build --output "$REPORT_DIR"
) 2>&1 | tee "$ASI_STEP_LOG"
ASI_LAST_STATUS=${PIPESTATUS[0]}
printf 'Exit=%s | Log=%s | Report=%s\n' "$ASI_LAST_STATUS" "$ASI_STEP_LOG" "$REPORT_DIR"
```

Mã 0 nghĩa tất cả split qua bước host; khác 0 thì đọc summary/log và chưa chạy
bước phụ thuộc. Một split lỗi không chặn split khác; calib/export lỗi thì không
chạy các stage phụ thuộc cho split đó. Công cụ từ chối output đã tồn tại.

## Cách đọc output

| Nội dung | File/thư mục |
|---|---|
| Tổng hợp và trạng thái từng split | `summary.txt`, `summary.csv`, `summary.json` |
| Log gộp từng split | `logs/sN/log_sN.txt` |
| Log từng stage, command, exit code | `logs/sN/{calib,test,compile}.log` |
| Model và metadata compiler riêng từng split | `compiled/sN/` |
| Phân vùng CPU/DPU, operator types, hash | `graph_sN.json` |
| Xác thực package, source hashes, conda, arch | `provenance/` |

`PASS_HOST_ONLY` không phải runtime PASS. `HAS_DPU_AND_CPU` là graph lai;
`DPU_PRESENT_REVIEW_OTHER_NODES` không khẳng định toàn DPU. Trên board còn cần
query arch/fingerprint, xác nhận CPU op và chạy root GraphRunner đúng input,
quantization và logits cuối. Nếu runner chưa có, ghi BLOCKED thay vì inference PASS.

## Kiểm thử trên host

Với Python host và dependency ML phù hợp:

```bash
python -B edge/tests/test_build_and_audit_models.py
python -B edge/tests/test_quantize_tail.py QuantizeTailTests.test_flatten_has_explicit_ncl_axes_for_vai25 QuantizeTailTests.test_split_matches_frozen_goldens
```

Bộ test lượng tử hóa đầy đủ còn có case dùng dữ liệu processed train/val riêng.
Thiếu dữ liệu đó không phải lỗi của luồng batch chỉ dùng package golden.
Test bằng stub không chứng nhận Vitis AI/DPU thực tế.

## Chạy full tail trên KV260

[`runtime/README.md`](runtime/README.md) mô tả runner C++ và driver chạy từng
split hoặc 10 split × 20 golden, lưu final logits, lỗi từng case và provenance.
Đã có hồ sơ native ARM/full-tail KV260 tại báo cáo tuần 5; xem các liên kết kết quả bên dưới. Không dùng binary host trên ARM.
Không truyền criterion thì driver chỉ báo sai khác, chưa kết luận số học PASS.

Kiểm input/layout/rounding và quy tắc báo cáo trên host (cần numpy, GCC):

```bash
python -B edge/tests/test_tail_runtime.py
```

Test này không chạy GraphRunner/DPU và không chứng nhận kết quả thiết bị.

## Tài liệu liên quan

- [Hợp đồng FP32 SV3–SV2](../contracts/sv3_sv2_week3_fp32.md).
- [Bàn giao FP32 Linux](../docs/sv3_sv2_week3_linux_fp32_handoff.md).
- [Mục lục báo cáo](../docs/README.md): các báo cáo SV2 cũ chỉ là hồ sơ lịch sử.

## Báo cáo và hồ sơ SV2 hiện hành

- [Tuần 5](../docs/sv2_edge_week5_report.md): 10 tail ×20 case thực thi.
- [Tuần 6](../docs/sv2_edge_week6_report.md): profiling load/first/steady CPU+DPU.
- [Notebook quan sát](../experiments/notebooks/sv2_edge_week5_week6.ipynb) đọc
  tóm tắt Git và kiểm checksum, không chạy lại thiết bị.
- `export_weekly_evidence.py`: export có anchor/checksum; không ghi đè đầu ra.

Không dùng kết quả calibration-reuse làm accuracy test độc lập hoặc suy ra
nghiệm thu số học từ việc execution/profiling đã đủ.

## SV2 tuần 7 — packet service

[File/TCP bench service](server/week7/README.md) dùng codec I1 v2 và native
[single-input root GraphRunner](runtime/single_input/README.md). Xem
[báo cáo tuần 7](../docs/sv2_edge_week7_report.md),
[kết quả](../results/week7/edge/README.md) và
[notebook chỉ đọc](../experiments/notebooks/sv2_edge_week7.ipynb).
50 sample/split pairs trên 5 ECG validation, numeric review pending; chưa có
BLE Device–KV260 hoặc accuracy test độc lập.
