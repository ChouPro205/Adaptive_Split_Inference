# SV3 M1 NoPeek v2: checkpoint pilot và grid (12/11/2026)

Checkpoint của cả 81 run NoPeek v2 (9 run pilot và 72 run grid, epoch 0–10), chạy ngày 12/11/2026 theo bản khóa v2, TF32 tắt. Release này làm theo tin SV1 ngày 13/11/2026, mục 4, và được đăng trước khi chạy tấn công. Thư mục `ml/provenance/m1-nopeek-v2-release-20261113/` trên `dev/ml-sv3`, ở commit mà tag này trỏ tới, chứa script dựng gói, script kiểm, log và bản sao tin của SV1 (`sv1_evidence/`).

## Ràng buộc

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Protocol NoPeek v2 | `ml/configs/mitdb_m1_nopeek_protocol_v2.json` | `83cce64defefa979abcf8c31cc27daf9ae81604caae911acf0901cba3783cf35` |
| Plan (81 cấu hình run) | `ml/manifests/mitdb-nopeek-m1-v2/plan-manifest.json` | `e2e4e85856ed1d1861a771388d40de24c27c1ff6ffbfac2138ea275f76b650f9` |
| File khóa và authorization | `ml/provenance/m1-nopeek-v2-lock-20261112/m1_nopeek_v2_lock_and_train_authorization.json` | `fe38f3a9f8a2dc4596fb46cb16defd9f917336a4efe38d5806ef7205f0872ad5` |
| Receipt pilot | `ml/provenance/m1-nopeek-v2-run-20261112/pilot-receipt.json` | `6b507258466aa1a21fba12365b8ba1e52512b4b820256586639e4fbdd809dc5b` |
| Receipt grid | `ml/provenance/m1-nopeek-v2-run-20261112/grid-receipt.json` | `67c938817f8f6eea0ab493d34e66bf6d04df3baec05bef043a4b6cb766dc7d84` |
| Lựa chọn grid | `ml/provenance/m1-nopeek-v2-run-20261112/grid-selection.json` | `9f7ab9bf008e066f6d921fa231a7d4b72ae8d4b75cb82d11c6f31b651ea8e48e` |

Run chạy từ commit khóa `8f81a91`. Receipt và lựa chọn nằm ở commit `c535158`.

## Tài sản

- `SV3_M1_NOPEEK_V2_CHECKPOINTS_20261112.zip` (365.412.646 byte), SHA-256 `df34b13e4ce478353e52cf5bfb907f9f37c1b5884980b86b4f5f153645dae351`. Zip có 1.949 entry: `PACKAGE_SHA256SUMS.txt` và 1.948 file của `ml/data/runs/nopeek-m1-v2-20261112/` (400.210.929 byte trước khi nén). Trong đó có 891 checkpoint (81 run × epoch 0–10). Mỗi run còn có metric validation theo epoch, `history.json`, `summary.json` và `attempt-identity.json` (GPU, torch, cờ TF32). Ngoài ra có kết quả từng stage, `pilot-decision.json` và `pilot-grid-result.json`. Zip không có arrays và không có DS2.
- `SV3_M1_NOPEEK_V2_CHECKPOINTS_20261112.zip.sha256`.
- `PACKAGE_SHA256SUMS.txt` (303.740 byte), SHA-256 `5b58c9fe160b9dea173254561804fc3e6afc3c9b3408378b2dd494d4a5bb3dde`. File này trùng file cùng tên trong zip, để đối chiếu SHA mà không cần tải zip.

Zip dựng hai lần ra cùng byte.

## Checkpoint dùng cho tấn công

ρ0 là checkpoint A, SHA-256 `fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c` (Release `sv3-m1-v4-checkpoint-lock-20261105` và gói A). Bảng dưới lấy theo `grid-selection.json`; mỗi seed dùng epoch đã chọn của chính nó. Đường dẫn: `ml/data/runs/nopeek-m1-v2-20261112/grid/grid-<s>-lambda<λ>-seed<seed>/checkpoint-epoch-<epoch>.pt`.

| s | Vai trò | λ | Seed | Epoch | SHA-256 |
|---|---|---:|---:|---:|---|
| s2 | ρ1 (seed triển khai) | 2 | 20261101 | 3 | `6e04b7259f0bfa2165303c4ecbcef148024d543e7b2a802fb38d0cc9da6abe3b` |
| s2 | λ 0 đối chứng, cùng seed và epoch (3a) | 0 | 20261101 | 3 | `44be97a1063a015f4b82d3cd0954f3521368ea0691b18765faf4ec1d93271d9f` |
| s2 | Seed còn lại của λ đã chọn (3c) | 2 | 20261030 | 3 | `d2bd639b6008e17ad71add21f00a54fdcdaea748229e4ce80751ad23f6234578` |
| s2 | Seed còn lại của λ đã chọn (3c) | 2 | 20261031 | 3 | `3a0efcb19bb34711bf0000182dae810f5556dd102e7d36d9381657a37ee79d23` |
| s4 | ρ1 (seed triển khai) | 1 | 20261031 | 3 | `7ef1cff382397383dc198f0d67e64b950e5152e6aaca3e3361563ae952b1823f` |
| s4 | λ 0 đối chứng, cùng seed và epoch (3a) | 0 | 20261031 | 3 | `823a002a8a8cf76b2adaecb64b172aa37933a2fe384a2a7051d100d053a98026` |
| s4 | Seed còn lại của λ đã chọn (3c nếu s_m = s4) | 1 | 20261030 | 3 | `d48f3df8cf4d74842ce198fc98ba2c41bcc741fcb2dafc4352fb027d956d0ea5` |
| s4 | Seed còn lại của λ đã chọn (3c nếu s_m = s4) | 1 | 20261101 | 4 | `020940b895546d477577c4b793db66423381ef38c119595f7397a389b3942e59` |
| s5 | ρ1 (seed triển khai) | 1 | 20261030 | 2 | `1698c9427ffd2b3497940a879530d98ef3e6a35318691c51aac7c28a55aa56dc` |
| s5 | λ 0 đối chứng, cùng seed và epoch (3a) | 0 | 20261030 | 2 | `526dfa1a309558da33a1c13e2ff2d127b1870dc63ac023027eaa2ad874048fd6` |
| s5 | Seed còn lại của λ đã chọn (3c nếu s_m = s5) | 1 | 20261031 | 1 | `5b95fdbc61b4a67216e632d1c0976d020c4053d861c38205062cde0b4ce91d68` |
| s5 | Seed còn lại của λ đã chọn (3c nếu s_m = s5) | 1 | 20261101 | 4 | `b9c5bb96bc330e5a449bd103c96a652991c0d2e6613934b2eb76d9d5afcc2199` |
| s8 | ρ1 (seed triển khai, chỉ chạy offline) | 5 | 20261031 | 5 | `a6ebc8c30f5fe25f4baf37e0eff9d1866d419873c8c6f99b14eb362cd81b2625` |
| s8 | λ 0 đối chứng, cùng seed và epoch (3a) | 0 | 20261031 | 5 | `841ad17994d6f6636d6c52ec7cabd24b83ef1fc3536a34b3a44d1164aafebdd5` |
| s8 | Seed còn lại của λ đã chọn | 5 | 20261030 | 5 | `fd3276347dc3dc7a6bdb991d03684376795081093fc3b880c8fd48515912ac60` |
| s8 | Seed còn lại của λ đã chọn | 5 | 20261101 | 5 | `ed157e7bbc65975f99a66738616eb1b43dccf75b957171915d4f9193dc1225db` |

`grid-selection.json` vẫn ghi `SELECTED_FOR_SV1_REVIEW_NOT_LOCKED` vì file được viết trước khi SV1 xem. Ngày 13/11, SV1 đồng ý dùng các checkpoint ρ1 ở trên (bản sao tin ở `sv1_evidence/`). Attack protocol v2 sẽ ràng buộc các SHA này khi khóa.

## Lưu ý

- Chạy lại trên cùng GPU (RTX 5060, TF32 tắt) cho checkpoint trùng bit. GPU khác thì không trùng bit, nên các file trong Release này là bằng chứng duy nhất của mô hình.
- Kiểm hash và kiểm inventory không phải bằng chứng chất lượng mô hình hay bằng chứng riêng tư.

## Kiểm

Giải nén zip vào gốc một checkout tại commit của tag. Trên Windows nên dùng thư mục có đường dẫn ngắn, vì có đường dẫn sâu.

```
sha256sum -c SV3_M1_NOPEEK_V2_CHECKPOINTS_20261112.zip.sha256
sha256sum -c PACKAGE_SHA256SUMS.txt
python -B ml/provenance/m1-nopeek-v2-release-20261113/verify_runs.py
```

`verify_runs.py` chỉ dùng thư viện chuẩn của Python, không cần torch. Script kiểm các điểm sau:

- inventory khớp đúng, không thiếu, không thừa file;
- cấu hình của từng run khớp plan;
- SHA của mọi checkpoint và history khớp receipt pilot/grid và summary;
- mọi run đều tắt TF32 và không mở DS2;
- các file ở mức trên cùng khớp bản đã commit;
- `PACKAGE_SHA256SUMS.txt` khớp các file.

Script in ra bảng vai trò ở trên. Script không đọc arrays và không mở DS2.
