# Báo cáo SV2/Edge tuần 7 — packet I1 v2 từ file đến tail trên KV260

Ngày thực thi và lập báo cáo: **23/10/2026**, múi giờ Asia/Saigon.

## 1. Kết quả và phạm vi

Đã đưa **50/50 request I1 v2 mang tensor thật/P1** qua file service trên KV260,
nhận đủ response hợp lệ: **46 lần chạy tail s0…s9 qua root GraphRunner CPU+DPU**
và **4 request s10 identity**, không tạo/nạp model s10. Cùng packet chạy trên
backend reference HOST để đối chiếu. Nhãn khớp reference **50/50 ở cả hai backend**.

Trạng thái: **`FILE_PIPELINE_EXECUTED_NUMERIC_REVIEW_PENDING`**. Đây là kết quả
execution và đối chiếu trong phạm vi file; chưa có quyết định nghiệm thu số học
INT8/DPU của nhóm, accuracy trên test độc lập hoặc inference qua BLE Device–KV260.

50 vector là **50 cặp sample/split lấy từ 5 mẫu ECG validation khác nhau**, phủ
11 điểm chia; s0…s5 mỗi split 5 vector, s6…s10 mỗi split 4 vector. Các mẫu được
lặp qua nhiều split, không phải 50 mẫu ECG độc lập. Chưa chạy bài 100 mẫu
end-to-end của tuần 8; kết quả TCP riêng ở mục 5 chỉ là HOST smoke s10.

## 2. Mục tiêu và đầu vào

Mục tiêu tuần 7 là nhận packet từ file/socket, kiểm CRC, xử lý scale per-channel,
chạy tail và trả kết quả. Với I1 v2/P1, phải unprotect trước khi giải lượng tử.
Luồng kế thừa [báo cáo tuần 6](sv2_edge_week6_report.md),
[I1 v2](../contracts/i1_device_edge_packet_v2.md),
[I2/1](../contracts/i2_protection_v1.md) và
[bàn giao 50 vector](../ml/docs/week6_p1_delivery.md).

| Đầu vào | Định danh |
|---|---|
| Model | `mitdb_week2_cnn_v1`, checkpoint `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` |
| Model package | `mitdb-week3-sv2-fp32-20261001-v1`, manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` |
| P1 package | `mitdb-week6-p1-50-20261016-v1` |
| P1 manifest | `d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36` |
| P1 ZIP SHA256 | `2afbab35b601ac14128c32018d6dc1d39afd1991759a7a0fd9ad2051d923359a` |
| Registry | `mitdb-week5-i2-registry-v1-r1`, profile 1296651265, wire split IDs 256…266 |
| Key/nonce bộ vector | Public key `00..1f`, sequence 1…50 cố định, chỉ kiểm offline `PUBLIC_TEST_ONLY` |
| Runtime | KV260 SD-A, PetaLinux 2022.1, Vitis AI 2.5, DPU B4096 một core; fingerprint kế thừa inventory `0x101000016010407` |
| Build native | aarch64, GCC 11.2.0, build receipt `2026-10-23T07:04:30Z` |
| Python board | Python 3.9.9, NumPy 1.21.2; môi trường đã xác nhận, không cài torch/ONNX lên board |

Dùng nguyên model, CPU plugins và bundle đã xác thực ở tuần 5; không quantize/
compile lại model, thay preprocessing, đổi packet hoặc sửa registry. Gói P1 có
405 file trong inventory và một root manifest, tổng 406 file.

## 3. Hiện thực

Source được đưa vào [edge/server/week7](../edge/server/week7/README.md), runner
một tensor tại [edge/runtime/single_input](../edge/runtime/single_input/README.md).
`serve.py`, `batch.py` và ba file native runner được copy **nguyên bytes** từ
snapshot đã chạy, đối chiếu lại với hồ sơ nhận từ board trước khi công bố.

Luồng xử lý:

1. Đọc frame có giới hạn, kiểm envelope/CRC và metadata theo reference I1 v2.
2. Với request P1: đảo I2/1, khôi phục đúng byte q; từ chối q=-128 sau unprotect.
3. Giải lượng tử bằng scale của **kênh gốc**, mở rộng từ FP16 đã lưu sang FP32.
4. s0…s8 giữ NCL; s9 reshape NC. Native runner chuyển NCL/NLC nếu graph yêu cầu,
   xử lý fix_point/DPU_ROUND và chạy **root** GraphRunner gồm CPU fallback/DPU.
5. Trả 5 raw logits N,S,V,F,Q, không softmax; argmax hòa chọn index nhỏ nhất.
   s10 trả chính logits sau giải lượng tử, không gọi native runner.

Runner tuần 5 chỉ nhận bộ 20 golden cố định. Bản tuần 7 nhận **một tensor NPY mới
được tạo từ packet**, không nhân bản packet thành 20 mẫu và không tra bảng logits
để trả lời. Source/runner/bundle đã dùng trong các tuần trước không bị sửa.

Batch xác thực anchor/inventory gói trước chạy; mỗi packet có tiến trình và
output riêng. Native timeout 4 s bao gồm nạp model; đây là hạn thực thi của công
cụ file, không phải số đo latency. Hiện nạp model lại theo request; chưa tối ưu
cache hoặc đo throughput. Lỗi CRC/envelope bị drop; lỗi sau CRC trả I1 error.

## 4. Kết quả theo split

Max abs = cực đại sai khác trên 5 logits và mọi vector trong split, so với logits
reference trên **tensor đã giải lượng tử** của gói SV3. Không phải sai số so với
input FP32 nguyên bản trước lượng tử hóa.

| s | Vector | HOST max abs | KV260 max abs | Khớp lớp KV260 |
|---:|---:|---:|---:|---:|
| 0 | 5 | 9.536743e-7 | 0.404701710 | 5/5 |
| 1 | 5 | 9.536743e-7 | 0.406458139 | 5/5 |
| 2 | 5 | 9.536743e-7 | 0.347266674 | 5/5 |
| 3 | 5 | 9.536743e-7 | 0.389440894 | 5/5 |
| 4 | 5 | 9.536743e-7 | 0.367522478 | 5/5 |
| 5 | 5 | 9.536743e-7 | 0.327105522 | 5/5 |
| 6 | 4 | 9.536743e-7 | 0.165102959 | 4/4 |
| 7 | 4 | 1.430511e-6 | 0.155872226 | 4/4 |
| 8 | 4 | 9.536743e-7 | 0.088961601 | 4/4 |
| 9 | 4 | 9.536743e-7 | 0.094398975 | 4/4 |
| 10 | 4 | 0 | 0 | 4/4 |

HOST sai khác lớn nhất **1.430511474609375e-6**, trong tolerance reference FP32
`<1e-3`. KV260 sai khác lớn nhất **0.40645813941955566**, chỉ báo mô tả:
không dùng tolerance FP32 để tự gọi INT8/DPU PASS. Cả 50 response CRC/header,
request ID và payload logits đều được tái kiểm từ bytes đã lưu.

Exporter kiểm lại q sau unprotect so với q chuẩn 50/50; với 46 native tail,
`input.npy` thực tế trùng byte tensor FP32 giải lượng tử/reshape từ packet,
runner.json là root_graph và logits trùng response. Bốn s10 identity khớp FP32
bit-exact, không có runner.json. Đây là tái kiểm bằng chứng đã lưu trên HOST,
không phải một lần chạy lại KV260 trong phiên viết báo cáo.

## 5. Socket, lỗi gặp và khắc phục

Server TCP chỉ bind localhost, mỗi kết nối mang một frame I1 nguyên bytes.
HOST client đọc packet P1 s10 thật từ gói, gửi qua socket, nhận response **64 B**
đúng request ID và 5 logits identity. Lượt thành công `socket_smoke_lan_2` có
exit0 và response_sent=true. Chưa thử TCP chạy tail s0…s9 trên KV260.

- Verifier SV3 ban đầu từ chối inventory dù 405 file đều đúng hash/size, do
  WindowsPath và PosixPath sắp thứ tự khác nhau. Wrapper riêng chỉ sắp inventory
  trong RAM bằng PureWindowsPath; không sửa gói/manifest/source SV3 hoặc bỏ gate.
  A+B sau đó đạt: 50/50 Python/C, 46 reference tail +4 identity.
- Socket lượt đầu nhận frame sai envelope/magic; log không đủ xác định loại
  client đã gửi. Lượt tiếp theo bị guard từ chối output đã tồn tại. Giữ cả hai
  log lỗi, tạo output mới rồi chạy đúng client I1 để có lượt thành công.
- Batch reference không in tiến độ từng vector ra terminal, mất vài phút do nạp
  Python/model mỗi request; có thể đọc summary/log từng vector để biết tiến triển.

TCP bench không thay BLE chính thức, reassembly, timeout/retry/duplicate cache
qua reconnect. Những phần đó tiếp tục triển khai/kiểm trong luồng tuần 8.

## 6. Bằng chứng, tính toàn vẹn và kiểm thử

- [Kết quả nhỏ có thể kiểm từ Git](../results/week7/edge/README.md):
  status, 100 dòng case của hai backend, CSV 22 hàng theo backend/split,
  P1 A+B receipts đã loại đường dẫn compiler cục bộ, socket và provenance.
- [Notebook quan sát chỉ đọc](../experiments/notebooks/sv2_edge_week7.ipynb) và
  [cấu hình thực thi](../experiments/configs/sv2_edge_week7.json).
- Kiểm inventory nguồn: **151 file reference, 289 file KV260**, tất cả đúng
  checksum. Archive nhận từ board đối chiếu remote SHA256:
  `ca8bea529211e5890b9abf097c41a13632d9bc32f90b0b57b4a2ad12c8ad69bb`.
- Native binary SHA256:
  `c6084cc0b1c2ecd306dbf2db88c3ef577e543fbfb7f77320949dfbad7bcfc247`.
  Model/plugin/source hashes nằm trong provenance. Raw/log/NPY/response/binary,
  archive và snapshot gốc giữ cục bộ, không đưa lên Git hoặc chỉnh bytes.
- `edge/export_week7_evidence.py` tái kiểm package, checksum, source mapping,
  input/response/runner và các phép so sánh trước khi export; từ chối ghi đè.

Kiểm trên HOST khi chuẩn bị source công bố: I1 v2 **23/23**, I2 **5/5**;
service **6/6** (bao gồm 54 negative request +5 pipeline vectors qua chính CLI);
adapter một tensor **3/3** qua helper C++ độc lập. Kiểm hồi quy runtime/profiler
mỗi bộ **5/5**. Các test này không phải DPU hoặc BLE mới.
Notebook chỉ đọc bảng/biểu đồ từ export; không build, SSH hay chạy inference.
Source công bố trùng snapshot đã chạy, kể cả native runner; commit Git được tạo
sau phép chạy nên source/binary hashes là định danh execution gốc.

Source công bố: commit `a851a05` (Edge service/runner/tests/exporter).

## 7. Trạng thái và bước tiếp theo

| Hạng mục | Trạng thái |
|---|---|
| Nhận/xác thực gói P1, Python/C và reference output | Đạt trong phạm vi HOST A+B |
| File pipeline qua KV260 | Đủ 50/50 execution, 46 root tail +4 identity |
| So lớp reference | 50/50, chỉ bộ validation gồm 5 mẫu ECG khác nhau |
| TCP localhost | HOST s10 smoke đạt; chưa phải KV260/BLE inference |
| Nghiệm thu số học INT8/DPU, demo/review nhóm | Còn chờ xác nhận riêng |
| Accuracy test frozen 8544 mẫu | Chưa đo trên luồng DPU này |
| BLE Device–KV260, 100 mẫu end-to-end | Chưa kiểm; chuyển tiếp tuần 8 |
| Queue/MQTT, cache model/chuyển split, tải nặng | Thuộc các tuần sau |

Tiếp theo: nhóm/SV3 review sai số theo đúng backend và phạm vi; triển khai BLE
central/reassembly/cache request, nhận cùng key bench qua kênh riêng và đối chiếu
key_check với SV1. Tổ chức echo rồi inference trên KV260 và bài end-to-end tuần 8.
Giữ baseline checkpoint/profile hiện hành; model NoPeek có trọng số mới cần phiên
bản bàn giao riêng. Không tự đổi registry nonce hoặc gán chữ ký phê duyệt.
