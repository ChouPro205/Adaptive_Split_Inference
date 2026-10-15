# SV3 tuần 6 — gói 50 vector P1 và xác nhận output

**PASS bàn giao SV3 tuần 6 trong phạm vi A+B trên host.** Ngày 16/10/2026.
MCU/BLE, nonce NVS và KV260/DPU vẫn cần nghiệm thu độc lập của SV1/SV2.

## Source, phạm vi và hiện vật

- Base mới nhất đã fetch: `af31ea784700cea1633b5c6290536a5208d052da` (PR29), nhánh `sv3/week6-p1-vectors-20261016`.
- Implementation sinh vector: `766a3cfa7e7828ecd00b9eb23cc3e5da4015ced5`. Commit `dec0449` ban đầu có typo SHA
  nền; gate dừng trước khi tạo gói, logs giữ nguyên. `766a3cf` sửa pin chính xác
  và thêm regression. Không thay SHA lịch sử hoặc đổi hợp đồng để PASS.
- Source hiện hành, registry và dependency đều đã được đọc/kiểm; không thấy quy
  định tên branch chi tiết ngoài các nhánh SV3 hiện có, nên dùng mẫu `sv3/weekN-*`.
  Worktree riêng `C:/Users/Admin/Adaptive_Split_Inference_sv3_week6_20261016`;
  clone updated và mọi checkout cũ được giữ nguyên.
- Model/checkpoint `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`;
  model package manifest `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.
- Input thật: 220 sample/split pairs validation tuần 5, manifest
  `8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd`.
  Chọn 5 mẫu đầu s0..s5 và 4 mẫu đầu s6..s10, không tạo tensor synthetic thay thế.
  Nhãn `not_week6_p1_vectors` của manifest nguồn giữ nguyên; gói mới có provenance riêng.
- Registry đã duyệt: profile `1296651265`, wire IDs `256..266`, key label `65537`,
  sender `131073`. Key duy nhất được dùng là public `00..1f`, **PUBLIC_TEST_ONLY**;
  không đọc hoặc sử dụng key bench/vận hành. Nonce sequence 1..50 cố định theo vector index.

[Release và checksum](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week6-p1-v1-20261016) đã upload và tải lại đủ 4 assets, nguyên bytes.
Không commit model, dataset hoặc ZIP lớn. Snapshot code + log + bộ vector nằm
trong handoff ZIP; implementation commit tách khỏi commit thêm evidence để không
có provenance tự tham chiếu.

| Artifact | Số byte | SHA-256 |
|---|---:|---|
| `mitdb-week6-p1-50-20261016-v1.zip` | 412045 | `2afbab35b601ac14128c32018d6dc1d39afd1991759a7a0fd9ad2051d923359a` |
| `sv3-week6-p1-handoff-20261016-v1.zip` | 1714357 | `40294b39c3863d9b5c72a807e971662bebfbcf38bb6246c20d4b6c1ec84a84cd` |

Manifest gói vector: **`d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36`** (406 file tính cả manifest).
Manifest băm mọi file ngoại trừ chính root manifest; ZIP hash báo ngoài ZIP.
Xem [receipt artifact](../provenance/week6-p1-20261016/delivery-assets.json) và
[upload/download verification](../provenance/week6-p1-20261016/release-publication.json).

## Kết quả thực sự đã chạy

| Gate | Kết quả mới |
|---|---|
| 50 vector thật, 11 split | PASS; s0..s5 mỗi split 5 ca, s6..s10 mỗi split 4 ca |
| q/FP16 giữ nguyên nguồn, shape/wire/descriptor/nonce | PASS; descriptor 28 B, nonce 12 B; unique sequence 1..50 |
| Python protect và unprotect | 50/50 byte-exact |
| C reference protect ↔ Python / C unprotect ↔ q | 50/50 + 50/50, trên chính bộ 50 mới |
| Byte 0x80 trong transformed | 39/50, tự nhiên với dữ liệu và key/nonce cố định |
| Output semantics | 46 tail s0..s9 + 4 identity s10, 5 logits N,S,V,F,Q, không softmax |
| Tie-breaking | 3 ca hòa riêng, chọn index nhỏ nhất; không tính trong 50 tensor thật |
| Package regressions | 16/16 thường và 16/16 `-O` |
| CLI file thiếu / file bị sửa | Exit 1 đúng mong đợi, không tạo passing result |
| I2 / I1 v2 regression | 5/5 và 23/23 tests, thường/`-O`; gồm C/Python, RFC, 4000 differential fuzz |
| I1 v2 golden | `make_vectors.py --check` exit 0 thường/`-O` |
| Quantization / interfaces / allocation v3 / registry v2 lịch sử | 6/7/7/5 tests, mỗi suite thường/`-O` |
| Approved registry với tensor thật | 220/220, code/registry/FP16 mapping hiện hành |
| P1 hiện hành | 10.000 round-trip byte-exact mới |
| Tái sinh package / ZIP | 406/406 file hash trùng, ZIP bytes trùng |
| Giải nén sang path độc lập | A+B PASS lại; handoff ZIP kiểm từng member sau giải nén |
| Bảo toàn | 210 source bindings trước triển khai không đổi; 569 dependency và 4 ZIP gốc khớp hash |

27 command trong [final command index](../provenance/week6-p1-20261016/final/command-index.json)
đều exit 0; hai CLI negative runs riêng exit 1 được ghi đúng kỳ vọng. Bootstrap,
source tests và lượt sinh lỗi ban đầu có receipt riêng, không xóa log lỗi.
Mỗi receipt có argv/cwd/time/environment/source hashes/stdout/stderr/exit.
C build: GCC MSYS2 15.2.0, C99 `-O2 -Wall -Wextra -Werror -pedantic`.
Python 3.11.9, torch 2.14.0+cu130, NumPy 2.4.6, ONNX 1.23.1, ORT 1.30.0;
CPU eval/inference, N=1, deterministic, one-thread, MKLDNN disabled.

[Chi tiết 50 Python/C](../provenance/week6-p1-20261016/final/p1_50.json),
[output semantics](../provenance/week6-p1-20261016/final/output_50.json),
[reproduction](../provenance/week6-p1-20261016/final/reproducibility.json),
[preservation](../provenance/week6-p1-20261016/final/preservation.json).

## Output semantics và sai số

Đã đọc model thật/frozen operation order, class mapping và I1 v2 §8.2. Model
kết thúc Linear 5 output, không Softmax/LogSoftmax/Sigmoid; response giữ nguyên
logits, có giá trị âm/>1. Tie tests đi qua encode/parse response và predicted_class.
Mỗi request thật đi qua parser → unprotect → kiểm q → dequantize theo kênh gốc,
callback tail đúng split → encode/parse response. s9 chuyển `[1,32,1]` về NC
`[1,32]`; s10 không gọi callback, không nạp/tạo tail_s10, trả identity chính xác FP32.

- q/P1 và C/Python: so raw bytes, yêu cầu byte-exact.
- Cùng q đã khôi phục với tail: output trước/sau P1 byte-identical; cả 50 output
  khớp reference logits lượng tử đã đóng băng (max abs quan sát 0).
- Đối chiếu float với reference dùng đúng `week3_sv2_common.TOLERANCE < 1e-3`,
  không đổi ngưỡng. Sai số quantized vs FP32 lớn nhất trong bộ này là
  `0.059641361236572266`, **chỉ chẩn đoán**, không coi là gate accuracy/DPU.
- Bảng nguồn 220 validation pairs không phải test set chính thức. Không báo
  accuracy DPU hoặc suy ra gate accuracy tuần 5 từ 50/220 vector này.

I2 spec còn mô tả các trạng thái chưa có activation/registry của giai đoạn cũ;
đã ưu tiên kế hoạch tuần 6 và registry/approval hiện hành như yêu cầu. Không có
mâu thuẫn byte phải sửa hợp đồng. Không sửa bảng approval/contract của SV1.

## Tái lập và sử dụng

Dùng clone đầy đủ tại implementation commit hoặc hậu duệ có cùng source bindings,
Python đúng môi trường và GCC. Nếu thiếu asset, tải đúng bốn ZIP gốc theo
[hydrate tuần 5](week5_delivery_v2.md), kiểm SHA/size bằng manifest hiện hành:

```powershell
python -B ml/scripts/setup_week5_delivery_v2.py --asset-cache <cache-4-ZIP-goc>
python -B ml/scripts/generate_week6_p1.py --source-commit 766a3cfa7e7828ecd00b9eb23cc3e5da4015ced5 --output <new-parent>/mitdb-week6-p1-50-20261016-v1
python -B ml/scripts/verify_week6_p1.py --package <package> --expected-manifest-sha256 d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36 --compiler gcc --output <new-A.json>
python -B ml/scripts/verify_week6_output.py --package <package> --expected-manifest-sha256 d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36 --output <new-B.json>
python -B ml/scripts/test_week6_p1.py --package <package> --expected-manifest-sha256 d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36
python -B ml/scripts/package_week6_p1.py --package <package> --expected-manifest-sha256 d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36 --output <new.zip>
```

Mọi output/log path phải mới; script từ chối ghi đè. `-O` dùng cùng arguments.
[README từng vector](week6_p1_package_readme.md) giải thích q raw, FP16 bits LE,
descriptor, nonce, request và logits. Code chính: `week6_p1.py`; ba entrypoint
`generate_week6_p1.py`, `verify_week6_p1.py`, `verify_week6_output.py`.

Luồng để đọc lại sau: q+scale nguồn → NCL metadata → descriptor/nonce → protect
→ transformed/request → unprotect byte-exact → scale kênh gốc → adapter NC nếu
cần → frozen tail/identity → 5 raw logits → argmax. Generator không tính lại scale.

SV1 tích hợp ngay 50 q/descriptor/nonce/public key và transformed/hash chuẩn,
port C lên MCU rồi capture từng vector. Host C PASS không thay capture MCU.
SV2 có request I1 v2 thật để kiểm parser/recovery; đánh giá DPU đợi backend
KV260 thật, cùng test set chính thức và gate tuần 5 không thay đổi.
Không triển khai firmware/BLE/NVS hoặc KV260 thay nhóm, không mở tuần 7/privacy/LUT.

Receipt tuần 5 vẫn chứng nhận snapshot lịch sử `3caf40a`; không chạy whole
verifier v3 trên source tuần 6 để tự gán PASS, không sửa inventory/anchor/receipt.
Các hồi quy trên là chạy mới; chỉ model, tensor, goldens và reference lịch sử
được tái sử dụng có kiểm hash. Nghiệm thu toàn tuần 6 chưa hoàn tất.
