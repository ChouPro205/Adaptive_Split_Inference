# Khối Edge (KV260 / DPU / VART) - Phạm vi SV2

Khối **Edge** do **SV2** phụ trách trong dự án **Adaptive Split Inference**. Khối này đảm nhiệm việc triển khai, lượng tử hóa và tăng tốc các mô hình phần đuôi (**Tail Models**) trên bo mạch **Xilinx Kria KV260**, đồng thời quản lý máy chủ xử lý suy luận, hàng đợi và phản hồi kết quả về phía Device (MCU).

---

## 1. Mục tiêu & Nhiệm vụ Tuần 4 (SV2)

Theo tài liệu kế hoạch nghiên cứu (`Huong1_Huong_dan_chi_tiet_tung_thanh_vien.pdf` - Mục A.2):

* **Nhiệm vụ:**
  1. Viết script `compile_all_splits.sh`: chạy vòng lặp qua mọi điểm cắt $s \in \{0, 1, \dots, 9\}$, tự động gọi `vai_q_onnx` (lượng tử hóa INT8) và `vai_c_xir` (biên dịch ra `.xmodel` cho DPU KV260).
  2. Tách biệt và lưu trữ log chi tiết cho từng điểm cắt $s$ (`log_s<id>.txt`), cô lập lỗi để một split thất bại không làm dừng quá trình chạy hàng loạt.
* **Tiêu chí nghiệm thu:**
  * Script chạy tự động qua đêm, sinh ra danh sách và bảng tổng kết các điểm cắt $s$ thành công / thất bại (`summary.txt`).

---

## 2. Cấu trúc thư mục khối Edge

```text
edge/
├── compile_all_splits.sh       # Kịch bản chính tự động hóa quantize và compile ONNX
├── quantize_tail.py            # (Dự phòng) Script Python gọi vai_q_pytorch cho code cũ
├── server/                     # (Tuần 7) Server socket/BLE tiếp nhận gói tin I1
├── dpu_runner/                 # (Tuần 8-10) Runtime VART nạp .xmodel và suy luận
├── broker/                     # (Tuần 9) Trình mô phỏng trạng thái hàng đợi MQTT
├── tests/                      # Kiểm thử tích hợp khối Edge
└── README.md
```

---

## 3. Lý do & Nguyên lý hoạt động

### 3.1. Lý do kỹ thuật (Why)
1. **Tính thích ứng động (Adaptive Split):** Hệ thống thay đổi điểm cắt $s$ tại runtime tùy theo biến động mạng và năng lượng của MCU. Phía Edge bắt buộc phải có sẵn các mô hình tail tương ứng cho mọi $s$ khả dĩ ($s = 0..9$).
2. **Đặc thù phần cứng DPU (`DPUCZDX8G`):** DPU trên KV260 tối ưu cho mạng 2D CNN và có các ràng buộc chặt chẽ về toán tử phần cứng (nhiều lớp 1D-Conv, Flatten, Linear hoặc một số phép tính có thể không được DPU hỗ trợ hoàn toàn).
3. **Tự động hóa qua đêm:** Quá trình lượng tử hóa và biên dịch 10 mô hình tail tốn nhiều thời gian và dễ phát sinh lỗi compiler ở các lớp lạ. Script tự động hóa giúp SV2 chạy kiểm tra qua đêm, phát hiện chính xác các lớp bị từ chối để chuẩn bị cho **Tuần 5** (phân loại mô hình: DPU thuần vs Lai DPU+PS).

### 3.2. Nguyên lý thực hiện (Principle)
Quy trình tuân thủ chặt chẽ hợp đồng kỹ thuật và quy ước thư mục mới:
* **Bước 1 - Lượng tử hóa (`vai_q_pytorch` qua `quantize_tail.py`):**
  - Khởi tạo và nạp trọng số mô hình Tail cho điểm cắt $s$ từ checkpoint đã duyệt; script kiểm SHA-256 `9b8be076…` của approved registry và dừng (exit 2) nếu thiếu hoặc sai checkpoint.
  - Chạy `vai_q_pytorch` (`pytorch_nndct`) ở 2 pha: hiệu chỉnh phân phối dải động (`calib`) và xuất đồ thị lượng tử hóa trung gian (`test`), sinh file `Sequential_int.xmodel` (hoặc `tail_<id>_int.xmodel`) và `quantize_provenance.json` ghi checkpoint, nguồn calibration và cờ synthetic.
* **Bước 2 - Biên dịch cho DPU (`vai_c_xir`):**
  - Nạp file `_int.xmodel` và ánh xạ đồ thị tính toán vào kiến trúc DPU KV260 (`DPUCZDX8G_ISA1_B4096`).
  - Phân tách đồ thị thành các kernel DPU và các subgraph fallback trên CPU (ARM PS), xuất file `.xmodel` cuối cùng vào `edge/build/compiled/tail_s<id>.xmodel`.
* **Bước 3 - Tổng hợp & Phân tích:**
  - Bắt mã lỗi, lưu log độc lập vào `edge/build/logs/log_s<id>.txt` và xuất báo cáo nghiệm thu dạng văn bản (`edge/build/summary.txt`).

---

## 4. Hướng dẫn sử dụng

Script `compile_all_splits.sh` bắt buộc phải chạy trong môi trường **Vitis AI Docker container**.

1. **Khởi động Vitis AI container:**
   ```bash
   ./docker_run.sh xilinx/vitis-ai-pytorch-cpu:ubuntu2004-3.5.0.306
   ```
2. **Kích hoạt môi trường conda:**
   ```bash
   conda activate vitis-ai-pytorch
   ```
3. **Thực thi script biên dịch toàn bộ các split:**
   ```bash
   cd /workspace/Adaptive_Split_Inference
   bash edge/compile_all_splits.sh
   ```
4. **Kiểm tra báo cáo nghiệm thu:**
   ```bash
   cat edge/build/summary.txt
   ```

---

## 5. Đầu vào bắt buộc và calibration

- Checkpoint: `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/model/checkpoint.pt`, đúng SHA-256 của approved registry. Thiếu hoặc sai thì `quantize_tail.py` dừng, không tạo artifact.
- Calibration mặc định: `--calib-split train --calib-samples 1000`. Script chọn đều, tất định 1000 mẫu từ `ml/data/processed/mitdb/train_X.npy` (kiểm hash raw với `ml/results/week5/dataset_manifest.json`), cho chạy qua head FP32 để lấy activation $z_s$. Có thể chọn `val`; **không cho phép** `test` vì tập test frozen chỉ dùng để đánh giá.
- `--calib_data <file.npy>` chỉ được dùng kèm `--calib-data-split train|val` để khai báo split nguồn của dữ liệu.
- `--synthetic-demo` là lựa chọn tường minh duy nhất cho trọng số/dữ liệu ngẫu nhiên. Kết quả có file `SYNTHETIC_NOT_FOR_ACCEPTANCE`, xmodel tên `tail_<s>_SYNTHETIC_int.xmodel`, và `compile_all_splits.sh` từ chối biên dịch.
- `--dry-run` chỉ kiểm checkpoint, calibration và forward pass; không tạo xmodel.

## 6. Lượng tử hóa từ Device đến tail trên DPU

| Bước | Bên thực hiện | Biểu diễn | Ghi chú |
|---|---|---|---|
| 1 | Device | INT8 đối xứng theo mẫu/kênh, zero-point 0, $q\in[-127,127]$, scale lưu FP16 | Đã nghiệm thu trên MCU tuần 5 |
| 2 | Device → Edge | Payload INT8 `C×L` byte; scale FP32 LE (mở rộng đúng FP16 đã lưu); zero-point int32 = 0 | Quy cách trong [addendum I1 v1](../contracts/i1_device_edge_packet_v1_addendum_r1.md); chưa có codec/transport |
| 3 | Edge | Đảo I2/1 nếu có, rồi giải lượng tử $\hat z = q \cdot scale$ (FP32) theo kênh gốc; s9 bỏ chiều L=1 | Đã kiểm trên host trong gate tuần 5 |
| 4 | DPU | Lớp đầu của xmodel lượng tử $\hat z$ sang định dạng fix-point INT8 của DPU (scale lũy thừa 2, theo tensor, do `vai_q` calibrate); trọng số INT8 | Bắt buộc với backend DPU |

Bước 4 không phải bước thừa: DPU chỉ nhận tensor ở định dạng fix-point của chính nó, còn scale của Device thay đổi theo từng mẫu và từng kênh nên không gộp được vào trọng số tĩnh hay vào scale theo tensor của DPU. Gate accuracy tuần 5 (8.544 mẫu × 11 split) chỉ bao phủ bước 1–3 với **tail FP32**; sai số do bước 4 (lượng tử đầu vào và trọng số trên DPU) **chưa được đo**. Cần đánh giá tail đã lượng tử bằng `vai_q_pytorch` trên tập test hoặc chạy end-to-end trên KV260 trước khi kết luận accuracy của luồng DPU. Calibration dùng activation FP32 của head, còn lúc chạy DPU nhận tensor đã giải lượng tử từ INT8; ảnh hưởng của khác biệt này cũng chưa được đo.

## 7. Kiểm thử trên host

```bash
python -B edge/tests/test_quantize_tail.py
```

Test dùng checkpoint và golden thật để kiểm head/tail của cả 10 điểm cắt (sai số `<1e-3` so với golden), kiểm từ chối checkpoint sai/thiếu, chính sách calibration và đánh dấu synthetic. API `vai_q_pytorch` được thay bằng stub, nên test **không** chứng minh xmodel hay DPU chạy đúng.
