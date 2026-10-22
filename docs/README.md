# Documentation

Nơi lưu tài liệu kiến trúc, hướng dẫn kỹ thuật, tiến độ, quyết định thiết kế
và báo cáo của dự án.

## Báo cáo tiến độ

### Khối Thiết bị (SV1 - Device / Châu)
- [Báo cáo SV1/Device (Châu) – Week 1](sv1_device_week1_report.md)
- [Báo cáo SV1/Device (Châu) – Week 2](sv1_device_week2_report.md)
- [Báo cáo SV1/Device (Châu) – Week 3](sv1_device_week3_report.md)
- [Báo cáo SV1/Device (Châu) – Week 4](sv1_device_week4_report.md)
- [Báo cáo SV1/Device (Châu) – Week 5](sv1_device_week5_report.md): sinh tự
  động khi nghiệm thu ngày 09/10/2026 và giữ nguyên từng byte vì hash của nó
  nằm trong hồ sơ nghiệm thu. Wire split ID được cấp sau đó, ngày 15/10/2026,
  trong [allocation hiện hành](../contracts/sv3_week5_allocation_v2.md).
- [Kết quả và hình minh chứng Week 2](../results/week2/README.md)
- [Kết quả MCU và timing Week 4](../results/week4/README.md)
- [Kết quả MCU Week 5](../results/week5/README.md)
- [Receipt tuần 5 cho source hiện tại](../ml/provenance/week5-current-20261015/README.md)
  và [đánh giá theo lớp](../ml/results/week5-per-class-20261015/README.md)
- [Firmware và công cụ SV1](../device/README.md)
- [Báo cáo SV1/Device (Châu) – Week 6](sv1_device_week6_report.md): 8 tiêu chí phía
  Device PASS trên Dongle qua BLE ngày 19/10/2026, peer là laptop Windows; tiêu chí,
  quyết định D1–D6, việc còn mở của SV2/SV3 và quy trình lab nằm trong phụ lục
- [Kết quả Dongle Week 6](../results/week6/README.md)

### Khối ML (SV3 - ML / Bùi Kỳ Anh)
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 1](SV3_ML_week1_report.md)
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 2](SV3_ML_week2_report.md)
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 3](sv3_ml_week3_report.md)
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 4](sv3_ml_week4_report.md)
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 5](sv3_ml_week5_report.md): INT8/FP16,
  P1 Python, accuracy 8.544 x 11, allocation/final acceptance PR25
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 6](sv3_ml_week6_report.md): 50 vector
  P1 thật, C/Python và output host; tiếp nhận MCU SV1 được ghi riêng
- [Báo cáo SV3/ML (Bùi Kỳ Anh) – Week 7](sv3_ml_week7_report.md): dCor,
  NoPeek smoke offline và cấu hình tuần 8; không thay nghiệm thu KV260
- [Checklist phụ thuộc SV3 tuần 7](sv3_week7_dependency_checklist.md)
- [SV3: sửa verifier FP32 tuần 3 trên Ubuntu/WSL](sv3_ml_week3_linux_fp32_fix_report.md)
- [SV3 Linux FP32 review v2: bảo toàn provenance và recipe](sv3_ml_week3_linux_fp32_review_v2_report.md)
- [SV3 → SV2: bàn giao Week 3 FP32 Linux](sv3_sv2_week3_linux_fp32_handoff.md)
- [Mục lục và tài liệu bổ trợ SV3](../ml/docs/reports/README.md)

### Khối Máy chủ biên (SV2 - Edge / KV260)
- [Báo cáo SV2/Edge – Week 1](sv2_edge_week1_report.md)
- [Báo cáo SV2/Edge – Week 2](sv2_edge_week2_report.md)
- [Báo cáo SV2/Edge – Week 3](sv2_edge_week3_report.md)
- [Báo cáo SV2/Edge – Week 4](sv2_edge_week4_report.md)

## Quy ước đặt tên báo cáo

Báo cáo mới dùng dạng `<sinh_vien>_<mang>_weekN_report.md`, ví dụ
`sv1_device_weekN_report.md`, `sv2_edge_weekN_report.md` và
`sv3_ml_weekN_report.md`. Quy ước này không yêu cầu đổi tên tài liệu lịch sử của
thành viên khác.

Tài liệu chuyên biệt cho firmware nằm tại
[`device/README.md`](../device/README.md); tài liệu pipeline ML nằm tại
[`ml/docs/`](../ml/docs/).

## Tài liệu kỹ thuật bổ trợ SV3

Báo cáo SV3 tuần 5–7 và checklist được quản lý tập trung ở `main/docs/`.
Phần code/evidence tuần 7 chưa merge, theo dõi riêng tại
[PR #34](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/34).

Các báo cáo tiến độ tuần 5–7 nằm ở `docs/` phía trên. Hồ sơ kỹ thuật và receipts
được dẫn tới vị trí gốc để giữ nguyên bằng chứng:

- [Delivery và allocation tuần 5](../ml/docs/week5_delivery_v2.md).
- [Gói 50 vector P1 tuần 6](../ml/docs/week6_p1_delivery.md): A+B host PASS ngày
  16/10; SV1 MCU/BLE PASS ngày 19/10 được ghi trong báo cáo tuần 6 tại root docs;
  KV260 còn chờ bằng chứng riêng. Không sửa tài liệu bàn giao ngày 16/10 để đổi lịch sử.
- [Code/kết quả smoke tuần 7](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/results/week7-nopeek/README.md).
