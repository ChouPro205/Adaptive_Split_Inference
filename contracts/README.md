# Contracts

Nơi quản lý hợp đồng giao diện I1-I4, packet format, schema, versioning và test vector dùng chung giữa device, edge và ML.

| Tài liệu | Trạng thái / phạm vi |
|---|---|
| [I1 v1](i1_device_edge_packet_v1.md) | `REVIEW_CANDIDATE`; packet Device–Edge v1, chưa cho phép transformed payload. Bản gốc giữ nguyên vì nằm trong receipt lịch sử. |
| [I1 v1 addendum r1](i1_device_edge_packet_v1_addendum_r1.md) | Deployment profile theo approved registry: logical/wire split, `model_profile_id`, s10 empty-tail, metadata INT8, miền `q∈[-127,127]` (từ chối −128 ở mức tensor lượng tử); các điểm còn OPEN. Không đổi wire v1. |
| [I2/1](i2_protection_v1.md) | Quy cách kỹ thuật SV1 đã chốt cho biến đổi đảo ngược activation INT8; chưa tích hợp thiết bị/Edge. |
| [I1 v2 proposal](i1_device_edge_packet_v2_proposal.md) | Đề xuất wire riêng để mang I2/1, chưa được SV2 duyệt hoặc triển khai. |
| [I3 input](I3_SV3_input.md) | SV3 góp ý LUT; schema/số đo vẫn mở. |
| [Bàn giao SV3 → SV1 Tuần 3](sv3_sv1_week3_model_handoff.md) | Gói FP32 `mitdb-week3-fp32-20260925-v2` verify PASS, boundary P2 đã được SV3/SV1 xác nhận; SV1 package review PASS, P2 trên MCU 20/20 PASS (28/09/2026), bảng 20 × 5 hoàn tất (30/09/2026). |

Mã tham chiếu Python/C và vector I2 nằm trong [`i2_ref/`](i2_ref/test_i2.py).

[SV3 to SV2 Week 3 FP32](sv3_sv2_week3_fp32.md): confirmed s=0..10 mapping and opset 13; ten FP32 ONNX tails, SV2 hardware validation pending.

## Quyết định SV3 tuần 5 hiện hành

[Allocation v2](sv3_week5_allocation_v2.md): Châu đã duyệt testbed ASI/MIT-BIH,
revision `mitdb-week5-i2-registry-v1-r1`; final verifier v3 kết hợp science,
approved registry và offline SV1 compatibility. Registry baseline và decision
notes v1/v2 là hồ sơ lịch sử. Runtime provisioning/nonce persistence/transport
chưa nghiệm thu; I1 tiếp tục REVIEW_CANDIDATE.
