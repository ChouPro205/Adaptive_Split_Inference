# Protocol NoPeek v2 (M1): bản sẵn sàng khóa, kèm diff so với v1

Ngày 11/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa. Chưa chạy pilot, chưa chạy grid, chưa train trên MITDB, chưa mở DS2.**

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Protocol NoPeek v2 | `ml/configs/mitdb_m1_nopeek_protocol_v2.json` | `83cce64defefa979abcf8c31cc27daf9ae81604caae911acf0901cba3783cf35` |
| Bản trước (v1, không sửa) | `ml/configs/mitdb_m1_nopeek_protocol_v1.json` | `1e180b45258d4f9c6902aeee8ccfedd5de38f62b9bb4a2f16f9030391b72ebf4` |
| Plan v2 (9 pilot + 72 grid) | `ml/manifests/mitdb-nopeek-m1-v2/plan-manifest.json` | `e2e4e85856ed1d1861a771388d40de24c27c1ff6ffbfac2138ea275f76b650f9` |
| Runner v2 | `ml/scripts/nopeek_m1_v2.py` | `393b22292fba8a33cc5a594d960801697ce892b8a62275f2a01ac8ee86ef69ac` |
| Test v2 | `ml/scripts/test_nopeek_m1_v2.py` | `22b5207e260653831c4deae0c34fa51380c94c03e9c5f42229a1215222ddf4a2` |
| Tin review của SV1 ngày 09/11 (review evidence) | `ml/provenance/m1-sv1-evidence-20261111/tra_loi_Ky_Anh_PR44_20261109.txt` | `2207542f6e3d09603093c69c9e646327082fe6bda1df2fd1fa71587664e15328` |
| Tin cập nhật của SV1 ngày 10/11 | `ml/provenance/m1-sv1-evidence-20261111/tin_Ky_Anh_tuan10_20261110.txt` | `7fabd2d6b1623cb526130e536adc0a95df96b609729c3c3c3e3d6dc22734f69c` (SV3 tự tính, SV1 không công bố) |
| Bản chốt câu hỏi 03/11 (bản chép) | `ml/provenance/m1-sv1-evidence-20261111/sv1_chot_cau_hoi_SV3_20261103.txt` | `be5d1411a61bcd0dadc614dc9255cf524d8c5854a0fa6e984f9cfd504584a343` |
| Receipt mã nguồn, plan, smoke | `ml/provenance/m1-nopeek-v2-code-20261111/receipt.json` | xem `SHA256SUMS.txt` cùng thư mục |

Ba file của SV1 được chép nguyên byte. SHA của cả ba khớp với số đã có: SV1 công bố hai số `2207542f…` và `be5d1411…`; số `7fabd2d6…` do SV3 tính lúc nhận tin.

## 1. Thay đổi so với v1

Diff đầy đủ nằm trong `ml/provenance/m1-nopeek-v2-code-20261111/diffs/`, gồm diff dòng của protocol, runner và test, cùng `compare-v1-v2.txt` (diff theo khóa JSON và so 81 file cấu hình run).

| # | Mục | v1 | v2 | Nguồn | Đổi giá trị cấu hình run? |
|---|---|---|---|---|---|
| 1 | `training.precision` | cuDNN TF32 bật (mặc định PyTorch), matmul TF32 tắt | Tắt cả cuDNN lẫn matmul, cho mọi run và mọi lượt đánh giá: validation, R_n, tấn công, DS2 | SV1 09/11 mục 4 điểm 5 | **Có**: `cudnn_allow_tf32` đổi từ true sang false ở cả 81 cấu hình |
| 2 | `initialization` | — | Thêm dòng SV1 yêu cầu: "A được train với cuDNN TF32 bật; điều này không làm thay đổi A". Ghi rõ lý do vẫn giữ kiểm epoch 0 | SV1 09/11 mục 4 điểm 5 | Không |
| 3 | `pilot.after_pilot` | Gửi receipt cho SV1, grid chạy "sau receipt" | Nếu luật chọn được LR an toàn thì chạy grid ngay, không chờ SV1; receipt pilot gửi cùng lúc. Chỉ dừng khi không LR nào an toàn | SV1 09/11 mục 4 điểm 2 | Không |
| 4 | `package_B_split_set`, `extension_stage` | Mở rộng s "theo protocol riêng" | Tập s mở rộng (fine-tune tail, gói B) = {2, s_m}, s_m theo luật điểm cắt giữa; grid giữ {2, 4, 5, 8}; số flash; không lượng tử trọng số; s8 chỉ chạy offline | SV1 10/11 mục 3 | Không |
| 5 | `source_bindings` | Bản chốt 03/11 trỏ vào `docs/inbox/` (không có trong repo) | Thêm tin 09/11 và 10/11. Bản chốt 03/11 trỏ vào bản chép trong provenance | SV1 09/11 mục 5 | Không |
| 6 | Định danh | — | `protocol_id`, `status`, `predecessor`, `changes_from_v1`, `execution_in_this_round` | — | Không |

Chỉ mục 1 làm đổi cấu hình run; đó là điểm 5. Mục 2–5 chép lại các quyết định của SV1 trong tin 09/11 và 10/11, mục 6 chỉ là định danh. Trong 103 lá JSON của v1, 91 lá giữ nguyên.

SV1 viết: "Nếu diff chỉ có điểm 5 thì không cần gửi lại mình trước khi khóa." Diff v2 có thêm mục 2–6, nên SV3 cần quyết có gửi lại SV1 trước khi khóa hay không.

## 2. Giữ nguyên (SV1 đồng ý điểm 1–4 ngày 09/11)

- Chính sách fine-tune giống A: sampler K-cân bằng, CE không trọng số, AdamW, batch 256, dropout bật khi train; LR hằng; 10 epoch cố định, không dừng sớm.
- Pilot: 3 LR {1e-5; 3e-5; 1e-4}, 9 run, luật chọn LR như v1.
- Grid: s ∈ {2, 4, 5, 8} × λ ∈ {0; 0,1; 0,5; 1; 2; 5} × 3 seed = 72 run, có kiểm tất định ở λ = 0.
- Ngưỡng tiện ích (`Fraction`, 19/20 × A), cách chọn epoch, chọn λ, seed triển khai, quy tắc sụp lớp, thống kê, báo đường λ = 0 trước khi tính Π, luật điểm cắt giữa: giữ nguyên văn v1.

## 3. Runner v2 khác v1 ở đâu

Runner v1 gắn cứng protocol v1 và bật cuDNN TF32, nên v2 là file mới (`git diff` trong `diffs/runner-v1-v2.diff`).

- **Đường dẫn và kiểu khóa mới:** `PROTOCOL`, `PLAN_DIR` trỏ sang v2; `AUTH_TYPE = M1_NOPEEK_V2_LOCK_AND_TRAIN_AUTHORIZATION`.
- **`set_precision`:** tắt TF32 bằng `torch.backends.cudnn.allow_tf32` và `torch.backends.cuda.matmul.allow_tf32` (cùng cách với script DS2), trước khi dựng mô hình. Cấu hình nào có TF32 bật thì dừng trước khi tạo thư mục output. Mỗi run ghi vào `attempt-identity.json` cả hai cờ trên và hai giá trị `fp32_precision` của API mới.
- **`require_authorization`:** ngoài các điểm v1 đã kiểm, file khóa phải có `review_evidence_path` đúng bằng file tin 09/11 mà protocol khai báo, và SHA của file đó phải bằng `review_evidence`. Đây là cách SV1 yêu cầu cho script DS2 (mục 3c): ràng buộc bằng đường dẫn và SHA của một file có trong repo, và script tự kiểm SHA.
- **Chế độ mới `run-pilot-grid`:** chạy pilot, ghi `pilot-decision.json`, nếu `PILOT_LR_CHOSEN` thì chạy grid ngay với LR đó, nếu không thì dừng và ghi `NOT_STARTED_NO_SAFE_LEARNING_RATE`. Các chế độ `run --stage pilot|grid` của v1 vẫn còn.
- **Phần chọn không đổi:** `macro_f1_exact`, `passes`, `collapsed`, `select_epoch`, `choose_pilot`, `choose_grid`, `lambda0_report`.

## 4. Đã làm và đã kiểm

Python 3.11.9, torch 2.14.0+cu130, RTX 5060. Mọi lệnh gọi với `-B`; log nằm trong `ml/provenance/m1-nopeek-v2-code-20261111/logs/`.

| Lệnh | Exit | Kết quả |
|---|---|---|
| `nopeek_m1_v2.py prepare` | 0 | Plan `e2e4e858…`, 81 cấu hình |
| `nopeek_m1_v2.py preflight`, chế độ thường và `-O` | 0, 0 | `PASS_PREFLIGHT_NO_MODEL_NO_FIT_NO_DS2`, 81 run; hai output trùng byte |
| `test_nopeek_m1_v2.py`, chế độ thường và `-O` | 0, 0 | 17 test: 9 test của v1 và 8 test mới (TF32, review evidence, luồng pilot→grid) |
| `nopeek_m1_v2.py smoke --epochs 2` trên dữ liệu ngẫu nhiên | 0 | `SMOKE_PASS_RANDOM_DATA_NOT_MITDB`; λ = 0 trùng bit giữa s2 và s8; λ = 5 có cập nhật trọng số; identity ghi `cudnn_allow_tf32: false`, `matmul_allow_tf32: false` |
| `tf32_probe.py default` và `off` | 0, 0 | Xem dưới |
| `compare_v1_v2.py` | 0 | Run id và thứ tự giống v1; mỗi cấu hình chỉ khác `cudnn_allow_tf32` và `protocol_sha256` |

**Probe TF32.** Đầu vào ngẫu nhiên có seed, chạy qua checkpoint gói A, không đọc MITDB và không train gì. Probe so CUDA với CPU:

| Chế độ | max \|logit CPU − CUDA\| | Lệch tương đối lớn nhất của gradient CE | Nhãn argmax |
|---|---|---|---|
| Mặc định (cuDNN TF32 bật) | 4,0e-3 | 1,0e-4 | trùng |
| `set_precision` của runner (TF32 tắt) | 5,2e-6 | 1,0e-6 | trùng |

Probe cho thấy runner tắt được TF32 thật, cả ở lượt chạy xuôi lẫn ở gradient. Probe không nói gì về chất lượng mô hình. Smoke cũng cho thấy cờ có tác dụng khi train: R_n của epoch 0 trùng smoke v1, còn R_n của epoch 1–2 lệch ở chữ số thập phân thứ 6 (ví dụ epoch 1: 0,9220593 ở v1 và 0,9220602 ở v2).

## 5. Chưa kiểm

- Chưa có run nào trên MITDB; cần file khóa ở mục 6.
- Chưa kiểm epoch 0 = A trên validation thật bằng đường code của runner. Bước này chạy ở run đầu tiên của pilot, trước mọi lần cập nhật trọng số. Dry run của script DS2 (TF32 tắt) đã cho ra lại đúng confusion của A.
- Chưa đo thời gian chạy thật của pilot và grid.
- Tài liệu này không có số liệu chất lượng mô hình. Preflight, smoke và test đạt chỉ xác nhận ràng buộc và luồng chạy.

## 6. Khóa: SV3 tự lập file, runner kiểm các trường sau

Như M1 v4: `approved_by` là SV3, thẩm quyền là SV1, review evidence là tin 09/11. Runner chỉ nhận file khóa có:

- `type` = `M1_NOPEEK_V2_LOCK_AND_TRAIN_AUTHORIZATION`, `allow_training` = `true`;
- `protocol_sha256` = `83cce64defefa979abcf8c31cc27daf9ae81604caae911acf0901cba3783cf35`;
- `plan_manifest_sha256` = `e2e4e85856ed1d1861a771388d40de24c27c1ff6ffbfac2138ea275f76b650f9`;
- `approved_by` không rỗng;
- `review_evidence` = `2207542f6e3d09603093c69c9e646327082fe6bda1df2fd1fa71587664e15328` và `review_evidence_path` = `ml/provenance/m1-sv1-evidence-20261111/tra_loi_Ky_Anh_PR44_20261109.txt`.

Plan đã ràng buộc SHA của 10 file nguồn; preflight kiểm lại chúng, cùng các mảng train/val, metric policy và tập con dCor, trước mỗi stage.

Lệnh chạy sau khi khóa:

```
python -B ml/scripts/nopeek_m1_v2.py run-pilot-grid --output ml/data/runs/<thư mục mới> --authorization <file khóa>
```

## 7. Bước tiếp theo

1. Khóa, rồi chạy `run-pilot-grid`. Gửi SV1 receipt pilot ngay khi grid bắt đầu.
2. Grid xong: chạy `lambda0-report` và `analyze-grid`, gửi SV1 đường macro-F1 theo epoch của λ = 0 cùng receipt grid, trước khi tính Π.
3. Lập attack protocol v2. Attack protocol v1 đang ràng buộc SHA của NoPeek v1 (`1e180b45…`), nên bản v2 phải trỏ sang NoPeek v2.
