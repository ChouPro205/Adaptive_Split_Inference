# Contracts

Nơi quản lý hợp đồng giao diện I1-I4, packet format, schema, versioning và test vector dùng chung giữa device, edge và ML.

## Đặc tả hiện hành cho triển khai mới (tuần 6)

| Tài liệu | Trạng thái / phạm vi |
|---|---|
| [I1 v2](i1_device_edge_packet_v2.md) | **Nguồn hiện hành của I1.** `protocol_version=2`: `model_profile_id` trên wire, request thường hoặc I2/1, thứ tự xử lý lỗi, response `SCORE_VECTOR`. Thiết kế Châu duyệt 15/10/2026; chưa triển khai, chưa `FROZEN`. |
| [I1 BLE binding v1](i1_ble_binding_v1.md) | Transport BLE dùng chung laptop/KV260: GATT, fragment, reassembly, timeout/retry, duplicate cache, chế độ echo. Thiết kế duyệt; chưa triển khai. |
| [I2/1 nonce và provisioning v1](i2_nonce_provisioning_v1.md) | Dải sequence lưu NVS trên `storage_partition`, provisioning key qua USB CDC. Thiết kế duyệt; persistence vẫn `NOT_ACCEPTED`. |
| [I2/1](i2_protection_v1.md) | Biến đổi đảo ngược activation INT8 (không phải mã hóa); không đổi. |
| [Approved registry](sv3_week5_approved_registry_v2.json) và [allocation](sv3_week5_allocation_v2.md) | Model profile, split ID 256..266, key/sender, trần buffer. |

Reference/test host của I1 v2, BLE binding và mô hình nonce:
[`i1v2_ref/`](i1v2_ref/test_i1v2.py) (`python -B contracts/i1v2_ref/test_i1v2.py`).
Kế hoạch và tiêu chí nghiệm thu: [tuần 6](../docs/week6_device_edge_plan.md).

## Tài liệu lịch sử (giữ nguyên byte, không dùng cho triển khai mới)

| Tài liệu | Trạng thái / phạm vi |
|---|---|
| [I1 v1](i1_device_edge_packet_v1.md) | `REVIEW_CANDIDATE`, `protocol_version=1`; thay bằng I1 v2 cho triển khai mới. Giữ nguyên vì nằm trong receipt lịch sử. |
| [I1 v1 addendum r1](i1_device_edge_packet_v1_addendum_r1.md) | Deployment profile cho v1; các mục OPEN đã đóng trong I1 v2 §13. |
| [I1 v2 proposal](i1_device_edge_packet_v2_proposal.md) | Đề xuất ban đầu; được thay bằng [I1 v2](i1_device_edge_packet_v2.md). |
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
