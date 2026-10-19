# SV1 tuần 6 — nghiệm thu Device trên Dongle qua BLE

Phiên lab `device-session-20261019`, ngày 19/10/2026 (Asia/Saigon). nRF52840 Dongle (PCA10059) là BLE
peripheral; laptop Windows 11 (bleak 3.0.2) là BLE central/echo peer. Firmware build
`afa88870379c-default-20261018T062058Z` và `afa88870379c-mtu23-20261018T062140Z` (commit `afa8887`,
cây sạch). Cả 8 tiêu chí ở [kế hoạch tuần 6](../../docs/week6_device_edge_plan.md) §1 **PASS** trên MCU.

- [Báo cáo cho thầy](../../docs/sv1_device_week6_report.md)
- Tiêu chí 1–2, 8 (DWT): [self-test](selftest_default.json), [50 vector P1](p1_vectors_50.csv), [DWT theo split](dwt_by_split.csv)
- Tiêu chí 3–5, 8 (RTT): [1000 packet MTU 247](loopback_official_1000_mtu247.json), [40 packet MTU 23](loopback_mtu23_4sizes_x10.json),
  [200 packet thường](loopback_plain200_mtu247.json), [counter](loopback_counters.csv), [RTT theo cỡ frame](loopback_rtt_by_size.csv)
- Tiêu chí 6: [19 kịch bản negative](negative_19_summary.json)
- Tiêu chí 7: [hook lỗi](nonce_hooks.json), [110 reset mềm](nonce_soft_reset_110.json), [12 lần rút USB](nonce_power_cut_12.json),
  [gộp ba phiên](nonce_combined.json), DFU [default→mtu23](sentinel_dfu_default_to_mtu23.json) và [mtu23→default](sentinel_dfu_mtu23_to_default.json)
- Tiêu chí 8 (build): [build_check/](build_check/), stack [high-water](stack_highwater.csv); [DFU receipt](dfu/)
- [manifest.json](manifest.json): SHA-256 và nguồn của từng file bằng chứng (README này không nằm trong manifest)

Hai file giữ lại dù **FAIL**, không dùng làm bằng chứng, để không giấu lần chạy hỏng:
[negative_first_run_summary.json](negative_first_run_summary.json) (`disconnect_mid` 18/19, do Windows giữ link
3,2 s sau `disconnect()`; xem báo cáo §3), và
[sentinel_dfu_mtu23_to_default_wrong_baseline.json](sentinel_dfu_mtu23_to_default_wrong_baseline.json) (lệnh của
runbook so image `default` với chính nó; đã sửa checker bằng `--image-before`).
[negative_disconnect_mid_trial.json](negative_disconnect_mid_trial.json) là lần thử PASS đầu tiên sau khi sửa công cụ.

Raw `cdc.log`/`peer.jsonl`/`session.json` (2,6 MB, có SHA-256 công cụ trong từng `session.json`) nằm ngoài Git tại
`D:\HUST\ASI_week6\device-session-20261019`; build tại `D:\HUST\ASI_week6\20261019-r1-default` và `-mtu23`.
Sinh lại thư mục này: `device/scripts/publish_week6_results.py` (lệnh ở đầu file).
