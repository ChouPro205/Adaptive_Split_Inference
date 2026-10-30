# Demo SV3 tuần 7 — dCor, gradient và loss NoPeek

Mục tiêu: trình bày và chạy phần toán/wiring trong khoảng 5–10 phút.
Runbook đã được chạy thử trên commit
`08e4b4259a2757be7b663b88cc1c98607602d266`. Kết quả kiểm thử xác minh toán/wiring;
hoạt động demo với GVHD được ghi nhận riêng. Không chạy grid dài, cập nhật model hoặc dùng test để học.

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

Nội dung trao đổi/demo: batch axis và flatten, R so với R², bias mẫu hữu hạn,
vì sao gradient dCor tới head, vì sao λ=0 trở về CE và vì sao metric này không
thay đánh giá tấn công. Kết quả buổi demo được ghi trong hồ sơ nghiệm thu riêng;
runbook và log kiểm thử là tài liệu chuẩn bị.

## 5. Lượt kiểm host 28/10/2026 và cách trình bày với GVHD

[Evidence mới](../ml/provenance/week7-host-20261028/README.md) ghi commit thực
chạy và output `demo.json` mới của lượt chạy kiểm thử; không gán lại lượt chạy cũ.
Lệnh này chỉ forward/backward, **không optimizer step**, 32 train IDs, không
test inference; hash trạng thái model trước/sau phải khớp. Để tự demo, dùng
output mới như `.cache/week7-demo-kyanh-01.json` theo §2.

Trình bày trong 5–10 phút:

1. Nêu mục tiêu: CE giữ thông tin phân lớp, λ·dCor tạo gradient phạt phụ thuộc
   giữa ECG x và activation z; λ=0 trở về CE. Inference không cần tính dCor.
2. Chỉ bốn ca toán trong output: self≈1, independent nhỏ nhưng dương, nonlinear
   square vẫn có phụ thuộc, constant=0 theo chính sách suy biến. Giải thích R
   có căn cuối, khác R²; bias mẫu hữu hạn phụ thuộc batch và số chiều.
3. Chỉ rows s2/s5/s8: CE, dCor, total và gradient head. Kiểm
   `gTotal−gCE≈0.5·gdCor`, gradient dCor khác 0 và weights unchanged. Bảng này
   không chọn λ/split tối ưu hoặc chứng minh model đã học tốt hơn.
4. Phân biệt P1 đảo được trên INT8 với regularizer NoPeek. dCor thấp không là
   chứng minh chống reconstruction/attribute attacks; phần đó để thiết kế sau.
5. Nêu kết quả hệ thống đã có: G2 200/200 so cùng backend. Accuracy DPU độc lập
   vẫn cần 8.544 mẫu/split, baseline 8.393 và ≥8.351 correct, đủ coverage.

Câu tự kiểm trước buổi gặp: vì sao noise độc lập không ra đúng 0, batch axis
là gì, gradient đến head qua đường nào, và vì sao G2 PASS không suy accuracy
DPU PASS? Dùng các câu hỏi này khi trình bày; kết quả trao đổi/demo và quyết định
review ML được ghi riêng theo quy trình nghiệm thu của nhóm.
