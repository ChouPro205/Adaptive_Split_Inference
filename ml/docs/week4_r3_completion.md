# Tổng kết SV3 tuần 4 — R3, review lần 2 PR #17

Release R3 sinh từ commit source đã chốt
`c793c06385198accc964e0e60988d7e7a7e9b566`, kế thừa sửa cache
`da4bebf06d015b4fce697eef08f97d1e92e086fd`. Lệnh chính thức:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/release_week4.py --repo-root . --revision r3 --compiler C:/msys64/ucrt64/bin/gcc.exe
```

Exit **0**. `ml/provenance/week4-r3/release_execution.json` ghi lệnh, cwd,
commit, exit status và log SHA. `commands.json` ghi đủ **18 lệnh exit 0**:
verifier/test tuần 3 SV1 và all-split, cache regression, 6 release tests,
export/verifier/test tuần 4, clone/checkout commit thật, verifier/test tuần 4
và all-split/cache trên checkout đó, export reproduction và verifier cho
reproduction. Không overlay source; artifacts checkout mới lấy từ ZIP R3
đã authenticate. Các log mới ở `ml/provenance/week4-r3/*.txt`.

Test tuần 4: 21 tamper rejections, 4 monotonic cases, reproduction 26 file
khoa học byte-identical và 220 golden cases bitwise. All-split verifier:
200 ONNX comparisons, strict `<1e-3`; test all-split 17 rejections. Test SV1
tuần 3: 27 rejections, giữ raw-derived inputs/C bits/goldens. Cache suite:
11 test, 10 PASS và 1 SKIP tạo symlink thật do Windows thiếu privilege;
guard symlink mô phỏng PASS. Đã kiểm cache thật, lặp verifier và forged
bytecode không được frozen loader thực thi. Không miễn gate runtime versions.

Kết quả profiling không đổi: 11 split s=0..10, 25 operations, 20 arrays,
109.653 FP32 parameter elements. Payload FP32 theo s:
`1440, 23040, 11520, 23040, 11520, 17280, 8640, 11520, 5632, 128, 20 B`.
NON_MONOTONIC=true; INT8 chỉ ước lượng, chưa có timing/firmware MCU tuần 4.

| Artifact R3 | SHA-256 | Size |
|---|---|---:|
| ZIP `mitdb-sv1-week4-fp32-20261001-r3.zip` | `4426bcd48282f84721d3dc00404de2e0cfaf38891e8fae850d15622323b972ff` | 5.659.073 bytes |
| Manifest `ml/results/week4-r3/manifest.json` | `80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c` | Xem receipt inventory |
| All-split manifest v1 trong ZIP | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` | Xem receipt inventory |

ZIP giữ đường dẫn repo, gồm 69 files: output R3 và all-split immutable tại
`ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/`.
`deliverables.json` phát hành ngoài ZIP ghi toàn bộ SHA/size và hai anchors.

405 file lịch sử được đối chiếu không đổi; 26 file khoa học R3 trùng bytes
R2. Model/checkpoint/inputs/sample order/goldens/preprocessing/tolerance
giữ nguyên. R2 docs, manifests, receipts và ZIP không sửa.
Xem `week4-review2/baseline.json` và `week4-r3/r2_preservation.json`.
Lý do R2 không khớp source `da4bebf…` và phạm vi từng bằng chứng PASS lịch
sử được ghi trong [audit](week4_review2_audit.md).

Commit bổ sung kết quả/evidence sau release chỉ thêm artifacts nhỏ, tài liệu
và logs; commit sinh artifacts trong manifest vẫn là SHA của lần export
thật. **Commit bàn giao cuối** nằm trong `source_transfer_receipt.json`
ngoài ZIP, cùng bundle/source ZIP SHA/size và final committed-checkout logs.
Nghiệm thu final checkout phải chạy trên SHA đó, không chép đè source.
Bundle và ZIP artifacts là hai thành phần bắt buộc, theo
[hướng dẫn R3](sv3_sv1_week4_handoff_r3.md).

SV1 nhận gói **PENDING** đến khi máy nhận xác nhận đủ file/commit/SHA/size
và các gate PASS. Local clone không phải máy SV1. Chưa có MCU tuần 4 hoặc
SV2 KV260 acceptance mới. Không merge hoặc flash. Chỉ công bố link tải sau
khi đã upload và xác minh; nếu thiếu kênh upload/đích nhận, giữ gói local
hoàn chỉnh và báo rõ phần còn thiếu.
