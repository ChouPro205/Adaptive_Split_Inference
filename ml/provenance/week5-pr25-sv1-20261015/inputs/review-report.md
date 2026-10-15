# Review độc lập PR25 — kết luận FAIL

Ngày 14/10/2026, Asia/Saigon. Chỉ PR25. **Chưa merge.** Có regression provenance SV1 bắt buộc; allocation deployment vẫn BLOCKED. Không thay main/SV1, không push nhánh review, không gửi comment/tin nhắn/upload, không bắt đầu tuần 6.

## SHA và phạm vi

| Vai trò | SHA |
|---|---|
| main đã fetch | `cfdfca1025ab5f707b46197b4c5dae868d38d473` |
| PR HEAD | `1ebbefb8264d9daee7b4b2cbb95be4d51f4d39c1` |
| merge-base | `65d44d2cd159b28cf9bb505a66d39ef67e8dbc19` |
| merge thử LOCAL | `651c473c9151ba1d09d89a858c2899d14c2944a4` |
| tree tích hợp LOCAL | `097a606ecdeb35202cf0e295179787cb26c501de` |

Tree local `097a606ecdeb35202cf0e295179787cb26c501de` khớp tree bàn giao tác giả. Hai parent là main và PR HEAD đã pin. SHA merge local không phải merge PR trên GitHub. Full diff và diff tích hợp được lưu nguyên trong evidence/pr-diff.txt và integration-diff.txt (mỗi file 57 MB); diff code/config, manifest, reports/receipts, registry và tài liệu liên quan được đối chiếu. Data/receipt additions được kiểm bằng scope, raw hashes, coverage và receipts mới.

## Finding bắt buộc sửa — P1: source binding thứ ba vẫn bị thay đổi

`ml/scripts/test_week5_p1.py:12` đổi import sang `week5_common_v2`, thêm output guard/result fields và đổi nhãn profile. File này nằm trong `preparation/evidence/accuracy/evaluation.json → provenance.source_files_sha256`, được `device/scripts/accept_week5_mcu.py:167` kiểm raw SHA256 trước cho reuse accuracy C. Hai file lịch sử `week5_common.py` và `evaluate_week5.py` đã giữ đúng bytes, nhưng chưa bao phủ binding của P1 test.

| Binding | Raw SHA256 |
|---|---|
| Receipt / main | `ad6be8d9b126448b2b1179cd6f9eb2da007c2c87bbb13f7869b5ad0b8ccf2cac` |
| PR / tree tích hợp | `88a3a1beeafd945074d7f0b77e82717b88ad9c46ec48a7efe2aced921a619271` |

Acceptance tích hợp thường và `-O` đều exit 1: `Frozen ML/tail source drift: ml/scripts/test_week5_p1.py`. Đối chứng trên main với cùng preparation/session gốc đều exit 0. Audit toàn bộ preparation source + C accuracy source + frozen ML provenance chỉ ra đúng mismatch này. Xem `evidence/complete-sv1-source-binding-audit.json`, `blocking-p1-source.diff` và `sv1-acceptance-original-capture*.stderr.txt`.

Yêu cầu tác giả: trả **nguyên raw bytes** `test_week5_p1.py` về main đã nghiệm thu; đưa P1 runner/result schema mới vào entrypoint/module có version mới, cập nhật full runner/verifier REQUIRED/provenance và tests tương ứng. Review lại đúng HEAD mới trên tree tích hợp; chạy lại suite và bốn gate SV1 thường/-O. Không overlay file main trong review để gọi PR HEAD hiện tại PASS, không đổi receipt/source gate hoặc rebuild/flash để thay evidence.

Tái hiện từ receiver đã hydrate, dùng raw capture P2 gốc theo byte audit:

```powershell
& 'D:\HUST\Adaptive_Split_Inference\ml\.venv\Scripts\python.exe' -B device/scripts/accept_week5_mcu.py --session 'D:\HUST\ASI_week5_mcu\20261009-212416' --preparation 'D:\HUST\ASI_week5_prepare\20261009-sv1-prepare01\preparation.json' --output '<thư-mục-mới>'
# Thêm -O trước -B cho chế độ optimized.
```

## R1/R2 và các gate độc lập

Clean receiver riêng ở `receiver/`, detached đúng integration SHA. Bốn ZIP gốc được kiểm size/SHA256 trước dùng; clean setup exit 0, đủ 569/569 dependency. Package FP32 41 file hydrate từ R3/R4 và xác thực bởi manifest/package/checkpoint gates. Không cần standalone FP32 ZIP cho receiver.

R1: 6 setup test methods thường/-O đều PASS; 10 ca setup thật gồm correct, từng header thiếu và marker ở từng header: 6 exit0, 4 marker exit1 đúng yêu cầu, bytes/mtime/marker giữ nguyên. Reviewer probes kiểm thêm generator failure, candidate sai ngay cả với header đang có, race ngay trước exclusive `xb`, cùng all-256-byte inverse/error/scale/boundary; cả hai modes PASS.

29 children mới (26 unit/regression thường/-O + P1 + real + accuracy) đều exit 0. P1 10000 synthetic, 220 tensors (20/split), unprotect trước dequantize, NC/NCL adapter và FP32 LE mở rộng từ FP16 lưu/đọc lại đều PASS. Strict đúng 0,5 pp FAIL đã được test thường/-O. Full runner và delivery verifier thường/-O exit **2/BLOCKED**, không gọi là PASS tổng.

Accuracy mới đủ 8544×11: FP32 8393/8544, worst s6 INT8 8388/8544, giảm 0.05852059925093633 pp. Predictions 93984 hàng raw SHA256 `0776e503b9e404c957cfcfb239356f52b17f34655cb2c5d15fdfe96cb3ae6e56` khớp frozen. P1 và real stream hashes khớp lịch sử. Xem `evidence/independent-frozen-comparison.json`.

## Hồ sơ SV1, newline và reuse

Preflight tích hợp thường/-O PASS. Real capture checker tích hợp thường/-O PASS đủ 220 primary +16 mixed, oracle236. Parser/package negative regressions chạy mới thường/-O PASS. Chúng không thay whole acceptance đang FAIL. Main control acceptance mới PASS: s0 20/20 bitwise, P2 20/20 bitwise, FP32 max 1.430511474609375e-05 <1e-3, oracle236, mismatch không giải thích 0. Giữ nguyên phân tích ba scale FP16 s10 khác golden do activation FP32 qua midpoint; không đổi thresholds/goldens.

3 ps1 trong checkout có CRLF khác raw LF receipt: đã đối chiếu expected/current/blob rồi chỉ materialize **blob cùng revision** đúng expected hash. Raw capture P2 tuần3 trong Git là LF nhưng original capture đã nghiệm thu là CRLF; sau đối chiếu ba bên đã copy **nguyên bytes gốc** có hash receipt vào checkout thử. Không normalize hash/file gốc. Initial acceptance exit1 tại P2 binding giữ log riêng; sau khi sửa fixture checkout đúng raw bytes vẫn exit1 tại P1 source drift. Hai byte audits ở evidence/sv1-checkout-byte-audit.json và p2-original-capture-byte-audit.json.

PR26 final integration receipt đã lưu riêng physical working-copy hashes và committed LF hashes cho reports. Đối chiếu mới trực tiếp các Git blob anchors và current results/week5 cùng receipt/log hashes, không dùng normalized hash. `evidence/accepted-pr26-report-reconciliation.json` ghi kết quả. Preparation vẫn NOT_RUN/PENDING nguyên bản; chỉ session DFU/capture/acceptance chứng minh MCU đã chạy.

Reuse: full C accuracy 8544×11 trong hồ sơ preparation, C host activations cho parser tests, original DFU/raw captures/command receipts, và preservation audit tác giả 94518/754. Invocation checker/tests/ML accuracy là chạy mới; không có MCU measurement/build/flash/COM mới. Source mismatch khiến accuracy C reuse không được acceptance tích hợp chấp nhận, dù main control chấp nhận.

## Artifact lịch sử và gói bàn giao

Hai audit gốc được tìm đúng trong phiên 20261010-pr25-01/evidence. Raw inventory anchor được xác thực; partition 226 missing =165 copied +61 unavailable được đối chiếu từng path/hash/size. Audit ngày14/10 mới phục hồi bytes khớp cho 15/61; còn46 unavailable là author-workspace extras. Chỉ1/61 là dependency portable bắt buộc: R3 ZIP, đã có đúng hash. Không xóa gate bắt buộc hoặc gọi toàn bộ extras là dependency receiver. Chi tiết đầy đủ61 hàng ở evidence/historical-61-current-audit.json.

Hai cây preparation (713 file) và MCU (83 file), hai audit, toàn inventory/logs review cũ, dependency receipts/portable/frozen/transitive và 15 recovered artifacts đã copy nguyên bytes. Không sửa path trong receipt; mappings nằm riêng. Những tham chiếu ZIP/checkpoint đã chuyển vị trí được map tới bản nguyên bytes có hash đúng. 3 DOCX yêu cầu lịch sử không có ở nguồn được dẫn, ghi rõ optional audit documents; không được verifier runtime đọc. Không còn dependency runtime evidence chưa cung cấp trong gói.

ZIP giao Châu tự gửi: `D:\HUST\ASI_pr25_review\20261014-160811-pr25-rereview\pr25-sv1-original-evidence-20261014-final.zip`.

SHA256: `4dcf8de3bba7aae761d7586ac6f684dd0558ce1a756ca197c8d28eadcee41aac`; size 230944445 B; 2280 file payload, raw 601727245 B. Inventory: `handoff-inventory-final.json`; source/copy trước-sau được kiểm lại, ZIP CRC và giải nén thử khớp toàn inventory; `handoff-verification-final.json`. Bản ZIP chưa có hậu tố -final là bản chuẩn bị trước khi bổ sung mapping, không phải gói bàn giao cuối.

## Allocation còn BLOCKED

Không tìm thấy approval trong registry/contracts/decisions hiện hành hoặc GitHub comments/reviews. Deployment IDs tiếp tục null. Xem **allocation-proposal.md** và JSON đi kèm: đủ 11 hàng s→wire ID256..266, model/profile/checkpoint, key_id/sender đề xuất, nonce reboot/retry, buffer và revision chờ chốt. Proposal không phải approval; không tạo approved_by hoặc trust anchor giả.

Châu cần chốt model_profile_id/mapping/key-sender namespace và Device deployment limits/nonce persistence; Trung cần xác nhận namespace ngoài repo, model/checkpoint/mapping, Edge capacities, key/sender scope, nonce policy, cùng registry raw SHA256/revision. Source và ELF cũ chứng minh quantized5760/C64/FP16scale128; FP32 wire scale256 không chứng minh packet buffer, I2 32768 không chứng minh Device hỗ trợ32768. Hai-buffer P1/transport deployment vẫn chưa triển khai/được nghiệm thu.

## GitHub, bảo toàn và trạng thái cuối

PR vẫn Draft/open/unmerged. Check-runs0, status contexts0 (combined status pending); không gọi zero checks là CI PASS. main protected=false, branch protection endpoint404 Branch not protected; effective rules=[] và rulesets=[]. Không bypass hoặc thử merge khi kỹ thuật FAIL. Metadata trước/cuối lưu trong evidence/github-*.json.

Inventory mới bảo toàn 35938 file across workspace/venv/IDE, preparation, session và old review evidence: PASS, 0 thay đổi/mất/thêm. `.git` và Python caches loại khỏi inventory immutable. `.vscode`, venv, assets và hồ sơ gốc giữ nguyên.

| Ref | SHA | Ahead/behind |
|---|---|---|
| main | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | 0/0 |
| origin/main | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | — |
| dev/device-sv1 | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | 0/0 |
| origin/dev/device-sv1 | `cfdfca1025ab5f707b46197b4c5dae868d38d473` | — |

Main workspace vẫn ở dev/device-sv1; porcelain rỗng. Không đồng bộ/reset refs vì chưa merge. Integration worktree và nhánh review mới giữ sạch; receiver có fixture newline/materialized sources và outputs mới được ghi rõ trong final-state.json để rerun. Cả phiên review cũ và hai worktree mới được giữ khi FAIL/BLOCKED; không xóa nhánh SV3.

## Gate table — invocation mới, exit code thật

Mỗi receipt có argv/cwd/source hashes/commit/tree/log hashes và result hashes khi có; JSON index đầy đủ ở command-index.json. Các helper-stage setup lỗi tìm ZIP R3 trước khi biết kho archive và initial acceptance newline FAIL được ghi riêng, không quy thành lỗi implementation. Reviewer orchestrator được bổ sung theo giai đoạn; self-hash trong một số wrapper receipts là snapshot trên đĩa lúc tạo receipt, không chứng minh phiên bản orchestrator đã nạp trong bộ nhớ. Các source hashes của code PR/test child và logger receipts mới là bindings cho kết quả; probes ngoài PR được lưu kèm riêng.

| Gate | Status | Exit | Receipt |
|---|---|---:|---|
| all-bytes-O | PASS | 0 | [all-bytes-O.command.json](evidence/all-bytes-O.command.json) |
| all-bytes | PASS | 0 | [all-bytes.command.json](evidence/all-bytes.command.json) |
| delivery-recheck-O | BLOCKED_REGISTRY | 2 | [delivery-recheck-O.command.json](evidence/delivery-recheck-O.command.json) |
| delivery-recheck | BLOCKED_REGISTRY | 2 | [delivery-recheck.command.json](evidence/delivery-recheck.command.json) |
| failure-window-O | PASS | 0 | [failure-window-O.command.json](evidence/failure-window-O.command.json) |
| failure-window | PASS | 0 | [failure-window.command.json](evidence/failure-window.command.json) |
| full-portable-suite | BLOCKED_REGISTRY | 2 | [full-portable-suite.command.json](evidence/full-portable-suite.command.json) |
| integrated-capture-O | PASS | 0 | [integrated-capture-O.command.json](evidence/integrated-capture-O.command.json) |
| integrated-capture | PASS | 0 | [integrated-capture.command.json](evidence/integrated-capture.command.json) |
| main-acceptance-O | PASS | 0 | [main-acceptance-O.command.json](evidence/main-acceptance-O.command.json) |
| main-acceptance | PASS | 0 | [main-acceptance.command.json](evidence/main-acceptance.command.json) |
| main-preflight-O | PASS | 0 | [main-preflight-O.command.json](evidence/main-preflight-O.command.json) |
| main-preflight | PASS | 0 | [main-preflight.command.json](evidence/main-preflight.command.json) |
| package-regression-O | PASS | 0 | [package-regression-O.command.json](evidence/package-regression-O.command.json) |
| package-regression | PASS | 0 | [package-regression.command.json](evidence/package-regression.command.json) |
| parser-regression-O | PASS | 0 | [parser-regression-O.command.json](evidence/parser-regression-O.command.json) |
| parser-regression | PASS | 0 | [parser-regression.command.json](evidence/parser-regression.command.json) |
| real-setup-correct-O | PASS | 0 | [real-setup-correct-O.command.json](evidence/real-setup-correct-O.command.json) |
| real-setup-correct | PASS | 0 | [real-setup-correct.command.json](evidence/real-setup-correct.command.json) |
| real-setup-marker-graph-O | PASS_EXPECTED_REFUSAL | 1 | [real-setup-marker-graph-O.command.json](evidence/real-setup-marker-graph-O.command.json) |
| real-setup-marker-graph | PASS_EXPECTED_REFUSAL | 1 | [real-setup-marker-graph.command.json](evidence/real-setup-marker-graph.command.json) |
| real-setup-marker-inputs-O | PASS_EXPECTED_REFUSAL | 1 | [real-setup-marker-inputs-O.command.json](evidence/real-setup-marker-inputs-O.command.json) |
| real-setup-marker-inputs | PASS_EXPECTED_REFUSAL | 1 | [real-setup-marker-inputs.command.json](evidence/real-setup-marker-inputs.command.json) |
| real-setup-missing-graph-O | PASS | 0 | [real-setup-missing-graph-O.command.json](evidence/real-setup-missing-graph-O.command.json) |
| real-setup-missing-graph | PASS | 0 | [real-setup-missing-graph.command.json](evidence/real-setup-missing-graph.command.json) |
| real-setup-missing-inputs-O | PASS | 0 | [real-setup-missing-inputs-O.command.json](evidence/real-setup-missing-inputs-O.command.json) |
| real-setup-missing-inputs | PASS | 0 | [real-setup-missing-inputs.command.json](evidence/real-setup-missing-inputs.command.json) |
| receiver-clean-setup | PASS | 0 | [receiver-clean-setup.command.json](evidence/receiver-clean-setup.command.json) |
| receiver-environment | PASS | 0 | [receiver-environment.command.json](evidence/receiver-environment.command.json) |
| sv1-acceptance-O | FAIL_INITIAL_CAPTURE_NEWLINE; superseded by authenticated-original recheck | 1 | [sv1-acceptance-O.command.json](evidence/sv1-acceptance-O.command.json) |
| sv1-acceptance-original-capture-O | FAIL | 1 | [sv1-acceptance-original-capture-O.command.json](evidence/sv1-acceptance-original-capture-O.command.json) |
| sv1-acceptance-original-capture | FAIL | 1 | [sv1-acceptance-original-capture.command.json](evidence/sv1-acceptance-original-capture.command.json) |
| sv1-acceptance | FAIL_INITIAL_CAPTURE_NEWLINE; superseded by authenticated-original recheck | 1 | [sv1-acceptance.command.json](evidence/sv1-acceptance.command.json) |
| sv1-preflight-O | PASS | 0 | [sv1-preflight-O.command.json](evidence/sv1-preflight-O.command.json) |
| sv1-preflight | PASS | 0 | [sv1-preflight.command.json](evidence/sv1-preflight.command.json) |
| accuracy | PASS | 0 | [accuracy.command.json](receiver/ml/provenance/reviewer-20261014/accuracy.command.json) |
| delivery | BLOCKED_REGISTRY | 2 | [delivery.command.json](receiver/ml/provenance/reviewer-20261014/delivery.command.json) |
| delivery_policy | PASS | 0 | [delivery_policy.command.json](receiver/ml/provenance/reviewer-20261014/delivery_policy.command.json) |
| delivery_policy_O | PASS | 0 | [delivery_policy_O.command.json](receiver/ml/provenance/reviewer-20261014/delivery_policy_O.command.json) |
| device_handoff | PASS | 0 | [device_handoff.command.json](receiver/ml/provenance/reviewer-20261014/device_handoff.command.json) |
| device_handoff_O | PASS | 0 | [device_handoff_O.command.json](receiver/ml/provenance/reviewer-20261014/device_handoff_O.command.json) |
| device_quantization | PASS | 0 | [device_quantization.command.json](receiver/ml/provenance/reviewer-20261014/device_quantization.command.json) |
| device_quantization_O | PASS | 0 | [device_quantization_O.command.json](receiver/ml/provenance/reviewer-20261014/device_quantization_O.command.json) |
| i2 | PASS | 0 | [i2.command.json](receiver/ml/provenance/reviewer-20261014/i2.command.json) |
| i2_O | PASS | 0 | [i2_O.command.json](receiver/ml/provenance/reviewer-20261014/i2_O.command.json) |
| interfaces | PASS | 0 | [interfaces.command.json](receiver/ml/provenance/reviewer-20261014/interfaces.command.json) |
| interfaces_O | PASS | 0 | [interfaces_O.command.json](receiver/ml/provenance/reviewer-20261014/interfaces_O.command.json) |
| p1 | PASS | 0 | [p1.command.json](receiver/ml/provenance/reviewer-20261014/p1.command.json) |
| quantization | PASS | 0 | [quantization.command.json](receiver/ml/provenance/reviewer-20261014/quantization.command.json) |
| quantization_O | PASS | 0 | [quantization_O.command.json](receiver/ml/provenance/reviewer-20261014/quantization_O.command.json) |
| real | PASS | 0 | [real.command.json](receiver/ml/provenance/reviewer-20261014/real.command.json) |
| registry_policy | PASS | 0 | [registry_policy.command.json](receiver/ml/provenance/reviewer-20261014/registry_policy.command.json) |
| registry_policy_O | PASS | 0 | [registry_policy_O.command.json](receiver/ml/provenance/reviewer-20261014/registry_policy_O.command.json) |
| setup_policy | PASS | 0 | [setup_policy.command.json](receiver/ml/provenance/reviewer-20261014/setup_policy.command.json) |
| setup_policy_O | PASS | 0 | [setup_policy_O.command.json](receiver/ml/provenance/reviewer-20261014/setup_policy_O.command.json) |
| week3_policy | PASS | 0 | [week3_policy.command.json](receiver/ml/provenance/reviewer-20261014/week3_policy.command.json) |
| week3_policy_O | PASS | 0 | [week3_policy_O.command.json](receiver/ml/provenance/reviewer-20261014/week3_policy_O.command.json) |
| week3_sv2 | PASS | 0 | [week3_sv2.command.json](receiver/ml/provenance/reviewer-20261014/week3_sv2.command.json) |
| week3_sv2_O | PASS | 0 | [week3_sv2_O.command.json](receiver/ml/provenance/reviewer-20261014/week3_sv2_O.command.json) |
| week4_policy | PASS | 0 | [week4_policy.command.json](receiver/ml/provenance/reviewer-20261014/week4_policy.command.json) |
| week4_policy_O | PASS | 0 | [week4_policy_O.command.json](receiver/ml/provenance/reviewer-20261014/week4_policy_O.command.json) |
| week4_release | PASS | 0 | [week4_release.command.json](receiver/ml/provenance/reviewer-20261014/week4_release.command.json) |
| week4_release_O | PASS | 0 | [week4_release_O.command.json](receiver/ml/provenance/reviewer-20261014/week4_release_O.command.json) |
| week4_tests | PASS | 0 | [week4_tests.command.json](receiver/ml/provenance/reviewer-20261014/week4_tests.command.json) |
| week4_tests_O | PASS | 0 | [week4_tests_O.command.json](receiver/ml/provenance/reviewer-20261014/week4_tests_O.command.json) |

Kết luận cuối: **FAIL — chưa đủ điều kiện merge PR25**. Blocker kỹ thuật: historical P1 script source binding; blocker quyết định: allocation chưa duyệt. Sau tác giả sửa, phải pin HEAD mới, tích hợp lại main mới nhất và rerun các gate bị ảnh hưởng, đặc biệt whole SV1 acceptance. Gói evidence đã sẵn để Châu gửi; không cần hỏi lại quyền merge khi một HEAD tương lai thực sự đạt toàn bộ điều kiện.
