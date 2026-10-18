# Firmware SV1 — nRF52840 Dongle PCA10059

Thư mục này chứa firmware và công cụ của SV1 cho Nordic nRF52840 Dongle
PCA10059 revision 2.1.1 (Cortex-M4F, 64 MHz, 1 MB Flash, 256 KB RAM). Môi
trường: nRF Connect SDK v3.4.0 LTS (Zephyr 4.4.0), target duy nhất:

```text
nrf52840dongle/nrf52840
```

Quy ước chung cho mọi chế độ:

- Không dùng biến thể `/bare`, không dùng `west flash`, không erase/recover.
  Nạp qua bootloader USB DFU có sẵn của dongle (nhấn RESET/SW2, LED đỏ nhấp nháy mờ).
- Build bằng West với `--no-sysbuild` vì cấu hình West cục bộ mặc định bật sysbuild.
- Script build chỉ build và đóng gói; nạp DFU và thu dữ liệu là các bước riêng,
  luôn chỉ định cổng COM thực tế vừa phát hiện (COM6/COM7 trong báo cáo chỉ là
  cổng của phiên đo đó).
- Console là USB CDC ACM; UART0 vật lý bị tắt trong `app.overlay`.

## Các chế độ firmware

| Chế độ | Chọn bằng | Mã nguồn chính | Build | Hướng dẫn / kết quả |
|---|---|---|---|---|
| Active (tuần 1–2): LED heartbeat, benchmark DWT, tự kiểm marker | `prj.conf` (mặc định) | `src/main.c` | `scripts/build_week1_demo.ps1` | [DFU và chạy demo](week1_dfu_demo_guide.md), [báo cáo tuần 1](../docs/sv1_device_week1_report.md) |
| Idle (tuần 2): đo dòng nền bằng PPK2 | `overlay-idle.conf` làm `CONF_FILE` | `src/main_idle.c` | `scripts/build_week2_idle.ps1` | [kết quả tuần 2](../results/week2/README.md) |
| Đầu FP32 đến P2 (tuần 3) | `overlay-week3.conf` | `src/main_week3.c`, `src/week3_head.c` | `scripts/build_week3_head.ps1` | [hướng dẫn tuần 3](week3_fp32_guide.md), [kết quả](../results/week3/) |
| 11 điểm cắt FP32, gói R3 (tuần 4) | `overlay-week4.conf` | `src/main_week4.c`, `src/week4_head.c`, `src/week4_protocol.c` | `scripts/build_week4_head.ps1` | [hướng dẫn tuần 4](week4_fp32_guide.md), [kết quả](../results/week4/README.md) |
| Lượng tử hóa INT8 + scale FP16 (tuần 5) | ứng dụng riêng `week5/` | `week5/main.c`, `week5/quantization.c` (dùng lại kernel/giao thức tuần 4) | `scripts/build_week5_head.ps1` | [hướng dẫn tuần 5](week5_prepare_guide.md), [kết quả](../results/week5/README.md) |
| BLE Device–Edge (tuần 6: firmware đầy đủ đã build và kiểm trên host, chưa chạy trên dongle) | ứng dụng riêng `week6/`, biến thể `default`/`mtu23` | `week6/main.c` | `scripts/build_week6.ps1` | [README tuần 6](week6/README.md), [runbook lab](week6/RUNBOOK.md), [kế hoạch](../docs/week6_device_edge_plan.md) |

Bốn chế độ đầu dùng chung `CMakeLists.txt`/`Kconfig` của thư mục này; CMake
chọn đúng một entry point theo Kconfig. Ứng dụng tuần 5 có `CMakeLists.txt`
riêng và được build qua `build_week5_head.ps1`: CMake yêu cầu `week5_build.h`
(định danh firmware), file này do `bind_week5_build.py` sinh ra ở thư mục
ngoài repo sau khi xác thực gói ML.

`P2` trong tài liệu tuần 3–4 là tên **mốc tensor** sau `MaxPool1d` đầu tiên
(`1×16×180`, trùng split `s=2`), không phải chế độ bảo vệ P2 của kế hoạch nghiên cứu.

## Cấu trúc thư mục

- `src/markers.c`, `src/markers.h`: bốn GPIO marker cho PPK2, ghi trực tiếp
  thanh ghi `OUTSET/OUTCLR`: D0 = P0.13 `HEAD`, D1 = P0.15 `PROTECTION`,
  D2 = P0.17 `TX`, D3 = P0.20 `WAIT`. Firmware Active chạy tự kiểm cả bốn
  marker; firmware tuần 3–5 mới bật/tắt `HEAD` quanh phần tính head.
- `src/`, `week5/`: mã nguồn firmware như bảng trên.
- `scripts/`: công cụ theo tuần. Tiền tố cho biết vai trò: `build_*` build và
  đóng gói, `flash_*` nạp USB DFU, `collect_*` thu dữ liệu qua CDC, `check_*`
  kiểm capture ngoại tuyến, `verify_*` kiểm trên host, `test_*` kiểm thử âm,
  `generate_*` sinh header input/graph từ gói ML đã xác thực, `inspect_*`
  kiểm ELF/map/bộ nhớ tĩnh, `analyze_*`/`summarize_*` tổng hợp bằng chứng,
  `accept_*`/`publish_*` nghiệm thu tuần 5. Ngoài ra:
  - `check_env.ps1`: kiểm môi trường NCS (kết quả trong `reports/environment_check.txt`);
  - `check_existing_modes.ps1`: build hồi quy Active và Idle vào thư mục riêng;
  - `nrf_terminal.ps1`: mở terminal đã nạp biến môi trường NCS (dùng trong cấu hình VS Code cục bộ);
  - `diagnose_week3_serial.ps1`, `diagnose_week3_pyserial.py`, `probe_week3_bulk.py`:
    công cụ chẩn đoán lỗi USB CDC tuần 3, được dẫn trong bảng bằng chứng
    [`reports/week3_build.md`](reports/week3_build.md).
- `reports/`: hồ sơ gốc tuần 1 và tuần 3. `results/week3/` giữ bản sao trùng
  byte của biên bản và JSON tuần 3; cả hai vị trí đều đang được tài liệu khác dẫn tới.
- `generated/`, `build*/`, `artifacts/`: bị Git ignore. `build-week3/`,
  `build-week4/` và các ZIP trong `artifacts/` chứa đúng image đã nạp và đo,
  hash ghi trong báo cáo; không xóa hoặc build đè lên chúng.

## File đang bị khóa bởi bằng chứng

- `preparation.json` của tuần 5 lưu hash của `week5/*`, `src/week4_head.*`,
  `src/week4_protocol.*`, `src/markers.*`, `generated/week4_*.h` và mọi
  `scripts/*week5*`. Sửa, xóa hoặc thêm file vào `week5/` làm
  `verify_week5_package.py` và `accept_week5_mcu.py` FAIL khi tái kiểm.
- `flash_week4_head.ps1` đối chiếu hash của `CMakeLists.txt`, `Kconfig`,
  `overlay-week4.conf` và mã nguồn tuần 4 với hồ sơ build trước khi nạp lại
  image tuần 4.
- Vì vậy firmware tuần mới nên là một ứng dụng riêng, dùng lại các module trên
  qua đường dẫn như `week5/CMakeLists.txt` đang làm, thay vì sửa trực tiếp.

## Build nhanh

Từ Git root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week1_demo.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week2_idle.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\check_env.ps1
```

Lệnh đầu build Active vào `device\build` và tạo
`device\artifacts\adaptive_split_week1_demo.zip`; lệnh thứ hai build Idle vào
`device\build-idle` và tạo `device\artifacts\adaptive_split_week2_idle.zip`.
Hai lệnh này ghi đè build/ZIP Active/Idle cũ theo chủ ý để chuyển qua lại giữa
hai chế độ; gói lịch sử `adaptive_split_base_v1.zip` không bị đụng tới. Các
script tuần 3–5 thì từ chối ghi đè image đã đo và yêu cầu thư mục output mới.

## Đo thời gian và các giới hạn đã chốt cho tuần 6

- t_dev của tuần 4 là thời gian của **cách hiện thực hiện tại**: kernel vòng
  lặp C FP32, build `CONFIG_SIZE_OPTIMIZATIONS=y` (`-Os`), DWT 64 MHz, khóa
  IRQ trong từng lần gọi head, chỉ mẫu 0. Đổi kernel, mức tối ưu, kiểu dữ liệu
  (INT8) hay phương pháp đo thì phải đo lại; không dùng t_dev này làm chi phí cố
  định của mô hình.
- Khóa IRQ suốt một lần gọi head (tới khoảng 2,4 s ở `s=8..10`) chỉ dùng cho
  firmware debug USB. Ứng dụng có radio không lấy cách này làm thiết kế mặc
  định; số đo khi đó sẽ gồm cả chi phí xử lý ngắt.
- Cấp phát key và lưu nonce bền qua reboot/mất điện vẫn `NOT_ACCEPTED` theo
  registry cho tới khi có triển khai và kiểm tra tương ứng.
- Firmware tuần 3–5 đã nghiệm thu được giữ nguyên; lỗi parser cũ của
  `main_week3.c` (phần còn lại của dòng quá dài được xử lý như lệnh mới) không
  ảnh hưởng luồng đang dùng nên không sửa.
- Profile INT8 của I1 theo [addendum r1](../contracts/i1_device_edge_packet_v1_addendum_r1.md);
  kiểm biên bằng `scripts/test_i1_profile.py --compiler <gcc>`.
- Firmware tuần 6 theo [I1 v2](../contracts/i1_device_edge_packet_v2.md),
  [BLE binding](../contracts/i1_ble_binding_v1.md) và
  [nonce/provisioning](../contracts/i2_nonce_provisioning_v1.md); làm ứng dụng
  riêng `week6/`, image phải kết thúc trước `0xDC000` (vùng NVS). Tiêu chí:
  [kế hoạch tuần 6](../docs/week6_device_edge_plan.md).

## Benchmark DWT của firmware Active

Firmware Active đo vòng lặp rỗng 10.000 lần lặp bằng bộ đếm chu kỳ DWT
`CYCCNT`: 20 lần warm-up, 20 lần đo, in min/max/trung bình/độ lệch và chỉ
báo `PASS` khi `(max − min) / trung bình < 1%`. Benchmark chạy lại mỗi khi mở
terminal (tín hiệu DTR); khi terminal vẫn mở, firmware in trạng thái mỗi 5 giây.
Phép đo này chỉ kiểm tra cơ chế đếm chu kỳ, không phải thời gian suy luận.
