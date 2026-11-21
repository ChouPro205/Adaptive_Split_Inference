# SV3 — sửa verifier FP32 tuần 3 trên Ubuntu, 06/10/2026

## Kết quả và phạm vi nghiệm thu

Đã tái hiện đúng `ValueError: Recomputed golden bits differ: s=9` trên
Ubuntu thật qua WSL2 với Python/dependency khớp manifest. Verifier đã sửa
PASS theo tùy chọn **`portable-fp32-v2`**. Chính sách cũ **`bitwise-v1`** vẫn
là mặc định, vẫn FAIL tại s=9 trên Linux này và PASS trên Windows đã pin.
PASS mới không đồng nghĩa hợp đồng bitwise cũ PASS, không xác nhận VART,
KV260, INT8 hoặc nghiệm thu máy nhận. SV2 vẫn phải chạy lại trên máy mình.

Đây là thay đổi chính sách verifier có tùy chọn riêng để review local.
Không sửa checkpoint, model, trọng số, preprocessing, sample IDs/order,
split mapping, ONNX, golden, evidence, manifest hoặc ZIP v1. Không push,
merge, commit bản sửa hoặc phát hành release mới; không triển khai tuần 5.

Source nền: `415d53431c81c465784dc08be42b568827a39cff`, ban đầu branch
`dev/model-sv3`; branch sửa riêng: `sv3/fix-week3-sv2-linux-fp32`.
Commit này chứa R4 merge `23b2b7d`; verifier/common/cache tại nền không khác
bản đã tích hợp R4. R4 historical export là `89109fd` theo receipt cũ;
không gán kiểm thử mới cho commit export đó. Kiểm thử bản sửa là kiểm thử
**working tree trên 415d534**, với SHA source từng lệnh trong evidence.

Các mục chưa theo dõi có sẵn được giữ: `AGENTS.md`, `exports/`, ZIP snapshot
tuần 1, `ml/configs.zip`, `ml/docs.zip`, `ml/manifests.zip`, `ml/src.zip`.
Chỉ thêm một thư mục riêng trong exports để kiểm đối chứng R4.

## Môi trường đã đo

| Thành phần | Linux qua WSL | Windows hiện có |
|---|---|---|
| OS | Ubuntu 24.04.5 LTS, WSL2 | Windows 11 |
| Kernel/CPU | 6.18.33.2-microsoft-standard-WSL2, x86_64, Intel i5-12400F | cùng máy vật lý, AVX2 |
| Python | CPython 3.11.9 native Linux | CPython 3.11.9 |
| torch | 2.14.0+cu130 | 2.14.0+cu130 |
| NumPy / ONNX / ORT | 2.4.6 / 1.23.1 / 1.30.0 | cùng phiên bản |
| protobuf / ml_dtypes / flatbuffers | 7.36.2 / 0.6.0 / 25.12.19 | cùng phiên bản |
| BLAS được build vào torch | oneMKL 2024.2, GCC 13.3 | oneMKL 2026.1, MSVC 19.42 |

Python 3.12.3 mặc định của Ubuntu không được dùng cho verifier. Venv riêng:
`/home/kyanh/asi-week3-sv2-linux/venv`; interpreter nằm trong filesystem Linux,
không dùng Windows venv qua `/mnt/c`. Source được đọc tại
`/mnt/c/Users/Admin/Adaptive_Split_Inference`; không cần clone Linux riêng.
Không thay đổi môi trường Windows. CUDA wheel được cài để khớp **đúng**
runtime gate v1, nhưng model/tails chạy CPU, eval, N=1, một thread,
deterministic algorithms, MKLDNN disabled. ORT dùng CPUExecutionProvider,
ORT_SEQUENTIAL, một thread intra/inter, ORT_ENABLE_BASIC.

[Environment đầy đủ](../ml/provenance/week3-sv2-linux/environment_linux.stdout.txt)
ghi OS, CPU, cwd, interpreter và toàn bộ dependency. Hai diagnostic full ghi
torch build/parallel config và biến backend. Không tải dataset hoặc artifact
bổ sung; dùng các package đã có trên máy.

## Nguyên nhân đã xác minh và giới hạn kết luận

1. Hash/size và anchor v1 hợp lệ; inventory R4 đã vượt qua trên Linux.
   [Verifier trước sửa](../ml/provenance/week3-sv2-linux/before_linux.stderr.txt)
   exit 1 chính xác tại s=9. Source verifier lấy từ checkout, không từ v1.
2. s=0..8 bitwise giống golden. Flatten, inactive Dropout không làm đổi dữ
   liệu. Khi cô lập Linear1 với **cùng bytes input, weight, bias** trên hai
   OS, output trước ReLU đã khác 178/640 phần tử, max_abs
   `1.9073486328125e-6`; profiler ghi `aten::linear` → `aten::addmm`.
   Sau ReLU còn 94/640 phần tử khác. Vì vậy điểm đầu tiên gây khác biệt đã
   khoanh vùng tại Linear1 (`classifier.2`), không phải mapping hoặc ReLU.
3. Linear2 với cùng s9 bàn giao cũng khác 61/100 phần tử, max_abs
   `9.5367431640625e-7`. Không quy toàn bộ sai lệch logits cho Linear1.
   [Đối chiếu operand/output](../ml/provenance/week3-sv2-linux/dense_comparison.json)
   được dựng từ `dense_windows.stdout.txt` và `dense_linux.stdout.txt`.
4. Oracle dot-product float64 của Linear1: output Linux sau ReLU lệch tối
   đa `3.388697173534183e-6`, output bàn giao lệch `4.07356812459625e-6`.
   Đây là diagnostic số học, không thay phép tính model bằng float64.
5. Đối chứng process riêng `MKL_CBWR=COMPATIBLE` làm thay đổi kết quả cả
   conv: s8 lệch `3.814697265625e-6`, s9 `7.62939453125e-6`.
   Đối chứng này chứng minh lựa chọn backend ảnh hưởng kết quả; **không dùng
   biến này làm fix** và không coi đối chứng là PASS portable, vì s1..8
   không còn bitwise. Backend mặc định được dùng cho mọi gate PASS.

Nguyên nhân chặn đã xác minh: verifier yêu cầu kết quả FP32 tính lại khác
build phải bitwise và yêu cầu error observations JSON trùng tuyệt đối,
trong khi hai native builds tạo sai lệch làm tròn nhỏ ở dense. Cùng số
phiên bản Python/torch không bảo đảm cùng BLAS binary. Việc khác MKL
2024.2/2026.1 là bằng chứng môi trường liên quan; **chưa chứng minh riêng
phiên bản MKL hoặc kernel/reduction/FMA cụ thể là nguyên nhân duy nhất**
vì chưa hoán đổi BLAS giữa hai builds.

Điều này phù hợp với tài liệu chính thức:
[PyTorch numerical accuracy](https://docs.pytorch.org/docs/stable/notes/numerical_accuracy.html)
không bảo đảm FP bitwise giữa các nền tảng;
[Intel numerical reproducibility](https://www.intel.com/content/www/us/en/docs/onemkl/developer-reference-dpcpp/2025-2/numerical-reproducibility.html)
giải thích thứ tự phép tính BLAS có thể làm khác kết quả. Các nguồn này hỗ
trợ diễn giải, không thay bằng chứng chạy của dự án.

## Sai lệch so với dữ liệu bàn giao gốc

Mọi tensor đúng shape, `<f4`, finite. Sai lệch tính bằng float64 subtraction.
[Diagnostic Linux](../ml/provenance/week3-sv2-linux/diagnostic_linux.stdout.txt)
lưu đủ shape/dtype, số phần tử khác bit, vị trí/giá trị cực đại cho s=0..10
và cả 200 ONNX cases; [Windows](../ml/provenance/week3-sv2-linux/diagnostic_windows.stdout.txt)
khớp bitwise mọi split, JSON evidence không có khác biệt.

| Kết quả Linux mặc định | Khác bit | Max absolute error | Vị trí cực đại (0-based) |
|---|---:|---:|---|
| s=0..8 | 0 mỗi split | 0 | xem diagnostic |
| s=9, shape (20,32) | 94/640 | 1.9073486328125e-6 | [0,28] |
| s=10, shape (20,5) | 67/100 | 1.1920928955078125e-6 | [6,4] |
| Full logits vs original reference_logits | 67/100 | 1.1920928955078125e-6 | [6,4] |
| ORT vs original reference_logits | 200/200 cases đạt <1e-3 | 2.6226043701171875e-6 | s=0, sample 16 |
| ORT vs Linux PyTorch tail | 200 cases | 2.384185791015625e-6 | xem per-case log |

Tại s9 [0,28]: Linux `15.718520164489746`, bàn giao `15.718518257141113`.
Tại s10/logits [6,4]: Linux `-2.9561874866485596`, bàn giao
`-2.956186294555664`. Numerical JSON tính theo cách cũ trên Linux có 307
field values khác bản bàn giao; diagnostic lưu từng đường dẫn, không chỉ
so sánh hai kết quả cùng tính lại trên Linux.

## Chính sách `portable-fp32-v2`

| Loại kiểm tra | Quy tắc |
|---|---|
| Anchor, file hash/size/inventory và identity | Giữ nguyên chính xác, trước recomputation |
| Activation s=0..8 tính lại | Giữ bitwise |
| Activation s=9 tính lại | Float32 đúng shape, finite; strict max_abs <1e-5; không rtol |
| s=10/full logits tính lại | Float32 đúng shape, finite; strict max_abs <1e-3 |
| Delivered s10 và delivered reference_logits | Bitwise identity |
| PyTorch tail/ORT trên golden bàn giao | So với **reference_logits gốc**; giữ strict <1e-3 |
| Evidence JSON bàn giao | Hash/bytes xác thực nguyên bản; metadata/schema/IDs/order/graphs/status/counts chính xác |
| Error observations, per-split/global/direct maxima | Mỗi số finite, không âm, <1e-3; maxima khớp đúng các rows của chính run đó |

Ngưỡng mới chỉ áp dụng **s9**, khoảng 5.24 lần cực đại `1.90735e-6` đã đo,
nhỏ hơn 100 lần tiêu chí logits. Đây là ngân sách tuyệt đối đề xuất cho
recomputation của dense activation, không phải hợp đồng mặc định cho mọi
tensor trung gian hoặc mọi nền tảng. Linux khác build gây drift conv sẽ
vẫn bị từ chối; cần diagnostic/review riêng nếu SV2 gặp tình huống đó.

Không dùng recursive allclose cho JSON. Giá trị sai số là observations của
từng run; không ép chúng bằng số của Windows. Global worst có thể chuyển
case nhưng phải đúng `max(rows)` của run, với metadata và coverage còn
nguyên. `bitwise-v1` vẫn so toàn bộ evidence JSON chính xác như trước.
Output PASS luôn có `recomputation_policy`, `reference_basis`,
`legacy_contract_pass` và per-split drift. Khi chạy portable,
`legacy_contract_pass=false` nghĩa là run này không tuyên bố đã chạy/PASS
hợp đồng legacy, kể cả các bits tình cờ khớp trên Windows.

Regression chứng minh drift nhỏ chỉ trong recomputation được chấp nhận;
golden dù sửa `1e-6` vẫn bị hash gate từ chối. Fault s9 `1e-4`, conv drift,
logit fault, strict boundary, NaN/±Inf, sai shape/dtype, sai metadata hoặc
error summaries đều bị từ chối. File thiếu/thừa/trùng, hash/size, cache,
symlink và anchor sai vẫn được kiểm qua suite R4.

## Bảng kiểm thử và logs

Đường dẫn trong bảng nằm dưới
[`ml/provenance/week3-sv2-linux/`](../ml/provenance/week3-sv2-linux/).
Mỗi tên có `.command.json`, `.stdout.txt`, `.stderr.txt`: argv nguyên văn,
cwd Windows (WSL cwd Linux ở environment), base commit, source SHA, exit
code và SHA streams. Prefix `final_*_v2` là suite mở rộng cuối; những log
không có suffix v2 của tamper/policy là lượt trước khi thêm ca regression.

| Gate | Ubuntu/WSL2 tác giả | Windows đã pin | Log prefix |
|---|---|---|---|
| Verifier trước sửa | FAIL s9, exit 1 | diagnostic bitwise + saved JSON khớp | before_linux / diagnostic_windows |
| Verifier portable | PASS 200 comparisons | PASS 200 comparisons | final_linux_verifier / final_windows_portable |
| Verifier legacy sau sửa | FAIL s9 (mặc định được giữ) | PASS | legacy_linux / final_windows_legacy |
| test_week3_sv2 | PASS 19 expected rejections, portable | PASS 19, legacy | final_linux_tamper_v2 / final_windows_tamper_v2 |
| test_week3_sv2_cache | PASS 16/16, portable | 15 PASS + 1 SKIP symlink thật (WinError 1314), legacy | final_linux_cache / final_windows_cache |
| test_week3_sv2_policy | PASS 8/8 | PASS 8/8 | final_linux_policy_v2 / final_windows_policy_v2 |
| SV1 tuần 3 verifier | FAIL inventory trước numerical gate | PASS, 1392 C elements | sv1_linux_verifier / sv1_windows_verifier |
| SV1 tuần 3 tamper suite | SKIP: positive gate Linux đang fail | PASS 27 rejections | sv1_windows_tests_corrected |
| R4 verifier với source sửa | FAIL Source file changed (đúng source pin) | cùng expected rejection | week4_linux_gate / week4_windows_gate |
| R4 với source nền riêng từ 415d534 | FAIL Golden FP32 bits differ: 9 | PASS, 220 golden cases, 109653 C elements | week4_linux_baseline / week4_windows_baseline |
| R4 full tamper/reproduction suite với source nền | SKIP: positive gate Linux đang fail | PASS 21 rejections, 4 monotonic cases, scientific reproduction | week4_windows_baseline_tests |
| test_week4_release | PASS 6/6 | SKIP: đã chạy Linux; không đổi release implementation | week4_linux_release_tests |
| Bash recipe đầy đủ | PASS exit 0: môi trường + checksum + diagnostic + verifier + 3 suites | Không áp dụng | recipe_linux |

SV1 inventory là vấn đề Linux có sẵn ở verifier riêng, không do patch này:
`verify_week3.py` và `week3_common.py` không sửa. Không tuyên bố SV1 Linux
PASS. R4 đã pin source hashes; phải tiếp tục từ chối source mới. Không đổi
anchor/source inventory R4 để hợp thức hóa. Source view đối chứng riêng
ở `exports/week3-sv2-linux-review-20261006/baseline`, dựng trực tiếp bằng
`git show 415d534:path`; receipt `week4_baseline_view.json` ghi danh sách
file. Đây không phải release mới. Suite mới chỉ mở rộng SV2; không tự thêm
portable policy vào verifier SV1/tuần 4 hoặc các release runner cũ.

Lượt `sv1_windows_tests` ban đầu lỗi CLI vì truyền `--compiler` không được
suite hỗ trợ; lượt `sv1_windows_tests_corrected` đã dùng GCC qua PATH và
PASS. Lưu log lỗi thao tác ban đầu để không che lịch sử.

## File sửa/thêm và tự review

- `ml/scripts/verify_week3_sv2.py`: tùy chọn policy; ngân sách s9 giới hạn;
  so original logits; kiểm metadata và tính nhất quán evidence riêng.
- `ml/scripts/test_week3_sv2.py`: truyền policy, thêm Inf và tiny golden
  mutation vẫn phải fail hash; giữ tamper tests cũ và overwrite guard.
- `ml/scripts/test_week3_sv2_cache.py`: truyền policy cho full verifier
  trong tests; mặc định legacy; không thay inventory/security assertions.
- `ml/scripts/test_week3_sv2_policy.py`: 8 regression tests số học/evidence,
  gồm injection fault trong verifier thật với nguyên anchor.
- `ml/scripts/diagnose_week3_sv2.py`: read-only diagnostic toàn split,
  original-logit comparisons và cô lập Linear/profiler.
- `ml/scripts/reproduce_week3_sv2_linux.sh`: recipe Linux đầy đủ, venv
  riêng, kiểm ZIP/manifest/files, ghi log và chạy các gates.
- Báo cáo này, mục lục docs, và evidence/tools dưới
  `ml/provenance/week3-sv2-linux/`: nguồn/lệnh/metrics để tái tạo và review.

Tự review: không thay `same_bits` toàn dự án, không sửa common backend,
mapping hoặc exporter, không thay package file set/SCRIPTS (v1 nguyên bản).
Policy nằm trong source verifier để không thêm dependency bị thiếu vào
cơ chế đóng gói scripts hiện có. Legacy default và so JSON exact được giữ.
`git diff --check` PASS. Source SHA trong receipt cuối phân biệt working
tree với base commit; không coi HEAD 415d534 là commit chứa fix chưa commit.

## Lệnh Bash để SV2 chạy lại

Dùng **source có bản sửa đã review**, không chạy scripts trong package v1.
Branch local chưa push: clone remote tại 415d534 hiện chưa tự có patch này.
SV3 cần chuyển source đã review cho SV2; chỉ package v1 là chưa đủ.
Đặt ZIP v1 đã bàn giao hoặc thư mục package nguyên bản tại
`ml/artifacts/week3/`. Không cần download/refit dataset.

```bash
# Ubuntu 24.04 / WSL2; đổi đường dẫn tới source đã nhận kèm bản sửa.
cd /mnt/c/Users/Admin/Adaptive_Split_Inference
bash ml/scripts/reproduce_week3_sv2_linux.sh
```

Script đầy đủ tại
[`reproduce_week3_sv2_linux.sh`](../ml/scripts/reproduce_week3_sv2_linux.sh):
tạo Python 3.11.9 Linux venv, cài torch 2.14.0+cu130 và ONNX/NumPy được
pin, xác minh checksum ZIP nếu có, anchor và hash/size files; diagnostic,
verifier portable, tamper/cache/policy tests; ghi command/stdout/stderr/exit
code/source hashes. Có thể chọn môi trường/log riêng:

```bash
ASI_LINUX_ENV_ROOT="$HOME/asi-sv2-review-env" \
ASI_LINUX_LOG_ROOT="$HOME/asi-sv2-review-logs" \
bash ml/scripts/reproduce_week3_sv2_linux.sh
```

Để kiểm hợp đồng cũ riêng (trên máy tác giả Linux đã xác nhận FAIL s9):

```bash
"$HOME/asi-week3-sv2-linux/venv/bin/python" -B ml/scripts/verify_week3_sv2.py \
  --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 \
  --expected-manifest-sha256 a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6 \
  --recomputation-policy bitwise-v1
```

## Artifact và thông tin cần SV2 xác nhận

`artifact_before.json` và `artifact_after.json` ghi SHA từng file v1 và
ZIP; `artifact_preservation.json` ghi đối chiếu trước/sau. Anchor giữ
`a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`;
ZIP giữ `b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7`.

Máy tác giả đã tái hiện lỗi; không thiếu dữ liệu để kết luận về máy này.
Để nghiệm thu máy nhận, SV2 cần gửi source commit **và source hashes**,
command/cwd/exit code/stdout/stderr, OS/CPU/Python/dependency/backend config,
package anchor/ZIP checksum, diagnostic per-split và 200 comparisons với
original logits, cùng policy dùng. Nếu portable vẫn fail s1..8 hoặc s9
vượt 1e-5, giữ FAIL và gửi diagnostic; không nâng threshold hoặc tái tạo
golden để lấy PASS. ACK của SV2 vẫn PENDING.
