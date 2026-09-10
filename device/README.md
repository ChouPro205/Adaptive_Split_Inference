# Adaptive Split Inference - firmware SV1 Tuần 1

Firmware demo cho Nordic nRF52840 USB Dongle PCA10059 revision 2.1.1, dùng
Zephyr trong nRF Connect SDK v3.4.0 LTS.

## Chức năng

- LED xanh `led0` heartbeat với chu kỳ đầy đủ khoảng 1 giây.
- Console USB CDC ACM, không dùng UART vật lý.
- Benchmark vòng lặp rỗng bằng DWT CYCCNT: 20 lần warm-up và đúng 20 lần đo.
- In min, max, average, deviation và chỉ PASS khi deviation nhỏ hơn 1%.
- Khi mở lại terminal, firmware chạy lại benchmark; khi terminal vẫn mở,
  firmware in trạng thái định kỳ mỗi 5 giây.

Target duy nhất:

```text
nrf52840dongle/nrf52840
```

Không dùng biến thể `/bare`, không dùng `west flash`, không erase/recover.

## Build và tạo USB DFU ZIP

Từ Git root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\build_week1_demo.ps1
```

Script kích hoạt toolchain NCS v3.4.0, build pristine với `--no-sysbuild`
(do cấu hình West cục bộ đang mặc định bật sysbuild), rồi tạo:

```text
device\build\zephyr\zephyr.hex
device\artifacts\adaptive_split_week1_demo.zip
```

Gói `adaptive_split_base_v1.zip` cũ không bị ghi đè.

## Nạp và theo dõi

Xem hướng dẫn ngắn, dùng trực tiếp ngày demo tại
[`DEMO_TOMORROW.md`](DEMO_TOMORROW.md).

## Kiểm tra môi trường

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\device\scripts\check_env.ps1
```
