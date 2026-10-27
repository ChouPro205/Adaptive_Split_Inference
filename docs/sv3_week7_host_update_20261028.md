# SV3 tuần 7 — cập nhật host ngày 28/10/2026

Ngày hồ sơ: **28/10/2026, Asia/Saigon**. Owner SV3: **Bùi Kỳ Anh**.
Phần host sẵn sàng review; **chưa nghiệm thu accuracy DPU, chưa xác nhận cá nhân
ML hoặc demo GVHD, không gọi toàn bộ checklist DONE**. Các mục lịch sử ngày
21–27/10 và receipts cũ giữ nguyên; phụ lục này cập nhật trạng thái tiếp nối.

## Nguồn và tích hợp

Checkout `exports/sv3-week7-reconcile-20261026`, duy nhất branch `dev/ml-sv3`,
sạch lúc nhận tại `4e027b22b936f628e60aa4215aebb7f0ff66cfc4`.
Đã đọc AGENTS ở root và contracts đúng checkout. Kiểm trực tiếp GitHub bằng
connector PR và `git ls-remote` trước khi fetch; không dùng cached origin/main
để xác định GitHub. Git Schannel gặp lỗi credential; dùng OpenSSL cho lần đọc
và fetch thành công, không đổi Git config toàn cục.

| Nguồn | Pin kiểm ngày 28/10 | Kết luận và trạng thái tích hợp |
|---|---|---|
| GitHub main | `02ad8c83297d5bee9298342b2bd4e4ff406922ac` | Đã merge vào SV3 bằng `32ea846c3bc1dfabc0e0145ae336fa49030c125b`, không conflict |
| Bốn commit SV3 | `08e4b4259a2757be7b663b88cc1c98607602d266`, `0545b470ebccb577baa8e11c1fff1c502f716b17`, `18e74ab198bd444e6cc0ae5eedaa9969132bd935`, `4e027b22b936f628e60aa4215aebb7f0ff66cfc4` | Giữ nguyên và là ancestor; không rebase/reset |
| [PR34](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/34) | merge `cbb54157431cb278b165c5b00931f2b806fbbca2` | dCor/NoPeek đã merge; hai finding P2 evaluator đã sửa ở `18e74ab`, review chấp nhận theo bàn giao của Kỳ Anh ngày 28/10; không liệt kê là blocker mở |
| SV1 tuần 7, main | `02ad8c8:docs/sv1_device_week7_report.md` | PASS 9/9 do SV1 công bố, MCU/PPK2/BLE với laptop stub; đã tích hợp, không phải phép đo mới của SV3 |
| [PR40](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/40), SV2 | `8d962095a11a0e41696b9cdeac163ed0d240daed` | Còn mở; file pipeline KV260 tuần 7 đã trên main; service G2 persistent s2 và export tuần 8 có trên nhánh SV2, chưa tích hợp PR40 vào main/SV3 |
| r2 trên nhánh SV1 | `549aa1021c250c5c8319f99c35b5b6d90c9744d1:contracts/sv1_sv2_week8_registry_revision_r2.json` | `CONFIRMED`, hiệu lực ghi 27/10, nguồn Trung xác nhận trực tiếp với Châu, do SV1 ghi; không có comment PR thay cho cuộc trao đổi đó |
| r2 trên main/checkout SV3 | `02ad8c8:contracts/sv1_sv2_week8_registry_revision_r2.json` | `PENDING_EDGE_CONFIRMATION`; cập nhật SV1 trên chưa tích hợp. Giữ nguyên file/registry và báo cáo lịch sử |

Nguồn pin, snapshot JSON, checksum export và phạm vi tìm output:
[hồ sơ mới](../ml/provenance/week7-host-20261028/README.md).
JSON xác nhận r2 không phải chữ ký mật mã hoặc lần kiểm board mới của SV3.
r2 chỉ xét nonce persistence Device; provisioning, quyền P1, production và
Edge high-water bền qua restart vẫn không được mở bởi phụ lục này.

PR38 đổi thông báo `samples must be 1..20` thành `samples must be 1`, giữ
predicate `samples == 1` trong `tail_runner.cpp`. Vì Git blob khác execution
tuần 7, audit source-exact 26/10 không được gán PASS cho source main mới.
[Đối chiếu source hashes và diff](../ml/provenance/week7-host-20261028/source-drift.json)
ghi thay đổi này; receipts/runtime cũ vẫn thuộc hashes thực đo, không chỉnh
source pin hoặc checksum để làm chúng khớp revision mới.

## Reconciliation và dependency checklist hiện tại

| Mục | Phần đã có, đúng nguồn | Còn chờ đúng owner |
|---|---|---|
| W7-01/02/03 | dCor R_n biased, objective CE+λ·dCor, loader/train-val và tests/smoke lịch sử đã có; tái kiểm suite thường/`-O` trên source cuối | Không còn việc implementation host tuần 7 độc lập bị chặn bởi SV2 |
| E-01/02/03/04/06/07 | Audit P1 A+B/file pipeline/root GraphRunner CPU+DPU/profile trên main kế thừa hồ sơ 26/10; không yêu cầu lại bảng/IDs/hash đã có | Trung: quantizer provenance, quant_info/compile artifacts và raw output nếu cần byte audit lineage; không gán bảng đã công bố thành tự chạy board |
| E-08 / G2 | Main PR39 có Device receipt 100 mẫu×P0/P1 = 200 chu kỳ. SV2 PR40 ghi 212 request toàn phiên, G2 200/200 khớp bit offline; bổ sung 21/21 và offline repeat 100/100 | Không còn ghi “chưa có BLE/KV260”. PR40 vẫn chờ review/tích hợp theo owner; trace HCI bổ sung cả buổi chưa khôi phục theo report SV2 |
| E-05 chuẩn bị | Reference frozen s2/s5/s8 đủ 8.544 mẫu/split, evaluator đã sửa và tests, gói chuyển giao/template có kiểm checksum | Trung/SV2: output full-test thật 25.632 row cùng provenance và artifacts; Kỳ Anh/SV3 tiếp nhận, kiểm rồi chạy evaluator |
| H-02 | [Draft ML I1 v2](sv3_week7_ml_i1v2_confirmation_draft.md) sẵn sàng | Kỳ Anh xác nhận thực tế phạm vi ML; Châu ghi theo change control. Yêu cầu làm việc này không tự là xác nhận |
| H-03 | r2 `CONFIRMED` trên SV1, main pending; nguồn trực tiếp Trung→Châu đã ghi rõ | Châu/Trung xử lý tích hợp revision; không yêu cầu Trung xác nhận lại chỉ vì main chưa cập nhật |
| L-01 | [Runbook](sv3_week7_demo_guide.md), demo Codex forward/backward mới, không optimizer step, weights trước/sau khớp | Kỳ Anh tự giải thích/demo; GVHD ghi nhận. Chưa xác nhận đã hiểu/đã demo |
| W8-01 | Giữ đề xuất s2/s5/s8, không chọn split/λ tối ưu từ timing hoặc demo | Grid dài/attacks/privacy/Pareto: SV3/GVHD, ngoài phạm vi phiên này |

G2 đo **tính đúng của đường truyền/so với cùng backend**; 87/100 agreement
reference trên bộ 100 mẫu được chọn theo mục tiêu G2 không phải accuracy test
độc lập. Theo SV2, N 54/55, S 8/11, V 25/25, F 0/1, Q 0/8; max absolute
logit error `5.721122741699219`. Đã ghi nhận lệch lớp Q/F và hòa logits trong
báo cáo SV1/SV2; không loại mẫu hoặc dùng bộ này chọn threshold.

## DPU full-test và bàn giao

Chưa thấy output `sv3-week7-dpu-output/1` thật đủ test trong results/ml/results
của main, nhánh SV1/SV2 đã pin hoặc vùng tiếp nhận cục bộ `.cache`, `results`,
`ml/results` đã kiểm. Không suy diễn inbox ngoài checkout. Vì chưa có output
đủ provenance/full-test, **E-05 là INCOMPLETE_NO_ACCEPTANCE; chưa có metrics
DPU full-test mới**. Kết quả G2 đã có không bị bỏ qua và không thế chỗ E-05.

[Bàn giao cho Trung](sv3_week7_sv2_handoff_20261028.md) chỉ đóng gói input/reference
có sẵn, không inference/regenerate. Manifest giữ nguyên SHA-256
`612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c`,
generation commit `08e4b42`. Gate vẫn strict drop **<0,5 điểm phần trăm**:
`200*(8393-correct_dpu) < 8544`, cần **ít nhất 8.351 correct và đủ 8.544 mẫu
mỗi split**. Mọi missing/failure là `INCOMPLETE_NO_ACCEPTANCE`.
Khi nhận, SV3 kiểm artifact bytes/hash/calibration lineage rồi chạy evaluator
đã sửa; báo confusion, per-class precision/recall/F1/support, macro-F1, accuracy,
missing/failures, class agreement và errors so full FP32/wire FP32-tail.

## Bằng chứng revision cuối

Lệnh, environment, source/log SHA, commit thực chạy và kết quả nằm riêng tại
[week7-host-20261028](../ml/provenance/week7-host-20261028/README.md).
Source/docs được commit trước khi thu evidence; commit hồ sơ sau chỉ thêm
kết quả, không gán lại receipt cho revision khác. Kiểm cuối tại HEAD giao
được lưu `.cache/week7-host-final-20261028/` và ràng buộc HEAD thực tế.
Không thay baseline, patient split, normalization, test, goldens, ignored arrays,
contract hoặc registry. Không publish/push/merge PR trong nhiệm vụ này.
