# SV3 Model/Privacy — báo cáo tuần 9 (30/10–08/11/2026)

Người lập: SV3. Nhánh `dev/ml-sv3`. Báo cáo tổng hợp, viết ngày 21/11/2026 từ các tài liệu ngày lẻ đã chuyển vào [`sv3_archive/`](sv3_archive/README.md) và các hồ sơ trong `ml/provenance/`. Tuần 9 tính từ 30/10, ngày bắt đầu chặng M1 ngay sau báo cáo tuần 8.

**Tóm tắt.** Làm lại phần dữ liệu và baseline theo hướng dẫn tuần 9–13 (bản 1.2):
- chia MIT-BIH thành DS1/DS2 theo bệnh nhân (de Chazal);
- khóa protocol baseline v4 và chạy lưới 18 slot;
- chọn cấu hình C5 và khóa checkpoint triển khai;
- dựng gói A ứng viên;
- soạn protocol NoPeek v1 và protocol tấn công v1, kèm bản nháp threat model.

DS2 chưa mở.

## 1. Dữ liệu M1: DS1/DS2 theo bệnh nhân (30/10)

- Chia lại dữ liệu theo de Chazal:
  - DS1 gồm 22 bản ghi để huấn luyện và chọn cấu hình;
  - DS2 gồm 21 bản ghi cho đánh giá chính (bỏ 202, vì 201 và 202 là cùng một người), cộng một dòng phụ đủ 22 bản ghi;
  - loại các bản ghi có máy tạo nhịp.
- Thêm kiểm tra rò rỉ bệnh nhân, gộp 201 và 202 thành một danh tính. Sau bước chia lại, train, validation và test không còn chung bệnh nhân. Cách chia 75/15/10 của tuần 1 không theo DS1/DS2.
- Tập validation gồm 4 bản ghi nguyên vẹn của DS1, chọn bằng quy tắc viết trước (seed 20261030). Cấu hình ở `ml/configs/mitdb_ds1ds2_m1_v3.json`.
- Có báo cáo nguồn (de Chazal 2004, PhysioNet, tổng quan 2025, EC57) và bảng truy vết yêu cầu sang hiện vật.
- Qua ba vòng review của SV1, protocol baseline đi từ ứng viên v1 đến v3.

## 2. Baseline v4, lưới 18 slot và checkpoint C5 (03–05/11)

- **Protocol v4** sửa theo review v3 của SV1:
  - sampler cân bằng trên 4 lớp N, S, V, F;
  - báo cáo DS2 một lần sau khi khóa;
  - luật dừng khi gặp lỗi code;
  - gate S là gate mềm.

  File `ml/configs/mitdb_m1_baseline_protocol_v4.json`, SHA-256 `7f9eb564176f1a14e521c91e464f4fb79eb77b792e6be69fd884374b8b471e18`. File khóa và cho phép train: `ml/provenance/m1-v4-lock-20261103/`.
- **Lưới 18 slot** (6 cấu hình × 3 seed): cả 18 slot chạy xong ở lần thử đầu, exit 0, không slot nào cần chạy lại.
- **Chọn C5** (sampler cân bằng, lr 0,0003):
  - mean macro-F1 trên 3 seed: 0,5129;
  - seed triển khai 20261101, epoch 4, macro-F1 validation **0,568222**;
  - gate N, V, S đều đạt.
- **Checkpoint triển khai:** SHA-256 `fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c`.
  - Chạy lại C5 một lần theo yêu cầu của SV1: ra đúng từng byte, 21/21 file khớp (`ml/provenance/m1-v4-c5-rerun-20261105/`).
  - File khóa checkpoint: `ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json`, SHA-256 `6848b08dc1f4f55d7d66a4e36b719d55c92eabf37b0c6edbbfdd6b921047d0bc`. Đăng Release ngày 05/11.

## 3. Gói A ứng viên và script DS2 (05/11)

- Dựng gói A (checkpoint, chuẩn hóa, golden tensor s0–s9 của 1.000 nhịp calibration, dự đoán tham chiếu) mà không dùng DS2: `ml/provenance/m1-v4-package-a-20261105/`.
- Script báo cáo DS2 FP32 chỉ chạy thử trên validation, không chạm DS2: `ml/provenance/m1-v4-ds2-script-20261105/`.

## 4. NoPeek v1 và protocol tấn công v1 (05/11)

- **Protocol NoPeek v1** (`ml/configs/mitdb_m1_nopeek_protocol_v1.json`, SHA-256 `1e180b45…72ebf4`):
  - lưới λ ∈ {0; 0,1; 0,5; 1; 2; 5} × 3 seed, khởi tạo từ C5;
  - ngưỡng tiện ích 0,95 × macro-F1 của A.

  Có runner và smoke trên dữ liệu giả.
- **Protocol tấn công v1** (`ml/configs/mitdb_m1_attack_protocol_v1.json`, SHA-256 `86917047…19b5a0`):
  - edge "trung thực nhưng tò mò";
  - tấn công tái tạo A1–A3 và tái định danh B;
  - Π = 1 − Adv tính theo balanced accuracy, Π_min = 0,5;
  - chia theo thời gian trong mỗi bản ghi.

  Kèm bản nháp threat model đầu tiên.

## 5. Phụ thuộc và việc chuyển sang tuần 10

- SV1 review gói C5 ngày 05/11. PR #44 (squash) vào `main` ngày 09/11.
- Gói A giao cho SV2 ở tuần 10.
- NoPeek và tấn công chuyển sang tuần 10, sau khi SV1 review v1.

## 6. Tài liệu chi tiết

| Ngày | Tài liệu |
|---|---|
| 30/10 | [Bàn giao chặng 1, ứng viên M1](sv3_archive/sv3_m1_audit_20261030.md); [nguồn và bảng đối chiếu](sv3_archive/sv3_m1_sources_20261030.md); [truy vết yêu cầu](sv3_archive/sv3_m1_traceability_20261030.md) |
| 30/10 | [Đối chiếu 9 câu trả lời SV1 (v2)](sv3_archive/sv3_m1_v2_decisions_20261030.md); [review v2](sv3_archive/sv3_m1_v2_review_20261030.md); [review v3](sv3_archive/sv3_m1_v3_review_20261030.md) |
| 03/11 | [Protocol v4](sv3_archive/sv3_m1_v4_review_20261103.md); [kết quả lưới 18 slot](sv3_archive/sv3_m1_v4_grid_result_20261103.md) |
| 05/11 | [NoPeek v1](sv3_archive/sv3_m1_nopeek_v1_review_20261105.md); [tấn công v1 và nháp threat model](sv3_archive/sv3_attack_protocol_threat_model_draft_20261105.md) |

Hồ sơ: `ml/provenance/m1-ds1ds2-20261030/`, `m1-v2-20261030/`, `m1-v3-20261030/`, `m1-v4-20261103/`, `m1-v4-lock-20261103/`, `m1-v4-grid-analysis-20261103/`, `m1-v4-checkpoint-lock-20261105/`, `m1-v4-release-20261105/`, `m1-v4-package-a-20261105/`, `m1-nopeek-v1-code-20261105/`.
