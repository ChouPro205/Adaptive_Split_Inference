# SV3 tuần 8 — protocol NoPeek v1 đề xuất

Ngày 29/10/2026. Trạng thái: **PROPOSED, chưa duyệt train dài**.
Nguồn triển khai khởi đầu: `d851e8621ee35e3e5da6451ca9c229094d147780`.
Source mới chưa commit được định danh bằng SHA-256 trong từng experiment.

## Phạm vi và lựa chọn cần chốt

Loss `CE + lambda1 × R_n(x,z_s)` dùng lại dCor biased sample tuần 7,
không phải R². Grid cố định s2/s5/s8 × {0, 0.1, 0.5, 1, 2, 5}, tức 18 run/seed.
Không thay smoke tuần 7, frozen checkpoint/reference/manifest hoặc registry.

| Tham số | Đề xuất v1 | Quyết định còn cần |
|---|---|---|
| Seeds | [20261021], 18 run | Một seed cho lượt đầu; hoặc [20261021,20261022,20261023], 54 run, có biến thiên giữa seed |
| Model được train | Chỉ head; tail frozen, eval, gradient CE vẫn truyền qua tail về head | Chốt head_only hoặc head_and_tail; smoke tuần 7 train cả hai; không trộn hai scope trong cùng so sánh |
| Batch | 32 cho train và validation dCor | Batch ảnh hưởng estimator; giữ nguyên giữa các lambda/split |
| Optimizer | Adam lr=1e-4, betas=(0.9,0.999), eps=1e-8, weight_decay=0; không scheduler | Chốt cấu hình |
| Epoch/early stop | Tối đa 30; patience=5 epoch không giảm CE | Epoch 1..30 đủ điều kiện chọn, epoch0 không tham gia chọn; min_delta=0 |
| Chọn checkpoint | CE trung bình trên validation thấp nhất, bằng nhau chọn epoch sớm nhất | Chốt quy tắc trước grid |
| Mất cân bằng | CE không trọng số, shuffle train; không resampling/augmentation | Giữ loss đúng cấu hình hiện có; ghi F1/recall; weighted CE là protocol riêng nếu muốn |
| Compute | FP32, CPU 4 threads, deterministic, MKLDNN off, TF32 off | Có thể chọn CUDA trước grid bằng config mới; không đổi device khi resume |

Config CPU là `ml/configs/week8_nopeek_protocol_v1.json`; biến thể CUDA đã pilot
là `ml/configs/week8_nopeek_protocol_v1_cuda.json`. Cả hai đều `PROPOSED`.
Gói lựa chọn sau pilot: ưu tiên CUDA/head_only và ba seed để có biến thiên;
nếu cần lượt thăm dò chi phí thấp hơn, dùng một seed và công bố giới hạn đó.
Đây là đề xuất cần người phụ trách/GVHD chốt, không phải quyết định đã phê duyệt.

Một seed chỉ mô tả một lần khởi tạo/shuffle, không ước lượng độ biến thiên giữa seed.
Ba seed tăng khoảng ba lần chi phí. Không dùng kết quả pilot để chọn lambda.
Nếu chọn head_and_tail, dropout của tail bật khi train, tắt khi validation.
Với head_only, dropout thuộc tail luôn eval; không vô tình làm frozen tail ngẫu nhiên.
Không áp ngưỡng accuracy tuần 9–10 làm gate mới cho tuần 8.

## Dữ liệu và khởi tạo

Checkpoint gốc `ml/data/week2/mitdb_baseline/best_checkpoint.pt`, epoch3,
SHA-256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Mọi tổ hợp đều deep-copy lại baseline này, tạo optimizer và seed mới;
không tiếp nối trọng số của lambda/split khác.

`load_train_val` xác thực model source/checkpoint, config, processed manifest,
patient manifest, normalization và cả sáu artifact train/val trước khi dùng.
Chỉ kiểm patient assignment test từ manifest; không mở test arrays/metadata.
Input MLII `[B,1,360]`, normalization frozen fit train, không fit lại.
Các bindings đầy đủ lưu trong `data-audit.json` và `identity.json` của pilot/grid.

| Split dữ liệu | Mẫu | Bệnh nhân/record | N/S/V/F/Q |
|---|---:|---|---|
| train | 81094 | 34/35 | 69215/1275/5927/790/3887 |
| validation | 15388 | 7/7 | 13003/1493/876/11/5 |

Validation F/Q chỉ 11/5 mẫu, nên recall có biến thiên lớn. Không suy chất lượng
toàn bộ lớp từ accuracy tổng. Patient sets không giao nhau. IDs, row indices
và class labels của phần dùng thực tế lưu trong `selected_samples.json`.
Full grid dùng toàn bộ train/val với thứ tự validation frozen không đổi giữa mọi run.
Train shuffle xác định bởi `(seed,epoch)`, drop_last=True: 81088 mẫu/epoch,
6 mẫu cuối permutation không được dùng trong epoch đó. Validation dùng đủ15388 mẫu;
480 batch32 + một batch28, không bỏ lớp hiếm ở cuối.

dCor báo trung bình có trọng số theo số mẫu của từng batch, không phải dCor
toàn dataset. Nếu validation có batch cuối một mẫu thì chỉ loại mẫu đó khỏi dCor,
vẫn tính CE/accuracy/F1/confusion/recall; log cả `samples` và `dcor_samples`.
Điều kiện batch/order được lưu để các so sánh có nghĩa.

## Pilot và kiểm thử

Pilot riêng: s2/s5/s8 × lambda {0,0.5} × seed20261021, hai epoch,
512 train và256 validation chọn deterministic không lặp từ frozen train/val.
Không phải grid18 run; không dùng metrics subset cho lựa chọn candidate.
Đi trọn train → validation → chọn/lưu checkpoint → nạp lại và xác thực metrics.
Các bài kiểm mới kiểm CE-only, gradient/mode, tail frozen, validation thuần,
strict-CE/tie, checkpoint reload, gián đoạn/chạy tiếp và từ chối evidence/config sai.
Các tests tuần7 bảo vệ công thức/loader và được chạy lại trên source hiện tại.

## Trạng thái, resume và bảo toàn kết quả

Results: `ml/results/week8-nopeek/{pilot,grid}/<experiment>/`.
Checkpoint: `ml/artifacts/week8-nopeek/{pilot,grid}/<experiment>/`, bị ignore theo `.pt`.
Mỗi experiment có config, source snapshot/hash, HEAD nền, môi trường,
data bindings/IDs, inventory và status. Mỗi run có history, summary và status
`NOT_STARTED/RUNNING/COMPLETED/FAILED/INTERRUPTED`.
Snapshot source chỉ chứa mã kỹ thuật đã chỉ định, không chép receipt lịch sử.

Mặc định từ chối output/artifacts đã tồn tại. `--resume` chỉ dùng đúng experiment,
source/config/IDs/môi trường đã khóa; xác thực inventory và completed checkpoints.
Lock độc quyền cả hai root ngăn hai process ghi cùng experiment/checkpoint.
`last.pt` là progress checkpoint atomic ở cuối mỗi epoch, gồm optimizer/RNG,
history và early-stopping counter. Gián đoạn giữa epoch: lặp lại epoch đó từ
checkpoint cuối đã lưu, cùng permutation/RNG; không nối run khác.
`best-epoch-NNN.pt` giữ nguyên theo epoch, không ghi đè.

Giới hạn: kill cứng có thể để lại `.lock`; phải kiểm process trước khi xử lý lock.
Nếu crash đúng giữa lưu best mới và cập nhật last, runner từ chối ghi đè orphan
best, yêu cầu bảo toàn file đó rồi đối chiếu thủ công hoặc dùng experiment mới.
Không hứa phục hồi tự động mọi hư hỏng/ổ đĩa đầy. Checkpoint mới luôn
`EXPERIMENT_ONLY_NOT_APPROVED`, chưa có deployment profile/version/golden mới.

## Lệnh tái lập từ worktree

PowerShell, môi trường đã có ở checkout gốc:

```powershell
$py = (Resolve-Path ../../ml/.venv/Scripts/python.exe).Path
& $py -B ml/scripts/test_week7_nopeek.py
& $py -B ml/scripts/test_week8_nopeek.py
& $py -O -B ml/scripts/test_week8_nopeek.py
& $py -B ml/scripts/run_week8_nopeek.py --mode pilot --output ml/results/week8-nopeek/pilot/pilot-v1 --artifacts ml/artifacts/week8-nopeek/pilot/pilot-v1
& $py -B ml/scripts/summarize_week8_nopeek.py --experiment ml/results/week8-nopeek/pilot/pilot-v1 --artifacts ml/artifacts/week8-nopeek/pilot/pilot-v1 --output ml/results/week8-nopeek/pilot/pilot-v1/analysis
# Pilot CUDA đã kiểm riêng, cùng subset/seed, giữ root khác:
& $py -B ml/scripts/run_week8_nopeek.py --config ml/configs/week8_nopeek_protocol_v1_cuda.json --mode pilot --output ml/results/week8-nopeek/pilot/pilot-cuda-v1 --artifacts ml/artifacts/week8-nopeek/pilot/pilot-cuda-v1
& $py -B ml/scripts/summarize_week8_nopeek.py --experiment ml/results/week8-nopeek/pilot/pilot-cuda-v1 --artifacts ml/artifacts/week8-nopeek/pilot/pilot-cuda-v1 --output ml/results/week8-nopeek/pilot/pilot-cuda-v1/analysis
```

Khi tái lập, chọn tên experiment mới. Đường dẫn pilot-v1 là evidence đã chạy,
không ghi đè. Grid chưa được phép với config `PROPOSED`.
Sau khi có quyết định thực tế, lưu một config đã khóa mới, ghi authority/evidence
đúng nguồn; không sửa config/identity của pilot đã chạy. Không tự ký thay GVHD.

```powershell
& $py -B ml/scripts/run_week8_nopeek.py --mode grid --config ml/configs/<approved-config>.json --output ml/results/week8-nopeek/grid/<new-experiment> --artifacts ml/artifacts/week8-nopeek/grid/<new-experiment>
# Chạy tiếp đúng experiment, không đổi source/config/device:
& $py -B ml/scripts/run_week8_nopeek.py --mode grid --config ml/configs/<approved-config>.json --output ml/results/week8-nopeek/grid/<new-experiment> --artifacts ml/artifacts/week8-nopeek/grid/<new-experiment> --resume
```

Exporter kiểm inventory, source snapshots, config/IDs, checkpoint hash và
metrics/selection bindings trước khi xuất CSV/JSON + PNG/SVG ba panel.
Pilot/partial được ghi nhãn; không nối qua tổ hợp thiếu để giả đường cong đầy đủ.
Nhiều seed báo mean ± sample std; một seed không có ước lượng biến thiên.
CE/dCor/macro-F1/confusion/recall đầy đủ lưu theo run, cùng best epoch/checkpoint SHA.
Candidate chỉ được chọn khi grid đã đủ theo quy tắc validation đã chốt.
Test evaluation là bước riêng sau khóa candidate; không dùng test để tuning,
calibration, chọn lambda, checkpoint hoặc early stopping.

## Ranh giới kết luận và phối hợp

Full-test baseline đã đạt `PASS_ACCURACY_GATE` và artifact đã review ngày29/10;
không còn mục chờ SV2 gửi25.632 output. Kết quả đó không chứng nhận NoPeek mới.
dCor giảm, smoke/pilot PASS và accuracy không chứng minh privacy hoặc differential privacy.
P2/decoder/GAN/tái định danh/adaptive attacker/Π/Pareto/controller thuộc giai đoạn sau.
SV1 giữ firmware/BLE/PPK2; SV2 giữ KV260/compile/runtime; SV3 giữ model/privacy.
C-01..C-04 và nghiệm thu GVHD được theo dõi riêng trong báo cáo tuần8;
không ký hoặc xác nhận thay người phụ trách.
