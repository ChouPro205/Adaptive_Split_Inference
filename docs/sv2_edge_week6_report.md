# Báo cáo SV2/Edge tuần 6 — profiling tail và thời gian nạp model

Ngày thực thi và lập báo cáo: 23/10/2026. Bằng chứng KV260 đã nhận về HOST.

## 1. Kết quả và phạm vi

Đã đo đủ s0…s9, **50 lượt nạp mới, 5000 lần đo steady-state**, qua root
GraphRunner CPU/PS+DPU. Trạng thái `PROFILE_EXECUTION_COMPLETE_REVIEW_PENDING`;
`full_10_tail_profiled=true`. Chưa có số đo DPU-only, năng lượng, BLE RTT hoặc
throughput server trong hồ sơ này. s10 empty-tail có latency null, không tạo số 0 giả.

Cùng model/input/CPU plugins của tuần 5; driver đối chiếu logits từng lần đo
bit-exact với output runtime tuần 5. Numeric acceptance và accuracy độc lập
không được suy ra từ timing hoặc hồi quy này.

## 2. Cấu hình và phương pháp

- KV260 PetaLinux 2022.1, Vitis AI 2.5, DPU B4096 một core, fingerprint
  `0x101000016010407`; Python board 3.9.9, native GCC 11.2.0.
- Mỗi split: 5 process mới; mỗi process có 1 inference đầu riêng, 20 warm-up,
  100 measured; input duyệt vòng 20 golden validation, batch 1.
- C++ `std::chrono::steady_clock`, đơn vị ms; ghi báo cáo ngoài vùng đo.
- Load = deserialize XIR + tạo root runner + lấy/kiểm tensor. Không gồm đọc NPY,
  process startup, dynamic loader trước main hoặc lần inference đầu.
- Tail total = prepare/layout/quantize + copy/sync input + execute/wait toàn
  root graph + sync/read/dequantize output. Không gồm load, SSH hoặc network.
- Fresh process reload vẫn chịu filesystem cache, không gọi cold SD load.
- CI95 trong JSON dùng Student-t bảo thủ, có giả định độc lập. Đọc thêm CI theo
  mean của 5 lượt; 500 observations không phải 500 mẫu test ECG độc lập.
- Governor/frequency/thermal/loadavg trước và sau được lưu ở profile; không
  ép xung, đổi governor hoặc tắt dịch vụ để làm đẹp số đo.

## 3. Số đo thực tế

Tất cả cột là ms; load và first là mean trên 5 lượt, steady trên 500 observations.

| s | Load mean | First tail mean | Root execute mean | Tail mean | Tail std | Tail p95 |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 94.072462 | 48.992393 | 48.296890 | 48.860473 | 0.117089 | 48.993306 |
| 1 | 84.558142 | 55.623491 | 46.973718 | 55.529234 | 0.092147 | 55.647362 |
| 2 | 73.624433 | 47.014073 | 42.497202 | 46.811305 | 0.098309 | 46.952531 |
| 3 | 66.291967 | 46.677700 | 37.906714 | 46.485816 | 0.110504 | 46.681941 |
| 4 | 57.486744 | 34.671304 | 30.100565 | 34.369950 | 0.098457 | 34.575856 |
| 5 | 51.135889 | 30.906374 | 24.158832 | 30.602407 | 0.081986 | 30.752619 |
| 6 | 44.173876 | 19.238166 | 15.626593 | 18.853804 | 0.058261 | 18.946046 |
| 7 | 39.327191 | 14.482112 | 9.851331 | 14.177441 | 0.069660 | 14.304445 |
| 8 | 29.761897 | 2.461330 | 0.180473 | 2.289066 | 0.048659 | 2.389677 |
| 9 | 27.677013 | 0.383592 | 0.157416 | 0.215778 | 0.014349 | 0.222861 |

`Root execute` đã gồm DPU, CPU fallback và runtime trong vùng execute/wait;
không thể lấy cột này làm thời gian DPU riêng. `Tail mean` thêm chi phí chuẩn bị
và I/O. Lần đầu phải tính load + first nếu cần chi phí có kết quả đầu tiên.
Không cộng latency 10 split làm latency một request: mỗi request chọn một split.

## 4. Source, hồ sơ và cách tái chạy

Source profiler đã dùng trong archive được đưa nguyên bytes vào
`edge/runtime/profile_tail_runner.cpp`, `profile_tail_models.py`,
`build_tail_profiler.sh`. Hash ghi trong profile cho phép đối chiếu với source
được bàn giao; không sửa snapshot đo hoặc checksum nguồn để khớp tên file mới.

- [Profile portable](../results/week6/edge/profile_edge.json), [CSV](../results/week6/edge/timing.csv),
  [status gốc](../results/week6/edge/status.json), [source hashes](../results/week6/edge/source_files.json).
- Archive nhận về SHA256:
  `532eb0a644c9b53c81c1d443939449e490c9274cecb1bd52d7f7752ab7eae773`.
- Kiểm **167 file OK** trong inventory nguồn trước khi export. Profile trong Git
  là bản trích kỹ thuật, có `source_profile_sha256`; không phải byte-copy toàn
  file nguồn chứa đường dẫn máy cá nhân. Raw từng lượt giữ nguyên cục bộ.
- [README tái chạy và giới hạn](../edge/runtime/README.md),
  [notebook chỉ đọc kết quả](../experiments/notebooks/sv2_edge_week5_week6.ipynb),
  [cấu hình phiên đo](../experiments/configs/sv2_edge_week6.json).

## 5. Kiểm thử và việc tiếp theo

Validator/statistics profiler 5/5 tests trên host; input/runtime 5/5; CPU kernel
4/4; batch 2/2 và hai test quantization trên golden. I1 v2 reference 23/23.
Đây là kiểm phần mềm, tách khỏi bằng chứng KV260 đã lưu.

D4 mới kiểm `vaitrace --help`, chưa có trace để tách riêng DPU. Tuần 7 cần
triển khai nhận packet từ file/Device, parser, adapter và backend, sau đó phối
hợp SV1 thử BLE central KV260 (echo trước inference). Log Device/laptop và
stub Edge của thành viên khác không thay bằng chứng KV260 thật. Không đổi
phạm vi hoặc đánh dấu nghiệm thu nhóm từ việc tạo báo cáo/commit.
