# SV3 → Trung/SV2: input/reference accuracy DPU, 28/10/2026

Trạng thái: **READY_FOR_TRANSFER_NOT_SENT**. Gói đã được chuẩn bị cục bộ; chưa
gửi, chưa xác nhận Trung đã nhận, chưa có nghiệm thu DPU.

Nguồn frozen:
`.cache/week7-reconcile/accuracy-8544-delivery/` trong checkout tiếp nối.
Manifest SHA-256:
`612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c`.
Generation commit `08e4b4259a2757be7b663b88cc1c98607602d266`.
Không chạy lệnh `prepare` ở hồ sơ cũ cho lần bàn giao này.

Gói được kiểm rồi đóng tại:
`.cache/week7-sv2-handoff-20261028-r1/sv3-week7-frozen-reference.zip`.
SHA/size ZIP và từng member ở
[handoff-receipt.json](../ml/provenance/week7-host-20261028/handoff-receipt.json).
Gói có manifest gốc, 8 file dữ liệu/reference (295.210.600 byte) và bản sao
byte-identical của [output template](../ml/provenance/week7-reconcile-20261026/dpu-output.template.json).
ZIP không đưa vào Git. Kỳ Anh chuyển gói/receipt qua kênh nội bộ đã thống nhất;
Trung kiểm SHA ZIP, giải vào thư mục mới rồi kiểm manifest SHA và toàn inventory
trước khi đọc NPY. Giữ reference cho so sánh, không dùng test/reference để
calibrate, train, chọn checkpoint hoặc tune runner.

Lệnh đóng gói đã dùng (output phải mới nếu cần chạy lại):

```powershell
$py = 'C:/Users/Admin/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe'
& $py -B ml/scripts/package_week7_reference.py --output .cache/week7-sv2-handoff-20261028-r1
```

Trung dùng native **root GraphRunner CPU+DPU**, model xmodel đã pin, lần lượt
đọc `inputs_s2.npy` `[8544,16,180]`, `inputs_s5.npy` `[8544,48,90]`,
`inputs_s8.npy` `[8544,64,22]`. Axis đầu theo `samples.csv`; mỗi row một input
batch 1. Đây là FP32 sau wire INT8/FP16 được giải lượng tử sẵn; không
normalize/quantize wire lần hai, không cần P1/BLE. Internal requantization dùng
fix_point/DPU_ROUND thật của adapter, ghi policy; không gọi backend là DPU-only.

Điền **bản sao** template bằng output thật: 25.632 row keyed bởi
`sample_id, split_point_s`, không duplicate/unknown IDs. Mỗi row OK có 5 raw
logits hữu hạn theo N,S,V,F,Q; argmax chọn index nhỏ nhất khi hòa. Timeout/lỗi
giữ row với status/reason thật và logits null, không bỏ mẫu hoặc điền reference.
Null/rows rỗng của template cố ý không đủ điều kiện nghiệm thu.

Provenance cần board/runtime/source commit, runner/plugin SHA, policy
quantize/layout/copy/fallback, xmodel từng split, quant_info và compile log
SHA **cùng artifact bytes/logs**, calibration provenance/20 IDs val và golden
hashes đã điền sẵn. Không cần gửi lại IDs/bảng/profile đã có; bổ sung đúng
lineage quantize→compile→execution và output full-test. Gửi cả inventory raw
outputs, lệnh thực chạy, timestamps, failures và checksum; không đưa khóa bench
vào JSON/repo. Giữ model hashes hiện hành, không relabel model khác vào profile.

SV3 kiểm provenance/artifacts trước khi chạy trên host, từ root checkout:

```powershell
& $py -B ml/scripts/week7_dpu_accuracy.py evaluate --reference .cache/week7-reconcile/accuracy-8544-delivery --outputs .cache/sv2-output-real.json --output .cache/week7-dpu-received-new/evaluation.json
```

Thay input bằng file đã nhận thật; output phải mới. Exit 0 chỉ khi mọi split
đầy đủ và đạt accuracy gate; exit 1 hoặc provenance bị từ chối không là nghiệm
thu. Gate baseline **8.393/8.544**, minimum **8.351 correct/split** và đủ **8.544**
mẫu/split; missing/failure luôn `INCOMPLETE_NO_ACCEPTANCE`. Logit error chỉ mô tả,
không dùng ngưỡng FP32 `<1e-3` cho DPU. G2 200/200 và 87/100 agreement không
thay full-test này. Kỳ Anh/Trung/GVHD giữ quyền nghiệm thu numeric theo nhóm.
