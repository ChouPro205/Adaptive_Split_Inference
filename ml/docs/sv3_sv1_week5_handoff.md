# SV3 → SV1: gói tuần 5, Python lượng tử hóa và P1

**Cập nhật 2026-10-09:** S6 đã chốt INT8 per-channel/FP16 stored scale,
FP32 LE wire expansion, I2 NCL và gate accuracy strict <0,5 pp.
[Hồ sơ mới](week5_technical_20261009.md) và
[decision note v1](../../contracts/sv3_week5_decisions_v1.md) ghi trạng thái
verification hiện hành. Các mô tả cần review phía dưới là hồ sơ lịch sử của
release 2026-10-05, giữ nguyên để không đổi provenance hay gói đã nghiệm thu.
Tổng tuần 5 hiện BLOCKED vì chưa cấp registry wire; REVIEW_STATUS=PENDING.

Gói dành cho SV1 review bản tham chiếu `ncl-int8-fp16-v1-review`. Đã đánh giá đủ
8.544 mẫu test chính thức, không retrain/fine-tune, không đổi checkpoint,
kiến trúc, preprocessing, split hay thứ tự nhãn. Cùng checkpoint trên CPU FP32;
chỉ activation tại điểm cắt được lượng tử hóa. P1 không nằm trong bảng accuracy.

## Nguồn chuẩn và trạng thái

- `main` nền: `9bce483ddbf3be2ca471e522833352ab18331736` (fetch ngày 2026-10-05).
- R4 vào main qua PR #18: `23b2b7d3fa152fcc50296a93ff592b42e00af943`.
- R4 sinh artifact tại `89109fd352d84a5fe0815d7e045e52538de7bad8`;
  receipt bàn giao R4 pin `3055bc403ea752f20699c454d67fdfafaada08b2`.
- Checkpoint: `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/model/checkpoint.pt`,
  450.551 byte, SHA-256 `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
- Model `mitdb_week2_cnn_v1`: 8 Conv1d + 2 Linear, 25 leaf ops, 109.653 parameters;
  unchanged `ml/src/mitdb_baseline_model.py` / source model trong package.
- Anchor package all-split: `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.

| Đầu ra | Trạng thái, bằng chứng |
|---|---|
| Loader test/checkpoint/head+tail | Hoàn thành; `week5_common.load_test`, `baseline`, `wrappers`; hash/membership/patient leakage PASS |
| Lượng tử hóa Python | Hoàn thành; 6 kiểm thử số học/byte; cần SV1 review để chốt cho C |
| 20 mẫu × 11 split | Hoàn thành 220 cặp; bytes + FP16 bits, manifest; không phải tập test accuracy |
| Accuracy toàn bộ test | Hoàn thành 8.544 mẫu × 11 split; mọi split giảm <0,5 pp |
| P1 Python I2/1 | Hoàn thành; tái sử dụng reference đã chốt, 10.000 deterministic và bit-exact round trips |
| Host I2 Python/C hiện có | 5 tests PASS; chỉ kiểm reference lịch sử, không thay gói 50 vector tuần 6 |
| Checkout sạch | Hoàn thành tại `b73a705461ceea2618f42d39184dda25e227efe5`; tải/hydrate public assets, 220 entries và accuracy/predictions byte-identical, P1 10.000 checksum-identical; `receiver_checks.json` |
| C P1 và 50 vector Python/C mới | Theo lịch tuần 6; chưa bàn giao trong tuần 5 |
| Device/Edge integration | Chưa đánh giá; cần registry deployment, key_id/sender scope, nonce bền qua reboot, buffer/transport do SV1/SV2 chốt |

Hai ZIP đã publish lên kho Releases hiện có và được tải lại qua URL công khai,
SHA/size khớp. Receipt và link tải nằm trong
`ml/provenance/week5/external_assets.json`.
PR cần SV1 review, không tự merge. Host PASS không thay nghiệm thu Dongle/KV260.
PR: [#20](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/20).
Các commit cập nhật receipt/docs sau source release không thay mã đã kiểm
trên checkout sạch. Đây là mô phỏng local máy nhận, chưa phải ACK của SV1.

## Danh sách tài nguyên và môi trường

| Đường dẫn | Nội dung |
|---|---|
| `ml/src/quantization.py` | `quantize_per_channel`, `dequantize_per_channel`, adapter NC↔NCL |
| `ml/src/p1.py` | Entry point API I2/1 nguyên bản: `Profile`, `descriptor`, `protect`, `unprotect` |
| `contracts/i2_protection_v1.md`, `contracts/i2_ref/` | I2/1 SV1 đã chốt, ChaCha20 và vector chuẩn; không sửa |
| `ml/scripts/week5_common.py` | Xác thực R4, loader full test, mapping, provenance |
| `ml/scripts/evaluate_week5.py` | FP32 gate đủ test trước đánh giá INT8/FP16 |
| `ml/scripts/export_week5.py` | Xuất đúng 20 `sample_id` từ `samples.csv` cũ |
| `ml/scripts/test_week5_quantization.py`, `test_week5_p1.py` | Numerical contract và P1 10.000 tensor |
| `ml/scripts/package_week5.py`, `hydrate_week5.py` | ZIP/hash/inventory và tải/đặt file ngoài Git |
| `ml/results/week5/` | `accuracy.csv`, `accuracy.md`, `evaluation.json`, `fp32_gates.json`, `dataset_manifest.json`, `split_mapping.json` |
| `ml/provenance/week5/` | Commands/logs, P1 seed/count/checksum, asset manifests/receipts |
| `ml/artifacts/week5/quantization20/` | 440 raw binary files và `manifest.json`, ngoài Git |
| `ml/results/week5/predictions.csv` | 93.984 dự đoán theo s/sample_id/label/patient/record, trong ZIP ngoài Git |

Đã chạy Python 3.11.9, NumPy 2.4.6, PyTorch 2.14.0+cu130 (inference CPU),
pandas 3.0.5. R4 imports cần ONNX 1.23.1, ONNX Runtime 1.30.0,
protobuf 7.36.2, ml_dtypes 0.6.0, flatbuffers 25.12.19. Dùng môi trường
`ml/requirements-core.txt` + `ml/requirements-cpu.txt` hoặc
`ml/requirements-gpu-cu130.txt`, và `ml/requirements-week3-onnx.txt` như R4.
Host I2/C test dùng GCC `C:/msys64/ucrt64/bin/gcc.exe` trên máy này.

## Dataset chính thức

MIT-BIH Arrhythmia Database 1.0.0; lead MLII chọn theo tên; không lọc,
không resample (native 360 Hz). Nhịp lấy từ expert annotation, 180 mẫu
trước + 180 mẫu sau R peak, bỏ nhịp sát biên. Z-score dùng duy nhất
thống kê train (`mean=-0.2912026352134608`, `std=0.45653058276514263`).
Label N/S/V/F/Q = 0/1/2/3/4. Input lưu FP32 `[N,360]`, loader cấp
FP32 `[N,1,360]`; label INT64. `sample_id` giữ quy tắc lịch sử
`MIT-BIH:<record>:<r_peak_sample>:<lead>` và nguyên thứ tự metadata.

Train 81.094 mẫu, validation 15.388, test 8.544. Test N/S/V/F/Q =
8.102/13/426/1/2; record 101/122/219/228, patient P101/P122/P219/P228.
`dataset_manifest.json` ghi mọi phân bố lớp, danh sách patient/record của
ba tập và dataset/config/split/normalization/processed hashes. Loader kiểm
toàn bộ artifacts của ba tập và ràng buộc bằng đúng provenance checkpoint;
không trùng patient, gồm nhóm 201/202 cùng bệnh nhân theo metadata chính thức.
Patient IDs là pseudonym công khai sẵn có, không tạo identity thay thế.

## Đặc tả lượng tử hóa cần SV1 review

Chưa có đặc tả INT8 per-channel/scale FP16 đã chốt trong repository.
Tuần 5 dùng yêu cầu hiện tại làm reference cần SV1 review. Tài liệu
`I2_SV3_provisional_interface.md` chỉ dẫn lịch sử PR #7; dùng I2/1 hiện hành.
Các đề xuất NTC/scale FP32 cũ không quyết định byte export tuần này.
I1 v1 hiện mô tả scales FP32 little-endian và cấm transformed payload;
FP16 ở đây là **file reference offline**, không tự đổi metadata I1 hay
gửi I2 qua I1 v1. I1 v2 vẫn là proposal, chưa coi là giao thức được duyệt.

API lượng tử hóa nhận ndarray FP32 NCL `[N,C,L]`, trả q INT8 cùng shape
và scale `<f2` `[N,C]`. Dongle N=1; batch N>1 vẫn lấy max abs trên L
riêng từng n,c. Zero-point 0; miền q `[-127,127]` (khác miền byte P1
có thể gồm -128). Dtype max abs/division ban đầu là FP32:

1. `maxima=max(abs(z), axis=2)`; `scale_raw=maxima/float32(127)`.
2. Kênh zero: scale FP16=1, q=0. Kênh khác zero: floor raw scale tới
   `float32(finfo(float16).smallest_normal)=2^-14=0.00006103515625`.
3. Reject NaN/Inf và scale_raw >65504; cast scale sang IEEE binary16,
   rồi đọc chính giá trị đã lưu về FP32 làm `scale_effective`.
4. `q=clip(rint(z/scale_effective),-127,127).astype(int8)`; nearest
   ties-to-even: ±0,5 → 0; +1,5 → +2; -1,5 → -2.
5. Dequantize `float32(q)*float32(scale_fp16_read)[...,None]`; reject
   scale nonfinite, zero/negative/subnormal, shape/dtype sai hoặc q=-128.

Tham chiếu [NumPy rint](https://numpy.org/doc/stable/reference/generated/numpy.rint.html)
và [NumPy finfo](https://numpy.org/doc/stable/reference/generated/numpy.finfo.html).
Raw q C order, byte offset `((n*C+c)*L+l)`, two's complement signed byte;
scale IEEE binary16 little-endian, offset `2*(n*C+c)`. Không có header trong
`.i8.bin`/`.scale.f16le.bin`; shape/file SHA nằm trong manifest JSON UTF-8 LF.
`scale_uint16_bits` là giá trị integer của bit pattern little-endian,
không phải giá trị scale chuyển sang integer. Dequantized checksum là raw
`<f4` C order; FP32 golden cũ chỉ được dẫn đường, không xuất lại.

s0 vẫn là normalized input qua identity head, full model tail. s9/s10
giữ NC theo mapping R4; adapter thêm L=1 trước quantize, bỏ L=1 trước tail.
Mỗi channel NC có một scale; s10 tail identity trên pre-softmax logits.
Không remap split s: I2 descriptor yêu cầu split_id khác 0, nên test P1
dùng `s+1` **chỉ trong test profile**, không phải wire/deployment registry.

## Lệnh tái lập từ repo root

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week5_quantization.py
& ml/.venv/Scripts/python.exe -B ml/scripts/export_week5.py
& ml/.venv/Scripts/python.exe -B ml/scripts/evaluate_week5.py --batch-size 1
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week5_p1.py --cases 10000
$env:CC='C:/msys64/ucrt64/bin/gcc.exe'
& ml/.venv/Scripts/python.exe -B contracts/i2_ref/test_i2.py
& ml/.venv/Scripts/python.exe -B ml/scripts/package_week5.py
```

Các lệnh export/evaluate/package từ chối ghi đè; trên máy đã có kết quả,
truyền `--output <folder-moi>` cho export/evaluate. `--batch-size 64` hỗ trợ
scale độc lập từng mẫu; kết quả chính thức tuần này dùng N=1. Gate FP32
strict `<1e-3` chạy mọi split và mọi mẫu trước quantization. Mode eval,
inference_mode, CPU FP32, one thread, deterministic, MKLDNN disabled.

P1 giữ nguyên IETF ChaCha20 counter=0, key32/nonce12, descriptor28,
Fisher–Yates rejection, affine modulo256 theo kênh nguồn và API I2/1.
Test seed 20261005, 16 public test keys, 10.000 tensor; mọi shape thật s0..10
sau adapter, single byte/channel, C=256 và payload 32.768 byte,
INT8 -128/127, zero/all-equal/random; deterministic protect và inverse
bit-exact. Hàm transform thuần không quản lý nonce reuse/persistence.
Round-trip là bằng chứng correctness Python, không chứng minh bảo mật.

## Tải tài nguyên ngoài Git

R4 giữ nguyên ở [release R4](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week4-r4-20261003).
Artifact ZIP tên `mitdb-sv1-week4-fp32-20261001-r4.zip`, 5.659.076 byte,
SHA-256 `0b29c1f0bd1327efdf5cad17d0dcfd40fb76cb9d8f7dce3ee8dc5ab4c25dfd8e`.
Tải [ZIP R4](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/download/sv3-week4-r4-20261003/mitdb-sv1-week4-fp32-20261001-r4.zip),
kiểm `Get-FileHash -Algorithm SHA256`, hydrate bằng API `release_week4.hydrate`
với trusted `ml/provenance/week4-r4/deliverables.json` như hướng dẫn R4.
ZIP có checkpoint, model/config, 20 inputs/golden và ONNX; không cần thay source.

Hai ZIP mới chứa dữ liệu frozen và comparison/predictions được đặt ngoài Git
tại [release tuần 5](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week5-v1-20261005),
pin source `b73a705461ceea2618f42d39184dda25e227efe5`.
`external_assets.json` có URL thực đã download verification, SHA-256,
size, version và đường đặt từng file; không dùng link dự kiến làm receipt.
Dataset ZIP chứa 10 processed artifacts cả ba tập để existing loader kiểm
leakage và hashes; không đổi/nhân bản/chia lại dữ liệu. Archive member hashes
là raw bytes; hash CSV/JSON của loader vẫn theo LF-normalized policy tuần 1.

```powershell
Get-FileHash ml/provenance/week5/external_assets.json -Algorithm SHA256
# Authenticate manifest hash từ commit bàn giao/trusted channel trước khi chạy.
& ml/.venv/Scripts/python.exe -B ml/scripts/hydrate_week5.py --expected-manifest-sha256 3fe550cbd3311825c7def1e2a6bb891032d0dd27ffe3990ced9f36451ee6d3ab
```

Hydrator kiểm archive SHA/size và mọi member trước ghi; chỉ hydrate data,
quantization20 và predictions, không ghi đè file khác bytes. Metadata/key
thật, firmware P1 và nghiệm thu thiết bị là phần ngoài gói host tuần 5.

| ZIP đã tải lại và xác minh | Bytes | SHA-256 | Đường đặt nội dung |
|---|---:|---|---|
| [mitdb-frozen-processed-week5-v1.zip](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/download/sv3-week5-v1-20261005/mitdb-frozen-processed-week5-v1.zip) | 33098461 | `b95d169f7cf454f11d21a858f6fee6f526347294f6673874318521a11ae8b0bf` | `ml/data/processed/mitdb/` |
| [sv3-week5-quantization-reference-v1.zip](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/download/sv3-week5-v1-20261005/sv3-week5-quantization-reference-v1.zip) | 807817 | `3105bc879af3c4d9d4eb87725c7d165328649afd1c5dd28fe1786fe66dc4ff7b` | `ml/artifacts/week5/quantization20/`, `ml/results/week5/predictions.csv` |

## Accuracy đầy đủ và mapping

FP32 8.393/8.544 = 98,232678%. Worst drop s6: 0,058521 pp; mọi s
strict <0,5 pp. s5 tăng accuracy nên giữ drop âm. Xem bảng đầy đủ trong
`ml/results/week5/accuracy.md` và CSV chưa làm tròn. Các kết quả gắn main nền,
checkpoint SHA, dataset manifest, quantization version, môi trường, command
và source hashes lúc chạy; `source_git_commit_at_execution` không tự nhận
là commit bàn giao khi source còn chưa commit. Không suy kết quả từ 20 mẫu.

| s | Điểm cắt | Shape thực N=1 | C | Axis | Elements | Scales | Tail |
|---:|---|---|---:|---:|---:|---:|---|
| 0 | normalized_model_input (identity head) | [1, 1, 360] | 1 | 1 | 360 | 1 | wrappers(model, 0)[1]; full_model |
| 1 | features.1 | [1, 16, 360] | 16 | 1 | 5760 | 16 | wrappers(model, 1)[1]; remaining_frozen_ops |
| 2 | features.4 | [1, 16, 180] | 16 | 1 | 2880 | 16 | wrappers(model, 2)[1]; remaining_frozen_ops |
| 3 | features.6 | [1, 32, 180] | 32 | 1 | 5760 | 32 | wrappers(model, 3)[1]; remaining_frozen_ops |
| 4 | features.9 | [1, 32, 90] | 32 | 1 | 2880 | 32 | wrappers(model, 4)[1]; remaining_frozen_ops |
| 5 | features.11 | [1, 48, 90] | 48 | 1 | 4320 | 48 | wrappers(model, 5)[1]; remaining_frozen_ops |
| 6 | features.14 | [1, 48, 45] | 48 | 1 | 2160 | 48 | wrappers(model, 6)[1]; remaining_frozen_ops |
| 7 | features.16 | [1, 64, 45] | 64 | 1 | 2880 | 64 | wrappers(model, 7)[1]; remaining_frozen_ops |
| 8 | features.19 | [1, 64, 22] | 64 | 1 | 1408 | 64 | wrappers(model, 8)[1]; remaining_frozen_ops |
| 9 | classifier.3 | [1, 32] | 32 | 1 | 32 | 32 | wrappers(model, 9)[1]; remaining_frozen_ops |
| 10 | classifier.4 | [1, 5] | 5 | 1 | 5 | 5 | wrappers(model, 10)[1]; identity |
