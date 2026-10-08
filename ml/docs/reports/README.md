# Báo cáo SV3 ML tuần 1–4

Bốn báo cáo tiến độ SV3 nằm tại [`docs/` ở thư mục gốc](../../../docs/README.md).

| Tuần | Báo cáo | Nội dung |
|---|---|---|
| 1 | [SV3 ML Week 1 Report](../../../docs/SV3_ML_week1_report.md) | Môi trường, dữ liệu MIT-BIH/PTB-XL, preprocessing, patient split và verification |
| 2 | [SV3 ML Week 2 Report](../../../docs/SV3_ML_week2_report.md) | Baseline CNN, training configuration, kết quả và provenance lịch sử |
| 3 | [Báo cáo tiến độ SV3 tuần 3](../../../docs/sv3_ml_week3_report.md) | Freeze, 20 mẫu/golden, head/tail, ONNX, review và nghiệm thu SV1/SV2 |
| 4 | [Báo cáo tiến độ SV3 tuần 4](../../../docs/sv3_ml_week4_report.md) | Profiling 11 splits, Figure 2, tham số/C99, R2→R3→R4 và trạng thái máy nhận/MCU |

Đây là bốn báo cáo tiến độ, không thay bằng audit/release notes. Báo cáo
tuần 1–2 giữ nguyên tên và nội dung lịch sử; báo cáo tuần 3–4 lập ngày
05/10/2026, chốt bằng chứng trên main `076719a` sau PR17/18/19.
SV3 FP32/profiling offline và SV1 MCU R3 đã có bằng chứng PASS trong phạm
vi đã kiểm. Full verifier Linux, SV2/KV260, ACK chính thức và MCU/timing
của build SV1 mới còn chờ; không coi merge hoặc upload là nghiệm thu.

## Tài liệu bổ trợ

- [Release và review bàn giao SV1 tuần 3](../week3_release.md)
- [Audit và numerical handoff all-split tuần 3](../week3_sv2_split_audit.md)
- [Review profiling tuần 4 ban đầu](../SV3_ML_week4_review.md)
- [Audit R2/R3](../week4_review2_audit.md) và [completion R3](../week4_r3_completion.md)
- [Audit inventory R4](../week4_inventory_order_fix.md) và [completion R4](../week4_r4_completion.md)
- [Handoff R4 cho SV1/SV2](../sv3_sv1_week4_handoff_r4.md)
- [Báo cáo SV1 tuần 4 và provenance phép đo R3](../../../docs/sv1_device_week4_report.md)

Audit/receipt/release lịch sử giữ trạng thái tại thời điểm phát hành;
hai báo cáo tiến độ mới ghi riêng trạng thái hiện tại và giới hạn evidence.
