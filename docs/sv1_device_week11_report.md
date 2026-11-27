# Báo cáo SV1 tuần 11 — chuẩn bị lab trạng thái kênh BLE tuần 12, định nghĩa S0c, mô hình E_tx

> **BẢN NHÁP 27/11/2026, chưa nghiệm thu.** Đã có: §1 (plan lab tuần 12, W11-D6), §2 (luật phân tích
> W11-D7…D14), §3 (TC5, mô hình E_tx từ raw tuần 10), phụ lục B (cách chạy). Chưa có: VERIFY trên dongle,
> TC2/TC3, kết quả lab.
> Các số trong §1.4 là ước lượng, không phải số đo.

Tuần 11 không có phiên PPK2 (W11-D1). Lab trạng thái kênh làm ở tuần 12 với image `link` của
`device/week11/`. Mọi luật phân tích trong báo cáo này được commit và push trước phiên đo đầu tiên. Nếu sửa
luật sau khi đã thấy dữ liệu thì ghi lại ở §2, như mục 6 của báo cáo tuần 10.

## 1. Plan lab tuần 12 (W11-D6, chốt 26/11)

### 1.1 Trạng thái kênh

OFAT quanh trạng thái gốc 2M / 15 ms / L 0 / 251 B / 0 dBm (W11-D3). Supervision timeout 4 s ở mọi trạng thái
(W7-D7). Châu chốt 14 trạng thái ngày 26/11:

| # | Tên | PHY | k (ms) | L | Độ dài gói (B) | TX (dBm) | Dùng cho |
|---|-----|-----|--------|---|----------------|----------|----------|
| 0 | base | 2M | 15 | 0 | 251 | 0 | gốc = bàn đo tuần 10 |
| 1 | k7.5 | 2M | 7,5 | 0 | 251 | 0 | trục k |
| 2 | k30 | 2M | 30 | 0 | 251 | 0 | trục k |
| 3 | k50 | 2M | 50 | 0 | 251 | 0 | trục k |
| 4 | k100 | 2M | 100 | 0 | 251 | 0 | trục k |
| 5 | L2 | 2M | 15 | 2 | 251 | 0 | trục L |
| 6 | L4 | 2M | 15 | 4 | 251 | 0 | trục L |
| 7 | L9 | 2M | 15 | 9 | 251 | 0 | trục L |
| 8 | 1M | 1M | 15 | 0 | 251 | 0 | mức β (1M × 251) |
| 9 | len27 | 2M | 15 | 0 | 27 | 0 | mức β (2M × 27) |
| 10 | tx-8 | 2M | 15 | 0 | 251 | −8 | công suất phát |
| 11 | coded-k30 | Coded S8 | 30 | 0 | 251 | 0 | cổng K, mức β Coded |
| 12 | coded-k30-len27 | Coded S8 | 30 | 0 | 27 | 0 | cổng K, mức β Coded |
| 13 | 1M-k30 | 1M | 30 | 0 | 251 | 0 | đối chứng của Coded ở cùng k |

Khối Coded dùng k 30 ms vì một gói 251 B ở S8 dài khoảng 17,6 ms, không vừa interval 15 ms. Nếu central
(adapter KV260) không có LE Coded thì dongle nhận lệnh từ chối. Khi đó hai khối Coded tự bị loại theo W11-D8,
phiên vẫn hợp lệ, và bảng báo "trạng thái không có với central này". Mục 1M × 27 B của bốn mức β (bản 2 §6)
được thay bằng 2M × 27 (len27) và 1M × 251. Chưa đo tổ hợp 1M × 27.

### 1.2 Các op trong một khối

Mỗi khối gồm:

1. STATE: dongle xin tham số, chờ central cấp, sau đó nghỉ 2 s.
2. IDLE 15 s: đo P_conn đầu khối.
3. Các op chính, thứ tự hoán vị.
4. IDLE 15 s: đo P_conn cuối khối.

Op chính của mọi khối:

- ECHO chế độ **ack** (chế độ chính): 12 cỡ khung × 6 lần. Cỡ khung là độ dài khung I1 v2 (W11-D2): 64, 104,
  112, 128, 130, 233, 256, 436, 512, 1024, 2048, 4096 B.
  - 7 cỡ của bảng thầy: 64…4096.
  - 104/130: S1 cố định 20/46 B.
  - 112: S0c.
  - 233: S0 Rice đủ mẫu.
  - 436: s0 thô.
- Khối có L > 0: mỗi cỡ chạy hai biến thể. Một là latency bật suốt. Hai là latency tắt trong WAIT
  (`sdc_hci_cmd_vs_peripheral_latency_mode_set`), bật lại sau WAIT.

Chỉ khối base có thêm:

- ECHO chế độ **full**: 12 cỡ × 3 lần, để đối chiếu với tuần 9–10 và tách năng lượng nhận E_rx(B).
- S0C: 25 mẫu W8-D3 (0…24) × {1, 100} lần encode mỗi xung D0.

Cuối phiên có khối kết nối lại: STATE base, rồi 8 lần RECONNECT, rồi IDLE 15 s.

Thứ tự khối là hoán vị ngẫu nhiên với seed 20261126 + phiên. Khối base luôn đứng đầu, để phiên bắt đầu giống
tuần 10. Thứ tự op trong khối hoán vị bằng cùng dòng số ngẫu nhiên đó.

### 1.3 Hai phiên

Mỗi trạng thái được đo ở ≥ 2 phiên (W10-D6). Mỗi phiên một image `link` riêng (plan biên dịch vào firmware,
firmware tự kiểm SHA-256). Image `link` không dùng NONCE, nên không tốn block.

| Phiên | SHA-256 plan (bảng trạng thái + mục) | Số mục | Thứ tự khối |
|-------|--------------------------------------|--------|-------------|
| 0 | `4054816b8bb75268eaf7387eef862e3627947023c8166ad6093b4c12252f79c6` | 1362 | base, L4, coded-k30-len27, L9, k50, 1M-k30, len27, k30, tx-8, L2, 1M, coded-k30, k7.5, k100, (kết nối lại) |
| 1 | `862808fbf8e3a0bbc92075144bcc0aadb0136b1f62d99f0727fb5ef640f4d6b3` | 1362 | base, 1M-k30, tx-8, coded-k30, k100, k30, L9, len27, k50, L4, coded-k30-len27, k7.5, L2, 1M, (kết nối lại) |

Mỗi phiên có 15 STATE, 29 IDLE, 1260 ECHO, 50 S0C và 8 RECONNECT.

### 1.4 Thời lượng (ước lượng, không phải luật)

`week11_analysis.estimate_session` ước lượng thời lượng từ thời gian phát sóng của gói (1M 8 µs/B, 2M 4 µs/B,
Coded S8 376 µs + 64 µs/B, T_IFS 150 µs). Các giả định:

- Mỗi notify 236 B dữ liệu; một notify là 251 octet LL, cắt thành ⌈251 / độ dài gói⌉ PDU.
- Số PDU mỗi connection event:
  - mô hình "nhanh": tối đa 6 PDU (tuần 10 đo ~11,6 µs/B ở 2M / 15 ms, tức khoảng 5 PDU);
  - mô hình "chậm": 1 PDU.
- Câu trả lời ack đến sau 2 event (× (L + 1) khi latency bật).
- Thời gian thủ tục: STATE 1,5 s + 2 s nghỉ; RECONNECT 9 s (timer cập nhật tham số 5 s của kết nối mới).
- Phần boot: self-test, 30 s idle radio tắt, kết nối, 5 s ổn định, 30 s idle có kết nối. Sau phiên: 60 s.

| Mô hình | Plan (phút) | Cả phiên (phút) |
|---------|-------------|-----------------|
| nhanh | 18,0 | 20,1 |
| chậm | 20,7 | 22,9 |

IDLE chiếm khoảng 7,3 phút, ECHO 8,4–11,1 phút. Hai phiên cộng thời gian nạp image ≈ 1 giờ 15 phút, nằm trong
ngân sách ≤ 2 × 45 phút của W11-D3. Thời gian capture mặc định là 1800 s. `week11_ppk2.py session` từ chối nếu
`--seconds` nhỏ hơn ước lượng chậm. Sau buổi chạy thử cùng KV260 (H4, `week11_lab.py session`), đặt `--seconds`
= thời gian chạy thử + 120 s, giống cách làm ở tuần 10 (chạy thử 4b). Mỗi phiên 1800 s là 180 M mẫu, khoảng
1,8 GB RAM khi phân tích (máy có 16 GB).

## 2. Luật phân tích (W11-D7…D14)

Mã nguồn: `device/scripts/week11_analysis.py`, có docstring đầy đủ. Hằng số khóa ở đầu file. Năng lượng là thô
(gross) ở đầu vào 5 V (W9-D9), trừ khi tên ghi `net` hoặc `marg`.

- **W11-D7 Tách op.** Đọc op theo thứ tự plan.
  - Op k bắt đầu ở cạnh lên CTRL (D4) và kết thúc ở cạnh lên CTRL của op k + 1. Op cuối là IDLE, kết thúc ở
    CTRL + a ms.
  - Xung CTRL trong 20 ms sau cạnh xuống D1 của một STATE là chữ ký từ chối, không phải op. Đúng 5 xung rộng
    1 ± 0,3 ms thì là "bị từ chối". Không có xung thì là "được cấp". Số xung khác hoặc độ rộng khác thì là lỗi.
  - Mỗi mẫu tính vào pha có marker duy nhất đang bật (W7-D11). Pha cần có: STATE ctrl+link, IDLE ctrl, ECHO
    ctrl+tx+wait (đúng thứ tự), S0C ctrl+dev, RECONNECT ctrl+link. Thiếu pha, lặp pha, pha lạ hay chồng pha là
    lỗi.
  - Timeout: WAIT ≥ 4980 ms, RECONNECT ≥ 29 980 ms.
  - |E_op − Σ pha| / E_op < 3 % trên phần hoạt động.
  - Mười xung CTRL 5 ms trước self-test nghĩa là plan hỏng, không có phiên.
- **W11-D8 Khối hợp lệ** khi đủ ba điều kiện:
  - STATE được cấp, không lỗi.
  - Cả hai IDLE qua kiểm interval: khoảng cách trung vị giữa các event radio (> 1 mA, gộp trong 2 ms) bằng
    k·(L + 1) ± max(0,5 ms; 3 %). Đây là bằng chứng vật lý cho k và L, vì image `link` không có console.
  - Không quá 2 % op còn lại có lỗi.

  Op của khối không hợp lệ không vào bảng nào. Khối bị từ chối không làm phiên FAIL, nhưng khối base và khối kết
  nối lại phải hợp lệ. PHY, độ dài gói và công suất phát không có marker: PHY và độ dài gói kiểm ở bước import
  (W11-D14). Công suất phát chỉ có bằng chứng là dongle không gửi chữ ký từ chối, tức controller chọn đúng
  −8 dBm; phía central không thấy được.
- **W11-D9 P_conn(trạng thái)** = công suất trung bình trong cửa sổ IDLE [CTRL + 1 s, CTRL kế − 10 ms].
  - Mỗi khối và mỗi phiên có 2 cửa sổ.
  - Trôi = |cuối − đầu| / trung bình, cảnh báo khi > 5 %.
  - Net = thô − P_idle,off (dòng idle tuần 2 × 5 V).
- **W11-D10 ECHO (sửa 27/11 sau TC5, Châu duyệt; chưa có dữ liệu tuần 12):** E_tx (D2), t_tx, E_wait (D3),
  t_wait, E_op thô.
  - marg = thô − P_conn(khối, phiên) × t: giá gửi cộng thêm trên giá giữ kết nối.
  - Lý do sửa: TC5 (§3) cho thấy D2 tắt khi gói cuối vào bộ đệm. Event dữ liệu cuối (~100 µJ ở 2M) rơi vào D3,
    nên D2 không phải giá gửi.
  - Burst: dùng `week11_etx_tc5.burst` (luật TC5), từ cạnh lên D2 tới cạnh xuống D3, lưới anchor theo interval k
    của trạng thái.
    - Ngưỡng event dữ liệu = max(1,2 ms; trung vị độ dài event rỗng trong IDLE của khối + 0,3 ms). Ở Coded event
      rỗng dài hơn nên ngưỡng tự tăng.
    - n_ev_tx là số event dữ liệu. E_burst và t_burst tính từ cạnh lên D2 tới hết event dữ liệu cuối.
    - Op không tìm được burst thì ghi burst_error. Op vẫn hợp lệ, chỉ thiếu số burst, và số lỗi được báo theo ô.
  - Mỗi ô (trạng thái, B, cờ) cần ≥ 5 op hợp lệ ở mỗi phiên, thiếu thì ô bị bỏ.
  - Mỗi trạng thái, chỉ dùng chế độ ack:
    - (i) **Chính:** fit E_tx,full = E_burst = α + β·B trên trung bình 7 cỡ của thầy (tiêu chí R² ≥ 0,98) và trên
      mọi op ack của 12 cỡ.
    - (ii) β' của luật hòa vốn = độ dốc của E_op,marg theo B, tức toàn bộ op trên giá giữ kết nối. Event cuối và
      ack 72 B cố định đều nằm trong, và phần ack triệt tiêu trong độ dốc.
    - (iii) n_ev theo B.
    - (iv) **Phụ:** các fit E_tx (D2) và E_tx,marg như tuần 10, để so sánh.
  - E_wait ở chế độ ack: báo độ dốc theo B. Burst của op full có thể lẫn vào khung được echo về nên không dùng.
  - L > 0: so latency bật với latency tắt trong WAIT, hiệu trung bình t_wait và E_wait, CI95 Welch.
  - Khối base: E_rx(B) = E_wait full − E_wait ack (cùng phiên, cùng B), fit theo B.
- **W11-D11 S0C:** giá một lần encode = (E_D0(×100) − E_D0(×1)) / 99 theo từng mẫu; chi phí gọi hàm và cạnh
  marker triệt tiêu nhau.
  - Tương tự cho t.
  - marg = − P_conn(base) × t.
  - Lõi (mức REG0) tính bằng `core_fit` trên các op ×100.
  - Báo kèm số ×1 làm giá một lần gọi.
- **W11-D12 RECONNECT:** t_link và E_link của D1, tính từ lúc dongle ngắt tới khi đã kết nối lại, MTU, đăng ký
  notify và trạng thái base. marg = E_link − P_conn(base) × t_link.
- **W11-D13 Gộp:** trung bình mọi giá trị hợp lệ của các phiên hợp lệ, kèm trung bình từng phiên và khoảng lệch
  giữa phiên (W9-D9, W11-D4). Số chính của E_tx và P_conn là thô; S0C báo thô + lõi.
- **W11-D14 Log KV260 (import):**
  - Mỗi mục ECHO của plan đúng một bản ghi echo, đúng thứ tự: độ dài, chế độ, request_id +1 mỗi ECHO.
  - TX end trên trace so với t_rx_ms, sau khi trừ trung vị, lệch < 30 ms.
  - Mỗi khối không bị từ chối: conn_update / phy_update / data_len cuối cùng trước IDLE đầu khối phải bằng trạng
    thái của khối.
  - Số kết nối = 1 + số RECONNECT.
  - t_edge = t_tx_done − t_rx.

  Dạng log (JSONL) đã ghi trong `week11_analysis.normalize_echo_records` / `check_link_events`. Dạng này chưa
  thống nhất với Trung, phải chốt ở H4. Nếu đổi thì sửa hàm chuẩn hóa trước lab và commit lại.

Phiên PASS khi qua mọi kiểm trace sau, và sau import qua thêm W11-D14:

- cắm sạc laptop;
- capture PASS;
- dòng idle lúc boot lệch ≤ 10 % so với tuần 2;
- không mất mẫu;
- plan không bị từ chối;
- self-test D0–D4;
- đủ mọi mục, đúng thứ tự, không có CTRL thừa;
- khối base hợp lệ, khối kết nối lại hợp lệ;
- mọi khối còn lại hợp lệ hoặc bị từ chối đúng chữ ký;
- lệch < 3 % ở mọi op hợp lệ;
- kênh D5–D7 thấp;
- sau phiên: về idle và tắt radio (luật tuần 10).

Kết quả cuối tuần 12 là `week11_ppk2.py summary` trên ≥ 2 phiên PASS, phải có cả plan phiên 0 và phiên 1.

**Bằng chứng host:** `test_week11_analysis_host.py` 13/13 PASS ngày 26/11. Test chạy trên trace tổng hợp, biết
trước dòng từng pha, có self-test, khối base, khối Coded bị từ chối, khối L2 và khối kết nối lại:

- tách đúng năng lượng từng pha;
- nhận đúng chữ ký từ chối;
- kiểm interval đạt ở k·(L + 1) và trượt khi event vẫn chạy ở k;
- P_conn đúng giá trị giải tích;
- fit E_tx ra đúng β với R² = 1;
- S0C, E_rx và latency bật − tắt ra đúng giá trị đã dựng;
- các đường lỗi: thiếu WAIT, chữ ký 3 xung, CTRL thừa, timeout;
- log echo và tham số được cấp đạt/trượt đúng chỗ;
- đi hết đường analyze → import → summary.

Đây không phải bằng chứng MCU. `test_week11_host.py` 5/5 và `test_week11_s0c_host.py` 6/6 vẫn PASS.

## 3. TC5 — mô hình E_tx theo connection event (từ raw B1/B2 tuần 10)

Script `device/scripts/week11_etx_tc5.py`, test `test_week11_etx_host.py` 6/6 PASS. Kết quả
`results/week11/device/tc5_etx-20261127/` (`summary.json`, `cycles_etx.csv`). Script chỉ đọc raw tuần 10:
`raw.bin` được kiểm SHA-256 theo `capture.json`, cùng `analysis/cycles.csv` và `alls_rows.csv` của B1 và B2.
Không có số đo mới.

### 3.1 Cách đếm

- Cửa sổ TX = run D2 của chu kỳ, như tuần 10. Lấy các run dòng > 1 mA từ đầu TX tới cuối chu kỳ, gộp các
  khoảng hở < 0,15 ms.
- Lưới anchor có interval 15 ms. Pha là trung vị vòng của (thời điểm bắt đầu mod 15 ms) trên các run ≥ 0,7 ms.
  Bỏ ra hai run: run CPU ở đầu TX và run nhận phản hồi kết thúc chu kỳ.
- Event dữ liệu là chuỗi anchor liên tiếp tính từ anchor đầu tiên sau đầu TX:
  - anchor nằm trong run CPU được tính là dữ liệu (payload đang được xếp hàng);
  - anchor có run > 1,2 ms được tính là dữ liệu;
  - anchor đầu tiên có run ngắn (event rỗng, ~0,85–1,0 ms ở ~3,5 mA) kết thúc chuỗi.
- n_ev là số event dữ liệu. E_burst là năng lượng thô từ đầu TX tới cuối event dữ liệu cuối.
  E_after = E_burst − E_tx(marker).
- Kết quả: 996/1000 chu kỳ s0–s9 phân tích được. 4 chu kỳ không tách được event (s7 ×2, s8, s9) nên bị bỏ.
- Soát tay 9 chu kỳ của B1 (s0 c7/c17/c31, s5 c1/c20/c28, s9 c2/c15/c27): n_ev khớp với đọc dạng sóng.
- Event dữ liệu đầy dài ~13 ms trong interval 15 ms, ở ~6,1 mA.

### 3.2 Kết quả

| s | B (byte) | n_ev TB | E_tx marker (µJ) | E_burst (µJ) | E_after (µJ) |
|---|---:|---:|---:|---:|---:|
| 9 | 96 | 1,1 | 26,5 | 127,1 | 100,5 |
| 0 | 362 | 1,1 | 29,5 | 133,9 | 104,4 |
| 8 | 1536 | 1,3 | 408,9 | 514,1 | 105,2 |
| 6 | 2256 | 2,2 | 573,7 | 673,1 | 99,3 |
| 2 | 2912 | 2,5 | 705,4 | 806,2 | 100,9 |
| 4 | 2944 | 2,3 | 699,0 | 805,8 | 106,8 |
| 7 | 3008 | 2,4 | 758,5 | 871,1 | 112,6 |
| 5 | 4416 | 4,2 | 1075,3 | 1151,9 | 76,6 |
| 1 | 5792 | 4,6 | 1365,6 | 1439,6 | 74,0 |
| 3 | 5824 | 4,8 | 1389,3 | 1486,6 | 97,3 |

Fit OLS trên 10 trung bình (sai số chuẩn trong ngoặc):

- **Marker (tuần 10):** E_tx = 4,4 (18,6) + 0,240 (0,005) µJ/B, R² 0,996. Phần dư của s0 là −61,7 µJ.
- **Burst:** E_burst = 113,2 (21,0) + 0,236 (0,006) µJ/B, R² 0,995. Phần dư của s0 là −64,8 µJ.
- **Tách E_burst thành ba phần:**
  - Event radio: E_events = 30,79 (0,06) mW × t_events − 15,5 µJ, R² 1,0000. Thời gian event
    t_events = 2,22 ms + 6,45 µs/B, R² 0,993, nên phần radio có độ dốc 0,199 µJ/B.
  - Run CPU đầu TX: E_cpu = 55,7 + 0,034 µJ/B, R² 0,82. Với payload nhiều event, run này chứa cả anchor đầu.
  - Phần còn lại (dòng < 1 mA giữa các run): 4,5 + 0,003 µJ/B.
  - Cộng ba phần: 113 µJ + 0,236 µJ/B.
- **Theo chu kỳ (n = 996):** E_burst = 53,0 (5,4) + 89,4 (3,2)·n_ev + 0,175 (0,003) µJ/B, R² 0,967.

Lặp lại giữa hai phiên: E_burst của s0 là 138,6 và 129,1 µJ, của s9 là 128,4 và 125,7 µJ, của s1 là 1454,8 và
1424,4 µJ.

### 3.3 Giải thích α và phần dư của s0

1. **α = 4,4 µJ không phải chi phí cố định vật lý.** Marker D2 tắt khi gói cuối đã vào bộ đệm của controller,
   không phải khi phát xong. Event dữ liệu cuối nằm sau marker, trong pha WAIT, trung bình 97,7 µJ mỗi chu kỳ
   (74–113 µJ theo s). Với s0 và s9, event duy nhất nằm hẳn sau marker, nên E_tx marker chỉ là chi phí CPU xếp
   hàng (27–30 µJ, ~1,3 ms). Tính đủ burst thì chi phí cố định mỗi lần gửi là ~113 µJ:
   - ~56 µJ ở run CPU;
   - ~53 µJ ở event radio, gồm phần khởi động HFXO và phần ack;
   - ~4 µJ còn lại.

   Phần năng lượng này đang nằm trong E_wait. Nó giải thích phần lớn hệ số chặn 115 µJ của E_wait (tuần 10).
2. **Độ dốc β là thời gian radio.** Trong event dữ liệu, công suất thô gần như không đổi, 30,8 mW (~6,2 mA ở
   5 V). Thời gian event tăng 6,45 µs/B, gần thời gian phát trên không ở 2M: PDU 251 B cộng IFS cộng ack là
   ~5,7 µs/B. Vậy β ≈ 30,8 mW × 6,45 µs/B = 0,199 µJ/B. Thêm 0,034 µJ/B cho CPU xếp hàng thì tổng là 0,236 µJ/B.
3. **Phần dư của s0 (−62 µJ) đến từ việc năng lượng bị lượng tử theo event.**
   - Payload vừa một event (s9 96 B, s0 362 B) tốn gần như như nhau: E_burst 127,1 và 133,9 µJ, tức +6,8 µJ cho
     +266 B (0,026 µJ/B).
   - Đường thẳng 96–5824 B có hệ số chặn bị kéo bởi các payload nhiều event (thêm ~89 µJ mỗi event), nên dự đoán
     quá cao ở đầu nhỏ. Ở s0, phần dư chia gần đều: CPU −30 µJ, event −32 µJ.
   - Khoảng 10 % chu kỳ s0/s9 có 2–3 event, với E_burst ~250–285 µJ: event lặp ở link layer, ngẫu nhiên.
4. **Tiêu chí của thầy (R² ≥ 0,98) vẫn đạt** với cả marker (0,996) lẫn burst (0,995). Fit 7 cỡ 64…4096 B đo ở
   lab tuần 12.

### 3.4 Hệ quả (đã báo Châu 27/11)

- Tổng năng lượng mỗi chu kỳ và Table III tuần 10 không đổi, vì E_tx + E_wait vẫn đúng. Chỉ có cách chia pha
  TX/WAIT theo marker là lệch ~100 µJ. Mô hình E_tx(B) trong bài phải dùng E_tx,full (burst) và định nghĩa pha
  rõ ràng.
- Với payload một event, giá theo byte gần như bằng 0. Chênh giữa S0c (~112 B), S0 Rice (~157 B) và S0 thô
  (362 B) chỉ khoảng vài µJ mỗi nhịp, không phải ~60 µJ như khi dùng 0,24 µJ/B. Lab tuần 12 đo trực tiếp các cỡ
  này (W11-D2).
- Luật W11-D10 tuần 11 cũng fit E_tx theo D2, nên gặp cùng vấn đề. Đã sửa ngày 27/11, trước khi commit luật
  (§2, W11-D10).

## 4. Việc còn mở (ghi lại khi nghiệm thu)

- TC4: build chính thức từ cây sạch, VERIFY trên dongle (USB), commit + push plan/luật trước lab.
- Coded của KV260: chờ phần 1 của Trung (H3). Nếu không có Coded thì hai khối Coded tự bị loại; phương án
  central Coded khác do Châu quyết.
- Dạng log echo / link-event với Trung (H4).
- TC2, TC3, TC6.

## Phụ lục B. Cách chạy

PowerShell tại gốc repo. Thêm gcc vào PATH bằng `$env:Path = 'C:\msys64\ucrt64\bin;' + $env:Path`; python là
`device\host\.venv\Scripts\python.exe -B`.

1. Test host:
   - `device\scripts\test_week11_host.py`
   - `device\scripts\test_week11_s0c_host.py`
   - `device\scripts\test_week11_analysis_host.py`
   - `device\scripts\test_week11_etx_host.py`
   - TC5: `device\scripts\week11_etx_tc5.py --out <thư mục mới>` (mặc định đọc `D:\HUST\ASI_week10\B1-20261119-1537`
     và `B2-20261119-1557`, ~5 phút).
2. Plan: `device\scripts\generate_week11_plan.py --output <thư mục mới>`. Ước lượng thời lượng:
   `device\scripts\week11_ppk2.py estimate --plan <plan> [--output <json mới>]`.
3. Build: `device\scripts\build_week11.ps1 -ReportDir <mới> -Variant link|link-usb -Session 0|1 -Samples
   D:\HUST\ASI_week8\samples-20261023-c -Plan <plan>`. Nạp image bằng `device\scripts\flash_week11.ps1`.
4. VERIFY (link-usb, USB laptop): `device\scripts\week11_lab.py verify --out <mới> --samples <W8-D3> --plan
   <plan> --session k`.
5. Chạy thử cùng KV260 (H4): `week11_lab.py session ...`; thử năng lực: `week11_lab.py cmd ... "STATEX 3 24 0 251
   0"`.
6. Phiên PPK2 (image `link` phiên k, đóng Power Profiler, cắm sạc laptop):
   `device\scripts\week11_ppk2.py session --port <PPK2> --out <mới> --temp-c <°C> --image <build> --receipt
   <receipt> --plan <plan> --session k [--seconds <chạy thử + 120>]`.
7. Sau phiên: `week11_ppk2.py import --out <phiên> --kv260-log <echo.jsonl> --link-events <links.jsonl>
   [--btsnoop <file>]`. Tổng hợp: `week11_ppk2.py summary --session <phiên 0> --session <phiên 1> --out <mới>`.
