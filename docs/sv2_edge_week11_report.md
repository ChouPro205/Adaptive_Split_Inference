# SV2 tuần 11 — độ bền cache và hàng đợi trên KV260

Tuần 23–29/11/2026. SV2 hoàn thành bốn đầu việc kỹ thuật gồm stress cache,
echo trên HOST, T1 checkpoint gói A và thử tải bùng. Hai phép đo phần cứng
dưới đây thực thi offline trên KV260 SD-A, PetaLinux 2022.1, kernel
`5.15.19-xilinx-v2022.1`, Vitis AI 2.5, Python 3.9.9 và DPU
`DPUCZDX8G_ISA1_B4096` ở 300 MHz. Hai lượt dùng cùng worker root GraphRunner
CPU+DPU, bộ model và CPU plugin đã xác thực ở tuần 10.
[Cấu hình](../experiments/configs/sv2_edge_week11.json) ·
[Hồ sơ tổng hợp và SHA](../results/week11/edge/README.md)

## Độ bền cache

Lượt `raw-cbb3f2b23b4a` nạp 10 model s0–s9 và warm-up 20 request mỗi split.
Seed 11 chọn 10.000 lần chuyển thực sự giữa hai split khác nhau. Sau warm-up
có **10.000/10.000** chuyển hợp lệ, phủ 90/90 cặp có hướng, với 10.210
request cả lượt. Logits khớp bit với parity đã niêm, worker thoát mã 0
và hồ sơ kernel trước/sau không có chênh lệch trong các dòng theo dõi
OOM, kill và segfault.

| Đại lượng | Mean (ms) | Độ lệch chuẩn (ms) | p95 (ms) | Max (ms) |
|---|---:|---:|---:|---:|
| Chuyển model, tính cả IPC SELECT | 0,306 | 0,028 | 0,344 | 0,754 |
| Chạy tail | 28,704 | 18,660 | 53,270 | 62,302 |

`psutil` thu 103 mẫu gồm ba mốc chuẩn bị và một mẫu mỗi 100 lần chuyển.
Hồi quy dưới đây dùng mốc sau warm-up và chuỗi stress.

| Tiến trình | RSS đầu → cuối (KiB) | Độ dốc (KB/1.000 lần) |
|---|---:|---:|
| Worker GraphRunner | 23.884 → 23.884 | ≈ 0 |
| Python điều phối | 31.692 → 31.840 | +15,76 |

Worker giữ RSS và bộ nhớ private trong toàn chuỗi sau warm-up. RSS Python
tăng 148 KiB và giữ 31.840 KiB từ lần 7.400 đến hết các mốc quan sát.
Kết luận về bộ nhớ giới hạn ở lượt đã đo. Trạng thái `PENDING` của
analyzer được giữ trong bản tổng hợp gốc.
[Summary stress](../results/week11/edge/summary.json) ·
[Chuỗi RAM](../results/week11/edge/memory.csv)

## Queue tải bùng

FIFO tuần 10 thực thi tail s2 thật. Seed 11 chọn vector, lịch đến gồm ba đợt
16 job, mỗi job cách nhau 1 ms trong đợt và đầu đợt cách nhau 3 s. Giới hạn
là 32 job nền đang chờ. `q` là độ sâu sau enqueue, tính job vừa vào và
loại job đang thực thi. Thời gian chờ lấy từ enqueue đến lúc bắt đầu
chạy tail theo đồng hồ monotonic trên board.

Có **48/48 job hoàn tất**, **q tối đa 15**, không có job bị từ chối, lỗi hay
lệch parity. Worker thoát mã 0. Hệ số hồi quy là **49,416 ms/job**, thấp hơn
mốc tham chiếu tuần 10 **51,7 ms/job** khoảng **2,284 ms/job**. Đây là phép
so sánh với mốc của nhóm trong kịch bản tải bùng offline. CSV ghi số mẫu,
mean và p95 cho từng q.
[Summary queue](../results/week11/edge/burst_summary.json) ·
[Thời gian chờ theo q](../results/week11/edge/wait_by_q.csv)

## Echo và T1 trên HOST

- **Echo full/ACK.** 24 vector SV1 và hai ca bổ sung 362 B đều khớp byte ở
  MTU 23 và 247, tổng **52 phép kiểm** qua phân mảnh/ghép khung stream
  0x02. Full trả nguyên frame. ACK dài 72 B, giữ request ID và mang độ dài
  cùng SHA-256 của khung nhận. Phạm vi là kiểm giao thức trên HOST.
  [Kết quả echo](../results/week11/edge/echo_summary.json)
- **T1 gói A.** Kiểm 58 mục inventory của Release M1 v4, nạp checkpoint
  C5 đã khóa và forward CPU s0 với một tensor train DS1, logits shape
  `[1,5]`. Ca âm dùng cùng cấu hình SHA A và từ chối checkpoint tuần 3
  do SHA khác. SHA A được gắn vào tiến trình dry-run. Lượng tử hóa, build
  xmodel và xác minh DPU thuộc H7.
  [Receipt rút gọn](../results/week11/edge/package_a_summary.json)

## Tái kiểm hồ sơ

- [Công cụ chạy và kiểm trên HOST/KV260](../edge/server/week11/README.md).
- [Notebook chỉ đọc](../experiments/notebooks/sv2_edge_week11.ipynb) kiểm
  SHA rồi hiển thị bảng và biểu đồ từ checkout.
- [Provenance](../results/week11/edge/provenance.json) ràng buộc run ID,
  checkout lúc đo, SHA source chạy thật và checksum capture. Báo cáo này
  thuộc SV2/Edge. Các hợp đồng I1–I4 giữ nguyên.

## CẦN PHỐI HỢP — review PR

SV2 gửi link báo cáo và export. Reviewer của nhóm kiểm source, phạm vi
đo, số liệu và SHA. Chờ review theo quy ước nhóm trước khi merge vào main.
