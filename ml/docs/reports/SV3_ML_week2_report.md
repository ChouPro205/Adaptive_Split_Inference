# SV3 ML — Week 2 Report

Báo cáo lịch sử SV3/Bùi Kỳ Anh, lập ngày 2026-09-25 tại checkout `f08ccb5`, nhánh `docs/sv3-week1-week2-reports`. **Historical Week 2 state** lấy từ implementation/evidence/review của PR #7, tích hợp ở `953b2fc`. **Current repository state** lấy từ `contracts/` tại checkout audit; mục “Contract decisions for post-Week-2 phases” tách riêng quyết định ngoài baseline Week 2. Không retrain, regenerate dataset, export hay thực hiện Week 3 trong phiên này.

Lưu ý niên đại quan trọng: Git cho thứ tự main `e26e632` (#8) → `953b2fc` (#7) → `7773b36` (#9). PR #8 tích hợp trước PR #7, dù nội dung là handoff cho giai đoạn sau Week 2. Vì vậy không ghi sai rằng cả #8 và #9 đều merge sau #7. Chi tiết timestamp và parent ở mục 19 và phần contract riêng.

## 1. Week 2 objective

**PROJECT REQUIREMENT:** tài liệu local `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx`, A.3, hàng Tuần 2:

> Huấn luyện 1D-CNN baseline (8–12 lớp, < 250k tham số). Ràng buộc: phải chạy được trên MCU.

Tiêu chí: **“Accuracy ≥ 98% trên MIT-BIH 5 lớp AAMI; mô hình < 1 MB”**. Hàng Tuần 3 mới yêu cầu chốt kiến trúc/số lớp L, xuất `.h` và ba bên cùng kết quả trên 20 mẫu. Báo cáo triển khai ba SV, mục 2.2, ghi train baseline MIT-BIH ở Tuần 2, nhưng đặt đạt accuracy ≥98%/chốt kiến trúc ở Tuần 3. Báo cáo này dùng tiêu chí chặt hơn của hướng dẫn chi tiết để audit Week 2, đồng thời ghi sự khác nhau giữa hai nguồn, không âm thầm đổi lịch.

I2 và I3 có hạn Tuần 2 trong bảng interface của báo cáo triển khai và phân công: I2 từ SV3 → SV1/SV2, API/key/nonce/vectors; I3 tất cả → GV, schema có đơn vị. Hoàn thành baseline ML không tự hoàn thành hai interface này.

Nguồn local có tại `ml/docs/project_sources/requirements/`, bị Git ignore. Hash bản đọc và phân biệt nguồn yêu cầu với evidence versioned được ghi ở [Week 1, mục 12](SV3_ML_week1_report.md#12-git--provenance-evidence). **IMPLEMENTATION DECISION:** quy ước lớp có học là Conv1d/Linear, mô hình cụ thể và hyperparameter ở mục 3–4. **OBSERVED RESULT:** manifest và metrics ở mục 6–7. Thiết kế ops thuận lợi cho MCU không đủ chứng minh đã chạy trên MCU.

## 2. Inputs inherited from Week 1

[Loader](../../src/mitdb_week2_data.py) đọc đúng config Week 1, patient manifest, normalization và processed manifest. X lưu `(N,360)` float32, khi đưa vào model chỉ `unsqueeze(1)` thành `(N,1,360)`; y int64, thứ tự `N/S/V/F/Q=0/1/2/3/4`.

| Split | Patients | Records | Beats |
|---|---:|---:|---:|
| Train | 34 | 35 | 81,094 |
| Validation | 7 | 7 | 15,388 |
| Test | 4 | 4 | 8,544 |

Giữ seed 30, patient-wise split và train mean/std `-0.2912026352134608` / `0.45653058276514263`. Loader kiểm hash từng artifact, finite/dtype/shape, nhãn với metadata, record/patient assignment và leakage. **Không re-split, không refit normalization, không đổi phân bố test.** PTB-XL chỉ được kiểm lại dữ liệu; baseline này không train PTB-XL.

| Ràng buộc dữ liệu | SHA-256 đã ghi trong run |
|---|---|
| Week 1 config | `f5d050686b9d4816052631380b81f0c4671faf1dc648f1d9c02b4c3dc3be0b54` |
| Patient manifest | `27b07a0a4fcaac010291fd088c702e9eea1899ed73c6cef618404bafd3c116fe` |
| Normalization | `37d42ff2cbacc44f268046a62c392d2b9676c2c49936ac4188207745edd2d48c` |
| Processed manifest | `f712c83d46d71ac6af75b7138668d8918eef87a4ddfeab8e8b5310ced2c44a3c` |

Chín hash X/y/metadata nằm trong [week2_run_manifest.json](../../provenance/week2_run_manifest.json), đồng nhất identifier Week 1. Không sửa manifest đó để khớp báo cáo.

## 3. Candidate model architecture

Nguồn: [mitdb_baseline_model.py](../../src/mitdb_baseline_model.py), local `architecture.json` được hash trong manifest. Candidate `mitdb_week2_cnn_v1`, chưa architecture freeze cho Week 3.

| Learned layer | Module | In → out | Parameters |
|---:|---|---|---:|
| 1 | `features.0`, Conv1d | 1 → 16 | 96 |
| 2 | `features.2`, Conv1d | 16 → 16 | 1,296 |
| 3 | `features.5`, Conv1d | 16 → 32 | 2,592 |
| 4 | `features.7`, Conv1d | 32 → 32 | 5,152 |
| 5 | `features.10`, Conv1d | 32 → 48 | 7,728 |
| 6 | `features.12`, Conv1d | 48 → 48 | 11,568 |
| 7 | `features.15`, Conv1d | 48 → 64 | 15,424 |
| 8 | `features.17`, Conv1d | 64 → 64 | 20,544 |
| 9 | `classifier.2`, Linear | 1,408 → 32 | 45,088 |
| 10 | `classifier.4`, Linear | 32 → 5 logits | 165 |

Mỗi Conv dùng kernel 5, padding 2, stride 1, dilation 1, groups 1, bias; có ReLU sau mỗi Conv. MaxPool1d kernel/stride 2 sau từng cặp, nên chiều dài `360→180→90→45→22`. Flatten `64×22=1408`, Dropout 0.2, Linear 32/ReLU, Linear 5. Không có BatchNorm trong candidate này.

Tổng **10 learned layers, 109,653 trainable parameters**, FP32 mathematical parameter footprint `109653×4=438612` bytes = `0.4182929992675781 MiB`. ReLU, MaxPool, Flatten, Dropout không có tham số học và không được cộng vào 10 lớp. Ops Conv/ReLU/Pool/Linear và dense nhỏ là lựa chọn hướng MCU. Footprint này chỉ tính tham số, không phải peak RAM, workspace, firmware Flash hay chứng nhận CMSIS-NN chạy được; MCU execution: **NOT VERIFIED FROM REPOSITORY EVIDENCE**.

## 4. Training configuration

Nguồn chuẩn: [mitdb_week2_baseline.json](../../configs/mitdb_week2_baseline.json), source trainer và `training_config.json` local.

| Setting | Giá trị thực |
|---|---|
| Seed | 30; Python/NumPy/PyTorch determinism trong trainer |
| Device | `auto`; historical run dùng CUDA, RTX 5060 |
| Torch threads / batch size | 4 / 256 |
| Optimizer | AdamW |
| Learning rate / weight decay | 0.001 / 0.0001 |
| Loss | CrossEntropyLoss |
| Scheduler | ReduceLROnPlateau, mode `max`, factor 0.5, patience 4; theo validation accuracy |
| Epoch cap / early stopping | 40 / 10 epoch không cải thiện nghiêm ngặt validation accuracy |
| Dropout | 0.2 |
| Class weighting / augmentation | none / none |
| Sampler | `shuffle_train_only`; không replacement sampler hoặc oversampling |
| Checkpoint selection | `validation_accuracy`, chỉ thay khi accuracy cao hơn |

Loss/sampler không cân bằng lớp là đặc điểm baseline được giữ nguyên khi audit; không ngầm thêm weighting để che hạn chế S/F/Q. Môi trường historical run: CPython 3.11.9, PyTorch 2.14.0+cu130, CUDA 13.0 theo [baseline evidence](../week2_baseline.md).

## 5. Model-selection methodology

```text
fixed train → train mỗi epoch
            → evaluate validation ở eval/inference mode
            → giữ checkpoint có validation accuracy tốt nhất
            → dừng theo patience/cap
            → load checkpoint đã chọn
            → evaluate held-out test
```

Trainer chỉ dùng validation cho scheduler, early stopping và checkpoint. Khi hòa accuracy, strict `>` giữ epoch đầu. Run chọn epoch 3 trong 13 epoch đã chạy. `metrics.json` ghi `selection_metric=validation_accuracy`, `test_evaluated_after_selection=true`; verifier đối chiếu epoch đầu có validation maximum với history/checkpoint/manifest.

Test không chọn model trong control flow; review docs ghi không tuning theo test và giữ nguyên model/config. “Test evaluated once” nghĩa là một lần trong **training run sau selection**; các lần post-run verifier có đánh giá lại để đối chiếu metrics, không phải test chỉ từng được đọc đúng một lần trên toàn bộ lịch sử. Không có bằng chứng mọi thử nghiệm ngoài repository; cam kết tuyệt đối không có thử nghiệm ngoài log: **NOT VERIFIED FROM REPOSITORY EVIDENCE**.

## 6. Week 2 result

Nguồn: manifest versioned, `week2_baseline.md`, `pr7_review_body.md`, và `ml/data/week2/mitdb_baseline/metrics.json` local có hash đối chiếu manifest trong audit tài liệu.

| Metric | OBSERVED RESULT |
|---|---:|
| Epoch đã chạy / selected epoch | 13 / 3 |
| Train accuracy tại epoch được chọn | 0.9770636545243792 = 97.706365% |
| Validation accuracy | 0.8448791265921497 = 84.487913% |
| Validation macro F1 / weighted F1 | 0.3046693137315278 / 0.8082875813111078 |
| Test accuracy | 0.9822097378277154 = 98.220974%; 8,392/8,544 |
| Test macro F1 / weighted F1 | 0.38259483458569765 / 0.9857395113242444 |
| Parameters / mathematical FP32 bytes | 109,653 / 438,612 |
| Serialized state dict / full checkpoint bytes | 445,495 / 450,551 |

Train metric là aggregate trong epoch huấn luyện do `train_epoch` trả về, không phải một lần eval lại toàn bộ train bằng final selected weights. Serialized sizes có overhead PyTorch nên không bằng `params×4`; cả ba số đều nhỏ hơn 1,000,000 bytes. Không biến các số này thành kích thước ONNX hoặc firmware.

## 7. Per-class results and scientific limitation

Confusion matrix test, hàng = true, cột = predicted, thứ tự N/S/V/F/Q:

```text
       N    S    V   F   Q
N   8020   67    8   0   7
S     13    0    0   0   0
V     48    3  372   1   2
F      0    0    1   0   0
Q      2    0    0   0   0
```

| Class | Test support | Test precision | Test recall | Test F1 | Validation support / recall |
|---|---:|---:|---:|---:|---|
| N | 8,102 | 0.992206 | 0.989879 | 0.991041 | 13,003 / 0.942782 |
| S | 13 | 0 | **0** | 0 | 1,493 / 0.002679 |
| V | 426 | 0.976378 | 0.873239 | 0.921933 | 876 / 0.842466 |
| F | 1 | 0 | **0** | 0 | 11 / 0 |
| Q | 2 | 0 | **0** | 0 | 5 / 0 |

Validation confusion matrix cùng thứ tự:

```text
N  12259   4  721  1  18
S   1380   4  109  0   0
V    133   2  738  0   3
F     10   0    1  0   0
Q      1   0    4  0   0
```

**Overall accuracy >=98% satisfies the formal Week 2 acceptance criterion, but does NOT establish robust five-class or clinical generalization.**

Test có 8,102/8,544 beat lớp N, S/F/Q đều recall 0; F/Q support 1/2 không đủ đánh giá ổn định. Validation có 1,493 S, chỉ đúng 4; test chỉ 13 S và không đúng mẫu nào. Sự khác nhau về class/patient composition giúp giải thích tại sao test accuracy cao hơn validation nhiều; không có cơ sở kết luận model tổng quát hóa tốt hơn trên mọi bệnh nhân mới. Macro F1 thấp phản ánh thất bại lớp thiểu số mà weighted F1/overall accuracy có thể che đi. Không đổi split hoặc tune theo test sau khi thấy kết quả này.

## 8. Files created or modified

Đây là file thay đổi trong PR #7, đối chiếu `git show --stat 953b2fc` (13 file).

| File | Purpose |
|---|---|
| `ml/configs/mitdb_week2_baseline.json` | Hyperparameters cố định |
| `ml/src/mitdb_baseline_model.py` | Candidate và architecture metadata |
| `ml/src/mitdb_week2_data.py` | Hash-bound fixed Week 1 loader |
| `ml/src/train_mitdb_baseline.py` | Training, validation selection, artifacts/provenance |
| `ml/src/test_week2_baseline.py` | Ba pre-training tests: shape/size, fixed data, eval không đổi weights |
| `ml/src/verify_week2_baseline.py` | Post-run hash/source/checkpoint/metrics validation |
| `ml/src/test_week2_provenance.py` | Isolated clean/dirty train và verify gates |
| `ml/docs/week2_baseline.md` | Methodology, commands, observed result |
| `ml/docs/pr7_review_body.md` | Review fixes, negative evidence, interface limitations |
| `ml/provenance/week2_run_manifest.json` | Preserved four-hash run evidence |
| `ml/README.md` | Entry point tới baseline |
| `contracts/I2_SV3_provisional_interface.md` | Historical I2 approval draft; hiện tại là pointer sau #9 |
| `contracts/I3_SV3_input.md` | Consulted SV3 input, schema còn OPEN |

`week1_common.py`/`mitdb_common.py` là dependencies được thêm vào gate, **không phải source được sửa trong PR #7**. Files I2 reference hiện tại do #9 thêm, không tính vào 13 file Week 2.

## 9. Reproducibility design

Thứ tự đúng là Week 1 read-only checks → pre-training tests → historical training → post-run verification. Pre-test chỉ cần data/source/config, không phụ thuộc checkpoint chưa tạo; post-verifier mới cần artifact. Trong phiên báo cáo không chạy trainer hoặc Week 1 orchestrator vì chúng ghi artifact.

Run manifest nối source SHA/hashes, dataset IDs, config, file sizes/hashes và headline metrics. Post-verifier kiểm architecture, state dict/checkpoint bằng nhau, epoch selection, confusion matrix, per-class metrics và không cập nhật parameter/gradient. Phải dùng device type được ghi: historical CUDA run cần CUDA khi yêu cầu exact predictions. Lỗi CPU làm đổi một N borderline được docs ghi lại; load được FP32 weights trên CPU không đồng nghĩa confusion matrix luôn bit-identical.

Source gate current kiểm six-file tracked/clean so với HEAD trước artifact loading/evaluation. Unrelated dirty/untracked report không làm gate science fail. Hash file source Week 2 là raw bytes như trainer thực hiện; không áp nhầm policy LF-normalized của dataset configs Week 1 cho mọi hash.

## 10. Historical run provenance

Historical source commit: **`8e98a0e4851abc979feb5fd5b97ece612b02cfaa`**. Manifest ghi **`scientific_sources_clean=true`, `worktree_dirty=true`**. Bốn source/config lúc run tracked và sạch; rộng hơn còn unrelated/evidence files theo docs. Không viết lại thành worktree clean chỉ vì scientific subset clean.

| Historical scientific file | Recorded SHA-256 |
|---|---|
| `ml/configs/mitdb_week2_baseline.json` | `273a563af79126c6ed6762c4bd01a186de055b6dea390688eefcf7522ae2e5e3` |
| `ml/src/mitdb_baseline_model.py` | `520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14` |
| `ml/src/mitdb_week2_data.py` | `363f5298e4e723cac19e15e062346f24c808820fe180c292d25372574a2ba907` |
| `ml/src/train_mitdb_baseline.py` | `a0fa0becf2539be37db9105eccb60d8ded8c25fae04d36fdda04ce6f82446152` |

Run cũ chỉ có **bốn hash**. Six-file policy xuất hiện trong review `525755f`; không retroactively gắn thêm helper hashes hoặc đổi `source_git_sha` sang squash commit `953b2fc`. Checkpoint/manifest cũ giữ nguyên. Source trainer hiện tại từ chối overwrite `week2_run_manifest.json` đã có.

## 11. Provenance review and fixes

Review nhận ra `week1_common.py` và `mitdb_common.py` là transitive executable dependencies: loader có thể đổi hành vi dù bốn file trực tiếp không thay. Fix tại `525755f` mở rộng `SCIENTIFIC_SOURCE_FILES` lên sáu file, tạo `require_clean_scientific_sources()` dùng chung train/verify, từ chối helper dirty trước khi dùng data/artifact.

`--historical` giới hạn ở đúng commit `8e98a0e...`: kiểm bốn hash với Git blobs, giữ `worktree_dirty=true`, model/data/config hiện tại không đổi; kiểm hai helper với commit cũ như **kiểm hiện tại**, không giả chúng đã được run cũ hash. AST của `evaluate`, `classification_metrics`, `set_determinism` phải giữ phép tính. Trainer hash đã đổi bởi review được phân biệt rõ với historical trainer hash. Đồng thời gate six-file hiện tại vẫn phải sạch. Default verifier dành cho evidence sáu hash của run mới, không dùng để ép manifest lịch sử thành schema mới.

## 12. Negative-test evidence

Nguồn thực thi lịch sử: [PR #7 review evidence](../pr7_review_body.md); cơ chế được đối chiếu với [test source](../../src/test_week2_provenance.py).

| Case | Child command trong isolated snapshot | Exit/result |
|---|---|---|
| Clean source, train gate | `test_week2_provenance.py --gate train` | 0, PASS |
| Clean source, verify gate | `test_week2_provenance.py --gate verify` | 0, PASS |
| Dirty `week1_common.py` | `--gate train` | 1, expected rejection |
| Dirty `week1_common.py` | `--gate verify` | 1, expected rejection |
| Dirty `mitdb_common.py` | `--gate train` | 1, expected rejection |
| Dirty `mitdb_common.py` | `--gate verify` | 1, expected rejection |

Child invocation thực do test tạo là `[sys.executable, '-B', 'ml/src/test_week2_provenance.py', '--gate', gate]`, cwd repo tạm. Lỗi phải đúng từng path:

```text
ERROR: Scientific source/config differs from HEAD: ml/src/week1_common.py
ERROR: Scientific source/config differs from HEAD: ml/src/mitdb_common.py
```

Test thêm harmless comment lần lượt, restore bytes trong `finally`, kiểm Git diff clean sau mỗi helper và kiểm helper thật chưa đổi. Optional `--verify-historical-artifacts` copy evidence sang clean snapshot, kiểm historical artifacts; không mở training job. Docs ghi bốn rejection đúng và command cha exit 0; không tính bốn exit 1 này là suite thất bại.

## 13. Artifact inventory

Sáu artifact local/ignored nằm tại `ml/data/week2/mitdb_baseline/`. Bảng chép size/hash từ manifest versioned; phiên audit đã đọc JSON và đối chiếu file bytes, không load/retrain model.

| Artifact path | Bytes | SHA-256 |
|---|---:|---|
| `ml/data/week2/mitdb_baseline/training_config.json` | 661 | `52cc1cb425ecdee5ec0996f8dcf3cad3a7cfc8cf1407427835e6a712875a525c` |
| `ml/data/week2/mitdb_baseline/architecture.json` | 2,438 | `f82aca937259873f9c3a9c2ba57ddb6f9c601bed9d12e5fbc5174575a3b7e44d` |
| `ml/data/week2/mitdb_baseline/history.json` | 22,063 | `cde775d79ec6f381176cff192853f28b6e0bd260842fc230733244972f3ec3db` |
| `ml/data/week2/mitdb_baseline/metrics.json` | 8,188 | `06101e61c9e423fc3e3fcbf843a4b32b3dd7616581b3cb63bea374afa5ba27a6` |
| `ml/data/week2/mitdb_baseline/best_state_dict.pt` | 445,495 | `f9d5763da844ab5ccdfc36a0899e0763501431c423f51ef1ce4e06e14769453f` |
| `ml/data/week2/mitdb_baseline/best_checkpoint.pt` | 450,551 | `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90` |

| File | Vai trò |
|---|---|
| `training_config.json` | Snapshot đúng cấu hình đã train |
| `architecture.json` | Layer/parameter/FP32 footprint |
| `history.json` | Loss, accuracy, LR và validation metrics mỗi epoch |
| `metrics.json` | Selected train/validation và final test/per-class/confusion matrix |
| `best_state_dict.pt` | Model tensors |
| `best_checkpoint.pt` | Tensors, selected epoch, config, validation và provenance |
| `ml/provenance/week2_run_manifest.json` | Versioned metadata/hash của sáu file trên và dataset/source identity |

Ignore rules loại `data/` và `*.pt`; Git clone không chứa các binary weights. Local có đủ sáu file tại audit này không có nghĩa chúng được giao qua Git. Không cung cấp một command retrain để ghi đè run lịch sử.

## 14. I2 interface work

### Historical state at the end of Week 2

**Historical Week 2 state:** blob `953b2fc:contracts/I2_SV3_provisional_interface.md` ghi **`I2 = PROVISIONAL / NOT COMPLETE — BLOCKED_ON_GV_APPROVAL`**. Không có I2 v1 finalized trong implementation/review PR #7.

**Agreed target direction:** activation INT8, NCL `[N,C,L]`, N=1; `protect()` giữ payload byte count; round-trip trả byte gốc chính xác. Validate dtype/layout/N/shape/element count/byte count/model/split/contract version; reject mismatch. FP32 vẫn là reference cho model/handoff Week 3, baseline Week 2 chưa chuyển INT8.

**Still open/provisional lúc đó:** thuật toán P1 ở mức byte; xoshiro128** hay ChaCha20; PRNG derivation/domain separation; key size/generation/provisioning/ID; nonce size/reuse/replay/wire; byte order; permutation sampling; affine generation/order; metadata; protection errors/version negotiation; normative Python/C vectors và equivalence. Draft ghi roadmap có sketch nonce 8 B nhưng pseudocode uint32, chưa chọn một trong hai. Signature chỉ nêu vai trò, chưa API type hoặc wire format chuẩn. Schedule draft để Python P1 khoảng Week 5, port C/handoff khoảng Week 6; PR #7 không implement P1.

Trạng thái hiện tại khác draft này và được ghi ở phần riêng bên dưới; không dùng pointer I2 đã thay ở #9 để xóa lịch sử blocked.

## 15. I1 compatibility

Ở PR #7, I1 v1 giữ `protocol_version=1`, **`flags=0`, `nonce_length=0`**, `PROTECTED_PAYLOAD` reserved/disabled, không chèn I2 metadata. SV3 Week 2 không tự đổi packet. Revision bảo vệ phải phối hợp owners **SV1/Châu và SV2/Trung**; ML owner cung cấp dtype/shape/quantization/profile/output semantics.

**Current repository state:** các quy tắc byte/flag/nonce v1 trên vẫn giữ nguyên sau #9. Tuy nhiên **file văn bản I1 v1 có được sửa**: cập nhật trạng thái baseline Week 2 và dẫn chiếu I2/I1 v2; không được nói “file không thay đổi”. I1 v1 vẫn `REVIEW_CANDIDATE`, không phải `FROZEN`. Nội dung hiện tại ghi Device/Edge đã chấp thuận thiết kế wire, còn profile/transport/limits/implementation sign-off; đó không phải bằng chứng SV2 đã duyệt I1 v2.

## 16. I3 status

[I3_SV3_input.md](../../../contracts/I3_SV3_input.md): **OPEN**; SV3 consulted, không sở hữu final global `lut.json`. Theo nguồn phân công/báo cáo, các thành viên góp input, schema chung cần cross-team/GV phê duyệt. Ví dụ units `E_dev_uJ`, `t_dev_ms`, `bytes_payload` là input đã ghi, không phải full approved schema.

Chưa có `Pi(s,rho)`, định nghĩa/đơn vị `rho`, energy/latency/privacy measurement hoặc final field inventory/index/version/missing-value policy. #9 thêm lời nhắc I2 chỉ một transform cố định, synthetic vector không là LUT row. Không tạo LUT hoặc fabricate measurements trong Week 2 hay phiên báo cáo.

## 17. Verification commands

Tất cả kết quả ở bảng là **recorded historical evidence**, không báo rằng vừa chạy lại ML tests. Với PowerShell từ repo root, docs ghi:

```powershell
$py = '.\ml\.venv\Scripts\python.exe'
```

| Command | Purpose | Exit/result và nguồn |
|---|---|---|
| `& $py -B ml/src/check_env.py` | Environment | 0/PASS, baseline docs |
| `& $py -B ml/src/verify_mitdb_integrity.py` | Raw checksum | 0/PASS, baseline + review |
| `& $py -B ml/src/inspect_mitdb.py` | Lead/record audit | 0/PASS, baseline |
| `& $py -B ml/src/test_segmentation.py` | Beat windows | 0/PASS, baseline |
| `& $py -B ml/src/audit_mitdb_preprocessing.py` | Beat accounting | 0/PASS, baseline + review |
| `& $py -B ml/src/verify_mitdb_normalization.py` | Fixed train stats | 0/PASS, baseline + review |
| `& $py -B ml/src/verify_mitdb_processed.py` | Arrays/hash/no leakage | 0/PASS, baseline + review |
| `& $py -B ml/src/test_week1_negative.py` | Week 1 gates | 0, 34/34 cases, baseline |
| `& $py -O ml/src/verify_mitdb_integrity.py` | Integrity không dựa assert | 0/PASS, baseline |
| `& $py -O ml/src/verify_mitdb_processed.py` | Processed invariant dưới -O | 0/PASS, baseline |
| `& $py -B ml/src/verify_ptbxl_normalization.py` | PTB preserved stats | 0/PASS, baseline + review |
| `& $py -B ml/src/verify_ptbxl.py` | PTB integrity/manifest | 0/PASS, baseline + review |
| `& $py -B ml/src/test_week2_baseline.py` | Pre-training checks | 0, 3 tests, baseline + review |
| `& $py -B ml/src/train_mitdb_baseline.py --config mitdb_week2_baseline.json` | Historical training only | 0, epoch 3 selected, baseline |
| `& $py -B ml/src/verify_week2_baseline.py` | Historical original verifier before six-file policy | 0/PASS, baseline; không phải lệnh hiện tại dành cho four-hash run |
| `& $py -B ml/src/test_week2_provenance.py --verify-historical-artifacts` | Review gates + preserved run | 0/PASS, PR #7 review |
| `& $py -B ml/src/verify_week2_baseline.py --historical` | Current policy, historical evidence | 0/PASS từ committed review source, PR #7 review |
| `git diff --check` | Whitespace | 0/PASS, baseline + review |

Lệnh kiểm lịch sử được docs hiện tại quy định:

```powershell
& $py -B ml/src/test_week2_baseline.py
& $py -B ml/src/test_week2_provenance.py --verify-historical-artifacts
& $py -B ml/src/verify_week2_baseline.py --historical
```

Đây là trích hướng dẫn/evidence, không yêu cầu bắt đầu run mới. Lần audit báo cáo chỉ kiểm Git, nội dung, arithmetic và hash artifact local; không chạy script có khả năng tạo scientific evidence mới.

## 18. Review history

| Technical issue | Fix / evidence |
|---|---|
| Test cần run artifacts trước khi training sẽ tạo dependency vòng | Tách pre-test `test_week2_baseline.py` khỏi post-verifier; code committed chứng minh thứ tự cuối cùng. SHA riêng cho mọi lần thử tiền-commit: NOT VERIFIED FROM REPOSITORY EVIDENCE |
| Run phải gắn source đã commit và không đổi | Source gate, four-file hashes và `8e98a0e` historical source |
| CPU evaluation đổi một borderline N prediction so với GPU | Verifier dùng recorded device; docs ghi rerun chuỗi thành công từ implementation commit, không đổi model/hyperparameter |
| Transitive helpers chưa nằm trong provenance gate | `525755f`: shared six-file list/gate và bốn dirty-helper rejections |
| Current source policy khác four-hash evidence | Historical mode kiểm blobs/AST/helpers, không sửa run manifest |
| Rerun dễ đè evidence | Trainer từ chối existing Week 2 manifest |
| I2 hướng INT8 dễ bị hiểu là đã quantize/đã được duyệt | Review draft tách target INT8, FP32 reference, open byte decisions và I1 v1 prohibition |
| Accuracy tổng cao che minority failure | Ghi confusion matrix, zero S/F/Q recall, validation gap |

## 19. Git / provenance evidence

| Commit | Description | Significance |
|---|---|---|
| `8e98a0e` — 2026-09-24 00:41:27 +07 | Original implementation | Historical source SHA trong manifest |
| `dec0ec5` — 00:53:37 +07 | Original evidence/docs | Lưu run và kết quả |
| `d21fef1` — cùng author timestamp implementation | Implementation trên nhánh v2 | Commit khác SHA; không thay identity run cũ |
| `1449a7b` — cùng author timestamp evidence | Evidence trên nhánh v2 | Bảo toàn historical SHA |
| `525755f` — 16:58:30 +07 | PR #7 review fixes | Helper gates/historical mode/I2 refinement |
| `953b2fc` — 22:12:51 +07 | PR #7 tích hợp main | 13-file Week 2 implementation/evidence; parent là `e26e632` |

Hai cặp original/v2 là các commit hiện diện trên các nhánh trong `git log --all`, không phải bằng chứng hai lần train độc lập. Chỉ run có manifest được báo cáo. Timestamp hàng original/v2 là author time; không dùng nó để suy một thời điểm rebase chưa được ghi. Source commit và merge/integration commit là hai vai trò khác nhau.

## 20. Week 2 acceptance audit

Đánh giá này áp dụng **Historical Week 2 state**, không tính quyết định #9 như output PR #7.

| Requirement | Evidence | Status |
|---|---|---|
| 8–12 learned layers | 8 Conv + 2 Linear | PASS |
| <250k parameters | 109,653 | PASS |
| Model <1 MB | FP32 438,612 B; serialized 445,495/450,551 B | PASS |
| ≥98% accuracy trên MIT-BIH 5-class label space | 98.220974% test; hạn chế minority ở mục 7 | PASS |
| Fixed patient-wise Week 1 data | Loader/manifests/hash; no resplit/refit | PASS |
| Validation-only selection | Trainer/history/selected epoch 3/verifier | PASS |
| No tuning against observed test trong evidence | Model/config được giữ, test sau selection; review xác nhận | PASS |
| Reproducibility | Four-hash run + review historical verifier; thiếu historical helper coverage | PARTIAL |
| Phải chạy được trên MCU | Ops/footprint hướng MCU; chưa có execution/peak RAM/kernel evidence | PARTIAL |
| I2 interface hoàn chỉnh | PROVISIONAL / NOT COMPLETE / BLOCKED_ON_GV_APPROVAL tại #7 | PARTIAL |
| I3 final shared schema | Consulted input; schema OPEN | PARTIAL |
| Giữ scope Week 2, không thực hiện Week 3 | PR #7 không freeze/export/port model | PASS |
| Reviewer/GV final acceptance | Không có sign-off riêng đủ chứng minh | NOT VERIFIED |

## 21. Final Week 2 status

### Technical ML status

**PASS cho các tiêu chí baseline định lượng trên host**: lớp, tham số, kích thước và overall accuracy. Không tuyên bố toàn bộ ràng buộc “chạy được trên MCU” đã PASS khi chưa có triển khai/bằng chứng thiết bị; vì vậy nghiệm thu trọn phạm vi còn **PARTIAL**. Five-class robustness/clinical generalization chưa được chứng minh, với S/F/Q recall test bằng 0.

### Project/interface status

**Historical Week 2 state:** I2 `PROVISIONAL / NOT COMPLETE / BLOCKED_ON_GV_APPROVAL`, I3 OPEN. **Current repository state:** I2 quy cách kỹ thuật đã được SV1 chốt tại #9 nhưng chưa Device–Edge integration/SV2-SV3 confirmation; I1 v2 chỉ đề xuất. Không cộng quyết định này vào công Week 2.

### Merge/reviewer status

Git chứng minh PR #7 đã vào main qua `953b2fc`. Reviewer/GV approval toàn bộ Week 2 hoặc I2 wire revision: **NOT VERIFIED FROM REPOSITORY EVIDENCE**. Không đồng nhất merge với mọi sign-off. Phiên này chỉ tạo báo cáo, không commit/push/merge hoặc bắt đầu Week 3.

## Contract decisions for post-Week-2 phases

### Chronology: lịch công việc khác thứ tự PR merge

| Commit / thời điểm +07 ngày 2026-09-24 | Nội dung | Phân loại đúng |
|---|---|---|
| `e26e632` (#8), 22:11:08 | Quy cách handoff Week 3 | Sau implementation/review `525755f`, nhưng **trước** merge #7 1 phút 43 giây; đã là parent của #7 |
| `953b2fc` (#7), 22:12:51 | Baseline Week 2 | I2 draft vẫn provisional |
| `7773b36` (#9), 23:26:37 | I2/1 technical specification và I1 v2 proposal | **Finalized after Week 2** đối với quy cách I2; sau merge #7 |

Tên phần này chỉ phạm vi quyết định phục vụ giai đoạn sau baseline, không khẳng định #8 merge sau #7. Blob #8 còn viết rõ “PR #7 chưa nằm trong main” và dẫn `525755f`; #9 cập nhật câu đó. Current contracts tại `f08ccb5` giữ các quyết định này.

### SV3 → SV1 handoff format finalized for Week 3

[Handoff contract](../../../contracts/sv3_sv1_week3_model_handoff.md), thêm ở #8, chốt **format `w3-sv1-handoff-v1` bởi SV1**, chưa có hiện vật/nghiệm thu. Một thư mục `ml/artifacts/week3/<handoff_id>/`, revision ID bất biến; manifest UTF-8 khai source commit/checkpoint/config/env/seed/eval/dataset/preprocessing, file path tương đối, size/hash/format/dtype/shape. Binary/file giao hash raw bytes; text UTF-8 LF; upstream Week 1 giữ đúng hash policy gốc.

Gói phải có README, manifest, `model/checkpoint.pt`, `model/train_config.json`, `model/graph.json`, `samples.csv`, `inputs.npy`, weights/bias hai Conv và op liên quan, `firmware/head_parameters.h`, `golden/<milestone_id>.npy`, `scripts/export_week3.py`, `scripts/verify_week3.py`. Đây là **tên file quy định**, không khẳng định đã tồn tại hoặc đã được tạo trong phiên này.

Tensor FP32 `<f4`, C-contiguous, activation NCL; Conv weights `(C_out,C_in/groups,K)`; C99 header `static const float` dùng hexadecimal float literal hậu tố `f` để giữ bit. Graph phải đủ op/BN/folding/mốc theo thứ tự chạy; không tự giả định `M_final=M2` hay copy shape candidate Week 2 sang model Week 3.

Đúng 20 nguồn mẫu khác nhau, `sample_index=0..19`, ID gắn metadata Week 1; input/golden cùng thứ tự và checkpoint `eval()`. SV1 kiểm package/bit weights, chạy hai Conv, thu đầy đủ output; từng mẫu tại M_final phải `max(abs(MCU-PyTorch)) < 1e-3`. SV3 cung cấp giá trị/model thật, SV1 nghiệm thu; chưa có checkpoint/golden bàn giao, firmware hai Conv hay 20/20 PASS được xác nhận bởi contract. Đây là mô tả yêu cầu handoff, không triển khai Week 3.

### I2 v1: what became normative after Week 2

[i2_protection_v1.md](../../../contracts/i2_protection_v1.md) là current source of truth: **“QUY CÁCH KỸ THUẬT ĐƯỢC SV1 CHỐT; triển khai Device–Edge và xác nhận SV2/SV3 chưa hoàn tất.”** Version thuật toán/descriptor `I2/1` độc lập I1 protocol version. Nó thay thế draft #7 ở mức technical format, không chứng minh GV đã duyệt wire protocol.

| Quyết định mở ở PR #7 | Normative ở #9 | Phần chưa được đóng |
|---|---|---|
| Dtype/layout/shape | INT8 two's complement, C-contiguous NCL `[1,C,L]`; `C<=256`, `1<=C*L<=32768` B | Activation/model split profile thật, quantization evidence |
| PRNG | IETF ChaCha20 block, key 32 B, nonce 12 B, counter bắt đầu 0 | Port/đo trên MCU/Edge |
| Derivation/byte order | Dùng key/nonce trực tiếp cho dòng ChaCha20; little-endian; không một seed/KDF tùy runtime | Không có KDF/domain separation theo profile bổ sung; key scope/nonce uniqueness được quy định ở registry/lớp cấp nonce |
| Affine coefficients | C byte đầu `a[s]=byte OR 1`, C byte tiếp `b[s]=byte`, theo kênh nguồn; modulo 256 | Không còn lựa chọn byte-algorithm mở |
| Permutation | Fisher–Yates, uint32 little-endian, rejection sampling; `p[out]=source` | Không còn sampling/order mở |
| Key format/ID | Random 32 B từ CSPRNG, public `key_id` khác 0, registry bind sender/model/split; provisioning ngoài I2/I1 | Cơ chế cấp/lưu key thật chưa triển khai |
| Nonce format/reuse | `sender_id:uint32_le || sequence:uint64_le`, 12 B; monotonic, uniqueness per key, persist-before-send/reserved range; retry phát lại bytes cũ | Persistent counter qua reboot/crash, registry sender và duplicate handling thực |
| Metadata/API | Descriptor 28 B; API protect/unprotect nhận bytes, descriptor, nonce, key, active profile; C thêm length/capacity | Vị trí mang trên wire I1 mới chưa approved |
| Error/version behavior | Explicit version/algorithm/profile/metadata/size/length/key-scope/buffer errors; reject trước ghi output, C cấm overlap | `NONCE_REUSE` thuộc integration layer, pure transform không tự phát hiện |
| Normative vectors/Python-C reference | Hai valid vectors, chín invalid vectors, reference `.py/.c/.h` và host suite | Synthetic vectors không phải model activation, không chứng minh cross-device integration |

Descriptor 28 B gồm version, algorithm, dtype, layout, model_profile_id, split_id, N, C, reserved, L, key_id và payload_length. Multi-byte little-endian; registry active phải độc lập với metadata tự khai và mọi ID/shape phải khớp. Transform dùng affine nguồn rồi hoán vị; inverse dùng hệ số lẻ nghịch đảo modulo 256 để phục hồi bit-exact. Đây là tóm tắt đặc tả hiện hữu, không thêm implementation mới.

**Chỉ payload tensor giữ nguyên độ dài** `C*L`; descriptor 28 B + nonce 12 B tạo 40 B overhead ngoài payload, chưa tính wire envelope. ChaCha20 chỉ sinh hệ số/permutation, không XOR tensor như stream cipher; không MAC/tag/authentication/confidentiality proof. Sai key bytes hoặc payload bị sửa có thể cho tensor khác mà không lỗi. Bit-exact round trip không phải bằng chứng bảo mật.

### Current reference evidence and remaining work

#9 thêm `contracts/i2_ref/i2_reference.py`, `i2_reference.c`, `i2_reference.h`, `vectors.json`, `test_i2.py`. Đã đọc các file/diff: reference triển khai descriptor/validation/transform; tests có RFC block vector, valid/invalid vectors, Python/C equality ở nhiều shape và giới hạn tamper/error-no-write. Test source ghi lệnh `python -B contracts/i2_ref/test_i2.py`, tự compile host C vào temp. **Không chạy suite này trong phiên viết báo cáo**; commit có test không tự chứng minh một lịch sử PASS, càng không là nRF52840/KV260 PASS. Exact recorded exit/log của I2 host suite tại #9: **NOT VERIFIED FROM REPOSITORY EVIDENCE** trong các nguồn đã kiểm.

Còn mở: real model/split/quantization registry, activation INT8 thật, key provisioning/storage, nonce state bền qua reboot, firmware/Edge port, transport/parser/buffer/retry/response, cross-device interop và memory/latency measurements. `32768` là cap tự chọn, không phải RAM dư đã đo. I3 schema/rho/privacy measurements vẫn OPEN; handoff Week 3 vẫn FP32. Xác nhận SV2/SV3 và GV không được tự suy từ technical finalization bởi SV1.

### I1 v2 proposed versus finalized; I1 v1 preserved

[I1 v2 proposal](../../../contracts/i1_device_edge_packet_v2_proposal.md) có status **ĐỀ XUẤT WIRE; CHƯA ĐƯỢC SV2 PHÊ DUYỆT, CHƯA TRIỂN KHAI**. Đề xuất giữ magic/header/CRC cơ bản, tăng `protocol_version=2`; request `flags=0x0002` là `I2_TRANSFORMED`, không mở reserved `0x0001`. Thêm `model_profile_id` 4 B trước tensor metadata; transformed request thêm descriptor 28 B và nonce 12 B; INT8/NCL/shape/length/profile lặp lại phải khớp. V1 parser từ chối v2, không fallback; unprotect trước dequantize theo kênh gốc.

Các byte/schema này là **proposal**, chưa normative wire triển khai. SV1/SV2 còn phải duyệt statuses, transport, limits, duplicate cache, response/retry, packet vectors và cross-device tests; SV3 phải giao profile/quantization/activation/tail semantics thật. #9 sửa nội dung giải thích/trạng thái trong `i1_device_edge_packet_v1.md`, nhưng không đổi v1 byte/flag/nonce rules: v1 tiếp tục `flags=0`, `nonce_length=0`, cấm transformed payload và giữ `REVIEW_CANDIDATE`.

### Ownership and approval

| Interface | Owner / trách nhiệm | Approval state hiện có |
|---|---|---|
| I2 historical assignment | SV3 → SV1/SV2 theo project sources | PR #7 blocked on GV approval |
| I2/1 current technical format | SV1/Châu chốt format chung; SV3/Kỳ Anh tạo activation/Python/model profile; SV2/Trung khôi phục trước tail | SV1 technical finalization; SV2/SV3 confirmation/integration chưa hoàn tất; không tuyên bố GV approved wire |
| I1 v1/v2 | SV1/Châu Device và SV2/Trung Edge; SV3 xác nhận ML profile | V1 design review candidate; v2 chưa SV2 approve; frozen cần cả owners/sign-off |
| Week 3 handoff | SV1 chốt format/nhận và nghiệm thu; SV3 xuất gói thực | Format finalized; artifacts và acceptance chưa có |
| I3 | Các bên góp input, schema chung cần cross-team/GV; SV3 consulted | OPEN |

### Complete changed-contract inventory inspected

`git show --stat` và diff #8/#9 đã được đối chiếu với current `contracts/`:

| Commit | File changed | Ý nghĩa |
|---|---|---|
| #8 `e26e632` | `sv3_sv1_week3_model_handoff.md` | Tạo toàn bộ quy cách handoff |
| #9 `7773b36` | `README.md` | Bản đồ status hiện tại |
| #9 | `I2_SV3_provisional_interface.md` | Thay draft bằng historical pointer, không dùng để implement |
| #9 | `I3_SV3_input.md` | I2 không tự định nghĩa rho/LUT |
| #9 | `i1_device_edge_packet_v1.md` | Cập nhật ML/I2 context, giữ v1 wire |
| #9 | `i1_device_edge_packet_v2_proposal.md` | Đề xuất revision riêng |
| #9 | `i2_protection_v1.md` | Normative technical I2/1 |
| #9 | `i2_ref/i2_reference.py`, `i2_ref/i2_reference.c`, `i2_ref/i2_reference.h` | Python/C host references và API |
| #9 | `i2_ref/test_i2.py`, `i2_ref/vectors.json` | Test definitions/synthetic vectors |
| #9 | `sv3_sv1_week3_model_handoff.md` | Đổi links/status sau #7/#9, giữ FP32 handoff |

Toàn bộ phần này là bối cảnh interface ngoài implementation Week 2. Báo cáo không tính reference P1 của #9 hoặc format handoff của #8 là kết quả triển khai của SV3 trong PR #7.
