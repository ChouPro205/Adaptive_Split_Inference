# SV3 tuần 7 — đối soát SV2 và hồ sơ tiếp nhận accuracy

**Bổ sung sau review, hồ sơ ngày 27/10/2026:** evaluator có hai lỗi validation
đã được sửa tại `18e74ab`; evidence mới 18/18 thường +18/18 `-O` ở
[hồ sơ sửa lỗi](../ml/provenance/week7-evaluator-fix-20261026/README.md).
Các số liệu/receipts bên dưới giữ nguyên mốc 26/10; reference không tạo lại.

Ngày đối soát: **26/10/2026, Asia/Saigon**. Kết luận: phần SV3 có đủ đầu vào đã
hoàn tất; **không đánh dấu toàn bộ tuần 7 DONE**. Accuracy DPU và các xác nhận
đúng owner còn riêng. Không flash, chạy BLE/E2E hoặc huấn luyện lưới NoPeek.

## 1. Mốc Git và phạm vi thay đổi

- Đã fetch GitHub. Main: `d91fe27cc83e617d8a86ad7d6731687eea518d6a`.
  [PR34](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/34) đã merge
  tại `cbb54157431cb278b165c5b00931f2b806fbbca2`;
  [PR36](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/36) đã merge
  tại `91aa696a18c6c48f12928943ce9fa4901d1c8987`.
- [PR38](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/38) còn mở,
  SV2 head `e53868088aceeba1bb4b70569597462539250f06`. Diff với main: ghi chú
  build lịch sử, README, thông báo `samples must be 1`, LF checksum tuần 5;
  không có output test DPU mới. Không đưa diff này vào branch SV3.
- SV1 head `dab40a39a6ca968ececf3a73b5f3e54817fa8f00`; tree diff với main rỗng.
  Có merge commits riêng trên nhánh, không có thay đổi file chưa đưa vào main.
- Checkout gốc `415d53431c81c465784dc08be42b568827a39cff` có 5 file tracked sửa
  và nhiều file untracked. Giữ nguyên. Các worktree cũ được kiểm trạng thái,
  không reset, rebase hay ghi vào source của chúng.
- Worktree mới: `exports/sv3-week7-reconcile-20261026`, branch
  `sv3/week7-reconcile-20261026`, từ main nói trên. Implementation mới:
  **`08e4b4259a2757be7b663b88cc1c98607602d266`**. Các command `delivery-*`
  kiểm commit này; báo cáo/receipt được giao sau implementation.

[GitHub snapshot](../ml/provenance/week7-reconcile-20261026/github-state.json),
[audit mới](../ml/provenance/week7-reconcile-20261026/delivery-audit.json).
Đây là kết quả đọc GitHub và kiểm tại HOST, không phải lần thực thi mới trên board.

## 2. Bàn giao và định danh backend

Nguồn SV2 dưới đây đều có trên main `d91fe27`; source execution tuần 7 được công
bố tại `a851a05b90827aeddcb660585bb989b0f594e39b`. Source được commit sau phép
chạy, vì vậy source/binary hashes trong provenance mới định danh lần chạy gốc.

| Kết luận | Nguồn/commit hoặc SHA-256 | Phạm vi kiểm ngày 26/10 |
|---|---|---|
| Nhận đúng P1 A+B | `results/week7/edge/p1_host_A.json`, `p1_host_B.json` tại `d91fe27`; 50/50 Python/C, 46 reference tail +4 identity | Tái tính và ghép receipt; A rows trùng bản SV3, B được so số học với reference |
| P1 version | `mitdb-week6-p1-50-20261016-v1`; manifest `d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36` | Gói cục bộ đúng 405 member + root manifest; raw input packet/q/logits được ghép với 100 dòng case |
| P1 ZIP | 412.045 byte; `2afbab35b601ac14128c32018d6dc1d39afd1991759a7a0fd9ad2051d923359a` | Tính lại ZIP SHA/size, khớp receipt release SV3 |
| Checkpoint | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` | Model package đã authenticate qua loader tuần 5 khi tạo reference |
| Package model/source | `mitdb-week3-sv2-fp32-20261001-v1`; manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`; source `8e98a0e4851abc979feb5fd5b97ece612b02cfaa` | Giữ nguyên baseline; không thay bằng smoke weights |
| Registry/profile | `mitdb-week5-i2-registry-v1-r1`; raw SHA `79392b6db73cde6d83eadb1f265f14102888ebdbf8ea1b72b6c127c5566eed24`; profile `1296651265`; wire IDs `256+s` | Registry snapshot trong provenance execution khớp Git blob hiện hành; không đổi approval/nonce |
| Mapping | s0…s8 NCL, s9 NC `[1,32]` sau wire NCL; s10 identity `[1,5]` | 50 vector metadata, sample/split/request IDs khớp gói SV3 |
| Model hashes | `results/week7/edge/provenance.json:model_hashes` tại `d91fe27` | Cả 10 hash khớp tuần 5 summary và tuần 6 profile; không có model s10 |
| Runtime | KV260 SD-A, PetaLinux 2022.1, Vitis AI 2.5, B4096; Python 3.9.9/NumPy 1.21.2; native GCC 11.2.0 | Thông tin execution công bố; không SSH/probe lại board |
| Native binary | `c6084cc0b1c2ecd306dbf2db88c3ef577e543fbfb7f77320949dfbad7bcfc247`; build `2026-10-23T07:04:30Z` | Đọc provenance; chưa có binary raw tại worktree để tự băm lại |
| Archive board | `ca8bea529211e5890b9abf097c41a13632d9bc32f90b0b57b4a2ad12c8ad69bb` | Pin archive đã công bố; chưa tải/giải archive gốc của SV2 |
| Calibration | `build_and_audit_models.py` truyền `golden/z_s{s}.npy`, `--calib-data-split val`, 20 mẫu; `samples.csv` SHA `4a6356312d5f62da6b2fdf9e609843d4dea3fc5c20767e201ea21a075e6f227c` | 10 input hashes trong tuần 5 khớp NPY golden gốc; 20 sample IDs có sẵn trong package và manifest mới. Đây là calibration reuse, không phải test độc lập |

Không cần SV2 gửi lại receipt A+B, ZIP identity, sample list 50 vector, model
hashes, bảng profiling hoặc thông tin môi trường đã có. Còn thiếu trên Git:
**per-split quantizer provenance/quant_info và compile logs/manifest gắn với đúng
xmodel**, để kiểm trực tiếp lineage calibration→quantize→compile của execution;
raw output/binary của board nếu cần nâng review từ bảng sang bytes.

Hai lưu ý kiểm toán được giữ trong [development notes](../ml/provenance/week7-reconcile-20261026/development-notes.md):

1. `host_verifier_receipts_sha256` băm receipt **gốc**, còn exporter bỏ `C_build`
   và serialize lại bản công bố. Dùng `sha256sum_export.txt` cho bytes công bố;
   không kết luận hai SHA khác nhau là dữ liệu hỏng.
2. Verifier tuần 6 yêu cầu toàn bộ source hiện hành bằng source sinh gói. Gate
   dừng đúng tại `edge/quantize_tail.py` do main đã có sửa hợp lệ của SV2. Không
   sửa/bỏ gate hay gán PASS cho verifier đó. Audit mới kiểm inventory gói và
   **199 Git blobs** tại generating commit `766a3cfa7e7828ecd00b9eb23cc3e5da4015ced5`.
   Native `.cpp/.hpp` tại checkout Windows có CRLF khác bytes đo; Git blobs main
   khớp source execution. Khi tái export lịch sử, dùng source đúng bytes từ Git,
   không sửa checksum lịch sử để khớp checkout hoặc source mới của PR38.

## 3. Tái kiểm độc lập kết quả SV2

Audit kiểm cả checksum export tuần 5/6/7, 100 dòng cases, 22 dòng by_split,
status, A+B, provenance, source execution và contract/reference snapshots.
Tái tính từ 5 số logit mỗi dòng, kiểm hữu hạn, sample/vector/request/wire IDs,
class order, max-abs, argmax theo chỉ số nhỏ nhất khi hòa và liên kết model hash.

| Backend | Request | Tail / identity | Unique ECG validation | Argmax agreement | Max-abs tính lại |
|---|---:|---:|---:|---:|---:|
| HOST reference | 50 | 46 reference /4 | 5 | 50/50 | `1.430511474609375e-6` |
| KV260 root CPU+DPU | 50 | 46 native /4 | 5 | 50/50 | `0.40645813941955566` |

Từng split nằm trong `delivery-audit.json:by_split`. Cả 50 prediction/reference
argmax đều là **N**. Không có coverage prediction S/V/F/Q, không đánh giá được
accuracy độc lập hay chấp nhận DPU từ bộ này. HOST nằm trong ngưỡng FP32 cũ
`<1e-3`; sai số KV260 chỉ là mô tả, **numeric acceptance vẫn PENDING**.

Đã tự kiểm raw **input P1 của SV3** (packet/q/frozen logits) bằng hash và bytes.
Chưa tự đọc raw **output SV2**: response.bin, input.npy, runner.json/log, binary
và archive board chỉ có inventory/hash. Việc exporter SV2 đã kiểm 151/289 file,
response CRC, NPY và runner là bằng chứng SV2 công bố; audit JSON không biến nó
thành phép đo board mới hoặc raw output recheck của SV3.

Review code giữ đúng I1 v2:

- `recover_q`: unprotect → từ chối q=-128; transformed 0x80 hợp lệ.
- `dequantize`: scale kênh gốc `index // length`, FP16 normal đã reload mở rộng
  FP32; không dùng scale ở vị trí kênh bị hoán vị.
- `serve.py`: s0…s8 NCL, s9 `[1,32]`; runner kiểm NCL/NC hoặc chuyển NLC có thứ
  tự rõ ràng, requantize bằng fix_point/DPU_ROUND. I1 q cấm -128 khác miền INT8
  nội bộ của DPU adapter có saturation [-128,127].
- s10 trả identity chính xác FP32, không gọi/nạp native tail. Bốn case logit
  và model=null khớp. Response là 5 raw logits N/S/V/F/Q, không softmax;
  tie chọn index nhỏ nhất. Ba tie cases riêng có receipt host, không giả thành
  case tie đã chạy trên DPU hoặc trong 50 vector thật.

## 4. Giữ ba split s2/s5/s8 cho thiết kế tuần 8

| Split | Xmodel SHA-256 | Load mean ms | First tail mean ms | Steady tail mean /p95 ms | KV260 max-abs, bộ nhỏ |
|---|---|---:|---:|---:|---:|
| s2 | `68c5f86b5ca60479176aa7a5da0e9fef5b79ac436b43468e8ba0ae5353deeaa9` | 73.624433 | 47.014073 | 46.811305 /46.952531 | 0.347266674 |
| s5 | `e000dafb9edd58fb00d675e77008e59892c00c53bae9d50735edb8228d7a39a2` | 51.135889 | 30.906374 | 30.602407 /30.752619 | 0.327105522 |
| s8 | `dcc460edff10e22874f27d60bd0c98374bd3937f87690944287eab8213e5517e` | 29.761897 | 2.461330 | 2.289066 /2.389677 | 0.088961601 |

Nguồn: `results/week6/edge/profile_edge.json`, `timing.csv`, tuần 7 cases tại
main `d91fe27`. Mỗi split 5 process load/first, 500 observations steady;
toàn bộ 10 split là 50 load và 5.000 observations. Đã đối chiếu JSON↔CSV,
model hashes qua tuần 5/6/7; raw timing samples không có tại worktree này.

Đây là **root GraphRunner CPU/PS+DPU**, gồm fallback, prepare/layout/quantize,
sync/copy/read; cột execute/wait cũng không phải DPU-only. Load tách first,
không gồm process startup/đọc NPY và filesystem cache không được kiểm soát.
Profile là runner tuần 6; service tuần 7 nạp model theo request, chưa có service
throughput/latency mới để dùng làm LUT hoàn chỉnh.

Đề xuất **giữ s2/s5/s8**: cả ba đã chạy thật trong file pipeline, khác độ sâu
head, kích thước tensor 2.880/4.320/1.408 phần tử và chi phí tail. s8 nhanh hơn
ở Edge chưa đủ để loại s2/s5: còn chi phí Device/link, accuracy test DPU và
trade-off utility/privacy. Không đổi config, checkpoint hay split mapping.
13 source/config/evidence bindings của NoPeek khớp pin cũ trong
[reuse receipt](../ml/provenance/week7-reconcile-20261026/nopeek-reuse.json).
Giữ evidence toán/loss/smoke đã đạt; không chạy lại training smoke/grid.

## 5. Accuracy DPU: phần chuẩn bị đã hoàn thành

Đã kiểm main và nhánh SV2 chưa merge: chưa có output DPU test 8.544 mẫu mới.
Bộ sẵn sàng ở **`.cache/week7-reconcile/accuracy-8544-delivery/`** trong worktree:

- `samples.csv`: 8.544 IDs duy nhất, thứ tự, patient/record IDs và labels frozen.
- `inputs_s2.npy`, `inputs_s5.npy`, `inputs_s8.npy`: activation sau INT8/FP16
  round-trip, giải lượng tử FP32; shape `[8544,16,180]`, `[8544,48,90]`,
  `[8544,64,22]`. Khi dùng single-input runner lấy slice `array[i:i+1]`.
- `reference_fp32.npy`: baseline full FP32; ba file
  `reference_wire_fp32tail_s{s}.npy`: cùng activation wire, tail FP32.
- `manifest.json`: SHA/size mọi file, checkpoint/model/dataset/source bindings,
  expected xmodel/calibration golden hashes. Bản sao receipt có track:
  [prepared-reference-manifest.json](../ml/provenance/week7-reconcile-20261026/prepared-reference-manifest.json).

Loader tuần 5 kiểm nguyên hash train/val/test và provenance checkpoint; đây là
evaluation, không dùng test để calibrate, train, early-stop hoặc chọn lambda.
FP32 tính lại **8.393/8.544 = 98,2326779026%**, khớp số correct lịch sử.
Support N/S/V/F/Q: **8.102/13/426/1/2**; lớp hiếm phải đọc cả support lẫn metrics.
Raw input/reference arrays giữ ngoài Git; nhận lại bằng cùng manifest hash.

SV2 cần trả cho **mỗi split** đủ 8.544 IDs (25.632 cặp với ba split):

1. Output JSON theo
   [template](../ml/provenance/week7-reconcile-20261026/dpu-output.template.json):
   `sample_id`, `split_point_s`, status, 5 logits N/S/V/F/Q cho OK hoặc lý do lỗi.
   Không dùng thứ tự dòng để ghép. Manifest reference phải đúng SHA template.
2. Board/runtime, source commit và runner/plugin hashes của **lần chạy thật**,
   policy layout/scale/fix_point/rounding. Xmodel phải bằng hash đã pin; nếu
   recompile/đổi trọng số thì review provenance và manifest mới trước nghiệm thu.
3. Quant_info, quantizer provenance, compile manifest/logs gắn từng model;
   xác nhận calibration bằng 20 golden val đã có, sample CSV/golden hashes nằm
   trong template. Không cần gửi lại danh sách IDs đã công bố; cần artifacts
   chứng minh đúng lineage của execution, gồm SHA và bytes/log để kiểm khi nhận.
4. Giữ cả timeout/failure/missing; không bỏ mẫu lỗi, không chỉ gửi prediction
   hoặc accuracy tổng. Không cần đợi BLE để chạy offline bằng native backend.

Lệnh tiếp nhận (từ root worktree, thay đường dẫn file thật và tên output mới):

```powershell
$py = 'C:/Users/Admin/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe'
& $py -B ml/scripts/week7_dpu_accuracy.py evaluate --reference .cache/week7-reconcile/accuracy-8544-delivery --outputs .cache/sv2-output.json --output ml/results/week7-dpu-new/evaluation.json
```

Evaluator kiểm hash reference, class/model/manifest/calibration identity, ghép
IDs, từ chối duplicate/unknown IDs/split, báo missing/failures và logits lỗi.
Xuất confusion matrix, precision/recall/F1/support, accuracy mẫu hợp lệ và
accuracy trên denominator đủ 8.544 (mẫu thiếu/lỗi tính không đúng), hai bộ logit
errors so full FP32 và so wire+FP32 tail, class agreement tương ứng.
Gate dùng lại **`200*(correct_fp32-correct_dpu) < 8544`**, tức drop <0,5 điểm
phần trăm; với baseline 8.393 correct, cần ít nhất **8.351 correct** và đủ mẫu.
Thiếu/lỗi bất kỳ → `INCOMPLETE_NO_ACCEPTANCE`, ngay cả khi count gate vẫn đạt.
Logit errors chỉ mô tả; không có threshold DPU tự đặt, không dùng FP32 <1e-3.
Output JSON và hashes là evidence có khai báo provenance; owner vẫn phải đối
chiếu artifacts thật khi nhận, không suy chữ ký hay raw execution từ JSON.

Tái tạo bộ input/reference tại máy nhận sau khi hydrate baseline/data đúng hash:

```powershell
& $py -B ml/scripts/week7_dpu_accuracy.py prepare --output .cache/week7-dpu-new-reference --splits 2 5 8
```

Muốn đánh giá thêm split s0…s9, chuẩn bị **thư mục mới** với `--splits` tương ứng;
s10 identity không phải phép đo accuracy DPU. Không ghi đè gói lần này.

## 6. Các kiểm tra thực sự chạy

Các hàng `delivery-*` dưới đây chạy trên **`08e4b4259a2757be7b663b88cc1c98607602d266`**,
với source SHA/log SHA, argv, cwd, exit và timestamps trong command receipts.

| Lệnh/receipt | Kết quả | Giới hạn |
|---|---|---|
| `review_week7_sv2.py --p1-package ... --p1-zip ...` / `delivery-audit` | PASS; 100 rows, 22 groups, export checksums, source/model/registry và P1 inputs khớp | Table audit + P1 input raw; không raw SV2 output/board mới |
| `test_week7_reconcile.py` / `delivery-tests` | 9/9, exit 0 | Synthetic validator fixtures; có full 8.544 IDs giả, không gọi hardware |
| `python -O -B ...test_week7_reconcile.py` / `delivery-tests-O` | 9/9, exit 0 | Kiểm gate không phụ thuộc Python assert |
| `week7_dpu_accuracy.py prepare ...` / `delivery-accuracy-prepare` | 8.544×3 input/reference, FP32 8.393 correct, exit 0 | Chưa có accuracy DPU |
| `demo_week7_nopeek.py ...` / `delivery-demo` | Ca toán, CE/dCor gradients s2/s5/s8 và loss PASS; weights giữ nguyên | Lượt chạy demo chuẩn bị/kiểm thử xác minh toán/wiring; demo GVHD có hồ sơ riêng |
| `nopeek-reuse.json` | 13 bindings khớp lịch sử | Tái sử dụng bằng chứng cũ, không gán thành smoke mới |
| `validate_delivery.py` / `delivery-validation.json` | PASS: 28 link nội bộ mới, 20 audit-input hashes, 7 prepared-source hashes, source/log pins; `git diff --check` exit 0 | Hai body báo cáo/checklist lịch sử giữ nguyên |

[Thư mục receipts](../ml/provenance/week7-reconcile-20261026/).
Các lượt phát triển/lỗi được giữ nguyên, tách khỏi `delivery-*`.

## 7. Còn chờ đúng đầu ra và owner

| Mục | Chờ ai /đầu ra cụ thể | Khi nhận thì thực hiện |
|---|---|---|
| Accuracy DPU | Trung/SV2: outputs 8.544×split, failures và provenance nêu ở §5 | Chạy evaluator; review confusion/per-class/logit errors, count gate và artifacts |
| Raw output audit /lineage đầy đủ | Trung/SV2: archive/response/NPY/runner/binary gốc nếu cần byte audit; quant_info/compile artifacts còn ngoài Git | Băm đối chiếu inventory đã có, kiểm parser→NPY→runner→response; không yêu cầu chạy lại nếu bytes hợp lệ |
| Numeric INT8/DPU | Kỳ Anh/Trung/GVHD theo thẩm quyền nhóm: chấp nhận sai số dựa trên full-test và quyết định ngưỡng logit nếu cần | Ghi quyết định riêng, không đổi baseline/threshold để hợp bộ nhỏ |
| H-02 ML I1 v2 | Kỳ Anh review [draft xác nhận ML](sv3_week7_ml_i1v2_confirmation_draft.md); Châu ghi nhận đúng quy trình | Ghi receipt/xác nhận có tên, không ký tự động |
| H-03 nonce/provisioning | Châu/SV1 và Trung/SV2: revision có thẩm quyền | Kiểm consumer theo revision; giữ registry cũ nguyên trạng |
| L-01 học hiểu/demo | Kỳ Anh và GVHD: buổi giải thích/demo thực tế | Dùng [runbook demo](sv3_week7_demo_guide.md), chỉ ghi đã demo sau khi diễn ra |
| Tuần 8 và sau | BLE central/reassembly/E2E 100 mẫu của SV1/SV2; thiết kế grid dài và attackers của SV3/GVHD | Mở nhiệm vụ riêng; không chặn phần toán/reference offline đã hoàn tất |

## 8. Tiếp nối ngày 28/10/2026 (không viết lại snapshot 26–27/10)

[Reconciliation mới có pin GitHub](sv3_week7_host_update_20261028.md) đối soát
main `02ad8c8` với bốn commit local; merge `32ea846` giữ nguyên lịch sử trên
`dev/ml-sv3`. SV1 tuần 7 PASS 9/9; SV2 đã có file pipeline KV260 và G2 s2
200/200, PR40 head `8d962095` vẫn mở. r2 đã `CONFIRMED` trên nhánh SV1
`549aa102` theo xác nhận trực tiếp Trung→Châu, main còn pending. Không sửa
contract/registry và không coi hai finding P2 evaluator đã sửa là blocker mở.

[Evidence host mới](../ml/provenance/week7-host-20261028/README.md) tách receipts
cũ. [Bộ chuyển Trung](sv3_week7_sv2_handoff_20261028.md) đóng từ reference có
sẵn, giữ manifest SHA. Không regenerate theo lệnh prepare lịch sử ở §5 trong
phiên này. Chưa có output DPU full-test thật đủ provenance để đánh giá;
E-05 `INCOMPLETE_NO_ACCEPTANCE`. H-02/L-01 có hồ sơ review/demo riêng;
quyết định nghiệm thu được ghi theo quy trình nhóm.
