# Demo SV3 tuần 7 — dCor, gradient và loss NoPeek

Mục tiêu: Kỳ Anh tự chạy và giải thích phần toán/wiring trong khoảng 5–10 phút.
Runbook đã được Codex chạy thử trên commit
`08e4b4259a2757be7b663b88cc1c98607602d266`; **chưa xác nhận Kỳ Anh đã học hiểu
hoặc đã demo với GVHD**. Không chạy grid dài, cập nhật model hoặc dùng test để học.

## 1. Ý chính trước khi chạy

NoPeek học representation bằng `L = CE + λ·dCor(x,z_s)`: CE giữ tín hiệu phân lớp,
dCor tạo thêm gradient để giảm sự phụ thuộc đo được giữa input x và activation z.
P1 là bước đảo được trên INT8 khi truyền; P1 không phải dCor và không tham gia
loss này. Inference phân lớp không cần tính dCor trên từng mẫu.

dCor đang dùng là **R_n biased**, không phải R²; khoảng cách Euclid, flatten các
chiều ngoài batch, double centering và căn cuối. Finite-sample bias làm noise
độc lập vẫn cho số dương; không áp một ngưỡng noise 1D cho ECG 360 chiều/batch 32.

## 2. Lệnh demo ngắn

Từ root worktree mới, dùng môi trường Python đã có torch/numpy/pandas/wfdb và
model/data frozen đúng hash. Máy hiện tại dùng:

```powershell
$py = 'C:/Users/Admin/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe'
& $py -B ml/scripts/demo_week7_nopeek.py --output .cache/week7-demo-review-01.json
```

Chọn tên output mới nếu đã tồn tại. Script authenticate model, đọc train/val
bằng loader tuần 7, chỉ lấy **32 mẫu train đầu**; không đọc test và không có
optimizer step. Hash tensor trạng thái model trước/sau phải trùng.

Kết quả đã chạy thử, xem [delivery-demo.json](../ml/provenance/week7-reconcile-20261026/delivery-demo.json):

| Ca toán | dCor xấp xỉ | Ý nghĩa cần giải thích |
|---|---:|---|
| `dCor(x,x)` | 1 | Tự phụ thuộc, x không hằng |
| Hai noise 1D độc lập, n=1024, seed 7 | 0.05144817 | Gần 0, không buộc đúng 0 ở mẫu hữu hạn |
| x và x² | 0.53698142 | Đo phụ thuộc phi tuyến |
| Một phía hằng | 0 | Chính sách suy biến của implementation |

| Split, cùng 32 train IDs | CE | dCor | λ | Total | ‖gCE‖ head | ‖gdCor‖ head |
|---|---:|---:|---:|---:|---:|---:|
| s2 | 0.08828842 | 0.99594069 | 0.5 | 0.58625877 | 0.64295381 | 0.09781700 |
| s5 | 0.08828842 | 0.84865558 | 0.5 | 0.51261622 | 0.95790291 | 1.38511527 |
| s8 | 0.08828842 | 0.78113514 | 0.5 | 0.47885600 | 0.98904383 | 1.63017738 |

Số float có thể lệch nhỏ theo môi trường. `lambda0_is_CE_tensor=True`, gradient
dCor khác 0/hữu hạn, `gTotal−gCE ≈ 0.5·gdCor`, residual quan sát tối đa
`1.3038516e-7`, và `weights_unchanged=True`. Đây là forward/backward baseline
eval mode, không phải kết quả training mới hay đường hội tụ.

## 3. Kiểm toán học/gradient hiện có nếu cần trình diễn chi tiết

Không viết lại test toán hoặc đổi tolerance. Dùng các ca đã có từ implementation
`6be51e3` (source hiện tại khớp theo reuse receipt):

```powershell
& $py -B ml/scripts/test_week7_nopeek.py DistanceCorrelationTests.test_independent_reference_and_not_squared DistanceCorrelationTests.test_constant_rows_zero_gradients_and_extreme_finite DistanceCorrelationTests.test_gradcheck_first_derivatives_both_inputs ObjectiveTests.test_lambda0_exact_loss_gradient_update ObjectiveTests.test_positive_lambda_gradient_difference_is_privacy
```

Mong đợi **5 tests OK**: reference độc lập và R khác R²; suy biến và gradient
hữu hạn; gradcheck; λ=0 khớp CE/loss/gradient/Adam; λ>0 thêm đúng gradient dCor.
Đây là lệnh sẵn sàng cho người dùng chạy; nhiệm vụ lần này tái sử dụng evidence
19/19 lịch sử, không gán lệnh 5 tests này thành lượt kiểm đã chạy mới.

## 4. Giới hạn kết luận và điều kiện ghi nhận demo

- dCor thấp hoặc gradient hoạt động **chưa chứng minh privacy**. Cần train đủ,
  threat model và decoder/GAN/attribute/adaptive attack ở giai đoạn sau.
- P1 dùng public vector chỉ kiểm tính đảo được/semantics, không chứng minh bảo
  mật vận hành. Không provision public key này cho bench hoặc deployment.
- Smoke 4 bước cũ chỉ kiểm wiring; bảng demo mới không dùng để chọn λ hoặc
  so accuracy. Accuracy DPU trên test 8.544 và BLE/E2E là các gate riêng.

Trước khi đánh dấu đã học hiểu/demo, Kỳ Anh cần tự giải thích: batch axis và
flatten, R so với R², bias mẫu hữu hạn, vì sao gradient dCor tới head, vì sao
λ=0 trở về CE và vì sao metric này không thay đánh giá tấn công. GVHD/người
nghiệm thu ghi nhận sau buổi thực tế; runbook và log do Codex chạy không thay
việc đó.
