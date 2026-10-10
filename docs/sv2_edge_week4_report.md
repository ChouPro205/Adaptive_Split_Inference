# Báo cáo tiến độ Tuần 4 — SV2 (FPGA/Edge, KV260)

## 1. Mục tiêu Tuần 4

Theo kế hoạch nghiên cứu (`Huong1_Huong_dan_chi_tiet_tung_thanh_vien.pdf` - Mục A.2) và định hướng từ Tuần 3:

1. **Tự động hóa hoàn toàn luồng biên dịch:** Viết kịch bản `compile_all_splits.sh` tự động hóa toàn bộ chu trình lượng tử hóa (`vai_q_pytorch`) và biên dịch (`vai_c_xir`) cho tất cả 10 điểm cắt khả dĩ $s \in \{0, 1, \dots, 9\}$ từ gói bàn giao của SV3.
2. **Cô lập lỗi và chạy qua đêm:** Đảm bảo quá trình xử lý từng điểm cắt $s$ hoạt động độc lập, không dùng `set -e` để ngắt ngang tiến trình nếu xảy ra lỗi cục bộ; thu thập log độc lập cho từng split (`log_s<id>.txt`).
3. **Tổng kết nghiệm thu:** Tự động xuất báo cáo tóm tắt trạng thái biên dịch (`summary.txt`) và phân tích tính tương thích phần cứng DPU B4096 trên Kria KV260, chuẩn bị cho nhiệm vụ phân loại mô hình (DPU thuần vs Lai DPU+PS) ở Tuần 5.

---

## 2. Môi trường và công cụ thực hiện

Tuân thủ quy ước dự án `ASI-CONVENTION-001` (Mục 10.2: không dùng từ "latest", ghi rõ phiên bản và tham số môi trường):

| Thành phần | Phiên bản / Định danh chi tiết |
|---|---|
| **Hệ điều hành Host** | Linux x86_64 (WSL2 Kernel `6.18.40.1-microsoft-standard-WSL2`, Ubuntu 22.04 LTS) |
| **Môi trường Vitis AI** | Docker container `xilinx/vitis-ai-pytorch-cpu:ubuntu2004-3.5.0.306` |
| **Framework & Compiler** | Python 3.8.6, PyTorch 1.13.1, GCC 7.5.0 |
| **Công cụ lượng tử hóa** | `vai_q_pytorch` 3.5.0+60df3f1+torch1.13.1 (thư viện `pytorch_nndct`) |
| **Trình biên dịch DPU** | `vai_c_xir` (Vitis AI Compiler 3.5.0) |
| **Kiến trúc DPU mục tiêu** | `DPUCZDX8G_ISA1_B4096` (`/opt/vitis_ai/compiler/arch/DPUCZDX8G/KV260/arch.json`) |
| **Gói bàn giao từ SV3** | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1` (Checkpoint SHA-256: `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`) |
| **Tập dữ liệu hiệu chuẩn** | 20 mẫu golden activations ($z_{s0}$ đến $z_{s9}$) định dạng `.npy` từ MIT-BIH |

---

## 3. Công việc đã thực hiện

### 3.1. Tiếp nhận và kiểm tra gói bàn giao từ SV3
- Đã kiểm tra cấu trúc gói `mitdb-week3-sv2-fp32-20261001-v1`: mô hình chuẩn `mitdb_week2_cnn_v1`, kiến trúc mạng 1D-CNN (8 tầng Conv1D kèm ReLU và MaxPool1D xen kẽ, tầng Classifier gồm Flatten, Dropout, 2 tầng Linear).
- Xác nhận ánh xạ tensor $z_s$ của 10 điểm cắt $s \in \{0..9\}$:
  - $s=0$: Đầu vào thô $[1, 1, 360]$ (NCL).
  - $s=1..8$: Kích hoạt trung gian các tầng tích chập/pooling ($[1, 16, 360]$ đến $[1, 64, 22]$).
  - $s=9$: Kích hoạt sau tầng Linear đầu tiên $[1, 32]$ (NC).
  - Điểm cắt $s=10$ là Full-Head trên MCU (Device), Tail rỗng nên không cần biên dịch phía Edge.

### 3.2. Xây dựng công cụ lượng tử hóa (`edge/quantize_tail.py`)
- Viết script Python nhận tham số điểm cắt `-s {0..9}`, `--quant_mode {calib, test}`, `--output_dir` và đường dẫn checkpoint.
- Tự động tách mô hình gốc thành Tail model tương ứng với điểm cắt $s$ bằng cách trích xuất danh sách module con sau chỉ số cắt `CUTS[s]`.
- Nạp chính xác tập 20 mẫu golden activation $z_s$ từ thư mục bàn giao của SV3 để phục vụ bước hiệu chỉnh dải động (calibration).
- Thực thi 2 pha lượng tử hóa chuẩn của Vitis AI PyTorch:
  - **Pha 1 (`calib`):** Thiết lập `torch_quantizer(quant_mode='calib')`, chạy forward pass trên 20 mẫu golden, xuất file tham số lượng tử `quant_info.json`.
  - **Pha 2 (`test`):** Thiết lập `torch_quantizer(quant_mode='test')`, xuất đồ thị trung gian XIR `Sequential_int.xmodel`.

### 3.3. Xây dựng kịch bản tự động hóa biên dịch hàng loạt (`edge/compile_all_splits.sh`)
- Thiết lập kịch bản chạy vòng lặp $s = 0 \dots 9$, tự động gọi `quantize_tail.py` (2 pha) và `vai_c_xir`.
- **Cơ chế cô lập lỗi:**
  - Không sử dụng cờ `set -e` để tránh việc một điểm cắt phát sinh lỗi làm dừng toàn bộ batch job qua đêm.
  - Kiểm tra mã lỗi (`exit_code`) sau từng công đoạn; nếu thất bại, ghi nhận vào file log riêng của split đó và chuyển sang điểm cắt tiếp theo.
- **Tổ chức thư mục xuất:**
  - File trung gian lượng tử: `edge/build/quantized/s<id>/`
  - File biên dịch hoàn thiện: `edge/build/compiled/tail_s<id>.xmodel`
  - Log thực thi chi tiết: `edge/build/logs/log_s<id>.txt`
  - Báo cáo tổng kết: `edge/build/summary.txt`

### 3.4. Thực thi và thu thập kết quả
- Chạy toàn bộ tiến trình trong Vitis AI Docker container.
- Thu thập đầy đủ log, kiểm tra tính toàn vẹn và mã MD5 của từng file `.xmodel`.

---

## 4. Kết quả nghiệm thu

### 4.1. Tóm tắt trạng thái nghiệm thu 10 điểm cắt

Trích xuất trực tiếp từ file báo cáo nghiệm thu tự động `edge/build/summary.txt`:

| Điểm cắt ($s$) | Trạng thái biên dịch | Log chi tiết | File đầu ra (.xmodel) |
|:---:|:---:|:---:|:---:|
| $s=0$ | **THANH_CONG** | `edge/build/logs/log_s0.txt` | `edge/build/compiled/tail_s0.xmodel` |
| $s=1$ | **THANH_CONG** | `edge/build/logs/log_s1.txt` | `edge/build/compiled/tail_s1.xmodel` |
| $s=2$ | **THANH_CONG** | `edge/build/logs/log_s2.txt` | `edge/build/compiled/tail_s2.xmodel` |
| $s=3$ | **THANH_CONG** | `edge/build/logs/log_s3.txt` | `edge/build/compiled/tail_s3.xmodel` |
| $s=4$ | **THANH_CONG** | `edge/build/logs/log_s4.txt` | `edge/build/compiled/tail_s4.xmodel` |
| $s=5$ | **THANH_CONG** | `edge/build/logs/log_s5.txt` | `edge/build/compiled/tail_s5.xmodel` |
| $s=6$ | **THANH_CONG** | `edge/build/logs/log_s6.txt` | `edge/build/compiled/tail_s6.xmodel` |
| $s=7$ | **THANH_CONG** | `edge/build/logs/log_s7.txt` | `edge/build/compiled/tail_s7.xmodel` |
| $s=8$ | **THANH_CONG** | `edge/build/logs/log_s8.txt` | `edge/build/compiled/tail_s8.xmodel` |
| $s=9$ | **THANH_CONG** | `edge/build/logs/log_s9.txt` | `edge/build/compiled/tail_s9.xmodel` |

* **Tổng số điểm cắt THÀNH CÔNG:** 10 / 10 (đạt 100%)
* **Tổng số điểm cắt THẤT BẠI:** 0

### 4.2. Đặc tính kỹ thuật chi tiết các mô hình Tail `.xmodel`

Toàn bộ 10 file `.xmodel` đều được biên dịch thành công cho kiến trúc `DPUCZDX8G_ISA1_B4096`:

| Split $s$ | Kích thước Tensor đầu vào | Số Op trong đồ thị | Tổng Device Subgraph | DPU Subgraph | CPU Subgraph | Kích thước file `.xmodel` | Mã MD5 Checksum |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **$s=0$** | $[1, 1, 360]$ | 84 ops | 5 | 2 | 3 | 286,713 bytes (280 KB) | `8814e94eb2fb41e5873b8096640896e4` |
| **$s=1$** | $[1, 16, 360]$ | 77 ops | 5 | 2 | 3 | 275,714 bytes (269 KB) | `352120ffaabf06fc4f38621a441dc6c2` |
| **$s=2$** | $[1, 16, 180]$ | 68 ops | 5 | 2 | 3 | 263,045 bytes (257 KB) | `d673142f10330ece37537f473bfbada7` |
| **$s=3$** | $[1, 32, 180]$ | 61 ops | 5 | 2 | 3 | 251,707 bytes (246 KB) | `24e8fde9dcd4f94e4fe87f3389cd7bec` |
| **$s=4$** | $[1, 32, 90]$ | 52 ops | 5 | 2 | 3 | 234,567 bytes (229 KB) | `369b2ad218a473c1123772b3c61e871b` |
| **$s=5$** | $[1, 48, 90]$ | 45 ops | 5 | 2 | 3 | 218,812 bytes (214 KB) | `d594eb733f3883bcbf48b5f905a7bc80` |
| **$s=6$** | $[1, 48, 45]$ | 36 ops | 5 | 2 | 3 | 197,272 bytes (193 KB) | `c3c28faa90c3ab2754a179b00890769d` |
| **$s=7$** | $[1, 64, 45]$ | 29 ops | 5 | 2 | 3 | 172,959 bytes (169 KB) | `a3da3f65dd6057bbdc5c2ae3d773e00b` |
| **$s=8$** | $[1, 64, 22]$ | 19 ops | 3 | 1 | 2 | 138,751 bytes (136 KB) | `de81abf9cd872a76a86d892ea6669b2c` |
| **$s=9$** | $[1, 32]$ | 8 ops | 3 | 1 | 2 | 87,147 bytes (85 KB) | `86b66d760725b4fb4b904af3673a9e34` |

### 4.3. Phân tích phân bổ toán tử DPU vs CPU (ARM PS)

Từ kết quả phân tích log biên dịch của `vai_c_xir`:

1. **Nhóm mô hình $s \in \{0, 1, \dots, 7\}$:**
   - Đồ thị chứa cả các khối tích chập Conv1D, MaxPool1D và bộ phân loại Classifier.
   - Trình biên dịch phân rã thành **2 DPU subgraphs** (tận dụng bộ tăng tốc phần cứng DPU cho các phép tính tích chập và fully connected) và **3 CPU subgraphs**.
   - Cảnh báo xuất hiện trong log:
     ```text
     [UNILOG][WARNING] xir::Op{name = Sequential__Sequential_MaxPool1d_X__ret_Y_sink_transpose_0, type = transpose} has been assigned to CPU.
     ```
     *Nguyên nhân:* Do DPU B4096 thao tác trên định dạng tensor tối ưu nội bộ, phép hoán vị trục (`transpose`) giữa tầng MaxPool cuối cùng và tầng Flatten/Linear chưa được DPU ISA hỗ trợ trực tiếp dạng phần cứng thuần nên compiler tự động gán fallback về CPU (PS) xử lý. Đây là cơ chế phân tách đồ thị chuẩn của Vitis AI.
2. **Nhóm mô hình $s \in \{8, 9\}$:**
   - Điểm cắt $s=8$ (bắt đầu từ Classifier: Flatten -> Dropout -> Linear -> ReLU -> Linear) và $s=9$ (chỉ còn tầng Linear cuối).
   - Đồ thị đơn giản hơn rất nhiều, phân rã thành **1 DPU subgraph** và **2 CPU subgraphs** (xử lý input/output và CPU memory copy).
   - Không xuất hiện cảnh báo transpose fallback từ MaxPool1D.

---

## 5. Đối chiếu quy ước dự án và quản lý dữ liệu

Tuân thủ quy ước `ASI-CONVENTION-001`:

1. **Quản lý file nhị phân và dữ liệu lớn (Mục 13.2):**
   - Các file `.xmodel` (tổng kích thước > 2.1 MB) cùng toàn bộ file trung gian lượng tử (`edge/build/quantized/`) và log biên dịch được đặt bên trong thư mục `edge/build/`.
   - Thư mục `edge/build/` và đuôi `*.xmodel` đã được cấu hình trong `.gitignore`, đảm bảo không commit file nhị phân lớn vào kho Git chung.
2. **Quy ước đặt tên biến (Mục 5.3):**
   - Toàn bộ biến đếm trong script tự động hóa dùng hậu tố chuẩn `_count` (`success_count`, `fail_count`).
3. **Kiểm tra bổ sung dữ liệu vào các thư mục khác:**
   - Theo quy ước dự án, thư mục `results/` (như `results/week2/`) dành cho dữ liệu đo kiểm thực nghiệm vật lý (dòng điện, công suất, log PPK2, biểu đồ sóng).
   - Ở Tuần 4, vai trò SV2 tập trung vào việc tự động hóa lượng tử hóa và biên dịch chuỗi mô hình Tail phía máy chủ biên (phần mềm/compiler), chưa tiến hành nạp đo thực tế trên board KV260 vật lý (công việc đo latency/throughput VART trên board thuộc các tuần tiếp theo).
   - Do đó, **không phát sinh việc đẩy thêm dữ liệu đo lường vào thư mục `results/` hay sửa đổi các thư mục hợp đồng `contracts/`**.
   - Cập nhật mục lục tài liệu tại `docs/README.md` để ghi nhận báo cáo Tuần 4 của SV2.

---

## 6. Vấn đề phát sinh và cách xử lý

| Vấn đề phát sinh | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cảnh báo `FutureWarning: Unlike other reduction functions... stats.mode` khi chạy `vai_q_pytorch` | Do thư viện SciPy bên trong container Vitis AI 3.5 thay đổi hành vi mặc định của hàm `mode` trong tương lai | Cảnh báo vô hại từ dependency upstream của Xilinx; thuật toán lượng tử hóa vẫn hội tụ bình thường |
| Cảnh báo `transpose Op has been assigned to CPU` | DPU không hỗ trợ tính toán trực tiếp lớp chuyển vị kênh tensor sau MaxPool1d | Trình biên dịch `vai_c_xir` tự động gán chạy trên CPU (ARM Cortex-A53 của KV260), mô hình vẫn được thực thi lai (hybrid) thông suốt qua runtime VART |
| Cần tránh dừng batch script khi có 1 split bị lỗi cú pháp | Bash mặc định nếu dùng `set -e` sẽ ngắt ngang toàn bộ tiến trình | Dùng `set -u`, xử lý mã lỗi tường minh bằng `exit_code` để cô lập lỗi cho từng split, đảm bảo batch job chạy qua đêm an toàn |

---

## 7. Kế hoạch Tuần 5 (tiếp theo)

1. **Phân loại kiến trúc Tail Model (Mục tiêu Tuần 5):**
   - Dựa trên dữ liệu Subgraph đã phân tích ở Tuần 4, chính thức phân loại 10 điểm cắt thành 2 nhóm:
     - **Nhóm DPU thuần / Ưu tiên DPU:** Các split có khối lượng tính toán Conv1D lớn ($s=0..6$), hưởng lợi tối đa từ DPU.
     - **Nhóm Lai (Hybrid DPU + PS CPU):** Các split nhỏ ($s=7..9$), đánh giá xem overhead nạp dữ liệu vào DPU so với chạy thẳng PyTorch/ONNX Runtime trên CPU của KV260 phương án nào tối ưu độ trễ hơn.
2. **Kiểm chứng độc lập trên KV260:**
   - Nạp các file `tail_s<id>.xmodel` lên board KV260 (`kv260-node01`).
   - Viết runner VART nhỏ gọn kiểm tra suy luận trên 20 mẫu golden, đối chiếu kết quả logits với đầu ra PyTorch FP32 của SV3.
