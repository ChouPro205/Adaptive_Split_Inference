# SV3 tuần 5 — implementation, verification và bàn giao 2026-10-09

`CURRENT WEEK=5`, `REVIEW_STATUS=PENDING`, **TECHNICAL_STATUS=BLOCKED**.
P1 Python, ML reference, accuracy, regression liên quan và preservation PASS.
Không tuyên bố PASS tổng vì chưa có allocation wire model/split được phê duyệt.
Không review tổng thể, merge/main, đổi tuần hoặc triển khai tuần 6.

## Phạm vi thay đổi và nguồn

Nhánh `sv3/week5-technical-20261009`, checkout riêng
`exports/week5-technical-20261009`, nền main
`65d44d2cd159b28cf9bb505a66d39ef67e8dbc19` (fetch ngày 2026-10-09).
Working tree gốc ở `415d53431c81c465784dc08be42b568827a39cff` và các thay đổi
tuần 3 chưa commit của người dùng được giữ nguyên. Không stash/reset/checkout
đè các thay đổi đó. Commit/PR cuối ghi trong `delivery_publication.json`.

Tái sử dụng P1 `ml/src/p1.py` delegate đúng I2/1 và reference lượng tử hóa
`ncl-int8-fp16-v1-review` từ `b73a705`. Không sửa thuật toán hay reference.
Bổ sung `week5_interfaces.py` để serialize scale FP32 LE từ scale FP16 đã lưu,
resolve profile từ ID registry tường minh và từ chối thiếu ID/sai checkpoint,
shape/dtype/layout/axis/buffer. Không suy shape từ payload hoặc cấp ID ngầm.

`test_week5_interfaces.py` kiểm vectors chuẩn, phân đoạn byte a/b, endian và
rejection sampling, lỗi metadata hai chiều, thứ tự unprotect/dequantize và
boundary accuracy. `verify_week5_real.py` kiểm read-only 220 golden pairs, q,
FP16 bits, bytes wire FP32, adapter NC/NCL và tail bit-exact. Runner accuracy
bổ sung gate tự quyết định PASS/FAIL và exit code; giữ nguyên quantization,
checkpoint, preprocessing và dataset. `run_week5_logged.py` lưu command,
source hashes, stdout/stderr/exit code ở vị trí mới; `preserve_week5.py` inventory
read-only; `verify_week5_delivery.py` đối chiếu receipts và không bỏ qua blocker.

[Decision note v1](../../contracts/sv3_week5_decisions_v1.md) là đặc tả quyết định
S6 và lập luận khả nghịch. [Checklist 1.1 cập nhật](../../docs/sv3_week5_scope_checklist_2026-10-09_v1.1.md)
ghi trạng thái từng mục; không đánh dấu người dùng đã học hiểu.

## Các gate

| Gate | Kết quả | Bằng chứng từ Git root |
|---|---|---|
| Python P1 đúng I2/1/ChaCha20, vectors/RFC | PASS | `ml/provenance/week5-20261009-v1/interfaces_final_v2.*`, `i2_existing.*`; 7 tests Python, 5 host Python/C tests lịch sử |
| Khả nghịch và giới hạn P1 | PASS | Decision note; đảo affine modulo256 theo kênh nguồn và đặt ngược permutation |
| Round-trip bit-exact | PASS | `p1_10000.json` (10.000 synthetic, seed 20261005, 16 public keys), `real_220_final_v2.json` (220 thật), tổng **10.220**, 0 tensor lỗi |
| Lặp lại/shape/INT8 biên | PASS | `p1_10000.json`: histogram shape; -128/127, toàn zero/hằng/random, single byte/channel và 32768 B; deterministic protect mỗi case |
| Scale stored FP16 và wire FP32 LE | PASS component | 220 cặp bytes/hash/FP16 bits; wire scale từng kênh mở rộng đúng FP16, tests thường và `-O`; không I1 packet/transport |
| Adapter s9/s10, q→P1→inverse→dequant→tail | PASS test profiles | 20 case mỗi s, cùng q/shape/logits byte-exact; shape trả NC trước tail |
| Model/split registry ML | PASS ML fields | Config FP32 confirmed và `contracts/sv3_week5_ml_registry_v1.json`, đúng checkpoint/cuts/shapes |
| Registry wire deployment | **BLOCKED** | FP32 config `split_id_namespace` không cấp I1 wire IDs; I1 mục 7, I2 mục 3 vẫn thiếu registry deployment; model_profile_id/wire_split_id giữ null |
| Accuracy | PASS | `ml/results/week5-20261009-v1-final/accuracy.csv`, `evaluation.json`, `fp32_gates.json`; đúng 8544 ×11, mọi split <0,5 pp |
| Regression liên quan | PASS | receipts/logs liệt kê dưới đây; các lỗi setup ban đầu được giữ và chạy lại thành công |
| Preservation lịch sử | PASS | 94.518 file gốc và 754 file asset copy khớp raw hash; `preservation_after.json`, `delivery_checked.json` |
| MCU/DPU tuần 5, I1 end-to-end | NOT_RUN | Không suy từ host reference, receipt FP32 tuần 4 hoặc quyết định đã chốt |
| Review người dùng, merge | NOT_RUN | REVIEW_STATUS=PENDING |

P1 synthetic output-stream SHA-256:
`cc83bbdd4c3c43dde1126a5ebaf935112aa911fc69adaff5191ae4176f42f365`,
giống bằng chứng lịch sử tại `b73a705`. 220 real cases dùng registry **PUBLIC_TEST_ONLY**,
explicit wire IDs 101,108,…,171, khác s+1; không phải mapping triển khai được
phê duyệt. Histogram synthetic phủ shape 11 split cùng 6 shape biên; các
shape trùng có count gộp. Real coverage báo riêng mỗi s=0..10 là 20.

## Accuracy đủ 8.544 test frozen

Mỗi split FP32 đúng **8.393/8.544**, accuracy **98,23267790262172%**.
Giảm pp =100×(correct_FP32−correct_INT8)/8544. Tỷ lệ tương đối
=100×(correct_FP32−correct_INT8)/8393. Bảng dưới làm tròn để đọc; gate dùng
integer chính xác `200*(correct_FP32−correct_INT8)<8544`; đúng 0,5 FAIL.

| s | Đúng INT8 / tổng | INT8 % | Giảm pp | Giảm tương đối % | Gate |
|---:|---:|---:|---:|---:|---|
| 0 | 8391/8544 | 98,209270 | 0,023408 | 0,023829 | PASS |
| 1 | 8390/8544 | 98,197566 | 0,035112 | 0,035744 | PASS |
| 2 | 8391/8544 | 98,209270 | 0,023408 | 0,023829 | PASS |
| 3 | 8392/8544 | 98,220974 | 0,011704 | 0,011915 | PASS |
| 4 | 8393/8544 | 98,232678 | 0 | 0 | PASS |
| 5 | 8395/8544 | 98,256086 | -0,023408 | -0,023829 | PASS |
| 6 | 8388/8544 | 98,174157 | 0,058521 | 0,059573 | PASS |
| 7 | 8391/8544 | 98,209270 | 0,023408 | 0,023829 | PASS |
| 8 | 8391/8544 | 98,209270 | 0,023408 | 0,023829 | PASS |
| 9 | 8393/8544 | 98,232678 | 0 | 0 | PASS |
| 10 | 8393/8544 | 98,232678 | 0 | 0 | PASS |

FP32 head+tail với full model cũng PASS strict <1e-3 trên đủ 8544 mẫu ở mọi s.
Predictions 93.984 hàng dữ liệu mới byte-identical với bảng frozen lịch sử;
SHA-256 chung `0776e503b9e404c957cfcfb239356f52b17f34655cb2c5d15fdfe96cb3ae6e56`.
Predictions mới ở thư mục results mới, ignored; bản identical đã có trong ZIP
ML lịch sử. Không tạo ZIP ML revision mới. 20 mẫu là validation golden đúng
identity/order cũ, không dùng đánh giá accuracy. Frozen test giữ 8544 IDs/labels,
4 patient và record 101/122/219/228; class N/S/V/F/Q 8102/13/426/1/2.

## Regression và lệnh đã chạy

Môi trường: Python 3.11.9, NumPy 2.4.6, Torch 2.14.0+cu130,
ONNX 1.23.1, ONNX Runtime 1.30.0; GCC UCRT trên PATH. Inference CPU FP32,
eval/inference_mode, một thread, deterministic, MKLDNN disabled. CUDA không
dùng. Command receipts có executable/path/source hash/elapsed time đầy đủ.

| Kiểm tra | Receipt tại `ml/provenance/week5-20261009-v1/` | Kết quả |
|---|---|---|
| Quantization 6 tests thường và -O | `quantization.command.json`, `quantization_optimized.command.json` | PASS |
| Interface 7 tests thường và -O | `interfaces_final_v2.command.json`, `interfaces_optimized_final_v2.command.json` | PASS |
| Host I2 Python/C 5 tests | `i2_existing.command.json` | PASS; không C port/50-vector tuần 6 |
| Gate hiện tại + R4 scientific regression | `week4_current.command.json` | PASS; 21 tampering rejections, scientific reproduction, 220 goldens nguyên byte |
| Current-source auth 9 tests | `week4_current_tests.command.json` | PASS |
| Release preservation 6 tests | `week4_release.command.json` | PASS |
| SV2 all-split tampering/verification | `week3_sv2.command.json` | PASS legacy bitwise policy |
| SV2 policy 8 tests | `week3_policy.command.json` | PASS |
| Device host handoff 22 tests | `device_handoff_final.command.json` | PASS sau tạo fixture mới tại checkout riêng |
| Checker real MCU capture lịch sử 20 negative cases | `device_capture_final.command.json` | PASS; không đo lại thiết bị/không tạo passing MCU data |
| Cache bổ sung 16 tests | `week3_cache.command.json`, `week3_cache_privileged.command.json` | 15 PASS, 1 SKIP WinError1314 tạo symlink; test mocked symlink guard PASS; không tự bật Developer Mode |

Các lần setup chưa đủ fixture: `device_handoff` và `device_handoff_with_assets`
exit1 do thiếu generated headers; `device_capture` exit2 do thiếu CLI args;
`delivery_precommit` exit1 do thiếu bản copy predictions cũ. Giữ logs nguyên
bản. Fixture/args/copy đã bổ sung trong checkout mới, final receipts PASS.
`delivery_checked` exit2 là **BLOCKED có chủ ý** do registry, không lỗi số học.

Lệnh tái lập từ Git root (chọn paths mới; không chạy export/package/hydrate
đè các asset hiện có):

```powershell
$asiPython = 'C:/Users/Admin/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe'
& $asiPython -B ml/scripts/test_week5_quantization.py
& $asiPython -O -B ml/scripts/test_week5_quantization.py
& $asiPython -B ml/scripts/test_week5_interfaces.py
& $asiPython -O -B ml/scripts/test_week5_interfaces.py
& $asiPython -B contracts/i2_ref/test_i2.py
& $asiPython -B ml/scripts/test_week5_p1.py --cases 10000 --output ml/provenance/week5-new-run/p1_10000.json
& $asiPython -B ml/scripts/verify_week5_real.py --output ml/provenance/week5-new-run/real_220.json
& $asiPython -B ml/scripts/evaluate_week5.py --batch-size 1 --output ml/results/week5-new-run
& $asiPython -B ml/scripts/verify_week4_current.py --regressions
& $asiPython -B ml/scripts/test_week4_current.py
& $asiPython -B ml/scripts/test_week4_release.py
& $asiPython -B ml/scripts/test_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6
& $asiPython -B ml/scripts/test_week3_sv2_policy.py
& $asiPython -B ml/scripts/test_week3_sv2_cache.py
& $asiPython -B device/scripts/generate_week4_inputs.py --generated-dir device/generated
& $asiPython -B device/scripts/test_week4_handoff.py
& $asiPython -B device/scripts/test_week4_capture.py --capture results/week4/logs/week4_capture.txt --work-dir ml/artifacts/week5/new-regression
```

Máy nhận thay `$asiPython` bằng Python trong môi trường dự án đã cài đúng
requirements. Asset nhận dùng release/receipt lịch sử tại
[handoff cũ](sv3_sv1_week5_handoff.md); xác thực hash trước dùng. Fixture header
chỉ tạo nếu `device/generated` chưa tồn tại; giữ bản cũ nếu đã nghiệm thu.
Để có logs mới, bọc mỗi lệnh bằng
`python -B ml/scripts/run_week5_logged.py --output <prefix-moi> -- <command>`.
Logger tự dùng Git safe.directory đúng checkout, không thay config global.

Aggregate cụ thể của đợt này:

```powershell
& $asiPython -B ml/scripts/run_week5_logged.py --output ml/provenance/week5-20261009-v1/delivery-postcommit -- $asiPython -B ml/scripts/verify_week5_delivery.py --original-root C:/Users/Admin/Adaptive_Split_Inference --output ml/provenance/week5-20261009-v1/delivery-postcommit.json
```

Exit2/JSON BLOCKED khi thiếu wire IDs đã chốt; exit1 khi verification lỗi.
Không có PASS tổng nếu registry thực chưa được xác nhận. Receipts kiểm source
đã chạy bằng raw hash; commit nền không thay thế hash source chưa commit.
Receipt postcommit pin commit implementation cuối và đối chiếu tested source
dependencies, không phải tái chạy mọi test. Chi tiết commit/PR ở publication receipt.

## Preservation và bàn giao

Inventory gốc gồm ML packages/goldens/manifest/results/provenance/configs,
dataset raw/processed, lịch sử `exports`, root ZIP/sidecars, và mọi file của
working tree đang thay đổi; loại `.git`, môi trường/cache được ghi rõ trong
script và checkout tuần 5 mới. 94.518 file giữ nguyên, 0 thiếu/đổi byte.
Inventory raw hash `2e9a969fbc01fe91675232369cea35423463126e42daf4f83693de69c22ea4ae`,
versioned lossless gzip trong `preservation_before.json.gz`; 754 file ML/data
copy vào checkout riêng cũng đối chiếu nguyên byte. After inventory canonical
SHA-256 `0676b4198fc9b4140c9f7a838638e04b2b654cc37e7b6f4ed2a8959cd4dba1f6`,
giống trước. Các Git refs/objects mới không thuộc tài sản ML bất biến.

| Tài sản lịch sử | Hash giữ nguyên |
|---|---|
| Checkpoint | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` |
| All-split package manifest | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` |
| Quantization20 manifest | `8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd` |
| Frozen processed ZIP | `b95d169f7cf454f11d21a858f6fee6f526347294f6673874318521a11ae8b0bf` |
| Quantization/reference ZIP | `3105bc879af3c4d9d4eb87725c7d165328649afd1c5dd28fe1786fe66dc4ff7b` |

10 frozen-dataset files và 442 reference/evaluation files khớp receipt release
đã publish từ `b73a705`; note/link clean-checkout ở `415d534` giữ nguyên tại
working tree gốc. Regression khoa học R4 kiểm commit sinh asset `89109fd`,
không relabel R3 MCU capture là R4 hay tuần 5. Không có thêm `.xmodel`/DPU
receipt tuần 5 trong hồ sơ này; model/ONNX/goldens all-split SV2 đã xác thực,
compile/runtime độc lập còn thuộc Trung.

SV1 nhận decision note, metadata ML, accuracy và reference/vectors đã đối chiếu.
Trung nhận API descriptor/active_profile, shape adapters và thứ tự phục hồi,
model/tail/checkpoint/asset anchors. Người dùng tự bàn giao; Codex không gửi
tin nhắn cho họ. Đề xuất wire allocation cụ thể ở decision note **chưa áp dụng**.
Chỉ sau approval registry và rerun các gate mapping thực mới có thể đóng tổng
tuần 5. Không hỏi lại scale, I2 NCL hoặc ngưỡng accuracy đã chốt.
