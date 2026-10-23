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
| Active (tuần 1–2): LED heartbeat, benchmark DWT, tự kiểm marker | `prj.conf` (mặc định) | `src/main.c` | `scripts/build_week1_demo.ps1` | [báo cáo tuần 1](../docs/sv1_device_week1_report.md) (phụ lục 10: DFU và chạy demo) |
| Idle (tuần 2): đo dòng nền bằng PPK2 | `overlay-idle.conf` làm `CONF_FILE` | `src/main_idle.c` | `scripts/build_week2_idle.ps1` | [kết quả tuần 2](../results/week2/README.md) |
| Đầu FP32 đến P2 (tuần 3) | `overlay-week3.conf` | `src/main_week3.c`, `src/week3_head.c` | `scripts/build_week3_head.ps1` | [báo cáo tuần 3](../docs/sv1_device_week3_report.md) (phụ lục 13), [kết quả](../results/week3/) |
| 11 điểm cắt FP32, gói R3 (tuần 4) | `overlay-week4.conf` | `src/main_week4.c`, `src/week4_head.c`, `src/week4_protocol.c` | `scripts/build_week4_head.ps1` | [báo cáo tuần 4](../docs/sv1_device_week4_report.md) (phụ lục 12), [kết quả](../results/week4/README.md) |
| Lượng tử hóa INT8 + scale FP16 (tuần 5) | ứng dụng riêng `week5/` | `week5/main.c`, `week5/quantization.c` (dùng lại kernel/giao thức tuần 4) | `scripts/build_week5_head.ps1` | [tái lập tuần 5](#tái-lập-tuần-5), [kết quả](../results/week5/README.md) |
| BLE Device–Edge (tuần 6: 8 tiêu chí phía Device PASS trên dongle ngày 19/10/2026, peer laptop) | ứng dụng riêng `week6/`, biến thể `default`/`mtu23` | `week6/main.c` | `scripts/build_week6.ps1` | [báo cáo tuần 6](../docs/sv1_device_week6_report.md) (phụ lục B: firmware, C: quy trình lab), [kết quả](../results/week6/README.md) |
| Đo năng lượng theo pha (tuần 7: 9 tiêu chí PASS, PPK2 ngày 22/10/2026): marker D0–D4, chu kỳ CTRL→HEAD→PROT→TX→WAIT, kernel FP32 tối ưu | ứng dụng riêng `week7/`, biến thể `bench`/`energy-usb`/`energy` × kernel `fast`/`week4` | `week7/main.c`, `week7/energy_cycle.c`, `week7/head_fast.c` | `scripts/build_week7.ps1` | [báo cáo tuần 7](../docs/sv1_device_week7_report.md) (phụ lục C: quy trình lab PPK2), [kết quả](../results/week7/README.md); công cụ `scripts/week7_ppk2.py`, `scripts/measure_energy.py`, `scripts/energy_phases.py` |

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
  Marker thứ năm D4 = P0.22 `CTRL` (tuần 7, cạnh P0.20 trên mép castellated) nằm ở
  `week7/marker_ctrl.c` vì `src/markers.c` đang bị khóa hash.
- `src/`, `week5/`, `week6/`, `week7/`: mã nguồn firmware như bảng trên. Từ tuần 5 mỗi tuần là
  một ứng dụng Zephyr riêng, dùng lại module tuần trước qua đường dẫn và biên dịch nguyên vẹn.
  `week7/head_fast.c` `#include` nguyên vẹn `src/week4_head.c` để hai kernel dùng chung trọng số
  (`static` trong `head_parameters.h`, 438,6 KB) thay vì nhân đôi Flash.
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
- `generated/`, `build*/`, `artifacts/`, `host/.venv`: bị Git ignore, chỉ có trên máy local.
  Giữ lại `build/` (Active), `build-idle/` (Idle), `build-week3/`, `build-week4/`, các ZIP và
  capture trong `artifacts/`: đó là image đã nạp và đo, hash ghi trong báo cáo; không xóa hoặc
  build đè lên chúng. Các build kiểm/hồi quy chưa nạp (`build-*-check`, `build-ml-env-check`,
  `build-pre-week5-cleanup*`, `build-week3-regression`, `build-week4-r3-recheck*`) đã xóa ngày
  19/10/2026; script build tạo lại khi cần. `generated/` phải giữ vì test tuần 4–5 đọc trực tiếp.
- Hướng dẫn chạy từng tuần nằm trong phụ lục của báo cáo tuần tương ứng ở `docs/`; tuần 5 ở
  mục [Tái lập tuần 5](#tái-lập-tuần-5) vì báo cáo tuần 5 bị khóa hash.

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

## Đo thời gian và các giới hạn đã chốt (áp dụng từ tuần 6)

- t_dev của tuần 4 là thời gian của **cách hiện thực hiện tại**: kernel vòng
  lặp C FP32, build `CONFIG_SIZE_OPTIMIZATIONS=y` (`-Os`), DWT 64 MHz, khóa
  IRQ trong từng lần gọi head, chỉ mẫu 0. Đổi kernel, mức tối ưu, kiểu dữ liệu
  (INT8) hay phương pháp đo thì phải đo lại; không dùng t_dev này làm chi phí cố
  định của mô hình.
- Khóa IRQ suốt một lần gọi head (tới khoảng 2,4 s ở `s=8..10`) chỉ dùng cho
  firmware debug USB. Ứng dụng có radio không lấy cách này làm thiết kế mặc
  định; số đo khi đó sẽ gồm cả chi phí xử lý ngắt.
- Cấp phát key và lưu nonce bền qua reboot/mất điện: đã triển khai và kiểm PASS trên dongle
  (tiêu chí 7 tuần 6). Registry `mitdb-week5-i2-registry-v1-r1` vẫn ghi `NOT_ACCEPTED` cho tới khi
  có revision mới do Châu và Trung xác nhận `device_revision = edge_revision`.
- Tuần 7: energy image cấp phát trước khối nonce lúc boot (một lần ghi NVS, một xung D1 trước
  self-test) để không chu kỳ đo nào ghi Flash; mỗi lần boot chạy tối đa 1023 chu kỳ P1.
  Sau phiên đo image energy vẫn quảng bá lại (`week6/ble_link.c` khởi động advertising khi connection được giải
  phóng); không chạm 100 chu kỳ đo, sửa ở tuần 8. `E_tx`/`E_wait` phụ thuộc vị trí dongle so với laptop.
- Firmware tuần 3–5 đã nghiệm thu được giữ nguyên; lỗi parser cũ của
  `main_week3.c` (phần còn lại của dòng quá dài được xử lý như lệnh mới) không
  ảnh hưởng luồng đang dùng nên không sửa.
- Profile INT8 của I1 theo [addendum r1](../contracts/i1_device_edge_packet_v1_addendum_r1.md);
  kiểm biên bằng `scripts/test_i1_profile.py --compiler <gcc>`.
- Firmware tuần 6 theo [I1 v2](../contracts/i1_device_edge_packet_v2.md),
  [BLE binding](../contracts/i1_ble_binding_v1.md) và
  [nonce/provisioning](../contracts/i2_nonce_provisioning_v1.md); làm ứng dụng
  riêng `week6/`, image phải kết thúc trước `0xDC000` (vùng NVS). Tiêu chí và kết quả:
  [báo cáo tuần 6](../docs/sv1_device_week6_report.md).

## Benchmark DWT của firmware Active

Firmware Active đo vòng lặp rỗng 10.000 lần lặp bằng bộ đếm chu kỳ DWT
`CYCCNT`: 20 lần warm-up, 20 lần đo, in min/max/trung bình/độ lệch và chỉ
báo `PASS` khi `(max − min) / trung bình < 1%`. Benchmark chạy lại mỗi khi mở
terminal (tín hiệu DTR); khi terminal vẫn mở, firmware in trạng thái mỗi 5 giây.
Phép đo này chỉ kiểm tra cơ chế đếm chu kỳ, không phải thời gian suy luận.

## Tái lập tuần 5

Gộp từ `week5_prepare_guide.md` cũ (đã xóa ngày 19/10/2026). Không đưa vào báo cáo tuần 5 vì
báo cáo đó được giữ nguyên từng byte (hash nằm trong hồ sơ nghiệm thu). Image đã nạp và nghiệm
thu ngày 09/10/2026 (220/220 + 16/16): xem [kết quả](../results/week5/README.md) và
[báo cáo](../docs/sv1_device_week5_report.md).

Ứng dụng `week5/` dùng nguyên kernel FP32 tuần 4, tham số R3 và 20 input đã chuẩn hóa; chỉ
activation ở điểm cắt được lượng tử: INT8 đối xứng theo mẫu/kênh trên L, scale FP16
little-endian, làm tròn nearest ties-to-even. Mọi file `preparation.json` gắn hash (gồm
`week5/*`, kernel/giao thức/marker tuần 4 dùng chung và `scripts/*week5*`) phải giữ nguyên.

Chuẩn bị không cần dongle (thư mục bằng chứng và build mới, ngoài repo):

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
$sv1Evidence = 'D:\HUST\ASI_week5_prepare\NEW_RUN\checks'
$sv1Build = 'D:\HUST\ASI_week5_prepare\NEW_RUN\firmware'
& ml/.venv/Scripts/python.exe -m pip install -r device/scripts/requirements-week5-collector.txt
foreach ($stage in @('baseline','host','accuracy','regression','capture-tests','tools-check')) {
    & ml/.venv/Scripts/python.exe -B device/scripts/run_week5_preparation.py --stage $stage --output $sv1Evidence
    if ($LASTEXITCODE -ne 0) { throw "Preparation failed: $stage" }
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File device/scripts/build_week5_head.ps1 -ReportDir $sv1Build
if ($LASTEXITCODE -ne 0) { throw 'Build/audit/package failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/run_week5_preparation.py --stage memory-audit --output $sv1Evidence --build-report $sv1Build
if ($LASTEXITCODE -ne 0) { throw 'Final ELF/map audit failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/run_week5_preparation.py --stage package-tests --output $sv1Evidence --build-report $sv1Build
if ($LASTEXITCODE -ne 0) { throw 'Package corruption tests failed' }
& ml/.venv/Scripts/python.exe -B device/scripts/summarize_week5_preparation.py --output $sv1Build --evidence $sv1Evidence
if ($LASTEXITCODE -ne 0) { throw 'Preparation evidence incomplete/stale' }
```

Mỗi lệnh có receipt (lệnh, exit code) và log; output từ chối ghi đè build đã nghiệm thu. Sau khi
commit/push source đã kiểm, `summarize_week5_preparation.py --output <build> --refresh-git` ghi SHA
cuối và kiểm nhánh remote, không đổi hash artifact.

Trên dongle (dùng đúng `preparation.json` đã chuẩn bị):

1. Nhấn RESET, xác nhận bootloader `VID_1915&PID_521F` và số COM hiện tại
   (`Get-PnpDevice -PresentOnly -Class Ports | Select-Object FriendlyName,InstanceId`).
2. Preflight chỉ đọc; dừng nếu có bất kỳ sai khác hash/source/package nào:
   `& ml/.venv/Scripts/python.exe -B device/scripts/verify_week5_package.py --preparation '<preparation.json>'`
3. Nạp: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File device/scripts/flash_week5_head.ps1 -Port COM<n> -Preparation '<preparation.json>' -ReceiptDir '<thư mục receipt mới>'`
4. Tìm lại cổng CDC (`Adaptive Split Inference SV1`, PID `0004`) rồi thu 20 mẫu × 11 split và 16
   lượt đổi mẫu/split: `& ml/.venv/Scripts/python.exe -B device/scripts/collect_week5.py --port COM<n> --preparation '<preparation.json>' --capture '<capture.txt mới>' --report '<report.json mới>'`
5. Kiểm lại capture đã lưu không cần cổng:
   `& ml/.venv/Scripts/python.exe -B device/scripts/check_week5_capture.py --capture '<capture.txt>' --collection-receipt '<capture.receipt.json>' --report '<recheck.json mới>'`

Checker kiểm ID, anchor, thứ tự, shape, FP32 strict `<1e-3`, s0 bitwise và lượng tử đúng Python
trên chính activation của MCU; từ chối reset, lặp, cắt cụt, payload/scale hỏng. `--simulated` chỉ
dùng cho fixture offline và luôn báo MCU PENDING. Ứng dụng không có lệnh BENCH nên timing và
RAM/stack lúc chạy của lượng tử hóa là NOT_MEASURED.
