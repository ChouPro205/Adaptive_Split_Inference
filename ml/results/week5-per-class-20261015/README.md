# Đánh giá theo lớp — snapshot tuần 5 (15/10/2026)

Bổ sung cho gate accuracy tuần 5; **không** thay gate đó và **không** đặt ngưỡng
mới. Gate nghiệm thu vẫn là: accuracy INT8+FP16 giảm `< 0,5` điểm phần trăm so
với FP32 ở mọi split.

## Nguồn

- Predictions của lần chạy `evaluate_week5_v2.py` mới trên source `e50c471`
  (`ml/provenance/week5-current-20261015/portable/accuracy/`), trùng byte với
  `ml/results/week5/predictions.csv` frozen (SHA-256
  `0776e503b9e404c957cfcfb239356f52b17f34655cb2c5d15fdfe96cb3ae6e56`): cùng
  checkpoint `9b8be076…`, tiền xử lý, split test và cấu hình lượng tử hóa
  `ncl-int8-fp16-v1-review`; tail là FP32.
- Lệnh: `ml/scripts/evaluate_week5_per_class.py`; receipt
  `ml/provenance/week5-current-20261015/extra/per_class.command.json`.

## File

| File | Nội dung |
|---|---|
| `per_class_metrics.json` | Toàn bộ số liệu, quy ước và nguồn |
| `per_class_metrics.csv` | Support, TP/FP/FN, precision, recall, F1 từng lớp, FP32 và INT8+FP16, 11 split; số dự đoán thay đổi |
| `confusion_matrices.csv` | Ma trận nhầm lẫn 5×5 (hàng: nhãn thật, cột: dự đoán) |
| `summary.csv` | Accuracy, macro-F1, balanced accuracy và recall từng lớp theo split |

Quy ước: precision để trống khi lớp không được dự đoán lần nào;
`F1 = 2TP/(2TP+FP+FN)`; macro-F1 là trung bình không trọng số của 5 lớp;
balanced accuracy là trung bình recall của các lớp có support > 0.

## Tập test và mô hình FP32

8.544 mẫu từ 4 bệnh nhân (P101, P122, P219, P228). Support: N 8.102, S 13,
V 426, F 1, Q 2. Kết quả FP32 giống nhau ở mọi split:

| Lớp | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| N | 8102 | 0,9922 | 0,9900 | 0,9911 |
| S | 13 | 0 (69 dự đoán, đều sai) | 0 | 0 |
| V | 426 | 0,9764 | 0,8732 | 0,9219 |
| F | 1 | 0 (1 dự đoán sai) | 0 | 0 |
| Q | 2 | 0 (9 dự đoán, đều sai) | 0 | 0 |

Accuracy 98,23%, macro-F1 0,3826, balanced accuracy 0,3726. Checkpoint đã duyệt
không nhận đúng mẫu S, F, Q nào của tập test; đây là đặc điểm của mô hình FP32,
không phải do lượng tử hóa.

## INT8+FP16 so với FP32

| s | Δ macro-F1 | Δ balanced acc. | N đúng→sai / sai→đúng | V đúng→sai / sai→đúng |
|---:|---:|---:|---:|---:|
| 0 | +0,00024 | +0,00040 | 5 / 2 | 1 / 2 |
| 1 | −0,00004 | −0,00007 | 4 / 1 | 0 / 0 |
| 2 | +0,00024 | +0,00040 | 4 / 1 | 0 / 1 |
| 3 | −0,00028 | −0,00047 | 1 / 1 | 1 / 0 |
| 4 | 0 | 0 | 2 / 2 | 0 / 0 |
| 5 | +0,00029 | +0,00049 | 1 / 2 | 0 / 1 |
| 6 | −0,00006 | −0,00012 | 5 / 0 | 0 / 0 |
| 7 | −0,00002 | −0,00005 | 2 / 0 | 0 / 0 |
| 8 | −0,00002 | −0,00005 | 2 / 0 | 0 / 0 |
| 9 | 0 | 0 | 0 / 0 | 0 / 0 |
| 10 | 0 | 0 | 0 / 0 | 0 / 0 |

Lượng tử hóa chỉ đổi dự đoán của một số mẫu N và V (nhiều nhất 10 mẫu ở `s=0`);
không đổi dự đoán nào của S, F, Q.

## Giới hạn

- S (13), F (1) và Q (2) có quá ít mẫu, tập test chỉ gồm 4 bệnh nhân: chưa đủ
  cơ sở kết luận về khả năng khái quát của các lớp này.
- Accuracy tổng thể chủ yếu phản ánh lớp N; không dùng nó để khẳng định chất
  lượng các lớp thiểu số.
- Số liệu dùng tail FP32 trên host; chưa bao gồm lượng tử hóa của tail trên DPU
  hay chạy trên MCU/KV260.
