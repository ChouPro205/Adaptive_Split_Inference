# Báo cáo SV2/Edge tuần 5 — full-tail CPU/DPU trên KV260

Ngày lập báo cáo: 23/10/2026. Kết quả thiết bị ngày 22/10/2026.

## 1. Mục tiêu và kết quả

Đã thực thi đủ **10 tail s0…s9 × 20 golden = 200 case** trên KV260 bằng C++
root `vitis::ai::GraphRunner`, bao gồm các phần CPU/PS và DPU. Cả 10 graph có
phân vùng CPU và DPU; không gọi là all-DPU. s10 là empty-tail, không có model.

Trạng thái phần mềm gốc: `EXECUTION_COMPLETE_ACCEPTANCE_PENDING`;
`full_10_tail_executed=true`, `approved_golden_scope_pass=false`.
Báo cáo ghi nhận execution; không tự chuyển trạng thái số học thành PASS.

## 2. Môi trường và nguồn đầu vào

- KV260: SD-A PetaLinux 2022.1, Vitis AI 2.5, XRT/XIR/VART.
- DPU `DPUCZDX8G_ISA1_B4096`, fingerprint `0x101000016010407`, một core.
- Build: Docker `xilinx/vitis-ai:2.5.0`, conda `vitis-ai-pytorch`; native ARM GCC 11.2.0.
- Package FP32 `mitdb-week3-sv2-fp32-20261001-v1`, manifest
  `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.
- 20 mẫu validation golden đã reuse làm calibration; batch runtime cố định 1.
- Không sửa checkpoint, thứ tự mẫu hoặc preprocessing; output 5 logits N,S,V,F,Q.

## 3. Hiện thực và xử lý lỗi

`edge/build_and_audit_models.py` thay batch shell cũ: calib → export → compile
→ inspect cho từng split, lưu lỗi riêng và không chạy stage phụ thuộc sau lỗi.
`quantize_tail.py` dùng Flatten có trục NCL tường minh, tương thích setter padding
1D của quantizer 2.5 trong tiến trình; bắt buộc output directory riêng.

Runtime `edge/runtime/tail_runner.cpp` tạo runner từ root graph, kiểm shape,
layout NCL/NLC/NC và DPU_ROUND/fix-point, lấy final logits (1,5). Các kernel CPU
Conv1d/MaxPool1d/ReLU thiếu trong image được cung cấp bằng ba thư viện app-local,
không cài đè thư viện hệ thống. Driver kiểm toàn bộ CPU libraries trước chạy;
các lượt lỗi cũ được giữ riêng. Kernel chỉ hỗ trợ thuộc tính ECG đóng băng,
không phải thư viện Conv1d tổng quát.

## 4. Kết quả thực tế

| s | Thực thi | Mẫu | Max abs logits vs FP32 | Khớp lớp FP32 |
|---|---|---:|---:|---:|
| 0 | FULL_TAIL_EXECUTED | 20 | 0.512259603 | 100.0% |
| 1 | FULL_TAIL_EXECUTED | 20 | 0.457110137 | 100.0% |
| 2 | FULL_TAIL_EXECUTED | 20 | 0.538231730 | 100.0% |
| 3 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |
| 4 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |
| 5 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |
| 6 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |
| 7 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |
| 8 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |
| 9 | FULL_TAIL_EXECUTED | 20 | 0.413231730 | 100.0% |

Max abs lấy cực đại trên 20×5 logits mỗi split. Khớp lớp với FP32 không phải
accuracy so với nhãn thật; chưa đo accuracy trên tập test độc lập. Chưa có ngưỡng
INT8 riêng được nạp trong lượt này; sai số không được so với ngưỡng FP32 để tự
kết luận đạt. Chi phí latency/load được đo riêng trong báo cáo tuần 6.

## 5. Bằng chứng và tái kiểm

- [Summary 10 tail](../results/week5/edge/summary.json), [status gốc](../results/week5/edge/status.json).
- [Provenance runtime](../results/week5/edge/provenance.json) và
  [hash từng file nguồn](../results/week5/edge/source_files.json).
- Checksum nguồn trên HOST: **46 file OK**. Inventory nguồn SHA256:
  `90b0dd1b4cdd1e5bc7d014dd95fb159712ce91630b31118a79e7b030198b024c`.
- Logits/comparison/log/source/binary gốc giữ trong kho bằng chứng cục bộ;
  Git chỉ có tóm tắt nhỏ và manifest. Không di chuyển hay sửa artifact gốc.
- Cách kiểm/chạy lại vào output mới: [runtime README](../edge/runtime/README.md).
- Export có kiểm anchor và checksum: `edge/export_weekly_evidence.py --help`;
  [hướng dẫn hồ sơ](../results/week5/edge/README.md).

## 6. Kiểm thử và phần còn lại

Kiểm host ngày 23/10: batch isolation 2 tests; CPU kernels 4 tests; runtime
input/report 5 tests; hai test quantization (Flatten và frozen goldens).
Các kiểm tra này không phải lần chạy lại DPU. Kiểm I1 v2 reference không thay
BLE Device–KV260. Còn riêng numeric acceptance, independent-test accuracy,
service BLE/parser/queue và end-to-end với Device.
