# Báo cáo SV1 tuần 7 — Marker D0–D4, công cụ đo PPK2 và chu kỳ đo năng lượng trên nRF52840 Dongle

Nghiệm thu kỹ thuật phía Device tuần 7: **PASS cả 9 tiêu chí** ([phụ lục A](#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-w7-d1w7-d11)),
scope **REAL_MCU + PPK2 Source Meter 5000 mV + BLE radio**. Peer BLE là laptop Windows 11 chạy *stub edge*
(`device/scripts/week7_stub_edge.py`), không phải KV260: số `E_tx`/`E_wait` tuần 7 chỉ dùng kiểm phương pháp,
**không đưa vào Table II**.

| Mục | Giá trị |
|---|---|
| Source firmware | commit `f16d897c0009`, cây sạch (`dirty=false`) cho cả 4 image |
| Build | NCS 3.4.0, `nrf52840dongle/nrf52840`, `--no-sysbuild`; biến thể `bench-fast`, `energy-usb-fast`, `energy-fast`, `energy-week4` |
| Image đo năng lượng | `f16d897c0009-energy-fast-20261019T141139Z` (không USB/console/log/LED), kernel FP32 tối ưu, `s = 2`, 50 P1 + 50 P0 |
| Công cụ | `measure_energy.py`, `energy_phases.py`, `week7_ppk2.py`, `week7_lab.py`, `check_week7.py`, `week7_stub_edge.py`, `week7_figures.py`, `publish_week7_results.py`; SHA-256 từng file trong `session.json` mỗi bước; ppk2-api 0.9.2 |
| Phiên raw | `D:\HUST\ASI_week7\session-20261020` (dongle cấp từ USB laptop: TC4, TC7, dry run), `D:\HUST\ASI_week7\session-20261022` (PPK2 A1, A2, B1, B2 ngày 22/10/2026); ngoài Git, SHA-256 trong [manifest](../results/week7/manifest.json) |
| Nguồn khi đo năng lượng | PPK2 Source Meter 5000 mV → USB breakout VBUS (quyết định PPK2 VBUS), dongle không cắm USB máy tính; nhiệt độ phòng 26–27 °C đầu và cuối (ước lượng, không có nhiệt kế; ghi `temp_room_C = 26.5`) |
| Số chính | Phiên **B2** (PASS ngay lần chạy gốc); B1 là phiên lặp lại cùng ngày (FAIL gốc do lỗi checker, kiểm lại PASS — §4) |

## 1. Kết quả theo tiêu chí

| # | Tiêu chí | Kết quả | Bằng chứng |
|---:|---|---|---|
| 1 | Marker D0–D4 trên PPK2 | **PASS** tự kiểm lúc boot của image energy (B2): D0→D1→D2→D3→D4 mỗi xung 200,09–200,10 ms, liền nhau (khe 0), 0 mẫu chồng, D5–D7 LOW cả bản ghi; image Active tuần 1 (A2): 29 xung D0→D3, xung trọn vẹn 499,97–499,98 ms, 0 lỗi thứ tự/độ rộng/chồng; D4 0 mẫu HIGH với image tuần 1 (P0.22 không chập P0.20, khớp đo thông mạch). D4 = P0.22 (W7-D4) | [ppk2_B_session.json](../results/week7/ppk2_B_session.json), [ppk2_A2_active_week1.json](../results/week7/ppk2_A2_active_week1.json), ảnh đấu dây (note trong `*_note-*.json`) |
| 2 | `measure_energy.py` thu đúng | **PASS** Source Meter 5000 mV, `GET_META_DATA` ngay sau khi mở cổng, DUT bật trong lúc ghi (bắt cả boot); bộ đếm mẫu 6 bit (bit 18–23) xác nhận là bộ đếm thật (bước 1 ở mọi mẫu), 0 gián đoạn trên A1 125 s, A2 15 s, B1 và B2 mỗi phiên 300 s; số mẫu DUT-ON lệch ≤ 0,011 % so với thời gian máy × 100 kS/s (giới hạn 0,1 %) | [ppk2_A1_idle_week2.json](../results/week7/ppk2_A1_idle_week2.json), `*_capture.json` |
| 3 | Bộ phân tích đã kiểm định | **PASS**: CSV tuần 2 → mean 25,416651984 µA, std 3,706868927 µA, 6 000 001 mẫu, điện tích hình thang 1,524999098 mC (chữ nhật 1,524999 mC), D0–D3 LOW 100 %; CSV Active tuần 2: 119 xung D0→D3, 500 ms, 0 chồng. Chuyển đổi raw trùng bit `PPK2_API.get_samples()`; 9 kịch bản tổng hợp. Đối chứng thu: image Idle tuần 2 qua ppk2-api **25,793 µA**, lệch 1,48 % so với 25,417 µA (giới hạn 10 %); điện tích 60 s 1,548 mC | `test_measure_energy.py` 22/22, [ppk2_A1_idle_week2.json](../results/week7/ppk2_A1_idle_week2.json) |
| 4 | Pipeline tuần 7 đúng byte | **PASS** 11 split × 20 mẫu: 220/220 q/scale trùng tensor MCU (golden SV3 trừ 3 bit scale FP16 đã giải thích ở tuần 5), 440/440 request I1 v2 (P0 + P1 key PUBLIC_TEST) trùng Python reference; dry run 50 P1 + 50 P0 với key bench: stub kiểm CRC + header + sequence tăng ngặt 100/100 | [verify_tc4.json](../results/week7/verify_tc4.json), [dryrun_50p1_50p0.json](../results/week7/dryrun_50p1_50p0.json) |
| 5 | Firmware đo tự chạy không USB | **PASS** (B2) stub nhận 100/100 request hợp lệ (0 CRC sai, 0 từ chối, q trùng byte golden), trả 100/100 response; bản ghi có đúng 100 chu kỳ đủ pha (50 P1, 50 P0), mỗi chu kỳ 1 xung TX, WAIT max 29,1 ms ≪ 5 s; cả 100 chu kỳ trên một kết nối (ngắt sau chu kỳ cuối theo thiết kế); cuối TX trên bản ghi khớp thời điểm stub nhận xong từng request, đúng thứ tự ρ (lệch khoảng cách max 18,4 ms < 30 ms). Nonce: sequence P1 60635138…60635187 > 60634163 (sequence cuối của B1) > 60631040 (`reserved_through` đọc ngay trước phiên B), stub unprotect đúng bằng key bench ⇒ key không đổi. B1: 13/14 gốc, 14/14 khi kiểm lại (§4.5) | [ppk2_B_session.json](../results/week7/ppk2_B_session.json), [stub_edge_session.json](../results/week7/stub_edge_session.json), [ppk2_B_attempt1_recheck_PASS.json](../results/week7/ppk2_B_attempt1_recheck_PASS.json) |
| 6 | Tách pha, tổng < 3 % | **PASS** `|E_cycle − Σ E_pha| / E_cycle`: B2 mean 0,116 %, max 0,144 % trên 100/100 chu kỳ (B1: 0,117 % / 0,159 %); mean ± CI95 mọi pha ở §3, thời lượng marker so DWT ở §2.2 | [cycles_100.csv](../results/week7/cycles_100.csv), [phase_energy_summary.csv](../results/week7/phase_energy_summary.csv) |
| 7 | Kernel FP32 tối ưu | **PASS** trên dongle: `CMP ALL` 220/220 trùng từng bit với kernel tuần 4 cùng image, `CMP MIX` 16/16; BENCH 11 split × (20 warm-up + 100) cho cả hai kernel, 1100 + 1100 số đo; tăng tốc 6,4–7,2× ở s = 1…10 (s = 10: 6,38× ≥ 1,5×) | [bench_tc7.json](../results/week7/bench_tc7.json), [t_dev_bench_by_split.csv](../results/week7/t_dev_bench_by_split.csv) |
| 8 | Build và tài nguyên | **PASS** 4 image kết thúc trước `0xDC000`, `dirty=false`, check tĩnh PASS; stack high-water §2 | [build_resources.csv](../results/week7/build_resources.csv), [build_check/](../results/week7/build_check/) |
| 9 | Hồ sơ | **PASS** results/week7 (66 file) + manifest, raw ngoài Git có SHA-256 (13 mục), session.json + ảnh + nhiệt độ mỗi phiên PPK2, báo cáo này; test host PASS | [results/week7](../results/week7/README.md) |

## 2. Thời gian và tài nguyên (TC7, TC8)

### 2.1. `t_dev` theo split, hai kernel trên cùng image `bench-fast`

Phương pháp tuần 4: mẫu 0, khóa IRQ trong một lần head, DWT 64 MHz, 20 warm-up + 100 lần đo.

| s | Kernel tuần 4 (ms) | Kernel tối ưu (ms) | Tăng tốc |
|---:|---:|---:|---:|
| 0 | 0,005 | 0,002 | 2,62× |
| 1 | 18,977 | 3,539 | 5,36× |
| 2 | 234,450 | 32,957 | 7,11× |
| 3 | 448,933 | 62,891 | 7,14× |
| 4 | 873,575 | 121,918 | 7,17× |
| 5 | 1190,504 | 170,377 | 6,99× |
| 6 | 1664,520 | 242,972 | 6,85× |
| 7 | 1978,059 | 297,886 | 6,64× |
| 8 | 2395,605 | 371,154 | 6,45× |
| 9 | 2409,009 | 377,330 | 6,38× |
| 10 | 2409,060 | 377,356 | 6,38× |

Kernel tuần 4 trên image tuần 7 lệch < 0,01 ms so với số công bố tuần 4 (cùng mã, khác image). Kernel mới giữ
`-ffp-contract=off` và đúng thứ tự cộng nên đầu ra trùng từng bit; tăng tốc đến từ `-O2` riêng file, đưa kiểm biên
padding ra khỏi vòng trong và con trỏ tăng dần.

### 2.2. Pha của chu kỳ đo theo DWT (dry run `energy-usb`, nguồn laptop, s = 2)

| Pha | P1 (µs, mean) | P0 (µs, mean) | Ghi chú |
|---|---:|---:|---|
| CTRL (stub controller, đệm tối thiểu) | 200 | 200 | W7-D2: đủ 20 mẫu ở 100 kS/s |
| HEAD = head(s) + lượng tử | 37 698 | 37 696 | gồm lượng tử 4 120 µs; head không khóa IRQ, chạy dưới các thread BT |
| PROT = nonce (block đặt trước) + descriptor + protect | 1 347 | 0 | P0 không có D1 |
| TX = encode + CRC + 14 fragment | 11 004 | 10 914 | gồm encode 3 433 / 3 392 µs; frame 3116 / 3076 B, MTU 247 |
| WAIT = tới khi parse xong response | 1 303 | 1 305 | response 64 B |

HEAD ở chu kỳ đo (37,70 ms) lớn hơn BENCH khóa IRQ (32,96 ms) + lượng tử (4,12 ms) = 37,08 ms khoảng 0,6 ms: phần
phục vụ connection event BLE trong lúc tính. Connection interval thực tế 15 ms (12 × 1,25 ms), latency 0,
supervision timeout 4 s, PHY 2M (`EVT CONN_PARAM` trong `dryrun/cdc.log`).

### 2.3. Thời lượng pha theo marker PPK2 (B2) so với DWT

| Pha | P1 marker (ms) | P1 DWT dry run (ms) | P0 marker (ms) | P0 DWT dry run (ms) |
|---|---:|---:|---:|---:|
| CTRL | 0,200 | 0,200 | 0,201 | 0,200 |
| HEAD | 37,83 | 37,70 (+0,36 %) | 37,84 | 37,70 (+0,39 %) |
| PROT | 1,30 | 1,35 (−46 µs) | — | — |
| TX | 32,87 (trung vị 29,1) | 11,00 | 32,82 | 10,91 |
| WAIT | 13,25 | 1,30 | 13,53 | 1,31 |

Các pha không dùng radio khớp DWT trong 0,4 % (PROT lệch −46 µs, dưới 5 mẫu PPK2). So với DWT tuần 4 ở s = 2
(234,458 ms, kernel cũ, khóa IRQ, chưa lượng tử), HEAD trên bản ghi là 37,83 ms (gồm lượng tử 4,12 ms), tức head
thuần ≈ 33,7 ms, nhanh ≈ 7× — khớp BENCH §2.1.

**TX và WAIT dài hơn dry run nhiều lần, cùng định nghĩa đo.** DWT `tx_cycles` và marker D2 cùng tính từ lúc luồng
gửi bắt đầu tới khi notify cuối hoàn tất (`week6/ble_link.c`). Ở dry run dongle cắm thẳng cổng USB laptop, sát
anten Bluetooth: 14 fragment (3116 B) đi hết trong một connection event (TX 10,9–12,0 ms). Trên bàn đo dongle nằm ở
breakout PPK2 xa hơn: 2–3 connection event (TX 27,8–40 ms, trung vị 29,1 ms), WAIT thêm khoảng một connection
interval (8,5–29 ms). Connection interval trên bản ghi vẫn 15,01 ms. Image energy không có console nên không đọc
được PHY thực tế ở phiên PPK2. Chu kỳ đầu tiên sau khi kết nối có TX ≈ 102 ms ở cả B1 và B2 (lặp lại, có hệ
thống). Hệ quả: `E_tx`/`E_wait` phụ thuộc vị trí đặt dongle so với laptop — phải cố định hình học bàn đo khi khóa
bàn đo (tuần 9). Bảng đầy đủ: [phase_time_marker_vs_dwt.csv](../results/week7/phase_time_marker_vs_dwt.csv).

### 2.4. Image và RAM

| Image | `zephyr.bin` (B) | Kết thúc | Dư trước `0xDC000` (B) | RAM tĩnh (B) |
|---|---:|---|---:|---:|
| bench-fast | 527 532 | 0x81cac | 369 492 | 100 469 |
| energy-usb-fast | 632 820 | 0x9b7f4 | 264 204 | 125 763 |
| energy-fast | 597 924 | 0x92fa4 | 299 100 | 110 988 |
| energy-week4 (dự phòng W7-D8) | 596 696 | 0x92ad8 | 300 328 | 110 988 |

Stack high-water (bản USB, sau 100 chu kỳ dry run): main 2264/8192, BT RX WQ 712/1024, i1_tx 520/2048,
bt_tx_processor 356/768, sysworkq 496/2048 B; bench sau `CMP ALL`: main 904/8192 B.

## 3. Năng lượng từng pha (TC6)

Phiên B2: 22/10/2026 09:18 (giờ Việt Nam), 26–27 °C, capture 300 s, 30 070 272 mẫu, 0 mất. Gross tại đầu vào 5 V
(W7-D5), net = gross − V·I_idle·t với `I_idle_uA` = 24,83 µA đo ngay trong image energy (29 s sau tự kiểm, radio
tắt; B1: 24,99 µA). Mean ± CI95 (Student-t, n − 1 bậc tự do), s = 2.

| Đại lượng | ρ = P1 (n = 50) | ρ = P0 (n = 50) |
|---|---:|---:|
| `E_ctrl_uJ` | 4,44 ± 0,03 | 4,43 ± 0,03 |
| `E_dev_uJ` | 683,2 ± 13,2 | 705,8 ± 15,3 |
| `E_prot_uJ` | 24,3 ± 1,3 | — |
| `E_tx_uJ` | 626,2 ± 11,8 | 622,1 ± 7,8 |
| `E_wait_uJ` | 130,7 ± 1,3 | 127,1 ± 4,1 |
| `E_gap_uJ` | 1,72 ± 0,05 | 1,66 ± 0,05 |
| `E_cycle_uJ` (gross) | **1470,5 ± 17,3** | **1461,1 ± 16,7** |
| `E_cycle_net_uJ` | 1459,9 ± 17,0 | 1450,6 ± 16,6 |
| `t_cycle_ms` | 85,5 ± 3,8 | 84,4 ± 2,5 |
| `t_dev_ms` / `t_prot_ms` | 37,83 / 1,30 | 37,84 / — |
| `t_tx_ms` / `t_wait_ms` | 32,9 ± 3,4 / 13,3 ± 0,8 | 32,8 ± 2,1 / 13,5 ± 1,0 |
| diff (%) mean / max | 0,117 / 0,144 | 0,114 / 0,138 |

CI95/mean của `E_cycle` là 1,2 % (tuần 9 yêu cầu < 10 %; tuần 7 chỉ ghi nhận). Bỏ chu kỳ đầu (TX 102 ms, §2.3),
`E_cycle` P1 là 1465,8 µJ.

**Lặp lại cùng ngày (B1, 9 phút trước B2, cùng image và bàn đo):** `E_cycle` P1 1438,0 ± 17,7 µJ, P0 1429,0 ± 15,1 µJ;
`E_dev` 658,3 / 681,0, `E_prot` 23,5, `E_tx` 619,2 / 615,9, `E_wait` 131,0 / 126,1 µJ. B2 − B1 ≈ +2,2 % `E_cycle`,
chủ yếu ở `E_dev` (+25 µJ) — lớn hơn CI95 trong từng phiên, nên khi so cấu hình phải đo xen kẽ trong cùng phiên.

**P1 − P0 chỉ ≈ 9 µJ (0,6 %), nhỏ hơn `E_prot` 24 µJ**, vì `E_dev` của P0 cao hơn P1 ≈ 23 µJ ở **cả B1 và B2**, dù
HEAD giống hệt nhau (`t_dev` 37,83 / 37,84 ms, cùng 20 mẫu). Giá trị nhỏ nhất của `E_dev` như nhau (≈ 600 µJ = HEAD
không có thêm hoạt động radio); khác biệt nằm ở đuôi trên (nhiều connection event có dữ liệu hơn trong lúc HEAD ở khối
P0). Đã loại giả thuyết khóa pha connection event: chu kỳ lặp 1080 ms ≈ 71,95 × 15,01 ms, pha trôi −0,048 chu kỳ
mỗi lần, phủ cả dải trong cả hai khối, không tương quan với `E_dev` (R² ≤ 0,02). Nguyên nhân còn mở; vì chênh lệch
cùng cỡ chi phí bảo vệ, **tuần 9 nên xen kẽ P1/P0 trong một phiên** thay cho hai khối liên tiếp (W7-D9) để
không lẫn hiệu ứng thời gian/trạng thái liên kết vào `ΔE_prot`.

Hình (thư mục [figures/](../results/week7/figures/)): [một chu kỳ P1](../results/week7/figures/fig_cycle_waveform_P1.png)
(bản nháp Figure 3 của bài báo), [một chu kỳ P0](../results/week7/figures/fig_cycle_waveform_P0.png),
[toàn phiên](../results/week7/figures/fig_session_overview.png), [năng lượng từng pha](../results/week7/figures/fig_phase_energy.png),
[histogram idle](../results/week7/figures/fig_idle_histogram.png), [diff 100 chu kỳ](../results/week7/figures/fig_diff_pct.png).
Mỗi hình có bản PDF vector cùng tên (IEEE: 3,5 / 7,16 in, Times 8 pt, font TrueType nhúng).

## 4. Sự cố và cách xử lý

1. **`verify` lần đầu FAIL 3 ca s = 10** (n = 8, 13, 18): lệch 1 ULP một kênh scale FP16. Đây đúng là chênh lệch MCU
   so với golden SV3 đã giải thích ở tuần 5 (`results/week5/golden_difference_analysis.json`), không phải lỗi firmware.
   Sửa checker: `week7_common.device_tensor()` áp đúng các bit MCU đó (kiểm SHA với `case_tables` của
   `week5_mcu_validation.json`); stub edge chọn mẫu theo cả q và scale (ở s = 10 nhiều mẫu trùng q). Chạy lại PASS.
   Bản FAIL giữ ở [verify_first_run_FAIL.json](../results/week7/verify_first_run_FAIL.json).
2. **Dry run: `p1_sequence_above_boot_reservation` FAIL do ngữ nghĩa checker sai.** `reserved_through` in lúc boot là
   **đầu trên** của block vừa đặt (60626945…60627968), không phải giá trị trước block. Thay bằng
   `p1_sequence_in_boot_block` + `--prior-reserved-through` (60626944 đọc bằng image tuần 6 trước khi nạp tuần 7).
   Bản FAIL giữ ở [dryrun_first_check_FAIL.json](../results/week7/dryrun_first_check_FAIL.json).
3. **Bench nhanh buổi sáng dừng giữa chừng** (hết phiên làm việc); không dùng làm bằng chứng, chạy lại đủ 11 split
   buổi chiều.
4. **Ngày PPK2: DFU lần đầu FAIL, nonce đọc muộn hơn runbook.** Khi chuyển dongle từ breakout sang USB laptop, dongle
   vào thẳng bootloader và cổng COM6 không mở được ("device not functioning"); rút cắm lại + RESET thì nạp được. Receipt
   exit 1 giữ trong [dfu/](../results/week7/dfu/) và liệt kê ở `failed_dfu_receipts` của manifest. Vì không chạy được
   image `energy-usb` lúc đầu, bước đọc nonce dời tới ngay trước phiên B: nạp `energy-usb-fast` → `verify --split 2`
   (PASS) → `reserved_through = 60631040` → nạp `energy-fast`.
5. **B1: `TC5_one_cycle_per_request` FAIL do checker so sai mốc.** Checker so khoảng cách **đầu** chu kỳ trên bản ghi
   với khoảng cách thời điểm stub nhận **xong** request (tức cuối TX). Hai đại lượng chỉ bằng nhau khi mọi chu kỳ có TX
   như nhau; chu kỳ đầu TX 101,9 ms so với trung vị 29 ms nên lệch 69 ms. Thêm vào đó đồng hồ stub
   (`time.monotonic` trên Windows) có bước 15,625 ms. Sửa `week7_ppk2.py`: so **cuối TX** (CTRL+HEAD+PROT+TX) với thời
   điểm stub nhận xong, thêm điều kiện thứ tự ρ trùng và lệch từng chu kỳ quanh trung vị < 30 ms; lệnh mới `recheck`
   ghi `check_session_recheck.json` cạnh bản gốc. B1 kiểm lại 14/14 (lệch max 14,2 ms). Vì checker sửa sau khi đã
   thấy dữ liệu, chạy thêm **B2** bằng checker mới: PASS 14/14 ngay lần gốc → B2 là số chính. Bản FAIL giữ ở
   [ppk2_B_attempt1_FAIL.json](../results/week7/ppk2_B_attempt1_FAIL.json).
6. **A1: độ lệch chuẩn 9,96 µA (tuần 2: 3,71 µA).** Có 137 gai > 100 µA (tối đa 463 µA) trong 60 s, phần lớn dồn
   vào một giây (trung bình giây đó 48,75 µA, các giây khác 24,9–26 µA); gai chiếm 1,38 % điện tích, bỏ gai trung
   bình còn 25,48 µA. Nguồn gai chưa rõ. Cửa sổ idle 29 s trong image energy không có gai như vậy (std 3,6–3,7 µA, max 35,5 µA ở B2, 42,4 µA ở B1).
7. **Sau chu kỳ cuối, dongle quảng bá lại.** `link_disconnect()` ngắt đúng lúc, nhưng `week6/ble_link.c` khởi động lại
   advertising khi connection được giải phóng (`recycled` → `adv_start`), nên stub kết nối thêm một lần ≈ 1,5 s sau
   response cuối, và dòng trung bình từ đó tới hết bản ghi ≈ 450 µA (thấy rõ trên
   [hình toàn phiên](../results/week7/figures/fig_session_overview.png)). Không chạm 100 chu kỳ đo; nhưng "ngắt kết nối,
   ngủ" của TC5 chưa đúng nghĩa đen → sửa ở tuần 8 (không quảng bá lại sau phiên đo).
8. **Số block nonce.** Giữa lần đọc nonce (block kết thúc 60631040) và B1 (block bắt đầu 60634113) có 3 block: một do
   boot ngay sau DFU `energy-fast` trên USB, hai lần boot chưa xác định (nghi do tiếp xúc khi rút dongle). Không ảnh
   hưởng tính duy nhất: block chỉ tăng, mỗi lần boot tốn 1024 sequence.

Firmware không đổi sau các sửa này (chỉ sửa script host), nên image đã build từ `f16d897` vẫn dùng được.

## 5. Giới hạn và việc tiếp theo

- Peer là laptop: `E_tx`, `E_wait` và khoảng nghỉ phụ thuộc Windows (connection interval 15 ms do thiết bị xin,
  central quyết định). Khi KV260/BlueZ thay laptop phải đo lại (W7-D7).
- Mọi số là **gross tại đầu vào 5 V** của dongle (gồm tổn hao bộ ổn áp), không phải năng lượng lõi nRF52840.
- Hai phiên B cùng một ngày (B2 − B1 ≈ +2,2 % `E_cycle`): chưa có độ lặp lại giữa các ngày (tuần 13).
- `E_tx`/`E_wait` phụ thuộc vị trí dongle so với central (§2.3): cố định hình học bàn đo khi khóa từ tuần 9.
- `E_dev` P0 > P1 ≈ 23 µJ chưa giải thích (§3): xen kẽ P1/P0 trong một phiên ở tuần 9.
- Tuần 8: image energy không quảng bá lại sau phiên đo (§4.7).
- Tuần 8 (G2): đổi peer sang KV260 (hoặc laptop chạy tail thật nếu GV đồng ý), thêm vào stub edge
  unprotect → dequantize → tail FP32; sau G2 chốt và khóa bàn đo từ tuần 9.

## Phụ lục A. Tiêu chí nghiệm thu và quyết định W7-D1…W7-D11

### A.1. Chín tiêu chí

| # | Tiêu chí | Định nghĩa đạt |
|---:|---|---|
| TC1 | Marker D0–D4 | Image đo tự kiểm 5 marker lúc boot (200 ms mỗi marker), PPK2 thấy đúng kênh và thứ tự, không kênh lên sai, không chồng; D0–D3 kiểm thêm bằng image Active tuần 1; ảnh đấu dây |
| TC2 | Thu đúng | Source Meter 5000 mV, 100 kS/s, `get_modifiers()` ngay sau khi mở cổng, bật DUT trong lúc ghi; raw + metadata + SHA-256 vào thư mục mới, từ chối ghi đè; không mất mẫu (bộ đếm mẫu hoặc số mẫu/thời gian ±0,1 %) |
| TC3 | Bộ phân tích | Tái lập số tuần 2 (25,417 µA, 1,525 mC, 6 000 001 mẫu, D0–D3 LOW); test tổng hợp đúng đáp án/mã lỗi; đối chứng thu Idle tuần 2 lệch ≤ 10 % |
| TC4 | Đúng byte | q/scale 20 mẫu (mọi split) trùng MCU tuần 5; request I1 v2 key PUBLIC_TEST trùng Python 20/20; với key bench stub kiểm CRC + header + sequence tăng ngặt |
| TC5 | Tự chạy không USB | Image energy: boot → idle 30 s → BLE → n chu kỳ; stub 100/100 request hợp lệ và response; đúng số chu kỳ đủ pha, không timeout, không retry, không mất kết nối; nonce không lặp |
| TC6 | Tổng < 3 % | `|E_cycle − Σ E_pha| / E_cycle < 3 %` cho mọi chu kỳ (mean và max); thời lượng pha so với DWT; mean ± CI95 Student-t |
| TC7 | Kernel tối ưu | Trùng từng bit kernel tuần 4: host 220/220, dongle 220/220 + 16 xen kẽ; BENCH 11 split 1100/1100; báo GV nếu tăng tốc < 1,5× ở s = 10 |
| TC8 | Build | NCS 3.4.0, image < `0xDC000`, Flash/RAM từ ELF, stack high-water, check tĩnh PASS, `dirty=false` |
| TC9 | Hồ sơ | results/week7 + manifest, raw ngoài Git có SHA-256, session.json mỗi bước, báo cáo có phụ lục, test host PASS |

### A.2. Quyết định đã chốt 19/10/2026 (GV giao SV1 tự chốt)

| # | Quyết định |
|---|---|
| W7-D1 | Tên biến theo repo + lộ trình + Table II: `E_ctrl/E_dev/E_prot/E_tx/E_wait/E_cycle/E_gap_uJ`, `t_*_ms`, `I_idle_uA`, `v_supply_mV` (= 5000), `temp_room_C`, `split_s`, `rho`, `n` (quy ước v1.0 chưa duyệt nên không áp) |
| W7-D2 | Ranh giới pha: D4 CTRL = controller stub, đệm tối thiểu 200 µs · D0 HEAD = head(s) + lượng tử INT8/FP16 + mở rộng scale FP32 · D1 PROT = nonce (block đặt trước lúc boot, không ghi Flash trong chu kỳ) + descriptor + protect; P0 không có D1 · D2 TX = encode + CRC + mọi fragment, luồng gửi hạ D2 khi notify cuối hoàn tất · D3 WAIT = tới khi parse xong response đúng `request_id`. Không retry; timeout 5 s → chu kỳ hỏng, bộ phân tích loại |
| W7-D3 | Idle 30 s trong firmware energy ngay sau tự kiểm (radio chưa bật, USB tắt, marker LOW); phiên A thêm 60 s bằng image Idle tuần 2 để so 25,417 µA |
| W7-D4 | D4 = **P0.22** (Hình 3 User Guide, cạnh trên; không dính SW2/LED/NFC); dự phòng P0.24; đo thông mạch trước khi cấp điện |
| W7-D5 | Số chính = gross tại đầu vào 5 V; thêm cột net = gross − V·I_idle·t |
| W7-D6 | Peer = laptop stub edge, MODE NORMAL: kiểm CRC/header, sequence P1 tăng ngặt, unprotect bằng key bench rồi so q trùng byte golden; trả RESPONSE 64 B với logits tham chiếu của mẫu đó; request sai không trả lời |
| W7-D7 | Thiết bị xin connection interval 15 ms (12 × 1,25 ms, latency 0, timeout 4 s); central quyết định; ghi giá trị thực; giữ cố định tuần 7–12 |
| W7-D8 | Kernel chọn bằng Kconfig, mặc định fast; nếu TC7 chưa đạt trước phiên B thì đo bằng `energy-week4` (TC7 đã đạt 20/10 → dùng fast) |
| W7-D9 | s = 2; một phiên = 50 P1 rồi 50 P0, nghỉ 1 s, mẫu `i % 20`; connected idle 30 s trước chu kỳ đầu |
| W7-D10 | Code ở `device/week7/*`, `device/scripts/{measure_energy,energy_phases,week7_*,check_week7*,build_week7,flash_week7,test_measure_energy,test_week7_host,publish_week7_results}`; raw/build ngoài Git ở `D:\HUST\ASI_week7\` |
| W7-D11 | Gán từng mẫu cho đúng một pha theo bit của chính mẫu đó, tổng chữ nhật `E = V·Σi·Δt`; hình thang chỉ để tái lập tuần 2 (báo cả hai) |

### A.3. Việc còn mở của người khác

- Trung (SV2): revision registry mới cho `runtime.nonce_persistence_reboot` (tiêu chí 7 tuần 6 đã đạt), cần Châu + Trung
  xác nhận `device_revision = edge_revision`; lịch thử KV260 làm BLE central cho G2 tuần 8; `week7_stub_edge.py` là
  tham chiếu hành vi response I1 v2.
- GV: Q2 (dongle dự phòng), Q3 (G2 tạm bằng laptop chạy tail nếu KV260 chưa sẵn), Q4 (lịch nhận `controller.c`).

## Phụ lục B. Firmware `device/week7/`

| File | Vai trò |
|---|---|
| `main.c` | Ba biến thể: `bench` (CMP/MIX/BENCH, TC7), `energy-usb` (VERIFY/CYCLES/SESSION/NONCE/CONNPARAM qua CDC, TC4 + dry run), `energy` (tự chạy phiên PPK2: đặt block nonce → tự kiểm D0–D4 → idle 30 s → BLE → connected idle 30 s → 50 P1 + 50 P0 → ngắt) |
| `energy_cycle.c/.h` | Một chu kỳ CTRL → HEAD → PROT → TX → WAIT, đo DWT từng pha |
| `head_fast.c/.h` | Kernel FP32 tối ưu, trùng bit kernel tuần 4 |
| `marker_ctrl.c/.h` | Marker D4 (P0.22) ghi thẳng OUTSET/OUTCLR Port 0 như `src/markers.c` |
| `Kconfig`, `prj.conf`, `overlay-*.conf`, `app.overlay` | Chọn biến thể/kernel, s, số chu kỳ, khoảng nghỉ, idle, timeout, interval |

Dùng lại nguyên vẹn qua đường dẫn: `src/week4_head.c`, `src/markers.c`, `week5/quantization.c`, `week6/{ble_link,frag,exchange,nonce_store,nonce_nvs,packets,sha256}.c`, `contracts/i1v2_ref`, `contracts/i2_ref`.
Nếu không có nonce READY, image energy không gửi I2/1: phát 10 xung CTRL 5 ms rồi dừng (nhìn thấy trên bản ghi).

## Phụ lục C. Quy trình chạy lại và checklist bàn đo

Biến dùng chung (PowerShell, gốc repo):

```powershell
$py  = "device\host\.venv\Scripts\python.exe"
$fw  = "D:\HUST\ASI_week7\firmware-20261019"
$S   = "D:\HUST\ASI_week7\session-<yyyymmdd>"      # thư mục MỚI cho ngày đo
$key = "D:\HUST\ASI_week6\secrets\bench_key_65537.bin"   # không in, không commit
```

### C.1. Dongle trên USB laptop (TC4, TC7, dry run)

1. Ghi trạng thái nonce bằng image đang có: `$py -m serial.tools.miniterm COMx 115200`, gõ `NONCE`, ghi
   `reserved_through`, `key_check` (= `4379e570eb84f891`). Không bao giờ `PROV ERASE`.
2. Nạp: RESET → cổng bootloader (`1915:521F`) → `device\scripts\flash_week7.ps1 -Port COMx -ReportDir $fw\bench-fast -ReceiptDir $S\dfu`.
3. `$py -B device\scripts\week7_lab.py bench --out $S\bench` (≈ 60 phút; thử nhanh `--bench-splits 0,2,10`) → TC7.
4. Nạp `energy-usb-fast`; `week7_lab.py verify --out $S\verify --split ALL` → TC4;
   `week7_lab.py dryrun --out $S\dryrun --p1 50 --p0 50 --key-file $key --prior-reserved-through <bước 1>`.

### C.2. Phiên PPK2 A (dongle cấp từ PPK2)

0. Đóng nRF Connect Power Profiler. `$py -B device\scripts\week7_ppk2.py probe` → cổng PPK2, ≈ 100 000 mẫu/s,
   `counter continuous` (xác nhận giả định bộ đếm mẫu ở bit 18–23; nếu không liên tục hoặc không đổi → dùng
   `--ignore-counter` ở mọi bước sau, TC2 dựa vào kiểm số mẫu/thời gian).
1. Dongle trên USB laptop, còn image `energy-usb`: `$py -B device\scripts\week7_lab.py verify --split 2 --out $S\nonce-check`
   → `reserved_through` mới nhất trong `cdc.log` (mỗi lần boot image tuần 7 đặt một block mới) dùng cho C.3.
   Nạp `flash_week7.ps1 -Port COMx -Package device\artifacts\adaptive_split_week2_idle.zip -ReceiptDir $S\dfu`;
   chuyển dongle sang breakout PPK2. Nếu dongle cắm vào đã ở bootloader (LED đỏ thở) thì nạp luôn và làm bước đọc
   nonce ngay trước C.3 (như ngày 22/10). Cổng bootloader không mở được → rút cắm lại rồi bấm RESET.
   Nút **RESET** nằm ở cạnh dài, bấm ngang; nút bấm từ trên xuống là SW1. LED đỏ thở = bootloader.
2. `$py -B device\scripts\week7_ppk2.py idle --port <PPK2> --out $S\A1-idle-w2 --temp-c <t> --image device\artifacts\adaptive_split_week2_idle.zip --receipt <receipt.json>`
   (125 s: idle 60 s từ giây thứ 5 so 25,417 µA ±10 % — lệch thì DỪNG điều tra; đồng thời là phép thử mất mẫu ≥ 120 s).
3. Nạp `adaptive_split_week1_demo.zip` như bước 1; `week7_ppk2.py active --port <PPK2> --out $S\A2-active-w1 --temp-c <t> --image ... --receipt ...`
   (15 s, xoay vòng D0→D3 500 ms).

### C.3. Phiên PPK2 B (TC1, TC2, TC5, TC6)

1. Dongle trên USB laptop: nạp `flash_week7.ps1 -Port COMx -ReportDir $fw\energy-fast -ReceiptDir $S\dfu`; chuyển sang breakout.
   Bluetooth laptop bật, không app BLE khác, không pair dongle trong Settings. Giữ đúng vị trí dongle/laptop cho mọi
   phiên cần so sánh (`E_tx`/`E_wait` phụ thuộc khoảng cách, §2.3).
2. `$py -B device\scripts\week7_ppk2.py session --port <PPK2> --out $S\B1 --temp-c <t> --image $fw\energy-fast --receipt <receipt.json> --key-file $key --prior-reserved-through <C.2 bước 1> --dryrun-check D:\HUST\ASI_week7\session-20261020\dryrun\check_dryrun_recheck_block.json --a1 $S\A1-idle-w2`
   — tự khởi động stub edge (quét BLE) TRƯỚC, rồi mới bật nguồn DUT và ghi 300 s, phân tích, đối chiếu stub ↔ bản ghi.
   Nếu stub không quét được, DUT không được bật (không tốn block nonce). Hai lần `scan_timeout` đầu (mỗi lần 15 s)
   là bình thường: radio tắt trong 30 s idle.
3. `week7_ppk2.py note --out $S\B1 --temp-end-c <t> --photo <ảnh đấu dây>`.
4. FAIL → chạy lại vào thư mục mới (`B2`…) với `--prior-reserved-through` = sequence P1 cuối của lần trước, giữ bản FAIL
   (`publish_week7_results.py --b-failed`). Sửa checker sau khi thấy dữ liệu thì `week7_ppk2.py recheck --out $S\B1`
   (ghi `check_session_recheck.json`, bản gốc giữ nguyên) **và** vẫn chạy phiên mới để có PASS gốc.
5. Hình: `$py -B device\scripts\week7_figures.py --session $S\B2 --a1 $S\A1-idle-w2 --out $S\figures`.
6. Công bố (lệnh đã chạy 22/10): `$py -B device\scripts\publish_week7_results.py --lab D:\HUST\ASI_week7\session-20261020 --firmware $fw --a1 $S\A1-idle-w2 --a2 $S\A2-active-w1 --b $S\B2 --b-failed $S\B1 --ppk2-dfu $S\dfu --figures $S\figures --out results\week7`.

### C.4. Checklist bàn đo (in dán lên bàn)

- [ ] Dongle **không** cắm USB máy tính; chỉ nhận nguồn từ PPK2 qua breakout VBUS 5,0 V; SB1/SB2 nguyên.
- [ ] GND chung PPK2 ↔ dongle; VCC cổng logic nối như tuần 2; D0 P0.13, D1 P0.15, D2 P0.17, D3 P0.20, D4 P0.22
      (đã đo thông mạch P0.22 với P0.20/P0.24/GND: không chập).
- [ ] `probe` OK trước mọi phiên; log `capture` có `GET_META_DATA` (`metadata_text` trong `capture.json`).
- [ ] Source Meter 5000 mV, 100 kS/s (script tự đặt).
- [ ] Image đem đo là `energy-fast` (build ID trong `session.json`), receipt DFU exit 0.
- [ ] Nhiệt độ phòng đầu (`--temp-c`) và cuối (`note --temp-end-c`); ảnh đấu dây mỗi phiên.
- [ ] Bluetooth laptop bật; stub edge chạy trước khi bật nguồn DUT (script tự làm).
- [ ] Mỗi lần thu một thư mục mới; sau phiên kiểm `check_*.json` PASS (số mẫu, 100 chu kỳ, stub đủ).

Test host: `test_measure_energy.py` 22/22, `test_week7_host.py` 16/16, `test_week6_host.py` 27/27 (chạy lại 22/10/2026 sau mọi sửa của ngày PPK2).
