# SV3 → SV1 Week 4 handoff

**SV3 Week 4 offline: PASS.** Model revision `mitdb_week2_cnn_v1`, epoch 3;
checkpoint SHA-256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Base Git commit `6e9af108b7b0c39d63bc1c8dbbfbf4fcbf89c67e`.

Các path dưới đây tính từ repository root. Canonical `L=10`, `s=0..10` đếm
8 Conv1d + 2 Linear. ReLU theo learned layer trước; Pool theo Conv chẵn trước;
Flatten + Dropout(eval) nằm trong head từ s=9. Không dùng s này trực tiếp để
cấp I1 wire IDs; wire ID 0 vẫn reserved theo contract hiện tại.

| Dữ liệu SV1 cần | Path |
|---|---|
| Canonical authority Week 3 | `ml/configs/week3_sv2_interface_review.json` và `contracts/sv3_sv2_week3_fp32.md` |
| Registry có shape/payload mọi s, JSON | [tensor_profile.json](../results/week4/tensor_profile.json) |
| CSV để ghép t_dev(s) sau này theo cột s | [tensor_profile.csv](../results/week4/tensor_profile.csv) |
| Full graph, attributes, weights/bias mapping | [model_graph.json](../results/week4/model_graph.json) |
| Weights/bias exact FP32 của cả 10 learned layers | `ml/results/week4/weights/{module_path}.{weight,bias}.npy` (20 file) |
| C99 hex-float header toàn model | `ml/results/week4/firmware/head_parameters.h` |
| C99 host compile + kiểm tra 109.653 FP32 bit patterns | [host_c_verification.json](../results/week4/firmware/host_c_verification.json) |
| CSV 20 sample IDs/order đã freeze | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/samples.csv` |
| Inputs đã chuẩn hóa, dùng trực tiếp | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/golden/z_s0.npy` |
| Golden mọi s, 20 mẫu/file | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/golden/z_s0.npy` … `z_s10.npy` |
| Manifest Week 4 và provenance | [manifest.json](../results/week4/manifest.json), [verification.json](../provenance/week4/verification.json) |
| Figure | [PDF](../results/week4/tensor_size_vs_split.pdf) |
| Hướng dẫn hiểu toàn bộ công việc | [Week 4 review](SV3_ML_week4_review.md) |

Inputs và samples ở gói trên byte-identical với `inputs.npy` và `samples.csv`
trong accepted SV1 v2 `mitdb-week3-fp32-20260925-v2`. z_s2 byte-identical với
golden P2 accepted. Đây là gói reference do SV3 tạo, dùng được ngay dù tên gói
có `sv2`; không cần đợi SV2 acceptance. Không chuẩn hóa inputs lần nữa.

Activation: float32 little-endian `<f4`, C-contiguous/C-order; s=0..8 dùng NCL,
s=9..10 dùng NC. `z[i:i+1]` giữ batch N=1 cho sample_index i; không đảo order
CSV 0..19. Conv weights OIK = out-channel, in-channel/groups, kernel; Linear
weights OI = out-feature, in-feature; bias O. Header dùng cùng exact FP32
C99 hex-float convention Week 3. Dùng header toàn model này khi port toàn head.

Payload trong profile là **per inference N=1**. Golden chứa batch 20 để đối
chiếu, không phải payload một inference. Các cột `bytes_int8_estimated` và
`kib_int8_estimated` là **ước lượng lý thuyết numel × 1**, chưa quantize.
Payload không gồm header packet/NPY, scale, stack/workspace hay Flash weights.

Từ repository root, với môi trường hiện tại:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4.py --repo-root . --output-dir ml/results/week4 --expected-manifest-sha256 d8ae119188eade380d86eca0f41fb4a27376c5c674a069192dbea284a945dea1 --compiler C:/msys64/ucrt64/bin/gcc.exe
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week4.py --repo-root . --output-dir ml/results/week4 --expected-manifest-sha256 d8ae119188eade380d86eca0f41fb4a27376c5c674a069192dbea284a945dea1 --compiler C:/msys64/ucrt64/bin/gcc.exe
```

Hai command đã PASS; test tự tái tạo trong thư mục tạm và so 28 file byte-for-byte.
Standalone reproduce vào **thư mục mới**, giữ nguyên thư mục đã nghiệm thu:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/profile_week4.py --repo-root . --output-dir ml/results/week4-repro --compiler C:/msys64/ucrt64/bin/gcc.exe
```

Command standalone mới ở trên là hướng dẫn tái tạo; chưa tạo `week4-repro`
thường trực. Export đã được kiểm thử thực sự qua test trong thư mục tạm.
Không lấy expected manifest hash từ chính thư mục nhận được để tự authenticate;
lấy digest đã chốt ở handoff/provenance tin cậy. Khi export revision mới, digest
được exporter in ra; chỉ dùng nó cho kiểm tra nội bộ artifact mình vừa tạo.

SV1 tự thực hiện `run_head(s)`, port/execution nRF52840, kiểm tra MCU với 20
reference theo contract FP32 hiện tại (max_abs_error **strictly <1e-3**), rồi
đo thiết bị từng s: warm-up ≥20, 100 runs, mean/std/p95; cố định CPU và điều
kiện đo theo tài liệu project. So reference PyTorch của artifact dùng **bitwise**;
không yêu cầu MCU có cùng arithmetic bitwise nếu contract dùng ngưỡng FP32.
Chưa có t_dev(s) Week 4; CSV chỉ có cột s để ghép số đo thực về sau.

**External status:** SV1 Week 3 có capture 20×5 đã recheck PASS; SV1 all-split
Week 4 execution/timing vẫn là công việc SV1. SV2 độc lập xử lý Vitis AI/operator
compatibility, quantization/xmodel và VART/KV260 acceptance. Những gate SV2 đó
còn pending và **không block handoff SV1 hoặc SV3 Week 4 offline**.

Weights/header và các gói binary Week 3 không nằm trong Git theo policy repo.
Nếu chuyển máy, cần chuyển toàn bộ `ml/results/week4/` và hai gói Week 3 được
verifier tham chiếu cùng trusted checkout/environment; Git checkout một mình
không chứa checkpoint/golden/parameter binaries. Không có firmware run_head
hay đo mới trên MCU/KV260 do SV3 thực hiện.
