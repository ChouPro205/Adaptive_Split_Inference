# SV3 tuần 8 — protocol train dài đã được người dùng chốt

Ngày29/10/2026, tiếp nối [protocol đề xuất và các pilot đầu](sv3_week8_protocol_v1.md).
Người dùng đã chọn ba seed20261021/20261022/20261023 và **train cả head + tail**,
Dropout bật trong train, tắt trong validation. Đây là xác nhận protocol thí nghiệm
của người dùng; không tự gán thành xác nhận GVHD hoặc duyệt triển khai.

[Quyết định gốc](../ml/provenance/week8-grid-20261029/user-protocol-confirmation.json)
giữ các trường locked đúng, nhưng trường answers bị mất ký tự tiếng Việt do
pipeline encoding. [Bản bổ sung UTF-8](../ml/provenance/week8-grid-20261029/user-protocol-confirmation-utf8.json)
giữ đúng nguyên văn hai câu trả lời; không ghi đè receipt đầu.

Config đã khóa: [week8_nopeek_approved_3seed_joint_v1.json](../ml/configs/week8_nopeek_approved_3seed_joint_v1.json).
Grid đủ54 run: s2/s5/s8 × lambda{0,0.1,0.5,1,2,5} ×3 seed.
Mỗi run bắt đầu lại từ cùng checkpoint frozen, optimizer mới và RNG theo seed.
Loss CE + lambda×dCor R_n; không weighted CE, resampling hoặc augmentation.
CUDA FP32 deterministic, TF32 off, batch32, Adam lr1e-4,
betas(0.9,0.999), eps1e-8, weight_decay0, không scheduler.
Tối đa30 epoch, patience5; chọn CE thấp nhất trên validation, hòa chọn epoch sớm.
Đọc đủ81094 train và15388 validation theo patient split frozen; drop_last train
còn81088 mẫu mỗi epoch, validation đủ mọi mẫu. Không đọc test arrays trong grid.

Pilot CUDA joint mới dùng512 train/256 validation, hai epoch,
s2/s5/s8 ×lambda0/0.5 ×seed20261021. Pilot này thay việc suy từ pilot head_only
sang chế độ train mới; giữ root và receipts riêng, không tính vào54 run grid.
Sau pilot joint v1, lượt grid đầu đo khoảng43 giây/epoch. Các phép kiểm hữu hạn
được gộp để giảm đồng bộ GPU, không đổi phép train. Tests24/24 thường/-O chạy
lại; phép đối chiếu engine kiểm loss/metrics/weights/gradients/RNG khớp bit
trên CPU và CUDA. Pilot joint v2 kiểm lại trọn vòng trên source mới.
Source/hash/runtime/config riêng được lưu trong experiment/receipts.

Trước khi có đủ kết quả grid, đã ghi [quy tắc chọn candidate](../ml/provenance/week8-grid-20261029/candidate-selection-rule.json):
trong mỗi split, chọn lambda có mean validation CE thấp nhất qua ba seed;
hòa chọn lambda nhỏ hơn. Giữ cả ba checkpoint seed, không chọn seed đẹp nhất.
Đây là quyết định triển khai theo validation CE; không gán là quy tắc GVHD đã duyệt.
Không tối ưu xuyên split hoặc dùng kết quả test/attack để chọn lambda.
Mean ± sample std(ddof1) mô tả biến thiên training giữa seed, không phải ba cohort
bệnh nhân độc lập. Accuracy, CE/dCor, macro-F1, confusion và recall lớp vẫn báo đủ.

Output chính thức:
`ml/results/week8-nopeek/grid/grid-3seed-joint-v2/`.
Checkpoints bị ignore:
`ml/artifacts/week8-nopeek/grid/grid-3seed-joint-v2/`.
Receipts/logs:
`ml/provenance/week8-grid-20261029/`.
Mỗi epoch lưu progress checkpoint atomic; run status phân biệt complete/error/interrupted.
Giới hạn orphan/lock và cách resume giữ theo protocol v1; không sửa evidence cũ.

```powershell
$py = (Resolve-Path ../../ml/.venv/Scripts/python.exe).Path
& $py -B ml/scripts/run_week8_nopeek.py --config ml/configs/week8_nopeek_approved_3seed_joint_v1.json --mode grid --output ml/results/week8-nopeek/grid/grid-3seed-joint-v2 --artifacts ml/artifacts/week8-nopeek/grid/grid-3seed-joint-v2
# Chỉ dùng --resume với đúng experiment/config/source/device:
& $py -B ml/scripts/run_week8_nopeek.py --config ml/configs/week8_nopeek_approved_3seed_joint_v1.json --mode grid --output ml/results/week8-nopeek/grid/grid-3seed-joint-v2 --artifacts ml/artifacts/week8-nopeek/grid/grid-3seed-joint-v2 --resume
& $py -B ml/scripts/summarize_week8_nopeek.py --experiment ml/results/week8-nopeek/grid/grid-3seed-joint-v2 --artifacts ml/artifacts/week8-nopeek/grid/grid-3seed-joint-v2 --output ml/results/week8-nopeek/grid/grid-3seed-joint-v2/analysis
```

Các đường dẫn trên là evidence thực tế; khi tái lập độc lập phải dùng tên experiment
mới, không ghi đè. Không tự chạy lại tổ hợp đã complete nếu không có lý do kiểm chứng.
Lượt `grid-3seed-joint-v1` bị ngắt để kiểm engine, giữ nguyên checkpoint/log/status
thô và stale locks; không resume hoặc tính nó vào54 run của v2.
Receipt bổ sung ghi rõ trạng thái ngắt; không sửa log cũ để giả complete.
Checkpoint mới là EXPERIMENT_ONLY_NOT_APPROVED. Baseline full-test/G2 vẫn có phạm
vi riêng, không chứng nhận checkpoint NoPeek. C-01..C-04, GVHD, firmware/BLE/PPK2,
KV260/compile/runtime và đánh giá tấn công không được ký thay hoặc gộp vào grid.

## Hoàn tất ngày30/10 và tổng hợp

Process v2 cũ tiếp tục qua lần hết hạn mức và hoàn tất54/54 run; không resume
hoặc restart trong lượt tiếp tục. Xem [báo cáo hiện hành](sv3_ml_week8_report.md)
và [receipt grid](../ml/provenance/week8-grid-20261029/grid-54-v2.receipt.json).

```powershell
& $py -B ml/scripts/analyze_week8_grid.py --experiment ml/results/week8-nopeek/grid/grid-3seed-joint-v2 --artifacts ml/artifacts/week8-nopeek/grid/grid-3seed-joint-v2 --rule ml/provenance/week8-grid-20261029/candidate-selection-rule.json --output ml/results/week8-nopeek/grid/grid-3seed-joint-v2/review
& $py -B ml/scripts/plot_week8_grid.py --review ml/results/week8-nopeek/grid/grid-3seed-joint-v2/review --output ml/results/week8-nopeek/grid/grid-3seed-joint-v2/figures-final
```

Có54 run/18 tổ hợp mean và sample std(ddof1), candidate lock giữ3 seed mỗi split,
hình ba panel PNG/SVG/PDF và dữ liệu vẽ. Lệnh từ chối ghi đè; tái lập dùng root mới.
Candidate lock không mở quyền đánh giá test: cần protocol test riêng đã khóa
và được cho phép; lượt này không chạy test.
