# Báo cáo tiến độ SV3 Bùi Kỳ Anh tuần 7

**Người thực hiện:** SV3/Bùi Kỳ Anh, phụ trách Model/Privacy và NoPeek offline.
**Ngày lập bản kỹ thuật:** 21/10/2026, múi giờ Asia/Saigon.
**Ngày chuẩn hóa báo cáo tại root docs:** 22/10/2026.
**Chốt bằng chứng kỹ thuật:** implementation `6be51e3a5d6be8309ef87720e98ed4305352f467`,
delivery `aadf27bf87dbd291c2ab48323c4edaa67c651a2f`; nền
`3c56b657aa5003483810b307bb5b666201bb8897`. Cập nhật sau mốc chốt được ghi riêng
ở mục 9, không đổi nhãn thời điểm hoặc người thực hiện của bằng chứng gốc.

Phần độc lập tuần 7 **PASS trên host**: dCor, loss NoPeek, kiểm toán học/gradient,
chạy thử MIT-BIH thật và cấu hình chuẩn bị tuần 8. Chưa nghiệm thu runtime/accuracy
KV260, hiệu quả chống tấn công hoặc toàn hệ thống. Hai báo cáo tiền đề nằm tại
[tuần 5](sv3_ml_week5_report.md) và [tuần 6](sv3_ml_week6_report.md).

Quy ước: **YÊU CẦU DỰ ÁN** là tiêu chí nguồn; **QUYẾT ĐỊNH TRIỂN KHAI** là
lựa chọn công thức/config/code; **KẾT QUẢ QUAN SÁT** có log/manifest đối chiếu.
`PASS` chỉ cho phạm vi đã kiểm; `PENDING` là còn chờ; `BLOCKED` có dependency
cụ thể; `NOT VERIFIED` chưa có bằng chứng. Code/test PASS không thay học hiểu.

**YÊU CẦU DỰ ÁN:** hàm dCor đúng ít nhất ba ca ở tuần 7; quét NoPeek ba split
ở tuần 8. **QUYẾT ĐỊNH TRIỂN KHAI:** dùng R_n biased, thêm gradient checks và
smoke ngắn; chưa chạy lưới dài. **KẾT QUẢ QUAN SÁT:** các số liệu của mục 5 thuộc
đúng implementation pin, không phải một lần huấn luyện mới khi biên tập báo cáo.

**Vị trí báo cáo chính thức:** `main/docs/`. PR #35 đưa báo cáo và checklist
lên main trước phần code tuần 7. Code/config, kết quả và receipts được bàn giao qua
[PR #34](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/34);
các liên kết tương ứng giữ pin commit `1518943` để định danh bản đã review.
Việc công bố báo cáo không thay thế review code hoặc nghiệm thu KV260.

## 1. Mục tiêu, phiên bản và nguồn yêu cầu

- Nhánh: `sv3/week7-nopeek-20261021`, worktree
  `exports/sv3-week7-20261021`. Checkout cũ `sv3/fix-week3-sv2-linux-fp32` và các
  thay đổi đang có được giữ nguyên; không tái sử dụng checkout cũ để sửa code mới.
- Nền từ GitHub sau `git fetch origin --prune`:
  **`3c56b657aa5003483810b307bb5b666201bb8897`** (PR #32).
- Commit triển khai được các lệnh cuối chứng nhận:
  **`6be51e3a5d6be8309ef87720e98ed4305352f467`**. Commit bổ sung sau chỉ lưu
  tài liệu/kết quả/provenance; không đổi executable source đã kiểm.
- Tuân thủ `AGENTS.md` ở workspace và thư mục project tham chiếu; `sources/`
  chỉ đọc. Không sửa lịch sử Cline, không liên hệ hay ký thay thành viên.
- Nguồn phân công nằm trong
  `C:/Users/Admin/.codex/.chatgpt-projects/g-p-6aa0e9f8edd48191976f9b12cd86e2ff/sources/`.
  `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx`, mục A.3, giai đoạn 2,
  đặt **kiểm chứng dCor ở tuần 7**, **quét lambda cho ba split ở tuần 8**,
  mở rộng/fine-tune ở tuần 9–10. SHA-256:
  `75fcd76999af521a568b039c6983414217c59991d37b5591b85d211db927880d`.
- `Huong1_Bao_cao_trien_khai_3SV.docx`, bảng giai đoạn 2, nói “bắt đầu NoPeek”
  từ tuần 7. SHA-256:
  `60f83fa7c0779d11c888a8a104c5fa55be0c8c8b171f9d72e29cbba9efcc9a90`.
  Báo cáo này lấy tiêu chí chi tiết làm phạm vi nghiệm thu; chạy thử ngắn là phần
  bổ sung theo yêu cầu hiện tại, không chạy toàn bộ lưới dài.
- Đã đọc hai bản phân công nhóm, lộ trình, hướng dẫn chi tiết, báo cáo triển khai,
  quy ước `QUY_UOC_LAM_VIEC_VA_DINH_DANG_DU_AN_v1.0(2).txt`; đối chiếu các
  báo cáo SV1/SV2, hồ sơ P1 và contract hiện hành. Bản trích nội dung Word nằm ở
  `ml/docs/project_sources/week7/` cục bộ, bị Git bỏ qua, không sửa tài liệu gốc.
  Tài liệu không cung cấp toàn bộ hội thoại/lập luận trước đây; không suy diễn
  xác nhận thành viên từ phần lịch sử còn thiếu.

## 2. Phối hợp và trạng thái bàn giao tại mốc 21/10

[Snapshot truy vấn và PR](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/provenance/week7-nopeek-20261021/github-state.json)
lưu kết quả đọc GitHub, gồm PR, branch và các discussion đã truy vấn.

| Bằng chứng | Kết luận đúng phạm vi |
|---|---|
| [PR #30](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/30), merge `5c8f051`; source/evidence `f3675848` | Đã giao 50 vector P1 thật và ngữ nghĩa output trên host; release tuần 6 có checksum. |
| [PR #32](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/32), merge `3c56b65`; firmware `afa8887` | SV1 đã chạy MCU thật, 50/50 protect và unprotect; 1000/1000 BLE loopback với **laptop**. Không chứng nhận KV260. |
| [PR #27](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/27), head `d758a48d` | Báo cáo mới nhất tìm thấy của SV2 là tuần 4, biên dịch 10 tail. Nhánh `origin/dev/edge-sv2` vẫn ở `d758a48d3044a427d2fa8693400f3f6fe82e7219`, ngày 10/10. |
| `edge/quantize_tail.py` trên main, thay đổi sau PR27 ở `4efd34b` | Đã bỏ fallback ngẫu nhiên và bắt provenance checkpoint/calibration; không lấy báo cáo compile cũ làm chứng nhận chạy pipeline hiện hành. |

Đã kiểm lại **29 file** trong `results/week6/manifest.json` đúng raw SHA-256/size.
`build_check/default_source.json` và `mtu23_source.json` pin manifest vector
`d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36`.
`selftest_default.json` và `p1_vectors_50.csv` có đủ 50 record đạt. Đây là bằng chứng
SV1 dùng đúng gói, không chỉ là phát biểu trong PR. Không chạy lại MCU ở phiên này.

SV2 đã xác nhận sử dụng gói **FP32 tuần 3** trong báo cáo tuần 4. Chưa tìm thấy
xác nhận nhận/chạy **gói P1 50 vector tuần 6** trong báo cáo/nhánh Edge hay
discussion PR30/32/29/27 được truy vấn; không kết luận rằng SV2 chắc chắn chưa
nhận qua kênh khác. Các discussion trả về rỗng.

Hồ sơ SV1 phụ lục A.3 ghi gói P1 và ngữ nghĩa response SV3 đã bàn giao 16/10.
Tuy nhiên `contracts/i1_device_edge_packet_v2.md` §14 vẫn để hàng SV3 và SV2
“Chưa xác nhận”. SV3 còn bước **xác nhận chính thức tensor/quantization/response**;
bằng chứng kỹ thuật host đã có. Không tự điền chữ ký của Kỳ Anh.
Registry hiện hành vẫn `NOT_ACCEPTED` cho nonce runtime; bằng chứng MCU đã có
nhưng cần revision do đúng thẩm quyền Châu/Trung phê duyệt, không sửa tại chỗ.

## 3. Công việc đã làm và các file chính

Luồng baseline: **ECG chuẩn hóa → head → activation z_s → lượng tử/P1 → truyền →
unprotect/giải lượng tử → tail → 5 logits N,S,V,F,Q**. Các phần trên wire giữ nguyên.

- [distance_correlation.py](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/src/distance_correlation.py) đo phụ thuộc giữa
  ECG đầu vào và activation **trước lượng tử/P1**, dùng lúc huấn luyện.
- [nopeek.py](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/src/nopeek.py) cộng `CE + lambda1 * dCor(x,z_s)`. Gradient CE
  cập nhật head và tail, gradient dCor đi qua head. Không detach activation.
- [nopeek_data.py](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/src/nopeek_data.py) xác thực train/val theo provenance
  checkpoint đã duyệt. Không tái chia bệnh nhân, không fit lại normalization,
  không mở test NPY/metadata trong loader hay quá trình huấn luyện/validation.
- [run_week7_nopeek.py](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/scripts/run_week7_nopeek.py) tái sử dụng nguyên
  `MitdbBaselineCNN`, `CUTS`, `SHAPES`, `wrappers` hiện hành; wrapper dùng chung
  module với model nên `.train()` vẫn kích hoạt Dropout đúng như CE baseline.
  Không thêm hay đổi lớp. Mỗi `(s,lambda)` bắt đầu từ bản sao checkpoint gốc.
- [test_week7_nopeek.py](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/scripts/test_week7_nopeek.py) kiểm toán học,
  gradient, objective, xác thực dữ liệu và điều kiện từ chối ghi đè/chạy sai phạm vi.
- [log_week7_command.py](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/scripts/log_week7_command.py) lưu command, exit code,
  commit, hash source và raw stdout/stderr, không lấy exit code lệnh sau để che lỗi.

Không đưa quantization/P1 vào đồ thị huấn luyện thử, không sửa firmware SV1 hay
backend SV2. Đây là khung NoPeek offline, chưa mô phỏng sai số DPU hoặc mạng BLE.

## 4. Định nghĩa dCor và giới hạn số học

Dùng **R_n, không phải R_n²**, estimator mẫu biased với khoảng cách Euclid,
alpha=1 và double centering thông thường; giữ đường chéo, chuẩn hóa bởi n².
Với A/B là hai ma trận khoảng cách đã center:

`R_n² = mean(A*B) / sqrt(mean(A*A)*mean(B*B)); R_n = sqrt(R_n²)`.

Công thức đối chiếu [Székely–Rizzo–Bakirov, định nghĩa 4–5, (2.8–2.10)](https://arxiv.org/pdf/0803.4101).
Objective đối chiếu [NoPeek, (1) và phụ lục B](https://ar5iv.labs.arxiv.org/html/2008.09161):
chọn hệ số CE=1, hệ số dCor=lambda1. Phụ lục triển khai căn cuối, nên không
thay ngầm bằng R_n² dù phần đạo hàm của bài cũng bàn tới đại lượng bình phương.

Batch là trục 0: `[B,1,360] → [B,360]`; `[B,C,L] → [B,C*L]`; NC giữ `[B,C]`.
Chuẩn hóa số học bằng **một scalar dương cho toàn bộ mỗi input**, không chuẩn hóa
riêng kênh/mẫu. Chia hai ma trận center cho norm riêng rồi lấy tích vô hướng;
n² triệt tiêu, tránh nhân phương sai rất nhỏ/lớn. Không thêm epsilon làm lệch
estimator. Clip R_n² vào [0,1] chỉ để xử lý sai số dấu/chặn do số học.

Tensor có mọi quan sát giống nhau/variance khoảng cách bằng 0 trả **0 và gradient
0**; dùng nhánh trước phép chia/căn để tránh NaN. Chọn subgradient 0 ở covariance
không dương do số học. B<2, scalar, feature rỗng, NaN/Inf, dtype/device/batch
không khớp đều bị từ chối; chỉ nhận dense float32/float64. B=2 hợp lệ nhưng R=1
cho hai tập không hằng, không có ý nghĩa kiểm độc lập; smoke dùng B=32.
Autograd bậc một hỗ trợ gần như khắp nơi; không cam kết đạo hàm bậc hai hoặc
độ chính xác tùy ý gần suy biến. `cdist` tính trực tiếp tránh lỗi sqrt tại diagonal.

Ca độc lập dùng n=1024, mỗi bên một chiều, ba seed cố định. R_n mẫu hữu hạn
không bắt bằng 0. Không áp ngưỡng gần 0 của ca này cho ECG 360 chiều hoặc
activation hàng nghìn chiều ở B=32; không coi một giá trị dCor là bằng chứng riêng tư.

## 5. Kết quả kiểm chứng và chạy thử trên commit triển khai

Môi trường: Python 3.11.9, PyTorch 2.14.0+cu130, NumPy 2.4.6; smoke CPU một
thread, deterministic, MKLDNN tắt. Có kiểm đối chiếu CUDA cho giá trị/gradient dCor.

| Kiểm tra | Kết quả cuối và bằng chứng |
|---|---|
| Bộ tuần 7 | **19/19 PASS**, thường và `-O`; `tests-final.*`, `tests-final-O.*` trong provenance |
| x=x, shapes/strides | Gần 1; tolerance float32 2e-6, float64 1e-12 |
| Nhiễu độc lập | 0.0514481666; 0.0486176742; 0.0663937348; seed 7/30/20261021, ngưỡng cố định <0.12 |
| Tham chiếu độc lập | 0.7287557921168066 và 0.5568883710815936; sai số tối đa khoảng 2.22e-16, tolerance 1e-12 |
| Gradient | gradcheck cả hai input: eps 1e-6, atol 1e-5, rtol 1e-3; hằng/duplicate không NaN/Inf |
| Một bước SGD, ca toán | R_n 0.7814269659902954 → 0.7801803187694226 |
| I1 v2 hồi quy | **23/23 PASS**; `i1-regression-final.*` |
| I2 hồi quy | **5/5 PASS**; `i2-regression-final.*` |
| Bảo toàn snapshot lịch sử | **2.441 file tracked gốc không đổi byte nào tại pin 6be51e3/aadf27b**; không chứng nhận toàn checkout sau biên tập docs hoặc merge main |

Các file bằng chứng nằm trong
[`ml/provenance/week7-nopeek-20261021`](https://github.com/ChouPro205/Adaptive_Split_Inference/tree/151894367b0a35df83a0effd86961816ffc89942/ml/provenance/week7-nopeek-20261021).
[Review audit](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/provenance/week7-nopeek-20261021/review-audit.json) kiểm hash
log/source, đối chiếu hai lượt cuối và hash artifact thử nghiệm. Không dùng receipt
tuần 5 để chứng nhận code tuần 7.

Đã tái sử dụng cache cục bộ sau xác thực checkpoint
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`
và toàn bộ định danh dữ liệu từ provenance checkpoint. NPY/checkpoint hash raw;
CSV/JSON hash theo chính sách LF hiện có. Vì asset đầy đủ và đúng pin, không cần
tải lại release. `asset-reuse.json` ghi nguồn và hash. Test chỉ được sao chép/hash
để bảo toàn, không được đưa vào train/val hay chọn mô hình.

Smoke dùng seed 20261021, Adam lr=1e-4, **4 bước ×32 train**, **512 val** chọn
ngẫu nhiên cố định từ 81.094 train/15.388 val đã xác thực; cùng mẫu cho mọi run.
Mọi ID/row/patient/class của subset lưu tại `selected_samples.json`.

| Split | Gradient dCor riêng tới head, L2 | Val accuracy lambda=0 | Val accuracy lambda=0.5 | Macro-F1 tương ứng |
|---|---:|---:|---:|---:|
| s2 | 0.3737411201 | 81.8359% | 82.0313% | 0.31170 / 0.31315 |
| s5 | 0.6470656395 | 81.8359% | 82.2266% | 0.31170 / 0.31462 |
| s8 | 0.6242136955 | 81.8359% | 82.6172% | 0.31170 / 0.31762 |

Lambda=0 khớp **bit-exact loss, toàn bộ gradient và một bước SGD** với forward CE
đầy đủ trên model thật ở cả ba split; unit test còn kiểm cập nhật Adam. Test
lambda>0 kiểm `g_total - g_CE = lambda*g_dCor` và gradient dCor khác 0.
Mỗi run lưu 4 train +16 val batch: CE/dCor/total/accuracy; summary có confusion
matrix, precision/recall/F1 theo lớp. Không dùng bảng nhỏ này chọn lambda hoặc
kết luận accuracy cải thiện; không so loss/dCor của hai batch khác nhau như một
đường hội tụ. Các lớp hiếm có ít hoặc không có support trong subset.

Hai lượt cuối `smoke-final` và `smoke-final-repeat-O` cho **cùng toàn bộ số liệu
batch, IDs được chọn, metrics, kiểm gradient và hash tensor trạng thái cuối**.
Kết quả chính ở
[`summary.json`](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/results/week7-nopeek/smoke-final/summary.json) và
[`batch_metrics.json`](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/results/week7-nopeek/smoke-final/batch_metrics.json).
6 checkpoint mỗi lượt nằm ở `ml/artifacts/week7/<run>/`, ngoài Git; có hash/size
trong summary và metadata `EXPERIMENT_ONLY_NOT_APPROVED`, profile ID=null.

## 6. Cấu hình chuẩn bị tuần 8

[Cấu hình](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/configs/week8_nopeek_sweep.json) chứa lambda
`{0,0.1,0.5,1,2,5}` cho ba split, mỗi run khởi tạo lại từ checkpoint gốc.
Max 30 epoch/patience 5 theo val CE là **đề xuất**, chưa chạy. Test frozen không
dùng cho early stopping/chọn lambda. Cần thảo luận nhiều seed, batch size và mất
cân bằng lớp trước khi dùng kết quả cho bài báo.

| Split | Điểm cắt hiện hành | Lý do chọn | Xác nhận SV2 còn cần |
|---|---|---|---|
| s2 | `features.4`, `[B,16,180]`, 2.880 phần tử/mẫu | Head sớm sau pooling, đúng boundary P2 đã dùng trên Device | Chạy tail lai DPU+CPU thật và provenance xmodel |
| s5 | `features.11`, `[B,48,90]`, 4.320 phần tử/mẫu | Điểm giữa có mở rộng kênh, thể hiện kích thước không đơn điệu | Runtime cho các CPU subgraph và accuracy |
| s8 | `features.19`, `[B,64,22]`, 1.408 phần tử/mẫu | Head sâu, tail classifier; khác chi phí/tensor hai điểm trước | Chạy classifier DPU+CPU thật, không suy từ compile PASS |

PR27 báo s0..7 có 2 DPU+3 CPU subgraph, s8/9 có 1 DPU+2 CPU; đây là thông tin
biên dịch cũ, chưa chứng nhận runtime. Không chọn s0 cho regularizer train head vì
head identity không có tham số; s10 là logits/device-only, khác mục tiêu split.
Quét offline vẫn làm được khi chưa có SV2; chủ động để tuần 8 nhằm tránh huấn luyện
lại nếu tập split triển khai thay đổi. Không gắn toàn bộ NoPeek là BLOCKED_SV2.

## 7. Review và việc tiếp theo

Đã đọc toàn bộ diff source/config/tests, đối chiếu công thức, kiểm data binding,
mode train/eval, checkpoint copies, paths và kết quả sau sửa. Lỗi phát hiện đã sửa:
(1) test ban đầu bắt nhầm lớp exception của validator và đếm nhầm số file đọc;
(2) smoke đầu lưu xong một trọng số rồi lỗi vì `relative_to` với đường dẫn tương
đối; đã canonicalize path trước kiểm/ghi. Log lỗi ban đầu được giữ, không lấy chúng
làm PASS, không đổi tolerance toán để test qua. Các lượt cuối ở commit mới đã chạy lại.

Không còn finding về công thức, shape, gradient, rò train/val/test hoặc thay ngầm
baseline trong phạm vi đã kiểm. Còn các giới hạn theo mức độ:

- **Cao, ngoài phạm vi host:** chưa có inference/accuracy thật trên KV260; không
  nghiệm thu tích hợp hay DPU từ compile report/echo laptop.
- **Trung bình, chất lượng mô hình:** baseline có hạn chế lớp hiếm đã ghi trong
  đánh giá tuần 5; smoke ngắn không xử lý hoặc chứng minh cải thiện vấn đề này.
  Chưa có đánh giá tấn công nên chưa có kết luận bảo vệ riêng tư.
- **Thấp, hồ sơ:** hàng SV3 ở I1 v2 §14 chưa cập nhật dù chứng cứ response đã giao;
  nonce registry chưa có revision nghiệm thu. Một số contract còn link kế hoạch
  tuần 6 đã xóa, theo PR32; giữ nguyên vì source bindings lịch sử và xử lý ở revision
  hợp lệ tiếp theo, không sửa chuẩn để làm PASS.

[Checklist phụ thuộc đầy đủ](sv3_week7_dependency_checklist.md) tách owner, đầu vào,
điều kiện tiếp tục và phần tái sử dụng cho từng việc. Kỳ Anh cần trao đổi với Trung
về receipt P1, model/checkpoint/calibration/xmodel, runtime và profiling; đối soát
với Châu về I1 v2/registry; trình GVHD phạm vi tuần 8, split và thiết kế đánh giá.
Không tự gửi liên hệ trong phiên này.

Nếu SV2 chỉ sửa parser/layout/dequantize: giữ dCor, tests toán, objective và model
offline; chạy lại contract/integration và so logits sau sửa. Nếu checkpoint/split
thay đổi: giữ toán/tests/loader nguyên tắc nhưng cập nhật **experiment config có
phiên bản mới**, xác thực nguồn mới rồi chạy lại smoke/train cho split bị ảnh hưởng.
Đổi kiến trúc hoặc profile triển khai cần review và revision; không ghi đè artifact
hay gán trọng số NoPeek vào profile baseline hiện hành.

**Code/kiểm thử đạt không đồng nghĩa Kỳ Anh đã học hiểu.** Việc giải thích lại
estimator, batch, gradient, finite-sample bias và ý nghĩa riêng tư cần buổi trao đổi/
demo riêng; không đánh dấu phần học hiểu DONE tự động.

## 8. Deliverables và cách nghiệm thu

Từ root của worktree/checkout mới, dùng Python theo `ml/README.md`; nếu thiếu asset,
dùng workflow [setup tuần 5](../ml/scripts/setup_week5_delivery_v2.py) và
[hướng dẫn bàn giao](../ml/docs/week5_delivery_v2.md), giữ hash/pin chính thức.
Không sửa dataset để vượt verifier. Các lệnh sau phải dùng tên output mới:

```powershell
python -B ml/scripts/test_week7_nopeek.py
python -O -B ml/scripts/test_week7_nopeek.py
python -B ml/scripts/run_week7_nopeek.py --output ml/results/week7-nopeek/new-run --artifacts ml/artifacts/week7/new-run
```

Dùng `log_week7_command.py --name <tên-mới> --directory <thư-mục-evidence> --
<python> ...` để lưu đầy đủ log. Chỉ trên snapshot lịch sử `6be51e3`/`aadf27b`
nguyên trạng, có thể gọi hàm `audit()` của
`ml/provenance/week7-nopeek-20261021/audit_results.py` để kiểm lại; CLI từ chối
ghi đè `review-audit.json` đã có. Không dùng gate baseline nguyên trạng để chứng nhận
checkout đã sửa docs/merge main. Audit kiểm artifact thử nghiệm nên cần giữ hoặc
tái tạo đúng các artifact ngoài Git trước khi chạy lại toàn audit tại máy khác.

## 9. Cập nhật sau mốc chốt ngày 21/10

Review độc lập ngày **21/10**, tại implementation `6be51e3` và delivery `aadf27b`,
đã chạy lại 19 test thường và `-O` đều PASS;
tái hiện sáu run bằng full-model forward và activation hooks, không gọi smoke
runner/head-tail wrappers của tác giả. Toàn bộ 120 batch records, selected IDs,
metrics và hash trạng thái trọng số cuối khớp. Audit đọc lại xác nhận 2.441 file
baseline ở snapshot đã kiểm không thay raw bytes; 29 file evidence SV1 và 50
record P1 đúng. Evidence review được lưu ngoài Git ở thư mục project ChatGPT,
không coi là file đã publish trong repository này.

Ngày 22/10, GitHub main có thêm
[PR #33 của SV1](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/33),
merge `fedeee9db111dedf74ff4102fd3b320992602d35`: báo cáo marker/PPK2 tuần 7
PASS 9/9, peer laptop stub. Đây là cập nhật của SV1, không phải phép đo của SV3
và không chứng nhận KV260. Kết quả năng lượng chỉ dùng kiểm phương pháp ở phạm
vi SV1 công bố; không lấy làm Pareto của model NoPeek hoặc Table II hoàn chỉnh.
Trước quy trình tạo PR ngày 22/10, chưa thấy PR cho nhánh SV3 tuần 7;
nhánh remote vẫn `aadf27b`. Trạng thái và kiểm thử sau đồng bộ main được ghi trong PR.

Việc biên tập này bổ sung root-docs tuần 5/6, chuẩn hóa báo cáo tuần 7 và mục lục.
Không sửa code/config/tests, contract/registry, model/dataset, results/provenance
hoặc receipts. Mục lục `docs/README.md` là thay đổi tài liệu có chủ đích so với
baseline 3c56b65: vì vậy audit lịch sử yêu cầu 2.441 file nguyên trạng phải chạy
trên snapshot 6be51e3/aadf27b đúng pin, không gán kết quả đó cho toàn checkout
sau khi đã biên tập docs hoặc đồng bộ main mới. Không sửa audit để bỏ gate.

## 10. Trạng thái nghiệm thu

| Hạng mục | Trạng thái | Giới hạn/điều kiện |
|---|---|---|
| dCor, reference độc lập, suy biến và gradient | PASS | Host, R_n biased và batch policy ghi rõ |
| Loss NoPeek và wiring lambda=0/lambda>0 | PASS | Gradient tới head; không thay baseline tích hợp |
| Smoke s2/s5/s8 x lambda0/0,5 | PASS | 128 train/512 val mỗi run, không chứng minh hội tụ/privacy |
| Tái lập và bảo toàn snapshot kỹ thuật | PASS tại pin đã kiểm | 120 batch records và sáu state hashes khớp; audit lịch sử không chứng nhận docs/main mới |
| Cấu hình quét tuần 8 | PASS chuẩn bị | Chưa có runner huấn luyện dài hoặc grid đã chạy |
| KV260 runtime/accuracy và Device–Edge thật | PENDING | Cần đầu ra SV2 theo checklist |
| Xác nhận I1 v2, revision nonce registry | PENDING | Đúng người và change control; không tự ký thay |
| Đánh giá tấn công/riêng tư | NOT VERIFIED | Thuộc giai đoạn sau |
| Học hiểu/demo GVHD | NOT VERIFIED trong phiên này | Người dùng cần tự giải thích/demo |

## 11. Công việc chuyển tiếp

1. Đưa nhánh qua PR review của nhóm, giữ nguyên các SHA lịch sử đã pin; đồng bộ
   main mới theo workflow, không rebase/force-push để đổi lịch sử bằng chứng.
2. Chốt thiết kế quét tuần 8 với GVHD: seeds/batch, metrics và lớp hiếm; viết
   runner train dài riêng, chọn mô hình bằng validation, không dùng test để tuning.
3. Nhận SV2 xác nhận checkpoint/split chạy thật, xmodel/provenance và output;
   ưu tiên s2/s5/s8 để giảm chạy lại. Offline NoPeek không cần đợi đủ BLE/server.
4. Đánh giá DPU khi có backend thật; profiling và BLE end-to-end là các gate
   riêng. Dùng [checklist phụ thuộc](sv3_week7_dependency_checklist.md) tại mốc
   21/10 và cập nhật trạng thái bằng evidence mới, không sửa lịch sử kết quả.
5. Ghi xác nhận ML I1 v2 của Kỳ Anh, phối hợp Châu/Trung về registry; model
   NoPeek được duyệt phải có checkpoint/golden/version triển khai mới phù hợp.

Phiên chuẩn hóa ngày 22/10 chỉ chỉnh tài liệu. Các kết quả ML/MCU/DPU không được
gọi là đã chạy mới ở phiên biên tập báo cáo này.
