# Báo cáo tiến độ SV3 Bùi Kỳ Anh tuần 3

**Người thực hiện:** SV3/Bùi Kỳ Anh, phụ trách ML và tham chiếu suy luận.
**Ngày lập:** 05/10/2026, múi giờ Asia/Saigon.
**Chốt bằng chứng:** 05/10/2026 lúc 00:40:29 +07:00; snapshot `origin/main`
`076719a30d4de2304281d718910c4727deed97d3`, sau PR17, PR18 và PR19.
Phạm vi lịch sử là công việc tuần 3 từ 25/09 đến 01/10/2026; các sửa công cụ
bàn giao và kết quả đến thời điểm chốt được ghi riêng để không đổi chronology.

SV3 đã chốt mô hình, bàn giao tham chiếu FP32 cho SV1 và xuất đủ các tail
ONNX cho SV2. Kiểm số học cục bộ đạt 220 ca PyTorch head/tail và 200 ca ONNX;
SV1 có bằng chứng MCU đủ 20 mẫu × 5 mốc. Nghiệm thu độc lập của SV2 trên
Linux/KV260 và ACK chính thức còn thiếu, nên chưa kết luận tuần 3 của toàn
nhóm hoàn tất.

Quy ước trong báo cáo: **YÊU CẦU DỰ ÁN** là tiêu chí từ tài liệu nguồn;
**QUYẾT ĐỊNH TRIỂN KHAI** là lựa chọn đã chốt trong config/contract/code;
**KẾT QUẢ QUAN SÁT** là kết quả có manifest, log hoặc capture đối chiếu.
`PASS` chỉ áp dụng cho phạm vi đã kiểm; `PENDING` là nghiệm thu còn chờ;
`BLOCKED` là có điều kiện cản trở cụ thể; `NOT VERIFIED` là chưa đủ bằng
chứng. Negative test PASS nghĩa là dữ liệu sai bị từ chối đúng lý do.

## 1. Mục tiêu và tiêu chí nghiệm thu

**YÊU CẦU DỰ ÁN.** Hướng dẫn chi tiết, mục A.3, hàng tuần 3 yêu cầu chốt
kiến trúc/số lớp L, xuất trọng số `.h` cho SV1, xuất ONNX cho SV2; tiêu chí
là cả hai thành viên nạp được mô hình và ba bên cho cùng kết quả trên 20
mẫu. Báo cáo triển khai, mục 2.2, đặt mốc accuracy ≥98% và chốt kiến trúc
ở tuần 3; hướng dẫn chi tiết đã đặt accuracy ở tuần 2. Báo cáo này kế thừa
kết quả baseline tuần 2, không nhận đó là một lần train mới của tuần 3.

| Nguồn yêu cầu đã đọc read-only | Vị trí | SHA-256 byte thô |
|---|---|---|
| `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx` | A.3, tuần 2–3 | `75fcd76999af521a568b039c6983414217c59991d37b5591b85d211db927880d` |
| `Huong1_Bao_cao_trien_khai_3SV.docx` | 2.2, tuần 3 | `60f83fa7c0779d11c888a8a104c5fa55be0c8c8b171f9d72e29cbba9efcc9a90` |

Hai bản local có hash khớp [danh sách nguồn yêu cầu versioned](../ml/configs/week4_requirement_references.json).
DOCX không nằm trong Git; các hash định danh bản đã đọc, không tạo một link
tải giả. Quy cách nghiệm thu kỹ thuật được cụ thể hóa trong
[contract SV3–SV1](../contracts/sv3_sv1_week3_model_handoff.md) và
[contract SV3–SV2](../contracts/sv3_sv2_week3_fp32.md): đúng model,
mẫu, shape/layout/dtype; xác thực manifest bằng hash độc lập; mỗi ca MCU
hoặc ONNX FP32 phải có `max(abs(output − reference)) < 1e-3` nghiêm ngặt.
Không suy PASS từ việc PR đã merge hoặc lệnh hướng dẫn có trong README.

## 2. Đầu vào kế thừa và phạm vi SV3

**QUYẾT ĐỊNH TRIỂN KHAI.** Dùng nguyên baseline `mitdb_week2_cnn_v1`,
MIT-BIH/1.0.0, checkpoint epoch 3 đã chọn bằng validation. Mô hình gồm tám
Conv1d và hai Linear, 109.653 tham số; không có BatchNorm/folding. Nguồn
mô hình lịch sử là `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`, khác với commit
bổ sung evidence hoặc commit squash merge.

| Đầu vào khóa | Giá trị và ý nghĩa |
|---|---|
| Full checkpoint | `best_checkpoint.pt` → `model/checkpoint.pt`, 450.551 B; SHA `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` |
| Source định nghĩa mô hình | `ml/src/mitdb_baseline_model.py`; SHA `520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14` |
| Dữ liệu tuần 1 | MLII theo tên; cửa sổ 360 điểm quanh expert R-peak; patient-wise train/val/test; Z-score scalar fit từ train |
| Tensor đầu vào | X `(N,360)` chuyển view thành `(N,1,360)`; float32, không chuẩn hóa lần hai |
| Baseline accuracy lịch sử | Test `98,220974%` (8.392/8.544); validation `84,487913%`; test macro F1 `0,382595`, recall S/F/Q đều 0 |
| Hạn chế dữ liệu tham chiếu | Bộ 20 mẫu dùng để debug số học, không phải test accuracy hoặc đánh giá đủ năm lớp |

Nguồn: [báo cáo tuần 2 giữ nguyên](SV3_ML_week2_report.md),
[manifest run tuần 2](../ml/provenance/week2_run_manifest.json),
[freeze config](../ml/configs/week3_model_freeze.json). Overall accuracy đạt
ngưỡng hình thức nhưng không chứng minh khả năng phân loại tốt lớp thiểu
số hay sử dụng y tế. Tuần 3 không đổi weights, kiến trúc, split bệnh nhân,
normalization hoặc sample selection để cải thiện số liệu đó.

SV3 chịu trách nhiệm freeze, exporter/verifier, checkpoint/code tham chiếu,
weights/header, golden, ONNX và provenance. SV1 port kernel, build/DFU và
thu kết quả nRF52840; SV2 kiểm Vitis AI, quantize/compile và chạy VART/KV260.
PTB-XL vẫn là dữ liệu đã chuẩn bị từ tuần 1, không phải mô hình được train
hay xuất trong bàn giao này. Bảo vệ I2, privacy attack và luồng Device–Edge
không được nghiệm thu bằng các phép so FP32 dưới đây.

## 3. Kiến trúc và cách xác định điểm cắt

**QUYẾT ĐỊNH TRIỂN KHAI.** `L=10` đếm lớp có tham số học, gồm tám Conv1d
và hai Linear; graph thực thi có **25 operations**. ReLU thuộc lớp có học
đứng trước; MaxPool thuộc Conv chẵn đứng trước; Flatten và Dropout ở eval
chuẩn bị Linear thứ nhất trong head từ `s=9`. `s` là số lớp có học trong
head, không phải chỉ số của mọi operation hoặc chiều dài ECG.

Với `z_s=head_s(x)`, tail nhận đúng `z_s` để tạo logits. `s=0` dùng head
identity/tail toàn mô hình; `s=10` dùng head toàn mô hình/tail identity.
Mapping được nhóm xác nhận ngày 01/10, thay trạng thái deferred trong audit
30/09; audit/config cũ được giữ trong `ml/provenance/week3/history/`.

| s | Head kết thúc tại | Shape N=1 | Layout | Tail bắt đầu tại |
|---:|---|---|---|---|
| 0 | Input đã chuẩn hóa, identity | `(1,1,360)` | NCL | `features.0` |
| 1 | `features.1` ReLU1 | `(1,16,360)` | NCL | `features.2` |
| 2 | `features.4` Pool2, P2 | `(1,16,180)` | NCL | `features.5` |
| 3 | `features.6` ReLU3 | `(1,32,180)` | NCL | `features.7` |
| 4 | `features.9` Pool4 | `(1,32,90)` | NCL | `features.10` |
| 5 | `features.11` ReLU5 | `(1,48,90)` | NCL | `features.12` |
| 6 | `features.14` Pool6 | `(1,48,45)` | NCL | `features.15` |
| 7 | `features.16` ReLU7 | `(1,64,45)` | NCL | `features.17` |
| 8 | `features.19` Pool8 | `(1,64,22)` | NCL | `classifier.0` |
| 9 | `classifier.3` ReLU sau Linear1 | `(1,32)` | NC | `classifier.4` |
| 10 | `classifier.4`, logits | `(1,5)` | NC | Identity, không edge compute |

Nguồn authoritative: [config split CONFIRMED tại commit export](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/dd1d4562062202c6721a03a81a7f2cfa29867c00/ml/configs/week3_sv2_interface_review.json).
Tất cả activation là IEEE-754 FP32, little-endian `<f4`, C-contiguous/C-order;
NCL là mẫu–kênh–chiều dài, NC là mẫu–đặc trưng. Conv weights dùng
`(C_out,C_in/groups,K)`; Linear dùng `(out,in)`. Output là logits trước
softmax theo N/S/V/F/Q, argmax nằm ngoài ONNX. Reference `split_id=s` không
tự cấp wire IDs I1; wire ID 0 vẫn được dành riêng trong protocol.

## 4. Bộ 20 mẫu và gói cho SV1

**Công việc và lý do.** Xuất input, bốn mảng weight/bias hai Conv, graph,
checkpoint, source snapshots, C99 header và năm golden để SV1 đối chiếu
đúng từng operation, thay vì chỉ nhận weights rồi tự đoán boundary.
`M_final=P2` được SV3 và SV1 xác nhận riêng trong freeze config.

```text
M0 → Conv1 → M1 → ReLU1 → R1 → Conv2 → M2 → ReLU2 → R2 → MaxPool → P2
```

| Mốc | Shape một mẫu | Payload FP32 một mẫu |
|---|---|---:|
| M0 | `(1,1,360)` | 1.440 B |
| M1, R1, M2, R2 | `(1,16,360)` | 23.040 B/mốc |
| P2 = s2 | `(1,16,180)` | 11.520 B |

Conv1 có weight `(16,1,5)`, Conv2 `(16,16,5)`, hai bias `(16,)`;
kernel 5, stride/dilation/groups 1, zero padding 2 mỗi phía. Pool kernel/
stride 2, không padding, `ceil_mode=false`. Tổng đoạn này là **1.392 FP32
tham số = 5.568 B**, khác payload activation và footprint firmware.
Header `static const float` dùng literal hexadecimal có hậu tố `f` để giữ
bit, không transpose hay fold tham số.

20 mẫu lấy từ validation, sắp numeric record ID → numeric R-peak → lead
name rồi lấy 20 hàng đầu. Các mẫu đều từ P105/record 105/MLII;
`sample_index=0..19` ứng với các R-peak sau, theo đúng thứ tự:

```text
197, 459, 708, 965, 1222, 1479, 1741, 2015, 2287, 2550,
2803, 3052, 3303, 3563, 3835, 4102, 4371, 4635, 4901, 5154
```

ID là `MIT-BIH:105:<r_peak>:MLII`; `inputs.npy[i]`, mọi golden `[i]` và
dòng CSV index i luôn cùng nguồn. Golden giao có batch 20, MCU xử lý N=1.
Không chọn lại mẫu, không thêm normalization; verifier SV1 tái tạo input
từ raw ECG đã khóa rồi recompute golden từ **input đã lưu/nạp lại**.
Nguồn thứ tự/mốc và sửa stride: [review evidence lịch sử](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/7960c47ddc0165307ff245cb46c3327656a3ade6/ml/docs/week3_review_evidence.md).

Gói chính thức SV1 **v2** có 29 file, tổng 2.726.226 B; ZIP 1.602.725 B.
Manifest liệt kê 28 file còn lại, không tự hash chính nó. NPY là định dạng
PC, có header riêng; firmware dùng dữ liệu FP32/header C, không truyền cả
NPY header như tensor. `.h` được xuất chưa tự chứng minh MCU đã chạy.

## 5. Gói all-split FP32 và ONNX cho SV2

**Công việc và lý do.** `export_week3_sv2.py` tái sử dụng checkpoint và
20 mẫu SV1 v2, tạo wrappers head/tail theo mapping đã chốt; xuất 11 golden
`z_s0..z_s10`, `reference_logits.npy` và đúng **10 ONNX** `tail_0..tail_9`.
`z_s0` là input ban đầu, `z_s2` trùng bytes golden P2 SV1, `z_s10` trùng
bytes reference logits. Không tạo `tail_10.onnx` vì tail đó là identity.

ONNX dùng opset **13**, fixed N=1, không dynamic axes/external weights;
input `input_activation`, output `logits` float32 `(1,5)`. Export dùng
TorchScript `dynamo=False` tường minh. Preprocessing/softmax/argmax không
được giấu trong tail. Gói `mitdb-week3-sv2-fp32-20261001-v1` gồm **41 file**,
6.239.715 B; inventory manifest có 40 bản ghi ngoài chính manifest; ZIP
4.507.827 B. Đủ model code/checkpoint/config để SV2 dựng lại tail.

Các file code chính và nhiệm vụ:

| File từ repo root | Vai trò |
|---|---|
| `ml/scripts/week3_common.py` | Freeze/data/hash/layout, load model, tham số/header C và bit comparison |
| `ml/scripts/export_week3.py`, `verify_week3.py`, `test_week3.py` | Bàn giao SV1, raw-derived input, graph/golden và rejection tests |
| `ml/scripts/week3_sv2_common.py` | Canonical split map, wrappers, authentication/inventory và numerical comparisons |
| `ml/scripts/export_week3_sv2.py`, `verify_week3_sv2.py`, `test_week3_sv2.py` | Xuất ONNX, kiểm checker/I/O/weights, 200 ca và mutation tests |
| `ml/scripts/audit_week3_sv2.py` | Audit trước khi interface được chốt; không coi audit provisional là release |
| `ml/configs/week3_model_freeze.json`, `week3_sv2_interface_review.json` | Định danh/checkpoint, consent boundary và mapping đã xác nhận |
| `contracts/sv3_sv1_week3_model_handoff.md`, `sv3_sv2_week3_fp32.md` | Quy cách giao/nhận và phân chia trách nhiệm |
| `ml/provenance/week3/` | Exact manifest, verification, numerical và audit lịch sử |

## 6. Kết quả kiểm chứng và môi trường

Các kết quả sau là **bằng chứng thực thi lịch sử**, không phải chạy lại
training/export trong phiên viết báo cáo. Bằng chứng v2 được version tại
`7960c47`; export/numerical all-split pin source `dd1d456`, được ghi nhận tại
`6e9af10`. Không gán SHA commit lưu evidence thành SHA của một clean run
nếu manifest/log không ghi điều đó.

| Gate | Kết quả quan sát | Nguồn/commit xác định phạm vi |
|---|---|---|
| SV1 v2 release verifier | PASS, external anchor, 20 raw-derived inputs, năm golden bitwise | [v2 verification tại 7960c47](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/7960c47ddc0165307ff245cb46c3327656a3ade6/ml/provenance/week3/mitdb-week3-fp32-20260925-v2.verification.json) |
| SV1 negative suite | 27/27 expected rejections; production package không đổi | Cùng v2 verification và [release report](../ml/docs/week3_release.md) |
| C99 host parameter check SV1 | 1.392/1.392 FP32 bit patterns khớp; GCC 15.2.0 | Cùng v2 verification; không phải nRF52840 |
| Reproduction SV1 v2 | 27 file trùng byte; README/manifest khác vì ID mới | Cùng v2 verification |
| PyTorch head/tail | 220/220, max error 0 ở cả 11 splits | [numerical tại 6e9af10](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/6e9af108b7b0c39d63bc1c8dbbfbf4fcbf89c67e/ml/provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.numerical.json), source dd1d456 |
| ONNX so full-model logits | 200/200 strict `<1e-3`; worst `2.6226043701171875e-6` | Cùng numerical; ONNX Runtime CPU |
| SV2 negative suite | 17/17 expected rejections | [all-split verification tại 6e9af10](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/6e9af108b7b0c39d63bc1c8dbbfbf4fcbf89c67e/ml/provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.verification.json) |
| Reproduction all-split | 39 file trùng byte; README/manifest khác vì ID mới; 10 ONNX và 12 golden files giữ nguyên | Cùng all-split verification |

ONNX worst theo `s=0..9` lần lượt là
`2.62260437e-6, 2.38418579e-6, 2.62260437e-6, 2.02655792e-6,
2.02655792e-6, 2.14576721e-6, 1.90734863e-6, 1.90734863e-6,
1.90734863e-6, 9.53674316e-7`. Global worst đồng hạng tại sample 16,
`MIT-BIH:105:4371:MLII`, s0/s2. s10 có 20 identity cases, không có ONNX
comparison; không cộng chúng thành 220 ca ONNX.

Môi trường: Windows, Python 3.11.9, torch 2.14.0+cu130, NumPy 2.4.6,
pandas 3.0.5, SciPy 1.17.1, WFDB 4.3.1; ONNX 1.23.1, ORT 1.30.0,
protobuf 7.36.2, ml_dtypes 0.6.0, flatbuffers 25.12.19. Tham chiếu split
dùng CPU eval/inference, N=1, deterministic, một thread, MKLDNN disabled;
ORT CPUExecutionProvider, sequential, một intra/inter-op thread,
`ORT_ENABLE_BASIC`. Export SV1 có kiểm lại provenance CUDA tuần 2;
không chuyển kết quả đó thành Linux, DPU hoặc INT8 PASS.

## 7. Review, revision và các lỗi đã xử lý

| Mốc | Vấn đề và cách xử lý | Giới hạn chronology |
|---|---|---|
| Review r1 → r2, 25/09 | r1 sai bit tại M1: 224 phần tử, max `5.960464477539063e-8`; singleton-channel stride đổi sau NPY serialization. Canonicalize và load input thực đã giao trước khi tính golden; r2 giữ bit equality | [Review evidence](../ml/docs/week3_review_evidence.md) ghi lỗi trước official release; không có SHA riêng cho mọi lần thử tiền commit |
| `4d65849bf11cab40f79026f27130fdbe44d82c58` | Freeze/boundary hai bên đã chốt; phát hành SV1 v1 | v1 sau đó bị supersede về assurance, không phát hiện tensor khoa học sai |
| `7960c47ddc0165307ff245cb46c3327656a3ade6` | Sau review SV1: yêu cầu external manifest anchor trước parse, pin model_version, bắt buộc test script; fixtures dtype/NaN/identity/shape đi tới đúng semantic gate; phát hành v2 | Sáu file đổi; 23 file trùng byte, gồm 14 scientific payload files; r2/v1 không sửa tại chỗ |
| Audit 30/09 → `dd1d4562062202c6721a03a81a7f2cfa29867c00`, 01/10 | Interface SV2 ban đầu thiếu quyết định; sau xác nhận nhóm mới chốt mapping/opset và export all-split | `BLOCKED_ON_SV2_INTERFACE` trong tài liệu cũ là trạng thái lịch sử; hiện tại FP32 contract CONFIRMED |
| `6e9af108b7b0c39d63bc1c8dbbfbf4fcbf89c67e` | Ghi manifest/numerical/verification all-split; đối chiếu SV1 capture 20×5 có sẵn | Không phải một phiên đo MCU mới của SV3 |
| `da4bebf06d015b4fce697eef08f97d1e92e086fd`, 01/10 | Sau export v1, SV2 gặp cache `.pyc`: giới hạn exemption ở cache CPython cạnh source được giao; entrypoints tắt bytecode writes; frozen loader compile chính source bytes đã hash | Là sửa công cụ bàn giao tuần 3 sau phát hành; v1 scripts/manifest/ZIP không đổi |
| `89109fd352d84a5fe0815d7e045e52538de7bad8`, 03/10 | Sau đó phát hiện inventory cùng nội dung nhưng Windows/POSIX sort Path khác thứ tự. Sort hai list theo chuỗi path, so nguyên bản ghi và giữ multiplicity | Không dùng dict làm mất duplicate; không gán fix R4 cho lần export 01/10 |

Sửa cache giữ reject file lạ/orphan cache/symlink; `-B` chỉ ngăn ghi cache,
không xóa cache có sẵn và không ngăn đọc bytecode. Cache `.cpython-312.pyc`
còn cho thấy runtime 3.12 khác Python 3.11.9 đã pin; fix không miễn gate
phiên bản. Suite R4 có **15 PASS + 1 SKIP** symlink thật do WinError 1314,
guard mô phỏng PASS; thiếu/thừa/duplicate/hash/size/shape/dtype/anchor sai
vẫn bị từ chối. [Báo cáo tuần 4](sv3_ml_week4_report.md) trình bày đầy đủ
release và clean checkout của các sửa này.

## 8. Bằng chứng SV1 và SV2 hiện tại

**KẾT QUẢ CỦA SV1.** SV1 nhận v2 và kiểm package ngày 28/09: verifier
PASS, 27 rejection tests, inventory 29 file. Firmware đo P2 có commit
`33a5288e475646c80f14a9cfcd2e797db64c5e41`; evidence bổ sung
`f1624f43fc68ef1472005b9edb2b5fc450cb1443`. Lần đầu chỉ trace đủ năm mốc
ở sample 0 và P2 ở 20 mẫu. Capture bổ sung 30/09 đã lấp khoảng trống 20×5,
vào main qua PR15 `bd64c3859e9ce8493e7115285cfbb3dc1f8f3859`.

| Kết quả thiết bị của SV1 | Giá trị |
|---|---|
| Trace đủ 20 mẫu × 5 mốc | 100/100 tensor PASS, đúng 20 IDs/thứ tự |
| Worst M1/R1 | `4.76837158203125e-7` |
| Worst M2/R2 | `9.5367431640625e-7` |
| Worst P2 | `7.152557373046875e-7`, 20/20 strict `<1e-3` |
| Capture 20×5 SHA-256 | `72c7b6a2ba554f7e6d242a49e20065a4b56a3967108206a9a4d8845f1e795606` |
| Image P2 tuần 3 | Flash 84.072 B, RAM linker 64.248 B; hai activation buffers 46.080 B; main stack high-water 544/4.096 B |

Nguồn: [SV1 report tại PR15](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/bd64c3859e9ce8493e7115285cfbb3dc1f8f3859/docs/sv1_device_week3_report.md),
[JSON 20×5](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/bd64c3859e9ce8493e7115285cfbb3dc1f8f3859/results/week3/week3_mcu_validation_20x5.json),
[CSV sai số](../results/week3/week3_milestone_errors_20x5.csv).
SV3 kiểm lại capture đã lưu và đối chiếu hash, không nhận công port/DFU/đo
dongle của SV1. Kết quả SV1 tuần 4 mới nhất cũng xác nhận P2 bitwise 20/20
với MCU tuần 3; đó là evidence bổ sung sau tuần 3.

**TRẠNG THÁI SV2.** Nhánh `origin/dev/edge-sv2` mới nhất là
`881f3c1ebfb41425f4ee65ccb3c6f97a03dcc301`, có báo cáo tuần 2. Báo cáo
[SV2 tuần 2](sv2_edge_week2_report.md) ghi thử ResNet18,
chưa chạy board; đây không phải nghiệm thu ECG all-split. Không thấy
report/log Linux full verifier hoặc ACK SV2 mới hơn trong nguồn đã kiểm.
PR17/18/19 không có comment ACK tại thời điểm chốt. Thiếu evidence không
cho phép kết luận SV2 chưa từng làm ngoài repo.

## 9. Deliverables và cách nghiệm thu

| Deliverable | Định danh/trust anchor | Nguồn công khai và cách kiểm |
|---|---|---|
| SV1 v2 | Manifest `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469`; ZIP `d5511f8c5ebfb1e9eced4aea2f8e89a20dd142b79987a40f6a3347d33d7481eb` | [Exact manifest](../ml/provenance/week3/mitdb-week3-fp32-20260925-v2.manifest.json), [release/commands](../ml/docs/week3_release.md); binary ngoài Git, clone riêng chưa đủ |
| SV2 all-split v1 | Manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`; ZIP gốc `b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7` | [Exact manifest](../ml/provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.manifest.json), [audit/numerical](../ml/docs/week3_sv2_split_audit.md); nguyên folder 41 file còn được giao trong ZIP R3/R4 |
| Source verifier đã sửa | Export/fix `89109fd`; bàn giao `3055bc4`; đã vào main qua PR18 `23b2b7d` | [Release R4](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week4-r4-20261003), [hướng dẫn nhận](../ml/docs/sv3_sv1_week4_handoff_r4.md); không thay scripts bên trong v1 |
| Evidence thiết bị | SV1 capture/JSON/CSV với IDs, shape, bit FP32, hash và firmware provenance | [Kết quả tuần 3](../results/week3/week3_mcu_validation_20x5.json); nghiệm thu per sample/milestone |

Người nhận xác thực ZIP/size và anchor từ checkout/kênh tin cậy độc lập
trước khi hydrate; chạy verifier từ trusted source checkout với anchor
tường minh, kiểm file/identity/layout, bit parameters/goldens rồi mới dùng
kết quả số học. SV1 v2 raw-derived verification cần dữ liệu tuần 1 đã khóa;
SV2 standalone FP32 chỉ cần gói all-split và dependencies đúng pin, không
cần raw dataset/GPU. Commands đầy đủ trong các handoff được liên kết ở
bảng; chúng là hướng dẫn tái kiểm, không phải lệnh vừa chạy trong phiên này.

## 10. Trạng thái nghiệm thu và kết luận có điều kiện

| Tiêu chí | Trạng thái tại thời điểm chốt | Bằng chứng/điều kiện còn thiếu |
|---|---|---|
| Freeze kiến trúc/checkpoint/L | PASS | Epoch 3, L=10, hashes và hai boundary confirmations |
| Baseline accuracy ≥98%, <250k params/<1 MB | PASS trong phạm vi baseline | Kế thừa tuần 2; không nhận là robust five-class |
| Xuất `.h`/gói SV1, raw-derived/golden/C bits | PASS | v2 verification và package acceptance SV1 |
| SV1 chạy đúng 20 mẫu, đủ năm mốc | PASS | Capture thực 20×5 tại PR15; không còn chỉ sample 0 |
| ONNX/FP32 all-split, 200 comparisons | PASS cục bộ Windows CPU | Source dd1d456, evidence 6e9af10; không phải DPU |
| Interface FP32 của SV2 | PASS về quyết định | Mapping/opset/tensor semantics CONFIRMED ngày 01/10 |
| Full verifier trên máy Linux SV2 | PENDING | Chỉ WSL Path probe và mô phỏng POSIX; chưa có log đủ numerical suite |
| Môi trường WSL của probe chạy full verifier | BLOCKED tại probe lịch sử | Python 3.12.3, thiếu môi trường/dependency pin 3.11.9; không suy trạng thái mọi máy Linux |
| SV2 nạp/chạy ECG trên VART/KV260; ba bên độc lập khớp 20 mẫu | PENDING | Chưa có nghiệm thu máy SV2/xmodel/DPU |
| ACK chính thức SV2; ACK bàn giao R3/R4 của SV1 | PENDING | Máy SV1 có kết quả kỹ thuật, report ghi ACK `DRAFT_NOT_SENT`; chưa thấy ACK đã gửi |
| Sign-off nghiệm thu toàn phạm vi của GV | NOT VERIFIED | Merge PR không thay văn bản nghiệm thu |

Phần SV3 tuần 3 đã hoàn thành tham chiếu FP32 có xác thực và tái lập;
SV1 đã hoàn tất số học MCU 20×5. Toàn bộ tiêu chí “cả SV1/SV2 nạp được,
ba bên cùng kết quả” vẫn chờ evidence SV2. Các lỗi cache/inventory đã sửa
trong source hiện có trên main, nhưng giữ nguyên artifact v1/v2 và trạng
thái lịch sử trong receipts. Đây là kết luận tiến độ có điều kiện, không
tuyên bố toàn dự án DONE hoặc triển khai tuần tiếp theo.

Phiên lập báo cáo chỉ đọc Git/docs/manifest/log, kiểm hash và số học bảng;
không retrain, export, chạy full ML suite, flash hay đo thiết bị mới.
Git và tài liệu không chứa toàn bộ chat/thử nghiệm bỏ dở của agent trước;
những phần thiếu evidence không được dựng lại bằng suy đoán. Xem thêm
[báo cáo tuần 4](sv3_ml_week4_report.md) và [mục lục bốn tuần](README.md).
