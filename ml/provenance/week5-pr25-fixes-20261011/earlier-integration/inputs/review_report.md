# Review độc lập PR #25 — SV3 tuần 5

Bắt đầu 10/10/2026; chốt 11/10/2026, Asia/Saigon. Người giao nhiệm vụ: Châu (SV1). Phạm vi chỉ PR25.

**Kết luận: FAIL. PR25 chưa merge.** Các gate Python/ML/P1 chạy mới đều PASS; regression provenance SV1 là gate bắt buộc FAIL. Wire allocation còn BLOCKED. Delivery verifier chưa tái lập được đầy đủ trên máy SV1 vì buộc có các artifact lịch sử ngoài các gói đã publish. Không đổi Draft, main hoặc SV1; giữ nhánh/worktree review. Bản nháp phản hồi nằm ở [feedback_draft.md](feedback_draft.md), chưa gửi.

## SHA và phạm vi review

| Vai trò | SHA |
|---|---|
| origin/main fetch dùng tích hợp | `cfdfca1025ab5f707b46197b4c5dae868d38d473` |
| PR25 HEAD đã pin, fetch lại cuối vẫn như cũ | `a2847117ac285bf16c572a56f48dbe39facd6b08` |
| PR base.sha do API trả / merge-base Git | `65d44d2cd159b28cf9bb505a66d39ef67e8dbc19` |
| Merge thử LOCAL, hai parent main và PR HEAD | `301026a1220b2135bea15dfa17c351e1e1ca20c5` |
| Tree merge thử LOCAL | `f94e923f2758fa1481495921a6b668f9d0f992b6` |
| Merge PR thực tế | **Không có** |

API PR vẫn trả base.sha lịch sử, khác origin/main đã fetch. Review dùng main mới nhất đã xác minh bằng Git, không dùng base.sha lịch sử làm nền. Trường merge_commit_sha `6338222163adb56252c9d243ba1982821e95c1f1` của API không phải merge thực tế: PR vẫn open/unmerged.

Nhánh LOCAL `review/pr25-sv3-week5`, worktree `D:/HUST/ASI_pr25_review/20261010-pr25-01/worktree`. Nhánh chưa tồn tại trước phiên, được tạo từ origin/main; merge thử không conflict. Không push nhánh review, không sửa nhánh tác giả, không xử lý các worktree cũ ngoài phạm vi. Toàn bộ diff 139 file và diff tích hợp đã lưu trong [evidence/pr-diff.txt](evidence/pr-diff.txt), [evidence/integration-diff.txt](evidence/integration-diff.txt), [evidence/changed-files.txt](evidence/changed-files.txt).

Đã đọc toàn bộ diff code/config: 9 file Python thay đổi/thêm, `.gitattributes`, `.gitignore`, các README; đối chiếu decision note, registry, checklist, technical report, handoff và provenance được dẫn. Đối chiếu I1 v1 metadata/scale/profile, I2/1/reference/header/vectors, registry FP32 confirmed, loader frozen và verifier SV1. Không đánh dấu người dùng đã học hiểu; các mục LEARN/UNDERSTAND chưa nghiệm thu vẫn giữ nguyên.

## Findings

### F1 — P1, regression tích hợp: gói SV1 đã nghiệm thu không qua source gate

Vị trí thay đổi: `ml/scripts/week5_common.py:61`, `ml/scripts/evaluate_week5.py:18`. Binding: `device/scripts/week5_common.py:44`; kiểm bắt buộc: `device/scripts/verify_week5_package.py:40`, `device/scripts/accept_week5_mcu.py:167`.

Hai script ML nằm trong source_sha256 của preparation đã build/nạp/đo. Thay đổi provenance hoặc runner dù không đổi firmware vẫn làm preflight cũ FAIL. Đã chạy mới preflight và acceptance thường/-O trên main: exit0. Trên tree tích hợp, sau khi tách sai khác checkout CRLF, cả bốn lệnh đều exit1 với `Prepared source changed: ml/scripts/week5_common.py`. Audit đầy đủ xác nhận evaluate_week5.py cũng khác binding, không chỉ lỗi đầu tiên.

| Source | Receipt/main SHA256 | Tree tích hợp SHA256 |
|---|---|---|
| ml/scripts/week5_common.py | `c1842a380afddaaf7e7968bfdd3ff7c03e08d36e9bec205da2819abdca105934` | `b7480d19bcc2932805547b25bc0cc5e5ab4b62276384c4ee63d065302cb3caf2` |
| ml/scripts/evaluate_week5.py | `c420029c0b8b1d7834bb32db0c428f379c1659cef3cc99ffa9a1271bfeb88eef` | `dcfcc1fc172c1781111627469acc7b6f9521f4da1dd4085227620c20d443b223` |

Minh chứng: [binding-mismatches-canonical.json](evidence/binding-mismatches-canonical.json), [preflight stderr](evidence/preflight-integrated-canonical.stderr.txt), [preflight -O stderr](evidence/preflight-integrated-canonical-O.stderr.txt), [acceptance stderr](evidence/acceptance-integrated-canonical.stderr.txt). Lệnh/executable/cwd/SHA/log hashes/exit có trong các `.command.json` tương ứng.

Tái hiện: dùng Python dự án, cwd worktree tích hợp, chạy `device/scripts/verify_week5_package.py --preparation D:/HUST/ASI_week5_prepare/20261009-sv1-prepare01/preparation.json`, thêm `-O` cho lần tối ưu. Với checkout Windows mặc định sẽ gặp lỗi CRLF có sẵn trước; để cô lập PR, dùng đúng raw Git blob của bốn file được chứng minh newline-only, như quy trình ghi ở phần setup. **Không thay hai script ML bằng phiên bản main.**

Yêu cầu sửa: ưu tiên giữ nguyên bytes của hai entrypoint đã bị binding, chuyển accuracy gate/provenance mới sang module/entrypoint mới có version và cập nhật test/import phù hợp. Nếu chọn cơ chế chuyển tiếp provenance khác, phải là revision/receipt mới có review và kiểm thử cho đúng old/new SHA; giữ snapshot lịch sử, source/model/manifest/payload gates và mọi binary. Không đổi hash receipt cũ, bỏ source gate hoặc whitelist source chưa kiểm. Build mới không chứng minh gói đã nghiệm thu cũ vẫn hợp lệ, nên không build/nạp lại để che lỗi này.

### F2 — BLOCKER đã khai báo, cần quyết định: chưa cấp model/wire split IDs

Vị trí: `contracts/sv3_week5_ml_registry_v1.json:9`, `:18` và các hàng split; `contracts/sv3_week5_decisions_v1.md:108`; `ml/src/week5_interfaces.py:43`.

model_profile_id và toàn bộ wire_split_id vẫn null. Registry FP32 ghi rõ s=0..10 không cấp I1 wire IDs. Tìm trong contracts/docs/config/device và discussion/reviews PR25 không có approval allocation mới. Proposal `0x4D495401`, `256+s` vẫn chưa áp dụng; review/merge có điều kiện không phải approval cho proposal. Test-only `0x575435`, s+1 hoặc 101+7*s không phải deployment registry. active_profile từ chối registry thiếu IDs ở cả thường/-O, đúng hành vi hiện tại.

Đề xuất để Châu chốt: reserve model_profile_id **0x4D495401 = 1296651265** cho `mitdb_week2_cnn_v1`/checkpoint đã pin; wire_split_id **256..266** tương ứng s0..s10. Các giá trị nằm trong uint32/uint16 và khác 0; chưa thấy collision với deployment registry được commit vì repository chưa có allocation triển khai khác. Đây không chứng minh namespace ngoài repository của Châu/Trung không collision: cần xác nhận chung và ghi approval/version trước khi điền registry.

max payload thực của các tensor là 5760 B, C tối đa 64. `device/week5/main.c:18`, `:21`, `:40` giữ quantized[5760], scale_le[128] và guard C<=64. **32768 là trần contract, không phải buffer MCU đã hỗ trợ.** Key_id/sender scope/nonce lifecycle, I1 transport và buffer deployment hai phía còn là dependency triển khai; không tự biến thành gate C/radio/Device–Edge bắt buộc của Python tuần 5. Sau approval phải có reconciliation registry revision và rerun mapping/descriptor/real-tail; không đổi reference/goldens/ZIP để cấp ID.

### F3 — P2, delivery verifier chưa portable theo các asset được bàn giao

Vị trí: `ml/scripts/verify_week5_delivery.py:91` đến kiểm ở dòng 95. Verifier đọc preservation_before của máy tác giả rồi buộc worktree bên nhận chứa **mọi** ml/artifacts và processed asset trong inventory lịch sử, gồm gói repro/README/manifest, ZIP và Git bundle cũ không có trong hai receipt release tuần 5.

Chạy mới verifier trên source tích hợp, dùng receipts tác giả giữ nguyên và accuracy/predictions chạy mới: exit1. Đã copy 600 file chuẩn; audit có 226 asset lịch sử thiếu, 0 asset hiện có khác hash. Bổ sung được 165 file bằng bytes có SHA đúng từ workspace/ZIP local, vẫn thiếu 61, thí dụ `ml/artifacts/week3/mitdb-week3-fp32-20260925-v1-repro/manifest.json`. Lần cuối vẫn exit1 tại dòng 95; chưa tới return BLOCKED/exit2. Không tái tạo các repro manifest/ZIP để giả khớp inventory.

Minh chứng: [delivery-hydrated.stderr.txt](evidence/delivery-hydrated.stderr.txt), [historical-assets-audit.json](evidence/historical-assets-audit.json), [historical-missing-copied.json](evidence/historical-missing-copied.json). Đây là thiếu dependency tái lập của aggregate, không phải thiếu 8544 mẫu hay 220 goldens hiện hành. Tài liệu mô tả exit2 khi thiếu wire allocation chưa đủ cho một checkout bên nhận có các gói chuẩn.

Yêu cầu sửa: cung cấp/authenticate đúng các dependency cần thiết, hoặc tách audit preservation toàn workspace tác giả khỏi verifier portable của tài sản bàn giao. Verifier portable vẫn phải kiểm source/model/checkpoint/manifest/payload/goldens, preservation và đủ coverage; không bỏ gate hoặc coi dependency thiếu là PASS. Receipt lịch sử 94518 file/754 copies vẫn giữ nguyên, không gọi đó là inventory chạy mới trên máy SV1.

## Python/ML chạy mới và đối chiếu

Python 3.11.9 từ `D:/HUST/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe`; torch 2.14.0+cu130, numpy 2.4.6. Child environment bỏ PYTHONHOME/PYTHONPATH, không đổi cấu hình/PATH toàn hệ thống; gcc chỉ thêm vào PATH của process. Chạy CPU deterministic, một thread, MKLDNN disabled theo repo. [environment-authentication.stdout.txt](evidence/environment-authentication.stdout.txt) xác nhận week5_common, week5_interfaces, p1 từ worktree review; packages/model/dataset được kiểm anchor trước dùng.

Quantization 6 tests, interfaces 7 tests, I2 Python/host-C 5 tests đều PASS thường/-O. Vectors/RFC8439, counter=0 cho transform, a/b phân đoạn theo kênh nguồn, uint32 LE, rejection Fisher–Yates và error ordering đã kiểm. 10000 synthetic: 0 lỗi, deterministic; 220 golden pairs: 20 mỗi s, exact q/FP16/wire bytes/dequantized/tail. Probe độc lập thường/-O kiểm tường minh tất cả 256 byte trên ba shape, 128 nghịch đảo hệ số lẻ và descriptor lỗi hai chiều. P1 bảo toàn -128/127; quantizer symmetric chỉ sinh -127..127 và dequantizer từ chối -128 theo reference.

Scale thuộc kênh gốc; unprotect trước dequantize. s9/s10 NC thêm L=1 tại I2 và bỏ trước tail. FP32 LE trên wire mở rộng đúng scale FP16 lưu/đọc lại. Serializer chỉ tạo vùng scale, không phải packet codec I1 hay nghiệm thu end-to-end. I1 v1 vẫn không mang protected payload; không áp dụng proposal I1 v2. Không tự xác nhận bảo mật/MAC/replay hoặc nonce deployment.

Accuracy **chạy mới** batch1, đủ 8544 mẫu ở từng s=0..10; exit0. Mỗi split quyết định bằng `200*(correct_FP32-correct_INT8)<8544`; boundary đúng 0.5 pp đã được test trên count1000 ở thường/-O và FAIL đúng. FP32 8393/8544 = 98.23267790262172%; worst s6 giảm 0.05852059925093633 pp. Không dùng trung bình split hoặc bộ20 để kết luận accuracy.

| s | FP32 đúng/8544 | INT8 đúng/8544 | Giảm pp (hiển thị) | Gate count exact |
|---:|---:|---:|---:|---|
| 0 | 8393 | 8391 | 0.023408240 | PASS |
| 1 | 8393 | 8390 | 0.035112360 | PASS |
| 2 | 8393 | 8391 | 0.023408240 | PASS |
| 3 | 8393 | 8392 | 0.011704120 | PASS |
| 4 | 8393 | 8393 | 0.000000000 | PASS |
| 5 | 8393 | 8395 | -0.023408240 | PASS |
| 6 | 8393 | 8388 | 0.058520599 | PASS |
| 7 | 8393 | 8391 | 0.023408240 | PASS |
| 8 | 8393 | 8391 | 0.023408240 | PASS |
| 9 | 8393 | 8393 | 0.000000000 | PASS |
| 10 | 8393 | 8393 | 0.000000000 | PASS |


Counts, gate_status và prediction disagreements khớp từng split với CSV tác giả. Predictions 93984 rows khớp nguyên bytes CSV frozen, SHA256 `0776e503b9e404c957cfcfb239356f52b17f34655cb2c5d15fdfe96cb3ae6e56`. P1 stream `cc83bbdd4c3c43dde1126a5ebaf935112aa911fc69adaff5191ae4176f42f365`; real stream `2ad478b4a35ed01a6fb4efc6f629de7f953a3854f4a5ca76e585c7e6f006287c`, đều khớp lịch sử. [independent-comparison.json](evidence/independent-comparison.json), [CSV mới](accuracy/accuracy.csv), [predictions mới](accuracy/predictions.csv).

## SV1 tuần 5 và regression

Main hiện hành: preflight và acceptance thường/-O đều PASS mới. Receipt chain REAL_USB_DFU → REAL_MCU_CAPTURE, firmware ID `04fbe659696a183e4680c16f1f425081500654da44cdb6fbf233de1372507207`, source build/nạp/đo `51ef9c966e052bfd63c8e416dcfad3d6af30e755` còn hợp lệ. Capture thật SHA256 `0c915b90658be5d01ce87eddab747f0f4c35dfdc893e1a617df8d6d42d986378`: 220 primary +16 mixed, oracle exact236, s0 identity20/20, P2 lịch sử20/20 bitwise, max FP32 error1.430511474609375e-05, unexplained mismatch0. Ba scale FP16 s10 khác golden (sample8/channel3,13/channel3,18/channel2) vẫn do head FP32 qua midpoint; Python trên chính activation MCU khớp từng byte, không whitelist.

Tree tích hợp: **checker raw capture thường/-O PASS**, firmware binding không đổi; **package preflight và acceptance tổng FAIL** vì F1. Vì thế không gọi gói SV1 trên tree tích hợp PASS. Accuracy C 8544×11 trong acceptance main là **reuse** có source/dependency/receipt hashes được acceptance verifier kiểm, không phải lần C accuracy mới và không được chuyển nhãn thành PASS integrated. Accuracy Python của reviewer đã chạy mới đầy đủ và đối chiếu số đếm.

Host C mới: Layer A220 exact goldens, Layer B220 exact oracle, forward/reverse/repeat660 mỗi layer, max head error như trên. Quantization C thường/-O kiểm 65536 binary16 decode patterns và guards. Parser/package-policy/current-R4/source tampering/release/SV2 policy/all-split/handoff/capture tuần4 liên quan đã chạy mới; xem bảng gate.

Cache suite bổ sung: thường có 15 PASS +1 SKIP WinError1314 symlink, không gọi 16/16 PASS. Mocked symlink guard PASS; actual OS symlink vẫn chưa được thực thi. Cache suite -O có 14 PASS,1 FAIL,1 SKIP: harness tạo filename opt-1.pyc theo parent -O nhưng child conventional loader không chạy -O nên không đọc forged cache. Target test cũng FAIL trên main với source không đổi: lỗi harness có sẵn, không phải regression PR25. [cache-main-O-target.stderr.txt](evidence/cache-main-O-target.stderr.txt). Probe thay thế ngoài PR dùng cùng optimization ở child, kiểm forged-cache rejection của frozen loader và mocked symlink guard: 2 PASS. Không sửa repo test, không gộp alternative thành PASS nguyên suite -O.

Không mở COM, DFU/flash/erase/recover, đo lại MCU, đổi NCS3.4.0, làm radio/DPU/I1 end-to-end hoặc C P1/50 vector tuần6. Không build mới vì đã có bằng chứng source binding/host C và lỗi provenance; build mới không giải quyết validity gói cũ. Timing/RAM/stack runtime vẫn NOT_MEASURED.

## Setup, preservation và minh chứng reuse

Hai ZIP tuần5 không ở đường dẫn chuẩn trong main, nhưng có bản local `ml/artifacts/week4/pr20-review/downloads/`. Đã hash theo receipt trust anchor `3fe550cbd3311825c7def1e2a6bb891032d0dd27ffe3990ced9f36451ee6d3ab`, copy nguyên bytes vào worktree. Checkpoint `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`; current FP32 manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`; quant manifest `8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd`; ZIP processed `b95d169f7cf454f11d21a858f6fee6f526347294f6673874318521a11ae8b0bf`; quant ZIP `3105bc879af3c4d9d4eb87725c7d165328649afd1c5dd28fe1786fe66dc4ff7b`. Loader kiểm configs/normalization/patient split/artifact hashes với frozen checkpoint trước accuracy. Không export/package/hydrate đè main hay sinh lại goldens/ZIP.

Checkout Windows mặc định làm bốn source receipt raw-LF thành CRLF (ba ps1 và requirements collector txt), dù Git blobs không đổi. Initial preflight logs giữ nguyên; đây là portability có sẵn, không quy cho diff PR25. Audit [binding-mismatches-initial.json](evidence/binding-mismatches-initial.json) so expected/main/current/blob. Để cô lập F1, materialize **đúng Git blob của integrated HEAD** cho bốn file mà normalized content, Git blob và main đều được chứng minh tương đương; không overlay ML source cũ, không sửa nội dung kỹ thuật. Git diff không có content change; index stat vẫn báo M do eol attributes. Thử refresh index không thành công, đã ghi riêng. [checkout-canonicalization.json](evidence/checkout-canonicalization.json) và source hashes canonical lưu bytes đã kiểm. Sau gate, trả đúng CRLF bytes ban đầu; trạng thái cuối ghi ở [checkout-eol-restored.json](evidence/checkout-eol-restored.json).

Các lỗi setup reviewer (fetch bị sandbox; thiếu ZIP chuẩn; audit gọi Git blob của generated header ignored; stat-only EOL check/refresh; UTF8 decode inventory) đều có transcript riêng, không bị quy thành lỗi implementation. Các log test FAIL ban đầu, FAIL cache, delivery thiếu asset và preflight cuối đều giữ nguyên; xem [setup_attempts.txt](evidence/setup_attempts.txt) và bảng gate. Không có lần preflight integrated thành công bị bỏ qua: lần cuối vẫn FAIL đúng F1.

Inventory **chạy mới** trước/sau: **35698 file**, trạng thái **PASS**, 0 thay đổi. Gồm toàn workspace (venv, .vscode, ML/data/builds/artifacts; loại .git và caches), preparation/binary/HEX/ZIP build đã nghiệm thu và session capture/receipts. Files trước thiếu/đổi: `[]`. [preservation-before.json](evidence/preservation-before.json), [preservation-after.json](evidence/preservation-after.json), [preservation-check.command.json](evidence/preservation-check.command.json). Git refs/objects mới phục vụ review không thuộc inventory immutable.


Reuse được ghi rõ: các source/log receipts tác giả trong delivery verifier, inventory lịch sử tác giả 94518 file, checksum/CSV lịch sử để **đối chiếu**, và accuracy C trong acceptance main. Raw hashes/dependencies được kiểm bởi verifier và comparison; không gọi các test tác giả hay C accuracy lịch sử là chạy mới. Delivery verifier invocation mới nhưng sử dụng receipts cũ; bản thân invocation cuối FAIL do61 dependency lịch sử còn thiếu. Các gate Python/ML/P1/R4/device checker/host nêu chạy mới là lệnh reviewer thực chạy, có log/exit riêng.

## GitHub và trạng thái cuối

PR open, Draft, merged=false; HEAD cuối không đổi. GitHub API báo mergeable=true/clean nhưng không thay thế gate review. Không có comments/reviews, check-runs0 và status contexts0; không coi zero checks là CI PASS. Public main endpoint báo protected=false, required contexts/checks rỗng; rulesets=[]; GET detailed branch protection bị403 do integration không có administration access. MCP repository permissions pull=true, push=false, admin=false. Không thử merge/write qua credential local khi gate FAIL. Metadata gốc/cuối ở [github-initial.json](evidence/github-initial.json), [github-final.json](evidence/github-final.json).

| Ref | SHA | Ahead/behind upstream |
|---|---|---|
| main | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | 0/0 |
| origin/main | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | — |
| dev/device-sv1 | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | 0/0 |
| origin/dev/device-sv1 | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | — |

Git status main: `## dev/device-sv1...origin/dev/device-sv1`; porcelain = ''. Review porcelain = ''. Nhánh review còn giữ, không push/xóa.

Cấu hình IDE: 2 file hash khớp trước review; compile database tồn tại tại `D:\HUST\ASI_week5_ide\20261010-223710\firmware\build\compile_commands.json`, 157 entries; compiler NCS tồn tại=True. App entries=4, file paths còn tồn tại=True. Không đổi configuration/database; xem final-state.json.


Không đồng bộ hoặc reset main/SV1 vì không merge. Không xóa nhánh review khi FAIL. Không push vào nhánh tác giả hoặc gửi comment/tin nhắn. PR27 và tuần6 không được thực hiện. Các giới hạn còn lại: namespace ngoài repo chưa được Châu/Trung xác nhận;61 artifact lịch sử delivery chưa có;1 actual-symlink SKIP; lỗi harness cache -O có coverage thay thế; không có xác nhận I1/Edge/DPU/radio/timing/RAM/stack mới. Không tuyên bố dự án không còn lỗi.

## Bảng toàn bộ lệnh/gate

Mỗi `.command.json` có executable, argv, cwd, source Git SHA, SHA256 project sources, stdout/stderr hashes, elapsed và exit. Mã thoát của wrapper tổng không thay mã của gate con. Dấu “new + reused receipts” chỉ rõ invocation mới không phải rerun toàn bộ receipts tác giả.

| Gate/lệnh | Kết quả | Exit | Fresh/reuse | Logs/command |
|---|---|---:|---|---|
| acceptance-integrated-canonical-O | FAIL: changed ML source binding | 1 | new | [command](evidence/acceptance-integrated-canonical-O.command.json), [stdout](evidence/acceptance-integrated-canonical-O.stdout.txt), [stderr](evidence/acceptance-integrated-canonical-O.stderr.txt) |
| acceptance-integrated-canonical | FAIL: changed ML source binding | 1 | new | [command](evidence/acceptance-integrated-canonical.command.json), [stdout](evidence/acceptance-integrated-canonical.stdout.txt), [stderr](evidence/acceptance-integrated-canonical.stderr.txt) |
| acceptance-integrated-O | FAIL: initial CRLF checkout | 1 | new | [command](evidence/acceptance-integrated-O.command.json), [stdout](evidence/acceptance-integrated-O.stdout.txt), [stderr](evidence/acceptance-integrated-O.stderr.txt) |
| acceptance-integrated | FAIL: initial CRLF checkout | 1 | new | [command](evidence/acceptance-integrated.command.json), [stdout](evidence/acceptance-integrated.stdout.txt), [stderr](evidence/acceptance-integrated.stderr.txt) |
| acceptance-main-O | PASS | 0 | new acceptance recheck; C accuracy inside report reused | [command](evidence/acceptance-main-O.command.json), [stdout](evidence/acceptance-main-O.stdout.txt), [stderr](evidence/acceptance-main-O.stderr.txt) |
| acceptance-main | PASS | 0 | new acceptance recheck; C accuracy inside report reused | [command](evidence/acceptance-main.command.json), [stdout](evidence/acceptance-main.stdout.txt), [stderr](evidence/acceptance-main.stderr.txt) |
| accuracy | PASS | 0 | new | [command](evidence/accuracy.command.json), [stdout](evidence/accuracy.stdout.txt), [stderr](evidence/accuracy.stderr.txt) |
| all-bytes-probe-O | PASS | 0 | new | [command](evidence/all-bytes-probe-O.command.json), [stdout](evidence/all-bytes-probe-O.stdout.txt), [stderr](evidence/all-bytes-probe-O.stderr.txt) |
| all-bytes-probe | PASS | 0 | new | [command](evidence/all-bytes-probe.command.json), [stdout](evidence/all-bytes-probe.stdout.txt), [stderr](evidence/all-bytes-probe.stderr.txt) |
| cache-main-O-target | FAIL reproduced on main (existing harness) | 1 | new | [command](evidence/cache-main-O-target.command.json), [stdout](evidence/cache-main-O-target.stdout.txt), [stderr](evidence/cache-main-O-target.stderr.txt) |
| cache-optimized-alternative | PASS 2 reviewer alternative tests; actual OS symlink still SKIP | 0 | new | [command](evidence/cache-optimized-alternative.command.json), [stdout](evidence/cache-optimized-alternative.stdout.txt), [stderr](evidence/cache-optimized-alternative.stderr.txt) |
| capture-regression-O | PASS | 0 | new | [command](evidence/capture-regression-O.command.json), [stdout](evidence/capture-regression-O.stdout.txt), [stderr](evidence/capture-regression-O.stderr.txt) |
| capture-regression | PASS | 0 | new | [command](evidence/capture-regression.command.json), [stdout](evidence/capture-regression.stdout.txt), [stderr](evidence/capture-regression.stderr.txt) |
| delivery-final | FAIL: missing historical assets | 1 | new invocation + reused author receipts + new reviewer accuracy | [command](evidence/delivery-final.command.json), [stdout](evidence/delivery-final.stdout.txt), [stderr](evidence/delivery-final.stderr.txt) |
| delivery-historical | FAIL: missing historical assets | 1 | new invocation + reused author receipts + new reviewer accuracy | [command](evidence/delivery-historical.command.json), [stdout](evidence/delivery-historical.stdout.txt), [stderr](evidence/delivery-historical.stderr.txt) |
| delivery-hydrated | FAIL: missing historical assets | 1 | new invocation + reused author receipts + new reviewer accuracy | [command](evidence/delivery-hydrated.command.json), [stdout](evidence/delivery-hydrated.stdout.txt), [stderr](evidence/delivery-hydrated.stderr.txt) |
| device-handoff-O | PASS | 0 | new | [command](evidence/device-handoff-O.command.json), [stdout](evidence/device-handoff-O.stdout.txt), [stderr](evidence/device-handoff-O.stderr.txt) |
| device-handoff | PASS | 0 | new | [command](evidence/device-handoff.command.json), [stdout](evidence/device-handoff.stdout.txt), [stderr](evidence/device-handoff.stderr.txt) |
| device-host | PASS | 0 | new | [command](evidence/device-host.command.json), [stdout](evidence/device-host.stdout.txt), [stderr](evidence/device-host.stderr.txt) |
| environment-authentication | PASS | 0 | new | [command](evidence/environment-authentication.command.json), [stdout](evidence/environment-authentication.stdout.txt), [stderr](evidence/environment-authentication.stderr.txt) |
| historical-week4-capture-O | PASS | 0 | new | [command](evidence/historical-week4-capture-O.command.json), [stdout](evidence/historical-week4-capture-O.stdout.txt), [stderr](evidence/historical-week4-capture-O.stderr.txt) |
| historical-week4-capture | PASS | 0 | new | [command](evidence/historical-week4-capture.command.json), [stdout](evidence/historical-week4-capture.stdout.txt), [stderr](evidence/historical-week4-capture.stderr.txt) |
| i2-O | PASS | 0 | new | [command](evidence/i2-O.command.json), [stdout](evidence/i2-O.stdout.txt), [stderr](evidence/i2-O.stderr.txt) |
| i2 | PASS | 0 | new | [command](evidence/i2.command.json), [stdout](evidence/i2.stdout.txt), [stderr](evidence/i2.stderr.txt) |
| interfaces-O | PASS | 0 | new | [command](evidence/interfaces-O.command.json), [stdout](evidence/interfaces-O.stdout.txt), [stderr](evidence/interfaces-O.stderr.txt) |
| interfaces | PASS | 0 | new | [command](evidence/interfaces.command.json), [stdout](evidence/interfaces.stdout.txt), [stderr](evidence/interfaces.stderr.txt) |
| mcu-recheck-integrated-O | PASS | 0 | new | [command](evidence/mcu-recheck-integrated-O.command.json), [stdout](evidence/mcu-recheck-integrated-O.stdout.txt), [stderr](evidence/mcu-recheck-integrated-O.stderr.txt) |
| mcu-recheck-integrated | PASS | 0 | new | [command](evidence/mcu-recheck-integrated.command.json), [stdout](evidence/mcu-recheck-integrated.stdout.txt), [stderr](evidence/mcu-recheck-integrated.stderr.txt) |
| mcu-recheck-main-O | PASS | 0 | new | [command](evidence/mcu-recheck-main-O.command.json), [stdout](evidence/mcu-recheck-main-O.stdout.txt), [stderr](evidence/mcu-recheck-main-O.stderr.txt) |
| mcu-recheck-main | PASS | 0 | new | [command](evidence/mcu-recheck-main.command.json), [stdout](evidence/mcu-recheck-main.stdout.txt), [stderr](evidence/mcu-recheck-main.stderr.txt) |
| p1-10000 | PASS | 0 | new | [command](evidence/p1-10000.command.json), [stdout](evidence/p1-10000.stdout.txt), [stderr](evidence/p1-10000.stderr.txt) |
| package-policy-O | PASS | 0 | new | [command](evidence/package-policy-O.command.json), [stdout](evidence/package-policy-O.stdout.txt), [stderr](evidence/package-policy-O.stderr.txt) |
| package-policy | PASS | 0 | new | [command](evidence/package-policy.command.json), [stdout](evidence/package-policy.stdout.txt), [stderr](evidence/package-policy.stderr.txt) |
| preflight-integrated-canonical-O | FAIL: changed ML source binding | 1 | new | [command](evidence/preflight-integrated-canonical-O.command.json), [stdout](evidence/preflight-integrated-canonical-O.stdout.txt), [stderr](evidence/preflight-integrated-canonical-O.stderr.txt) |
| preflight-integrated-canonical | FAIL: changed ML source binding | 1 | new | [command](evidence/preflight-integrated-canonical.command.json), [stdout](evidence/preflight-integrated-canonical.stdout.txt), [stderr](evidence/preflight-integrated-canonical.stderr.txt) |
| preflight-integrated-O | FAIL: initial CRLF checkout | 1 | new | [command](evidence/preflight-integrated-O.command.json), [stdout](evidence/preflight-integrated-O.stdout.txt), [stderr](evidence/preflight-integrated-O.stderr.txt) |
| preflight-integrated | FAIL: initial CRLF checkout | 1 | new | [command](evidence/preflight-integrated.command.json), [stdout](evidence/preflight-integrated.stdout.txt), [stderr](evidence/preflight-integrated.stderr.txt) |
| preflight-main-O | PASS | 0 | new | [command](evidence/preflight-main-O.command.json), [stdout](evidence/preflight-main-O.stdout.txt), [stderr](evidence/preflight-main-O.stderr.txt) |
| preflight-main | PASS | 0 | new | [command](evidence/preflight-main.command.json), [stdout](evidence/preflight-main.stdout.txt), [stderr](evidence/preflight-main.stderr.txt) |
| preservation-check | PASS | 0 | new | [command](evidence/preservation-check.command.json), [stdout](evidence/preservation-check.stdout.txt), [stderr](evidence/preservation-check.stderr.txt) |
| quantization-c-O | PASS | 0 | new | [command](evidence/quantization-c-O.command.json), [stdout](evidence/quantization-c-O.stdout.txt), [stderr](evidence/quantization-c-O.stderr.txt) |
| quantization-c | PASS | 0 | new | [command](evidence/quantization-c.command.json), [stdout](evidence/quantization-c.stdout.txt), [stderr](evidence/quantization-c.stderr.txt) |
| quantization-O | PASS | 0 | new | [command](evidence/quantization-O.command.json), [stdout](evidence/quantization-O.stdout.txt), [stderr](evidence/quantization-O.stderr.txt) |
| quantization | PASS | 0 | new | [command](evidence/quantization.command.json), [stdout](evidence/quantization.stdout.txt), [stderr](evidence/quantization.stderr.txt) |
| r4-current-O | PASS | 0 | new | [command](evidence/r4-current-O.command.json), [stdout](evidence/r4-current-O.stdout.txt), [stderr](evidence/r4-current-O.stderr.txt) |
| r4-current | PASS | 0 | new | [command](evidence/r4-current.command.json), [stdout](evidence/r4-current.stdout.txt), [stderr](evidence/r4-current.stderr.txt) |
| r4-policy-O | PASS | 0 | new | [command](evidence/r4-policy-O.command.json), [stdout](evidence/r4-policy-O.stdout.txt), [stderr](evidence/r4-policy-O.stderr.txt) |
| r4-policy | PASS | 0 | new | [command](evidence/r4-policy.command.json), [stdout](evidence/r4-policy.stdout.txt), [stderr](evidence/r4-policy.stderr.txt) |
| r4-release-O | PASS | 0 | new | [command](evidence/r4-release-O.command.json), [stdout](evidence/r4-release-O.stdout.txt), [stderr](evidence/r4-release-O.stderr.txt) |
| r4-release | PASS | 0 | new | [command](evidence/r4-release.command.json), [stdout](evidence/r4-release.stdout.txt), [stderr](evidence/r4-release.stderr.txt) |
| real-220 | PASS | 0 | new | [command](evidence/real-220.command.json), [stdout](evidence/real-220.stdout.txt), [stderr](evidence/real-220.stderr.txt) |
| week3-cache-O | 14 PASS + 1 FAIL + 1 SKIP (existing harness) | 1 | new | [command](evidence/week3-cache-O.command.json), [stdout](evidence/week3-cache-O.stdout.txt), [stderr](evidence/week3-cache-O.stderr.txt) |
| week3-cache | 15 PASS + 1 SKIP | 0 | new | [command](evidence/week3-cache.command.json), [stdout](evidence/week3-cache.stdout.txt), [stderr](evidence/week3-cache.stderr.txt) |
| week3-policy-O | PASS | 0 | new | [command](evidence/week3-policy-O.command.json), [stdout](evidence/week3-policy-O.stdout.txt), [stderr](evidence/week3-policy-O.stderr.txt) |
| week3-policy | PASS | 0 | new | [command](evidence/week3-policy.command.json), [stdout](evidence/week3-policy.stdout.txt), [stderr](evidence/week3-policy.stderr.txt) |
| week3-sv2-O | PASS | 0 | new | [command](evidence/week3-sv2-O.command.json), [stdout](evidence/week3-sv2-O.stdout.txt), [stderr](evidence/week3-sv2-O.stderr.txt) |
| week3-sv2 | PASS | 0 | new | [command](evidence/week3-sv2.command.json), [stdout](evidence/week3-sv2.stdout.txt), [stderr](evidence/week3-sv2.stderr.txt) |

