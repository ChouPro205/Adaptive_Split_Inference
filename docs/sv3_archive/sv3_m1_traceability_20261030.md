# Truy vết yêu cầu M1 và ranh giới các chặng sau

HD = *Hướng dẫn thực hiện cho từng thành viên, tuần 9–13*, 7 trang. DX = *Đề xuất phương án cho phần ML và lịch thay checkpoint*, 5 trang. Đã đọc đủ cả hai; hash tên file gốc trong `ml/provenance/m1-ds1ds2-20261030/pdf-sources.json`. PDF là yêu cầu/thảo luận tại thời điểm soạn, không là bằng chứng trạng thái PR hiện tại.

| Yêu cầu | Tài liệu/mục/trang | Hiện vật hiện tại tại HEAD 6a8d06a | Thay đổi/chuyển tiếp | Xác minh | Trạng thái lượt này |
|---|---|---|---|---|---|
| Quyền áp dụng phương án | HD đầu p1; DX đầu p1 và §7 p5 | Không có biên bản duyệt trong nguồn đã kiểm | `approval.meeting_adoption=NOT_EVIDENCED` | Nhóm/thầy cung cấp quyết định | CHƯA KHÓA |
| Một/hai gói và lịch | DX §4–5 p4: một gói cuối tuần 12; HD §1 p1, §3 p2, §4.4/4.6 p4: A/B | Handoff tuần 3–6 thuộc checkpoint cũ | A baseline cố định cho phần cứng; B NoPeek/P2 từ tuần 14 theo HD là hướng triển khai ứng viên, cần nhóm chốt | Đối chiếu đúng hai PDF; chưa tạo A/B | KHÁC BIỆT ĐÃ GHI |
| Kiến trúc, 360, N/S/V/F/Q, s0–s10, không RR | HD §1 p1; DX §3 p2–3 | `mitdb_baseline_model.py`, `week3_model_freeze.json`, registry v2 | Giữ bytes nguồn/model/contract; config mới cấm RR | SHA bảo toàn + negative config tests | PASS BẢO TOÀN |
| M1 dữ liệu/số lớp/review | HD §3/4.1 p2–3 | Week1 ratio 75/15/10, không phải DS1/DS2 | `mitdb_ds1ds2_m1_v1.json`, manifest `mitdb-ds1ds2-m1-v1-r2/` | Verifier raw + SHA + SV1/SV2 review | CODE PASS; ỨNG VIÊN |
| DS1 22, test chính 21, loại paced | HD §4.1 p2; DX §3.1 p3 | `mitdb_patient_split.csv` cũ giữ nguyên | Manifest mới đủ 48 record, 202 aux-only | Canonical inventory; negative DS2/202/paced | PASS ỨNG VIÊN |
| Kiểm bệnh nhân, 201/202 chung người | HD §4.1 p2–3; DX §3.1 p3 | `mitdb_common.get_patient_id`, mapping tuần 1 | Canonical P201_202; main/train/val rời nhau; aux được ghi overlap | Giả patient ID + leakage tests | PASS ỨNG VIÊN |
| 4–5 val nguyên record, quy tắc viết trước | HD §4.1 p2 | Week8 loader dùng nguyên split cũ | Đề xuất 5 record, seed 20261030, >=10% S/V DS1; rank SHA256 tất định | Rebuild + đổi split với hash rebound phải fail | QUY TẮC CHỜ DUYỆT |
| MLII/114 và nhịp biên | HD §4.1 p2–3 | Week1 chọn MLII theo tên, drop [R−180,R+180) | Producer mới cùng phép cắt; audit 48 kênh | Verifier đọc hai lead riêng; sửa lead metadata phải fail | PASS RAW |
| Normalization chỉ train sau val | HD §4.1 p2–3, §4.4 p4 | Norm cũ fit train cũ | Norm mới gắn config/split/fit IDs, float64 population variance | Tính lại độc lập + đổi mean/rebind hash | PASS RAW |
| Counts N/S/V/F/Q và S từng test record | HD §4.1 p2–3 | Tuần 1/2/7 count thuộc split cũ | Counts/audit mới, giải thích 26/25 nhịp biên | Raw labels so từng nhịp, manifest/CSV | PASS RAW |
| Nguồn P04/MIT/REV25/EC57/4–6 bài | HD §4.1 p3 | References cũ chưa là audit DS1/DS2 | Báo cáo nguồn riêng, sáu bài cổ điển/deep | Locator + mức full text/partial/metadata | CÒN BẢNG ẢNH P04/CHUẨN |
| Baseline 3 seed, imbalance, macro-F1, khóa rồi DS2 | HD §4.2 p3; DX §3 p2 | Trainer tuần 2 chọn accuracy; weights none | Cần trainer/config phiên bản mới ở chặng 2 | Chốt loss/seed/zero-division trước train | NGOÀI LƯỢT NÀY |
| Golden calibration DS1, prediction hai đường | HD §4.3 p3–4 | Gói 3/5 và predictions cũ | Bản mới chỉ sau baseline khóa; 202/test cấm calibration | M1 có guard calibration; chưa sinh tensor/predictions | HOÃN CHẶNG 3 |
| Gói A đủ tám thành phần | HD §4.4 p4 | Checkpoint/head header cũ có provenance | Checkpoint, header, tensor, norm, dữ liệu, golden, predictions, README/SHA | Checklist mới sẽ theo §4.4 | HOÃN CHẶNG 3 |
| Epoch 0 có thể được chọn | HD §4.5 p4; DX §3 p3 | `run_week8_nopeek.py:188–229` bắt đầu epoch 1 | Runner phiên bản mới ở chặng 4 | Test epoch0 và reload | CHƯA THỰC HIỆN |
| Grid 54, chọn macro-F1>=0,95 baseline, min dCor | HD §4.5 p4; DX §3 p3 | Runner chọn validation CE; analyzer mean CE | Quy tắc mới, pilot val, collapse/seed-failure khóa trước | Không dùng analyzer cũ để chọn trên DS1/DS2 mới | CHƯA THỰC HIỆN |
| Hình IEEE và baseline/always-N | HD §4.5 p4; DX §3 p3 | Plot tuần 8 giữ lịch sử | Macro-F1/dCor, Times 8pt, 3,5/7,16in, PDF+600dpi PNG | QA hình ở chặng 4 | CHƯA THỰC HIỆN |
| P2/head/flash, B và attacks | HD §3 p2, §4.6–4.7 p4, §8 p7 | P1 và model cũ; chưa có evidence giải quyết head/flash mới | Cần đo flash theo s và quyết định phương pháp của SV3/thầy/SV1 | Không tự freeze head để né giới hạn | HOÃN CHẶNG 5 |
| SV2 compile/gate, SV1 VERIFY/G2, r3 ba người | HD §5–6 p5–6 | Full-test cũ reviewed trên checkpoint cũ; I1/registry v2 | Không sửa firmware/contract/r3 trong lượt này | Owner xác nhận đúng scope sau A | HOÃN CHẶNG 6 |
| Mô hình toán/controller/Lyapunov | DX §6 p5; tài liệu thầy C.2–C.4/WP-D; Khung §3.4–3.5 | Có yêu cầu/hướng dẫn; chưa xác thực một proof/controller hoàn chỉnh | Báo phần thiếu/người phụ trách trong báo cáo M1 | Không đặt định lý hoặc suy acceptance từ ML | GAP ĐÃ GHI |

HD còn nêu mất utility >5% ở §8, trong khi tiêu chí gốc thầy ở §4.5 là tổn thất <=2% và bộ chọn mới dùng macro-F1 >=95% baseline. Đây là ba điều kiện khác nhau; cần chốt metric và mẫu số ở chặng 4, không gộp thành một ngưỡng. Câu “năng lượng không phụ thuộc trọng số” trong hai PDF được dùng để sắp lịch; phép kiểm D0/D4 vẫn cần dữ liệu đo để xác nhận sau thay checkpoint.

Không suy DX §7 (PR43 chưa merge) hoặc HD §2 (PR43 đóng) thành trạng thái GitHub hiện tại. Lượt local này không truy vấn hoặc sửa PR; Git log local chỉ chứng minh các commit có sẵn trong checkout.
