# DCentNet: đọc toàn văn và đoạn khác biệt (related work)

Ngày 20/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`. Đây là bản nháp, chưa review.

Việc này theo tin SV1 ngày 19/11, mục 6: đọc kỹ toàn văn DCentNet, kiểm DOI, rồi viết đoạn khác biệt. SV1 nêu bốn ý cần có: đo theo pha có marker, quét đủ 11 điểm cắt, edge DPU thật, và mô hình năng lượng được kiểm bằng số đo.

## 1. Nguồn và trạng thái xuất bản

- **Bản đã đọc:** toàn văn arXiv 2502.17446v1 (bản HTML, 31/01/2025).
- **Bản đã đăng:** X. Li, B. Huang, B. Cardiff, D. John, "DCentNet: Decentralized multistage biomedical signal classification using early exits", *Biomedical Signal Processing and Control*, vol. 104, art. 107468, tháng 6/2025, doi 10.1016/j.bspc.2024.107468.
  - Đã kiểm qua Crossref: trùng tiêu đề, trùng 4 tác giả.
  - Bản ghi arXiv cũng trỏ đến DOI này.
  - **Nên trích bản đã đăng.**
- **Chưa kiểm được:** nội dung bản đã đăng có trùng arXiv v1 không, vì bản Elsevier không truy cập được. Các số dưới đây lấy từ arXiv v1.
- **Một bài liên quan cần xét cho Table I:** cùng nhóm tác giả có X. Li, B. Cardiff, D. John, "A two-stage ECG classifier for decentralized inferencing across edge-cloud continuum", *IEEE Sensors Journal* 24(14), 2024, doi 10.1109/JSEN.2024.3406780. DCentNet trích bài này cho chỉ số DtC. Mình chưa đọc.

## 2. DCentNet làm gì (theo arXiv v1)

| Mặt | DCentNet |
|---|---|
| Ý chính | Chia một CNN thành 2–3 mạng con bằng early-exit point (EEP). Mỗi EEP có cặp encoder–decoder nén feature map trước khi gửi. Nhịp nào đủ tự tin ở EEP thì dừng, không gửi tiếp |
| Chọn điểm chia | Thử mọi vị trí EEP: 5 vị trí cho 1 EEP, 10 tổ hợp cho 2 EEP trên mạng 6 lớp conv. Chọn bằng giải thuật di truyền, hàm mục tiêu là tổng có trọng số của accuracy, sensitivity và FLOPs. Đây là thiết kế offline, không thích nghi lúc chạy |
| Dữ liệu | MIT-BIH, MLII, 5 lớp AAMI, nhịp 260 mẫu (resample từ 360 Hz). Chia 70/15/15 % cho train/val/test, không nêu là chia theo bệnh nhân, nên nhiều khả năng là **trong bệnh nhân** (cùng người ở cả train và test) |
| Phần cứng | Arduino Nano 33 BLE Sense (Cortex-M4, chip trên board là nRF52840). Đầu vào FP32. Chỉ mạng con đầu (khoảng 2 lớp, khoảng 70 KB) chạy trên board. Bên nhận là một Nano 33 khác nối PC, **không có edge thực hiện phần còn lại của mạng trên phần cứng** |
| Đo năng lượng | PPK2. Chỉ báo **dòng trung bình (mA) theo chế độ**: inference-only 0,74; sleep 0,58; BLE connected 3,66; broadcast 3,20; "Ours" 1,07–1,79 (connected) và 0,79–0,94 (broadcast) theo ngưỡng 0,5–0,9. Dùng 500 nhịp mỗi ngưỡng. Không tách theo pha, không có marker, không có CI |
| Độ phức tạp | Tính bằng FLOPs (khoảng 220–262k so với 303k của mạng gốc). Không đo năng lượng tính toán theo lớp, không có giá mỗi byte gửi qua BLE |
| Kết quả chính | 1 EEP: giảm 94,54 % dữ liệu gửi và 21 % FLOPs. 2 EEP: accuracy 97,74 %, sensitivity 98,36 %. Tiết kiệm trung bình 73,6 % công suất so với truyền BLE liên tục |
| Riêng tư | Chỉ lập luận định tính (xử lý tại chỗ thì ít dữ liệu nhạy cảm bị gửi đi). Không có tấn công, không có thước đo |

## 3. Khác biệt với bài của nhóm

| Mặt | DCentNet | Nhóm mình |
|---|---|---|
| Đo năng lượng | Dòng trung bình theo chế độ, cho một cấu hình | Năng lượng theo từng pha (HEAD, PROT, TX, WAIT), tách bằng marker GPIO, PPK2, hai phiên xen kẽ, CI95 |
| Điểm chia đo trên phần cứng | Một mạng con đầu | Đủ 11 điểm cắt s0–s10 của cùng một mô hình |
| Phía edge | Board thứ hai chỉ để nhận | KV260 chạy tail INT8 trên DPU thật; t_edge và E_wait đo theo hàng đợi |
| Mô hình năng lượng | FLOPs làm đại diện | E_dev, E_tx(B), E_wait(t_wait), P_conn, kiểm bằng số đo (E_tx tuyến tính theo byte, R² 0,996; E_dev khi radio bật lệch ≤ 2 % ở s ≥ 2, số tuần 10 trên main) |
| Chia dữ liệu | 70/15/15, nhiều khả năng trong bệnh nhân | DS1/DS2 giữa các bệnh nhân (de Chazal) |
| Riêng tư | Lập luận định tính | Tấn công tái tạo và tái định danh có cận trên (tấn công ghép), kết quả âm có kiểm chứng |
| Thích nghi | Chọn EEP offline bằng GA, ngưỡng tự tin cố định | Controller chọn điểm cắt và trạng thái radio lúc chạy (đang phát triển, G5) |
| Nén ở điểm chia | Có (encoder–decoder ở EEP) | Không. Tensor giữa luôn ≥ 362 B nên điểm cắt giữa thua gửi thô; đường nén P3 còn chờ cổng |
| Early exit | Có | Không (ASI bản 2: không làm) |

**Điểm phải thừa nhận thẳng trong bài:**
- DCentNet có nén feature ở điểm chia và có early exit; mô hình của nhóm không có cả hai. Vì vậy kết luận "điểm cắt giữa thua gửi thô" của nhóm chỉ đúng cho mô hình không nén ở điểm cắt. Không được viết như thể nó bác bỏ DCentNet.
- Phần lớn mức giảm dữ liệu gửi của DCentNet đến từ việc dừng sớm, không phải từ việc chia mô hình.

## 4. Đoạn khác biệt (tiếng Anh, cho Section II)

> The closest prior work in hardware and data is DCentNet [Li et al., BSPC 2025], which also runs the first part of an ECG CNN on an nRF52840-based board (Arduino Nano 33 BLE Sense), sends features over BLE, measures current with a PPK2 and evaluates on MIT-BIH. DCentNet partitions the network at early-exit points with an encoder that compresses the feature map, chooses the exit positions offline with a genetic algorithm over accuracy, sensitivity and FLOPs, and reports average current per operating mode for one deployed sub-network, with a second board acting only as a receiver. Our work differs in four respects. First, we measure energy per phase (head, protection, transmission, waiting) with GPIO markers, in two interleaved sessions with confidence intervals, rather than mode-averaged current. Second, we measure all 11 split points of the same model on the device instead of a single deployed configuration. Third, the remaining layers run on a real edge accelerator (an INT8 DPU on a KV260), so the waiting time and its energy on the device are measured, including their dependence on the edge queue. Fourth, the per-phase energy model, with transmission energy linear in payload bytes, waiting energy linear in waiting time and connection power, is checked against these measurements rather than approximated by FLOPs. We also split MIT-BIH between patients and evaluate privacy against reconstruction and re-identification attacks, which DCentNet discusses only qualitatively. Unlike DCentNet, our model has no compressing encoder and no early exit at the split points; our finding that intermediate splits lose to sending the raw beat applies to such uncompressed partitions, and compression at the split is the mechanism by which DCentNet reduces transmission.

Ghi chú về câu "two interleaved sessions with confidence intervals": số phiên và cách xếp lấy theo báo cáo tuần 10 của SV1; khi viết bản cuối cần trỏ đúng số liệu chính thức.

## 5. Dòng cho Table I (nháp)

| Work | Platform / link | Data | Split / adaptation | Energy evaluation | Privacy |
|---|---|---|---|---|---|
| Li et al., DCentNet (BSPC 2025) | Arduino Nano 33 BLE Sense (nRF52840), BLE; second board as receiver | MIT-BIH MLII, 5 AAMI classes, 70/15/15 split | 1–2 early-exit points with feature encoder; exit positions by GA offline; fixed confidence threshold | PPK2, average current per mode; FLOPs as complexity | Qualitative only |

## 6. Chưa làm

- Chưa đối chiếu bản BSPC đã đăng với arXiv v1.
- Chưa đọc bài IEEE Sensors J 2024 của cùng nhóm.
- Chưa xem repo GitHub của DCentNet (`microa/DCentNet`) để biết kích thước encoder và số byte gửi ở EEP. Bài không ghi rõ số byte.
