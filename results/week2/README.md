# Kết quả đo Week 2 – nRF52840 Dongle với PPK2

## Mục tiêu

- Đo dòng tiêu thụ của nRF52840 Dongle bằng Nordic Power Profiler Kit II
  (PPK2).
- Kiểm tra firmware Active, firmware Idle và các GPIO logic marker trong cấu
  hình đo thực tế.

## Phần cứng và cách nối

- Thiết bị: Nordic nRF52840 Dongle PCA10059.
- PPK2 hoạt động ở chế độ Source Meter, điện áp nguồn 5,0 V.
- Dongle được cấp nguồn qua USB breakout.
- Không thay đổi cầu hàn SB1/SB2.
- Không cấp nguồn đồng thời cho dongle từ PPK2 và cổng USB của máy tính.
- Các kênh logic được nối như sau:

| Kênh PPK2 | GPIO nRF52840 |
|---|---|
| D0 | P0.13 |
| D1 | P0.15 |
| D2 | P0.17 |
| D3 | P0.20 |

Ảnh đấu nối thực tế: [PPK2 và USB breakout](figures/setup_wiring_vbus5v.jpg).

## Thông số đo

- Tần số lấy mẫu: 100.000 samples/s (100 kS/s).
- Thời gian mỗi phép đo: 60 giây.
- Active và Idle được đo với cùng cấu hình phần cứng, nguồn và cách nối.

## Kết quả Idle

Các giá trị dưới đây được lấy trực tiếp từ
[`summary/week2_idle_summary.csv`](summary/week2_idle_summary.csv):

| Đại lượng | Kết quả |
|---|---:|
| Số lượng mẫu | 6.000.001 |
| Thời lượng | 60,000 s |
| Tần số lấy mẫu thực tế | 100.000 samples/s |
| Dòng trung bình | 25,417 µA |
| Độ lệch chuẩn mẫu | 3,707 µA |
| Dòng trung vị | 23,946 µA |
| Dòng nhỏ nhất | 20,328 µA |
| Dòng lớn nhất | 35,683 µA |
| Percentile 95% | 33,124 µA |
| Percentile 99% | 34,051 µA |
| Điện tích tích phân | 1,525 mC |

D0, D1, D2 và D3 đều giữ mức LOW trong toàn bộ 6.000.001 mẫu; không có mẫu
non-LOW hoặc mẫu logic không hợp lệ.

Histogram Idle lệch phải: phần lớn mẫu tập trung ở vùng dòng thấp, kèm theo
một số mẫu có dòng cao hơn tạo thành phần đuôi về phía phải.

## Hình minh chứng

- [Ảnh đấu nối PPK2, USB breakout và dongle](figures/setup_wiring_vbus5v.jpg)
- [Active và logic marker – toàn bộ 60 giây](figures/active_marker_overview_60s.png)
- [Active và logic marker – phóng to 3 giây](figures/active_marker_zoom_3s.png)
- [Dạng sóng dòng Idle – 60 giây](figures/idle_waveform_60s.png)
- [Phân bố dòng Idle](figures/idle_current_histogram.png)

Phép đo Active hiện được dùng để xác nhận marker và chu kỳ hoạt động của
firmware. Kết quả này chưa được coi là benchmark năng lượng cuối cùng của hệ
thống.

## Chạy lại phân tích Idle

Chạy từ thư mục gốc của repository:

```powershell
python .\tools\analyze_week2_idle.py .\results\week2\raw\2026-09-22_idle_vbus5v_60s.csv
```

Các file đo thô CSV/PPK2 được lưu cục bộ trong `results/week2/raw/` và bị Git
ignore. GitHub chỉ lưu script phân tích, bảng summary, README và các hình minh
chứng; dữ liệu đo thô không được đưa lên repository.
