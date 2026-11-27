# Attack v3 r5: kết quả phần a, b, c, d trên DS1

Ngày 27/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Đọc trước.** Đây là số phát triển trên DS1 (N = 22), chỉ dùng làm cảnh báo sớm (tin SV1 27/11 mục 3). Bệnh nhân DS1 đã có trong tập train của checkpoint A. Các số này không chọn tham số nào ngoài α; α chỉ chọn trên phần utility. Số của bài lấy từ lượt DS2 riêng tư (tuần 14). DS2 chưa mở.

## 1. Lượt chạy và hồ sơ

| | Phần a, b, d | Phần c |
|---|---|---|
| Lệnh | `attack_m1_v3.py run --parts abd` | `noise_m1_v3.py run --part-a-dir <thư mục a, b, d>`, không có `--fallback-R` |
| Commit nguồn | `e55e82b` (commit file cho phép chạy) | `7dba869` (commit receipt a, b, d) |
| Thời gian (UTC) | 06:22–06:44, khoảng 22 phút | 06:57–08:52, khoảng 1 giờ 55 phút |
| Mã thoát, stderr | 0, trống | 0, trống |
| Receipt | `ml/provenance/m1-attack-v3-abd-run-20261127/receipt.json`, SHA `e3996a01…` | `ml/provenance/m1-attack-v3-c-run-20261127/receipt.json`, SHA `2e571b70…` |

- File cho phép chạy: `ml/provenance/m1-attack-v3-run-auth-20261127/`, SHA `6481e9a2…`, commit `e55e82b`; chỉ DS1, `allow_DS2 = false`, nhiễu sinh mới mỗi epoch.
- RTX 5060, torch 2.14.0+cu130, TF32 tắt, chế độ tất định bật.
- Kiểm trong lượt chạy: s9/s10 trên 20 nhịp golden trùng từng bit; S0c trùng từng bit với `s0c_v1_ref.py` trên 20 nhịp golden và trên toàn bộ 50.995 nhịp DS1 của lượt chạy; cổng tái lập phần b đạt ở mọi đích s2, s4, s5, s8, s9, s10.
- Phần c: run manifest ghi phương án nhiễu "fresh" trước lần fit đầu. Các file phần a mà phần c đọc khớp receipt a, b, d.
- Mỗi Π kèm CI95 bootstrap khối trong bệnh nhân (2000 lần, khối 10 nhịp). Π_k kèm khoảng phân vị trên 200 lần rút.

## 2. Phần a và b: Π theo nhịp (ρ0)

| Nguồn gửi | Π_v3 | CI95 | Kẻ tấn công mạnh nhất | Adv B-naive |
|---|---|---|---|---|
| S0c | 0,075 | 0,069–0,081 | B-naive ở S0c | 0,925 |
| s0 | 0,068 | 0,062–0,073 | ghép s0 → s8 | 0,817 |
| s2 | 0,068 | 0,062–0,073 | ghép s2 → s8 | 0,900 |
| s4 | 0,068 | 0,062–0,073 | ghép s4 → s8 | 0,919 |
| s5 | 0,068 | 0,062–0,073 | ghép s5 → s8 | 0,924 |
| s8 | 0,068 | 0,062–0,073 | B-naive ở s8 | 0,932 |
| s9 | 0,102 | 0,095–0,110 | B-naive ở s9 | 0,898 |
| s10 (logits FP32) | 0,287 | 0,279–0,298 | B-naive ở s10 | 0,713 |

- Mọi điểm gửi đều dưới Π_min = 0,5. Cách đọc khai trước: Π(s9) dưới Π_min; Π trên logits dưới Π_min.
- Tấn công ghép làm Π của s0 đến s5 bằng Π của s8: edge chạy tiếp các lớp đã đóng băng tới s8 rồi dùng kẻ tấn công ở s8.
- Với S0c, tấn công ghép yếu hơn tấn công trực tiếp: Adv ghép sang s2 chỉ 0,41, sang s9 là 0,87. Kẻ tấn công trực tiếp trên 46 giá trị đã đạt Adv 0,925.
- Mức dựng lại từ S0c (chỉ báo): nội suy của edge, không cần train, cho NRMSE trung bình 0,338, Pearson 0,934; bộ refiner train trên kết quả nội suy tốt hơn, NRMSE 0,179, Pearson 0,982, và là số báo chính theo protocol.

## 3. Phần d: Π khi gộp k nhịp (ρ0)

Π_k lấy trường hợp xấu nhất trên {đa số, mềm, trung bình} × {liên tiếp, rải rác} × mọi kẻ tấn công.

| Hàng | k = 1 | 2 | 5 | 10 | 20 | 50 | 100 |
|---|---|---|---|---|---|---|---|
| S0c | 0,075 | 0,042 | 0,020 | 0,011 | 0,009 | 0,003 | 0,001 |
| s0 | 0,068 | 0,036 | 0,014 | 0,006 | 0,001 | 0 | 0 |
| s2 | 0,068 | 0,042 | 0,014 | 0,003 | 0,001 | 0 | 0 |
| s4 | 0,068 | 0,039 | 0,016 | 0,005 | 0,002 | 0 | 0 |
| s5 | 0,063 | 0,043 | 0,014 | 0,005 | 0,001 | 0 | 0 |
| s8 | 0,068 | 0,044 | 0,014 | 0,004 | 0,001 | 0 | 0 |
| s9 | 0,102 | 0,040 | 0,018 | 0,006 | 0,003 | 0,000 | 0 |
| s10 | 0,287 | 0,178 | 0,094 | 0,063 | 0,040 | 0,028 | 0,019 |

Gộp 10 nhịp là đủ để nhận đúng người gần như chắc chắn ở mọi điểm gửi. Đây là bằng chứng cho ý "không che danh tính" trong threat model.

## 4. Phần c: nhánh R (S2 + ρ2) và đối chứng C0c

α chọn trên phần utility (DS1 validation) để đạt 99/98/97/95 % macro-F1 của A. Mốc macro-F1 0,5398.

| Cấu hình | Mục tiêu | α | macro-F1 | Π | CI95 | Π_k10 | Kẻ tấn công mạnh nhất | Dựng lại A1 thích nghi: NRMSE / Pearson | Đạt trên DS1 |
|---|---|---|---|---|---|---|---|---|---|
| R2 | 99 % | 0,0705 | 0,5679 | 0,067 | 0,061–0,072 | 0,005 | ghép thích nghi → s8 | 0,057 / 0,998 | Không |
| R2 | 98 % | 0,2190 | 0,5601 | 0,070 | 0,064–0,076 | 0,003 | ghép thích nghi → s8 | 0,098 / 0,995 | Không |
| R2 | 97 % | 0,3260 | 0,5575 | 0,072 | 0,066–0,077 | 0,006 | ghép thích nghi → s8 | 0,125 / 0,991 | Không |
| R2 | 95 % | 0,4114 | 0,5433 | 0,074 | 0,068–0,080 | 0,006 | ghép thích nghi → s8 | 0,143 / 0,989 | Không |
| C0c | 99 % | 0,0353 | 0,5631 | 0,070 | 0,065–0,076 | 0,006 | ghép thích nghi → s8 | 0,191 / 0,980 | Không |
| C0c | 98 % | 0,0628 | 0,5571 | 0,075 | 0,068–0,081 | 0,005 | ghép thích nghi → s8 | 0,207 / 0,976 | Không |
| C0c | 97 % | 0,0775 | 0,5512 | 0,078 | 0,072–0,085 | 0,005 | ghép thích nghi → s8 | 0,217 / 0,974 | Không |
| C0c | 95 % | 0,0912 | 0,5420 | 0,075 | 0,069–0,081 | 0,004 | ghép thích nghi → s8 | 0,226 / 0,972 | Không |

- Cả 8 điểm qua cổng macro-F1, nhưng Π chỉ khoảng 0,07, xa Π_min = 0,5. `selected_on_DS1` rỗng; cách đọc khai trước là "neither". Theo bảng quyết định của hướng dẫn mục 5.3a, đây là kết quả âm cho cơ chế và phạm vi đã thử.
- So với lúc không nhiễu (Π của s2 là 0,068, của S0c là 0,075), nhiễu ở các mức này gần như không nâng Π.
- Mức dựng lại chỉ báo, không là điều kiện đạt. Ở cả 8 điểm, decoder A1 thích nghi chạy đủ 50 epoch.

## 5. Số epoch thực chạy của các biến thể thích nghi (patience 5, tối đa 50)

Theo tin SV1 27/11 mục 2: kẻ tấn công nào dừng trước epoch 20 đã thấy ít lần rút nhiễu hơn mức tối thiểu 20 của phương án dự phòng. Số này dùng cho mục hạn chế, không phải cổng.

| Điểm | Số biến thể thích nghi | Ít nhất | Nhiều nhất | Dừng trước epoch 20 |
|---|---|---|---|---|
| R2 99 % | 19 | 17 | 50 | 2 |
| R2 98 % | 19 | 19 | 50 | 2 |
| R2 97 % | 19 | 17 | 50 | 1 |
| R2 95 % | 19 | 19 | 50 | 3 |
| C0c 99 % | 22 | 16 | 50 | 3 |
| C0c 98 % | 22 | 18 | 50 | 1 |
| C0c 97 % | 22 | 17 | 50 | 2 |
| C0c 95 % | 22 | 16 | 50 | 1 |

- Biến thể thích nghi gồm B-adaptive và B-composite-adaptive (→ s4, s5, s8, s9, s10; C0c có thêm → s2) cho 3 seed, cộng A1 thích nghi.
- Cả 15 trên 164 lần train dừng trước epoch 20 đều là B-composite-adaptive → s8; biến thể này chạy 16–39 epoch. Nó cũng là kẻ tấn công mạnh nhất ở cả 8 điểm. Dừng theo patience nghĩa là validation của kẻ tấn công không còn cải thiện, nhưng việc nó thấy ít hơn 20 lần rút nhiễu vẫn là một hạn chế phải ghi.
- Bảng đầy đủ theo từng biến thể và seed: `epochs_run` trong `ml/provenance/m1-attack-v3-c-run-20261127/receipt.json`.

## 6. Lệch GPU − CPU ở epoch 1 (chỉ báo)

Trên 256 hàng, mỗi đích s′: max |GPU − CPU| của u_s′ lớn nhất 0,139 (C0c 98 %), tỉ lệ giá trị lượng tử ở s′ bị lệch không quá 0,16 % ở mọi điểm. Số theo từng điểm và đích ở mục `gpu_cpu_epoch1` của receipt phần c.

## 7. Chưa làm

- Lượt DS2 riêng tư (tuần 14) theo r5 đã khóa: cần file cho phép riêng.
- Bảng quyết định nhánh R cho ngày 13/12 (H9) và số ngày công đã dùng.
- Hình Π–macro-F1 và Π theo k: làm khi có số DS2.
