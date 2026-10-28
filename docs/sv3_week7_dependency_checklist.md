# Checklist SV3 tuần 7 và điều kiện tiếp tục

**Bổ sung sửa evaluator, hồ sơ 27/10/2026:** hai lỗi split rỗng/inventory thiếu
đã được sửa và kiểm mới 18/18 thường +18/18 `-O` tại `18e74ab`; xem mục cuối.

**Cập nhật mới nhất 26/10/2026:** xem [đối soát SV2](sv3_week7_reconciliation_20261026.md)
và bảng trạng thái cuối tài liệu. Các mục mô tả ngày 21/10 bên dưới được giữ
nguyên để bảo toàn lịch sử; không đọc BLOCKED_SV2 cũ thành thiếu receipt hiện tại.
Phần offline SV3 đã làm xong; accuracy DPU và xác nhận owner vẫn chưa nghiệm thu.

Bản tài liệu đặt tại `main/docs/`; code/evidence tuần 7 được bàn giao qua
[PR #34](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/34).
Liên kết evidence được pin tới commit `1518943`; các trạng thái bên dưới giữ mốc
đối chiếu lịch sử, không coi việc chuyển tài liệu là nghiệm thu code hay KV260.

Đối chiếu ngày 21/10/2026 trên nền `3c56b657`, code độc lập `6be51e3a`.
[Báo cáo và review](sv3_ml_week7_report.md) giải thích phạm vi; [snapshot GitHub](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/provenance/week7-nopeek-20261021/github-state.json)
và [audit cuối](https://github.com/ChouPro205/Adaptive_Split_Inference/blob/151894367b0a35df83a0effd86961816ffc89942/ml/provenance/week7-nopeek-20261021/review-audit.json) là bằng chứng.
Không có xác nhận hay liên hệ nào được Codex thực hiện thay thành viên.

Trạng thái: DONE = đã có kết quả trong phạm vi ghi rõ; READY = có thể thực hiện
ngay; BLOCKED_SV2 = thiếu đầu ra cụ thể của SV2; BLOCKED_OTHER = thiếu đầu vào/
thẩm quyền khác; DEFERRED_SCOPE = chủ động để giai đoạn sau, không phải thiếu KV260.
DONE của code mới gồm commit/đẩy nhánh và các lệnh đã lưu; không đồng nghĩa đã
merge main, trình diễn cho GVHD, học hiểu hoặc nghiệm thu phần cứng.

## Phần đã hoàn tất độc lập

### W7-01 Distance correlation

- **Owner:** Kỳ Anh/SV3. **Trạng thái: DONE.** Hàm R_n biased, batch axis 0,
  suy biến trả 0 và có first-order gradient, tài liệu/tolerances rõ ràng.
- **Bằng chứng:** `ml/src/distance_correlation.py`, commit `6be51e3a`;
  `tests-final`/`tests-final-O`, tham chiếu độc lập, gradcheck và SGD thực tế.
- **Thiếu/cung cấp:** không thiếu cho toán học tuần 7. **Điều kiện nghiệm thu:**
  chạy lại 19 test; không đổi estimator/ngưỡng để hợp kết quả.
- **Bước sau/tái sử dụng:** dùng nguyên hàm cho NoPeek mọi split. Lỗi DPU không
  làm mất kết quả toán; thay dtype/estimator phải kiểm lại riêng.

### W7-02 Dữ liệu và NoPeek chạy thử

- **Owner:** Kỳ Anh/SV3. **Trạng thái: DONE** cho host offline, không cho KV260.
- **Bằng chứng:** `nopeek.py`, `nopeek_data.py`, `run_week7_nopeek.py`;
  `ml/results/week7-nopeek/smoke-final/`, lượt lặp `smoke-final-repeat-O`;
  3 split ×2 lambda, 4 bước/train và 512 val, λ=0 exact CE, gradient dCor tới head.
- **Thiếu/cung cấp:** không thiếu cho smoke; **điều kiện nghiệm thu:** checkpoint
  đúng hash, train/val đúng provenance, test không dùng, hai lượt tái lập và không
  đè baseline. Tất cả đã kiểm ở commit triển khai.
- **Bước sau/tái sử dụng:** giữ khung loss/loader/logging; nếu đổi split/checkpoint,
  tạo config/output mới và chạy lại wiring/smoke tương ứng.

### W7-03 Bảo toàn và review

- **Owner:** Kỳ Anh/SV3. **Trạng thái: DONE.**
- **Bằng chứng:** `baseline-files-before.json`, `review-audit.json`: 2.441 file
  tracked gốc không đổi raw bytes; original dataset/checkpoint cache vẫn đúng
  hash; I1 23 test và I2 5 test đạt. Hai lỗi test/path phát hiện đã sửa và kiểm lại.
- **Thiếu/cung cấp:** không thiếu trong phạm vi host. **Điều kiện nghiệm thu:**
  diff chỉ thêm source/config/tests/docs/evidence mới, không đổi contract/registry.
- **Bước sau/tái sử dụng:** giữ inventory và receipts; thay interface có revision
  mới, không sửa hay tái ký receipts lịch sử.

### W8-01 Cấu hình quét và chọn ba split đề xuất

- **Owner:** Kỳ Anh/SV3. **Trạng thái: DONE** cho việc chuẩn bị.
- **Bằng chứng:** `ml/configs/week8_nopeek_sweep.json`: s2/s5/s8,
  lambda={0,0.1,0.5,1,2,5}; lý do/tensor sizes trong báo cáo tuần 7.
- **Thiếu/cung cấp:** không thiếu để có cấu hình đề xuất; SV2 còn cung cấp xác
  nhận triển khai ở E-03. **Điều kiện nghiệm thu:** config chưa gắn deployment
  profile, không tuyên bố lưới đã chạy.
- **Bước sau/tái sử dụng:** chốt thiết kế tuần 8 với GVHD; nếu thay split chỉ sửa
  phiên bản cấu hình mới, giữ hàm toán, loader và checks.

### H-01 SV1 dùng gói P1 đúng phiên bản

- **Owner:** Châu/SV1; SV3 đối chiếu hồ sơ. **Trạng thái: DONE** cho Device/laptop.
- **Bằng chứng:** PR32/merge `3c56b65`, firmware `afa8887`; build source pin
  manifest `d0914acb…1c36`, `selftest_default.json`, `p1_vectors_50.csv` có 50/50
  protect/unprotect, 39 vector chứa 0x80; 29 file manifest đã kiểm hash lại.
- **Thiếu/cung cấp:** không thiếu receipt SV1 dùng gói. **Điều kiện nghiệm thu:**
  phạm vi MCU và laptop peer; không dùng để thay nghiệm thu KV260.
- **Bước sau/tái sử dụng:** dùng nguyên vector/capture/hash cho tích hợp Edge;
  chỉ chạy lại phần liên quan nếu firmware hoặc profile hợp lệ thay đổi.

## Những đầu ra cụ thể cần SV2

### E-01 Receipt nhận và chạy gói P1 tuần 6

- **Owner:** Trung/SV2. **Trạng thái: BLOCKED_SV2**, thuộc hồ sơ tiếp nhận.
- **Bằng chứng:** báo cáo SV2 tuần 4 xác nhận gói FP32 tuần 3, checkpoint
  `9b8be076…1f90`; chưa có receipt P1 tuần 6 trong các nguồn đã đọc. Không suy
  diễn việc trao đổi ngoài GitHub.
- **Thiếu/cung cấp:** Trung cung cấp tên gói, ZIP/manifest hash, commit tooling,
  kết quả verifier/50 vectors hoặc lỗi gặp. Pin P1 manifest phải là
  `d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36`.
- **Điều kiện tiếp tục:** nhận receipt có version/hash và log, không cần đợi DPU
  chỉ để xác nhận đã nhận/chạy kiểm host.
- **Bước sau/tái sử dụng:** đối chiếu receipt; gói P1, Python/C vectors và output
  reference tái sử dụng nguyên trạng nếu profile không đổi.

### E-02 Định danh mô hình backend đang dùng

- **Owner:** Trung/SV2. **Trạng thái: BLOCKED_SV2** cho đối chiếu backend.
- **Bằng chứng:** PR27 báo nguồn `mitdb-week3-sv2-fp32-20261001-v1` và checkpoint
  `9b8be076…1f90`; chưa có receipt triển khai hiện hành sau các sửa ở main.
- **Thiếu/cung cấp:** Trung cung cấp checkpoint SHA-256, model/source commit,
  split mapping, registry revision/profile, quantizer/compiler/runtime version,
  calibration dataset/split và sample IDs. SV3 có sẵn pin baseline đối chiếu.
- **Điều kiện tiếp tục:** các ID khớp baseline hoặc có thay đổi được review bằng
  phiên bản mới; cấm tự relabel trọng số khác vào profile hiện hành.
- **Bước sau/tái sử dụng:** khóa identity cho E-03/E-04/E-05; nếu chỉ đổi toolchain
  giữ FP32/goldens, nếu đổi checkpoint tái tạo experiment mới có provenance.

### E-03 Xmodel và bảng split thực sự chạy được

- **Owner:** Trung/SV2. **Trạng thái: BLOCKED_SV2** cho triển khai.
- **Bằng chứng:** PR27 compile 10/10; s0..7: 2 DPU+3 CPU, s8/9: 1 DPU+2 CPU.
  MD5/size báo cáo không thay thế xmodel+provenance+runtime. s10 tail identity.
- **Thiếu/cung cấp:** Trung cung cấp xmodel SHA-256/size, checkpoint/calibration
  provenance, compile logs, danh sách CPU fallback và thứ tự thực thi, kết quả
  runtime từng split cần dùng; tối thiểu xác nhận ba split đề xuất s2/s5/s8.
- **Điều kiện tiếp tục:** graph/subgraph chạy thật trên KV260 bằng đúng bộ trọng
  số E-02; không gọi một graph có CPU subgraph là “DPU thuần”.
- **Bước sau/tái sử dụng:** chốt split triển khai; offline NoPeek vẫn chạy được
  trước bước này. Nếu loại một split, chỉ thay config/lượt train split đó.

### E-04 Logits và predictions thật trên KV260

- **Owner:** Trung/SV2 sinh kết quả; Kỳ Anh/SV3 so sánh. **Trạng thái: BLOCKED_SV2.**
- **Bằng chứng:** host reference/P1 tuần 6 và goldens s0..s10 đã có; SV1 echo
  laptop không chạy inference KV260. Chưa có output KV260 gắn sample IDs.
- **Thiếu/cung cấp:** Trung cung cấp board/runtime/build ID, xmodel hash E-03,
  đầu vào và thứ tự mẫu, logits 5 lớp N,S,V,F,Q, prediction, trạng thái lỗi;
  log CPU fallback thực sự thực thi. Có thể bắt đầu bằng 20 golden/50 vector.
- **Điều kiện tiếp tục:** sample ID, shape, class order và preprocessing ghép đúng
  reference; báo cả sai số, không đổi tail/contract để khớp output.
- **Bước sau/tái sử dụng:** SV3 đối chiếu từng mẫu trước đánh giá accuracy;
  giữ reference/math/tests nếu lỗi nằm trong adapter/runner SV2.

### E-05 Accuracy và sai số của luồng lượng tử DPU

- **Owner:** Kỳ Anh/SV3 đánh giá cùng Trung/SV2. **Trạng thái: BLOCKED_SV2.**
- **Bằng chứng:** `evaluate_week5_v2.py`/quyết định tuần 5 đã có full-test FP32
  và INT8+FP16 **tail FP32**, chưa có bước requantize/input DPU thật.
- **Thiếu/cung cấp:** Trung cung cấp output backend đúng E-02/E-03/E-04 trên
  tập test frozen **8.544 sample IDs**, chính sách input/output scale và rounding,
  failures/missing samples, xmodel/quant_info hashes. Không yêu cầu profiling E-06
  hay BLE E-08 để đánh giá offline DPU accuracy.
- **Điều kiện nghiệm thu:** không rò test vào calibration/training; áp gate
  accuracy hiện hành **drop <0,5 điểm phần trăm**, kiểm nguyên chính xác
  `200*(correct_fp32-correct_dpu) < num_samples`; đồng thời báo confusion/per-class
  và raw logit errors. Ngưỡng FP32 <1e-3 không tự áp cho DPU lượng tử; nếu cần
  gate logit mới, SV3/SV2/GVHD phải thống nhất trước khi gọi PASS.
- **Bước sau/tái sử dụng:** nối output thật với reference đã pin; sửa scale/layout
  thì chạy lại comparison/accuracy tương ứng, không viết lại dCor hoặc goldens.

### E-06 Profiling tail và nạp mô hình

- **Owner:** Trung/SV2. **Trạng thái: BLOCKED_SV2** cho số đo Edge/LUT.
- **Bằng chứng:** hướng dẫn chi tiết A.2 tuần 6 yêu cầu `profile_edge.json`, đo
  cả nạp xmodel; chưa tìm thấy hồ sơ runtime này trên nhánh/báo cáo hiện có.
- **Thiếu/cung cấp:** Trung cung cấp cold load/warm cache time, inference tail
  gồm CPU fallback và copies, split/xmodel/board/runtime ID, warm-up, raw samples,
  n, mean/std/p95, đơn vị và cách đo. Tách load khỏi service/inference time.
- **Điều kiện tiếp tục:** số liệu thật trên KV260, đủ provenance và lệnh tái tạo.
  Không dùng RTT BLE của laptop hoặc thời gian smoke CPU làm thời gian DPU.
- **Bước sau/tái sử dụng:** SV3 dùng cho chọn split/Pareto sau; dCor/train offline
  không phụ thuộc số đo này và không cần chạy lại chỉ vì latency thay đổi.

### E-07 Parser và pipeline I1 v2 trên Edge

- **Owner:** Trung/SV2. **Trạng thái: BLOCKED_SV2** cho tích hợp giao thức.
- **Bằng chứng:** `contracts/i1v2_ref/vectors.json`, host C/Python và P1/output
  tuần 6 đã có; hồi quy I1 23/23 hiện tại PASS, chưa có kiểm Edge thật tương ứng.
- **Thiếu/cung cấp:** Trung cung cấp log vectors golden/negative/pipeline/response
  với mã lỗi/thứ tự đúng; parser/buffer commit, unprotect, q=-128 rejection,
  dequantize scale kênh gốc, reshape NC s9, s10 identity, response logits/tie policy.
- **Điều kiện tiếp tục:** byte/shape/scale/response khớp reference, không đổi
  offset/enum hoặc chấp nhận -128 để vượt kiểm. Phần parser có thể kiểm từ file
  trước khi BLE/DPU sẵn sàng; yêu cầu này không chặn W7-01/02.
- **Bước sau/tái sử dụng:** SV3 review lỗi theo từng stage; giữ vectors/contracts,
  sửa backend rồi kiểm lại; đổi semantics cần revision theo change control.

### E-08 KV260 central, reassembly và end-to-end

- **Owner:** Trung/SV2 cùng Châu/SV1. **Trạng thái: BLOCKED_SV2** cho pipeline thật.
- **Bằng chứng:** Device/laptop BLE đã PASS; binding xác định KV260 là central
  chính thức. Chưa có session KV260 thay laptop trong hồ sơ hiện có.
- **Thiếu/cung cấp:** Trung cung cấp USB BLE được image nhận, kernel/BlueZ,
  scan/connect/notify/MTU, fragment/reassembly/timeout/retry/duplicate-cache logs;
  key_check đối chiếu qua kênh đúng, không đưa key thật vào repo. Khi inference,
  cần E-04/E-07; echo transport có thể kiểm trước inference.
- **Điều kiện nghiệm thu:** binding hiện hành và vectors qua link thật; sau đó
  bài end-to-end tuần 8 với 100 mẫu nhãn khớp offline. Echo không thay inference.
- **Bước sau/tái sử dụng:** dùng firmware/capture/vector SV1 đã chốt; lỗi chỉ ở
  BLE Edge không yêu cầu train lại NoPeek.

## Hồ sơ và thẩm quyền còn thiếu

### H-02 Xác nhận kỹ thuật I1 v2 của SV3

- **Owner:** Kỳ Anh/SV3; Châu giữ hồ sơ contract. **Trạng thái: READY.**
- **Bằng chứng:** PR30/P1 output thật, 46 tail s0..s9 +4 identity s10, logits và
  tie cases; SV1 phụ lục A.3 ghi đã nhận semantics. Contract §14 hàng SV3 còn pending.
- **Thiếu/cung cấp:** Kỳ Anh xác nhận chính thức tensor/quantization/response
  trong đúng hồ sơ; Châu cập nhật theo change control nếu cần. Không thiếu KV260
  để xác nhận phần ML host đã kiểm, không tự coi chữ ký đã có.
- **Điều kiện tiếp tục:** xác nhận của đúng người, phạm vi ghi rõ host baseline;
  xác nhận parser/buffer KV260 của Trung vẫn là việc riêng.
- **Bước sau/tái sử dụng:** đối soát và ghi receipt/revision hợp lệ, tái sử dụng
  toàn bộ bằng chứng PR30; không sửa hash-bound contract ở phiên triển khai này.

### H-03 Revision nghiệm thu nonce registry

- **Owner:** Châu/SV1 và Trung/SV2 theo thẩm quyền registry. **Trạng thái: BLOCKED_OTHER.**
- **Bằng chứng:** Device đã có reset/mất điện/DFU/negative proof; approved registry
  vẫn `NOT_ACCEPTED`, nonce contract §8 yêu cầu revision mới sau tiêu chí 1–6.
- **Thiếu/cung cấp:** Châu/Trung review chứng cứ và phát hành revision có tên,
  xác nhận phạm vi runtime/provisioning phù hợp; không thiếu code dCor.
- **Điều kiện nghiệm thu:** giữ registry cũ, revision mới tham chiếu đúng evidence,
  đúng người phê duyệt, cập nhật consumer theo change control; không tự đổi trạng
  thái hay cấp profile mới cho trọng số NoPeek.
- **Bước sau/tái sử dụng:** dùng nonce/MCU proof hiện có; chỉ kiểm lại consumer
  theo revision mới. Nếu đổi key/sender/protocol, chạy lại các gate bị ảnh hưởng.

## Việc làm được offline nhưng để giai đoạn sau

### W8-02 Huấn luyện toàn bộ lưới dài

- **Owner:** Kỳ Anh/SV3; GVHD duyệt thiết kế thí nghiệm. **Trạng thái: DEFERRED_SCOPE.**
- **Bằng chứng:** cấu hình W8-01 và smoke đã chạy; chưa có đường accuracy–lambda
  đầy đủ, chưa chọn lambda tối ưu. Khả năng huấn luyện offline không phụ thuộc KV260.
- **Thiếu/cung cấp:** Kỳ Anh/GVHD chốt epoch/batch/seed, metrics và xử lý mất cân
  bằng; SV2 xác nhận split triển khai giúp giảm chạy lại, không phải điều kiện toán.
- **Điều kiện tiếp tục:** bước tuần 8 được mở, tạo runner huấn luyện dài riêng có
  checkpoint selection theo val, output mới; không dùng smoke runner để chạy grid.
- **Bước sau/tái sử dụng:** dùng dCor/objective/loader/wrappers/logging/tests;
  nếu SV2 đổi danh sách split chỉ train lại split cần thiết và giữ các run cũ.

### P-01 Tấn công và kết luận riêng tư

- **Owner:** Kỳ Anh/SV3 cùng GVHD. **Trạng thái: DEFERRED_SCOPE.**
- **Bằng chứng:** mới có regularizer dCor/wiring; chưa có A1/A2/GAN/thuộc tính/
  thích nghi, chưa có bảng Π hay Pareto được nghiệm thu.
- **Thiếu/cung cấp:** thiết kế threat model, dữ liệu và attacker/training của các
  tuần sau do SV3; số đo năng lượng do SV1 chỉ khi làm Pareto.
- **Điều kiện nghiệm thu:** đánh giá tấn công đúng kế hoạch, test frozen và báo
  cả thất bại của bảo vệ; không coi dCor thấp là chứng minh an toàn.
- **Bước sau/tái sử dụng:** giữ checkpoint thử nghiệm/cấu hình/ID nguồn; nếu
  representation đổi phải train/evaluate lại attacker trên phiên bản mới.

### L-01 Học hiểu và demo với GVHD

- **Owner:** Kỳ Anh và GVHD. **Trạng thái: READY**, chưa đánh dấu học hiểu DONE.
- **Bằng chứng:** code/test/log và giải thích trong báo cáo đã sẵn sàng; chưa có
  bằng chứng Kỳ Anh tự giải thích/biểu diễn trước GVHD trong phiên này.
- **Thiếu/cung cấp:** Kỳ Anh giải thích R so với R², batch/finite-sample bias,
  gradient CE/dCor, giới hạn privacy và tự chạy demo; GVHD xác nhận theo quy ước.
- **Điều kiện nghiệm thu:** demo/trao đổi thực tế, không suy từ code PASS.
- **Bước sau/tái sử dụng:** dùng ca nhỏ, log real-data và checklist này; không cần
  đợi SV2 để học hoặc demo phần độc lập tuần 7.

## Cập nhật đối soát ngày 26/10/2026

Main được fetch tại `d91fe27cc83e617d8a86ad7d6731687eea518d6a`; PR34/36 đã
merge, PR38 SV2 còn mở. Branch SV1 không có tree diff riêng so với main.
Implementation đối soát SV3 `08e4b4259a2757be7b663b88cc1c98607602d266`;
[audit mới](../ml/provenance/week7-reconcile-20261026/delivery-audit.json),
[chi tiết kiểm/owner/đầu ra còn thiếu](sv3_week7_reconciliation_20261026.md).
Không thay trạng thái/hashes/receipt ở các mục lịch sử phía trên.

| Mục | Trạng thái hiện tại và phần SV3 đã hoàn tất | Phần còn chờ /bước tiếp theo |
|---|---|---|
| W7-01/02/03 | **DONE trong scope host đã pin**; 13 source/config/evidence bindings khớp; giữ dCor/loss/smoke cũ | Không cần train/smoke lại vì checkpoint/split/tensor không đổi; không gán audit 2.441 file cũ cho main mới |
| W8-01 | **DONE chuẩn bị, giữ s2/s5/s8**; cả ba có file runtime CPU+DPU và profile model hash khớp | Chưa chọn split tối ưu cho toàn hệ thống, chưa chọn λ |
| E-01 | **DONE đối soát receipt P1 A+B**; version/ZIP/manifest/vector IDs khớp; 199 source blobs lịch sử và raw input SV3 kiểm được | Không yêu cầu SV2 gửi lại dữ liệu đã có; current-source verifier tuần 6 không PASS trên main mới, xem ghi chú đúng phạm vi |
| E-02 | **DONE đối soát định danh đã công bố**, checkpoint/model/registry/profile/wire IDs/runtime/model hashes khớp | **Chờ SV2** quant_info/quantizer provenance/compile artifacts thật gắn từng xmodel để đóng lineage calibration; 20 golden val/IDs đã có |
| E-03 | **DONE review execution** s0…s9 qua root CPU+DPU, s10 identity; s2/s5/s8 giữ được | Xmodel/binary raw chỉ có hash/inventory trên Git; không chứng nhận đã tự chạy board |
| E-04 | **DONE kiểm bảng** 50 request/backend, 46 tail +4 identity, 50/50 argmax, HOST max `1.430511e-6`, KV260 `0.4064581394` | Chỉ 5 ECG val và prediction N. Raw output SV2 chưa tự đọc; numeric DPU acceptance vẫn riêng |
| E-05 chuẩn bị | **DONE** manifest/8.544 IDs/input/reference s2/s5/s8 và evaluator có tests thường/`-O` 9/9; FP32 8.393 correct | **Chờ Trung/SV2:** output đủ 8.544×split/status/logits và provenance; chạy evaluator, gate drop <0,5 pp, confusion/per-class/errors. Không đợi BLE |
| E-06 | **DONE review profile đã công bố**, 10 model hashes qua 3 tuần khớp, load/first/steady JSON↔CSV | Là CPU/PS+DPU, cache không kiểm soát; raw timings/DPU-only/service latency chưa tái kiểm hoặc chưa đo. Không yêu cầu lại bảng đã có |
| E-07 | **DONE review ML semantics/source và bảng file pipeline**: unprotect→q→scale gốc, s9 NC, s10 identity, 5 logits/tie policy | Không tự xác nhận parser/buffer hardware thay Trung; raw output audit và numeric acceptance riêng |
| E-08 | **DEFERRED_SCOPE tuần 8** cho BLE/E2E trong nhiệm vụ này; vẫn chưa nghiệm thu Device–KV260 | Châu/Trung triển khai/kiểm link thật và 100 mẫu bằng nhiệm vụ riêng |
| H-02 | **DONE soạn dự thảo; CHỜ KỲ ANH XÁC NHẬN** | Review [draft ML I1 v2](sv3_week7_ml_i1v2_confirmation_draft.md); Châu ghi nhận đúng change control |
| H-03 | **BLOCKED_OTHER /chờ owner** | Châu/Trung phát hành revision nonce/provisioning phù hợp; không tự đổi registry ACCEPTED |
| L-01 | **DONE runbook và lệnh demo đã được kiểm thử; READY cho Kỳ Anh thực hiện** | [Demo guide](sv3_week7_demo_guide.md); chưa đánh dấu học hiểu/demo GVHD DONE |
| W8-02/P-01 | **DEFERRED_SCOPE** | Grid dài, threat model/attacks/privacy/Pareto theo thiết kế SV3/GVHD ở giai đoạn sau |

Không còn mục SV3 độc lập có đủ đầu vào mà chỉ dừng ở kế hoạch trong phạm vi
nhiệm vụ này. **Toàn bộ tuần 7 vẫn chưa DONE** do accuracy DPU và các xác nhận
bên ngoài còn mở; không tự ký, merge hoặc sửa baseline/registry/contract.

## Bổ sung sau review evaluator — hồ sơ 27/10/2026

- **E-05 /validation split: DONE phần sửa.** `split_points` phải là list
  không rỗng, int s0…s9 không bool hoặc duplicate; CLI từ chối results rỗng,
  thiếu/trùng/sai split yêu cầu trước khi ghi report hoặc chọn exit thành công.
- **E-05 /inventory reference: DONE phần sửa.** Buộc đủ `samples.csv`,
  `reference_fp32.npy`, `inputs_s{s}.npy`, `reference_wire_fp32tail_s{s}.npy`
  theo mỗi split. Kiểm file/path/size/hash trước đọc để đánh giá; thiếu mục,
  thiếu file hoặc bytes không đúng đều bị từ chối, không sửa hash để làm PASS.
- **E-05 /regressions và reference: DONE kiểm mới**, implementation
  `18e74ab198bd444e6cc0ae5eedaa9969132bd935`: 18/18 thường +18/18 `-O`;
  CLI hợp lệ 1/2 split, invalid manifests, inventory tamper/missing/path và các
  gate cũ được phủ. Reproducer xác nhận CLI source `0545b47` từng false-success,
  còn bản sửa exit 1 không tạo report. Mọi output test là SYNTHETIC_TEST_ONLY.
- **Bộ reference thật giữ nguyên và hợp lệ:** kiểm mới 8 file, 295.210.600 byte,
  manifest SHA `612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c`;
  8.544 IDs tại s2/s5/s8, 8.393 correct FP32 từ logits đã lưu. Không tạo lại
  inputs/chạy model. Giữ generation pin `08e4b42` và receipts cũ nguyên trạng.
- **E-05 nghiệm thu DPU vẫn CHỜ SV2:** output thật 8.544×split, status/logits
  và provenance/quant_info/compile artifacts. Khi nhận, chạy evaluator đã sửa,
  giữ gate `200*(correct_fp32-correct_dpu) < 8544`; không đợi BLE.
- **H-02/H-03/L-01 và numeric acceptance:** vẫn cần xác nhận thực tế của
  Kỳ Anh/Châu/Trung/GVHD theo mục cũ; không tự ký hoặc đổi registry ACCEPTED.

[Evidence mới và hướng dẫn tái kiểm](../ml/provenance/week7-evaluator-fix-20261026/README.md),
[verification.json](../ml/provenance/week7-evaluator-fix-20261026/verification.json).
Các trạng thái/tests 9/9 và receipts tại mốc `0545b47` giữ như lịch sử; không
gán bằng chứng source cũ cho evaluator mới. Toàn bộ tuần 7 vẫn chưa DONE.

## Cập nhật dependency 28/10/2026 — nguồn hiện hành

Bảng hiện hành ở [phụ lục host và hệ thống](sv3_week7_host_update_20261028.md)
thay cho việc suy trạng thái hiện tại từ các mục lịch sử phía trên.

- W7 host: source/tests/demo/reference/template sẵn sàng review, có
  [evidence mới theo revision](../ml/provenance/week7-host-20261028/README.md).
  Hai finding P2 evaluator đã đóng theo review được bàn giao, không blocker mở.
- E-08: đã có file pipeline KV260 trên main và G2 s2 200/200; PR40 head
  `8d962095` vẫn mở. Không tiếp tục ghi “chưa có BLE/KV260”; G2 không thay E-05.
- E-05: `INCOMPLETE_NO_ACCEPTANCE`, chờ Trung output thật 8.544 mẫu mỗi split
  s2/s5/s8 và provenance/artifacts. Baseline 8.393 correct, tối thiểu 8.351 và
  đủ coverage; giữ strict drop <0,5 pp. [Bàn giao](sv3_week7_sv2_handoff_20261028.md)
  sẵn sàng chuyển, chưa nói Trung đã nhận.
- H-03: r2 `CONFIRMED` ở SV1 `549aa102`, Trung xác nhận trực tiếp với Châu;
  main `02ad8c8` còn `PENDING_EDGE_CONFIRMATION`. Chờ Châu/Trung tích hợp,
  không tự sửa registry hoặc đòi lại xác nhận đã có.
- H-02/L-01: còn chờ Kỳ Anh xác nhận ML và tự giải thích/demo với GVHD.
  Lượt chạy demo chuẩn bị/kiểm thử không là bằng chứng cá nhân. W8 grid/attack vẫn ngoài scope.
