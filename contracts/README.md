# Contracts

Nơi quản lý hợp đồng giao diện I1-I4, packet format, schema, versioning và test vector dùng chung giữa device, edge và ML.

| Tài liệu | Trạng thái / phạm vi |
|---|---|
| [I1 v1](i1_device_edge_packet_v1.md) | `REVIEW_CANDIDATE`; packet Device–Edge v1, chưa cho phép transformed payload. |
| [I2/1](i2_protection_v1.md) | Quy cách kỹ thuật SV1 đã chốt cho biến đổi đảo ngược activation INT8; chưa tích hợp thiết bị/Edge. |
| [I1 v2 proposal](i1_device_edge_packet_v2_proposal.md) | Đề xuất wire riêng để mang I2/1, chưa được SV2 duyệt hoặc triển khai. |
| [I3 input](I3_SV3_input.md) | SV3 góp ý LUT; schema/số đo vẫn mở. |
| [Bàn giao SV3 → SV1 Tuần 3](sv3_sv1_week3_model_handoff.md) | Gói FP32 `mitdb-week3-fp32-20260925-v2` verify PASS, boundary P2 đã được SV3/SV1 xác nhận; package review/MCU validation của SV1 PENDING. |

Mã tham chiếu Python/C và vector I2 nằm trong [`i2_ref/`](i2_ref/test_i2.py).
