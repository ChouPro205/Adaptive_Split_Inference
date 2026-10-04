# Sửa inventory SV2 và bàn giao tuần 4 R4

## Phạm vi và nguyên nhân

Source nền: `2506239d62f620a41b860f4487ca3ee58c349cd5`, branch
`sv3/week3-sv2-fp32-handoff`. PR #17 đã được merge trước phiên sửa này;
các commit bổ sung trên branch không tự cập nhật `main`. Không merge mới,
không flash, không huấn luyện hoặc triển khai tuần tiếp theo.

`sorted(package.rglob("*"))` sử dụng phép so sánh Path của hệ điều hành.
Manifest v1 được xuất trên Windows: `README.md` nằm sau `models/...`;
POSIX đặt `README.md` trước `evidence/...`. Cả hai có 40 bản ghi giống nhau
về path, hash, size, shape và dtype, nhưng phép so sánh list cũ từ chối.

`authenticate()` nay sắp xếp cả hai list theo chuỗi `row["path"]` trước khi
so sánh toàn bộ bản ghi. Không dùng dict loại mất phần tử trùng. Không đổi
inventory exporter, expected-manifest-sha256, kiểm tra file hay bảo vệ
cache/symlink/frozen loader của `da4bebf06d015b4fce697eef08f97d1e92e086fd`.

Gói `mitdb-week3-sv2-fp32-20261001-v1` giữ nguyên mọi byte, kể cả scripts:

- ZIP SHA-256: `b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7`.
- Manifest anchor: `a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6`.

SV2 phải chạy verifier từ **source checkout mới**, trỏ tới package v1
nguyên bản; không chạy hoặc thay scripts bên trong package.

## Hồi quy trước khi commit bản sửa

Evidence ở `ml/provenance/week4-inventory-fix/`. Log trước/sau có HEAD nền
2506239; đây là kiểm thử working tree, chưa phải kiểm thử commit bàn giao.
`before_fix` dùng common.py nguyên bản tại HEAD cùng test mới chưa commit;
`after_fix` dùng common.py đã sửa cùng test mới. Gate release và bundle
checkout sau đó phải ghi SHA commit thực tế riêng.

- `before_fix`: test verifier thật trên v1, chỉ thay thứ tự inventory bằng
  PurePosixPath; exit **1**, `Inventory differs` đúng lỗi cần tái hiện.
- `after_fix`: cùng suite mở rộng, exit **0**, 16 test: **15 PASS, 1 SKIP**
  tạo symlink thật do Windows thiếu privilege. Guard symlink mô phỏng PASS.
  Verifier đầy đủ chạy 200 so sánh ONNX cho cả thứ tự POSIX và đảo ngược.
- Test từ chối file thiếu/thừa, duplicate ở manifest hoặc inventory,
  sai hash/size/shape/dtype và anchor sai. Manifest fixture được tạo trong
  thư mục tạm; không thay anchor của release. Các test cache và bytecode
  giả trước đây được giữ nguyên và vẫn chạy.
- `linux_probe`: WSL Ubuntu 24.04, Linux kernel 6.18.33.2, Python 3.12.3;
  thao tác Path thật tái hiện khác biệt thứ tự, exit **0**. Đây chỉ là
  kiểm tra thứ tự đường dẫn, **không phải PASS verifier Linux**.
  WSL thiếu Python 3.11.9 và toàn bộ dependency tensor/ONNX được pin;
  verifier đầy đủ Linux và nghiệm thu máy SV2: **PENDING**. Không bỏ gate
  runtime để chạy bằng Python 3.12.

Windows dùng `ml/.venv/Scripts/python.exe` Python 3.11.9 và requirements
của repository: `requirements-gpu-cu130.txt`, `requirements-week3-onnx.txt`.
Kiểm thử thứ tự POSIX bằng PurePosixPath trên Windows là mô phỏng rõ ràng.

## R3 và revision mới

R3 đã phát hành giữ nguyên. Source-hash gate R3 ràng buộc common.py và
test cache cũ, vì vậy R3 không nghiệm thu được với source mới; không đổi
manifest R3 để làm gate PASS. R4 phải xuất bằng `release_week4.py` từ
commit sửa đã chốt và sạch, ghi đúng commit export vào manifest. Receipt
source transfer bên ngoài ZIP ghi đúng commit bàn giao, được kiểm lại trên
bundle checkout thật. Mọi nghiệm thu SV1/SV2 vẫn PENDING đến khi nhận ACK.

Suite order mới được thêm vào `test_week3_sv2_cache.py` để cả release gate
và receiver gate hiện có tự chạy nó, đồng thời source hash của test đã nằm
trong manifest tuần 4. Không thay đổi quy trình release để bỏ qua gate.
