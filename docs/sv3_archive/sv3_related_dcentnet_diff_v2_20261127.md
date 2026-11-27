# DCentNet: đoạn khác biệt (related work), bản 2

Ngày 27/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`. Đây là bản nháp, chưa review.

Bản này sửa bản 20/11 ([`sv3_related_dcentnet_diff_20261120.md`](sv3_related_dcentnet_diff_20261120.md), giữ nguyên) theo review ngày 25/11 của SV1, mục 5. Phần đọc toàn văn DCentNet (mục 1–2 của bản 20/11) không đổi, nên không chép lại.

## 1. Những gì sửa

| Chỗ | Bản 20/11 | Bản này |
|---|---|---|
| Ô "Mô hình năng lượng" | E_dev khi radio bật lệch ≤ 2 % ở s ≥ 2 | Công thức E_dev,on ≈ E_dev,off + 0,7 mW × t_dev khớp phần lõi trong 1,03 % ở mọi s ≥ 2; số thô lệch giữa các ngày tới khoảng 15 % do bộ ổn áp REG0 (báo cáo tuần 10) |
| Dòng "Nén ở điểm chia" | Không | S0 chuẩn có nén cố định ở đầu vào (S0c: gom 46 giá trị, Rice); bộ nén cố định ở S1 đã được thử. Không có encoder học được ở điểm cắt; P3 còn chờ cổng K |
| Câu cuối đoạn tiếng Anh | "Our model has no compressing encoder…; intermediate splits lose to sending the raw beat" | Viết lại theo S0c và S1, vẫn giữ ý không bác bỏ DCentNet |
| Bài IEEE Sensors J 2024 | Chưa đọc | Vẫn **chưa đọc được toàn văn** (xem mục 4); chưa chốt dòng Table I |

## 2. Bảng khác biệt (bản sửa)

| Mặt | DCentNet | Nhóm mình |
|---|---|---|
| Đo năng lượng | Dòng trung bình theo chế độ, cho một cấu hình | Năng lượng theo từng pha (HEAD, PROT, TX, WAIT), tách bằng marker GPIO, PPK2, hai phiên xen kẽ, CI95 |
| Điểm chia đo trên phần cứng | Một mạng con đầu | Đủ 11 điểm cắt s0–s10 của cùng một mô hình |
| Phía edge | Board thứ hai chỉ để nhận | KV260 chạy tail INT8 trên DPU thật; t_edge và E_wait đo theo hàng đợi |
| Mô hình năng lượng | FLOPs làm đại diện | E_dev, E_tx(B), E_wait(t_wait), P_conn, kiểm bằng số đo: E_tx tuyến tính theo byte (R² 0,996); E_dev,on ≈ E_dev,off + 0,7 mW × t_dev khớp phần lõi trong 1,03 % ở mọi s ≥ 2, số thô lệch giữa các ngày tới khoảng 15 % do REG0 (tuần 10, trên main) |
| Chia dữ liệu | 70/15/15, nhiều khả năng trong bệnh nhân | DS1/DS2 giữa các bệnh nhân (de Chazal) |
| Riêng tư | Lập luận định tính | Tấn công tái tạo và tái định danh có cận trên (tấn công ghép, gộp k nhịp), kết quả âm có kiểm chứng |
| Thích nghi | Chọn EEP offline bằng GA, ngưỡng tự tin cố định | Controller chọn điểm cắt và trạng thái radio lúc chạy (đang phát triển, G5) |
| Nén | Encoder–decoder học được ở EEP | Nén cố định ở đầu vào: S0c (46 giá trị, Rice; thân TB khoảng 36 B) là S0 chuẩn; bộ nén cố định ở S1 đã thử. Không có encoder học được ở điểm cắt; P3 chờ cổng K |
| Early exit | Có | Không (ASI bản 2 và 3: không làm) |

**Điểm phải thừa nhận thẳng trong bài** (giữ từ bản 20/11, sửa theo nén):
- DCentNet có encoder học được ở điểm chia và có early exit. Mô hình của nhóm chỉ có nén cố định ở đầu vào (S0c, và S1 đã thử), không có encoder học được, không có early exit.
- Kết luận về điểm cắt giữa của nhóm chỉ đúng cho điểm cắt không có encoder học được. Không được viết như thể nó bác bỏ DCentNet.
- Phần lớn mức giảm dữ liệu gửi của DCentNet đến từ việc dừng sớm, không phải từ việc chia mô hình.

## 3. Đoạn khác biệt (tiếng Anh, cho Section II)

> The closest prior work in hardware and data is DCentNet [Li et al., BSPC 2025], which also runs the first part of an ECG CNN on an nRF52840-based board (Arduino Nano 33 BLE Sense), sends features over BLE, measures current with a PPK2 and evaluates on MIT-BIH. DCentNet partitions the network at early-exit points with a learned encoder that compresses the feature map, chooses the exit positions offline with a genetic algorithm over accuracy, sensitivity and FLOPs, and reports average current per operating mode for one deployed sub-network, with a second board acting only as a receiver. Our work differs in four respects. First, we measure energy per phase (head, protection, transmission, waiting) with GPIO markers, in two interleaved sessions with confidence intervals, rather than mode-averaged current. Second, we measure all 11 split points of the same model on the device instead of a single deployed configuration. Third, the remaining layers run on a real edge accelerator (an INT8 DPU on a KV260), so the waiting time and its energy on the device are measured, including their dependence on the edge queue. Fourth, the per-phase energy model, with transmission energy linear in payload bytes, waiting energy linear in waiting time and connection power, and device energy predicted from the radio-off measurement plus a constant radio power, is checked against these measurements rather than approximated by FLOPs. We also split MIT-BIH between patients and evaluate privacy against reconstruction and re-identification attacks, which DCentNet discusses only qualitatively. Compression in our system is fixed rather than learned: the standard full-offload action sends a reduced, Rice-coded beat (about 36 B), and a fixed compressor at the first split was also evaluated, but no split point has a learned encoder and there is no early exit. Our conclusions about intermediate splits therefore concern partitions without a learned encoder; a learned encoder at the split, as in DCentNet, is a different design point that our results do not rule out.

Ghi chú:
- "Two interleaved sessions with confidence intervals" và "device energy predicted from the radio-off measurement plus a constant radio power" lấy theo báo cáo tuần 10 của SV1. Khi viết bản cuối cần trỏ đúng số chính thức (1,03 %, R² 0,996) và nêu lệch giữa các ngày do REG0 trong phần đo, không trong related work.
- Câu "a fixed compressor at the first split was also evaluated" theo review 25/11 của SV1. Mình chưa có số của phép thử S1 trong nhánh của mình. Cần SV1 cho đường dẫn kết quả để trích đúng.

## 4. Bài IEEE Sensors J 2024 của cùng nhóm

X. Li, B. Cardiff, D. John, "A two-stage ECG classifier for decentralized inferencing across edge-cloud continuum", *IEEE Sensors Journal* 24(14), 2024, doi 10.1109/JSEN.2024.3406780.

- Ngày 27/11 mình chưa lấy được toàn văn: không có bản arXiv; bản IEEE cần quyền truy cập.
- Theo phần tóm tắt công khai:
  - Bài chia hai tầng. Tầng 1 trên thiết bị đeo là explainable boosting machine, độ phức tạp thấp. Tầng 2 trên cloud là CNN.
  - Ngưỡng của tầng 1 điều chỉnh được để đổi chất lượng lấy lưu lượng mạng, và có thể thay đổi lúc chạy theo điều kiện thực.
  - Thí nghiệm dùng MIT-BIH.
- Điều này liên quan trực tiếp tới ý "thích nghi lúc chạy" của nhóm. Vì vậy **chưa chốt dòng Table I và chưa viết câu so sánh nào** với bài này cho tới khi đọc toàn văn (hướng dẫn tuần 11–24, mục 5.2: đọc toàn văn trước khi viết câu so sánh).
- Cần: người dùng hoặc SV1 lấy PDF qua thư viện trường.

## 5. Dòng Table I (nháp, chỉ DCentNet)

| Work | Platform / link | Data | Split / adaptation | Energy evaluation | Privacy |
|---|---|---|---|---|---|
| Li et al., DCentNet (BSPC 2025) | Arduino Nano 33 BLE Sense (nRF52840), BLE; second board as receiver | MIT-BIH MLII, 5 AAMI classes, 70/15/15 split | 1–2 early-exit points with learned feature encoder; exit positions by GA offline; fixed confidence threshold | PPK2, average current per mode; FLOPs as complexity | Qualitative only |

Các cột này còn đổi theo yêu cầu của hướng dẫn mục 5.2: hành động radio BLE, năng lượng phần cứng theo pha, controller trên MCU, ràng buộc dữ liệu. Việc này làm cùng Table I bản nháp.

## 6. Chưa làm

- Chưa đối chiếu bản BSPC đã đăng với arXiv v1.
- Chưa đọc toàn văn bài IEEE Sensors J 2024.
- Chưa xem repo GitHub của DCentNet (`microa/DCentNet`) để biết số byte gửi ở EEP.
