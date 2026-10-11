# PR25 F1/F3 — tái lập có phạm vi, version 2

CURRENT WEEK=5; REVIEW_STATUS=PENDING. Tổng BLOCKED vì registry chưa duyệt.

`week5_common.py` và `evaluate_week5.py` là source lịch sử bị receipts SV1
ràng buộc. Giữ nguyên raw bytes theo main `cfdfca1025ab5f707b46197b4c5dae868d38d473`:
`c1842a380afddaaf7e7968bfdd3ff7c03e08d36e9bec205da2819abdca105934` và
`c420029c0b8b1d7834bb32db0c428f379c1659cef3cc99ffa9a1271bfeb88eef`.
Entry mới là `evaluate_week5_v2.py`, import `week5_common_v2.py`. Gate exact
`200*(correct_FP32-correct_INT8)<num_samples`; n phải 8544 tại mọi s0..s10.
Đúng 0,5 điểm phần trăm FAIL. Không đổi source gate hoặc receipt SV1.

## Dependency và scope

`ml/manifests/week5_delivery_scope_v2.json` khai báo **569 file bắt buộc**,
đường dẫn tương đối, SHA256 raw bytes, kích thước, version, nguồn và member ZIP.
Bao gồm model/checkpoint, toàn package FP32 (manifest độc lập `a6d168...`),
processed dataset, quantization20/220 goldens, frozen results, năm ZIP,
R3/R4 dependencies cho regression, source reference bất biến, hai header fixture
host tái lập exact và receipts preservation lịch sử được authenticate.
Nguồn ZIP và mọi SHA256/kích thước đầy đủ nằm trong manifest:

| Dependency | Nguồn | Version |
|---|---|---|
| mitdb-frozen-processed-week5-v1.zip | GitHub Release sv3-week5-v1-20261005 | week5-v1 |
| sv3-week5-quantization-reference-v1.zip | Cùng release | week5-v1 |
| mitdb-week3-sv2-fp32-20261001-v1.zip | Transfer đúng ZIP gốc từ SV3; receipt `ml/provenance/week3/mitdb-week3-sv2-fp32-20261001-v1.verification.json`; chưa xác minh URL public | 20261001-v1 |
| mitdb-sv1-week4-fp32-20261001-r3.zip | GitHub Release sv3-week4-r3-20261001 | r3 |
| mitdb-sv1-week4-fp32-20261001-r4.zip | GitHub Release sv3-week4-r4-20261003 | r4 |

Không rebuild ZIP/goldens/manifests hoặc checkpoint để điền dependency thiếu.
Thiếu/sai hash file bắt buộc exit1; không biến thành PASS. Mọi fresh gate buộc
source dependencies khớp raw hashes, logs và result files có SHA256, accuracy
đủ prediction coverage/counts, preservation before/after đúng toàn scope.

Audit toàn workspace tác giả được tách thành
`verify_week5_author_workspace_v1.py` (giữ logic cũ). Nó vẫn cần toàn workspace
lịch sử, snapshot source mà receipts từng test đã kiểm, và không phải verifier
cho máy nhận. Receipts 94518 file/754 copies không sửa; verifier portable kiểm
bytes và tính toàn vẹn của receipts, ghi rõ REUSED_AUTHOR_WORKSPACE_AUDIT.
Inventory mới của máy nhận là 569 file trong scope, không gọi là 94518/754.

Chỉ `C:/Users/Admin/Downloads/review_report.md` được cung cấp trong phiên sửa.
Không có `evidence/historical-assets-audit.json` hay
`evidence/historical-missing-copied.json`; không có thư mục
`D:/HUST/ASI_pr25_review/20261010-pr25-01`. Vì vậy chưa đối chiếu được **61 đường
dẫn cuối** reviewer thiếu. Ví dụ repro/manifest/ZIP/bundle trong báo cáo thuộc
audit workspace; kết luận từng file cần hai audit đầy đủ. Cần nhận hai audit,
inventory gốc và command/log hydrated được dẫn; không đoán danh sách 61.
Scope portable dựa trên inventory releases đã xác thực, không dựa vào xóa file
khỏi danh sách 61 chưa nhận. Missing required dependency trong scope vẫn FAIL.

## Setup sạch và lệnh đầy đủ

Clone đủ lịch sử Git (không shallow): regression R3/R4 dùng source Git đã pin.
Kiểm thử trên tree tích hợp LOCAL với main đã pin, không merge main remote:

```powershell
git clone https://github.com/ChouPro205/Adaptive_Split_Inference.git receiver
Set-Location receiver
git -c core.autocrlf=false checkout --detach cfdfca1025ab5f707b46197b4c5dae868d38d473
git merge --no-ff <PR25-fix-SHA> -m "Local PR25 acceptance integration"
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r ml/requirements-core.txt -r ml/requirements-week3-onnx.txt
# Torch phải đúng 2.14.0+cu130 cho bitwise Windows đã pin; dùng requirements-gpu-cu130.txt.
.venv/Scripts/python.exe -m pip install -r ml/requirements-gpu-cu130.txt
python -B ml/scripts/setup_week5_delivery_v2.py --asset-cache <thu-mục-chứa-4-ZIP-gốc>
python -B ml/scripts/run_week5_delivery_v2.py --output ml/provenance/receiver-new
```

Đặt `python` là executable venv đã pin; PATH child có GCC. Môi trường kiểm thử
Windows Python3.11.9, torch2.14.0+cu130, numpy2.4.6, CPU deterministic, một
thread, MKLDNN disabled. Wrapper chỉ bỏ PYTHONHOME/PYTHONPATH ở child.
Suite chạy P1 10000, 220 tensor thật, accuracy8544×11 và unit/regression thường/-O.
Exit2 nghĩa các gate portable đạt và allocation BLOCKED; exit1 là gate/dependency
lỗi. Suite không thay thế SV1 preflight/acceptance tổng.

Để kiểm lại bằng evidence mới đã có (không gọi tests reuse là chạy mới):

```powershell
python -B ml/scripts/verify_week5_delivery_v2.py --evidence ml/provenance/receiver-new --accuracy ml/provenance/receiver-new/accuracy --output ml/provenance/delivery-recheck-new.json
python -O -B ml/scripts/verify_week5_delivery_v2.py --evidence ml/provenance/receiver-new --accuracy ml/provenance/receiver-new/accuracy --output ml/provenance/delivery-recheck-O-new.json
python -B ml/scripts/evaluate_week5_v2.py --batch-size 1 --output ml/results/accuracy-new
```

## SV1 acceptance offline

Cần nguyên preparation.json, binary/build artifacts theo path trong receipt,
session receipts và capture đã nghiệm thu. Chạy trên tree tích hợp cả thường/-O:

```powershell
python -B device/scripts/verify_week5_package.py --preparation <preparation.json>
python -O -B device/scripts/verify_week5_package.py --preparation <preparation.json>
python -B device/scripts/accept_week5_mcu.py --session <session-dir> --preparation <preparation.json> --output <new-acceptance-dir>
python -O -B device/scripts/accept_week5_mcu.py --session <session-dir> --preparation <preparation.json> --output <new-acceptance-O-dir>
```

Không mở COM, flash, build firmware hoặc đo MCU mới. Accuracy C bên trong là
reuse nếu verifier chứng minh source/dependency/receipt hashes đúng. Checkout
Windows có thể đổi LF→CRLF ở ps1/txt. Audit expected/current/raw Git blob trước;
chỉ materialize blob cùng revision ở checkout thử nếu chứng minh newline-only
và blob đúng receipt hash. Lưu audit; không normalize hash hoặc nới gate.

Registry quyết định và verifier sau approval: [bảng F2](../../contracts/sv3_week5_registry_decisions_v2.md).
