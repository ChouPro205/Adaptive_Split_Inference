# SV3 → SV1 tuần 4 — revision R4

R4 sửa thứ tự inventory theo OS tại `89109fd352d84a5fe0815d7e045e52538de7bad8`,
giữ bảo vệ cache của `da4bebf…`. R3 và all-split tuần 3 giữ nguyên. R3
không nghiệm thu source mới. Tên ZIP giữ ngày 20261001 theo quy trình
export hiện có; R4 phát hành ngày 2026-10-03 tại
https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-week4-r4-20261003 .
Kết quả tuần 4: 11 split s=0..10, graph 25 ops, 20 parameter arrays và C99
header 109.653 FP32 elements; Figure 2 thể hiện payload không đơn điệu.
INT8 chỉ là ước lượng numel × 1; chưa có firmware/timing MCU tuần 4.

Source, artifacts, logs và receipt phải được authenticate qua trusted
checkout/kênh độc lập trước khi chạy. Nguồn nằm trong Git bundle tự chứa
`adaptive-split-inference-r4.bundle`; artifacts trong
`mitdb-sv1-week4-fp32-20261001-r4.zip`. Cả hai là bắt buộc.

`source_transfer_receipt.json` ngoài ZIP ghi **commit bàn giao** chính xác,
bundle SHA/size, ZIP SHA/size, manifest anchors và file inventory.
`ml/provenance/week4-r4/deliverables.json` là receipt lúc phát hành, ghi
**commit sinh artifacts** giống `manifest.source_git_commit`. Commit ghi
thêm evidence sau phát hành không tự nhận là commit sinh artifacts: receipt
bàn giao pin commit cuối và kiểm toàn bộ source hashes trên commit đó.
Hai SHA có thể khác vì evidence được commit sau khi lệnh đã chạy; source
release phải giống byte/hash và được kiểm trên checkout bàn giao thật.

| Nội dung ZIP R4 | Đường dẫn từ repo root |
|---|---|
| All-split immutable v1, gồm model/checkpoint/config, 20 inputs/11 goldens, 10 ONNX | `ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/` |
| All-split manifest anchor | `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6` |
| Profile/graph/figures/manifest R4 | `ml/results/week4-r4/` |
| 20 arrays | `ml/results/week4-r4/weights/` |
| Full C99 header | `ml/results/week4-r4/firmware/head_parameters.h` |

Đọc tổng kết tại `ml/docs/week4_r4_completion.md` và logs ở
`ml/provenance/week4-r4/`. Folder bàn giao còn có final checkout logs,
`SHA256SUMS.txt` và receipt cập nhật đúng bundle. Local PASS và upload không
thay thế ACK của SV1: **SV1_RECEIPT_PENDING** cho đến khi máy nhận kiểm đủ
file và trả commit, SHA/size, exit status/logs PASS. Không merge/flash.

Sau khi đã authenticate receipt, từ folder bàn giao chạy PowerShell:

```powershell
$r = Get-Content -Raw source_transfer_receipt.json | ConvertFrom-Json
$bundle = (Resolve-Path adaptive-split-inference-r4.bundle).Path
if ((Get-FileHash $bundle -Algorithm SHA256).Hash.ToLower() -ne $r.bundle_sha256) { throw 'Wrong source bundle' }
if ((Get-Item $bundle).Length -ne $r.bundle_size_bytes) { throw 'Wrong source size' }
git clone $bundle sv1-r4-checkout
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
Set-Location sv1-r4-checkout
git checkout --detach $r.source_commit_sha
if ($LASTEXITCODE -ne 0 -or (git rev-parse HEAD) -ne $r.source_commit_sha) { throw 'Wrong source commit' }
git bundle verify $bundle
if ($LASTEXITCODE -ne 0) { throw 'Bundle failed' }
```

Cài environment theo requirements, hoặc chỉ định interpreter bên ngoài đã
pin. Python 3.11.9 và các dependency phải khớp manifest. Không dùng source
trong immutable all-split v1 để thay source checkout đã sửa cache.

Tại checkout, hydrate artifacts từ ZIP đã authenticate bằng API chính thức
(truyền đường dẫn receipt/ZIP ngoài checkout và dùng interpreter đã pin):

```python
import json, sys
from pathlib import Path
sys.path.insert(0, "ml/scripts")
from release_week4 import hydrate
r = json.loads(Path("../deliverables.json").read_text(encoding="utf-8"))
hydrate(Path("."), Path("../mitdb-sv1-week4-fp32-20261001-r4.zip"),
        r["archive_sha256"], r["archive_size_bytes"], r["files"])
```

Hydration xác thực toàn ZIP và từng member trước khi bổ sung file; file đã
có trong checkout phải trùng bytes, khác nội dung thì từ chối ghi đè.
Không cần dataset, checkpoint tuần 2 duplicate hoặc DOCX cho gate tuần 4.

```powershell
$d = Get-Content -Raw ../deliverables.json | ConvertFrom-Json
& <PINNED_PYTHON> -B ml/scripts/verify_week4.py --repo-root . --output-dir ml/results/week4-r4 --expected-manifest-sha256 $d.week4_manifest_sha256 --compiler gcc
if ($LASTEXITCODE -ne 0) { throw 'Week 4 verifier failed' }
& <PINNED_PYTHON> -B ml/scripts/test_week4.py --repo-root . --output-dir ml/results/week4-r4 --expected-manifest-sha256 $d.week4_manifest_sha256 --compiler gcc
if ($LASTEXITCODE -ne 0) { throw 'Week 4 tests/reproduction failed' }
& <PINNED_PYTHON> -B ml/scripts/verify_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 $d.week3_manifest_sha256
if ($LASTEXITCODE -ne 0) { throw 'All-split verifier failed' }
& <PINNED_PYTHON> -B ml/scripts/test_week3_sv2.py --package ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1 --expected-manifest-sha256 $d.week3_manifest_sha256
if ($LASTEXITCODE -ne 0) { throw 'All-split tests failed' }
& <PINNED_PYTHON> -B ml/scripts/test_week3_sv2_cache.py
if ($LASTEXITCODE -ne 0) { throw 'Cache/inventory regression failed' }
```

SV1 báo mọi SKIP và lý do cùng logs. Test symlink thật có thể SKIP khi
Windows không cấp quyền; guard mô phỏng vẫn phải PASS. Sai phiên bản Python
hoặc dependency không được miễn gate do bản sửa cache.

Lệnh release tác giả (chỉ chạy một lần cho revision chưa tồn tại):

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/release_week4.py --repo-root . --revision r4 --compiler C:/msys64/ucrt64/bin/gcc.exe
```

Frozen checkpoint SHA
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Model source SHA
`520b615aa342b0a328b70de8ccffa141dbe13ad9b973bc4d2caf449a9d0afa14`.
Giữ preprocessing, IDs/order, NCL s0..8, NC s9..10, `<f4` và C order.
Golden kiểm bitwise; ONNX/MCU strict `<1e-3` giữ nguyên. SV1 chọn wire IDs,
port head và nghiệm thu thiết bị riêng. SV2 Vitis AI/xmodel/VART/KV260
acceptance pending riêng, không chặn nghiệm thu SV3 offline.

## SV2 Linux: source mới, package v1 nguyên bản

PR #17 đã merge trước bản sửa; lấy branch mới hoặc bundle R4, checkout
đúng `source_commit_sha` trong receipt R4 đã authenticate. Không dùng
checkout main cũ hoặc scripts đóng trong package v1. Giữ nguyên mọi file
trong v1, ZIP và manifest anchor; không chép scripts mới vào v1.

Tại repo root, dùng Bash và môi trường Python 3.11.9 của SV2 đã pin theo
`ml/requirements-gpu-cu130.txt` và `ml/requirements-week3-onnx.txt`.
Thay PACKAGE bằng đường dẫn tuyệt đối tới v1 nguyên bản đang có:

```bash
set -euo pipefail
PYTHON=python3.11
PACKAGE=/absolute/path/mitdb-week3-sv2-fp32-20261001-v1
ANCHOR=a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6

# Ghi bằng chứng source/môi trường và kiểm anchor độc lập.
git rev-parse HEAD
"$PYTHON" --version
"$PYTHON" -m pip freeze
printf '%s  %s\n' "$ANCHOR" "$PACKAGE/manifest.json" | sha256sum --check -
"$PYTHON" -B ml/scripts/verify_week3_sv2.py --package "$PACKAGE" \
  --expected-manifest-sha256 "$ANCHOR" 2>&1 | tee sv2-v1-verifier.txt
"$PYTHON" -B ml/scripts/test_week3_sv2.py --package "$PACKAGE" \
  --expected-manifest-sha256 "$ANCHOR" 2>&1 | tee sv2-v1-tests.txt
"$PYTHON" -B ml/scripts/test_week3_sv2_cache.py 2>&1 | tee sv2-cache-inventory.txt
```

`test_week3_sv2_cache.py` có hai test cache và một test inventory dùng v1
ở đường dẫn chuẩn trong checkout. Nếu package nằm ngoài checkout, suite
có thể SKIP các test đó; phải báo SKIP, không gọi tất cả PASS. Để chạy đủ,
đặt một **bản sao byte-identical** của v1 vào đường dẫn chuẩn
`ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/` hoặc hydrate R4 bằng
API ở trên; không chỉnh sửa package. Hai lệnh verifier/test có --package
vẫn trực tiếp kiểm gói v1 tại đường dẫn đã chỉ định.

Trạng thái tác giả: Windows verifier/gate đã chạy; mô phỏng POSIX và đảo
list trên Windows đã chạy verifier đủ 200 ONNX comparisons. WSL Ubuntu
24.04 chỉ chạy probe thứ tự Path thật; Python 3.12.3 thiếu dependency pin.
**Verifier đầy đủ Linux PENDING; ACK SV1/SV2 PENDING.** Không dùng probe
hoặc clone local để thay nghiệm thu máy nhận.

SV1 gửi lại commit, SHA/size bundle và artifact ZIP, manifest anchor,
log/exit từng gate tuần 4 và tuần 3 all-split/cache, mọi SKIP và lý do.
SV2 gửi commit, Python/dependency versions, SHA ZIP v1/manifest, stdout +
stderr và exit từng gate, số 200 comparisons và max error, mọi SKIP; chỉ
xác nhận sau khi chạy trên máy Linux nhận. Không merge, flash hoặc chuyển
sang tuần tiếp theo trong bàn giao này.
