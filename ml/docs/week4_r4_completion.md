# SV3 tuần 4 R4 — sửa thứ tự inventory SV2

Commit sửa và export: `89109fd352d84a5fe0815d7e045e52538de7bad8`.
Commit bàn giao được pin riêng trong `source_transfer_receipt.json` ngoài
ZIP, sau khi commit tài liệu/evidence. Manifest không gán commit bàn giao
cho lần export trước đó. Source hashes phải khớp tại cả hai commit.

Release: https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week4-r4-20261003 .
PR #17 đã merge ngày 2026-10-02, trước bản sửa; bổ sung branch và mô tả PR
không tự đưa fix vào main. Không tạo PR mới, merge, force push hoặc flash.

## Kết quả và bằng chứng

Windows, Python 3.11.9, GCC 15.2.0, torch 2.14.0+cu130, numpy 2.4.6,
onnx 1.23.1, onnxruntime 1.30.0, protobuf 7.36.2, ml_dtypes 0.6.0,
flatbuffers 25.12.19, matplotlib 3.11.2; khớp dependency gate của manifest.

```powershell
$env:PATH='C:\msys64\ucrt64\bin;'+$env:PATH
& ml/.venv/Scripts/python.exe -B ml/scripts/release_week4.py --repo-root . --revision r4 --compiler C:/msys64/ucrt64/bin/gcc.exe
```

Exit **0**. Quy trình chính thức chạy **18 lệnh exit 0**, gồm verifier/test
tuần 3 SV1, verifier/test SV2, suite cache/inventory, 6 release tests,
export/verifier/test tuần 4; sau đó clone commit thật, hydrate ZIP đã
authenticate, chạy lại gate tuần 4/SV2/cache, export và verify reproduction.
Danh sách lệnh đầy đủ, cwd, commit, exit và log SHA ở
`ml/provenance/week4-r4/commands.json`; log gọi release ở `release_execution.json`.

| Gate | Kết quả tại commit export |
|---|---|
| SV2 verifier trên v1 nguyên bản | PASS; 200 ONNX comparisons, max error 2.6226043701171875e-6, strict <1e-3 |
| SV2 tamper suite | PASS; 17 expected rejections |
| Cache + inventory suite | 15 PASS, 1 SKIP symlink thật vì WinError 1314; guard mô phỏng PASS |
| POSIX/reversed inventory trên Windows | PASS; mỗi lần chạy đủ verifier 200 comparisons; v1 không đổi |
| SV1 tuần 3 | PASS verifier, 27 expected rejections |
| Tuần 4 | PASS; 21 tamper rejections, 4 monotonic cases, 220 golden cases bitwise, 109653 C FP32 elements |
| Release/hydration security suite | PASS; 6 tests |
| WSL Ubuntu 24.04 | Probe Path thật PASS, exit 0; chỉ kiểm thứ tự |
| Verifier đầy đủ Linux và ACK SV1/SV2 | PENDING; WSL chỉ có Python 3.12.3, thiếu môi trường pin |

Trước sửa, test mới chạy với common.py tại `2506239` fail exit 1 với
`Inventory differs`. Sau sửa suite exit 0. Hai kết quả đầu là working-tree
tests, ghi rõ trong [audit](week4_inventory_order_fix.md); không gán chúng
cho checkout đã commit. Gate release ở trên xác nhận commit `89109fd`.
Final bundle checkout được kiểm sau commit bàn giao; logs riêng trong
`r4-validation-logs.zip` và receipt. Local clone không thay ACK máy nhận.

## Artifact và bảo toàn lịch sử

| Nội dung | SHA-256 | Bytes |
|---|---|---:|
| `mitdb-sv1-week4-fp32-20261001-r4.zip` | `0b29c1f0bd1327efdf5cad17d0dcfd40fb76cb9d8f7dce3ee8dc5ab4c25dfd8e` | 5659076 |
| R4 manifest anchor | `3ca39030081c6b53a5191f927ead6fdc84cdeba1c69766bbdbc9f1cb9ca3d49a` | Xem receipt |
| V1 manifest anchor giữ nguyên | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` | Xem receipt |

ZIP R4 gồm 69 file với đường dẫn repo: 41 file all-split v1 nguyên bản và
28 file output R4. Không đóng gói lại ZIP v1; ZIP v1 cũ vẫn có SHA
`b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7`.
Scripts bên trong v1 vẫn là lịch sử; luôn chạy verifier từ source checkout mới.

`r3_preservation.json`: **389 file lịch sử không đổi**, gồm packages tuần
3, output R1/R2/R3, provenance R3, ZIP/bundle/transfer R3 và exports R3.
R4 so với R3: **26 file khoa học trùng byte**, host C report cũng trùng byte.
Chỉ `manifest.json` khác, tại đúng hai trường:

- `source_git_commit`: commit export mới.
- `source_files`: hash của `week3_sv2_common.py` và `test_week3_sv2_cache.py`
  thay đổi tương ứng bản sửa và regression; các source hash khác giữ nguyên.

Không đổi model, checkpoint, inputs, samples, goldens, tolerance, graph,
payload, weights, header hoặc figures. ZIP mới có SHA/size riêng vì manifest
mới và đường dẫn revision mới; không chỉnh checksum của asset cũ.
R3 verifier với source mới bị từ chối exit 1 tại source-hash gate, đúng
thiết kế; log `r3_expected_source_rejection.txt` ghi nhận rõ.

Xem [hướng dẫn SV1/SV2 và lệnh Linux](sv3_sv1_week4_handoff_r4.md).
Bundle/ZIP source, SHA/size và commit bàn giao cuối nằm trong receipt.
Chỉ công bố tải thành công sau khi kiểm SHA/size của bytes tải thực tế;
upload/download evidence nằm ở `exports/week4-r4/upload_receipt.json`.
