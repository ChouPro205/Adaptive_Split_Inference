# SV2 tuần 10 — cache model và chuyển split trên KV260

Mục tiêu tuần 10 của Edge là chọn tail theo split trong request, giữ model đã
nạp và chứng minh thời gian chuyển split sau lần đầu dưới 50 ms. KV260 chạy
PetaLinux 2022.1, kernel 5.15.19-xilinx-v2022.1, Vitis AI 2.5 và Python 3.9.9
(GCC 11.2.0). Phiên BLE dùng adapter UB500, Bleak 0.22.3 và dongle nRF52840
phía SV1. Kết quả dưới đây được đọc từ hồ sơ lưu của board.

## Cache và kiểm tra offline

Worker ARM64 giữ 10 context XIR/root GraphRunner cho s0–s9. Receiver chọn
context theo split, thực thi lại tail cho request mới và theo dõi cache model
riêng với cache response. Với s10, luồng offline kiểm đường identity. Trong
buổi BLE mọi split, s10 được tính trên Device nên không có request Edge.

Hai lượt smoke có 5 và 13 request. Parity khớp bit **50/50** với baseline
single-input trên cùng bộ model. Bộ gồm 46 lượt tail và 4 lượt identity từ
5 ECG, dùng để kiểm tương đương triển khai. Cả 500 dự đoán cache bàn giao
cho SV1 đã được phía nhận xác nhận đủ và đúng q/scale theo bộ tham chiếu.

Benchmark hoàn thành **2.233 dòng**, warm-up 20 lần mỗi model. Trong
**1.801 lần đổi split có cache hit**, mean **0,355 ms**, độ lệch chuẩn
**0,019 ms**, p95 **0,378 ms**, max **0,810 ms**, không có mẫu ≥50 ms.
Benchmark offline quan sát 19/90 cặp đổi có hướng. Phép đo tính từ khi
Python gửi SELECT đến khi nhận xác nhận native, gồm IPC. Thời gian nạp lần
đầu (native 9,331–94,702 ms), chạy tail và BLE RTT được ghi riêng.
Bộ số liệu đáp ứng ngưỡng trên các lượt quan sát. Stress 10.000 lần và
kiểm rò bộ nhớ thuộc tuần 11.

## Phối hợp Device

Mỗi lượt preload đủ 10 tail và có Read PHY TX/RX 2M trước request đầu.
Kết quả khớp bit trong bảng là đối chiếu **phía Edge** với predictions
offline. Lượt chạy khô 4a/4b đã hoàn thành theo xác nhận của SV2, với
timeout chờ ngắt BLE cuối phiên sau khi đã đủ request. Raw giữ trạng thái
INCOMPLETE. Các lượt A/B đóng service sạch và qua kiểm tra hồ sơ Edge.

| Lượt | Request OK / khớp bit / dự kiến | Queue | Kết quả phía Edge |
|---|---:|---|---|
| 4a | 100 / 100 / 100 | FIFO, λ=0 | Đủ request, timeout cuối |
| 4b | 500 / 500 / 500 | Tắt | Đủ request, timeout cuối |
| A1 lần 2 | 200 / 200 / 200 | E_wait, seed 101 | Kiểm hồ sơ đạt |
| A2 | 200 / 200 / 200 | E_wait, seed 102 | Kiểm hồ sơ đạt |
| B1 | 500 / 500 / 500 | Tắt | Kiểm hồ sơ đạt |
| B2 | 500 / 500 / 500 | Tắt | Kiểm hồ sơ đạt |

A1/A2 dùng cùng CSV tải 460 s và 100 request P1 + 100 P0 mỗi lượt.
Ghép được đủ 200 job foreground mỗi lượt. Sai khác lớn nhất giữa dấu
thời gian enqueue và RX là 35,174 ms ở A1, 35,974 ms ở A2. Queue giới
hạn sức chứa nên từ chối 1.233/5.400 job nền ở A1 và 1.288/5.458 ở A2.
B1 và B2 mỗi lượt có 497 lần chuyển model quan sát được, đủ 90/90 cặp có
hướng, max lần lượt **0,497 ms** và **0,465 ms**.

Phần này công bố hồ sơ Edge. Import Device, phân tích năng lượng PPK2 và
xác nhận nghiệm thu chung do SV1/GV đối chiếu theo phiên. Các gói đo
được nhận diện bằng SHA-256 trong hồ sơ tổng hợp.

## Chạy lại và review

- Source và lệnh chuẩn bị/build/chạy: [service offline](../edge/server/week10/README.md),
  [worker GraphRunner](../edge/runtime/model_cache/README.md).
- [Cấu hình thí nghiệm](../experiments/configs/sv2_edge_week10.json),
  [hồ sơ tổng hợp](../results/week10/edge/README.md) và
  [notebook chỉ đọc](../experiments/notebooks/sv2_edge_week10.ipynb).
- I1–I4 giữ nguyên. Các gói lab ghi hash adapter thực đo. Việc tái tạo
  capture BLE cần bộ đầu vào và công cụ lab từ bàn giao của nhóm.

SV2 có thể dùng notebook để xem số liệu, hoặc dùng lệnh smoke trên KV260
để demo đổi split và tái sử dụng context. Phối hợp demo với GV khi cả hai
sẵn sàng. Reviewer kiểm kết quả và phạm vi trước khi merge.
