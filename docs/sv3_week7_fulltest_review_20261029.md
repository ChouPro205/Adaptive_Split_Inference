# SV3 tuần 7 — tiếp nhận và review full-test KV260 ngày 29/10/2026

**E-05: đã đạt gate accuracy frozen và đã review artifact cho s2/s5/s8.** Đã nhận
đủ 25.632 output do SV2 thực thi trên KV260. Không còn chờ Trung gửi full-test
trong phạm vi ba split này. Xác nhận ML cá nhân/demo GVHD chưa được ghi nhận;
việc cập nhật này không tự ký nghiệm thu thay owner hoặc GVHD.

## Nguồn và phạm vi

Nguồn tiếp nhận là `gui_sv3_fulltest.zip`, `gui_sv3_fulltest.zip.sha256.txt`
và `summary.json` do SV2 gửi. ZIP 176.599.416 byte, SHA-256:
`e6f86a848c9d107ea300b9cf26ed07d59e2caf866a7b057b3c3bda7af08fbcf3`.
File checksum khớp; summary bên ngoài trùng bytes bản trong ZIP.
ZIP và raw outputs được lưu cục bộ, bị Git ignore; repo lưu kết quả/receipt review.

Đã kiểm 179.569 member bằng SHA-256/CRC trong ZIP 179.570 member và 384.672
binding checksum lồng nhau. Đủ 25.632 input khớp bit reference, raw row,
native runner JSON, execution log và command thành công tương ứng.

Reference manifest frozen giữ nguyên SHA-256:
`612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c`;
generation commit `08e4b4259a2757be7b663b88cc1c98607602d266`.
Baseline `mitdb_week2_cnn_v1`, checkpoint:
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Patient split, normalization và test frozen không đổi; test không dùng để train,
calibrate, chọn checkpoint hoặc chọn lambda.

Review/evaluation mới chạy tại source commit
`9b363f023204ead01e43a8103d927dff41182c29`, không phải lượt chạy board mới.
Source evaluator không đổi so với các tests ở `bed2dfc`; [evaluation mới](../ml/provenance/week7-fulltest-20261029/evaluation.json)
ghi rõ input commit, evaluator SHA, output SHA và backend provenance.
Các tests NoPeek 19/19 và reconciliation 18/18, thường và `-O`, vẫn thuộc
`bed2dfcf86a5d5e323575def5bbbb562f7ee6b51`, tái sử dụng theo source bindings.

## Gate accuracy và kết quả

Gate giữ nguyên: `200*(correct_fp32-correct_dpu) < 8544`, đủ 8.544 mẫu mỗi split,
không missing/failure. Baseline 8.393/8.544 = 98,232678%; cần ít nhất 8.351 correct.

| Split | Received/valid | Missing/lỗi | Correct | Accuracy | Drop so FP32 (điểm %) | Evaluator |
|---|---:|---:|---:|---:|---:|---|
| s2 | 8.544/8.544 | 0/0 | 8.412 | 98,455056% | -0,222378 | PASS_ACCURACY_GATE |
| s5 | 8.544/8.544 | 0/0 | 8.388 | 98,174157% | +0,058521 | PASS_ACCURACY_GATE |
| s8 | 8.544/8.544 | 0/0 | 8.389 | 98,185861% | +0,046816 | PASS_ACCURACY_GATE |

Drop âm ở s2 nghĩa là hơn baseline 19 mẫu đúng trong phép so frozen này.
Không suy rằng đã train mô hình mới hoặc đã chứng minh privacy.

| Split | Macro-F1 | Recall V | Recall S/F/Q | Agreement với full FP32 | Max-abs logit error với full FP32 |
|---|---:|---:|---|---:|---:|
| FP32 baseline | 0,382607 | 87,3239% | 0/0/0 | 8.544/8.544 | 0 |
| s2 | 0,383798 | 87,7934% | 0/0/0 | 8.497/8.544 | 5,753110 |
| s5 | 0,377261 | 82,6291% | 0/0/0 | 8.481/8.544 | 5,878110 |
| s8 | 0,375290 | 80,9859% | 0/0/0 | 8.476/8.544 | 5,878110 |

N chiếm 8.102/8.544 mẫu; S/F/Q chỉ có 13/1/2 mẫu. Accuracy tổng đạt gate nhưng
chất lượng các lớp hiếm còn hạn chế, kể cả baseline. Báo cả confusion/per-class,
macro-F1 và sai số đầy đủ trong evaluation; không sửa test/split hoặc threshold
để cải thiện bảng. Logit errors là mô tả; không tự áp gate FP32 `<1e-3` lên DPU.

## Artifact và runtime

Compiled xmodel cả ba split đúng SHA frozen; quant_info, compiler-input xmodel,
compiled xmodel, calibration golden, quantize provenance, compile manifest/logs
và arch được nối bằng hashes. Calibration đúng 20 mẫu validation của gói model,
không giao test. Checkpoint/model/version không thay đổi.

Runner source pin `8d962095a11a0e41696b9cdeac163ed0d240daed` đúng bốn source
runtime đã lưu; runner binary hash, driver hash và CPU plugin hashes nhất quán
với identity/preflight/output. Native adapter dùng layout/fix_point và
`DPU_ROUND_HALF_TO_POSITIVE_INFINITY`; logits là N/S/V/F/Q raw scores.

Runtime là root GraphRunner có CPU fallback trên KV260. Mỗi mẫu dùng một process
runner mới: thời gian command không phải steady-state profiling hoặc năng lượng.
Tên `input_2.npy` được driver dùng chung trong thư mục từng split; mọi nội dung
và shape thực tế đã đối chiếu với đúng reference. ZIP có CPU plugin hashes nhưng
không kèm bytes thư viện .so; cần lưu bổ sung nếu muốn archive tự chứa toàn bộ
runtime để tái lập. Điều đó không đòi mặc định chạy lại inference đã kiểm.

G2 200/200 và accuracy full-test có phạm vi riêng. Gói này bổ sung evidence
accuracy độc lập; không biến G2 thành accuracy, không phải phép đo năng lượng,
không chứng nhận nonce/provisioning hoặc chống tấn công privacy.

## Tiếp nhận và hồ sơ lịch sử

[Receipt SV2 nhận reference](../ml/provenance/week7-fulltest-20261029/sv2-reference-receipt.json)
ghi đúng ZIP đầu vào SHA `74775bf3ea3c6fde306e601315c32b8293d3db74fc12975515b503c406fd3429`
và manifest frozen. Vì đã có bằng chứng nhận và thực thi, trạng thái tiếp nối là
**REFERENCE_RECEIVED_OUTPUT_RETURNED_AND_REVIEWED**. Snapshot bàn giao 28/10 vẫn
giữ `READY_FOR_TRANSFER_NOT_SENT` đúng thời điểm ban đầu.

[Summary gốc SV2](../ml/provenance/week7-fulltest-20261029/sv2-summary.json) giữ nguyên
`HOST_ANALYSIS_SAVED_RAW_NOT_FORMAL_ACCEPTANCE` và
`PASS_COUNT_GATE_PENDING_SV3_ARTIFACT_REVIEW`. Review mới được ghi riêng trong
[artifact-review](../ml/provenance/week7-fulltest-20261029/artifact-review.json)
và [hồ sơ kiểm chứng](../ml/provenance/week7-fulltest-20261029/README.md);
không relabel log/receipt cũ thành chứng nhận revision mới.

## Phần còn chờ đúng người phụ trách

| Việc | Trạng thái sau tiếp nhận | Người thực hiện |
|---|---|---|
| E-05 full-test s2/s5/s8 | PASS_ACCURACY_GATE; artifact đã review, không còn thiếu output | SV3 lưu kết quả review; owner/GVHD ghi quyết định nghiệm thu theo quy trình |
| ML I1 v2 | Chưa ghi nhận xác nhận cá nhân; draft giữ CHƯA KÝ | Kỳ Anh review tensor/scale/shape/logits; Châu ghi nhận quyết định thật |
| dCor/NoPeek demo | Có code/tests/runbook; chưa ghi nhận Kỳ Anh tự demo với GVHD | Kỳ Anh và GVHD |
| r2 nonce Device | CONFIRMED trên SV1 `549aa102`; main `91827d3` vẫn PENDING_EDGE_CONFIRMATION | Châu/Trung tích hợp xác nhận đã có theo change control |

Đã đọc trực tiếp GitHub ngày 29/10: main `91827d3d9b7b1914d0330e71c2f9e7514840f802`,
nhánh SV1 `549aa1021c250c5c8319f99c35b5b6d90c9744d1`. r2 xác nhận Trung nói trực
tiếp với Châu ngày 27/10, do SV1 ghi; không cần coi là chưa có xác nhận hoặc yêu
cầu đo lại chỉ vì main chưa tích hợp. Scope r2 là nonce persistence/reboot Device;
không mở provisioning/P1 production và không sửa Edge high-water bền qua restart.
Hồ sơ này không sửa registry hoặc ký thay SV1/SV2.

Không phát hiện lỗi trong gói đòi SV1/SV2 chạy lại board để đạt gate accuracy.
Lưới dài s2/s5/s8 × lambda {0, 0.1, 0.5, 1, 2, 5} thuộc tuần 8; P2, attackers,
Π/Pareto là các giai đoạn tiếp theo. Toàn bộ tuần 7 chưa được gán DONE khi xác
nhận cá nhân và quyết định nghiệm thu tương ứng chưa được ghi nhận.
