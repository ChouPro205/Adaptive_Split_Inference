# SV1 tuần 9 — E_dev(s) cho mọi s và khóa bàn đo PPK2

Hai ngày lab: 29/10/2026 (TC2 VERIFY + TDEV, ba phiên `E_dev` B4-1…3, hai phiên thử bộ ổn áp) và 09/11/2026 (phần B
với KV260 ở s = 2). Firmware tuần 9 commit `2e1daff` (image `dev`, `dev-usb`) và `a412624` (biến thể REG0/REG1 LDO),
cây sạch; phần B dùng image `energy` sạch của tuần 8 (`5d070cbaddf0-…-20261026T055457Z`). **8/8 tiêu chí PASS.**

- [Báo cáo tuần 9](../../../docs/sv1_device_week9_report.md)
- TC1: [build_check/](build_check/), [build_resources.csv](build_resources.csv), [dfu/](dfu/); thứ tự chu kỳ
  [plan/](plan/), tham chiếu host [refs/](refs/)
- TC2: [VERIFY + TDEV](tc2_verify.json), SESSION khô [gap 0](tc2_session_dry_gap0.json) và
  [gap 1000 ms](tc2_session_dry_gap1000.json)
- TC3–TC5 (ba phiên board): `b4_s{1,2,3}_check_session_recheck.json` (PASS), `b4_s*_energy_dev.json`,
  `b4_s*_session.json`, `b4_s*_capture.json`, `b4_s*_analysis_summary.json`, ghi chú `b4_s*_note-*.json`.
  Báo cáo gốc `b4_s*_check_session_FAIL_original.json` giữ lại: chỉ FAIL `TC4_no_sample_above_3mA_between_cycles`
  do ngắt tràn RTC 512 s (báo cáo §6.1)
- TC6: [phiên 1 → 2](b4_compare_s1_s2.json), [phiên 2 → 3](b4_compare_s2_s3.json)
- Thử bộ ổn áp: `b4_reg0ldo_*` (PASS), `b4_reg1ldo_*` (giữ báo cáo FAIL một chu kỳ, §3)
- TC7 (KV260, s = 2): phiên 1 `b5_kv260_p1_*` và phiên 4 `b5_kv260_p4_*` (mỗi phiên `check_session`, `check_kv260`,
  `energy_kv260_s2`, `edge_summary`, `session`, `capture`, `analysis_summary`, ghi chú). Phiên 2 (`b5_kv260_p2_*`,
  mất 48 mẫu giữa hai chu kỳ) và phiên 3 (`b5_kv260_p3_*`, laptop chạy pin) giữ báo cáo FAIL (§6.3)
- Phân tích ([analysis/](analysis/), sinh bằng `week9_figures.py tables`):
  [table_iii_e_dev.csv](analysis/table_iii_e_dev.csv) (cột E_dev cho Bảng III),
  [table_kv260_s2_pooled.csv](analysis/table_kv260_s2_pooled.csv), [table_kv260_s2.csv](analysis/table_kv260_s2.csv),
  bảng từng chu kỳ `cycles_dev_*.csv`, `cycles_kv260_*.csv`, khoảng nghỉ có kết nối `gaps_kv260_*.csv`,
  [week9_analysis.json](analysis/week9_analysis.json) (mọi thống kê, SHA-256 đầu vào, quyết định W9-D9…D12)
- Hình IEEE ([figures/](figures/), PDF vector + PNG 600 dpi; số liệu từng hình là `analysis/fig_*.csv`)
- [manifest.json](manifest.json): SHA-256 và nguồn từng file (README này không nằm trong manifest), raw ngoài Git
  (`raw_outside_git`), báo cáo FAIL giữ lại (`kept_fail_reports`)

Raw (PPK2 `raw.bin`, `cdc.log`, log request/Read PHY/btmon của KV260, ảnh bàn đo, log console) nằm ngoài Git tại
`D:\HUST\ASI_week9\` và `D:\HUST\Trung\0911\`. Sinh lại thư mục này: phụ lục C của báo cáo.
