# Báo cáo tiến độ Tuần 3 — SV2 (FPGA/Edge, KV260)

## 1. Mục tiêu

1. Biến KV260 thành máy chủ Linux (Ubuntu 22.04) truy cập từ xa bằng SSH (Tuần 1).
2. Cài Kria-PYNQ và kiểm chứng DPU bằng notebook mẫu (Tuần 2).

## 2. Tóm tắt kết quả

| # | Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | Ghi thẻ SD Ubuntu 22.04, boot KV260 | DONE | Terminal `ubuntu@kv260-node01` |
| 2 | Cập nhật boot firmware (file v2022.1 update1) | DONE | File `BOOT_xilinx-k26-starterkit-v2022.1-05140151_update1.BIN` có trên board; cần log `xmutil bootfw_status` |
| 3 | Đặt hostname, IP tĩnh | 192.168.0.134 | Log `ip a`, file netplan (đã có sao lưu `netplan_backup.yaml`) |
| 4 | SSH vào board từ PC | DONE | Phiên SSH/serial đã chụp |
| 5 | Tắt giao diện đồ họa (`multi-user.target`) | DONE | Log `systemctl get-default` |
| 6 | `xlnx-config` cài đặt, `xlnx-config -q` đúng | DONE | Log `xlnx-config -q` |
| 7 | Cài Kria-PYNQ (`install.sh -b KV260`) | DONE | `import pynq` → `3.0.1`; `pynq-dpu 2.5` |
| 8 | Jupyter service chạy và tự khởi động | DONE | `jupyter.service` active (running), enabled |
| 9 | Notebook DPU mẫu (ResNet50) cho kết quả đúng | DONE | Cần ảnh/log kết quả phân loại + thời gian suy luận |
| 10 | Tắt board đúng quy trình | DONE | Log `reboot: Power down` |

## 3. Môi trường đã ghi nhận (không dùng "latest")

| Thành phần | Phiên bản |
|---|---|
| Hệ điều hành | Ubuntu 22.04 for Kria |
| Boot firmware | v2022.1 |
| Kria-PYNQ |
| pynq | 3.0.1 |
| pynq-dpu | 2.5 |
| Địa chỉ mạng | 192.168.0.134, hostname `kv260-node01` |
| Nguồn cấp | 12 V / 3 A chính hãng (Basic Accessory Pack) |

## 4. Chi tiết thực hiện

### 4.1 Hệ điều hành và mạng
- Ghi thẻ SD bằng balenaEtcher, đổi mật khẩu mặc định ở lần đăng nhập đầu.
- Đặt hostname `kv260-node01` (khớp `edge_id = KV260_NODE_01` của hợp đồng I4).
- Cấu hình IP tĩnh bằng netplan, kiểm tra bằng `netplan try`. 

### 4.2 Boot firmware
- Đã tải file BOOT v2022.1 update1 về board.

### 4.3 Kria-PYNQ
- Lệnh: `sudo bash install.sh -b KV260`. Cài thành công, `pynq 3.0.1`, `pynq-dpu 2.5`.
- Jupyter: dịch vụ `jupyter.service` chạy với quyền root nên thư mục notebook **không** nằm trong `/home/ubuntu` (lệnh `cd ~/jupyter_notebooks` báo lỗi là bình thường). Truy cập qua `http://<IP>:9090`.


## 5. Vấn đề phát sinh và cách xử lý

| Vấn đề | Nguyên nhân | Xử lý |
|---|---|---|
| `cd ~/jupyter_notebooks`: No such file or directory | Jupyter chạy bằng root, notebook không ở home của `ubuntu` | Truy cập qua trình duyệt cổng 9090 / tìm bằng `find` |
| Cảnh báo `unregister bridge display ...` khi shutdown | Cảnh báo driver hiển thị khi tắt máy | Vô hại; log `Power down` xác nhận tắt thành công |

## 7. Kế hoạch tuần tới

1. Cài Vitis AI 3.5 (Docker) trên PC; quantize và compile một mô hình nhỏ ra `.xmodel` với `arch.json` của KV260. Tiêu chí: có file `.xmodel` kèm log biên dịch.
2. Nạp `.xmodel` tự biên dịch lên KV260; kết quả khớp PyTorch.
3. Chốt phương án khớp phiên bản `pynq-dpu` ↔ Vitis AI cùng GVHD.

