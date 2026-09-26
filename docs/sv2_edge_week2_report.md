# Báo cáo công việc Week 2 – Vitis AI Docker & Lượng tử hóa thử nghiệm (KV260)

## 1. Mục tiêu Week 2

- Cài đặt Vitis AI 3.5 bằng Docker trên máy tính cá nhân (không cài trên KV260).
- Đi qua thử một lượt "dây chuyền" lượng tử hóa: mô hình PyTorch (FP32) → quantize (test mode) → compile ra file `.xmodel` cho kiến trúc DPU của KV260.
- Việc nạp file `.xmodel` lên KV260 và chạy thử trên phần cứng thật hoãn sang giai đoạn sau do chưa có board KV260 vật lý trong tay ở tuần này.

## 2. Môi trường và công cụ

| Thành phần | Giá trị |
| --- | --- |
| Docker image | `ubuntu2004-3.5.0.306` (CPU) |
| Vitis AI Git Hash | `6a9757a` |
| Build date (image) | 2023-06-26 |
| Workflow | pytorch |
| Framework | PyTorch 1.13.1, `vai_q_pytorch` 3.5.0+60df3f1 |
| Python | 3.8.6 (GCC 7.5.0) |
| Mô hình thử nghiệm | ResNet18 (`model/resnet18.pth`, pretrained) |
| Dataset test | `imagenet-mini`, `subset_len=200`, `batch_size=32` |
| Target DPU (biên dịch) | `DPUCZDX8G_ISA1_B4096` (kiến trúc DPU B4096 dùng trên KV260) |

*Ghi chú:* tập test chỉ dùng 200 ảnh trong `imagenet-mini` (không phải toàn bộ tập validation ImageNet), nên các số liệu accuracy dưới đây chỉ có giá trị **so sánh tương đối FP32 và INT8 trong cùng điều kiện**, không phản ánh accuracy chính thức của mô hình.

## 3. Công việc đã thực hiện

### 3.1. Cài đặt và khởi động container Vitis AI 3.5

Khởi động container thành công, xác nhận đúng phiên bản qua banner khởi động (Docker Image Version `ubuntu2004-3.5.0.306`, Git Hash `6a9757a`, Workflow `pytorch`).

### 3.2. Chạy baseline FP32 (chưa lượng tử hóa)

Lệnh chạy: `python resnet18_quant.py --quant_mode float --data_dir imagenet-mini --model_dir model --subset_len 200 --batch_size 32`

Kết quả (trích `log_float_baseline.txt`):

| Chỉ số | Giá trị |
| --- | --- |
| Loss | 0.0393 |
| Top-1 accuracy | 73.0% |
| Top-5 accuracy | 89.5% |

### 3.3. Lượng tử hóa INT8 và test lại

Chạy `vai_q_pytorch` ở chế độ test với cấu hình lượng tử hóa mặc định, xử lý qua toàn bộ 71 node của đồ thị ResNet18 (conv, batch norm, relu, add, pooling, linear...), sinh module đã lượng tử hóa (`quantize_result/ResNet.py`).

Kết quả (trích `log_int8_test.txt`):

| Chỉ số | Giá trị |
| --- | --- |
| Loss | 0.0479 |
| Top-1 accuracy | 68.0% |
| Top-5 accuracy | 89.0% |

### 3.4. Biên dịch (compile) sang `.xmodel` cho KV260

Lệnh biên dịch nhắm đúng kiến trúc DPU của KV260 (trích `log_compile.txt`):

| Thông tin biên dịch | Giá trị |
| --- | --- |
| Target architecture | `DPUCZDX8G_ISA1_B4096` |
| Graph | ResNet, 171 phép toán (op) |
| Subgraph | Tổng 3 subgraph thiết bị, trong đó **1 subgraph chạy trên DPU** |
| File xmodel sinh ra | `compiled_model/resnet18_kv260.xmodel` |
| MD5 (theo log compile) | `1a2425ed124dbf8cd46978da66b552be` |

### 3.5. Xác minh file đầu ra

Kiểm tra các file trung gian và file cuối cùng bằng `ls -lh` và `sha256sum`:

| File | Kích thước | Vai trò |
| --- | --- | --- |
| `model/resnet18.pth` | 45M | Trọng số PyTorch gốc (FP32) |
| `quantize_result/ResNet_int.xmodel` | 45M | Kết quả trung gian sau bước quantize |
| `compiled_model/resnet18_kv260.xmodel` | 12M | File cuối cùng, đã biên dịch cho DPU B4096 của KV260 |

SHA-256 của file sẽ dùng để nạp lên KV260: `2353da1c0551a6d539d4e6adec33b0dab246d29483402c254233fe846b97a186` — giá trị này cần lưu lại để đối chiếu, đảm bảo file không bị hỏng khi copy sang KV260 ở bước tiếp theo.

## 4. Kết quả tổng hợp: FP32 baseline so với INT8

| Chỉ số | FP32 (baseline) | INT8 (quantized) | Chênh lệch |
| --- | --- | --- | --- |
| Loss | 0.0393 | 0.0479 | +0.0085 |
| Top-1 accuracy | 73.0% | 68.0% | −5.0 điểm % |
| Top-5 accuracy | 89.5% | 89.0% | −0.5 điểm % |

Nhận xét: mức sụt giảm accuracy sau lượng tử hóa (khoảng 5 điểm % ở top-1) nằm trong khoảng có thể chấp nhận được cho một lần lượng tử hóa mặc định (post-training quantization) chưa tinh chỉnh, trên một mô hình mẫu (ResNet18) chỉ dùng để làm quen quy trình — chưa phải mô hình ECG 1D-CNN chính thức của dự án.

## 5. Hạn chế và lưu ý

- Chưa thực hiện bước nạp `resnet18_kv260.xmodel` lên KV260 và chạy trên DPU thật, do chưa có board vật lý trong tay ở tuần này.
- Test accuracy chỉ chạy trên tập con 200 ảnh (`subset_len=200`) của `imagenet-mini`, không phải toàn bộ tập validation chuẩn — số liệu chỉ dùng để so sánh tương đối FP32/INT8 trong cùng điều kiện thử nghiệm.
- Đây là thử nghiệm trên mô hình mẫu (ResNet18) để làm quen luồng công cụ Vitis AI, chưa áp dụng lên mô hình 1D-CNN thật của dự án (thuộc phạm vi SV3).

## 6. Hướng tuần tiếp theo

- Nhận/kết nối board KV260 vật lý, copy `compiled_model/resnet18_kv260.xmodel` lên board và xác nhận `sha256sum` khớp với giá trị đã ghi ở Mục 3.6.
- Chạy thử `resnet18_kv260.xmodel` trên DPU thật qua PYNQ/VART, so sánh kết quả phân loại với kết quả chạy trên PyTorch (offline) như Mốc thành công đã đề ra.
- Bắt đầu tìm hiểu cách áp dụng lại quy trình quantize → compile này cho mô hình 1D-CNN thật của dự án khi SV3 bàn giao mô hình.
