# Adaptive Split Inference

Adaptive Split Inference là dự án nghiên cứu hệ thống suy luận thích nghi được phân chia giữa thiết bị đầu cuối và edge. Mục tiêu là đo lường, lựa chọn và thực thi điểm chia mô hình phù hợp với tài nguyên, độ trễ, năng lượng và điều kiện truyền thông.

## Cấu trúc và trách nhiệm

- `device`: firmware nRF52840 Dongle PCA10059 của SV1.
- `edge`: KV260, Tail DNN, queue và server của SV2.
- `ml`: mô hình, lượng tử hóa và protection của SV3.
- `contracts`: hợp đồng giao diện I1-I4, packet format và test vector dùng chung.
- `experiments`: cấu hình thí nghiệm, dữ liệu đo đã xử lý và kết quả.
- `results`: kết quả đo, bảng tổng hợp và hình minh chứng; dữ liệu raw được
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
python .\tools\analyze_week2_idle.py .\results\week2\raw\2026-09-22_idle_vbus5v_60s.csv
```

Raw CSV/PPK2 và build artifact được Git ignore. Summary và hình minh chứng vẫn
được theo dõi để kết quả có thể kiểm tra mà không đưa dữ liệu raw lớn lên Git.

## Tài liệu

- [Báo cáo Week 1](docs/week1_report.md)
- [Báo cáo Week 2](docs/week2_report.md)
- [Kết quả đo Week 2](results/week2/README.md)
- [Mục lục tài liệu](docs/README.md)
