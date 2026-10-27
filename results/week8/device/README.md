# SV1 tuần 8 — G2 end-to-end Dongle → BLE → KV260

Ba ngày lab: 23/10/2026 (TC2 image dirty, TC3 laptop chạy tail thật), 26/10/2026 (PPK2 TC6, G2 với KV260),
27/10/2026 (kiểm liên kết PHY/DLE với KV260, TC2 trên image sạch). Firmware commit `5d070cb`, cây sạch; s = 2,
100 mẫu W8-D3 (`set_sha256 7cfecbb2…1639`), mỗi mẫu một cặp P1/P0. **G2 PASS với KV260**: 200/200 chu kỳ, nhãn trên
dongle khớp KV260 offline 100/100 mỗi ρ, logits trùng bit. 8/9 tiêu chí PASS; TC7 (revision registry) chờ SV2 xác nhận.

- [Báo cáo cho thầy](../../../docs/sv1_device_week8_report.md)
- TC1: [build_check/](build_check/), [tài nguyên](build_resources.csv); [DFU receipt](dfu/)
- TC2: [VERIFY image sạch](verify_tc2_clean.json), [VERIFY image dirty 23/10](verify_tc2_dirty_20261023.json);
  bộ mẫu [samples/](samples/) (`samples.csv`, `excluded.csv`, `manifest.json`)
- TC3: [laptop tail 200 chu kỳ](tc3_laptop_tail_200.json), [edge laptop](tc3_laptop_edge_summary.json),
  [bảng chu kỳ](cycles_tc3_laptop.csv)
- TC5 (G2): [100 cặp với KV260](kv260_g2_pairs100.json), [log KV260 đã import](kv260_g2_pairs100_peer_summary.json),
  [bảng 200 chu kỳ](cycles_kv260_g2_pairs100.csv); bước trước: `kv260_g2_one0P0.json`, `kv260_g2_one0P1.json`, `kv260_g2_pairs5.json`
- TC4, TC8 (liên kết): [sự kiện liên kết từ dongle](link_events.csv),
  [1M](kv260_supp1_1M_one0P0.json), [5 cặp vẫn 1M sau btmgmt](kv260_supp2_1M_pairs5.json),
  [5 cặp 2M sau LE Set PHY](kv260_supp4_2M_pairs5.json), STATUS sau Set PHY
  ([kết nối 2](link_phy_status_conn2.log.txt), [kết nối 3](link_phy_status_conn3.log.txt), [công cụ](link_phy_status_tool.py.txt))
- TC6 (PPK2, image energy, peer laptop): [kiểm phiên](ppk2_B5_session.json), [phân tích pha](phase_analysis_summary.json),
  [200 chu kỳ](cycles_200.csv), [thống kê pha](phase_energy_summary.csv), [edge](ppk2_B5_edge_summary.json),
  [capture](ppk2_B5_session_capture.json), [session](ppk2_B5_session_session.json). Số năng lượng chỉ để kiểm hành vi
  image, không đưa vào Table II.
- TC7: [revision registry](../../../contracts/sv1_sv2_week8_registry_revision_r2.json)
- [manifest.json](manifest.json): SHA-256 và nguồn từng file (README này không nằm trong manifest), raw ngoài Git
  (`raw_outside_git`), báo cáo FAIL giữ lại (`kept_fail_reports`)

Phiên B5 lần 1 (image dirty, 26/10 12:25): [FAIL gốc](ppk2_B5_attempt1_FAIL.json) chỉ ở `one_cycle_per_request` do ghép
chu kỳ theo một mốc khi Windows giao notify trễ; [kiểm lại bằng checker hai mốc](ppk2_B5_attempt1_recheck_PASS.json)
PASS 20/20. Xem báo cáo §6.1.

Thư mục `kv260-supp2-2M-pairs5-20261027-1403` ngoài Git có chữ "2M" trong tên nhưng chạy ở 1M; bản trong thư mục
này đặt tên đúng `kv260_supp2_1M_pairs5.json`.

`tx_us`/`wait_us` trong các bảng chu kỳ là thời gian CPU thức (DWT dừng khi CPU ngủ), không phải độ trễ (báo cáo §4).

Raw (`cdc.log`, log request KV260, PPK2 `raw.bin`, `week8_inputs.h`, `reference_s2.npz`, gói SV2, ảnh) nằm ngoài Git
tại `D:\HUST\ASI_week8\`. Sinh lại thư mục này: `device/scripts/publish_week8_results.py --lab D:/HUST/ASI_week8
--out results/week8/device` (phụ lục C của báo cáo).
