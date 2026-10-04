# SV3 ML — Week 1 Report

Báo cáo lịch sử SV3/Bùi Kỳ Anh, lập ngày 2026-09-25 từ checkout `f08ccb5` trên nhánh `docs/sv3-week1-week2-reports`. Phạm vi Week 1 gồm setup `8c94d8e`, pipeline ban đầu `74e414e` và toàn bộ sửa sau review được tích hợp ở `246a2c6`. Trạng thái ban đầu khi audit: working tree clean. Các kết quả chạy dưới đây là bằng chứng lịch sử; phiên lập báo cáo chỉ đọc nguồn, không tải lại dữ liệu, chạy lại pipeline hoặc sửa manifest.

Quy ước: **PROJECT REQUIREMENT** là yêu cầu trong tài liệu dự án; **IMPLEMENTATION DECISION** là lựa chọn cụ thể trong config/source; **OBSERVED RESULT** là số liệu trong manifest/tài liệu kiểm chứng. Việc đã merge không thay thế chữ ký nghiệm thu của reviewer/GV.

## 1. Week 1 objective

**PROJECT REQUIREMENT.** `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx`, mục A.3, bảng Giai đoạn 1, hàng Tuần 1, yêu cầu:

> Dựng môi trường PyTorch, tải MIT-BIH và PTB-XL từ PhysioNet; tiền xử lý: cắt nhịp, chuẩn hóa, chia train/val/test theo bệnh nhân (không chia ngẫu nhiên!).

Tiêu chí gốc: **“Tập dữ liệu sẵn sàng; không có rò rỉ bệnh nhân giữa train và test”**. `Huong1_Bao_cao_trien_khai_3SV.docx`, mục 2.2, cũng giao cả MIT-BIH và PTB-XL. Review ngày 2026-09-17 trong `yeu_cau_hoan_thien_tuan_1_sv3_ky_anh.docx` kết luận hai commit đầu chưa đạt checklist đầy đủ, cấm tự bỏ PTB-XL và yêu cầu:

| Nhóm yêu cầu | Điều kiện |
|---|---|
| P0 | PTB-XL đầy đủ theo profile 100 Hz đã chốt; MIT-BIH pin version/48 record/checksum; dữ liệu thiếu hoặc rỗng phải fail; invariant vẫn hoạt động dưới `python -O` |
| P1 | Config nguồn chuẩn; môi trường CPU/GPU tái lập; run provenance, command, hash, exit status |
| P2 | Hợp đồng dữ liệu/tích hợp trước Week 3; phần deployment chưa phải điều kiện hoàn tất model trong Week 1 |

**IMPLEMENTATION DECISION.** MIT-BIH dùng beat MLII; PTB-XL giữ nguyên record 12 lead, không áp nguyên pipeline beat đơn lead. Nguồn phụ thuộc gồm PhysioNet, WFDB, môi trường Python/PyTorch và metadata bệnh nhân. Đầu ra cung cấp dữ liệu đã khóa cho SV3 làm baseline; không phải split activation gửi Device–Edge.

Ngoài scope: train CNN, privacy attack, ONNX, quantization, khóa kiến trúc và firmware deployment. Nguồn dự án local cùng hash được kê ở mục 12; [traceability](../ml/docs/week1_requirements_traceability.md) và [protocol](../ml/docs/week1_data_protocol.md) là diễn giải versioned, không thay thế tài liệu yêu cầu gốc.

## 2. Starting state

Git `7341f94` có scaffold `ml/README.md`. `8c94d8e` thêm `ml/.gitignore`, snapshot `requirements.txt` và checker môi trường. `74e414e` thêm pipeline MIT-BIH, manifest bệnh nhân, normalization và bản verification ban đầu. Nội dung report tại `74e414e` đã ghi 105,026 beat và split 34/7/4 bệnh nhân; các số này được bảo toàn sau review.

Tại review 2026-09-17, PTB-XL chưa có downloader/config/manifest/verifier; integrity, fail-on-empty, kiểm tra version và provenance chưa đầy đủ. Vì vậy không dùng kết quả MIT-BIH ban đầu để tuyên bố hoàn thành toàn bộ Week 1 trước `246a2c6`. Dữ liệu local trước commit setup, thời điểm tải lần đầu và cấu hình máy trước đó: **NOT VERIFIED FROM REPOSITORY EVIDENCE**.

## 3. Environment setup

**OBSERVED RESULT:** [environment setup](../ml/docs/environment_setup.md), [verification](../ml/docs/week1_verification.md) và [run manifest](../ml/provenance/week1_run_manifest.json) ghi:

| Thành phần | Môi trường được ghi nhận |
|---|---|
| Python / OS | CPython 3.11.9; Windows NT 10.0 build 26200, PowerShell |
| Virtual environment | `ml/.venv`; bị ignore |
| PyTorch / CUDA / GPU | 2.14.0+cu130; runtime 13.0; NVIDIA GeForce RTX 5060; CUDA available theo verification |
| NumPy / pandas / SciPy | 2.4.6 / 3.0.5 / 1.17.1 |
| Matplotlib / WFDB / scikit-learn | 3.11.2 / 4.3.1 / 1.9.1 |
| Phiên bản Python hỗ trợ | `>=3.11,<3.12` theo config/docs |

`check_env.py` kiểm version thực với `environment.json`, thử tensor CPU/CUDA và trả non-zero khi sai. `requirements-core.txt` cộng selector CPU hoặc GPU giúp dựng môi trường không phụ thuộc snapshot GPU duy nhất. README có các lệnh sau; đây là **hướng dẫn được lưu**, không phải log chứng minh từng lệnh pip đã chạy trong phiên lịch sử:

```powershell
py -3.11 -m venv ml\.venv
.\ml\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ml\requirements-gpu-cu130.txt
python -B ml\src\check_env.py --mode gpu
```

Nhánh CPU dùng `ml/requirements-cpu.txt` và `--mode cpu`. Review cũ ghi terminal gặp `ModuleNotFoundError: torch`; đây là thiếu khả năng tái tạo môi trường ở terminal review, không chứng minh mô hình sai. Bổ sung hướng dẫn và checker xử lý khoảng trống đó. Phiên bản driver NVIDIA cụ thể, manifest chạy trên Linux, một lần dựng lại từ máy hoàn toàn mới: **NOT VERIFIED FROM REPOSITORY EVIDENCE**. Không suy kết quả Linux từ việc README có lệnh Linux.

## 4. Dataset acquisition

### 4.1 MIT-BIH

[Config](../ml/configs/mitdb_week1_config.json) pin MIT-BIH Arrhythmia Database v1.0.0, nguồn `https://physionet.org/files/mitdb/1.0.0/`, DOI `10.13026/C2F305`, license Open Data Commons Attribution License v1.0. `download_mitdb.py` lấy checksum manifest và `.hea/.dat/.atr` của đúng 48 record trong `mitdb_expected_records.txt`. File non-empty có thể được giữ lại để tiếp tục tải; **verifier độc lập** mới quyết định integrity, không coi tồn tại file là đủ.

Audit ghi 48/48 record và 144/144 file đúng checksum. Tất cả record có 360 Hz; bản audit `74e414e` ghi 650,000 sample/record. Chọn MLII theo tên: 46 record hợp lệ; 102 và 104 không có MLII nên loại khỏi preprocessing, vẫn kiểm integrity trong bộ 48 record; 114 dùng channel index 1.

### 4.2 PTB-XL

[Config](../ml/configs/ptbxl_week1_config.json) pin v1.0.3, nguồn `https://physionet.org/files/ptb-xl/1.0.3/`, DOI `10.13026/kfzx-aw45`, license CC BY 4.0. Downloader lấy `SHA256SUMS.txt` về tên local `SHA256SUMS.official.txt`, `ptbxl_database.csv`, `scp_statements.csv`, `LICENSE.txt` và `.hea/.dat` qua `filename_lr`. Chỉ waveform chính thức 100 Hz được chọn, không tuyên bố đã tải bản 500 Hz.

**IMPLEMENTATION DECISION:** 10 giây × 100 Hz × 12 lead cho shape WFDB `(1000,12)`; giảm I/O so với 500 Hz mà giữ cấu trúc record 12 lead. Lead order là `I, II, III, AVR, AVL, AVF, V1, V2, V3, V4, V5, V6`. `scp_codes` giữ dictionary multi-label code → likelihood, canonical sorted JSON; mọi code phải thuộc `scp_statements.csv`. Không ép thành năm lớp AAMI.

Checksum manifest được pin trước; metadata được hash **trước khi parse**; path từ metadata phải nằm trong raw directory, không nhận absolute/parent/drive-qualified path. Cached waveform vẫn được hash. Manifest phải đúng một hàng cho từng canonical `ecg_id`, không chỉ đúng tổng số hàng.

**OBSERVED RESULT cuối Week 1:** 21,799 record, 18,869 bệnh nhân, 61,007 SCP assignments và 43,601 file được checksum (43,598 waveform/header + 3 metadata). PTB-XL đã có pipeline dữ liệu và normalization đầy đủ, không còn ở mức “chỉ metadata/chưa làm” như review ban đầu. Raw WFDB là nguồn chuẩn; không tạo một bộ processed beat AAMI giả cho PTB-XL.

## 5. MIT-BIH preprocessing methodology

```text
raw ECG đã kiểm integrity
→ chọn record có MLII và lead theo tên
→ đọc expert annotations, bỏ symbol ngoài mapping
→ ánh xạ AAMI
→ cắt cửa sổ [R-180, R+180), bỏ cửa sổ biên thiếu
→ gán train/val/test theo manifest bệnh nhân
→ áp Z-score fit từ train
→ X/y/metadata + processed_manifest.json
```

| Bước | Quyết định thực tế và mục đích |
|---|---|
| Lead | MLII, không mặc định channel 0; tránh chọn nhầm lead ở record 114 |
| Annotation | Dùng vị trí expert annotation; không chạy một detector R-peak mới |
| AAMI | `N,L,R,e,j → N`; `A,a,J,S → S`; `V,E → V`; `F → F`; `/,f,Q → Q`; nhãn index `N/S/V/F/Q = 0/1/2/3/4` |
| Segmentation | 360 sample = 1 giây, 180 mỗi phía; không padding; tránh tạo dữ liệu biên nhân tạo |
| Filtering | `enabled=false`; không thêm filter vào waveform đã khóa |
| Split | Patient-wise, ratio mục tiêu 75/15/10, seed 30; 201/202 cùng bệnh nhân và cùng train; tỷ lệ thực theo số bệnh nhân nguyên, không ép tỷ lệ beat |
| Normalization | Global scalar `(x-mean)/std`, chỉ fit trên train; val/test chỉ dùng lại, ngăn leakage thống kê |
| Output | `X float32 (N,360)`, `y int64 (N,)`; metadata giữ patient/record/R-peak/symbol/AAMI/lead để truy về raw |

Seed và ratio là **IMPLEMENTATION DECISION**, không phải mọi chi tiết đều được tài liệu dự án bắt buộc. Dữ liệu bệnh nhân không chồng lấn là **PROJECT REQUIREMENT**. Pipeline không đổi sau khi review; các fix chủ yếu hoàn thiện kiểm chứng và PTB-XL.

## 6. Data integrity and leakage prevention

Ba tập bệnh nhân được kiểm giao rỗng từng cặp. Record 201/202 được gom trước khi chia nên không tạo leakage do một bệnh nhân có hai record. Normalization JSON gắn config hash, manifest hash và `fit_split=train`; processed manifest tiếp tục gắn normalization/config/split và hash từng array/metadata. Verifier đối chiếu mỗi metadata row với annotation/raw waveform, không chỉ kiểm shape.

PTB-XL dùng official folds 1–8 train, 9 validation, 10 test; verifier độc lập kiểm patient disjoint và exact canonical ID set. Validator chạy trước cả tính normalization và verification; row count bằng nhau vẫn không đủ nếu ID bị lặp/thay thế. Normalization theo từng lead được fit trên 17,418 train record, tức 17,418,000 giá trị/lead. Verifier độc lập stream raw train, áp stats, cast float32, kiểm finite/mean/std; không import phép tính producer để tự xác nhận chính nó.

`week1_common.py` dùng `require(...)`/exception cho invariant quan trọng, hoạt động cả khi `python -O` bỏ assert. Text artifact/config dùng `sha256_utf8_lf_normalized`; binary/raw dataset dùng `sha256_raw_bytes`. `.gitattributes` cố định LF cho text `ml/**`; canonical hash còn chống sai lệch khi công cụ tạo CRLF. Hash ràng buộc nội dung, không tự chứng minh chất lượng nhãn hoặc khả năng tổng quát hóa.

## 7. Files created or modified

Các đường dẫn sau tính từ repository root; nhóm file đều tồn tại trong Git Week 1. Không gộp file Week 2 vào bảng.

| File | Purpose | Week 1 role |
|---|---|---|
| `ml/.gitignore`, `.gitattributes` | Loại artifact lớn; quy tắc LF | Setup và hardening |
| `ml/requirements.txt`, `ml/requirements-core.txt`, `ml/requirements-cpu.txt`, `ml/requirements-gpu-cu130.txt` | Snapshot và bộ cài CPU/GPU | Environment |
| `ml/configs/environment.json`, `ml/src/check_env.py` | Constraints và runtime checker | P1 setup fix |
| `ml/configs/mitdb_week1_config.json`, `ml/configs/ptbxl_week1_config.json` | Dataset/protocol source of truth | Tránh hard-code phân tán |
| `ml/configs/mitdb_normalization.json`, `ml/configs/ptbxl_normalization.json` | Stats train-only và provenance | Artifact nhỏ versioned |
| `ml/manifests/mitdb_expected_records.txt`, `ml/manifests/mitdb_patient_split.csv`, `ml/manifests/ptbxl_patient_split.csv` | Completeness và patient split | Dataset identity |
| `ml/src/download_mitdb.py`, `ml/src/download_ptbxl.py` | Acquisition version cố định | P0 data |
| `ml/src/week1_common.py`, `ml/src/mitdb_common.py`, `ml/src/ptbxl_common.py` | Config/hash/validation/segmentation/metadata dùng chung | Hardening |
| `ml/src/inspect_mitdb.py`, `ml/src/test_segmentation.py`, `ml/src/audit_mitdb_preprocessing.py` | Lead, annotation và beat accounting | Audit MIT-BIH |
| `ml/src/build_mitdb_manifest.py`, `ml/src/build_ptbxl_manifest.py` | Manifest bệnh nhân | Split |
| `ml/src/compute_mitdb_normalization.py`, `ml/src/compute_ptbxl_normalization.py` | Fit train-only | Normalization |
| `ml/src/build_mitdb_processed.py` | X/y/metadata/processed manifest | MIT-BIH output |
| `ml/src/verify_mitdb_integrity.py`, `ml/src/verify_mitdb_normalization.py`, `ml/src/verify_mitdb_processed.py` | Kiểm raw/stats/processed | Verification |
| `ml/src/verify_ptbxl.py`, `ml/src/verify_ptbxl_normalization.py` | Strict completeness và normalization độc lập | Hoàn thiện PTB-XL |
| `ml/src/test_week1_negative.py`, `ml/src/run_week1_verification.py` | Mutation tests; fail-fast orchestration | Chặn PASS giả |
| `ml/README.md`, `ml/docs/environment_setup.md`, `ml/docs/week1_data_protocol.md`, `ml/docs/week1_data_contract.md`, `ml/docs/week1_requirements_traceability.md`, `ml/docs/week1_verification.md` | Hướng dẫn, quyết định, evidence | Báo cáo và reproducibility |
| `ml/provenance/week1_run_manifest.json` | Thời gian, nguồn, commands, hash, exit | Run evidence |

## 8. Verification and tests

Nguồn máy đọc: [week1_run_manifest.json](../ml/provenance/week1_run_manifest.json), run từ `2026-09-18T07:30:05.817564+00:00` đến `2026-09-18T07:39:34.193627+00:00`, source `d6fde9884968c7ab316976ddec3b171ecdcd1946`, overall exit `0`. Bảng dưới là 19 lệnh **thực sự được manifest ghi lại**, không phải các lệnh vừa chạy để viết report.

| Command | Purpose | Result |
|---|---|---|
| `python -B ml/src/check_env.py` | Version/tensor checks | Exit 0 |
| `python -B ml/src/download_mitdb.py` | Acquire pinned MIT-BIH | Exit 0 |
| `python -B ml/src/verify_mitdb_integrity.py` | 48-record/file/checksum integrity | Exit 0 |
| `python -B ml/src/inspect_mitdb.py` | Record/lead audit | Exit 0 |
| `python -B ml/src/test_segmentation.py` | Segmentation checks | Exit 0 |
| `python -B ml/src/audit_mitdb_preprocessing.py` | Annotation/beat/class accounting | Exit 0 |
| `python -B ml/src/build_mitdb_manifest.py` | Patient split manifest | Exit 0 |
| `python -B ml/src/compute_mitdb_normalization.py` | Fit train-only MIT statistics | Exit 0 |
| `python -B ml/src/verify_mitdb_normalization.py` | Validate MIT normalization | Exit 0 |
| `python -B ml/src/build_mitdb_processed.py` | Build fixed MIT arrays/metadata | Exit 0 |
| `python -B ml/src/verify_mitdb_processed.py` | Raw-to-processed/hash verification | Exit 0 |
| `python -O ml/src/verify_mitdb_integrity.py` | Integrity under optimized Python | Exit 0 |
| `python -O ml/src/verify_mitdb_processed.py` | Processed checks under optimized Python | Exit 0 |
| `python -B ml/src/download_ptbxl.py` | Acquire pinned PTB-XL | Exit 0 |
| `python -B ml/src/build_ptbxl_manifest.py` | Canonical PTB patient/SCP manifest | Exit 0 |
| `python -B ml/src/compute_ptbxl_normalization.py` | Fit per-lead PTB train statistics | Exit 0 |
| `python -B ml/src/verify_ptbxl_normalization.py` | Independent PTB normalization verification | Exit 0 |
| `python -B ml/src/verify_ptbxl.py` | Strict PTB dataset verification | Exit 0 |
| `python -B ml/src/test_week1_negative.py` | Expected-failure suite | Exit 0 |

Runner lịch sử được tài liệu ghi:

```powershell
python -B ml/src/run_week1_verification.py
```

Lệnh này tạo lại một số artifact nên không được chạy trong phiên lập báo cáo. Manifest lưu `duration_seconds` và `output_sha256` cho từng lệnh; hash output không thay thế raw stdout nếu raw log không được giữ.

Negative suite ghi 34 child cases đều exit `1`, có lỗi tường minh, không in `STATUS: PASS`; suite cha exit `0` vì đã từ chối đúng. Các ca gồm raw rỗng; MIT thiếu record/hea/dat/atr/sai checksum; PTB metadata cache hỏng, thiếu header/data/record, checksum waveform sai; năm dạng manifest hỏng (header-only, thiếu hàng, thừa hàng, duplicate ID kèm thiếu ID, foreign ID kèm thiếu ID). Tất cả được thử normal và `python -O`.

Năm mutation manifest phải báo đúng nguyên nhân, ví dụ `CSV contains no data rows`, `PTB-XL manifest row count mismatch`, `Duplicate ecg_id values in PTB-XL manifest`, `PTB-XL manifest ecg_id set mismatch`; lỗi hash ở bước sau không được tính là thành công của gate completeness. Test sử dụng thư mục tạm/hard link/copy, không sửa raw thật.

[Verification](../ml/docs/week1_verification.md) còn ghi bốn positive mutation checks LF/CRLF PASS, PTB strict/normalization verifier dưới `python -O` PASS, và isolated fail-fast: child đầu exit `7`, chỉ chạy 1/2 command, runner exit `1`, không tạo sentinel. Các kiểm tra bổ sung này không nằm trong danh sách 19 command; exact invocation đầy đủ của fail-fast fixture: **NOT VERIFIED FROM REPOSITORY EVIDENCE**.

## 9. Key observed results

| MIT-BIH accounting | Kết quả |
|---|---:|
| Raw record / record có MLII | 48 / 46 |
| Bệnh nhân eligible | 45 |
| Annotation trong 46 record xử lý | 108,144 |
| Annotation bị bỏ / beat biên thiếu | 3,066 / 52 |
| Beat hợp lệ | 105,026 |
| N / S / V / F / Q | 90,320 / 2,781 / 7,229 / 802 / 3,894 |

Đẳng thức audit: `108144 - 3066 - 52 = 105026`.

| Split | MIT patients / records / beats | PTB patients / records |
|---|---|---|
| train | 34 / 35 / 81,094 | 15,023 / 17,418 |
| validation | 7 / 7 / 15,388 | 1,942 / 2,183 |
| test | 4 / 4 / 8,544 | 1,904 / 2,198 |

MIT train mean/std: `-0.2912026352134608` / `0.45653058276514263`; normalized train ≈ `-9.6210e-11` / `0.999999999635`. Bản `74e414e` còn ghi validation mean/std ≈ `-0.2587103347` / `1.1056936625`, test ≈ `-0.4544693434` / `1.0416752841`. Val/test không bắt buộc mean 0, std 1 vì dùng stats train.

PTB normalized train: max absolute mean từng lead ≈ `1.235e-9`, max deviation std khỏi 1 ≈ `2.413e-9`, đều trong tolerance `1e-6`. Toàn bộ 12 mean/std gốc được bảo toàn trong [ptbxl_normalization.json](../ml/configs/ptbxl_normalization.json). Không suy các số này thành kết quả training PTB-XL.

## 10. Problems encountered and fixes

| Vấn đề có bằng chứng | Sửa và ý nghĩa |
|---|---|
| PTB-XL chưa triển khai ở hai commit đầu | `287f0cd` bổ sung acquisition/config/manifest/stats/verifiers; được tích hợp `246a2c6` |
| Tập rỗng vẫn disjoint; audit `0=0` có thể PASS | Yêu cầu non-empty, count chuẩn, file đầy đủ; exception/non-zero trước xử lý |
| `assert` bị vô hiệu bởi `-O` | Invariant dùng explicit validation; negative suite chạy cả hai mode |
| MIT downloader chưa pin đủ nguồn/integrity | Version, DOI/license, official record list, pinned SHA256SUMS và strict verifier |
| PTB cached metadata/path/checksum và normalization cần kiểm độc lập | `f6abdea` hardening checksum-before-parse, path confinement, train-only output verification, fail-fast |
| PTB manifest có thể đúng tổng hàng nhưng duplicate/missing ID | `de20490` exact canonical ID set và kiểm từng field trước producer/verifier |
| Text hash khác nhau giữa LF/CRLF | `de20490` normalized text policy, binary giữ raw bytes |
| Negative case thất bại vì hash ở bước sau vẫn có thể được nhận | `d6fde98` yêu cầu đúng lỗi validator, năm mutation riêng |
| Setup thiếu hướng dẫn/version checking, review gặp thiếu torch | CPU/GPU selectors, environment config, version/tensor checks |

**Mâu thuẫn evidence cần giữ nguyên:** `week1_verification.md` nói `post_run_dirty=true`; JSON hiện tại và blob `519b925:ml/provenance/week1_run_manifest.json` đều ghi `git.dirty=false`, **`git.post_run_dirty=false`**. Report lấy giá trị JSON làm giá trị manifest đã lưu và nêu rõ khác biệt, không sửa một trong hai nguồn. Source runner lấy `post_run_dirty` trước khi ghi chính manifest, nên trường đó không mô tả đầy đủ trạng thái sau mọi thao tác ghi. Nguyên nhân chính xác khiến lời văn và JSON lệch nhau: **NOT VERIFIED FROM REPOSITORY EVIDENCE**; không tự đổi thành `true`.

## 11. Reproducibility artifacts

Versioned: configs, split CSV, official record list, stats JSON, source, requirements, docs và run manifest. Local/ignored: `ml/.venv`, raw ECG, `ml/data/processed/mitdb/` gồm chín X/y/metadata file và `processed_manifest.json`. Processed manifest nằm local nhưng hash của nó và từng output được ghi trong provenance versioned. Không gọi processed arrays là dữ liệu nằm sẵn trong Git clone.

Các identifier sau chép từ manifest, theo đúng hash policy ở mục 6:

| Identifier | SHA-256 |
|---|---|
| Config `environment.json` | `a5e201eec25bea5eac9ebfc71792917bc6552fcf774b0faee514388d4e026a01` |
| Config `mitdb_week1_config.json` | `f5d050686b9d4816052631380b81f0c4671faf1dc648f1d9c02b4c3dc3be0b54` |
| Config `ptbxl_week1_config.json` | `d8a34e7b2a6c6f4bfcf435f6d0bbe4fcbaf978973846fb4506ee32c60b89d9c8` |
| `mitdb.checksum_manifest_sha256` | `b61158a96d5f2ca80edfb354a9a66a6324836c390a84e1966dcee2b907d6be43` |
| `mitdb.required_file_tree_sha256` | `09d0f9c2cf19cbcfc8b704681ce388e62ec89832bfed59169e70ac9ea147e46f` |
| `ptbxl.checksum_manifest_sha256` | `b7224b92b341511ec3ceb13dc6652079b2c36a06504bcb49506f157f51dc695d` |
| `ptbxl.required_file_tree_sha256` | `b4863f3c13d7ccdd31244944d8cd1e1ed3e98ff2877d7ca5b154cbf471170242` |
| `ml/manifests/mitdb_expected_records.txt` | `fcdca7ead9fc93f612f7e025029241cb6429ba2fcd05327b661bdc6b26fbcb57` |
| `ml/manifests/mitdb_patient_split.csv` | `27b07a0a4fcaac010291fd088c702e9eea1899ed73c6cef618404bafd3c116fe` |
| `ml/manifests/ptbxl_patient_split.csv` | `c90fa0d79a65e86ff4c8ca42ef1adcb9f887e639fcea7868af16b3d5d045988c` |
| `ml/configs/mitdb_normalization.json` | `37d42ff2cbacc44f268046a62c392d2b9676c2c49936ac4188207745edd2d48c` |
| `ml/configs/ptbxl_normalization.json` | `7268a3b5d47a2d8a450a74a5c2b368526567da5d4c94a26d4579328b36310e8d` |
| `ml/data/processed/mitdb/train_X.npy` | `80168e5014d9018483a7d4c4f7079bb31b6b81e934992ed1169c350f4cf02c6f` |
| `ml/data/processed/mitdb/train_y.npy` | `00280fa08d2dad50805729a5be1bc182b9b56e81b5281e231ee9896914625752` |
| `ml/data/processed/mitdb/train_metadata.csv` | `86c5c3a634fc5adfca09ec2f8378efb0d52f21205cfaf9470432f89ffdc0977a` |
| `ml/data/processed/mitdb/val_X.npy` | `60a84c4096d9d476fac53fbf0a9b5acce1df4953011e4f6ceb9d5858e550e732` |
| `ml/data/processed/mitdb/val_y.npy` | `4973e373127aa250c923e5386dd5557010808a565329efdc1758c50a849dcf43` |
| `ml/data/processed/mitdb/val_metadata.csv` | `3c41a19339ef9548afae786e9e2861e8834b48718ae5f90ca799e00f57e2fc68` |
| `ml/data/processed/mitdb/test_X.npy` | `062208131e2e8a39e3767fdc901c83f5aeb14becbca585a12a340c2f61faf16e` |
| `ml/data/processed/mitdb/test_y.npy` | `ae99ea072108103aca2abc612bbc40222f7363cda9c4fdac695d8620f29324c6` |
| `ml/data/processed/mitdb/test_metadata.csv` | `02a6a91c0e35710d0be13f10b2360e034918f546b3ba2c7df7a2fd484ecd1178` |
| `ml/data/processed/mitdb/processed_manifest.json` | `f712c83d46d71ac6af75b7138668d8918eef87a4ddfeab8e8b5310ced2c44a3c` |

Checksum/tree hash MIT và PTB ở bảng là bằng chứng run lịch sử; phiên viết report không rehash toàn bộ raw dataset. Project DOCX cũng local/ignored; người clone chỉ có nguồn versioned phải được cấp lại đúng bản tài liệu nếu muốn tái kiểm yêu cầu gốc.

## 12. Git / provenance evidence

| Commit | Description | Significance |
|---|---|---|
| `8c94d8e` — 2026-09-14 | Setup ML | Requirements, checker, ignore |
| `74e414e` — 2026-09-17 | Pipeline MIT-BIH | Split/stats/beat audit ban đầu |
| `287f0cd` — 2026-09-18 | Complete review requirements | PTB-XL và integrity/config/provenance |
| `18683b8` — 2026-09-18 | Post-commit evidence | Ghi run sau commit |
| `f6abdea` — 2026-09-18 | Harden review gates | Cached checksums, path safety, verifier/fail-fast |
| `92bd689` — 2026-09-18 | Verification evidence | Cập nhật evidence sau hardening |
| `de20490` — 2026-09-18 | Manifest/hash fix | Exact PTB IDs và LF-normalized hash |
| `0259937` — 2026-09-18 | Manifest/hash evidence | Stats/provenance theo policy đã sửa |
| `d6fde98` — 2026-09-18 | Reason-specific negative tests | Source của final run |
| `519b925` — 2026-09-18 | Final reason-specific evidence | 34 ca và manifest final |
| `246a2c6` — 2026-09-18 | Tích hợp Week 1 fixes vào main | Tổng hợp patch review; không phải một lần thay split/train mới |

Các commit review còn truy cập qua history `--all`; không giả định mọi SHA đều là first-parent commit main. Đối chiếu đã dùng file content/diff, đặc biệt `de20490` và `d6fde98`, không suy tính đúng chỉ từ commit message.

Nguồn dự án được đọc trực tiếp từ DOCX local (XML trong archive), không tải từ web:

| Nguồn local / vị trí nội dung | SHA-256 raw bytes |
|---|---|
| `ml/docs/project_sources/requirements/06_Huong1_Adaptive_Split_Inference_Lo_trinh.docx` — Roadmap, nguồn bối cảnh | `c1dd459531796e8140ec965b517ce66fa6ac381d161d203e36e692041993f829` |
| `ml/docs/project_sources/requirements/Huong1_Bao_cao_trien_khai_3SV.docx` — 2.2 và 4.4.2 | `60f83fa7c0779d11c888a8a104c5fa55be0c8c8b171f9d72e29cbba9efcc9a90` |
| `ml/docs/project_sources/requirements/Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx` — A.3, hàng Tuần 1–3 | `75fcd76999af521a568b039c6983414217c59991d37b5591b85d211db927880d` |
| `ml/docs/project_sources/requirements/Huong1_Phan_cong_nhom_nghien_cuu.docx` — Phần 4, bảng I1–I4 | `116a8762a5b37b1b7f7696ea1c4edca4e5a8e9c7694d81e74e9999d0a2ebbce4` |
| `ml/docs/project_sources/review/yeu_cau_hoan_thien_tuan_1_sv3_ky_anh.docx` — Review 2026-09-17, P0/P1/P2 | `33d5cab49ad7d1a551b21751b81155802e9ca1619dd5ba82c776792feff46088` |

Các file này có ở checkout local nhưng `git ls-files ml/docs/project_sources` không có entry; do đó câu “không có trong Git tree” ở contract hiện tại đúng về Git, không đồng nghĩa file vắng trên máy audit. Tài liệu reference paper không được dùng như requirement. SHA trong bảng định danh bản local đã đọc, không chứng minh nó tồn tại tại mọi commit lịch sử.

## 13. Week 1 acceptance and carry-forward audit

Tiêu chí nghiệm thu dữ liệu cốt lõi của Week 1 là dữ liệu sẵn sàng và không có rò rỉ bệnh nhân. P2 deployment readiness trước Week 3 là điều kiện chuyển tiếp (carry-forward), không phải tiêu chí nghiệm thu dữ liệu cốt lõi của Week 1; trạng thái PARTIAL của hạng mục này được giữ nguyên.

| Requirement | Evidence | Status |
|---|---|---|
| Môi trường PyTorch và version/tensor check | 19-command manifest, environment docs/config | PASS |
| MIT-BIH đầy đủ, đúng version/checksum | 48 records, 144 files, pinned/tree hashes | PASS |
| PTB-XL đầy đủ theo profile 100 Hz đã chốt, 12 lead/SCP | 21,799 records, 43,601 checksummed files, strict manifest | PASS |
| Patient-wise không leakage | MIT 34/7/4; PTB official folds, pairwise intersections empty | PASS |
| Train-only normalization và output liên kết raw | Stats/config/manifest hashes, independent verifiers | PASS |
| Chặn empty/missing/corrupt; hoạt động dưới `-O` | 34 expected failures; reason-specific gates | PASS |
| Config nguồn chuẩn và hash cross-platform | Shared helpers, LF/CRLF checks | PASS |
| Run provenance hoàn toàn nhất quán lời văn/JSON | Có manifest nhưng `post_run_dirty` lệch tài liệu | PARTIAL |
| Data-side integration contract | Shape/layout/unit/label/stats trong contract | PASS |
| Carry-forward: P2 deployment contract đầy đủ trước Week 3 | ONNX/tensor name/split/quantization còn deferred | PARTIAL |
| Linux hoặc clean-machine reproduction | Chỉ có Windows recorded run | NOT VERIFIED |
| Chữ ký nghiệm thu reviewer/GV riêng | Merge commit không đủ chứng minh sign-off | NOT VERIFIED |
| CNN training/export trong Week 1 | Ngoài scope Week 1 | NOT APPLICABLE |

## 14. Final Week 1 status

Week 1 đã hoàn thiện nền dữ liệu **cả MIT-BIH và PTB-XL**, preprocessing, normalization, split chống leakage và các gate review P0/P1 theo bằng chứng đã lưu. Phần cần bổ sung so với prompt/báo cáo ban đầu chính là toàn bộ PTB-XL, checksum-before-parse, manifest exact-ID, independent normalization, 34 negative cases, LF/CRLF và fail-fast evidence.

Còn giới hạn về tính nhất quán `post_run_dirty`, thiếu manifest Linux/clean-machine và sign-off riêng của GV. P2 deployment/export tiếp tục là việc giai đoạn sau; không dùng data contract để tuyên bố đã khóa model. Báo cáo không huấn luyện hoặc mô tả methodology Week 2 như công việc Week 1, không sửa bằng chứng lịch sử.
