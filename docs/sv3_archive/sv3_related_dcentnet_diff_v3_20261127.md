# DCentNet: đoạn khác biệt (related work), bản 3

Ngày 27/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`. Đây là bản nháp, chờ SV1 đọc lại.

Bản này sửa bản 2 ([`sv3_related_dcentnet_diff_v2_20261127.md`](sv3_related_dcentnet_diff_v2_20261127.md), giữ nguyên) theo mục 5 tin 27/11 của SV1 (`ml/provenance/m1-sv1-evidence-20261127/`, SHA `696f3309…`). Phần đọc toàn văn DCentNet (mục 1–2 của bản 20/11) không đổi, nên không chép lại.

## 1. Những gì sửa so với bản 2

| Chỗ | Bản 2 | Bản này |
|---|---|---|
| Câu về bộ nén ở S1 trong đoạn tiếng Anh | "a fixed compressor at the first split was also evaluated" | Chỗ trống `[K]`, điền sau quyết định K ngày 13/12: hoặc kết quả cổng K đo ở lab tuần 12, hoặc P3 (tin 27/11 mục 5b) |
| Số S1 trong bảng tiếng Việt | Chưa có nguồn | Trích khảo sát 20/11 (Hướng xử lý ASI bản 3, trang 2–3; kết quả trên main ở `results/week11/device/analysis/compression-20261120/`). Chỉ dùng trong bảng nội bộ, không trích làm kết quả của bài |
| Số byte S0c | "about 36 B" | 36,4 B trung bình trên DS1 validation, theo cách ghi nguồn của threat model bản 3 |
| Bài IEEE Sensors J 2024 | Chưa đọc toàn văn | Đã đọc toàn văn (mục 4); có dòng Table I và câu khác biệt |
| Bài NEWCAS 2023 | Chưa có trong danh sách | Đã đọc toàn văn (mục 5); có dòng Table I. SV1 thêm vào danh sách đọc ngày 27/11 |
| Đoạn tiếng Anh | Chỉ so với DCentNet | Thêm hai câu về hai bài trước của cùng nhóm, và một câu phân biệt tỉ lệ nhịp gửi đi của họ với ràng buộc Y của nhóm |

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
| Nén | Encoder–decoder học được ở EEP | Nén cố định ở đầu vào: S0c (46 giá trị, Rice; thân TB 36,4 B trên DS1 val) là S0 chuẩn. Bộ nén cố định ở S1 (S1F v1, `contracts/s1f_v1_ref` trên main): khảo sát 20/11 trên DS1 val cho 46 B với macro-F1 0,5619 và 20 B với 0,3517 (mốc 0,5398); chưa khóa, không trích làm kết quả. Không có encoder học được ở điểm cắt; P3 chờ cổng K |
| Early exit | Có | Không (ASI bản 2 và 3: không làm) |

**Điểm phải thừa nhận thẳng trong bài** (giữ từ bản 2):
- DCentNet có encoder học được ở điểm chia và có early exit. Mô hình của nhóm chỉ có nén cố định (S0c ở đầu vào; S1 cố định tùy quyết định K), không có encoder học được, không có early exit.
- Kết luận về điểm cắt giữa của nhóm chỉ đúng cho điểm cắt không có encoder học được. Không được viết như thể nó bác bỏ DCentNet.
- Phần lớn mức giảm dữ liệu gửi của DCentNet đến từ việc dừng sớm, không phải từ việc chia mô hình. Bài NEWCAS 2023 xác nhận điều này: con số "giảm 60 % dữ liệu gửi" của bài đó chính là tỉ lệ nhịp dừng ở exit (60 % ở ngưỡng 0,9), không phải tỉ lệ nén của encoder (mục 5).

## 3. Đoạn khác biệt (tiếng Anh, cho Section II)

> The closest prior work in hardware and data is DCentNet [Li et al., BSPC 2025], which also runs the first part of an ECG CNN on an nRF52840-based board (Arduino Nano 33 BLE Sense), sends features over BLE, measures current with a PPK2 and evaluates on MIT-BIH. DCentNet partitions the network at early-exit points with a learned encoder that compresses the feature map, chooses the exit positions offline with a genetic algorithm over accuracy, sensitivity and FLOPs, and reports average current per operating mode for one deployed sub-network, with a second board acting only as a receiver. It builds on two earlier studies of the same group: a 1D-CNN with one early exit and an encoder–decoder at the exit, evaluated by FLOPs only [NEWCAS 2023], and a two-stage cascade in which a feature-based classifier on the device forwards the beats it flags as abnormal to a CNN in the cloud [IEEE Sensors J. 2024]. In both, the share of beats sent is set by a confidence or decision threshold swept offline, and energy is estimated from per-operation and per-bit constants rather than measured. Our work differs in four respects. First, we measure energy per phase (head, protection, transmission, waiting) with GPIO markers, in two interleaved sessions with confidence intervals, rather than mode-averaged current. Second, we measure all 11 split points of the same model on the device instead of a single deployed configuration. Third, the remaining layers run on a real edge accelerator (an INT8 DPU on a KV260), so the waiting time and its energy on the device are measured, including their dependence on the edge queue. Fourth, the per-phase energy model, with transmission energy linear in payload bytes, waiting energy linear in waiting time and connection power, and device energy predicted from the radio-off measurement plus a constant radio power, is checked against these measurements rather than approximated by FLOPs. We also split MIT-BIH between patients and evaluate privacy against reconstruction and re-identification attacks, which these works discuss only qualitatively or not at all. The fraction of beats kept on the device is, in our system, a long-term constraint ($\ge p$) that the controller maintains while it chooses the split point and the radio state at run time, not a by-product of a classification threshold. Compression in our system is fixed rather than learned: the standard full-offload action sends a reduced, Rice-coded beat (36.4 B on average, Section III) `[K]`, but no split point has a learned encoder and there is no early exit. Our conclusions about intermediate splits therefore concern partitions without a learned encoder; a learned encoder at the split, as in DCentNet, is a different design point that our results do not rule out.

Ghi chú:
- `[K]` thay câu "and a fixed compressor at the first split was also evaluated" của bản 2. Sau 13/12 điền một trong hai: kết quả cổng K đo ở lab tuần 12 (S1 cố định), hoặc P3. Nếu K đóng thì bỏ chỗ trống, câu vẫn đúng ngữ pháp.
- Câu "rather than measured" về hai bài trước dựa trên toàn văn: bài NEWCAS chỉ báo FLOPs; bài Sensors J ước tính năng lượng bằng hằng số MAC của ASIC 28 nm và 143 nJ/bit cho BLE lấy từ tài liệu khác, thời gian chạy trên thiết bị tính từ số chu kỳ trên nRF5340 giả định.
- Câu về tỉ lệ nhịp giữ tại chỗ dùng "controller maintains" vì controller đang phát triển (G5). Nếu bài nộp trước khi G5 xong thì SV1 quyết có giữ câu này không.
- "Two interleaved sessions with confidence intervals" và "device energy predicted from the radio-off measurement plus a constant radio power" lấy theo báo cáo tuần 10 của SV1. Khi viết bản cuối cần trỏ đúng số chính thức (1,03 %, R² 0,996) và nêu lệch giữa các ngày do REG0 trong phần đo, không trong related work.

## 4. Bài IEEE Sensors J 2024 (đã đọc toàn văn)

X. Li, B. Cardiff, D. John, "A two-stage ECG classifier for decentralized inferencing across edge-cloud continuum", *IEEE Sensors Journal* 24(14), pp. 23324–23335, 2024, doi 10.1109/JSEN.2024.3406780. Bản mở theo giấy phép CC BY-NC-ND 4.0. Bản PDF người dùng tìm ngày 27/11 giữ cục bộ, SHA-256 `fd5ff0f8f2aa752a03ad052cccf47fd7f12fbaa26d85ff1fbb804b9426fbabf1`, không đưa vào repo.

- **Cách chia:** hai mô hình khác nhau nối tiếp nhau, không chia một mạng. Tầng 1 trên thiết bị là explainable boosting machine phân loại nhị phân (bình thường/bất thường) trên 32 đặc trưng: 26 mẫu lấy thưa từ phức bộ QRS, 4 khoảng thời gian, 2 biên độ/cực tính (trích bằng ecgpuwave). Nhịp bị báo bất thường được gửi nguyên (260 mẫu) lên CNN 10 lớp trên cloud để phân 5 lớp AAMI. Không gửi đặc trưng trung gian.
- **Tham số điều khiển:** ngưỡng EBM quyết định tỉ lệ dữ liệu gửi lên cloud (DtC). Bài gọi ngưỡng là tham số điều khiển theo điều kiện thực, nhưng chỉ quét offline 100 giá trị ngưỡng; không có controller, không xét pin, kênh hay hàng đợi.
- **Phần cứng:** không chạy trên MCU. Thời gian tầng 1 tính từ số chu kỳ trên nRF5340 giả định ở 64 MHz (khoảng 2,5 ms). Năng lượng ước tính: MAC 16 bit 0,39 pJ trên ASIC 28 nm FD-SOI, BLE 143 nJ/bit lấy từ tài liệu khác. Độ trễ theo mô hình L = DtC · L_c + L_e. Không có số đo.
- **Dữ liệu:** MIT-BIH, 5 lớp AAMI. Chia theo nhịp: 70/30 cho tầng 1, 70/15/15 cho tầng 2. Bài tự nói train và test không tách theo người.
- **Kết quả nêu trong bài:** gửi khoảng 41 % nhịp lên cloud thì độ chính xác và độ nhạy hệ thống khoảng 98 %; ước tính giảm năng lượng truyền khoảng 3 lần.
- **Riêng tư:** chỉ nhắc trong phần mở đầu như một lý do để xử lý tại thiết bị; không đánh giá.
- **Liên quan tới nhóm:** DtC gần với tỉ lệ nhịp gửi đi (1 − p) trong ràng buộc Y. Khác biệt: ở bài này tỉ lệ gửi là hệ quả của ngưỡng phân loại theo nội dung nhịp, chọn offline; ở nhóm là ràng buộc dài hạn do controller giữ, đồng thời chọn điểm cắt và trạng thái radio. Bài không có điểm cắt giữa nào, nên không so được ở mặt chia mạng.

## 5. Bài NEWCAS 2023 (đã đọc toàn văn)

X. Li, H. Vandierendonck, D. S. Nikolopoulos, B. Ji, B. Cardiff, D. John, "Decentralised biomedical signal classification using early exits", *21st IEEE Interregional NEWCAS Conference*, 2023, doi 10.1109/NEWCAS57931.2023.10198098. Bài 2 trang. Bản PDF mở lấy từ par.nsf.gov (`servlets/purl/10537792`) ngày 27/11, SHA-256 `4d48f1a6b93867481c594a76bea294442b62e84faf5dabdf9879d8a3ba73eb78`, giữ cục bộ, không đưa vào repo.

- **Cách chia:** 1D-CNN của cùng nhóm (ICECS 2020), sửa stride và kernel hai lớp đầu. Thêm một early exit ở một trong hai vị trí; hai vị trí được đánh giá riêng. Ở exit có cặp encoder–decoder Conv1d để thu nhỏ feature map gửi sang tầng sau. Bài không nêu số byte hay tỉ lệ nén của encoder trong phần chữ.
- **Quyết định dừng:** so xác suất lớn nhất trong 5 lớp với một ngưỡng (0,6–0,97), quét offline.
- **"Giảm 60 % dữ liệu gửi":** là tỉ lệ nhịp dừng ở exit 1 với ngưỡng 0,9 (exit rate 60 %), không phải tỉ lệ nén. Ở cấu hình đó độ chính xác 97,55 %, độ nhạy 98,45 %, FLOPs trung bình giảm 38,45 %.
- **Phần cứng:** không có. Chỉ báo FLOPs.
- **Dữ liệu:** MIT-BIH, 5 lớp AAMI, 70/15/15; bài không nói chia theo người.
- **Riêng tư, controller lúc chạy:** không có.
- **Quan hệ với DCentNet:** cùng tác giả chính và cùng ý early exit có encoder–decoder ở exit, nhiều khả năng là tiền thân của DCentNet (như SV1 nhận định). Bài không tự nói điều này, nên đoạn tiếng Anh chỉ viết "earlier studies of the same group".

## 6. Dòng Table I (nháp)

| Work | Platform / link | Data | Split / adaptation | Energy evaluation | Privacy |
|---|---|---|---|---|---|
| Li et al., NEWCAS 2023 | None (simulation) | MIT-BIH, 5 AAMI classes, 70/15/15 split (not stated as inter-patient) | One early exit (two candidate positions) with encoder–decoder; max-probability threshold swept offline | FLOPs only | Not evaluated |
| Li et al., IEEE Sensors J. 2024 | nRF5340 assumed (cycle count); BLE energy from literature; cloud CNN | MIT-BIH, 5 AAMI classes; beat-level 70/30 and 70/15/15 split | Two-stage cascade of different models (EBM on device, CNN in cloud); flagged beats sent raw; threshold swept offline | Estimated: 28 nm ASIC MAC energy, 143 nJ/bit BLE; latency model | Motivation only |
| Li et al., DCentNet (BSPC 2025) | Arduino Nano 33 BLE Sense (nRF52840), BLE; second board as receiver | MIT-BIH MLII, 5 AAMI classes, 70/15/15 split | 1–2 early-exit points with learned feature encoder; exit positions by GA offline; fixed confidence threshold | PPK2, average current per mode; FLOPs as complexity | Qualitative only |

Các cột vẫn còn đổi theo yêu cầu của hướng dẫn mục 5.2 (hành động radio BLE, năng lượng phần cứng theo pha, controller trên MCU, ràng buộc dữ liệu). Việc này làm cùng Table I bản nháp ở `local_only/`.

## 7. Chưa làm

- Chưa đối chiếu bản BSPC đã đăng với arXiv v1.
- Chưa xem repo GitHub của DCentNet (`microa/DCentNet`) để biết số byte gửi ở EEP.
- Số byte của encoder trong bài NEWCAS chỉ có thể đọc từ kích thước trong hình 1; chưa trích vì phần chữ không nêu.
