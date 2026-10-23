# SV1 tuần 5 — đã nghiệm thu kỹ thuật trên Dongle

Phiên `20261009-212416`; source image `51ef9c966e052bfd63c8e416dcfad3d6af30e755`. DFU thật exit 0, MCU 220/220 primary + 16/16 mixed PASS.
FP32 strict `<1e-3`, s0 bitwise, INT8/FP16 oracle và P2 tuần 3 bitwise 20/20 đều PASS. Accuracy offline đủ 8.544 × 11 đạt ngưỡng; không chạy cả tập này trên Dongle.

- [Báo cáo cho thầy](../../docs/sv1_device_week5_report.md)
- [JSON nghiệm thu và provenance](week5_mcu_validation.json)
- [220 primary cases](validation_20x11.csv) và [16 mixed cases](validation_mixed.csv)
- [Kích thước FP32/INT8/scales](tensor_sizes.csv)
- [Accuracy offline](accuracy_offline.csv)
- [Phân tích sai khác với golden SV3](golden_difference_analysis.json)

Chỉ payload INT8 giảm đúng 4×. Tổng INT8 + scale FP16 giảm tùy split; bảng chưa gồm header/I1 wire scales.
Timing, RAM/stack runtime: NOT_MEASURED. P1 C, radio và tích hợp Device–Edge chưa thực hiện; I1 chưa FROZEN.

Raw capture, DFU receipt, collection receipt và logs: `D:\HUST\ASI_week5_mcu\20261009-212416`. Binaries/build vẫn trong `D:\HUST\ASI_week5_prepare\20261009-sv1-prepare01`. Các hashes nằm trong JSON.
preparation.json giữ nguyên snapshot NOT_RUN/PENDING trước nạp; kết quả thật được ghi riêng.
Trạng thái tích hợp Git tại commit báo cáo này: chưa merge. PR, commit báo cáo, merge SHA và đối chiếu bốn refs được lưu sau tích hợp tại `D:\HUST\ASI_week5_mcu\20261009-212416\git\git_integration_final.json`.
Source của image đã đo luôn là SHA 51ef9c9 ở trên; commit báo cáo/merge không thay source SHA đó.
