# SV1 tuần 7 — marker D0–D4, công cụ đo PPK2 và năng lượng từng pha trên Dongle

Hai ngày lab: 20/10/2026 dongle cấp từ USB laptop (`session-20261020`: TC4, TC7, dry run) và 22/10/2026 dongle cấp
từ PPK2 Source Meter 5000 mV qua breakout VBUS (`session-20261022`: A1, A2, B1, B2), 26–27 °C. Firmware commit
`f16d897`, cây sạch; image đo `f16d897c0009-energy-fast-20261019T141139Z`; peer BLE là laptop Windows 11 chạy stub
edge. Cả 9 tiêu chí tuần 7 ([phụ lục A của báo cáo](../../docs/sv1_device_week7_report.md#phụ-lục-a-tiêu-chí-nghiệm-thu-và-quyết-định-w7-d1w7-d11)) **PASS**.
Số chính là phiên **B2** (s = 2, 50 P1 + 50 P0): `E_cycle` 1470,5 ± 17,3 µJ (P1), 1461,1 ± 16,7 µJ (P0), gross tại 5 V.

- [Báo cáo cho thầy](../../docs/sv1_device_week7_report.md)
- TC1, TC2, TC5, TC6 (phiên B2): [kiểm phiên](ppk2_B_session.json), [phân tích pha](phase_analysis_summary.json),
  [100 chu kỳ](cycles_100.csv), [thống kê từng pha](phase_energy_summary.csv), [marker so DWT](phase_time_marker_vs_dwt.csv),
  [stub edge](stub_edge_session.json), [capture](ppk2_B_session_capture.json), [session](ppk2_B_session_session.json)
- TC1 (D0–D3), TC2: [A2 image Active tuần 1](ppk2_A2_active_week1.json); TC2, TC3: [A1 image Idle tuần 2](ppk2_A1_idle_week2.json)
- TC4: [verify 11 split](verify_tc4.json), [dry run 50 + 50](dryrun_50p1_50p0.json), [stub dry run](dryrun_stub_edge.json)
- TC7: [bench hai kernel](bench_tc7.json), [t_dev theo split](t_dev_bench_by_split.csv)
- TC8: [build_check/](build_check/), [tài nguyên](build_resources.csv); [DFU receipt](dfu/)
- Hình IEEE (PDF vector + PNG 600 dpi): [figures/](figures/)
- [manifest.json](manifest.json): SHA-256 và nguồn của từng file (README này không nằm trong manifest), raw ngoài Git
  (`raw_outside_git`), báo cáo FAIL giữ lại (`kept_fail_reports`), DFU hỏng (`failed_dfu_receipts`)

Phiên lặp lại **B1** (9 phút trước B2, cùng image và bàn đo): [FAIL gốc](ppk2_B_attempt1_FAIL.json) chỉ ở
`TC5_one_cycle_per_request` do checker so đầu chu kỳ với thời điểm stub nhận xong request (= cuối TX);
[kiểm lại bằng checker đã sửa](ppk2_B_attempt1_recheck_PASS.json) PASS 14/14; [phân tích](ppk2_B_attempt1_phase_analysis_summary.json),
[100 chu kỳ](ppk2_B_attempt1_cycles_100.csv). Xem báo cáo §4.5.

Giữ lại dù **FAIL**, không dùng làm bằng chứng: [verify_first_run_FAIL.json](verify_first_run_FAIL.json) (3 ca s = 10
lệch 1 ULP scale FP16, đã giải thích ở tuần 5), [dryrun_first_check_FAIL.json](dryrun_first_check_FAIL.json)
(ngữ nghĩa `reserved_through` lúc boot), [ppk2_B_attempt1_FAIL.json](ppk2_B_attempt1_FAIL.json), và receipt DFU exit 1
`dfu/dfu-20261022-083808-…` (cổng bootloader không mở được, nạp lại sau khi rút cắm).

Raw PPK2 (`raw.bin`, 4 B/mẫu), `cdc.log`, `peer.jsonl` nằm ngoài Git tại `D:\HUST\ASI_week7\session-20261020` và
`D:\HUST\ASI_week7\session-20261022`; build tại `D:\HUST\ASI_week7\firmware-20261019`. Phân tích lại từ raw:
`device/scripts/energy_phases.py analyze --raw <phiên>\ppk2 ...`. Sinh lại thư mục này:
`device/scripts/publish_week7_results.py` (lệnh ở phụ lục C.3 của báo cáo).
