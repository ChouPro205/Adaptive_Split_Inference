# Báo cáo SV1 tuần 5 — lượng tử hóa activation trên nRF52840 Dongle

Nghiệm thu kỹ thuật: **PASS**, scope **REAL_MCU_CAPTURE**, ngày 2026-10-09 (Asia/Saigon).
Source dùng để build/nạp/đo: `51ef9c966e052bfd63c8e416dcfad3d6af30e755`. Firmware ID `04fbe659696a183e4680c16f1f425081500654da44cdb6fbf233de1372507207`.
Source kernel CNN FP32, checkpoint, preprocessing, mapping s=0..10 và mọi tài sản/bằng chứng tuần 3–4 giữ nguyên. App tuần 5 độc lập; không build lại vì source/artifact vẫn đúng.

| Gate | Kết quả |
|---|---|
| Preflight source/ELF/HEX/ZIP/application | PASS thường và -O |
| Nordic application USB DFU | PASS, exit 0, bootloader COM6 |
| MCU capture thật | 220/220 primary + 16/16 mixed, ứng dụng COM7 |
| FP32 finite/strict <1e-3 và s0 bitwise | PASS; max abs error 1.43051147461e-05; s0 20/20 bitwise |
| INT8/FP16 trên chính FP32 MCU | Oracle exact 236/236, không tolerance/whitelist |
| P2 so capture MCU tuần 3 có provenance | PASS; 20/20 bitwise; max error 0.0 |
| Checker độc lập và guard provenance | PASS thường và -O; các negative tests PASS |
| Regression hiện hành/quantization/parser/capture lịch sử | PASS thường và -O |
| Accuracy offline | 8.544 × 11, baseline 8.393; mọi split strict drop <0,5 pp |
| Timing / RAM / stack runtime | NOT_MEASURED |

Các trường hash/source/command/exit-code trong JSON nối snapshot chuẩn bị → REAL_USB_DFU → collection receipt → capture → checker thường/-O → P2 lịch sử → nghiệm thu.
DFU UTC: `2026-10-09T14:25:36.9203075+00:00`; collection UTC: `2026-10-09T14:39:59.880726+00:00`.
Bootloader USB `VID_1915/PID_521F`; CDC `VID_2FE3/PID_0004`, product `Adaptive Split Inference SV1`. Cổng được xác định từ thiết bị thực tế mỗi giai đoạn.

## Sai khác số học đã phân tích

Mọi byte INT8 MCU khớp cả golden SV3. Ba scale FP16 khác golden tại s10 được kiểm lại trên capture thật; không sử dụng whitelist từ Host C.
| Mẫu | Kênh | Raw scale golden FP32 | Raw scale MCU FP32 | Midpoint FP16 | Bits golden → MCU |
|---:|---:|---:|---:|---:|---|
| 8 | 3 | 0.00103424757253 | 0.00103426491842 | 0.00103425979614 | 0x143c → 0x143d |
| 13 | 3 | 0.00204945169389 | 0.0020494335331 | 0.00204944610596 | 0x1833 → 0x1832 |
| 18 | 2 | 0.00497248396277 | 0.00497244019061 | 0.00497245788574 | 0x1d18 → 0x1d17 |

Sai số head FP32 làm raw scale đi qua midpoint FP16. Python reference trên đúng activation MCU tạo chính bytes/bits MCU đã gửi. Unexplained mismatch = 0.

## Accuracy toàn bộ tập test — offline

Tái sử dụng kết quả head FP32 chuẩn → quantization/dequantization C → tail frozen: source hashes, checkpoint, dataset receipts và tail đều không đổi. Không dùng 20 mẫu thay tập accuracy và không tuyên bố chạy 8.544 mẫu trên Dongle.
| s | FP32 đúng/8544 | INT8+FP16 đúng/8544 | Accuracy (%) | Giảm (pp) | Giảm tương đối (%) |
|---:|---:|---:|---:|---:|---:|
| 0 | 8393 | 8391 | 98.209270 | 0.023408 | 0.023829 |
| 1 | 8393 | 8390 | 98.197566 | 0.035112 | 0.035744 |
| 2 | 8393 | 8391 | 98.209270 | 0.023408 | 0.023829 |
| 3 | 8393 | 8392 | 98.220974 | 0.011704 | 0.011915 |
| 4 | 8393 | 8393 | 98.232678 | 0.000000 | 0.000000 |
| 5 | 8393 | 8395 | 98.256086 | -0.023408 | -0.023829 |
| 6 | 8393 | 8388 | 98.174157 | 0.058521 | 0.059573 |
| 7 | 8393 | 8391 | 98.209270 | 0.023408 | 0.023829 |
| 8 | 8393 | 8391 | 98.209270 | 0.023408 | 0.023829 |
| 9 | 8393 | 8393 | 98.232678 | 0.000000 | 0.000000 |
| 10 | 8393 | 8393 | 98.232678 | 0.000000 | 0.000000 |

Baseline 8393/8544 = 98,232678%. Worst s6: giảm 0.058521 pp; giảm tương đối 0.059573%. s5 cải thiện nên giữ drop âm.

## Kích thước tensor và scales offline

| s | Shape | FP32 B | INT8 B | FP16 scale B | Tổng B | Giảm tổng (%) |
|---:|---|---:|---:|---:|---:|---:|
| 0 | 1x1x360 NCL | 1440 | 360 | 2 | 362 | 74.861111 |
| 1 | 1x16x360 NCL | 23040 | 5760 | 32 | 5792 | 74.861111 |
| 2 | 1x16x180 NCL | 11520 | 2880 | 32 | 2912 | 74.722222 |
| 3 | 1x32x180 NCL | 23040 | 5760 | 64 | 5824 | 74.722222 |
| 4 | 1x32x90 NCL | 11520 | 2880 | 64 | 2944 | 74.444444 |
| 5 | 1x48x90 NCL | 17280 | 4320 | 96 | 4416 | 74.444444 |
| 6 | 1x48x45 NCL | 8640 | 2160 | 96 | 2256 | 73.888889 |
| 7 | 1x64x45 NCL | 11520 | 2880 | 128 | 3008 | 73.888889 |
| 8 | 1x64x22 NCL | 5632 | 1408 | 128 | 1536 | 72.727273 |
| 9 | 1x32 NC | 128 | 32 | 64 | 96 | 25.000000 |
| 10 | 1x5 NC | 20 | 5 | 10 | 15 | 25.000000 |

FP32 = 4 × elements; INT8 = elements; scale FP16 = 2 × channels. Chỉ payload INT8 giảm đúng 4×; tổng cộng scale giảm 25%–74,861111% tùy split. Chưa tính header hoặc wire I1.

## Quyết định hiện hành và giới hạn

- INT8 symmetric per sample/channel trên L, zero-point=0, q trong [-127,127]; scale lưu FP16; q dùng scale_effective đọc lại từ FP16. FP32 và FP16 đều làm tròn nearest ties-to-even theo reference.
- I1 v1 khi triển khai: scales FP32 little-endian, là giá trị FP16 đã lưu mở rộng chính xác sang FP32. Wire protocol giữ nguyên; I1 chưa FROZEN và Device–Edge chưa PASS.
- I2/1: NCL, descriptor/profile N,C,L; s9/s10 thêm L=1; đảo I2 trước dequantize. Model s=0..10 giữ nguyên; wire split_id phải có mapping registry rõ ràng, chưa gán trong tuần này.
- Accuracy chính: strict giảm <0,5 điểm phần trăm mỗi split; mức giảm tương đối là thông tin bổ sung.
- Không có BENCH; timing và RAM/stack runtime NOT_MEASURED. Không lấy số tuần 4 thay cho tuần 5. PPK2, radio, P1 C, KV260 và tuần 6 chưa bắt đầu.

## Hiện vật và các SHA độc lập

Snapshot trước nạp giữ nguyên `D:\HUST\ASI_week5_prepare\20261009-sv1-prepare01\preparation.json`; SHA256 `bed996d79ea68a888ccee254869c45921296bb85fa6ed3e93b36debe10c63cac`; trạng thái bên trong vẫn NOT_RUN/PENDING. Kết quả thật nằm trong receipts/báo cáo riêng.
Phiên raw/logs/receipts: `D:\HUST\ASI_week5_mcu\20261009-212416`. Capture SHA256 `0c915b90658be5d01ce87eddab747f0f4c35dfdc893e1a617df8d6d42d986378`.
P2 cũ được pin vào tree `51ef9c966e052bfd63c8e416dcfad3d6af30e755`, package v2 manifest `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`, capture `72c7b6a2ba554f7e6d242a49e20065a4b56a3967108206a9a4d8845f1e795606` và anchor báo cáo R3 đã chấp nhận.

- ELF: `D:\HUST\ASI_week5_prepare\20261009-sv1-prepare01\build\zephyr\zephyr.elf`; SHA256 `64b930ec978c5f628c1de85cd32cd51f44a3a2ec95c84a0cdddf58529c87ccab`.
- HEX: `D:\HUST\ASI_week5_prepare\20261009-sv1-prepare01\build\zephyr\zephyr.hex`; SHA256 `0da170739e6170fbc6b639c2f66ff4f0e713d1e59183ad57484e94d270c61d41`.
- ZIP: `D:\HUST\ASI_week5_prepare\20261009-sv1-prepare01\adaptive_split_week5.zip`; SHA256 `00760b2a8467bdf0875883ac865b8b2e6c24f2e250555e93c3a722f11952b40f`.
- Application trong ZIP: SHA256 `15f07bffb1411eff9d565381fce1078cc477fa01e0533db0cce9923f53a0bf27`; 524180 B.

Bảng đầy đủ 220 case, 16 mixed case, kích thước, accuracy và JSON provenance nằm tại `results/week5/`.
Commit báo cáo và merge SHA được ghi riêng sau tích hợp trong `D:\HUST\ASI_week5_mcu\20261009-212416\git\git_integration_final.json`. Tại thời điểm tạo commit báo cáo, tích hợp Git còn PENDING; không thay image source SHA bằng report/merge SHA.
