# Dự thảo xác nhận ML I1 v2 — chờ Kỳ Anh review

**DRAFT / CHƯA KÝ / CHƯA PHÊ DUYỆT.** Chuẩn bị ngày 26/10/2026 cho Bùi Kỳ Anh,
SV3 — Model/Privacy. Hồ sơ này không thay xác nhận/chữ ký của các owner: Kỳ Anh, Châu, Trung hoặc GVHD.
Không sửa contract §14, registry `NOT_ACCEPTED` hoặc revision nonce/provisioning.

## Nội dung đề nghị Kỳ Anh xem xét xác nhận

Phạm vi ML được đối soát trên baseline `mitdb_week2_cnn_v1`, checkpoint SHA-256
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`, model package
manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.
Registry `mitdb-week5-i2-registry-v1-r1`, profile `1296651265`, wire split IDs
256…266, gói P1 manifest
`d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36`.

1. Wire tensor NCL `[1,C,L]`, INT8 đối xứng q∈[-127,127], zero-point 0, scale
   per-channel thuộc **kênh gốc**. Scale là FP16 normal dương đã lưu/reload,
   mở rộng chính xác FP32. Unprotect trước → kiểm q=-128 → dequantize cuối.
   Byte 0x80 trong transformed payload không bị coi là q=-128 trước unprotect.
2. s0…s8 giữ NCL cho tail; s9 reshape `[1,32,1]`→NC `[1,32]`, không đổi thứ tự.
   s10 diagnostic là 5 logits identity sau giải lượng tử; không chạy/nạp tail_s10.
3. Response `SCORE_VECTOR/FLOAT32`, 5 raw logits **N,S,V,F,Q**, hữu hạn,
   không softmax. Dự đoán là argmax, hòa chọn chỉ số nhỏ nhất. Adapter nội bộ
   DPU có requantization riêng; giới hạn q của I1 không bị đổi theo miền DPU.
4. Phần host P1 A+B/reference và input raw đã được kiểm. Hồ sơ file pipeline
   SV2 trên KV260 có 50 request, 46 native root CPU+DPU +4 identity, chỉ 5 ECG
   validation khác nhau. Tái kiểm bảng JSON cho 50/50 class agreement mỗi
   backend; max-abs HOST `1.430511474609375e-6`, KV260 `0.40645813941955566`.
   Không xem 50 cặp sample/split là 50 ECG độc lập hoặc accuracy DPU.

Nội dung này chỉ đề nghị xác nhận **tensor/quantization/response của baseline
đã nêu**, dựa trên evidence đúng pin. Nó không xác nhận raw response/NPY/binary
board đã được SV3 tái kiểm, numeric acceptance INT8/DPU, full-test accuracy,
BLE Device–KV260, nghiệm thu nonce/provisioning, model NoPeek mới hoặc privacy.
Parser/buffer KV260 của Trung và approval/change control của Châu có xác nhận riêng.

## Hồ sơ đi kèm và việc sau review

- Contract chuẩn: [I1 v2](../contracts/i1_device_edge_packet_v2.md), đặc biệt §6–8/14.
- Host baseline: [bàn giao P1 tuần 6](../ml/docs/week6_p1_delivery.md), generating
  commit `766a3cfa7e7828ecd00b9eb23cc3e5da4015ced5`.
- SV2 source execution công bố tại `a851a05b90827aeddcb660585bb989b0f594e39b`;
  [báo cáo SV2 tuần 7](sv2_edge_week7_report.md), main đọc tại `d91fe27`.
- Audit mới: [delivery-audit.json](../ml/provenance/week7-reconcile-20261026/delivery-audit.json),
  thực thi trên `08e4b4259a2757be7b663b88cc1c98607602d266`.
- [Đối soát và phần còn chờ](sv3_week7_reconciliation_20261026.md).

Kỳ Anh review nội dung và ghi quyết định thực tế. Nếu được xác nhận, Châu ghi
receipt/revision theo quy trình hiện hành, giữ chứng cứ và registry lịch sử.
Không điền ngày ký hoặc trạng thái APPROVED trước khi người có thẩm quyền xác nhận.

| Vai trò | Trạng thái của bản dự thảo |
|---|---|
| Kỳ Anh — ML reviewer | Chờ review/xác nhận thực tế |
| Trung — parser/buffer/runtime Edge | Chờ xác nhận riêng đúng phạm vi |
| Châu — contract/registry/change control | Không có revision/xác nhận mới trong nhiệm vụ này |
| GVHD — nghiệm thu/demo/numeric nếu cần | Chưa ghi nhận xác nhận mới |
