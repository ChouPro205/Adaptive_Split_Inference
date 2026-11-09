# Báo cáo SV1 tuần 9 — E_dev(s) cho mọi s và khóa bàn đo PPK2

Nghiệm thu kỹ thuật phía Device tuần 9: **8/8 tiêu chí PASS** ([phụ lục A](#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-w9-d1w9-d12)).
`E_dev(s)` đo cho **mọi s = 0…10, n = 50 mỗi s, ba phiên** trên cùng bàn đo; CI95 mỗi s ≤ 5,25 % giá trị trung bình
(ngưỡng 10 %), thời gian marker lệch DWT ≤ 0,16 %. Phần B với KV260 ở s = 2 (TC7) PASS 19/19 ở hai phiên.

Phát hiện quan trọng nhất cho bài báo: trên bàn đo VBUS 5 V, dòng lúc tính có **hai mức** do bộ DC/DC REG0 của
nRF52840 ở tải nhẹ, và tỉ lệ thời gian ở mức cao trôi giữa các phiên. Vì vậy số thô giữa hai phiên cùng ngày lệch tới
7,5 % (B4) và 9,6 % (B5). Khi ngoại suy về lúc không có mức cao ("E lõi"), các phiên khớp nhau trong 0,75 % (s ≥ 2).
Cách dùng số cho bài báo được chốt ở §3.3 (W9-D9…W9-D12).

| Mục | Giá trị |
|---|---|
| Source firmware | `device/week9/` commit `2e1daff93ad1` (`dev`, `dev-usb`), `a4126242ae1d` (biến thể REG0/REG1 LDO), cây sạch; phần B dùng image `energy` sạch tuần 8 `5d070cbaddf0-week8-energy-fast-20261026T055457Z` |
| Build | NCS 3.4.0, `nrf52840dongle/nrf52840`; `dev-usb` (console CDC: VERIFY, TDEV, SESSION khô), `dev` (tự chạy phiên PPK2, không BT, không USB, không log) |
| Bộ mẫu, thứ tự | 50 mẫu đầu của bộ W8-D3 (`set_sha256 7cfecbb2…1639`); một phiên = 50 vòng × 11 s = 550 chu kỳ, mỗi vòng một hoán vị s (seed 20261103), `plan_sha256 5b1fcfe8…4a9f` nhúng vào image và tự kiểm lúc boot (W9-D3, W9-D4) |
| Bàn đo | PPK2 Source Meter 5000 mV → breakout VBUS của dongle; marker D0 P0.13, D1 P0.15, D2 P0.17, D3 P0.20, D4 P0.22; 100 kS/s; nhiệt độ phòng 26,5 °C (29/10), 25–26 °C (09/11); KV260 cạnh PPK2 (ảnh trong manifest) |
| Peer phần B | KV260, service G2 tuần 8 commit `948297f9`, model `68c5f86b…`, tail DPU, tự quét/nối, LE Set PHY 2M + Read PHY mỗi lần nối, không pair, không mã hóa, queue/MQTT tắt |
| Phiên lab | 29/10 (B2 TC2, B4 ba phiên + hai phiên thử bộ ổn áp), 09/11 (B5 bốn phiên, PASS phiên 1 và 4); raw ngoài Git tại `D:\HUST\ASI_week9\`, `D:\HUST\Trung\0911\`, SHA-256 trong [manifest](../results/week9/device/manifest.json) |
| Công cụ | `generate_week9_plan.py`, `generate_week9_refs.py`, `build_week9.ps1`, `check_week9_build.py`, `flash_week9.ps1`, `week9_lab.py`, `check_week9.py`, `week9_ppk2.py`, `week9_figures.py`, `publish_week9_results.py`; ppk2-api 0.9.2 |

## 1. Kết quả theo tiêu chí

| # | Tiêu chí | Kết quả | Bằng chứng |
|---:|---|---|---|
| 1 | Build sạch, plan và bộ mẫu đúng | **PASS** bốn image từ cây sạch: `dev` 24/24, `dev-usb` 23/23, `dev-reg0-ldo` 26/26, `dev-reg1-ldo` 26/26 check tĩnh. Image `dev` không có BT/USB/printk/LED và không tham chiếu NVS nonce; kết thúc ở `0x95db4`, dưới vùng NVS `0xDC000` | [build_check/](../results/week9/device/build_check/), [build_resources.csv](../results/week9/device/build_resources.csv) |
| 2 | VERIFY + DWT trên dongle | **PASS** 10/10: 550/550 cặp q/scale trùng tham chiếu host C; digest plan trên dongle = anchor; TDEV head so BENCH FAST tuần 7: s1 +0,079 %, s2…s10 ≤ 0,006 %, s0 +0,35 µs (qua nhờ sàn 0,5 µs). SESSION khô 550 chu kỳ đúng plan (6/6, cả gap 0 và gap 1000 ms) | [tc2_verify.json](../results/week9/device/tc2_verify.json), [tc2_session_dry_gap1000.json](../results/week9/device/tc2_session_dry_gap1000.json) |
| 3 | Bàn đo khóa | **PASS**: I_idle cửa sổ 29 s trong image = 24,90 / 24,83 / 24,82 µA (−2,0 / −2,3 / −2,3 % so 25,42 µA tuần 2); phần B 24,61 / 24,54 µA. Ảnh đầu/cuối, nhiệt độ đầu/cuối trong note từng phiên; tự kiểm D0–D4 PASS mọi phiên | `b4_s*_check_session_recheck.json`, `*_note-*.json` |
| 4 | Phiên E_dev | **PASS** 17/17 cả ba phiên (bản recheck): 0 mất mẫu, đúng 550 chu kỳ hợp lệ, độ rộng HEAD từng chu kỳ khớp DWT của (n, s) theo plan, D1–D3 LOW, tổng pha so cả chu kỳ < 3 %, giữa chu kỳ không có radio. Bản gốc FAIL 1 check do ngắt tràn RTC (§6.1), giữ lại | [b4_s1_check_session_recheck.json](../results/week9/device/b4_s1_check_session_recheck.json), `b4_s*_check_session_FAIL_original.json` |
| 5 | `energy_dev.json` | **PASS** mọi s, mọi phiên: CI95/mean ≤ 5,25 % (s0), ≤ 1,4 % khi s ≥ 1; t_dev marker so DWT ≤ 0,16 % | `b4_s*_energy_dev.json`, [table_iii_e_dev.csv](../results/week9/device/analysis/table_iii_e_dev.csv) |
| 6 | Lặp lại cùng ngày | **PASS** (báo cáo): phiên 1 → 2 lệch +1,8…+5,3 % (s ≥ 1), s0 +13 %; phiên 2 → 3 ≤ 2,35 %. E lõi lệch ≤ 0,75 % (s ≥ 2) giữa ba phiên (§3) | [b4_compare_s1_s2.json](../results/week9/device/b4_compare_s1_s2.json), [b4_compare_s2_s3.json](../results/week9/device/b4_compare_s2_s3.json) |
| 7 | Phần B KV260, s = 2 | **PASS** 19/19 ở phiên 1 và phiên 4: 200 chu kỳ hợp lệ theo cặp W8-D1, log KV260 200/200 OK, nhãn = KV260 offline 100/100 mỗi ρ, PHY 2M, một kết nối, ghép chu kỳ hai mốc, sau phiên về idle và tắt radio | [b5_kv260_p1_check_kv260.json](../results/week9/device/b5_kv260_p1_check_kv260.json), [b5_kv260_p4_check_kv260.json](../results/week9/device/b5_kv260_p4_check_kv260.json) |
| 8 | Hồ sơ | **PASS** báo cáo này, [results/week9/device](../results/week9/device/README.md) (139 file + manifest, 52 mục raw ngoài Git có SHA-256), test host PASS (§6.5). TC7 tuần 8 (revision registry r2) đã đóng 27/10: Trung xác nhận, ghi ở [registry r2](../contracts/sv1_sv2_week8_registry_revision_r2.json) | [manifest.json](../results/week9/device/manifest.json) |

## 2. E_dev(s) cho mọi s (cột E_dev của Bảng III)

`E_dev` = năng lượng ở đầu vào 5 V trong lúc chỉ D0 (HEAD = head(s) + lượng tử INT8/FP16) ở mức cao, radio tắt
(W9-D1, W9-D2). Số gộp là trung bình 150 chu kỳ của ba phiên board. "Khoảng phiên" là trung bình nhỏ nhất và lớn nhất
trong ba phiên. "E lõi" là E khi tỉ lệ khối 1 ms ở mức cao bằng 0 (§3). Thời gian theo DWT (TDEV, IRQ khóa).

| s | Payload (B) | t_dev (ms) | Lượng tử (% t_dev) | **E_dev gộp (µJ)** | CI95 ± | Khoảng phiên (µJ) | Lệch phiên (%) | E lõi (µJ) | Lệch lõi (%) | Tỉ lệ cao (%), phiên 1/2/3 |
|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|
| 0 | 362 | 0,55 | 99 | **9,8** | 0,2 | 9,0–10,3 | 13,2 | 6,0 | 3,8 | 43,8 / 61,3 / 63,7 |
| 1 | 5792 | 11,69 | 70 | **169,1** | 1,2 | 165,8–171,0 | 3,1 | 140,3 | 4,3 | 30,4 / 33,1 / 34,0 |
| 2 | 2912 | 37,10 | 11 | **558,5** | 7,1 | 535,1–576,8 | 7,5 | 483,3 | 0,75 | 14,9 / 22,4 / 26,4 |
| 3 | 5824 | 71,16 | 12 | **1021,0** | 9,9 | 981,4–1051,5 | 6,9 | 923,4 | 0,38 | 8,8 / 15,5 / 18,8 |
| 4 | 2944 | 126,17 | 3 | **1787,1** | 11,2 | 1737,5–1830,6 | 5,2 | 1659,6 | 0,43 | 6,5 / 10,9 / 14,2 |
| 5 | 4416 | 176,70 | 4 | **2443,5** | 9,6 | 2403,4–2479,4 | 3,1 | 2320,6 | 0,46 | 5,3 / 7,6 / 9,6 |
| 6 | 2256 | 246,24 | 1 | **3407,3** | 15,3 | 3344,3–3444,9 | 3,0 | 3250,2 | 0,09 | 4,3 / 7,8 / 8,3 |
| 7 | 3008 | 302,23 | 1 | **4174,7** | 15,4 | 4105,1–4222,4 | 2,8 | 3987,1 | 0,37 | 4,2 / 7,3 / 8,0 |
| 8 | 1536 | 373,46 | 1 | **5131,5** | 16,1 | 5047,6–5174,2 | 2,5 | 4934,3 | 0,22 | 3,3 / 6,7 / 6,6 |
| 9 | 96 | 377,55 | 0 | **5254,2** | 22,5 | 5159,7–5306,7 | 2,8 | 4999,3 | 0,30 | 4,6 / 8,5 / 8,2 |
| 10 | 15 | 377,40 | 0 | **5238,4** | 19,2 | 5145,3–5309,0 | 3,1 | 4991,1 | 0,13 | 4,4 / 7,3 / 8,6 |

Nhận xét:

- `E_dev` tăng gần tỉ lệ với `t_dev`: dòng trung bình lúc tính khoảng 2,7–3,0 mA ở 5 V với mọi s ≥ 2. s8, s9, s10
  gần như bằng nhau (head chỉ thêm lớp rất nhỏ sau s8) nên s9, s10 không rẻ hơn s8 về tính toán. Chúng chỉ khác ở
  payload (96 B, 15 B so với 1536 B).
- Ở s0 (0,55 ms) và s1 (11,7 ms), phần lượng tử chiếm 99 % và 70 % thời gian HEAD
  ([fig_quant_share](../results/week9/device/figures/fig_quant_share.png)). Chi phí lượng tử 5792 giá trị ở s1 lớn hơn
  cả head; tối ưu lượng tử sẽ có lợi nhất cho các điểm cắt nông.
- Thời gian marker lệch DWT ≤ 0,16 % mọi s ([fig_t_dev_marker_vs_dwt](../results/week9/device/figures/fig_t_dev_marker_vs_dwt.png)),
  nên `t_dev` trong mô hình lấy theo DWT là đủ chính xác.
- Hình: [E_dev(s) + payload](../results/week9/device/figures/fig_e_dev_vs_split.png) (bản nháp cho Hình 4 / Bảng III),
  [một chu kỳ ở s0, s2, s10](../results/week9/device/figures/fig_cycle_waveforms.png),
  [toàn phiên](../results/week9/device/figures/fig_session_overview.png),
  [histogram idle so tuần 2](../results/week9/device/figures/fig_idle_histogram.png).

## 3. Dòng hai mức do bộ ổn áp REG0

### 3.1. Hiện tượng

Dòng HEAD theo từng khối 1 ms nhảy giữa hai mức khoảng 2,6 mA và 4,4–4,8 mA, ngẫu nhiên. PPK2 ở range 2 suốt HEAD
nên đây không phải đổi range của PPK2. Mức thấp không đổi giữa các phiên (2640 / 2645 µA). Chỉ **tỉ lệ khối ở mức cao**
thay đổi: tăng dần trong phiên và giữa các phiên (s2: 14,9 → 22,4 → 26,4 % qua ba phiên B4; B5: 24 % → 28 % → 40 % ở
phiên 1 → 2 → 4). Tỉ lệ này giải thích R² = 0,89–0,99 phương sai `E_dev` trong từng s
([fig_reg0_two_level](../results/week9/device/figures/fig_reg0_two_level.png), phải).

### 3.2. Thí nghiệm bộ ổn áp (29/10)

Hai biến thể image chỉ đổi chế độ bộ ổn áp trong devicetree (overlay `device/week9/overlay-reg{0,1}-ldo.overlay`):

| Cấu hình | Dòng HEAD | CI95 E_dev (s ≥ 1) | E_dev so board |
|---|---|---|---|
| Board: REG0 DC/DC + REG1 DC/DC | hai mức 2,6 / 4,4–4,8 mA | 0,23–2,36 % | 1 |
| REG0 LDO, REG1 DC/DC | một mức ~3,5 mA (97 % khối trong 3,4–3,6 mA) | 0,03–0,13 % | ×1,12 (s1) … ×1,30 (s ≥ 5) |
| REG0 DC/DC, REG1 LDO | một mức 6,5–7,0 mA | 0,04–0,23 % | ×2,3 |

Hai mức chỉ xuất hiện khi **cả hai** DC/DC cùng bật. Tắt DC/DC của REG0, hoặc tăng tải cho REG0 bằng cách để REG1
chạy LDO, đều làm hai mức biến mất. Kết luận: nguồn gây hai mức là **REG0 DC/DC ở tải nhẹ**; chưa loại trừ hẳn tương
tác giữa hai bộ DC/DC. Cấu hình board vẫn là cấu hình tốn ít năng lượng nhất, nên số chính giữ cấu hình board.

Phạm vi áp dụng: REG0 nằm trên đường VDDH (USB VBUS 5 V hoặc pin Li-ion một cell 2,5–5,5 V). Thiết bị đeo dùng
Li-ion qua VDDH cũng đi qua REG0, nên bàn đo VBUS đại diện cho trường hợp này; chỉ khác hiệu suất REG0 ở 3,7 V so
với 5 V. Pin cúc áo cấp thẳng VDD thì bỏ qua REG0 và không có hiện tượng này.

### 3.3. Cách dùng số cho bài báo (chốt 09/11, trước khi có dữ liệu tuần 13)

| # | Quyết định |
|---|---|
| W9-D9 | Giá trị cho Bảng III, LUT và mô phỏng = **trung bình gộp** các phiên hợp lệ (năng lượng thiết bị thực sự tốn trung bình trên đường VBUS → REG0). Độ bất định = **khoảng các trung bình phiên**; CI95 theo chu kỳ báo kèm nhưng không dùng làm sai số chính (nó bỏ qua lệch giữa phiên) |
| W9-D10 | Báo **E lõi** (hệ số chặn của E = a + b × tỉ lệ cao, theo từng s, từng phiên) và **tỉ lệ cao trung bình** cạnh mọi số gộp `E_dev`, `E_prot`: đây là thước đo tái lập và cận dưới (REG0 luôn ở mức thấp) |
| W9-D11 | Luật so khác ngày của tuần 13 (D0/D4), khai trước khi đo: giữ tiêu chí thô < 10 % mỗi s của kế hoạch, **thêm** E lõi lệch ≤ 2 % (s ≥ 2) / ≤ 8 % (s ≤ 1). Thô trượt mà lõi đạt = do tỉ lệ chế độ REG0, ghi rõ trong báo cáo; lõi trượt = có thay đổi thật (firmware, mô hình, bàn đo), phải tìm nguyên nhân trước D5 |
| W9-D12 | Mô phỏng E7: chạy cơ sở với số gộp, chạy độ nhạy với trung bình phiên nhỏ nhất và lớn nhất |

Lý do chọn số gộp (không chọn E lõi) làm số chính: E lõi là trường hợp REG0 không bao giờ nhảy lên mức cao, trong khi
thiết bị thật trên đường VDDH vẫn nhảy. Ngưỡng 2 % / 8 % lấy từ lệch lõi lớn nhất đã thấy cùng ngày (0,75 % / 4,3 %)
nhân khoảng hai lần.

## 4. Phần B: KV260 ở s = 2 (TC7)

Bốn phiên ngày 09/11, cùng image `energy` tuần 8, không nạp lại giữa các phiên. Phiên 1 và 4 PASS (dùng làm số).
Phiên 2 chỉ FAIL `no_data_loss` (mất 48 mẫu giữa hai chu kỳ), dùng làm đối chứng. Phiên 3 hỏng do laptop chạy pin (§6.3).

Liên kết (btmon của KV260, cả ba phiên có log): LE PHY Update → **2M/2M**, Connection Update → **interval 15 ms,
latency 0, timeout 4 s** (dongle xin 15 ms như W8-D10). Interval ước lượng từ trace PPK2 cũng là 15,0 ms.

Năng lượng mỗi chu kỳ (µJ, gross 5 V; gộp = 200 chu kỳ của phiên 1 + 4 cho mỗi ρ):

| Pha | P1 gộp | P1 phiên 1 / 4 | P0 gộp | P0 phiên 1 / 4 | Lệch phiên | E lõi (P1 / P0) |
|---|---:|---|---:|---|---:|---|
| E_dev | 624,3 | 594,5 / 654,2 | 624,7 | 598,0 / 651,5 | 8,6–9,6 % | 509,7 / 511,3 |
| E_prot | 22,7 | 21,1 / 24,3 | 0 | 0 | 14,3 % | 14,9 / – |
| E_tx | 603,2 | 601,6 / 604,8 | 600,6 | 596,8 / 604,4 | 0,5–1,3 % | |
| E_wait | 265,5 | 263,9 / 267,1 | 259,0 | 258,0 / 260,0 | 0,8–1,2 % | |
| E_cycle | 1522,0 | 1487,3 / 1556,7 | 1490,6 | 1459,1 / 1522,1 | 4,2–4,6 % | |

Thời gian (phiên 1, P1 / P0): t_dev 37,77 ms, t_prot 1,36 ms, t_tx 28,2 / 28,9 ms, t_wait 88,2 / 88,0 ms (tail DPU
+ gửi kết quả), t_cycle 155,7 / 154,9 ms. Hiệu theo cặp P1 − P0 (CI95): E_prot +21,1 ± 0,9 µJ (phiên 1),
+24,3 ± 0,9 µJ (phiên 4); E_cycle +28,3 ± 4,8 và +34,6 ± 14,1 µJ; E_dev −3,5 ± 4,7 và +2,7 ± 13,1 µJ (không khác 0).
Hình: [fig_kv260_phases](../results/week9/device/figures/fig_kv260_phases.png).

Phần radio (E_tx, E_wait) lặp lại trong 1,3 %. Phần tính (E_dev, E_prot) lệch nhiều vì REG0 (§3), nhưng E lõi của ba
phiên (kể cả phiên 2) khớp trong 0,75 % (E_dev) và 3,4 % (E_prot).

**Công suất giữ kết nối (P_conn)**, đo trong khoảng nghỉ 980 ms giữa hai chu kỳ (bỏ 10 ms mỗi đầu, 199 khoảng mỗi phiên):

| Peer, interval | P_conn gross (mW) | P_conn net (mW, trừ I_idle) |
|---|---:|---:|
| KV260, 15 ms (phiên 1 / 2 / 4) | 1,578 / 1,585 / 1,586 | 1,455 / 1,462 / 1,464 |
| Laptop tuần 8 (B5 26/10), 45 ms | 0,617 | 0,491 |

P_conn lặp lại trong 0,6 % giữa các phiên và tỉ lệ gần nghịch với interval. Con số 0,62 mW dùng ở các ước lượng trước
là của laptop ở **45 ms**, không phải 15 ms; ở cấu hình chốt cho thí nghiệm (KV260, 15 ms) P_conn cao gấp khoảng 2,5
lần (§5).

**Radio bật so với tắt lúc tính (W9-D1), s = 2:** E lõi 509,7–511,3 µJ (radio kết nối) so với 483,3 µJ (image `dev`,
radio tắt), tức khoảng +27 µJ (+5,5 %); t_dev 37,77 ms so với 37,10 ms (+1,8 %, ngắt radio). Số thô (624 so với 558 µJ)
lẫn với tỉ lệ cao của REG0 nên không dùng để so. Phần thêm tương đương khoảng 0,7 mW trong lúc tính, nhỏ hơn P_conn
net lúc nghỉ (1,46 mW) vì CPU đã thức sẵn và HFXO đã chạy.

## 5. Ảnh hưởng tới mô hình và bài báo

1. **P_conn phụ thuộc mạnh vào interval:** 1,46 mW net ở 15 ms so với 0,49 mW ở 45 ms. Mô hình năng lượng phải dùng
   P_conn theo trạng thái kênh k (interval là một thành phần của k), và tuần 11 cần đo P_conn ở mỗi trạng thái k. Với
   P_conn của cấu hình chốt, khoảng thời gian giữa hai lần suy luận mà từ đó tính hết trên thiết bị và tắt radio (s10)
   rẻ hơn s2 giảm từ khoảng 7,9 s (ước lượng cũ, P_conn của laptop 45 ms) xuống khoảng **2,6 s**. Kịch bản chính
   Δ = 0,8 s vẫn nằm dưới ngưỡng này.
2. **Số tuyệt đối của phần tính dao động theo phiên trên đường REG0** (§3): đã chốt W9-D9…D12. Hiệu theo cặp trong
   cùng phiên (E_prot, Δ(P1 − P0)) không bị ảnh hưởng. Bài báo phải nêu hiện tượng, tỉ lệ cao, E lõi và khoảng phiên ở
   phần testbed.
3. **E_dev đo với radio tắt thấp hơn khi radio kết nối** khoảng 5,5 % ở s2. Đề xuất cho mô hình:
   `E_dev,on(s) ≈ E_dev,off(s) + P_extra · t_dev(s)` với P_extra ≈ 0,7 mW. Kiểm lại ở một s sâu (s4 hoặc s5) trong
   các phiên BLE tuần 10–11 trước khi dùng cho mọi s.
4. Tuần 13 so khác ngày theo W9-D11 (khai trước).

## 6. Sự cố và cách xử lý

1. **Ngắt tràn RTC trong khoảng nghỉ (B4, 29/10).** Mỗi phiên có đúng một sự kiện > 3 mA ở 513,27 s sau khi cấp
   nguồn (hai xung 50–70 µs, đỉnh 3,1–8,7 mA). Thời điểm trùng ngắt OVERFLOW của bộ đếm RTC 24 bit mà Zephyr dùng
   (`nrf_rtc_timer.c`, mỗi 2^24 / 32768 Hz = 512 s), không phải radio (radio lặp lại mỗi 15–100 ms, mỗi lần vài ms).
   Luật TC4 sửa (commit `8417d87`): mỗi sự kiện > 3 mA ≤ 0,5 ms và tối đa ⌊T / 512 s⌋ + 1 sự kiện. Recheck ba phiên
   PASS 17/17; bản gốc FAIL giữ trong results.
2. **Phiên REG1-LDO FAIL `TC4_head_width_matches_plan`.** Một chu kỳ (165, s1) ngắn hơn DWT 0,505 %, vượt ngưỡng
   0,5 %. Ở cấu hình này mọi s nhanh hơn DWT 0,17–0,35 % (HFINT chạy nhanh hơn khi REG1 ở LDO), không phải lệch
   plan. Đây là phiên thí nghiệm, không phải số tiêu chí; giữ nguyên checker và báo cáo FAIL.
3. **Mất mẫu PPK2 khi laptop chạy pin (B5, 09/11).** Khoảng nghỉ dài nhất giữa hai lần đọc USB tăng 0,06 s → 0,12 s →
   0,28 s qua phiên 1 → 2 → 3 khi laptop chạy pin (Windows Balanced). Phiên 2 mất 48 mẫu giữa hai chu kỳ; phiên 3
   mất khoảng 190 000 mẫu từ giây thứ 2,4, làm lệch dây chuyền self-test và cửa sổ idle. Sau khi cắm sạc và chọn Best
   performance, phiên 4 có khoảng nghỉ đọc dài nhất 0,0096 s và 0 mất mẫu. **Luật lab mới:** khi capture PPK2 phải cắm
   sạc laptop, chọn Best performance, không dùng laptop hay chép file trong lúc đo. Trung không gửi log phiên 3 (trace
   không dùng được).
4. **Log Read PHY có các lần đọc 1M trước khi PHY Update xong.** Service KV260 đọc PHY nhiều lần sau khi nối: 5 lần
   đầu ra 1M, lần thứ 6 (khoảng 0,6 s sau) ra 2M, request đầu tiên đến khoảng 35 s sau đó. Importer cũ yêu cầu mọi lần
   đọc là 2M nên báo FAIL sai. Sửa (commit `8dc8ff9`): kiểm PHY theo thời gian (cùng đồng hồ `t_rx_ms`); lần đọc cuối
   trước request đầu tiên phải là 2M và từ lần đọc 2M đầu tiên trở đi không còn lần nào khác 2M. Log không có thời gian
   vẫn theo luật cũ. btmon xác nhận độc lập có LE PHY Update Complete 2M/2M. Không sửa log tay.
5. **Test host** chạy lại 09/11 trên HEAD: `test_week9_host.py` 26/26 (có B5 tuần 8 và build tuần 8),
   `test_week8_host.py` 14/14, `test_measure_energy.py` 22/22, `test_week6_host.py` 27/27,
   `contracts/i1v2_ref/test_i1v2.py` 23/23, `contracts/i2_ref/test_i2.py` 5/5.

## 7. Giới hạn và việc tiếp theo

- Một dongle, một bàn đo, một nhiệt độ (25–26,5 °C); E_dev đo với trọng số head tuần 5. Tuần 13 đo lại với trọng số
  gói A (D0–D7) và so khác ngày theo W9-D11.
- E lõi là phép ngoại suy tuyến tính theo tỉ lệ cao; mô hình hai mức chưa tách được phần năng lượng của từng lần
  chuyển mức. Ở s0, s1 tỉ lệ cao > 30 % và R² thấp hơn nên E lõi kém chính xác hơn (lệch lõi 3,8–4,3 %).
- Phần B chỉ ở s = 2 và một interval (15 ms). Tuần 10: E_prot P1 + E_wait theo kế hoạch, thêm một điểm radio bật ở
  s4 hoặc s5 để kiểm mô hình `E_dev,on` (§5.3). Tuần 11: E_tx(B) và P_conn theo từng trạng thái kênh k.
- `--prior-reserved-through` lần sau: ≥ 60657663 (block của lần boot phiên 4, 09/11).

## Phụ lục A. Tiêu chí nghiệm thu và quyết định W9-D1…W9-D12

### A.1. Tám tiêu chí (chốt 27/10)

| # | Tiêu chí | Định nghĩa đạt |
|---:|---|---|
| TC1 | Build | `dev-usb` + `dev` từ cây sạch, kiểm tĩnh PASS (image `dev` không có BT/USB/log/LED, không tham chiếu NVS nonce), header mẫu + plan khớp SHA |
| TC2 | VERIFY + DWT | 550 q/scale trùng tham chiếu host C; DWT head từng s lệch ≤ 2 % so BENCH FAST tuần 7 (sàn 0,5 µs) |
| TC3 | Bàn đo khóa | Checklist C.4 tuần 7, ảnh và nhiệt độ đầu/cuối; I_idle cửa sổ 30 s trong image lệch ≤ 10 % so 25,4 µA tuần 2 |
| TC4 | Phiên E_dev | Tự kiểm D0–D4 PASS, 0 mất mẫu, đúng 550 chu kỳ hợp lệ (50 mỗi s), thứ tự s = plan, D1–D3 LOW, khoảng nghỉ không có radio, tổng pha so cả chu kỳ < 3 % |
| TC5 | `energy_dev.json` | Mỗi s mean/std/CI95 (Student-t) của `E_dev_uJ` (gross, net), `t_dev_ms`, `bytes_payload`; CI95/mean < 10 % mọi s; t_dev marker so DWT ≤ 1 % |
| TC6 | Lặp lại cùng ngày | Phiên thứ hai cùng bàn đo; báo lệch mean từng s (tiêu chí < 10 % khác ngày thuộc tuần 13) |
| TC7 | Phần B KV260 s = 2 | 200 chu kỳ hợp lệ, log KV260 200 OK + PHY 2M, nhãn = KV260 offline 100/100 mỗi ρ, ghép chu kỳ hai mốc, sau phiên về idle; bảng pha theo ρ + Δ theo cặp |
| TC8 | Hồ sơ | Báo cáo + `results/week9/device` + manifest; PR (kèm TC7 tuần 8 đã đóng) |

### A.2. Quyết định (Châu chốt hoặc ủy quyền chốt, 27/10–09/11/2026)

| # | Quyết định |
|---|---|
| W9-D1 | `E_dev` đo ở image không bật BLE (radio tắt, không USB/console/LED, không nonce/I2): E_dev là chi phí tính. Phần radio trong lúc tính báo riêng bằng đối chứng s = 2 với phiên KV260 (§4) |
| W9-D2 | `E_dev_uJ` = năng lượng marker D0 = head(s) + lượng tử INT8/FP16; gross ở 5 V là số chính, kèm net (W7-D5), `t_dev_ms`, `bytes_payload` |
| W9-D3 | Mẫu: 50 mẫu đầu của bộ W8-D3, cùng 50 mẫu cho mọi s |
| W9-D4 | Một phiên = 50 vòng × 11 s = 550 chu kỳ, mỗi vòng một hoán vị s (seed 20261103), vòng k dùng mẫu k; chu kỳ = CTRL 200 µs → HEAD(s) → nghỉ 1 s. Thứ tự sinh ở host, nhúng vào image, checker so trace với plan |
| W9-D5 | Firmware mới `device/week9/` (fork tuần 8); hai biến thể `dev-usb` và `dev`; `dev` không gọi `bt_enable`, không đụng NVS nonce |
| W9-D6 | Tham chiếu host: shim C (`device/week9/host_test/dev_shim.c`, cùng `head_fast.c` + `quantization.c`) chạy 50 mẫu × 11 s |
| W9-D7 | Bàn đo khóa tới hết tuần 12: dongle trên breakout VBUS 5 V, D0–D4 như bảng đầu; mỗi image đo tự kiểm D0–D4 lúc boot; nạp theo cách tuần 7–8 (giữ dây marker) |
| W9-D8 | Phần B: image `energy` tuần 8 sạch, 100 cặp P1/P0, PHY 2M xác nhận bằng log Read PHY của KV260 |
| W9-D9 | Số chính = trung bình gộp các phiên hợp lệ; độ bất định = khoảng trung bình phiên (§3.3) |
| W9-D10 | Báo E lõi và tỉ lệ cao cạnh mọi số gộp E_dev, E_prot (§3.3) |
| W9-D11 | Tuần 13 so khác ngày: thô < 10 % và lõi ≤ 2 % (s ≥ 2) / ≤ 8 % (s ≤ 1), khai trước (§3.3) |
| W9-D12 | Mô phỏng E7: cơ sở = số gộp, độ nhạy = trung bình phiên nhỏ nhất/lớn nhất (§3.3) |

Sửa luật trong tuần (không đổi định nghĩa tiêu chí): TC2 thêm sàn 0,5 µs (s0 chỉ 1,9 µs head, vài chu kỳ gọi hàm đã
vượt 2 %); TC4 khoảng nghỉ cho phép ngắt tràn RTC (§6.1); TC7 kiểm PHY theo thời gian (§6.4).

### A.3. Việc còn mở của người khác

- Trung (SV2): giữ log Read PHY có `t_ms` và chạy btmon ở các phiên đo tuần 10–11 (interval và PHY thật); cho biết
  tập và số mẫu calibration lượng tử của gói A (chỉ từ DS1); khóa xmodel trước khi chạy DS2 (tuần 13).
- Kỳ Anh (SV3): không có việc phụ thuộc trực tiếp vào số tuần 9; E_dev(s) gộp và E lõi dùng được cho bảng dạng dài.

## Phụ lục B. Firmware `device/week9/`

| File | Vai trò |
|---|---|
| `main.c` | `dev-usb`: STATUS, VERIFY ALL\|<s>, TDEV ALL\|<s> (20 mẫu khởi động + 50 mẫu, IRQ khóa), ONE <n> <s>, SESSION [gap] [first] [count], MARKERS, STACK. `dev`: kiểm digest plan (sai → 10 xung CTRL 5 ms rồi dừng) → tự kiểm D0–D4 → idle 30 s → 550 chu kỳ → ngủ |
| `dev_cycle.c/.h` | Một chu kỳ CTRL → HEAD với s theo từng chu kỳ (dùng lại cho các phiên BLE nhiều s tuần 10–11) |
| `Kconfig`, `CMakeLists.txt`, `overlay-dev-usb.conf`, `overlay-dev.conf` | `WEEK9_DEV_USB` / `WEEK9_DEV`, gap 1000 ms, idle 30 s, self-test 200 ms, CTRL 200 µs; dùng `prj.conf` + `app.overlay` tuần 7 |
| `overlay-reg0-ldo.overlay`, `overlay-reg1-ldo.overlay` | Biến thể thí nghiệm bộ ổn áp (`build_week9.ps1 -Regulator`) |
| `host_test/dev_shim.c` | `head_fast.c` + `quantization.c` trên host (gcc) cho tham chiếu và test |

`week9_plan.h` sinh bởi `generate_week9_plan.py` (splitmix64 + Fisher-Yates trong `week9_common.plan_splits`, không
phụ thuộc numpy). Dùng lại nguyên vẹn: `week7/{head_fast,marker_ctrl}.c`, `src/markers.c`, `week5/quantization.c`.

## Phụ lục C. Quy trình chạy lại

Biến dùng chung (PowerShell, gốc repo):

```powershell
$py  = "device\host\.venv\Scripts\python.exe"
$W9  = "D:\HUST\ASI_week9"
$smp = "D:\HUST\ASI_week8\samples-20261023-c"
```

Trước mọi capture PPK2: **cắm sạc laptop, Power mode = Best performance**, đóng nRF Connect Power Profiler, không
dùng laptop hay chép file trong lúc đo (§6.3). PPK2 = COM8; bootloader dongle = COM6 (RESET ở cạnh dài, bấm ngang;
LED đỏ thở = bootloader).

1. Plan và tham chiếu (tất định, sinh lại ra cùng SHA):
   `$py -B device\scripts\generate_week9_plan.py --output $W9\plan-<mới>`,
   `$py -B device\scripts\generate_week9_refs.py --samples $smp --output $W9\refs-<mới>`
   (`plan_sha256 5b1fcfe8…4a9f`; anchor ghi trong `week9_common.py` và `build_week9.ps1`).
2. Build: `device\scripts\build_week9.ps1 -ReportDir $W9\build-<mới> -Variant dev-usb|dev -Samples $smp -Plan $W9\plan-20261029 [-Regulator reg0-ldo|reg1-ldo]`.
3. Nạp (dongle cắm USB laptop, RESET): `device\scripts\flash_week9.ps1 -Port <bootloader> -ReportDir <build> -ReceiptDir $W9\dfu`.
4. TC2 (`dev-usb`): `$py -B device\scripts\week9_lab.py verify --out $W9\verify-<mới> --samples $smp --refs $W9\refs-20261029`;
   SESSION khô: `$py -B device\scripts\week9_lab.py session --out <dir> --samples $smp --refs $W9\refs-20261029 --gap-ms 1000`.
5. Phiên E_dev (`dev`, dongle trên breakout VBUS 5 V, giữ dây D0–D4 + GND):
   `$py -B device\scripts\week9_ppk2.py probe --port COM8`, rồi
   `$py -B device\scripts\week9_ppk2.py session-dev --port COM8 --out $W9\B4-<mới> --temp-c <t> --image $W9\build-20261029-clean-dev --receipt <receipt> --samples $smp --refs $W9\refs-20261029 --dwt-verify $W9\verify-20261029-1223`
   (~13 phút), `week9_ppk2.py note --out <dir> --temp-end-c <t> --photo <ảnh>`, phiên thứ hai vào thư mục mới,
   `week9_ppk2.py compare --a <phiên 1> --b <phiên 2> --output <json>`. FAIL thì giữ thư mục, chạy thư mục mới; sửa
   checker thì `week9_ppk2.py recheck --out <dir>`. Tự kiểm D0–D4 FAIL = dừng, sửa dây, chụp ảnh.
6. Phần B (image `energy` tuần 8): service KV260 đã quét ASI-SV1 (Set PHY 2M + Read PHY có `t_ms`, btmon nếu được,
   queue/MQTT tắt) **trước** khi bật nguồn:
   `$py -B device\scripts\week9_ppk2.py session-kv260 --port COM8 --out $W9\B5-<mới> --temp-c <t> --image D:\HUST\ASI_week8\build-20261026-clean-energy --receipt $W9\dfu\dfu-20261029-144215-energy-fast.json --samples $smp --prior-reserved-through 60657663 --note "<khoảng cách, commit service>"`
   (420 s), rồi nhận log của KV260 và
   `$py -B device\scripts\week9_ppk2.py import-kv260 --out <dir> --kv260-log <requests.jsonl> --phy-log <phy.log> --edge-reference D:\HUST\ASI_week8\from-trung-20261026-g2\review\offline_second\predictions.jsonl`.
   Lệch định dạng thì sửa importer, không sửa log tay; mỗi phiên KV260 ghi log sang file mới.
7. Phân tích và hình:
   `$py -B device\scripts\week9_figures.py tables --lab $W9 --week8-b5 D:\HUST\ASI_week8\B5-official-20261026-1328 --kv260-logs D:\HUST\Trung\0911 --out $W9\analysis-<mới>`
   (~8 phút, đọc raw của 9 phiên), rồi `week9_figures.py figures --tables <thư mục đó>`.
8. Công bố: `$py -B device\scripts\publish_week9_results.py --lab $W9 --analysis $W9\analysis-20261109 --kv260-logs D:\HUST\Trung\0911 --out results\week9\device`.
9. Test host: `$py -B device\scripts\test_week9_host.py --samples $smp --plan $W9\plan-20261029 --refs $W9\refs-20261029 --week8-build D:\HUST\ASI_week8\build-20261026-clean-energy --week8-b5 D:\HUST\ASI_week8\B5-official-20261026-1328`.
