# Adaptive Split Inference

Adaptive Split Inference là dự án nghiên cứu hệ thống suy luận thích nghi được phân chia giữa thiết bị đầu cuối và edge. Mục tiêu là đo lường, lựa chọn và thực thi điểm chia mô hình phù hợp với tài nguyên, độ trễ, năng lượng và điều kiện truyền thông.

## Cấu trúc và trách nhiệm

- `device`: firmware nRF52840 Dongle PCA10059 của SV1.
- `edge`: KV260, Tail DNN, queue và server của SV2.
- `ml`: mô hình, lượng tử hóa và protection của SV3.
- `contracts`: hợp đồng giao diện I1-I4, packet format và test vector dùng chung.
- `experiments`: cấu hình thí nghiệm, dữ liệu đo đã xử lý và kết quả.
- `results`: kết quả đo, bảng tổng hợp và hình minh chứng, chia theo tuần
  (`results/weekN/device` của SV1, `results/weekN/edge` của SV2); dữ liệu raw được
  giữ cục bộ.
- `docs`: tài liệu kỹ thuật, tiến độ và báo cáo.
- `tools`: công cụ dùng chung của nhóm.

Thiết bị đầu cuối hiện tại là Nordic nRF52840 Dongle PCA10059 revision 2.1.1. Firmware dùng nRF Connect SDK v3.4.0 LTS với board target `nrf52840dongle/nrf52840`; không dùng biến thể `/bare`.

Mỗi thành viên chỉ chỉnh sửa phần thuộc trách nhiệm của mình và phối hợp thay đổi giao diện qua `contracts`. Không commit build cache, dataset lớn, model artifact lớn, file khóa, `.env` hoặc thông tin bí mật.

Project này không tự động flash thiết bị. Quy trình nạp firmware phải được thực hiện ở một bước riêng sau khi artifact được kiểm tra.

## Môi trường firmware

- nRF Connect SDK v3.4.0 LTS, Zephyr 4.4.0.
- Board target: `nrf52840dongle/nrf52840` (không dùng biến thể `/bare`).
- Toolchain và quy trình chi tiết được mô tả trong
  [`device/README.md`](device/README.md).

## Build firmware

Chạy từ Git root. Build Active và tạo gói USB DFU:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week1_demo.ps1
```

Build Idle dùng cho phép đo dòng nền Week 2:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week2_idle.ps1
```

Hai script chỉ build và tạo artifact; thao tác DFU/flash là bước riêng.

## Tái tạo phân tích Idle

Khi file raw đang có ở máy cục bộ:

```powershell
python .\tools\analyze_week2_idle.py .\results\week2\device\raw\2026-09-22_idle_vbus5v_60s.csv
```

Raw CSV/PPK2 và build artifact được Git ignore. Summary và hình minh chứng vẫn
được theo dõi để kết quả có thể kiểm tra mà không đưa dữ liệu raw lớn lên Git.

## Tài liệu

- [PR25 R1/R2: bảo toàn header và setup bốn ZIP](ml/docs/week5_pr25_r1r2_20261012.md):
  logs mới và gate portable; registry/SV1 evidence vẫn BLOCKED, REVIEW_STATUS=PENDING.
- [SV3 tuần 5: implementation và verification](ml/docs/week5_technical_20261009.md):
  kết quả lịch sử. [Allocation đã duyệt và final acceptance v3](contracts/sv3_week5_allocation_v2.md)
  là luồng hiện hành cho testbed ASI/MIT-BIH; runtime transport/provisioning còn mở.
- [Kiểm tra checkout hiện tại trước tuần 5](ml/docs/week4_current_verification.md):
  entrypoint ML dùng chung policy xác thực với device, tách rõ snapshot lịch sử.
- [Báo cáo SV1/Device Week 4: 11 splits FP32](docs/sv1_device_week4_report.md)
- [Bằng chứng MCU Week 4](results/week4/device/README.md) và
  [hydrate/tái kiểm sau tích hợp R4](docs/sv1_device_week4_report.md#12-phụ-lục-hydrate-tái-kiểm-build-và-chạy-lại-firmware-tuần-4): source ML
  có fix R4, phép đo chính thức giữ provenance R3 ngày 02/10/2026.
- [Báo cáo SV1/Device Week 1](docs/sv1_device_week1_report.md)
- [Báo cáo SV1/Device Week 2](docs/sv1_device_week2_report.md)
- [Báo cáo SV1/Device Week 3](docs/sv1_device_week3_report.md)
- [Báo cáo SV1/Device Week 5](docs/sv1_device_week5_report.md) và
  [kết quả MCU Week 5](results/week5/device/README.md)
- [Báo cáo SV1/Device Week 6: BLE Device–laptop, P1 C và nonce](docs/sv1_device_week6_report.md) và
  [kết quả Dongle Week 6](results/week6/device/README.md)
- [Kết quả đo Week 2](results/week2/device/README.md)
- [Đặc tả Device–Edge hiện hành (I1 v2, BLE binding, nonce)](contracts/README.md)
  và [tiêu chí tuần 6](docs/sv1_device_week6_report.md#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-d1d6)
- [Mục lục tài liệu](docs/README.md)

- [SV2/Edge tuần 7: packet I1 v2 từ file đến KV260](docs/sv2_edge_week7_report.md),
  [source service](edge/server/week7/README.md) và [kết quả](results/week7/edge/README.md).

- [SV2/Edge tuần 8: BLE G2 và hồ sơ bổ sung PHY](docs/sv2_edge_week8_report.md), [kết quả](results/week8/edge/README.md).
