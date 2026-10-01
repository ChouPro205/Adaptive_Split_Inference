# PR #17 — audit trước sửa review lần 2

Đối chiếu ngày 2026-10-01: local HEAD và GitHub PR #17 cùng
`da4bebf06d015b4fce697eef08f97d1e92e086fd`, PR mở, chưa merge.
Đã đọc AGENTS.md, Git diff, tài liệu tuần 3/4, manifests, receipts và logs.
GitHub trả danh sách discussion/review/inline threads rỗng; không có bằng
chứng về chat chưa lưu. Các ghi chép Cline là lịch sử, giữ nguyên.

| Công việc lịch sử | Bằng chứng và giới hạn |
|---|---|
| `dd1d456` / `6e9af10` | Canonical L=10, s=0..10; all-split v1, 200 ONNX FP32 comparisons. SV2 hardware acceptance riêng còn pending. |
| `39231d0c86c9f0291c2dbb4697e2a0a5b4999d2a` | Implementation profiling tuần 4: 11 boundaries, graph 25 ops, 20 arrays, 109.653 FP32 parameters, C99 header, Figure 2, NON_MONOTONIC=true. |
| `1ef28806fa5533fa56afafe746ecb5008ae96c34` | R2 sửa provenance/gates. `week4-r2/completion.json` và `committed-checkout/summary.json` ghi verifier/test exit 0 trên checkout đúng commit, không overlay source. |
| `416820f84dca5f26497233ef69b3b159153c47eb` | Handoff R2 ghi lần kiểm evidence HEAD verifier/test PASS; không phải nhận thiết bị. |
| `5429689b3440ec6bcb2fe5571387be3839a27ee2` | `week4-r2/source-transfer/summary.json`: clone bundle tự chứa, verifier/test exit 0. Bundle SHA `018bf4aa8e4074310054660b6a60e1d82fbd31aef8ff99146b11a31be37d8b9c`, 3.653.678 bytes. |
| `96fe4ad05353d397cc360528912a3eb0f9c0e19e` | Commit ghi lại bằng chứng bundle R2 của `5429689…`; không biến nó thành bằng chứng của source mới hơn. |
| `da4bebf06d015b4fce697eef08f97d1e92e086fd` | Sửa inventory cache, hạn chế tên CPython cache cạnh source đã giao, ngăn cache writes ở entrypoints, frozen loader compile source đã authenticate thay vì đọc `.pyc`. |

R2 manifest ghi generating HEAD `39231d0…`, vì release trước đây chạy khi
source sửa R2 chưa commit. Do đó 18/18 regression trong
`week4-r2/regressions-complete/summary.json` ghi HEAD `39231d0…`; đây là bằng
chứng working tree lúc chạy, không đủ để khẳng định 18 gate chạy trên clean
checkout `1ef2880…`. Bằng chứng clean checkout/bundle ở bảng trên chỉ ghi
verifier/test tuần 4. Không gộp các phạm vi này.

R2 manifest anchor:
`940371931c3138da2c8757ee2d847ed1fe22e2504fd790e25509b7f54c00fa67`.
R2 ZIP SHA `0ac95f9855484659ea1d8c988dd77d7a4635427169a7bdc8ed1884fef19f1140`,
5.658.710 bytes. R2 giữ nguyên, bao gồm historical manifests và receipts.

Trên HEAD `da4bebf…`, hai source bindings của R2 đã khác:
`ml/scripts/week3_common.py` và `ml/scripts/week3_sv2_common.py`.
Verifier R2 chạy lại trước sửa exit **1**, lý do
`Source file changed: ml/scripts/week3_common.py`. Lệnh đầy đủ, log hash,
hash cũ/mới và snapshot 405 file lịch sử nằm trong
`ml/provenance/week4-review2/`. Đây là rejection đúng của source gate,
không phải lý do bỏ gate hay sửa manifest R2.

R3 phải phát hành từ source đã commit, dùng exporter/release chính thức,
hash mới và ZIP mới. Clean checkout nhận artifacts từ ZIP authenticated,
không overlay source; chạy verifier/test/reproduction tuần 4 và regression
tuần 3 chịu ảnh hưởng. Giữ model/checkpoint/20 inputs/goldens/tolerance.

SV1 nhận R2 chưa có kênh/ACK. Việc tạo và kiểm local không phải đã chuyển
gói. SV1 nhận R3 cũng PENDING cho đến khi máy nhận xác nhận đủ file,
SHA/size/commit và các gate PASS. Không merge hoặc flash.
