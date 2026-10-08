# Xác thực checkout hiện tại trước tuần 5

Chạy từ repo root với `ml/.venv`. Device và ML dùng chung
`tools/week4_handoff_auth.py`; các manifest/release R3/R4 và tài sản khoa học
giữ nguyên. Không chạy lại release/export để thay các anchor cũ.

Trước khi chạy, hydrate đủ R3/R4 và all-split v1 theo receipts trong
[`handoff R3`](sv3_sv1_week4_handoff_r3.md) và
[`handoff R4`](sv3_sv1_week4_handoff_r4.md). Git phải có cả source commits cố định
`c793c06385198accc964e0e60988d7e7a7e9b566` và
`89109fd352d84a5fe0815d7e045e52538de7bad8`; nếu clone không chứa các objects này,
lấy từ source bundles đã xác thực theo receipts lịch sử. Wrapper không tải hoặc
thay thế bằng HEAD khi thiếu nguồn. Python/dependency versions phải khớp manifest.

```powershell
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
$sv1Compiler = 'C:/msys64/ucrt64/bin/gcc.exe'
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4_current.py --compiler $sv1Compiler
& ml/.venv/Scripts/python.exe -B -O ml/scripts/verify_week4_current.py --compiler $sv1Compiler
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week4_current.py
& ml/.venv/Scripts/python.exe -B -O ml/scripts/test_week4_current.py
& ml/.venv/Scripts/python.exe -B device/scripts/test_week4_handoff.py
& ml/.venv/Scripts/python.exe -B -O device/scripts/test_week4_handoff.py
& ml/.venv/Scripts/python.exe -B ml/scripts/test_week5_quantization.py
& ml/.venv/Scripts/python.exe -B -O ml/scripts/test_week5_quantization.py
```

Kiểm `$LASTEXITCODE` sau từng lệnh. Compiler phải là host GCC đã kiểm trong
môi trường dự án. Thay đổi environment chỉ áp dụng cho process kiểm tra;
không chỉnh cấu hình Python/NCS hệ thống.

Entrypoint mặc định xác thực **checkout hiện tại**, gồm mọi binding R4,
mọi payload R3/R4/all-split và 27 file parity. Bộ ba PR22 chỉ được chấp nhận
đúng cặp hash theo từng path từ nguồn R4
`89109fd352d84a5fe0815d7e045e52538de7bad8`, PR22
`add8503d58c6f707a35b4502bf98aff91109c1cd` và merge
`e6d3e8cc40323227d0f15a4bb4091957f2498744`. Cả ba phải cùng phiên bản;
bộ R4 gốc vẫn hợp lệ. Source ngoài phạm vi, sửa nội dung, sửa binding hoặc
payload đều bị từ chối trước khi chạy engine. Không tự chấp nhận hash/commit mới.

Sau gate hiện tại, wrapper tạo source view tạm hoàn toàn từ commit R4 cố định,
kiểm 21 bindings lịch sử rồi chạy verifier số học R4 nguyên bản. View có HEAD
detached đúng commit R4 để regression tái lập ghi đúng metadata. Object store
chỉ được đọc; current checkout/refs/index không bị thay đổi. Package copy được
xác thực lại; view tạm tự dọn. Code tính mô hình/graph và tài sản vẫn là phiên
bản đã pin, chỉ ba script verifier/test PR22 có ngoại lệ đã kiểm.

Proof tách `handoff_authentication` của nguồn hiện tại,
`historical_numerical_engine` và SHA của tooling đang chạy. Tooling hiện hành
nằm ngoài inventory source sinh release; không tự nhận là source sinh artifact.
`verify_week4.py`, `test_week4.py`, manifest và các pin lịch sử giữ nguyên.

Xác thực snapshot R4 lịch sử riêng:

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4_current.py --source-mode historical --compiler $sv1Compiler
& ml/.venv/Scripts/python.exe -B -O ml/scripts/verify_week4_current.py --source-mode historical --compiler $sv1Compiler
```

Mode này trả `WEEK4_HISTORICAL_CHECKS_PASS` với `PINNED_R4_SNAPSHOT_ONLY`;
không chứng nhận source checkout hiện tại và không thay thế gate mặc định.
Không dùng mode lịch sử để bỏ qua source hiện tại bị sửa.

Chạy lại regression ML R4 nguyên bản (21 expected rejections, tái tạo khoa học):

```powershell
& ml/.venv/Scripts/python.exe -B ml/scripts/verify_week4_current.py --regressions --compiler $sv1Compiler
& ml/.venv/Scripts/python.exe -B -O ml/scripts/verify_week4_current.py --regressions --compiler $sv1Compiler
```

Gate nguồn hiện tại vẫn chạy trước regression. Những trường hợp dùng anchor
test tự tạo trong suite lịch sử chỉ phục vụ cô lập semantic errors, không nới
anchor CLI hoặc manifest production.

Báo cáo MCU R3 chỉ chấp nhận đúng hai raw hash LF/CRLF đã xác minh; BOM,
whitespace bổ sung hay sửa nội dung đều bị từ chối. Capture/ELF/DFU đã đo giữ
provenance R3 ngày 02/10/2026. Host/reference PASS không chứng nhận firmware
tuần 5, DPU/KV260 hay một image mới chưa đo.
