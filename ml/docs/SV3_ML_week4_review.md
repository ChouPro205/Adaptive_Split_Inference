# SV3 ML — Week 4 Review

**WEEK 4 STATUS: PASS — phần SV3 offline đã hoàn thành.** Review này được tạo
sau implementation, verifier, tampering/reproduction tests và regression Week
1–3 đều PASS. Không phải thông báo toàn nhóm đã hoàn thành hardware Week 4.

## 1. Mục tiêu Week 4

Trong `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx`, bảng SV3, hàng tuần 4
yêu cầu: “Profiling kích thước tensor trung gian mọi s → Figure 2” và “Kiểm
tra tính không đơn điệu”. `Huong1_Bao_cao_trien_khai_3SV.docx`, hàng tuần 4,
cũng giao SV3 profiling kích thước tensor mọi s để tạo Fig. 2. Lộ trình, bài
4.1–4.2, giải thích công thức kích thước và biểu đồ. Ba file nguồn thực tế đã
đọc nằm trong `ml/docs/project_sources/requirements/`; raw hashes nằm trong
[manifest Week 4](../results/week4/manifest.json), trường `project_requirements`.

SV3 lấy model frozen, chạy head tại từng điểm cắt, ghi shape/payload, phân
tích tăng giảm, tạo figure và cấp reference/parameters cho SV1. SV1 port head
và đo nRF52840. SV2 xử lý tail trên FPGA độc lập. SV3 có thể chạy toàn bộ phần
offline bằng checkpoint và inputs đã có, vì vậy không cần chờ SV2 acceptance.

Tài liệu minh họa có pseudo-code `list(model.children())[:s]` và host timing.
Model thực tế có hai container lớn features/classifier, nên code minh họa đó
không thể dùng để đánh số 10 learned layers. Tuần này dùng executable mapping
Week 3 đã được xác nhận, và không tạo timing host hoặc giả t_dev(s).

## 2. Trạng thái đầu vào từ Week 3

Source of truth mới nhất là [contract SV3–SV2](../../contracts/sv3_sv2_week3_fp32.md),
[interface config CONFIRMED](../configs/week3_sv2_interface_review.json), commit
`dd1d456` và [evidence handoff](week3_sv2_split_audit.md), được ghi lại ở HEAD
`6e9af108b7b0c39d63bc1c8dbbfbf4fcbf89c67e`. Branch hiện tại là
`sv3/week3-sv2-fp32-handoff`; các thay đổi Week 4 còn local, chưa commit.

| Đầu vào | Quyết định đã xác minh |
|---|---|
| Model revision | `mitdb_week2_cnn_v1`, MIT-BIH/1.0.0, selected epoch 3 |
| Checkpoint gốc | `ml/data/week2/mitdb_baseline/best_checkpoint.pt` |
| Checkpoint sử dụng | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/model/checkpoint.pt`, cùng SHA-256 |
| Frozen architecture source | `ml/src/mitdb_baseline_model.py`, cùng source/hash với model packaged Week 3 |
| Split version | `sv3-sv2-week3-fp32-v1`, L=10, s=0..10 |
| SV1 accepted handoff | `mitdb-week3-fp32-20260925-v2`, P2 sau `features.4` |
| All-split FP32 package | `mitdb-week3-sv2-fp32-20261001-v1`; 11 goldens và 10 ONNX đã tồn tại |
| 20 mẫu | Cùng CSV/sample_index 0..19 đã chọn Week 3; không chọn lại |
| C header Week 3 | Chỉ Conv1/Conv2 + bias; cần mở rộng thành full model cho Week 4 |
| SV1 Week 3 | Recheck capture đã lưu: 100/100 tensor, 20×5 PASS |
| SV2 independent acceptance | Pending Vitis AI/xmodel/VART/KV260; không block SV3 offline |

Checkpoint raw SHA-256:
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Frozen model source SHA-256:
`520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14`.

Các audit/review cũ còn ghi interface blocked hoặc SV1 trace thiếu là lịch sử;
không dùng chúng để phủ nhận config/contract CONFIRMED và capture mới đã có.
Không sửa historical manifests hoặc trường historical `onnx_status` trong
freeze config để “khớp” trạng thái mới. Chứng cứ hiện tại được ghi riêng.

## 3. Kiến trúc model và ý nghĩa split point

Model gồm 8 Conv1d, mỗi Conv theo sau bởi ReLU; sau Conv2/4/6/8 có MaxPool1d.
Channels đi qua `1→16→16→32→32→48→48→64→64`; length `360→180→90→45→22`.
Sau đó Flatten, Dropout(eval), Linear `1408→32`, ReLU, Linear `32→5` logits.
Class order cố định N/S/V/F/Q; output chưa softmax, argmax ở ngoài model.

**L=10** là số lớp có learned weights: tám Conv và hai Linear. Nó không phải
length ECG 360 hay tổng 25 operations. **s** là số learned layers trong head.
`head_s` chạy phần đầu trên thiết bị; `tail_s` chạy phần còn lại ở edge;
`z_s = head_s(x)` là tensor tại boundary. Để edge tiếp tục tính đúng, thiết
bị phải truyền z_s theo shape/layout đã chốt. Vì vậy numel của z_s quyết định
logical payload, không phải số weights hoặc kích thước checkpoint.

s=0: head identity, z_0=input đã normalized, tail=full model. s=10: head=full
model, z_10=logits, tail identity. ReLU thuộc learned layer trước; Pool thuộc
Conv chẵn trước. s=8 vẫn là NCL, còn Flatten/Dropout chuẩn bị Linear1 nằm trong
head s=9. Dropout ở eval là identity. P2 milestone Week 3 nghĩa là Pool sau
Conv2, không phải implementation cơ chế bảo vệ P2.

## 4. Những file/code Week 4 đã thêm hoặc sửa

Các script mới đều trong `ml/scripts/`, không sửa code khoa học Week 1–3.

- [week4_common.py](../scripts/week4_common.py): các hàm dùng chung. Input là
  authenticated package Week 3, model và 20 inputs. `frozen()` kiểm tra hashes
  và config authority; `profile()` chạy mỗi head trên từng sample N=1 trong
  eval/no_grad; `graph_parameters()` dùng hooks trên full forward để ghi 25
  ops và lấy 20 parameter arrays; `analysis()` tính chênh lệch/ratio/max/min.
  Output là dữ liệu registry, graph, weights, CSV và figure. Không tự tạo
  split numbering; dùng lại wrappers/CUTS của Week 3.
- [profile_week4.py](../scripts/profile_week4.py): exporter. Input là repo
  frozen; output là thư mục mới `ml/results/week4/`. Nó xuất profile,
  parameters/header, compile-check, figure và manifest. Từ chối overwrite;
  không train, chuẩn hóa lại hoặc sinh duplicate golden. INT8 chỉ tính numel.
- [verify_week4.py](../scripts/verify_week4.py): verifier. Input là output
  folder, repo và **independently trusted manifest SHA-256**. Output PASS chỉ
  khi hash/inventory, execution profile, full-forward graph, bitwise goldens,
  parameters và compiled C bits đều khớp. Full-model logits/predictions được
  kiểm tra với frozen reference. Không tự nới tolerance.
- [test_week4.py](../scripts/test_week4.py): test tampering/reproduction. Input
  là gói đã xác thực; nó sửa **bản sao trong temp**, thử 18 corruption cases,
  chạy exporter vào thư mục mới và so toàn bộ 28 file byte-for-byte. Output
  gồm reason-specific rejections, 4 trường hợp phân loại monotonic và kết quả
  reproduction; không sửa gói thật. Semantic fixtures dùng trust anchor riêng
  của test để kiểm tra nội dung sau khi hashes đã khớp.
- [run_week4_regressions.py](../scripts/run_week4_regressions.py): input là
  repo/artifacts lịch sử; output là 18 logs và summary mới dưới provenance
  Week 4. Chạy các verifier/test có sẵn, fail-fast, snapshot 280 file và so
  trước/sau. Không chạy download/build/normalization-fit/training, và không
  ghi lại manifests Week 1–3.
- [tensor_profile.json](../results/week4/tensor_profile.json): **registry mở
  rộng của canonical mapping Week 3**, không tạo một numbering thứ hai. Input
  là execution profile; output mỗi s có boundary/head-last/tail-first,
  shape/layout/numel, FP32 actual và INT8 estimated bytes/KiB, cùng analysis.
- [tensor_profile.csv](../results/week4/tensor_profile.csv): cùng số liệu JSON
  ở dạng bảng; input registry, output chia sẻ cho SV1. Có cột s để join số đo
  thiết bị thật về sau, chưa có cột timing giả.
- [model_graph.json](../results/week4/model_graph.json): full-forward hook
  execution và live module attributes tạo ra 25 op specs, input/output shapes,
  parameter paths/checkpoint keys/layout. SV1 cần nó vì weights một mình chưa
  mô tả được ReLU, Pool, Flatten và Dropout.
- `ml/results/week4/weights/{module_path}.{weight,bias}.npy`: 20 arrays
  float32 lấy trực tiếp từ checkpoint, gồm cả bias. Input parameters frozen,
  output C-order không fold, không transpose, không hạ precision. Exact paths
  và shapes nằm trong model_graph và manifest.
- `ml/results/week4/firmware/head_parameters.h`: cùng arrays được viết thành
  C99 hex-float literals và shape/count constants. Input graph/weights, output
  C header đầy đủ; không phải firmware run_head. [host_c_verification.json](../results/week4/firmware/host_c_verification.json)
  ghi GCC/flags và kiểm tra bit patterns sau compile; đây là host sanity check.
- [tensor_size_vs_split.pdf](../results/week4/tensor_size_vs_split.pdf) và
  [PNG](../results/week4/tensor_size_vs_split.png): input registry thực, output
  figure vector và preview. Marker/nét khác nhau để đọc được khi in đen trắng.
- [manifest.json](../results/week4/manifest.json): input tất cả artifact/source
  metadata; output raw hashes, shapes/dtypes/logical bytes, 41 reused Week 3
  file bindings, sample order và dependency versions. Phân biệt file_size_bytes
  với logical_tensor_bytes. generation_command là template cho thư mục mới;
  lệnh export thực tế đã chạy được ghi ở phần 10 bên dưới.
- [verification.json](../provenance/week4/verification.json),
  [test_execution.json](../provenance/week4/test_execution.json),
  [week4_tests.txt](../provenance/week4/week4_tests.txt) và
  [regressions/summary.json](../provenance/week4/regressions/summary.json): input
  là kết quả command thực sự đã chạy; output bằng chứng PASS, hashes của logs,
  reproduction và historical-file preservation. Các logs `.txt` được summary
  trỏ chính xác, không thay historical provenance.
- `ml/provenance/week4/sv1_week3_capture_recheck.{json,csv}`: input capture
  Week 3 hiện có và SV1 v2; output recheck riêng, không ghi đè báo cáo SV1.
  Không phải một lần chạy MCU mới và không chứa t_dev(s) Week 4.
- `.gitignore`: thêm exclusions cho generated weights và full C header theo
  binary/model-artifact policy hiện tại. Các profile/figure/evidence nhỏ vẫn
  có thể version trong Git. Những ZIP/report unrelated ban đầu được giữ nguyên.
- [sv3_sv1_week4_handoff.md](sv3_sv1_week4_handoff.md) và review này: chỉ tạo
  sau PASS. Input là artifact/evidence đã nghiệm thu; output hướng dẫn sử dụng
  và giải thích cho SV1/sinh viên. Receipt `ml/provenance/week4/deliverables.json`
  ghi hashes của output cuối cùng, kể cả docs; không tự hash receipt vào chính nó.

## 5. Bảng canonical split

N=1 cho mọi row; dtype actual là float32. NCL ở s=0..8, NC ở s=9..10.
“—” ở head s=0 nghĩa là identity, ở tail s=10 nghĩa là identity.

| s | Boundary | Head last | Tail first | Shape N=1 | Numel | FP32 B | INT8 estimated B |
|---|---|---|---|---|---:|---:|---:|
| 0 | normalized_model_input (identity head) | ? | features.0 | (1, 1, 360) | 360 | 1440 | 360 |
| 1 | features.1 | features.1 | features.2 | (1, 16, 360) | 5760 | 23040 | 5760 |
| 2 | features.4 | features.4 | features.5 | (1, 16, 180) | 2880 | 11520 | 2880 |
| 3 | features.6 | features.6 | features.7 | (1, 32, 180) | 5760 | 23040 | 5760 |
| 4 | features.9 | features.9 | features.10 | (1, 32, 90) | 2880 | 11520 | 2880 |
| 5 | features.11 | features.11 | features.12 | (1, 48, 90) | 4320 | 17280 | 4320 |
| 6 | features.14 | features.14 | features.15 | (1, 48, 45) | 2160 | 8640 | 2160 |
| 7 | features.16 | features.16 | features.17 | (1, 64, 45) | 2880 | 11520 | 2880 |
| 8 | features.19 | features.19 | classifier.0 | (1, 64, 22) | 1408 | 5632 | 1408 |
| 9 | classifier.3 | classifier.3 | classifier.4 | (1, 32) | 32 | 128 | 32 |
| 10 | classifier.4 | classifier.4 | ? | (1, 5) | 5 | 20 | 5 |

`numel = product(shape_n1)`, `bytes_fp32 = numel × 4`,
`bytes_int8_estimated = numel × 1`. KiB = bytes/1024, không phải bytes/1000.
Ví dụ s=2: `1×16×180=2880` phần tử, `11520 B=11.25 KiB` FP32,
`2880 B=2.8125 KiB` INT8 lý thuyết. File golden chứa 20 samples, nên tensor
bytes của file đó lớn gấp 20 lần payload per inference; NPY header không tính.

## 6. Phân tích tensor size

**NON_MONOTONIC=true.** Không có transition bằng nhau. Max=23.040 B tại
s=1 và s=3; min=20 B tại s=10. Max/min=1152 lần, nhưng ratio payload này
không chứng minh split nào tốt nhất về latency/energy.

| Transition | Thay đổi FP32 | Ratio B(s+1)/B(s) | Nguyên nhân trong graph thật |
|---|---:|---:|---|
| 0→1 | +21.600 B | 16 | Conv1 tăng channels 1→16, giữ length 360 |
| 1→2 | −11.520 B | 0.5 | Conv2 giữ 16 channels; Pool2 giảm 360→180 |
| 2→3 | +11.520 B | 2 | Conv3 tăng channels 16→32, length 180 |
| 3→4 | −11.520 B | 0.5 | Pool4 giảm 180→90 |
| 4→5 | +5.760 B | 1.5 | Conv5 tăng channels 32→48, length 90 |
| 5→6 | −8.640 B | 0.5 | Pool6 giảm 90→45 |
| 6→7 | +2.880 B | 4/3 | Conv7 tăng channels 48→64, length 45 |
| 7→8 | −5.888 B | 22/45 | Pool8 floor: length 45→22; không ceil |
| 8→9 | −5.504 B | 1/44 | Flatten giữ 1408 phần tử; Linear1 giảm 1408→32 |
| 9→10 | −108 B | 5/32 | Linear2 giảm 32→5 logits |

Những bước tăng ở 0→1, 2→3, 4→5, 6→7 là channel expansion thực sự. Pool
tạo các bước giảm xen kẽ; riêng Pool8 reduction factor là 45/22≈2.045, không
chính xác 2. Linear1 giảm 44 lần. ReLU và Dropout(eval) không đổi shape;
Flatten chỉ đổi cách biểu diễn, không giảm số phần tử. Kết luận tự tính trong
JSON và verifier recompute, không suy đoán từ hình. Không có warning giảm
đơn điệu ở model này; nếu xảy ra, code yêu cầu báo GV và giữ model frozen.

## 7. Bộ 20 mẫu và golden output

Reuse toàn bộ `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/golden/`.
`samples.csv` giữ sample_index 0..19, sample_id `MIT-BIH:105:197:MLII` đến
`MIT-BIH:105:5154:MLII` theo đúng order Week 3. Selection đã được chốt từ
Week 3 bằng sort record ID/r_peak/lead rồi first 20; tuần này không chọn lại.

CSV hash `4a6356312d5f62da6b2fdf9e609843d4dea3fc5c20767e201ea21a075e6f227c`;
input hash `dac1d1e9df849bf4ffa30359384d129586f67ec0703157b692d1344685b78dcc`.
Các file này byte-identical với accepted SV1 v2. `z_s2.npy` cũng byte-identical
với P2 accepted; `z_s10.npy` cùng bytes với `reference_logits.npy`.

| File | Shape batch 20 | Layout |
|---|---|---|
| `golden/z_s0.npy` | (20, 1, 360) | NCL |
| `golden/z_s1.npy` | (20, 16, 360) | NCL |
| `golden/z_s2.npy` | (20, 16, 180) | NCL |
| `golden/z_s3.npy` | (20, 32, 180) | NCL |
| `golden/z_s4.npy` | (20, 32, 90) | NCL |
| `golden/z_s5.npy` | (20, 48, 90) | NCL |
| `golden/z_s6.npy` | (20, 48, 45) | NCL |
| `golden/z_s7.npy` | (20, 64, 45) | NCL |
| `golden/z_s8.npy` | (20, 64, 22) | NCL |
| `golden/z_s9.npy` | (20, 32) | NC |
| `golden/z_s10.npy` | (20, 5) | NC |

Mọi golden float32 `<f4`, finite, C-contiguous. Verifier chạy **từng sample
N=1** qua frozen PyTorch, rồi ghép 20 rows lại và so bitwise cho mọi s:
220/220 cases PASS. Nó kiểm tra s=0=input, s=10=full-model logits và argmax
predictions không đổi. Không chuẩn hóa lại, shuffle hay thêm mẫu.

SV1 chạy sample i từ inputs `x[i:i+1]`, lưu output run_head(s), reshape theo
registry và so với `z_s[sample_index]` đúng layout. Reference artifact phải
bitwise với PyTorch; MCU tuân theo contract FP32 hiện tại max_abs_error
**strictly <1e-3**. Hai tiêu chí đó có mục đích khác nhau; Week 4 không tự
nới tolerance và chưa tuyên bố mọi split MCU PASS.

## 8. Model parameter handoff cho SV1

Full header `ml/results/week4/firmware/head_parameters.h` và 20 `.npy` trong
`weights/` bao phủ 8 Conv + 2 Linear, **109.653 FP32 parameters = 438.612 B**
logical parameters. Đây là parameter storage, không phải z_s payload.

Conv: kernel=5, stride=1, padding=2 symmetric zeros, dilation=1, groups=1;
in/out channels từng layer theo model_graph. Weight layout OIK, bias O.
Linear: weight OI, bias O, 1408→32 và 32→5. Tất cả đều có bias; không có
BatchNorm/folding. model_graph ghi đầy đủ ReLU placement, MaxPool kernel=2,
stride=2, padding=0, dilation=1, ceil_mode=false, return_indices=false;
Flatten start_dim=1/end_dim=-1, C-order; Dropout eval identity với p frozen.

Verifier tái lấy checkpoint parameters, kiểm tra từng array byte-for-byte,
kiểm tra từng C99 hex literal rồi compile bằng GCC `-std=c99 -Wall -Wextra
-Werror -pedantic`. Executable host in ra toàn bộ 109.653 FP32 bit patterns:
PASS. C compiler sanity check không chứng minh firmware vừa memory hoặc
timing trên nRF52840. SV1 tự port, chạy và đo; SV3 không implement run_head.

## 9. Figure Week 4

[PDF vector](../results/week4/tensor_size_vs_split.pdf), 15.632 bytes;
[PNG preview](../results/week4/tensor_size_vs_split.png), 100.829 bytes.
Trục x là canonical s, trục y logical payload per inference KiB. Nét đen
liền/chấm tròn là FP32 actual; nét xám đứt/ô vuông là INT8 estimated/theoretical.
Đã kiểm tra PNG cùng figure: labels/legend đọc được, không clipping, phân
biệt series bằng nét/marker khi in đen trắng. PDF dùng vector/font TrueType.

Hình chứng minh payload không đơn điệu và các kích thước cụ thể. Nó không
cho biết t_dev, t_edge, latency truyền thật, năng lượng, allocator/workspace,
packet overhead, accuracy sau quantization hoặc split tối ưu. FP32/INT8
ratio 4 chỉ là lý thuyết bytes/phần tử; chưa có INT8 experiment. Có thể join
CSV theo s với số đo SV1 về sau; không có số đo đó được tạo trong tuần này.

## 10. Verification

Mọi command trong block sau đã thực sự chạy ở repository root và exit 0.
`run_week4_regressions.py` gọi 18 command con dưới đây, ghi stdout/stderr vào
logs riêng, dừng nếu fail. Không dùng runner Week 1 để ghi đè lịch sử hoặc
rebuild dữ liệu. [Summary](../provenance/week4/regressions/summary.json) ghi
full command, log path/hash và snapshot 280 file unchanged.

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/profile_week4.py --repo-root . --output-dir ml/results/week4 --compiler C:/msys64/ucrt64/bin/gcc.exe
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4.py --repo-root . --output-dir ml/results/week4 --expected-manifest-sha256 d8ae119188eade380d86eca0f41fb4a27376c5c674a069192dbea284a945dea1 --compiler C:/msys64/ucrt64/bin/gcc.exe
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week4.py --repo-root . --output-dir ml/results/week4 --expected-manifest-sha256 d8ae119188eade380d86eca0f41fb4a27376c5c674a069192dbea284a945dea1 --compiler C:/msys64/ucrt64/bin/gcc.exe
& ml/.venv/Scripts/python.exe -B ml/scripts/run_week4_regressions.py --repo-root . --evidence-dir ml/provenance/week4/regressions
& ml/.venv/Scripts/python.exe -B ml/src/check_env.py
& ml/.venv/Scripts/python.exe -B ml/src/verify_mitdb_integrity.py
& ml/.venv/Scripts/python.exe -B ml/src/test_segmentation.py
& ml/.venv/Scripts/python.exe -B ml/src/audit_mitdb_preprocessing.py
& ml/.venv/Scripts/python.exe -B ml/src/verify_mitdb_normalization.py
& ml/.venv/Scripts/python.exe -B ml/src/verify_mitdb_processed.py
& ml/.venv/Scripts/python.exe -B ml/src/verify_ptbxl_normalization.py
& ml/.venv/Scripts/python.exe -B ml/src/verify_ptbxl.py
& ml/.venv/Scripts/python.exe -B ml/src/test_week1_negative.py
& ml/.venv/Scripts/python.exe -B ml/src/test_week2_baseline.py
& ml/.venv/Scripts/python.exe -B -O ml/src/verify_mitdb_integrity.py
& ml/.venv/Scripts/python.exe -B -O ml/src/verify_mitdb_processed.py
& ml/.venv/Scripts/python.exe -B ml/src/verify_week2_baseline.py --historical
& ml/.venv/Scripts/python.exe -B ml/src/test_week2_provenance.py --verify-historical-artifacts
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3.py --repo-root . --package ml/artifacts/week3/mitdb-week3-fp32-20260925-v2 --expected-manifest-sha256 0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469 --compiler C:/msys64/ucrt64/bin/gcc.exe
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3.py --repo-root . --package ml/artifacts/week3/mitdb-week3-fp32-20260925-v2 --expected-manifest-sha256 0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6
& ml/.venv/Scripts/python.exe -B device/scripts/check_week3_capture.py --repo-root . --capture results/week3/logs/week3_capture_20x5.txt --mode 20x5 --report-output ml/provenance/week4/sv1_week3_capture_recheck.json --csv-output ml/provenance/week4/sv1_week3_capture_recheck.csv
git diff --check
```

| Gate | Kết quả thực tế |
|---|---|
| Week 4 verifier | PASS: 11 boundaries, 220 bitwise golden cases, endpoints/predictions |
| Full-model parameter/C99 bits | PASS: 109.653 values, 20 arrays, không thiếu bias |
| Week 4 tampering | PASS: 18 reason-specific expected rejections |
| Monotonic classification | PASS: increasing, decreasing, flat, non-monotonic |
| Reproduction | PASS: 28/28 file byte-identical trong thư mục mới/temp |
| Week 1 | PASS: MIT-BIH/PTB-XL integrity/normalization/processed data, segmentation, 34 negative cases, -O checks |
| Week 2 | PASS: 3 baseline tests, historical verifier, provenance tests; không train |
| Week 3 SV1 package | PASS: original verifier + 27 expected rejections |
| Week 3 FP32 ONNX package | PASS: 200/200 ONNX FP32 comparisons, 20 identity cases + 17 expected rejections |
| SV1 existing capture recheck | PASS: 100/100 tensors, cùng IDs và số liệu với báo cáo 20×5 đã lưu |
| Preservation | PASS: 280 historical/user files cùng raw bytes trước/sau |
| Figure visual inspection | PASS: PNG từ cùng plot đã xem; grayscale readable |
| Whitespace | PASS: `git diff --check` |

Negative tests được coi PASS khi corruption bị từ chối đúng lý do; đây không
phải bỏ qua một lỗi thật. ONNX gate là ONNX Runtime CPU FP32; không phải
KV260/VART acceptance. Capture checker đọc log có sẵn, không đo MCU mới.
Matplotlib có cảnh báo không ghi được user font cache trong sandbox ở lần
export; PDF/PNG vẫn được tạo, kiểm tra và reproduce byte-identical, exit 0.

## 11. Reproducibility/provenance

Base Git commit: `6e9af108b7b0c39d63bc1c8dbbfbf4fcbf89c67e`. Frozen scientific
source commit: `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`. Code Week 4 local
chưa commit; manifest bind raw source-file hashes, không giả rằng HEAD đã
chứa code mới. Python 3.11.9, Torch 2.14.0+cu130; exact NumPy/ONNX/ORT và
Matplotlib versions nằm trong manifest. Inference CPU một thread, deterministic,
MKLDNN disabled, eval/no_grad theo contract reference.

| Trust binding | Raw SHA-256 |
|---|---|
| Week 4 manifest | `d8ae119188eade380d86eca0f41fb4a27376c5c674a069192dbea284a945dea1` |
| Week 3 all-split manifest | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` |
| Week 3 SV1 accepted v2 manifest | `0d263abeb09d5425d98568af755527457a52a6b468573cd12ac12efd97f00469` |
| Week 4 tensor_profile.json | `0d95458ee42616c0c62d263d05cdff9663f1737df7b792ea05c088a7523d1557` |
| Full C header | `3f811758ca6fc6a8fdefa74ff50ccb48031c006e9a12b617604dad033657487b` |

Inputs/checkpoint/sample hashes ở phần 2/7, mọi generated/reused tensor có
raw hash/shape/dtype/logical bytes trong manifest. Các source configs bind
patient split, normalization và label mapping frozen; raw-derived Week 3
verifier và regression Week 1–2 đã kiểm lại chúng. Không sửa manifests cũ.

`test_week4.py` thực sự gọi exporter vào một thư mục temp mới, verify rồi so
28 file hashes với lần đầu; các 220 golden cases reused được regenerate từ
PyTorch và so bitwise. Standalone reproduction command, **hướng dẫn chưa
chạy với path thường trực này**, là:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/profile_week4.py --repo-root . --output-dir ml/results/week4-repro --compiler C:/msys64/ucrt64/bin/gcc.exe
```

Exporter không overwrite. Reproduction cần các frozen local binary packages,
inputs/checkpoint và requirement sources đã đọc. Chuyển máy cần cả full
generated folder và dữ liệu referenced, không chỉ Git checkout. Không dùng
manifest hash tự tính từ thư mục nhận được làm trust anchor bên ngoài.

## 12. Kết quả nghiệm thu Week 4

| Definition of Done | Status / evidence |
|---|---|
| Frozen model/checkpoint unchanged | PASS: pinned hashes + 280-file preservation |
| Canonical mapping từ final Week 3 | PASS: config/contract CONFIRMED, L=10/s=0..10 |
| Profile toàn bộ splits | PASS: 11 rows, không thiếu/duplicate |
| Execution-confirmed shape | PASS: từng head ×20 N=1; independent full-forward hooks |
| Numel | PASS: product(shape), N=1 semantics |
| FP32 bytes | PASS: numel×4 |
| Estimated INT8 bytes/label | PASS: numel×1, theoretical only |
| Non-monotonic analysis | PASS: true, 4 tăng/6 giảm/0 bằng; recompute |
| Figure | PASS: vector PDF + inspected grayscale PNG |
| 20-sample all-split goldens | PASS: reuse, same IDs/order, 220/220 bitwise |
| All-head parameters/op specification | PASS: 20 arrays/25 ops, C99 exact bits |
| Manifest/provenance | PASS: model, samples, configs, sources, artifacts, runtime hashes |
| Week 4 verifier | PASS |
| Week 1–3 regressions | PASS: 18 commands, logs và hashes đã lưu |
| Reproduction | PASS: 28 generated files byte-identical; goldens recomputed bitwise |
| No Week 5 implementation | PASS |
| No fake MCU timing | PASS: không tạo t_dev(s) |
| No fake SV2/KV260 result | PASS: external pending ghi rõ |
| Real INT8/MCU Week 4 execution/SV2 acceptance | NOT APPLICABLE cho SV3 offline deliverable; chưa tuyên bố PASS |

SV3 Week 4 offline hoàn thành. SV1/SV2 hardware acceptance ở công việc riêng
vẫn cần thực hiện; kết quả này không tự đóng các gate của toàn nhóm.

## 13. Việc Week 4 KHÔNG làm

Không retrain hoặc đổi architecture/checkpoint; không đổi preprocessing,
patient split, normalization, labels, samples hay order. Không quantization
implementation, không P1/permutation/mask/PRNG protection, không NoPeek/P2
protection, không privacy attack. Không firmware run_head, MCU timing hoặc
KV260 timing; không xmodel compile và không fake SV2 acceptance. Không push,
merge, mở PR hoặc reset thay đổi có sẵn. **No Week 5 work was started.**

## 14. Dependency sau Week 4

SV1 dùng ngay registry, full weights/C header, op graph, 20 inputs và golden
mọi s để port/validate `run_head(s)` rồi đo timing thực nRF52840. Handoff ngắn
có command/path ở [sv3_sv1_week4_handoff.md](sv3_sv1_week4_handoff.md).

SV2 tiếp tục independently kiểm compatibility, quantize/compile các tail và
chạy VART/KV260. FP32 CPU references đã có; SV2 pending không ngăn SV1 dùng
gói này và không block SV3 Week 4. INT8/DPU accuracy criteria phải theo
project contract riêng, không mặc nhiên áp dụng ngưỡng FP32 <1e-3.

Các tuần sau mới ghép t_dev/t_edge thực, overhead truyền và tiêu chí bảo vệ
vào bài toán lựa chọn split. Tuần này chỉ cung cấp dữ liệu nền và kiểm chứng,
chưa bắt đầu những implementation đó.

## 15. Tôi cần hiểu gì trước khi sang Week 5

Cần đọc được đường đi `x → head_s → z_s → tail_s → logits`, biết s đếm
learned layers, còn ReLU/Pool/Flatten/Dropout được gắn theo convention. Cần
phân biệt NCL với NC và C-order, giữ sample_index đúng CSV khi so reference.

Cần tự tính numel/bytes/KiB, biết payload một inference khác batch 20 và
khác Flash weights hoặc NPY file size. Cần hiểu channel expansion làm payload
tăng còn Pool/Linear làm giảm, vì thế cắt sâu hơn chưa luôn giảm truyền ở
mỗi bước. INT8 estimated hiện tại chỉ là phép nhân lý thuyết, chưa có accuracy
hoặc scale thực nghiệm. Cuối cùng, hiểu bitwise reference check, MCU FP32
tolerance, trusted manifest hash và hardware timing là các loại bằng chứng
khác nhau. Chỉ tìm hiểu các khái niệm này; không có code Week 5 được bắt đầu.
