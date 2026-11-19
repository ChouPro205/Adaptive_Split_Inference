# Báo cáo SV1 tuần 10 — E_prot P1, E_wait theo hàng đợi, chu kỳ mọi s lúc radio bật

Nghiệm thu kỹ thuật phía Device tuần 10: **8/8 tiêu chí PASS** ([phụ lục A](#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-w10-d1w10-d9)).
Phiên E_prot đo ngày 13/11; phiên E_wait và phiên mọi s cùng SV2 (KV260) dời từ 14/11 sang 19/11 vì máy của SV2
hỏng. Mọi luật phân tích được commit trước phiên đo, trừ một lần sửa luật `post_radio_off` sau khi thấy dữ liệu A1
(§6, mục 6).

Kết quả chính:

- **P1 (I2/1) tốn ít năng lượng hơn lớp conv rẻ nhất của head ở mọi s = 0…9**, theo luật chặt nhất đã khai trước
  (W10-D2). Trường hợp sát nhất là s3: trung bình phiên lớn nhất của E_prot bằng 0,64 lần trung bình phiên nhỏ nhất
  của E_conv,min (§2).
- **E_wait tăng tuyến tính theo thời gian chờ, độ dốc bằng công suất giữ kết nối:** E_wait = 115,1 + 1,699 µJ/ms ×
  t_wait (R² 0,995). Độ dốc lệch P_conn đo cùng phiên (1,574 mW) 7,9 % và lớn gấp 13,4 lần công suất idle radio tắt.
  Mỗi job đang chờ cộng 51,7 ms (= 1,06 × t_service) và khoảng 88 µJ. Hàng đợi dài (q ≈ 7) làm E_wait tăng 3,2 lần so
  với hàng đợi rỗng (§3).
- **Đủ cột Table III của Khung (trừ Acc) cho s0…s10 lúc radio bật**, đo trực tiếp, CI95/mean < 10 % ở mọi s. Gửi thô
  (s0) tốn 0,30 mJ/83 ms mỗi chu kỳ; mọi điểm cắt giữa tốn 1,71–7,06 mJ; s10 tại chỗ 6,55 mJ/384 ms (§4).
  E_tx = 4,4 + 0,240 µJ/B (R² 0,996).
- **Công thức E_dev,on ≈ E_dev,off + 0,7 mW × t_dev đạt** (W10-D5): E lõi lệch ≤ 1,03 % ở mọi s ≥ 2. Nhưng số thô
  radio bật cao hơn radio tắt tuần 9 khoảng 25–31 % ở s ≥ 2, và s2 thô lệch +15 % so với phiên B5 tuần 9 (cùng KV260,
  khác ngày, khác image), trong khi E lõi lệch 0,5 %. Đây là hiện tượng REG0 hai mức của tuần 9, mạnh hơn khi radio
  bật. Cách dùng số đã chốt ở §7.

| Mục | Giá trị |
|---|---|
| Source firmware | `device/week10/` commit `7767499` (`ble`, `ble-usb`), `device/week10/prot/` commit `9357451` (`prot`, `prot-usb`), cây sạch; phiên E_wait dùng image `energy` sạch tuần 8 `5d070cbaddf0-week8-energy-fast-20261026T055457Z` |
| Build | NCS 3.4.0, `nrf52840dongle/nrf52840`, kernel head `fast`; build ID `77674993ef18-week10-ble[-usb]-20261112T0712…Z`, `9357451f16d8-week10-prot[-usb]-20261112T0744…Z` |
| Bộ mẫu | Bộ W8-D3 (`set_sha256 7cfecbb2…1639`) |
| Plan | `prot` 1050 chu kỳ = 50 vòng × (10 cặp P1/P0 + 1 HEAD-only s1), hoán vị s seed 20261110, `plan_sha256 2094c48b…`; `ble` 550 chu kỳ = 50 vòng × s 0…10, seed 20261112, `plan_sha256 27e20954…`; khối tải E_wait seed 20261111, CSV `38937e54…035e` (W10-D1, W10-D3, W10-D4) |
| Bàn đo | Như tuần 9 (W9-D7): PPK2 Source Meter 5000 mV → breakout VBUS của dongle; marker D0 P0.13, D1 P0.15, D2 P0.17, D3 P0.20, D4 P0.22; 100 kS/s; laptop cắm sạc, Best performance |
| Liên kết BLE | KV260 là central, PHY 2M (Set PHY + Read PHY), connection interval 15 ms (`interval_1250us = 12`), peripheral latency 0, một kết nối |
| Phiên lab | 12/11 (VERIFY `ble-usb`, `prot-usb`; chạy khô với KV260; chạy khô `prot`), 13/11 (P1, P2 E_prot, 24–25 °C), 19/11 (A1, A2 E_wait; B1, B2 mọi s; 25 °C); raw ngoài Git tại `D:\HUST\ASI_week10\`, SHA-256 trong manifest |
| Công cụ | `generate_week10_plan.py`, `generate_week10_refs.py`, `build_week10.ps1`, `check_week10_build.py`, `flash_week10.ps1`, `week10_lab.py`, `check_week10.py`, `week10_ppk2.py`, `week10_prot.py`, `week10_ble.py`, `week10_analysis.py`, `week10_figures.py`, `publish_week10_results.py`; ppk2-api 0.9.2 |
| Kết quả | `results/week10/device/` (125 file + `manifest.json`; 87 file raw ngoài Git có SHA-256) |

## 1. Kết quả theo tiêu chí

| # | Tiêu chí | Kết quả | Bằng chứng |
|---:|---|---|---|
| 1 | Build 4 biến thể | **PASS** từ cây sạch (`dirty = false`): `ble-usb` 31/31, `ble` 33/33, `prot-usb` 24/24, `prot` 25/25 check tĩnh + Kconfig + cờ biên dịch. `prot` không BT/USB/log/LED, plan SHA nhúng và tự kiểm lúc boot, nonce chỉ đặt block lúc boot. Bin 747 268 / 711 008 / 668 136 / 627 352 B, giới hạn 897 024 B | `build_check/*_week10_build_check.json`, `build_resources.csv` |
| 2 | VERIFY + DWT, phiên khô | **PASS**. `prot-usb` 13/13: 500/500 q/scale = tham chiếu host, 500/500 output protect() = `i2_ref` Python (key test công khai), 50/50 output conv = host, TPROT s0–s9 + TCONV 50 lần mỗi s. Phiên khô `prot` 1050 chu kỳ 10/10. `ble-usb` 12/12: 550 VQ, 500 request = tham chiếu Python, 50 nhãn s10 = host. Chạy khô với KV260: 4a (queue bật, λ 0, 110 chu kỳ) 19/19, 4b (550 chu kỳ) 18/18, nhãn và logits = KV260 offline mọi s | `sessions/verify-*`, `sessions/dry-*` |
| 3 | Bàn đo khóa | **PASS** cả 6 phiên PPK2: I_idle P1/P2 24,55 / 24,49 µA, A1/A2 24,78 / 24,70 µA, B1/B2 25,55 / 24,83 µA (−3,7 … +0,5 % so 25,42 µA tuần 2); tự kiểm D0–D4 PASS; `BatteryStatus = 2` trước mọi capture; ảnh `bench-20261113-prot.png`, `bench-20261119-ewait.png`; 24–25 °C đọc tay | `sessions/*/check_*.json` |
| 4 | Phiên E_prot | **PASS** 15/15 cả hai phiên: 0 mất mẫu (135 069 696 / 135 069 184 mẫu, bộ đếm liên tục), đúng 1050 chu kỳ hợp lệ, thứ tự = plan, D1 chỉ trong chu kỳ P1, đúng 1 xung D1 đặt block lúc boot, tổng pha so cả chu kỳ < 3 % (lớn nhất 1,55 %), sau phiên về idle | `sessions/prot_P*/check_session.json` |
| 5 | `energy_prot.json` | **PASS**: CI95/mean ≤ 4,9 % mọi s (ngưỡng 10 %); W10-D2 "P1 < 1 lớp conv" **ĐẠT** mọi s 0–9 (§2) | `summaries/summary-prot-20261113-1242/energy_prot.json` |
| 6 | Phiên E_wait | **PASS** A1 32/32, A2 32/32: 0 mất mẫu, 200 chu kỳ (100 P1 + 100 P0) hợp lệ, KV260 trả đủ 200, nhãn = offline (`c91af325…`) 100/100 mỗi ρ, PHY 2M đọc lại, một kết nối, mọi request khớp một job foreground của `queue_sim` (lệch ≤ 36 ms < 50 ms), q ghi ở mọi request, median q ở λ 30 ≥ 4, nonce > prior và tăng. Hồi quy E_wait = a + b · t_wait: b = 1,699 µJ/ms (CI95 1,687–1,711), R² 0,995; b lệch P_conn 1,574 mW 7,9 % (§3) | `sessions/ewait_A*/check_ewait.json`, `summaries/summary-ewait-20261119-1531/` |
| 7 | Phiên mọi s, radio bật | **PASS** B1 25/25, B2 25/25: 550 chu kỳ, thứ tự = plan, 500 request (s0–s9) mỗi phiên, nhãn và logits = KV260 offline bit-exact mọi s, s10 nhãn tại chỗ = tham chiếu host (VERIFY), PHY 2M, một kết nối; bảng đủ cột theo s, CI95/mean < 10 % mọi s; W10-D5 **ĐẠT** (§4) | `sessions/alls_B*/check_alls.json`, `summaries/summary-alls-20261119-1614/` |
| 8 | Hồ sơ | **PASS**: báo cáo này; `results/week10/device` + manifest; test host PASS (§6); protocol G5 v1 push trước Π thử, đặc tả controller đã sửa P_conn, tập s chạy P2 + flash (§5); PR `dev/device-sv1` → `main` | `manifest.json` |

## 2. E_prot của P1 theo s (TC5, W10-D1, W10-D2)

`E_prot` = năng lượng ở đầu vào 5 V trong lúc marker D1 ở mức cao = lấy nonce từ block đã đặt lúc boot + ghi
descriptor + `protect()` (I2/1), radio tắt. Mỗi s có 100 chu kỳ P1 (50 mỗi phiên). Số gộp là trung bình 100 chu
kỳ; "khoảng phiên" là hai trung bình phiên; "E lõi" là hệ số chặn của E = a + b × tỉ lệ cao với khối 50 µs (5 mẫu,
chọn từ dữ liệu B5 tuần 9 trước khi đo, xem `prot_block_choice.json`). t_prot theo marker; DWT đo riêng ở
`prot-usb`.

| s | Giá trị (C × L) | Payload (B) | t_prot (ms) | **E_prot gộp (µJ)** | CI95 ± | Khoảng phiên (µJ) | Lệch phiên (%) | E lõi (µJ) | Lệch lõi (%) | Tỉ lệ cao (%), P1 / P2 | / E_conv,min | % E_dev(s) |
|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---:|
| 0 | 1 × 360 | 362 | 0,242 | **3,46** | 0,11 | 3,41–3,50 | 2,6 | 3,24 | 0,43 | 11,5 / 7,0 | 0,05 | 33,4 |
| 1 | 16 × 360 | 5792 | 2,286 | **40,46** | 1,64 | 39,21–41,71 | 6,2 | 31,09 | 0,25 | 33,0 / 43,9 | 0,54 | 24,8 |
| 2 | 16 × 180 | 2912 | 1,296 | **21,62** | 0,98 | 20,68–22,55 | 8,6 | 17,49 | 0,47 | 23,1 / 37,3 | 0,29 | 4,0 |
| 3 | 32 × 180 | 5824 | 2,478 | **42,21** | 1,70 | 39,64–44,78 | 12,2 | 33,45 | 0,30 | 23,0 / 42,9 | 0,57 | 4,3 |
| 4 | 32 × 90 | 2944 | 1,488 | **23,35** | 0,90 | 22,70–24,00 | 5,6 | 20,03 | 0,22 | 16,9 / 24,8 | 0,31 | 1,4 |
| 5 | 48 × 90 | 4416 | 2,268 | **36,38** | 1,33 | 35,00–37,76 | 7,6 | 30,49 | 0,23 | 18,1 / 29,1 | 0,49 | 1,5 |
| 6 | 48 × 45 | 2256 | 1,526 | **23,58** | 0,89 | 23,21–23,95 | 3,1 | 20,42 | 0,37 | 16,5 / 21,5 | 0,32 | 0,7 |
| 7 | 64 × 45 | 3008 | 1,966 | **29,17** | 0,76 | 27,82–30,52 | 9,2 | 26,27 | 0,37 | 7,2 / 20,3 | 0,39 | 0,7 |
| 8 | 64 × 22 | 1536 | 1,460 | **21,06** | 0,63 | 20,68–21,45 | 3,7 | 19,36 | 0,13 | 8,5 / 13,3 | 0,28 | 0,4 |
| 9 | 32 × 1 | 96 | 0,510 | **8,19** | 0,40 | 7,86–8,51 | 8,0 | 6,77 | 0,01 | 21,0 / 33,6 | 0,11 | 0,2 |

"% E_dev(s)" so với E_dev radio tắt của chu kỳ P0 cùng phiên. s10 là device-only, không gửi nên không có E_prot.

**Lớp conv tham chiếu (W10-D2).** E_conv,min = chu kỳ HEAD-only s1 (features.0 + ReLU, 1 → 16 kênh, không lượng tử,
marker D0), 50 chu kỳ mỗi phiên trong cùng phiên: **74,70 µJ** gộp (CI95 ± 2,03), phiên 69,50 / 79,91 µJ, E lõi
52,4 / 54,1 µJ, t_conv 3,542 ms (marker) / 3,613 ms (DWT ở `prot-usb`).

Luật W10-D2, khai trước khi đo: đạt khi trung bình phiên **lớn nhất** của E_prot(P1, s) nhỏ hơn trung bình phiên
**nhỏ nhất** của E_conv,min, ở mọi s 0–9. Kết quả: **ĐẠT mọi s**; tỉ lệ theo luật này lớn nhất ở s3 = 0,64, rồi
s1 = 0,60, s5 = 0,54; các s còn lại ≤ 0,44. So với lớp ngay trước điểm cắt (E_dev(s) − E_dev(s − 1) của tuần 9), P1
bằng 0,25 lần ở s1 và ≤ 0,09 lần khi s ≥ 2. Hình: [fig_e_prot_vs_conv](../results/week10/device/figures/fig_e_prot_vs_conv.png).

Nhận xét:

- **Chi phí P1 không tỉ lệ với số byte.** t_prot khớp mô hình t = 0,082 ms + 0,343 µs × (số giá trị) + 14,0 µs ×
  (số kênh), R² = 0,999, lệch lớn nhất 32 µs; E_prot = 1,57 µJ + 6,14 nJ × (số giá trị) + 0,168 µJ × (số kênh),
  R² = 0,997. Cấu trúc này đúng với thuật toán I2/1 (`contracts/i2_ref/i2_reference.c`): mỗi kênh sinh a_i, b_i và
  một bước hoán vị Fisher–Yates từ luồng khóa, mỗi giá trị chỉ làm một phép affine 8 bit. Vì vậy s1 và s3 (5760 giá
  trị) đắt nhất, còn s9 (32 kênh × 1) đắt hơn s0 (1 kênh × 360) dù payload nhỏ hơn 4 lần.
- **Công suất lúc chạy P1** là 14,3–17,7 mW gross (E_prot / t_prot), cùng mức với lúc tính head. Phần tính chịu cùng
  hiện tượng REG0 hai mức như E_dev: ở mọi s ≥ 1, phiên P2 có tỉ lệ cao lớn hơn P1 và số thô cao hơn P1 3,1–12,2 %
  (s0 ngược lại: tỉ lệ cao 11,5 → 7,0 %, thô −2,6 %), còn E lõi hai phiên lệch ≤ 0,47 % ở mọi s. Cách dùng số theo W9-D9/W9-D10: số chính = gộp, kèm khoảng phiên, E lõi và tỉ lệ cao.
- **Hiệu theo cặp Δ(P1 − P0)** của (E_dev + E_prot) chỉ dùng được ở s nông. Ở s0, s1, Δ = 3,6 ± 0,3 và
  41,6 ± 2,9 µJ, khớp E_prot đo bằng marker. Ở s ≥ 2, CI95 của Δ rộng ± 12–19 µJ vì dao động E_dev do REG0 (hàng
  trăm đến hàng nghìn µJ) lấn át phần P1 (20–40 µJ). Δ vẫn chứa E_prot marker trong CI95 ở mọi s, nhưng không đủ
  chặt để làm số chính. Số chính là E_prot đo bằng marker D1, đúng định nghĩa W10-D1; Δ chỉ báo kèm.
- **Marker so DWT:** t_prot marker lệch DWT ≤ 0,5 % ở s ≥ 1 (s0 + 1,7 %, do độ phân giải 10 µs so với 0,24 ms).
  t_conv marker ngắn hơn DWT 2,0 %; DWT đo ở `prot-usb` có USB bật nên chỉ dùng để gỡ lỗi, không vào số năng lượng.
- **So radio bật (tuần 9, s2, KV260):** E_prot gross 22,7 µJ (tuần 9) so với 21,6 µJ (tuần 10); E lõi cùng khối
  50 µs là 18,7 µJ (B5 tuần 9) so với 17,5 µJ. Radio kết nối làm E_prot tăng khoảng 1,2 µJ (+7 %) ở s2, cùng chiều
  với E_dev (+5,5 %, tuần 9 §4).

### 2.1. Chu kỳ P0: E_dev radio tắt ở ngày khác (chỉ báo, W9-D11)

Mỗi phiên E_prot có 500 chu kỳ P0 = CTRL + HEAD(s), giống chu kỳ đo E_dev tuần 9. Đây là phép thử sớm luật so khác
ngày W9-D11 của tuần 13 (13/11 so với 29/10). **Bảng III vẫn giữ số tuần 9.**

| s | E_dev P0 13/11 (µJ) | Bảng III tuần 9 (µJ) | Lệch thô (%) | E lõi 13/11 (µJ) | E lõi tuần 9 (µJ) | Lệch lõi (%) | Ngưỡng lõi |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 10,36 | 9,84 | +5,4 | 6,44 | 6,03 | +6,7 | 8 % |
| 1 | 163,4 | 169,1 | −3,4 | 140,0 | 140,3 | −0,2 | 8 % |
| 2 | 539,6 | 558,5 | −3,4 | 481,4 | 483,3 | −0,4 | 2 % |
| 3…9 | | | −2,3…−3,9 | | | −0,3…−0,5 | 2 % |

**ĐẠT mọi s**: thô < 10 % và lõi trong ngưỡng. Lõi khớp tuần 9 trong 0,5 % ở s ≥ 1, tức cùng firmware và trọng số
cho cùng chi phí tính sau hai tuần. Thô thấp hơn khoảng 3 % vì tỉ lệ REG0 ở mức cao ngày 13/11 thấp hơn ngày 29/10.
Riêng s0 (0,55 ms) lệch lõi +6,7 %, vẫn dưới ngưỡng 8 % của s ≤ 1; như tuần 9 §7, ở s0 chu kỳ quá ngắn nên phép
ngoại suy E lõi kém chính xác hơn.

## 3. E_wait theo hàng đợi (TC6, W10-D3)

Thiết kế khóa trước buổi đo (commit `df243a9`): image `energy` tuần 8 (s2, 100 cặp P1/P0), service KV260 có
`queue_sim` FIFO 8 job nền + 1 foreground, request BLE xếp hàng như job nền; tải theo khối 20 s, λ ∈ {0, 15, 30}
job/s, thứ tự khối ngẫu nhiên (seed 20261111). Hai phiên khác seed tải: A1 seed 101, A2 seed 102 (§6, mục 7).
E_wait = năng lượng marker D3 (từ lúc gửi xong tới lúc parse xong phản hồi); t_wait theo marker; q = số job đứng
trước request lúc nó đến (`queue_length_jobs` − 1).

**Theo mức tải** (gộp 2 phiên, bỏ 2 s đầu mỗi khối):

| λ (job/s) | n | q lúc đến | t_wait (ms) | E_wait (µJ) | CI95 ± (µJ) | Lệch phiên E_wait (%) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 103 | 0 | 96,9 | **281,9** | 5,7 | 0,8 |
| 15 | 163 | 1,04 | 161,3 | **388,3** | 19,5 | 9,8 |
| 30 | 96 | 6,93 | 463,0 | **900,3** | 22,1 | 0,04 |

Ở λ 15 hai phiên lệch 9,8 % vì q trung bình mỗi phiên khác nhau (tải Poisson theo seed, q lệch 32 %); khi xét theo q
thì hai phiên khớp (bảng dưới). Ở λ 30 hàng đợi gần đầy (median q ≥ 4, đạt luật), t_wait 463 ms, sát hạn D = 500 ms.

**Theo q** (mọi chu kỳ, gộp 2 phiên):

| q | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| n | 201 | 44 | 29 | 13 | 10 | 4 | 18 | 45 | 36 |
| t_wait (ms) | 100,9 | 161,4 | 211,7 | 265,7 | 319,0 | 350,5 | 417,2 | 472,5 | 504,8 |
| E_wait (µJ) | 287,6 | 387,5 | 474,0 | 556,7 | 659,0 | 704,3 | 826,9 | 919,1 | 969,6 |

**Hai hồi quy (luật khai trước):**

- t_wait = 103,3 + 51,73 ms × q (CI95 độ dốc 51,10–52,36; R² 0,985; n = 400). t_service của job nền đo ở KV260 =
  48,90 ms → độ dốc / t_service = **1,06**, trong [0,8; 1,2] → **dùng mô hình q̂ · t_svc** của Algorithm 1 (hạng tử
  hàng đợi eq (1) của Khung). Từng phiên: 51,89 / 51,56 ms/job (1,06 / 1,06).
- E_wait = 115,1 + **1,699 µJ/ms** × t_wait (CI95 độ dốc 1,687–1,711; hệ số chặn 111,8–118,4 µJ; R² 0,995;
  n = 400). Từng phiên: 1,682 / 1,715. Độ dốc b là công suất trong lúc chờ (P_wait), lệch P_conn gross đo từ khoảng
  nghỉ giữa chu kỳ cùng phiên (1,574 mW; tuần 9: 1,582 mW) **7,9 %**, trong ngưỡng 20 % → **dùng mô hình đường
  thẳng**. Hệ số chặn a ≈ 115 µJ là chi phí nhận và parse phản hồi.
- **P_wait = 13,4 × P_idle radio tắt.** Nếu controller dùng P_idle (0,125 mW) như công thức gốc của Lộ trình 9.2
  thì E_wait bị hụt khoảng 13 lần. Controller phải dùng P_wait ≈ P_conn.

Hàng đợi dài (λ 30) / rỗng (λ 0) = **3,21 ×** E_wait. Hai phiên khớp nhau: độ dốc t_wait lệch 0,6 %, độ dốc E_wait
lệch 2,0 %. E_wait hầu như chỉ là năng lượng giữ kết nối nên không bị hiện tượng REG0 hai mức (P_conn lặp lại
trong 0,7 % giữa A1, A2, B1, B2 và tuần 9).

Hình: [fig_twait_vs_q](../results/week10/device/figures/fig_twait_vs_q.png),
[fig_ewait_vs_twait](../results/week10/device/figures/fig_ewait_vs_twait.png).

## 4. Chu kỳ mọi s lúc radio bật (TC7, W10-D4, W10-D5)

Image `ble` (ρ0, s 0…10, s10 = device-only giữ kết nối), queue tắt, KV260 nạp sẵn tail s0–s9 (cache), hàng đợi
rỗng. n = 50 mỗi s mỗi phiên, gộp 100 chu kỳ mỗi s. P_conn B1/B2 = 1,574 / 1,580 mW.

| s | Tensor (B) | E_dev,on (µJ) | Lệch phiên (%) | E lõi (µJ) | Thô on/off | Lõi on/off | E_tx (µJ) | E_wait (µJ) | **E chu kỳ (µJ)** | CI95 ± | T (ms) | t_edge (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 362 | 9,4 | 8,4 | 5,6 | 0,96 | 0,92 | 29,5 | 254,9 | **299,5** | 6,6 | 83,2 | 57,4 |
| 1 | 5792 | 193,9 | 0,6 | 170,2 | 1,15 | 1,21 | 1365,6 | 325,9 | **1891,6** | 21,2 | 194,5 | 99,5 |
| 2 | 2912 | 718,6 | 2,5 | 512,4 | 1,29 | 1,06 | 705,4 | 275,7 | **1705,9** | 26,7 | 163,7 | 72,2 |
| 3 | 5824 | 1336,0 | 3,7 | 976,5 | 1,31 | 1,06 | 1389,3 | 321,8 | **3053,3** | 51,3 | 247,6 | 91,0 |
| 4 | 2944 | 2322,3 | 3,4 | 1731,4 | 1,30 | 1,04 | 699,0 | 257,2 | **3284,7** | 40,0 | 235,0 | 60,5 |
| 5 | 4416 | 3126,7 | 4,5 | 2437,6 | 1,28 | 1,05 | 1075,3 | 250,4 | **4458,9** | 45,7 | 311,9 | 66,7 |
| 6 | 2256 | 4329,8 | 3,2 | 3393,2 | 1,27 | 1,04 | 573,7 | 223,8 | **5133,7** | 52,3 | 337,5 | 41,0 |
| 7 | 3008 | 5246,9 | 4,5 | 4159,8 | 1,26 | 1,04 | 758,5 | 242,1 | **6253,7** | 66,9 | 402,2 | 41,4 |
| 8 | 1536 | 6452,5 | 2,8 | 5160,1 | 1,26 | 1,05 | 409,1 | 191,6 | **7059,4** | 66,3 | 441,8 | 19,7 |
| 9 | 96 | 6559,6 | 2,9 | 5217,2 | 1,25 | 1,04 | 26,5 | 146,4 | **6738,1** | 67,1 | 411,9 | 7,4 |
| 10 | 0 | 6541,6 | 4,1 | 5242,7 | 1,25 | 1,05 | — | — | **6545,7** | 64,5 | 383,5 | — |

"Tensor" là payload I1 v2 (header + int8). "E chu kỳ" và T tính từ cạnh lên CTRL tới cạnh xuống WAIT (= E_tot của
Khung trừ E_prot, vì ρ0); tổng các pha lệch E chu kỳ ≤ 0,77 %. "on/off" so với E_dev radio tắt Bảng III tuần 9.
E_prot ρ0 = 0. Cột Acc thuộc SV3.

**E_tx theo payload** (10 điểm s0–s9): E_tx = 4,44 + **0,240 µJ/B** × B (CI95 độ dốc 0,227–0,252; R² 0,996) → tuyến
tính, không cần cảnh báo (ngưỡng R² 0,95). Điểm lệch xa nhất là s0 (−62 µJ so với đường thẳng): 362 B vừa một
connection event nên rẻ hơn hồi quy. Thời gian truyền ≈ 11,6 µs/B. Hình:
[fig_etx_vs_payload](../results/week10/device/figures/fig_etx_vs_payload.png).

**W10-D5 (công thức E_dev,on):** E lõi radio bật so với E lõi radio tắt tuần 9 + 0,7 mW × t_dev lệch −1,03 … +0,52 %
ở mọi s ≥ 2 → **ĐẠT** (ngưỡng 2 %). Hằng số 0,7 mW lấy từ s2 tuần 9 nên s2 không phải điểm kiểm độc lập; 8 điểm s3…s10
là kiểm thật. s0 (−13 %) và s1 (+14 %) ngoài luật: chu kỳ ngắn, E lõi ngoại suy kém chính xác, và s1 lệch lõi giữa
hai phiên tới 21 %. Hình: [fig_dev_on_vs_off](../results/week10/device/figures/fig_dev_on_vs_off.png).

**Số thô radio bật cao hơn radio tắt 25–31 % ở s ≥ 2**, trong khi phần lõi chỉ cao hơn 4–6 % (đúng bằng 0,7 mW ×
t_dev). Phần chênh còn lại nằm ở tỉ lệ thời gian REG0 chạy mức cao: khi radio bật, tỉ lệ này tăng. So với phiên B5
tuần 9 (cùng KV260, image `energy`, s2): thô 718,6 so với 624 µJ (+15 %, vượt 10 % của luật so khác ngày W9-D11),
lõi 512,4 so với 510 µJ (+0,5 %). Theo từng chu kỳ, E_dev s2 dao động 588–834 µJ. Cách dùng số: §7.

**Thứ tự năng lượng và thời gian theo s.** Gửi thô (s0) rẻ và nhanh nhất ở mọi trạng thái hàng đợi đo được. Mọi
s1…s8 tốn hơn và chậm hơn s0 vì tensor không lần nào nhỏ hơn đầu vào trước s9; s9 gần như bằng s10 cộng thêm phần
gửi và chờ. Riêng phần tính head s1 đã tốn thêm 185 µJ so với s0, nhiều hơn toàn bộ E_tx của s0 (29,5 µJ). Hình:
[fig_cycle_by_split_radio_on](../results/week10/device/figures/fig_cycle_by_split_radio_on.png).

## 5. Hồ sơ đã khóa trước khi có số đo

- **Protocol mô phỏng G5 v1** (W10-D7): `experiments/g5_sim/protocol_v1.md`, commit `c5aaf3f`
  (12/11 12:14 +07, SHA-256 `0d43bb24…a808bb`), push lên `dev/device-sv1` **trước khi có Π thử** (SV3 chưa gửi số Π
  nào sau 09/11). Bản v1.1 commit `96d6dd2` (12/11 12:20, SHA-256 `2a16fabf…fdda2b1`) chỉ thêm quét tải ổn định
  (L-steady/E8b), cũng trước Π thử. Số đo đến sau chỉ là đầu vào. Protocol G5 v2 (theo hướng xử lý chốt 19/11) sẽ
  khóa ở tuần 13.
- **Luật phân tích W10-D1…D5** (checker, `week10_analysis.py`, tách chu kỳ) commit `df243a9`, `7767499`, `9357451`,
  `36ce0cc`, `ca0a67d` (12/11), trước phiên đo đầu tiên (13/11 11:54). Cỡ khối 50 µs cho E lõi pha PROT chọn từ B5
  tuần 9 ngày 12/11. Một lần sửa sau khi thấy dữ liệu: `5feb8d2` (19/11, §6 mục 6).
- **Đặc tả controller** (việc 1a tuần 9): đã sửa P_conn 0,62 mW → 1,58 mW gross / 1,46 mW net (KV260, interval
  15 ms), ngưỡng Δ để "s10 tắt radio" rẻ hơn s2 từ 7,9 s → 2,6 s, thêm P_conn(k) theo interval.
- **Tập s chạy P2 trên dongle** (W10-D9): {s2, s_m}, s_m theo luật 05/11 (s4 mặc định, s5 chỉ khi riêng s5 đạt ở
  ρ0/ρ1). Head NoPeek FP32: s2 5,6 KB, s4 36,5 KB, s5 67,5 KB → nhiều nhất 73,1 KB; thêm SMP khoảng 15 KB và mã
  nhiễu. Image `ble` hiện dùng 711 008 B, còn trống 186 016 B (181,7 KiB) dưới vùng NVS → đủ chỗ, không cần lượng tử
  trọng số head, không phải đo lại E_dev. Đo lại flash từ image thật ở tuần 12. (Theo hướng xử lý 19/11, ρ1 ra khỏi
  tập hành động; ρ2 ở s2 là đường mở rộng có giới hạn, nên phần flash này chỉ cần nếu đường đó đạt.)

## 6. Sự cố và ghi chú

1. **Lệch 1 ở số NONCE ghi trong kế hoạch.** Số "60657663" ghi trước đây cho `--prior-reserved-through` thấp hơn
   thực tế 1. Đọc NONCE bằng `prot-usb` ngày 12/11: `reserved_through` = 60 658 688, giải thích được hoàn toàn (block
   B5-4 tuần 9 + một lần boot `energy` khi cắm laptop). Không có tiêu hao lạ. Prior là cận dưới nên kiểm "nonce >
   prior" vẫn đúng.
2. **REBOOT qua CDC ở `prot-usb` không khởi động lại** sau phiên khô (lần đọc NONCE sau đó trả mã 1 vì
   `block_reserved = 1`). Giá trị `reserved_through` = 60 659 712 vẫn đúng; không ảnh hưởng image `prot`.
3. **DLL shim host trên Windows** (12/11): Windows không ghi đè DLL đang nạp nên lần import thứ hai trong cùng tiến
   trình lỗi. Sửa ở commit `9f56198`: mỗi lần build dùng tên DLL riêng.
4. **Thời lượng capture mặc định** (12/11): 1260 s chỉ để lại khoảng 5 s sau phiên `prot`, chắc chắn trượt check
   `post_window`. Sửa trước phiên đo ở commit `ca0a67d`: prot 1350 s, alls 960 s, ewait 540 s.
5. **Buổi đo với KV260 dời 14/11 → 19/11** vì máy của SV2 hỏng. Trong thời gian chờ, dongle giữ image `prot` trên
   breakout; ngày 19/11 nạp `energy` (biên nhận `dfu-20261119-123946-energy-fast.json`) cho A1, A2 rồi `ble`
   (`dfu-20261119-153454-week10-ble.json`) cho B1, B2.
6. **Luật `post_radio_off` sửa sau khi thấy dữ liệu A1** (commit `5feb8d2`, trước khi import A1 và trước phiên A2).
   Lần chấm đầu A1 FAIL vì hai xung 0,29 ms ở 513,8 / 514,2 s sau khi dongle bật. Đây là ngắt tràn RTC 24 bit
   (32 768 Hz → mỗi 512 s), không phải radio: phiên P1 ngày 13/11 với image `prot` không có BT cũng có xung ở
   513,6 / 1025,6 s, và A2 lặp lại ở 513,81 / 514,15 s. Luật mới: luật tuần 9 HOẶC mọi xung ≤ 0,5 ms nằm trong ±3 s
   quanh k · 512 s, ≤ 2 xung mỗi mốc. Lần chấm đầu giữ trong `sessions/ewait_A1-20261119-1500/check_session.json`
   (FAIL) làm bằng chứng; lần chấm cuối `check_ewait.json` PASS. Luật này chỉ đụng tới kiểm "radio tắt sau phiên",
   không đụng số năng lượng nào.
7. **Seed tải thực tế 101 / 102**, không phải 111 / 222 như tin hẹn với SV2 và như ghi chú gõ tay trong
   `session.json` của A1 ("seed 111"). Seed thật lấy từ `queue_run.json` của SV2; hai phiên vẫn khác seed nên đúng
   W10-D3. A1 là lần chạy thứ hai của SV2 (`A1_lan_2.tar.gz`); lý do bỏ lần thứ nhất SV2 xác nhận khi review PR.
8. **Báo cáo chấm FAIL trong manifest** (3 trên 17): hai lần chấm đầu của chạy khô 4a, 4b là trước khi import log KV260
   (`kv260_log_imported = false`, đúng quy trình), lần chấm sau PASS; lần còn lại là A1 ở mục 6.
9. **Test host** chạy lại 19/11 trên `5feb8d2`: `test_week10_host.py` 24/24, `test_week10_ble_host.py` 10/10,
   `test_week10_prot_host.py` 6/6, `test_week10_figures_host.py` PASS. Lần FAIL không tái hiện được ngày 13/11 (nghi
   nhóm `QueueLog` chạy Dispatcher thật của SV2 theo thời gian thực) không lặp lại.

## 7. Ảnh hưởng tới mô hình và bài báo

- **Mô hình E_wait cho controller:** E_wait(q) = 115 µJ + P_wait · (t_0 + q̂ · t_svc), P_wait ≈ P_conn (1,57–1,70 mW),
  không phải P_idle. Hạng tử hàng đợi q̂ · t_svc của Algorithm 1 đúng với số đo (1,06 ×). Đây là bằng chứng trực tiếp
  cho câu "E_wait tăng theo hàng đợi" mà Khung yêu cầu.
- **P1 ngoài tập hành động** (chốt 03/11): kết quả E_prot không đụng N1–N3. Bài chỉ cần 2–3 câu: P1 hiện thực trên
  MCU, chi phí 3,5–42 µJ (0,2–4,3 % E_dev ở s ≥ 2; tối đa 0,64 lớp conv rẻ nhất theo luật chặt), và lý do không dùng
  (P1 không che dữ liệu trước edge).
- **Điểm cắt giữa bị s0 hoặc s10 áp đảo** ở cấu hình đo (2M, 15 ms, hàng đợi rỗng tới đầy). Kết quả này cùng Π thử
  của SV3 dẫn tới hướng xử lý chốt 19/11/2026 (tài liệu gửi nhóm, ngoài repo): giữ mô hình, tập hành động gồm mọi s
  và trạng thái radio BLE, ràng buộc tỉ lệ nhịp xử lý tại chỗ, luật hòa vốn kiểm bằng số đo. Hệ quả cho phần đo: lab
  tuần 12 đo E_tx và P_conn theo PHY, interval, **peripheral latency** (mọi số tuần 8–10 là latency 0) và độ dài gói.
- **REG0 hai mức mạnh hơn khi radio bật** (§4). Cách dùng số (chốt 19/11): Table III/LUT dùng số thô gộp 2 phiên + cột
  E lõi + khoảng phiên; bài nêu lệch khác ngày tới 15 % ở số thô và ≤ 1 % ở phần lõi; mô phỏng G5 có dải độ nhạy
  E_dev ± 15 %; đo đối chứng dongle cấp VDD xét cuối tuần 13. Checklist "đo lại ngày khác lệch < 10 %" báo theo cả
  hai: thô (tới 15 %) và lõi (≤ 1 %). E_tx, E_wait, P_conn không bị ảnh hưởng (lặp lại ≤ 2 %).
- **Kiểm tái lập khác ngày** của E_dev radio tắt (§2.1) đạt luật W9-D11 trước tuần 13.

## 8. Giới hạn và việc tiếp theo

- Một dongle, một bàn đo, một hình học anten; nhiệt độ phòng đọc tay lúc bắt đầu buổi, không đọc lại giữa các phiên.
- E lõi là phép ngoại suy tuyến tính theo tỉ lệ cao; R² ≥ 0,99 ở s ≥ 1 với E_prot; ở s0, s1 của phiên mọi s phép ngoại
  suy kém (§4).
- E_wait chỉ đo ở s2 (image `energy`); với s khác, phần phụ thuộc q giống nhau (job nền như nhau), chỉ t_edge của
  foreground đổi theo s (bảng §4).
- Mọi số đo ở PHY 2M, interval 15 ms, peripheral latency 0, data length tối đa. Các trạng thái kênh khác đo ở tuần 12.
- Trạng thái bàn đo cuối tuần 10: dongle chạy `ble` (build `77674993ef18`), nằm trên breakout PPK2; `--prior-reserved-through`
  cho phiên `prot`/`energy` tiếp theo ≥ 60 662 784 + 1024 × (số lần boot `energy` sau 13/11).
- Tuần 11: theo hướng xử lý 19/11 (lab tuần 12 ở trên; contract I3; chuẩn bị D0–D7 tuần 13).

## Phụ lục A. Tiêu chí nghiệm thu và quyết định W10-D1…W10-D9

### A.1. Tám tiêu chí (chốt 10/11)

| # | Tiêu chí | Định nghĩa đạt |
|---:|---|---|
| TC1 | Build | `device/week10/` từ cây sạch, 4 biến thể `prot-usb`, `prot`, `ble-usb`, `ble`, kiểm tĩnh PASS; `prot` không BT/USB/log/LED, plan SHA nhúng + tự kiểm lúc boot, nonce chỉ đặt block lúc boot (trước cửa sổ idle) |
| TC2 | VERIFY | `prot-usb` q/scale trùng tham chiếu host mọi (s, mẫu); output protect() trùng `i2_ref` Python (key test công khai) mọi s; DWT TPROT(s) + HEAD-only s1. `ble-usb` phiên khô với KV260: nhãn = KV260 offline mọi s của plan, request đi qua queue |
| TC3 | Bàn đo khóa | Như TC3 tuần 9 (I_idle ≤ 10 % so 25,4 µA, ảnh, nhiệt độ, tự kiểm D0–D4) + `BatteryStatus = 2` trước mỗi capture |
| TC4 | Phiên E_prot | ≥ 2 phiên hợp lệ: 0 mất mẫu, đúng số chu kỳ + thứ tự = plan, D1 chỉ ở chu kỳ P1, nonce tăng và > prior, tổng pha < 3 % |
| TC5 | `energy_prot.json` | Mỗi s 0–9: E_prot P1 (gross, net, lõi, tỉ lệ cao), t_prot marker + DWT, Δ(P1 − P0) theo cặp của D0 + D1, CI95/mean < 10 %; kèm E_dev radio tắt của chu kỳ P0 và E_conv,min; kết luận "P1 < 1 lớp conv" theo W10-D2, báo đúng kết quả dù đạt hay trượt |
| TC6 | Phiên E_wait | ≥ 2 phiên hợp lệ như TC7 tuần 9 (log 200 OK, nhãn = offline, PHY 2M, một kết nối) + log KV260 có q lúc request đến; E_wait, t_wait theo mức tải và theo q; hồi quy E_wait = a + b · t_wait (b, CI95, R²), so b với P_conn gross 1,58 mW |
| TC7 | Phiên mọi s | `ble`, s 0–10, ≥ 2 phiên, n = 50 mỗi s mỗi phiên, thứ tự = plan, nhãn = KV260 offline mỗi s (s10: nhãn tại chỗ = tham chiếu host); bảng Tensor, E_dev,on, E_tx, E_wait, E_tot, T, t_edge, P_conn theo s; kiểm công thức E_dev,on theo W10-D5 |
| TC8 | Hồ sơ | Báo cáo này, `results/week10/device` + manifest, test host PASS, PR; protocol G5 v1 đã push trước Π thử (W10-D7); đặc tả controller đã sửa P_conn; ghi tập s chạy P2 trên dongle + flash (W10-D9) |

### A.2. Quyết định (chốt 10/11/2026)

| # | Quyết định |
|---|---|
| W10-D1 | E_prot đo ở image radio tắt `prot`: s 0–9, mỗi vòng một hoán vị s (seed 20261110), mỗi s một cặp P1/P0 liền nhau, thứ tự trong cặp xen kẽ theo vòng, thêm 1 chu kỳ HEAD-only s1; 50 vòng (≈ 21 phút/phiên), vòng k dùng mẫu k của bộ W8-D3. E_prot = năng lượng marker D1 (nonce + descriptor + protect()); số chính gross 5 V gộp phiên, kèm lõi + tỉ lệ cao; cỡ khối tỉ lệ cao pha PROT chọn từ B5 tuần 9 trước khi đo |
| W10-D2 | "1 lớp conv" = lớp conv rẻ nhất của head (features.0 + ReLU, s0 → s1), đo trực tiếp bằng chu kỳ HEAD-only s1 trong cùng phiên. Đạt khi trung bình phiên lớn nhất của E_prot(P1, s) < trung bình phiên nhỏ nhất của E_conv,min ở mọi s 0–9. Báo thêm tỉ lệ so lớp ngay trước s và % E_dev(s). Không tối ưu code P1 trong tuần 10 |
| W10-D3 | E_wait: image `energy` tuần 8 + service KV260 có `queue_sim` (FIFO 8 + 1), tải khối 20 s λ ∈ {0, 15, 30} job/s, thứ tự khối seed 20261111; ≥ 2 phiên khác seed tải; hồi quy E_wait = a + b · t_wait và t_wait theo q; dùng q̂ · t_svc nếu độ dốc / t_svc ∈ [0,8; 1,2]; dùng đường thẳng E_wait nếu R² ≥ 0,9 và \|b − P_conn\| / P_conn ≤ 20 %, không thì bảng 50 ms |
| W10-D4 | Phiên mọi s: image `ble`, chỉ ρ0, s 0–10 (s10 device-only), hoán vị s seed 20261112, n = 50/s, ≥ 2 phiên; Table III dùng số đo trực tiếp, LUT dùng E_dev radio bật, Bảng III giữ radio tắt |
| W10-D5 | Công thức E_dev,on ≈ E_dev,off + 0,7 mW · t_dev kiểm bằng E lõi, đạt khi lệch ≤ 2 % ở s ≥ 2; chỉ để giải thích vật lý, LUT luôn là số đo |
| W10-D6 | Mọi phiên xen kẽ cấu hình, ≥ 2 phiên mỗi cấu hình, báo gộp + khoảng phiên + lõi + tỉ lệ cao; luật phân tích commit trước phiên đo |
| W10-D7 | Protocol mô phỏng G5 v1 commit + push trước Π thử; SHA ghi trong báo cáo (§5) |
| W10-D8 | Firmware mới `device/week10/`, script `*_week10*`; dùng lại nguyên vẹn head_fast, quantization, i2, ble_link, dev_cycle; không sửa file tuần 7–9 |
| W10-D9 | Tập s chạy P2 trên dongle = {s2, s_m}; flash đủ (§5) |
| Bổ sung 19/11 | Luật `post_radio_off` bỏ qua xung tràn RTC tại k · 512 s (§6 mục 6). Cách dùng số thô/lõi khi REG0 hai mức mạnh hơn lúc radio bật (§7) |

### A.3. Việc còn mở của người khác

- Trung (SV2): review phần KV260/E_wait của PR tuần 10; xác nhận lý do bỏ lần chạy A1 thứ nhất (§6 mục 7).
- Kỳ Anh (SV3): không có việc phụ thuộc vào số tuần 10; E_prot P1 không vào bảng dạng dài (P1 ngoài tập hành động).

## Phụ lục B. Firmware `device/week10/`

| File | Vai trò |
|---|---|
| `main.c`, `ble_cycle.c/.h` | App `ble`/`ble-usb`: fork `g2_cycle` tuần 8 + `dev_cycle` tuần 9; chu kỳ CTRL → HEAD(s) → TX → WAIT với s theo plan, ρ0, không NVS/nonce; s10 = HEAD + nhãn FP32 tại chỗ, không TX/WAIT, giữ kết nối. `ble-usb`: VERIFY, SESSION khô qua CDC |
| `ble_plan_bytes.h`, `Kconfig`, `CMakeLists.txt`, `overlay-ble.conf`, `overlay-ble-usb.conf` | Plan (s, ρ, B, k) để tuần 11 chỉ thêm plan E_tx(B)/P_conn(k); `ble_link` tuần 8, overlay radio tuần 7 |
| `host_test/ble_shim.c` | head + lượng tử + đóng gói request trên host (gcc) cho tham chiếu |
| `prot/main.c`, `prot/prot_cycle.c/.h` | App `prot`/`prot-usb`, radio tắt, NVS nonce tuần 6: P1 = CTRL + HEAD + PROT (D1), P0 = CTRL + HEAD, CONV = head s1 không lượng tử. `prot` đặt 1 block nonce lúc boot (1 xung D1 trước tự kiểm); `prot-usb` không đặt block lúc boot (lệnh NONCE đọc được trạng thái của image trước) |
| `prot/Kconfig`, `prot/overlay-nvs.conf`, `prot/overlay-prot.conf`, `prot/overlay-prot-usb.conf` | Cấu hình hai biến thể |

## Phụ lục C. Quy trình chạy lại

Biến dùng chung (PowerShell, gốc repo):

```powershell
$env:Path = 'C:\msys64\ucrt64\bin;' + $env:Path   # gcc cho shim host
$py  = "device\host\.venv\Scripts\python.exe"
$W10 = "D:\HUST\ASI_week10"
$smp = "D:\HUST\ASI_week8\samples-20261023-c"
$plan = "$W10\plan-20261112"
```

Trước mọi capture PPK2: **cắm sạc laptop, Power mode = Best performance**, đóng nRF Connect Power Profiler, không
dùng laptop hay chép file trong lúc đo, `$py -B device\scripts\week10_ppk2.py probe --port COM8`, đo nhiệt độ phòng,
chụp ảnh bàn đo. PPK2 = COM8; bootloader dongle = COM6 (RESET cạnh dài, bấm ngang; LED đỏ thở = bootloader); app = COM7.
`--prior-reserved-through` là cận dưới của NONCE (mỗi lần boot `energy`/`prot` tốn 1 block 1024); không bao giờ `PROV ERASE`.

1. Plan và tham chiếu (tất định, sinh lại ra cùng SHA): `$py -B device\scripts\generate_week10_plan.py --output $W10\plan-<mới>`
   (prot `2094c48b…`, ble `27e20954…`, CSV tải `38937e54…`), `$py -B device\scripts\generate_week10_refs.py` → refs s0…s9.
2. Build: `device\scripts\build_week10.ps1 -ReportDir $W10\build-<mới> -Variant prot|prot-usb|ble|ble-usb -Samples $smp -Plan $plan`.
3. Nạp (dongle cắm laptop, RESET): `device\scripts\flash_week10.ps1 -Port COM6 -ReportDir <build> -ReceiptDir $W10\dfu`.
   Image `energy` tuần 8: `device\scripts\flash_week8.ps1 -Port COM6 -ReportDir D:\HUST\ASI_week8\build-20261026-clean-energy -ReceiptDir $W10\dfu`.
4. TC2 prot (`prot-usb`): `week10_lab.py nonce`, `week10_lab.py verify-prot`, `week10_lab.py session-prot` (chạy khô).
   TC2 ble (`ble-usb` + KV260): `week10_lab.py verify`, rồi `week10_lab.py session --out <dir> --samples $smp --plan $plan [--count 110]`
   và `week10_lab.py import-kv260 --out <dir> --kv260-log <capture\requests.jsonl> --edge-reference <predictions_s0…s9> [--queue-dir <capture\queue_sim> --require-queue]`.
   `<predictions_s0…s9>` = 10 lần `--edge-reference D:\HUST\ASI_week10\from-trung-20261112-cache\gui_sv1_cache\predictions\predictions_s{0..9}.jsonl`.
   Log chính thức của SV2 là `capture\requests.jsonl` (không dùng `capture\peer.jsonl`).
5. Phiên E_prot (`prot` trên breakout, không cắm laptop trước):
   `$py -B device\scripts\week10_ppk2.py session-prot --port COM8 --out $W10\P<k>-<giờ> --temp-c <t> --image $W10\build-20261112-clean-prot --receipt $W10\dfu\dfu-20261112-211138-week10-prot.json --samples $smp --plan $plan --prior-reserved-through <cận dưới>`
   (~22,5 phút), rồi `week10_ppk2.py summary-prot --session <P1> --session <P2> --tprot $W10\verify-prot-20261112\check_verify-prot-20261112T140553Z.json --out $W10\summary-prot-<giờ>`.
6. Phiên E_wait (`energy` tuần 8 trên breakout; SV2 bật `queue_sim` với `ewait_load_blocks.csv`, khác seed mỗi phiên, bắt đầu khi liên kết sẵn sàng):
   `$py -B device\scripts\week10_ppk2.py session-ewait --port COM8 --out $W10\A<k>-<giờ> --temp-c <t> --image D:\HUST\ASI_week8\build-20261026-clean-energy --receipt <biên nhận energy mới> --samples $smp --plan $plan --prior-reserved-through <cận dưới> --note "<seed, commit service>"`,
   rồi `week10_ppk2.py import-ewait --out <A> --kv260-log <capture\requests.jsonl> --phy-log <capture\phy.jsonl> --queue-dir <capture\queue_sim> --edge-reference D:\HUST\ASI_week8\from-trung-20261026-g2\review\offline_second\predictions.jsonl`
   (`c91af325…`). Sau ≥ 2 phiên PASS: `week10_ppk2.py summary-ewait --session <A1> --session <A2> --out $W10\summary-ewait-<giờ>`.
7. Phiên mọi s (`ble` trên breakout; SV2 tắt queue, nạp sẵn tail s0–s9):
   `$py -B device\scripts\week10_ppk2.py session-alls --port COM8 --out $W10\B<k>-<giờ> --temp-c <t> --image $W10\build-20261112-clean-ble --receipt <biên nhận ble> --samples $smp --plan $plan`,
   rồi `week10_ppk2.py import-alls --out <B> --kv260-log <capture\requests.jsonl> --phy-log <capture\phy.jsonl> <predictions_s0…s9>`.
   Sau ≥ 2 phiên PASS: `week10_ppk2.py summary-alls --session <B1> --session <B2> --out $W10\summary-alls-<giờ>`.
8. Bảng và hình: `$py -B device\scripts\week10_figures.py tables --prot-summary $W10\summary-prot-20261113-1242 --ewait-summary $W10\summary-ewait-20261119-1531 --ewait-session $W10\A1-20261119-1500 --ewait-session $W10\A2-20261119-1518 --alls-summary $W10\summary-alls-20261119-1614 --out $W10\analysis-<giờ>`,
   rồi `week10_figures.py figures --tables <dir>`. Phần thiếu ghi MISSING. Bản dùng cho báo cáo: `$W10\analysis-20261119`.
9. Công bố (đã chạy 19/11, ra 125 file):

   ```powershell
   & $py -B device\scripts\publish_week10_results.py --lab $W10 `
     --session verify-ble=verify-ble-20261112 --session dry-ble=dry4a-20261112-1557 --session dry-ble=dry4b-20261112-1611 `
     --session verify-prot=verify-prot-20261112 --session dry-prot=dry-prot-20261112 `
     --session nonce=nonce-20261112-before-prot --session nonce=nonce-20261112-after-dry-prot `
     --session prot=P1-20261113-1154 --session prot=P2-20261113-1219 `
     --session ewait=A1-20261119-1500 --session ewait=A2-20261119-1518 `
     --session alls=B1-20261119-1537 --session alls=B2-20261119-1557 `
     --summary $W10\summary-prot-20261113-1242 --summary $W10\summary-ewait-20261119-1531 --summary $W10\summary-alls-20261119-1614 `
     --analysis $W10\analysis-20261119 `
     --raw "D:\HUST\Trung\1211\log1\4a.tar.gz=..." --raw "D:\HUST\Trung\1211\log2\4b.tar.gz=..." `
     --raw "D:\HUST\Trung\1211\Trunggui\gui_sv1_cache.tar.gz=..." --raw "D:\HUST\Trung\1911\logA1\A1_lan_2.tar.gz=..." `
     --raw "D:\HUST\Trung\1911\logA2\A2.tar.gz=..." --raw "D:\HUST\Trung\1911\logB1\B1.tar.gz=..." --raw "D:\HUST\Trung\1911\logB2\B2.tar.gz=..." `
     --out results\week10\device
   ```

10. Test host: `test_week10_host.py`, `test_week10_ble_host.py`, `test_week10_prot_host.py`, `test_week10_figures_host.py`.
