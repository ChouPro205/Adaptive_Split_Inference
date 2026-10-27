# Báo cáo SV1 tuần 8 — G2 end-to-end Dongle → BLE → KV260 với 100 mẫu

Nghiệm thu kỹ thuật phía Device tuần 8: **8/9 tiêu chí PASS, TC7 (revision registry) chờ SV2 xác nhận**
([phụ lục A](#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-w8-d1w8-d13)). **G2 đạt với KV260**: 100 mẫu × (P1, P0) =
200 chu kỳ, 0 lỗi, nhãn đọc trên dongle khớp KV260 offline 100/100 cho mỗi ρ và logits trùng từng bit.
Tiêu chí G2 W8-D8 so với KV260 offline vì tail chạy trên DPU INT8. So với tham chiếu FP32 W8-D4, KV260 khớp
87/100 mỗi ρ; phần lệch do lượng tử tail DPU, không do đường truyền (§3).

| Mục | Giá trị |
|---|---|
| Source firmware | commit `5d070cbaddf0`, cây sạch (`dirty=false`) cho cả hai image |
| Build | NCS 3.4.0, `nrf52840dongle/nrf52840`; `energy-usb-fast` (console CDC) và `energy-fast` (tự chạy phiên PPK2, không USB) |
| Bộ mẫu (W8-D3) | 100 mẫu từ tập test tuần 5, `set_sha256 = 7cfecbb2…1639`, nhúng vào image dạng `week8_inputs.h` (100 × 360 FP32) |
| Cấu hình chạy | s = 2, mỗi mẫu một cặp P1/P0, thứ tự trong cặp đảo luân phiên (W8-D1); key bench `key_id 65537` |
| Peer G2 | KV260 (BlueZ central, service thường trú của SV2, tail DPU), cách dongle khoảng 50 cm |
| Phiên lab | 23/10 (TC2 dirty, TC3), 26/10 (PPK2 TC6, G2 KV260), 27/10 (kiểm liên kết PHY/DLE, TC2 trên image sạch); raw ngoài Git tại `D:\HUST\ASI_week8\`, SHA-256 trong [manifest](../results/week8/device/manifest.json) |
| Công cụ | `generate_week8_samples.py`, `build_week8.ps1`, `check_week8_build.py`, `flash_week8.ps1`, `week8_lab.py`, `check_week8.py`, `week8_edge.py`, `week8_tail_worker.py`, `week8_ppk2.py`, `publish_week8_results.py` |

## 1. Kết quả theo tiêu chí

| # | Tiêu chí | Kết quả | Bằng chứng |
|---:|---|---|---|
| 1 | Build sạch, bộ mẫu đúng | **PASS** cả hai image từ `5d070cb`, cây sạch; kiểm tĩnh 33/33 (`energy-usb`) và 34/34 (`energy`); `build_week8.ps1` kiểm manifest + SHA của 3 file bộ mẫu trước khi chép `week8_inputs.h` vào build; image giữ chuỗi `WEEK8_SET_SHA256=` | [build_check/](../results/week8/device/build_check/), [build_resources.csv](../results/week8/device/build_resources.csv) |
| 2 | Head + lượng tử 100 mẫu khớp host | **PASS** 8/8 trên image sạch (27/10): 100 VQ có q/scale/ID trùng `samples.csv`, 200 VREQ (P0 + P1 key PUBLIC_TEST) trùng Python reference, set SHA trong banner và `VERIFY END`. Image dirty ngày 23/10 cũng 8/8 | [verify_tc2_clean.json](../results/week8/device/verify_tc2_clean.json), [verify_tc2_dirty_20261023.json](../results/week8/device/verify_tc2_dirty_20261023.json) |
| 3 | G2 dự phòng: laptop chạy tail thật | **PASS** 18/18 (23/10): 200/200 chu kỳ OK, nhãn trên dongle = W8-D4 100/100 cho P1 và cho P0, logits dongle = edge = `reference_s2.npz` trùng bit, q/scale edge (P1 sau unprotect) = mẫu 200/200 | [tc3_laptop_tail_200.json](../results/week8/device/tc3_laptop_tail_200.json), [tc3_laptop_edge_summary.json](../results/week8/device/tc3_laptop_edge_summary.json) |
| 4 | KV260 kết nối, thông số liên kết, P1 bit-exact | **PASS**. MTU 247; DLE 251/251 B; KV260 nối ở interval 45 ms (timeout 420 ms), dongle xin 15 ms → 15 ms, timeout 4 s; PHY mặc định **1M**, lên **2M** sau lệnh HCI LE Set PHY phía KV260 (§2). q và scale KV260 nhận được sau unprotect trùng mẫu 200/200 | [link_events.csv](../results/week8/device/link_events.csv), [link_phy_status_conn3.log.txt](../results/week8/device/link_phy_status_conn3.log.txt), [kv260_g2_pairs100.json](../results/week8/device/kv260_g2_pairs100.json) |
| 5 | **G2** với KV260 | **PASS** 18/18 (26/10 15:19): 200/200 chu kỳ, 0 lỗi/timeout/invalid, 0 ghi Flash trong chu kỳ; nhãn trên dongle = KV260 offline 100/100 cho mỗi ρ, logits dongle = log KV260 = offline trùng bit; sequence P1 60647432…60647531 tăng ngặt trong block của lần boot. Trước đó ONE P0, ONE P1, 5 cặp đều PASS | [kv260_g2_pairs100.json](../results/week8/device/kv260_g2_pairs100.json), [cycles_kv260_g2_pairs100.csv](../results/week8/device/cycles_kv260_g2_pairs100.csv), `kv260_g2_one0P0/one0P1/pairs5.json` |
| 6 | Image energy không quảng bá lại sau phiên | **PASS** 20/20 (26/10 13:28, image sạch): 58,7 s sau chu kỳ cuối dòng trung bình 24,96 µA so với I_idle 25,15 µA (lệch 0,74 %), max 35,5 µA, 0 mẫu > 3 mA, edge chỉ thấy 1 kết nối; 200/200 chu kỳ, edge nhãn 100/100 mỗi ρ | [ppk2_B5_session.json](../results/week8/device/ppk2_B5_session.json) |
| 7 | Revision registry `runtime.nonce_persistence_reboot` | **CHỜ SV2**: đã soạn revision `mitdb-week5-i2-registry-v1-r2` (SV1 xác nhận); có hiệu lực khi Trung xác nhận cùng mã revision trong PR này (§5) | [sv1_sv2_week8_registry_revision_r2.json](../contracts/sv1_sv2_week8_registry_revision_r2.json) |
| 8 | Chốt cấu hình bàn đo tuần 9 | **PASS**: peer KV260, interval 15 ms, MTU 247, DLE 251, PHY 2M (kèm điều kiện), image `5d070cbaddf0-week8-energy-fast-20261026T055457Z`, khoảng cách và ảnh (W8-D9…D12, phụ lục A.2) | phụ lục A.2, ảnh `photos/bench-kv260-20261026.png` (ngoài Git, SHA trong manifest) |
| 9 | Hồ sơ | **PASS** báo cáo này, [results/week8/device](../results/week8/device/README.md) (49 file + manifest, 32 mục raw ngoài Git có SHA-256), test host PASS (§6) | [manifest.json](../results/week8/device/manifest.json) |

## 2. Liên kết BLE với KV260 (TC4, TC8)

Thông số đọc từ log của chính dongle (`EVT`/`LINK` trong `cdc.log`), cùng một liên kết với KV260 nên không cần
trace phía KV260 để đọc MTU, DLE và interval:

| Thông số | Giá trị | Nguồn |
|---|---|---|
| ATT MTU | 247 (KV260 đề nghị 517) | `EVT ATT_MTU tx=517 rx=247` |
| Data length | 251 / 251 B | `EVT DATA_LEN` (27/10, cả ba lần nối) |
| Connection interval | KV260 nối ở 36 × 1,25 = 45 ms, timeout 420 ms; dongle gửi `CONNPARAM 12 12` → 15 ms, latency 0, timeout 4 s (W8-D10) | `EVT CONNECTED`, `EVT CONN_PARAM` |
| PHY | **1M mặc định**; G2 ngày 26/10 chạy ở 1M | `LINK phy_tx=0` (không có thủ tục PHY update) |
| PHY sau LE Set PHY | **2M / 2M** | KV260: LE Read PHY = 2M/2M sau HCI `0x08 0x0032`; dongle: `LINK phy_tx=2 phy_rx=2` |

Kiểm PHY ngày 27/10 (13:51–14:12, dongle cắm lại nên boot mới):

1. Lượt 1, 1M: ONE 0 P0 OK; bắt được đủ chuỗi `CONNECTED → ATT_MTU 247 → DATA_LEN 251 → CONN_PARAM 15 ms`.
2. Lượt 2: KV260 ngắt, `btmgmt phy LE1MTX LE1MRX LE2MTX LE2MRX`, nối lại. `Selected phys` đã có LE2M nhưng BlueZ
   **không** tự chuyển: 5 cặp chạy ở 1M (`phy_tx=0` suốt). Thư mục raw lượt này tên `…supp2-2M…`, thực tế là 1M.
3. KV260 gửi HCI LE Set PHY (all_phys 0, tx/rx = 2M) trên handle 16; Read PHY trả 2M/2M; dongle `STATUS` (không
   chạy chu kỳ, không tốn nonce) báo `phy_tx=2 phy_rx=2`. Dòng `EVT PHY` không có trong log vì CDC đang đóng lúc đổi.
4. Lượt 4: service restart, kết nối thứ 3, Set PHY lại → 2M/2M ở cả hai đầu → 5 cặp ở 2M, 10/10 OK, log KV260 khớp.

Cả ba lượt import-peer PASS (15/18/18 check), log request KV260 khớp log gốc của service 21/21 dòng, 0 cache hit.

**Kết luận cho tuần 9 (W8-D11):** dùng 2M. BlueZ trên KV260 không tự nâng PHY nên **mỗi lần nối** phải gửi Set PHY
rồi Read PHY; phía dongle phải thấy `phy_tx=2 phy_rx=2` trước khi đo. Image `energy` không có console nên trong phiên
PPK2 chỉ xác nhận PHY được bằng log Read PHY của KV260.

Laptop Windows (TC3, B5) tự lên 2M nhưng tự chọn interval 15 ms hoặc 45 ms tùy lần (B5 12:25 là 15 ms, B5 13:28 là
45 ms), nên không dùng làm peer đo.

## 3. Nhãn: KV260 so với FP32 và nhãn thật

| So sánh (100 mẫu, mỗi ρ) | Khớp |
|---|---:|
| Dongle ↔ KV260 offline (tiêu chí G2, W8-D8) | **100/100**, logits trùng bit |
| KV260 offline lần 1 ↔ lần 2 | 100/100 trùng bit |
| KV260 ↔ tham chiếu FP32/INT8-FP16 W8-D4 | 87/100 |
| Nhãn thật: FP32 / KV260 | 58/100 / 67/100 |

Theo lớp tham chiếu W8-D4: N 54/55, S 8/11, V 25/25, F 0/1, Q 0/8. Đầu vào tail của KV260 (z = q·scale) đúng: tail
FP32 trên cùng z cho đúng logits tham chiếu. Logits KV260 là bội của 0,125 (output INT8 fix_point 3): 4 mẫu hòa
top-2, 3 trong số đó lật nhãn S → N (mẫu 52, 66, 91). Lớp Q bị hạ logit trung bình −3,3 một cách có hệ thống,
nên mẫu 57, 73, 80 lật dù biên FP32 1,7–1,9. Đây là lượng tử tail DPU (PTQ), không do truyền hay ghép.

Bộ mẫu dồn vào các lớp mô hình dễ sai (chọn theo dự đoán FP32 Q/S/F), nên 87/100 và 58/100 không đại diện cho
tập test. Đã báo SV2/SV3/GV phần lệch lớp Q; không tune và không bỏ mẫu. Số đại diện cần KV260 chạy offline toàn
tập 8544 (SV2, tùy chọn).

Bộ mẫu ([samples.csv](../results/week8/device/samples/samples.csv)): đủ 16 mẫu S/F/Q thật + mọi mẫu FP32 đoán F (1)
và Q (8) + 11 mẫu đoán S + 30 V + 34 N (rút ngẫu nhiên, seed 20261027). Nhãn tham chiếu N 55, S 11, V 25, F 1, Q 8.
Loại 6 mẫu có nhãn FP32 ≠ INT8 ở s = 2 ([excluded.csv](../results/week8/device/samples/excluded.csv)); nhãn host cho
6 mẫu này cũng khớp W8-D4. q đường C (head trên host bằng chính `head_fast.c`) trùng đường PyTorch 99/100; mẫu test
85 khác q nhưng trùng scale và nhãn. Tham chiếu dùng đường C vì đó là cái dongle tính.

## 4. Thời gian

| | Laptop tail (TC3) | KV260 (G2) |
|---|---:|---:|
| head (DWT, ms) | 38,0 | 38,0 |
| lượng tử / protect P1 / encode (DWT, ms) | 4,1 / 1,30 / 3,4 | 4,1 / 1,30 / 3,4 |
| tail phía edge (ms) | 0,7–1,4 (FP32 CPU laptop) | 45,5–47,8 (DPU + plugin CPU, `steady_clock`) |
| edge từ nhận xong request tới gửi response (ms) | — | 69–83 |
| khoảng cách hai chu kỳ trên đồng hồ host (trung vị, ms) | 1094 | 1203 |

**`tx_us` và `wait_us` của firmware không phải độ trễ.** Chúng đo bằng DWT `CYCCNT`, mà bộ đếm này dừng khi CPU ngủ
(WFI trong `k_sem_take` lúc chờ notify/response), nên chỉ là thời gian CPU thức. Với KV260, `wait_us` chỉ 2,9–3,6 ms
dù tail đã mất 45,7 ms; khoảng cách chu kỳ trên đồng hồ host dài hơn TC3 khoảng 109 ms, khớp thời gian xử lý của
KV260 cộng BLE. Thời gian thực của TX và WAIT lấy từ marker D2/D3 trên PPK2. Năng lượng không bị ảnh hưởng vì PPK2
tích phân dòng theo marker. Cùng lý do, `tx_us` không dùng so 1M với 2M được (10,9 ms ở cả hai).

**Đính chính báo cáo tuần 7 §2.2–2.3:** tuần 7 giải thích TX/WAIT marker (32,9 / 13,3 ms) dài hơn DWT dry run
(11,0 / 1,3 ms) là do dongle ở bàn đo xa anten hơn. Hai số không cùng đại lượng: DWT bỏ qua thời gian CPU ngủ,
marker thì không. So sánh đó không chứng minh `E_tx`/`E_wait` phụ thuộc vị trí; tuần 9 vẫn cố định hình học bàn đo
(W8-D12) để không phải giả định điều ngược lại. Báo cáo tuần 7 giữ nguyên.

## 5. Registry: `runtime.nonce_persistence_reboot` (TC7, W8-D13)

Revision mới [`mitdb-week5-i2-registry-v1-r2`](../contracts/sv1_sv2_week8_registry_revision_r2.json) là file delta
trên [registry v2](../contracts/sv3_week5_approved_registry_v2.json) (SHA-256 `79392b6d…ed24`, không sửa). Nó chỉ đổi
`runtime.nonce_persistence_reboot` thành `ACCEPTED`, phạm vi là bộ đếm nonce của dongle (sender 131073, key 65537).

- Bằng chứng §8 mục 1–6 của [nonce provisioning](../contracts/i2_nonce_provisioning_v1.md) là hồ sơ tuần 6:
  110 reset mềm, 12 lần rút nguồn thật, hook lỗi ghi/thiếu record, 2 lần DFU giữ sentinel.
- Phía edge, tuần 8 bổ sung: KV260 unprotect 116 request P1 qua 2 lần boot (106 ngày 26/10, 10 ngày 27/10),
  sequence luôn tăng và lần boot sau nằm trên block của lần boot trước.
- Giữ nguyên `provisioning = NOT_ACCEPTED` (chỉ có key bench), `p1_transmission_authorized = false`.
- Giới hạn đã ghi trong file: KV260 giữ high-water sequence trong bộ nhớ, mất khi restart service, nên edge
  không từ chối được sequence cũ sau restart. SV2 sửa trước khi dùng ngoài bench.
- Có hiệu lực khi Trung bình luận trong PR tuần 8 xác nhận cùng mã revision (`device_revision = edge_revision`).

Key bench 65537 đã đi qua app chat thay vì USB khi gửi gói cho KV260. Chỉ Châu và Trung có, chỉ dùng với dữ liệu bench
MIT-BIH; hệ thống thật hoặc đánh giá bảo mật phải cấp key mới theo nonce provisioning v1.

## 6. Sự cố và cách xử lý

1. **B5 lần 1 (26/10 12:25, image dirty): 19/20, `one_cycle_per_request` FAIL.** Max lệch 47 ms > 30 ms ở 6/199
   khoảng chu kỳ. Windows giao notify trễ, độ lệch tương quan 0,80 với `t_wait` của dongle; chu kỳ cách nhau
   ≥ 1080 ms nên việc ghép 1:1 không mơ hồ. Sửa `week8_ppk2.match_cycles`: dùng mốc tốt hơn trong hai mốc (cuối TX ↔
   edge nhận xong; cuối WAIT ↔ edge gửi xong) < 30 ms, mọi lệch < ½ khoảng chu kỳ; ca âm (lệch 1 chu kỳ, thiếu
   request, đảo ρ, +60 ms) đều FAIL. Kiểm lại PASS 20/20; phiên chính thức trên image sạch PASS ngay lần gốc. Bản
   FAIL giữ ở [ppk2_B5_attempt1_FAIL.json](../results/week8/device/ppk2_B5_attempt1_FAIL.json).
2. **Thử nối KV260 lúc 16:38 ngày 26/10 hết 600 s, KV260 không nối, 0 request.** Bỏ, không tính; `cdc.log` giữ trong
   `raw_outside_git`. Lần boot đó tốn 1 block nonce.
3. **Trace HCI.** btsnoop ngày 26/10 của SV2 không chứa sự kiện kết nối G2; ngày 27/10 SV2 không tìm thấy btsnoop.
   MTU/DLE/interval lấy từ log dongle, PHY từ Read PHY (KV260) + `LINK` (dongle). Đồng hồ KV260 không đồng bộ với
   laptop nên giờ trong log KV260 chỉ dùng để xếp thứ tự trong cùng KV260.
4. **Service KV260 đổi giữa 26/10 và 27/10** (SHA `79a1da1b…` → `a424bc90…`): chỉ thêm `--hold-after-count` giữ kết
   nối sau đủ số request; đường suy luận không đổi. Cả 3 lượt ngày 27/10 dùng cùng SHA.
5. **Ngày G2 chạy ở 1M** vì chưa biết BlueZ không tự nâng PHY (§2). Không ảnh hưởng G2 (tiêu chí là đúng dữ liệu);
   ảnh hưởng `E_tx` nên tuần 9 chốt 2M.

Firmware không đổi sau các sửa trên (chỉ sửa script host).

Test host chạy lại 27/10/2026 trên HEAD: `test_week8_host.py --samples D:\HUST\ASI_week8\samples-20261023-c` 14/14,
`test_measure_energy.py` 22/22, `test_week6_host.py` 27/27, `contracts/i1v2_ref/test_i1v2.py` 23/23,
`contracts/i2_ref/test_i2.py` 5/5. `test_week7_host.py` trên HEAD chỉ 9/16: 7 test còn lại lỗi `FileNotFoundError`
vì PR #37 đã chuyển `results/week5/*.json` sang `results/week5/device/`, còn script tuần 7 bị khóa nên vẫn trỏ đường
dẫn cũ. Trên worktree tạm ở commit `7bbbc23` (trước khi chuyển, chép đúng byte các file tuần 5 đã nghiệm thu):
16/16. Script tuần 8 dùng `week7_common.py` cho reference I1/I2 nhưng không gọi phần đọc các file tuần 5 đó
(test tuần 8 và mọi checker tuần 8 chạy PASS trên HEAD).

## 7. Giới hạn và việc tiếp theo

- Năng lượng tuần 8 (B5, peer laptop, PHY 2M, interval 45 ms) chỉ dùng kiểm hành vi image, **không đưa vào Table II**.
  Đo chính thức với KV260 từ tuần 9.
- `week8_ppk2.py session` hiện tự chạy edge laptop: tuần 9 cần chế độ peer ngoài (KV260), kèm kiểm log Read PHY 2M
  của KV260 trước mỗi phiên, và mỗi phiên KV260 xuất log request cùng định dạng để `check_week8.py` đối chiếu.
- Lệch nhãn do DPU (lớp Q) thuộc SV2/SV3; bộ mẫu không đại diện cho accuracy.
- Edge chưa lưu bền high-water sequence (§5).

## Phụ lục A. Tiêu chí nghiệm thu và quyết định W8-D1…W8-D13

### A.1. Chín tiêu chí

| # | Tiêu chí | Định nghĩa đạt |
|---:|---|---|
| TC1 | Build | `energy-usb` + `energy` từ cây sạch, kiểm tĩnh PASS; `week8_inputs.h` khớp SHA bộ mẫu W8-D3 |
| TC2 | Head + lượng tử | 100 mẫu ở s = 2 trên dongle khớp tham chiếu host (cùng tiêu chí VERIFY tuần 5–7) |
| TC3 | G2 dự phòng | Laptop chạy tail thật: 200 chu kỳ, 0 lỗi, nhãn trên dongle khớp W8-D4 100/100 cho P1 và P0 |
| TC4 | KV260 | Kết nối được; ghi MTU/interval/PHY/DLE thực; P1 unprotect bit-exact (q KV260 = q dongle) |
| TC5 | G2 | 200 chu kỳ với KV260, 0 lỗi/timeout, nhãn 100/100 mỗi ρ theo W8-D8 |
| TC6 | Sau phiên | PPK2, image energy: dòng trung bình ≥ 20 s về idle, không quảng bá lại (W8-D2) |
| TC7 | Registry | Revision `runtime.nonce_persistence_reboot` được Châu + Trung xác nhận |
| TC8 | Bàn đo tuần 9 | Chốt peer, interval thực, PHY, image + SHA, khoảng cách, ảnh |
| TC9 | Hồ sơ | Báo cáo + `results/week8/device` + manifest; commit + PR |

### A.2. Quyết định (Châu chốt hoặc giao Claude chốt theo ủy quyền, 22–27/10/2026)

| # | Quyết định |
|---|---|
| W8-D1 | Từ tuần 9 đo luân phiên P1/P0 theo cặp (cùng mẫu, cặp k chẵn P1→P0, k lẻ P0→P1), Δ theo cặp + CI95; `E_prot` lấy từ marker D1 là số chính, Δ(P1−P0) là số phụ. Lý do: `E_dev` P0 > P1 ≈ 23 µJ ở tuần 7 |
| W8-D2 | Sau phiên đo, thiết bị tự ngắt thì không quảng bá lại tới khi reboot (`week8/ble_link.c`, cờ `adv_closed`); central tự ngắt thì vẫn quảng bá lại. Kiểm trên dongle 22/10, PPK2 ở TC6 |
| W8-D3 | 100 mẫu từ tập test tuần 5: đủ 16 S/F/Q thật + mọi mẫu đoán F/Q + 11 đoán S + 30 V + 34 N (seed 20261027); loại 6 mẫu FP32 ≠ INT8 |
| W8-D4 | Nhãn tham chiếu = `prediction_int8_fp16` ở s = 2 (`ml/results/week5/predictions.csv`); DPU lệch thì đối chiếu KV260 offline để tách lỗi lượng tử với lỗi truyền |
| W8-D5 | s = 2; mỗi mẫu P1 và P0 → 200 chu kỳ/phiên; key bench 65537 chép sang KV260, chỉ để unprotect |
| W8-D6 | Firmware `week8/main.c` + `week8/g2_cycle.c` (fork tuần 7), in logits + nhãn mỗi chu kỳ; image energy giữ phiên tự động → tuần 9 dùng nguyên |
| W8-D7 | Mốc dự phòng 29/10: KV260 chưa nhận tensor thì G2 bằng laptop chạy tail thật (TC3). Không phải kích hoạt |
| W8-D8 | G2 với KV260 = nhãn trên dongle khớp KV260 offline 100/100 mỗi ρ + logits trùng bit; khớp FP32 và nhãn thật báo riêng |
| W8-D9 | Peer tuần 9 = KV260 |
| W8-D10 | Interval 15 ms (dongle xin 12 × 1,25 ms, KV260 chấp nhận), MTU 247 |
| W8-D11 | PHY tuần 9 = 2M: mỗi kết nối KV260 gửi Set PHY + Read PHY, ghi log; dongle phải báo `phy_tx=2` trước khi đo; phiên Set PHY lỗi không tính; không trộn 1M/2M trong một bộ số; firmware không sửa |
| W8-D12 | Bàn đo: KV260 cách dongle khoảng 50 cm như ảnh `photos/bench-kv260-20261026.png`; image `energy` sạch `5d070cbaddf0-…-20261026T055457Z` |
| W8-D13 | Registry: revision mới (không sửa registry v2), `nonce_persistence_reboot = ACCEPTED` cho bộ đếm nonce dongle; giữ `p1_transmission_authorized = false`, `provisioning = NOT_ACCEPTED` |

### A.3. Việc còn mở của người khác

- Trung (SV2): xác nhận revision `mitdb-week5-i2-registry-v1-r2` trong PR này (TC7); đưa Set PHY + Read PHY vào
  service/script khởi động cho tuần 9; push code sau F6 lên `dev/edge-sv2` và gửi commit SHA; lưu bền high-water
  sequence; tùy chọn chạy offline toàn tập 8544 để có accuracy DPU theo lớp.
- SV3 + GV: nắm lệch lớp Q do lượng tử tail DPU (§3).
- Châu: Q2 dongle dự phòng (rủi ro cho tuần 9–12), Q4 lịch nhận `controller.c`.

## Phụ lục B. Firmware `device/week8/`

| File | Vai trò |
|---|---|
| `main.c` | `energy-usb`: VERIFY (100 VQ + 200 VREQ, key PUBLIC_TEST), `ONE <n> P1\|P0`, `PAIRS <first> <count>`, SESSION, NONCE, CONNPARAM, STATUS. `energy`: phiên tự động như tuần 7 (block nonce → tự kiểm D0–D4 → idle 30 s → BLE → connected idle 30 s → 100 cặp → ngắt, không quảng bá lại) |
| `g2_cycle.c/.h` | Một chu kỳ CTRL → HEAD → PROT → TX → WAIT trên mẫu n; in `logits=` (bit FP32 hex), `label=` (argmax đầu tiên, NaN → 255), `ref=`, `match=` |
| `g2_plan.h` | Thứ tự cặp W8-D1: cặp k = mẫu k mod 100 |
| `ble_link.c` | Bản sao `week6/ble_link.c` + cờ `adv_closed` (W8-D2) |
| `Kconfig`, `CMakeLists.txt` | `WEEK8_PAIRS` (mặc định 100), dùng lại Kconfig/conf/overlay tuần 7 |
| `host_test/head_shim.c`, `host_test/g2_shim.c` | Chạy `head_fast.c` + lượng tử tuần 5 và luật nhãn/thứ tự cặp trên host (gcc) để sinh tham chiếu và test |

Dùng lại nguyên vẹn qua đường dẫn: `week7/{head_fast,marker_ctrl}.c` (`head_fast.c` include `src/week4_head.c`),
`src/markers.c`, `week5/quantization.c`, `week6/{frag,nonce_store,nonce_nvs,packets,sha256}.c`,
`contracts/i1v2_ref/i1v2_codec.c`, `contracts/i2_ref/i2_reference.c`; Kconfig/conf/overlay của `week7/`.

## Phụ lục C. Quy trình chạy lại

Biến dùng chung (PowerShell, gốc repo):

```powershell
$py  = "device\host\.venv\Scripts\python.exe"
$W   = "D:\HUST\ASI_week8"
$smp = "$W\samples-20261023-c"
$key = "D:\HUST\ASI_week6\secrets\bench_key_65537.bin"   # không in, không commit
```

1. Bộ mẫu (≈ 70 s, `ml\.venv`): `ml\.venv\Scripts\python.exe -B device\scripts\generate_week8_samples.py --output $W\samples-<mới>`.
   Chạy lại phải ra `set_sha256 = 7cfecbb2…1639`.
2. Build: `device\scripts\build_week8.ps1 -ReportDir $W\build-<mới> -Variant energy-usb|energy -Samples $smp`.
3. Nạp: RESET (nút ở cạnh dài, bấm ngang; LED đỏ thở = bootloader) →
   `device\scripts\flash_week8.ps1 -Port <bootloader> -ReportDir <build> -ReceiptDir $W\dfu`. Mỗi lần boot tốn một block
   1024 sequence; không bao giờ `PROV ERASE`.
4. TC2: `$py -B device\scripts\week8_lab.py verify --out $W\verify-<mới> --samples $smp`.
5. TC3 (laptop tail, cần `ml\.venv`): `$py -B device\scripts\week8_lab.py cycles --out $W\cycles-<mới> --samples $smp --pairs 100 --key-file $key --prior-reserved-through <N>`.
6. G2 với KV260: mở console **trước** khi KV260 nối để bắt `EVT CONNECTED/DATA_LEN/PHY`:
   `$py -B device\scripts\week8_lab.py cycles --peer external --peer-name KV260 --out $W\kv260-<mới> --samples $smp --prior-reserved-through <N> [--one 0 P0 | --first 0 --pairs 100 --key-file $key]`
   (chờ `LINK ready=1` tối đa 600 s). Lab tiếp tục ngay khi thấy kết nối, nên muốn đổi PHY thì KV260 phải ngắt trước
   khi mở lượt mới. Sau đó nhận log request KV260 rồi
   `$py -B device\scripts\week8_lab.py import-peer --out $W\kv260-<…> --peer-log <log> --edge-reference <predictions.jsonl offline đã kiểm>`.
   Lỗi định dạng thì sửa importer hoặc nhờ SV2 xuất lại, không sửa log tay.
7. TC6 (PPK2, image energy; dongle trên breakout VBUS 5 V, D0–D4):
   `$py -B device\scripts\week8_ppk2.py probe`, rồi
   `$py -B device\scripts\week8_ppk2.py session --port <PPK2> --out $W\B5-<mới> --temp-c <t> --image $W\build-20261026-clean-energy --receipt <receipt> --samples $smp --key-file $key --prior-reserved-through <N> --note "<khoảng cách>"`,
   sau đó `week8_ppk2.py note --out <dir> --temp-end-c <t> --photo <ảnh>`. FAIL thì chạy thư mục mới, giữ bản FAIL;
   sửa checker thì `week8_ppk2.py recheck --out <dir>`.
8. Đọc PHY không chạy chu kỳ: script `link_phy_status_tool.py.txt` trong results (mở CDC, gửi `STATUS`).
9. Công bố: `$py -B device\scripts\publish_week8_results.py --lab $W --out results\week8\device`.

`--prior-reserved-through` lần sau: ≥ 60651520 (block của lần boot 27/10).
