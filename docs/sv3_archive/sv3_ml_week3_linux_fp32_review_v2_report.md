# SV3 Linux FP32 — review v2: bảo toàn provenance và recipe

## Kết quả và source được kiểm chứng

Branch `sv3/fix-week3-sv2-linux-fp32`, nền
`415d53431c81c465784dc08be42b568827a39cff`, working tree chưa commit.
Lần này chỉ sửa Git attributes, recipe/setup/authentication logging và
công cụ tạo receipt/kiểm chứng/đóng gói. Không sửa logic verifier portable,
tests số học, common backend hoặc artifact khoa học. Không commit/push,
merge hoặc release. Git indexes/trees dùng để kiểm chứng thuộc repository
tạm, không thay index repository làm việc.

Receipt cũ vẫn xác nhận source cũ. SHA script cũ:
`d988e9f16c9617e07c9a621eceaf01d177c825010881a0ebce2b2cb499a428f0`.
Snapshot script nguyên bytes được giữ ở
`ml/provenance/week3-sv2-linux/review-v2/source-before/ml/scripts/reproduce_week3_sv2_linux.sh`.
SHA script mới nằm trong `recipe_success/receipt.json` và source inventory
v2; không thay hash trong `review_receipt.json` cũ.

## CRLF: bằng chứng trước/sau

[before.json](../ml/provenance/week3-sv2-linux/review-v2/before.json)
ghi SHA/size của 125 file lịch sử: 61 file có CRLF, cùng snapshot attrs cũ,
script cũ, artifact v1 và ZIP review cũ.
Ngoại lệ duy nhất thêm **cuối** `.gitattributes`:

```gitattributes
ml/provenance/week3-sv2-linux/** -text
```

`git check-attr` trả `text: unset` trong phạm vi này, kể cả evidence v2;
`eol: lf` kế thừa vẫn hiển thị nhưng không chuẩn hóa khi text đã unset.
Provenance `week4-r4` và source ngoài phạm vi vẫn theo quy tắc cũ.
Không chuyển log lịch sử sang LF và không sửa hash lịch sử.

| Đường kiểm chứng ví dụ `final_linux_verifier.command.json` | SHA-256 |
|---|---|
| Raw lịch sử, index và checkout sau sửa, patch sau sửa | `2784a0df309e37134e80e3b8ac0a80be4f5afae930492ee0674f52ad4fe7f567` |
| Index/checkout trước sửa | `b0304f1c89de0dac68fe8a531e68033600f614c680e19e9429d041ec3639caaa` |

[transfer_before.json](../ml/provenance/week3-sv2-linux/review-v2/transfer_before.json)
tái hiện thật 61 file đổi bytes khi add/checkout với attrs cũ, không chỉ
tính hash từ `replace(CRLF, LF)`.
[transfer_after.json](../ml/provenance/week3-sv2-linux/review-v2/transfer_after.json)
ghi lệnh, cwd, stdout/stderr/exit, index tree và kết quả sau attrs mới:

- Git: clone riêng tại base, copy fix/source/evidence, add vào index tạm
  với `core.autocrlf=true`, checkout sạch bằng `checkout-index` từ index đó;
  so từng file về bytes/SHA/size và kiểm receipt/streams/source.
- Patch: tạo `git diff --cached --binary --full-index --no-textconv` tại
  index tạm đã áp dụng attrs mới; clone sạch khác tại base; **thực hiện**
  `git apply --binary`, rồi so bytes và kiểm receipt. Không dừng ở `--check`.
- Probe đầu sau sửa: 639 file đều giữ nguyên bytes trên cả hai đường;
  125 historical files, 76 streams, 13 source hashes receipt cũ và 12 source
  hashes receipt recipe mới được xác minh. Patch đóng gói cuối được tạo
  lại sau khi thêm báo cáo/evidence, rồi kiểm chứng lại độc lập; số file và
  hash patch cuối ở `_review/transfer_validation.json` trong ZIP và
  `SV3_LINUX_FP32_REVIEW_v2.validation.json` bên ngoài.

Hợp đồng byte-transfer bao gồm mọi file thuộc fix, toàn bộ provenance và
source/requirements được receipts tham chiếu. Hai context files R4 không
sửa (`week4_requirement_references.json`, `mitdb_patient_split.csv`) có
CRLF cục bộ nhưng theo quy tắc LF hiện hữu và không được receipt SV2 pin
raw source bytes; không mở rộng ngoại lệ sang chúng. Bytes context được
giữ nguyên trong ZIP để tham khảo, không thuộc patch fix. Package v1 vốn
chuyển ngoài Git được kiểm raw bytes riêng, không add vào Git.

## Recipe mới

`reproduce_week3_sv2_linux.sh` tạo log directory mới và thiết lập logger/
exit handler trước khi tìm repo, download, tạo venv, pip install và auth.
Mỗi bước ghi command shell-escaped, argv NUL-delimited, cwd, timestamps,
stdout, stderr và exit code. Không ghi đè thư mục run cũ. Khi thất bại,
ghi `recipe.exit_code.txt` + `summary.txt`, exit khác 0 và không báo PASS
cuối hoặc tạo success receipt.

- Python của venv thực tế được log, gồm version, executable, resolved
  executable, prefix/platform. Venv có sẵn khác native Linux Python
  3.11.9 bị từ chối trước dependency install.
- Download/installer/hash/version uv, Python install, venv creation,
  torch/ONNX/NumPy install và freeze đều đi qua logger.
- SHA của chính `.sh`, hai helper mới, mọi module trực tiếp dùng bởi gates/
  overwrite guard và requirements ONNX thực sự đọc bởi setup được log.
  Pins torch/NumPy trong argv được ràng buộc bởi script SHA.
- `authenticate_week3_sv2_package.py` tách bước auth chuẩn thư viện ra để
  có command/streams riêng: giữ anchor và hash/size/ZIP gốc như recipe cũ.
  Full verifier vẫn thực hiện integrity và numerical assertions như trước.
- `record_week3_sv2_recipe.py` tạo **receipt mới**, xác minh source không
  đổi trong run, các bước exit 0, auth trước/sau giống nhau. Receipt chỉ
  bao phủ các bước đã hoàn tất trước khi tạo receipt; command tạo receipt
  và exit handler có log riêng để tránh self-hash vòng tròn.

## Kiểm thử Ubuntu/WSL2

Recipe chạy end-to-end với venv native Linux mới:
`/home/kyanh/asi-week3-review-v2-clean-env/venv`, Python 3.11.9.
Giữ pins torch 2.14.0+cu130, numpy 2.4.6, ONNX 1.23.1, ORT 1.30.0,
protobuf 7.36.2, ml_dtypes 0.6.0, flatbuffers 25.12.19. CPU backend giữ
eval/N=1/one-thread/deterministic/MKLDNN disabled và ORT CPU/basic.

[Recipe receipt mới](../ml/provenance/week3-sv2-linux/review-v2/recipe_success/receipt.json)
ghi 27 bước đã hoàn tất trước tạo receipt, 12 source/requirements hashes
và runtime Python thực tế. Command/stdout/stderr outer run ở
`review-v2/recipe_success.command.json` và các files cùng prefix.

| Gate | Trạng thái | Evidence |
|---|---|---|
| Fresh setup/download/install/auth | PASS, exit 0 | recipe_success/* |
| Diagnostic s0..10 + original logits/ORT | PASS, exit 0 | diagnostic.stdout.txt |
| Portable verifier | PASS 200 comparisons | verifier.stdout.txt |
| Tamper suite | PASS 19 expected rejections | tamper.stdout.txt |
| Cache/inventory | PASS 16/16, không SKIP symlink Linux | cache.stderr.txt |
| Numerical policy | PASS 8/8 | policy.stderr.txt |
| Venv fixture Python 3.12.3 | PASS expected rejection: recipe exit 2 | recipe_wrong_python/* |
| Fixture manifest sai | PASS expected rejection: recipe exit 1 | recipe_bad_manifest/* |
| Git checkout + patch thật | PASS raw bytes/receipts/source hashes | transfer_after.json + final ZIP validation |
| Artifact v1 và ZIP review cũ | PASS SHA/size giữ nguyên | before.json + preservation_v2.json |
| Windows full SV2 rerun | SKIP: không đổi verifier/test logic; native Windows được kiểm ở revision trước | historical logs nguyên bản |
| SV1 Linux / R4 rerun | SKIP trong revision này; giữ trạng thái FAIL/SKIP/PENDING riêng đã báo cáo | báo cáo và logs revision trước |

[failure_fixtures.json](../ml/provenance/week3-sv2-linux/review-v2/failure_fixtures.json)
chứng minh cả hai lỗi được ghi command/cwd/streams/exit, không tạo receipt
PASS và không bắt đầu diagnostic. Manifest sai nằm trong clone fixture
riêng dưới exports; không sửa manifest v1 thật. Fixture Python dùng symlink
đến `/usr/bin/python3` trong môi trường fixture Linux riêng.

## Bảo toàn phạm vi và đóng gói

Verifier/common/tests khoa học giữ nguyên SHA của revision trước. Không đổi
bitwise-v1 mặc định, s9 portable strict `<1e-5`, logits/ONNX strict `<1e-3`,
identity, integrity hoặc numerical evidence. Checkpoint/model/weights,
preprocessing, sample IDs/order, splits, golden, ONNX và manifest v1 không
đổi bytes. Không sửa source-hash gate hoặc anchor R4; không tuyên bố toàn
bộ tuần 3/4 PASS Linux hoặc nghiệm thu SV2.

File sửa/thêm chính trong revision này:

- `.gitattributes`: ngoại lệ raw evidence giới hạn đúng thư mục provenance.
- `ml/scripts/reproduce_week3_sv2_linux.sh`: logger sớm, runtime guard,
  source hashes, auth trước/sau và receipt mới.
- `ml/scripts/authenticate_week3_sv2_package.py`,
  `ml/scripts/record_week3_sv2_recipe.py`: auth được log và receipt mới.
- Báo cáo v2, link mục lục docs; `review-v2/` chứa snapshots, tools,
  các runs mới, fixture validation và transfer/preservation evidence.

`SV3_LINUX_FP32_REVIEW.zip` và validation cũ giữ nguyên. Gói v2 chứa source
hiện tại, requirements, patch đầy đủ so với base, package v1 nguyên bản,
toàn bộ provenance cũ và mới, script snapshot cũ và báo cáo hai revisions.
Không đưa dataset, venv, `.git` hoặc ZIP v1 trùng dữ liệu vào ZIP.
CRC, inventory, raw hashes, receipts/streams/source hashes và Git/patch
byte equality được kiểm khi đóng gói; index repository gốc được kiểm
không đổi. ZIP v2 hash/size nằm ở validation sidecar và thông báo bàn giao.

Recipe chạy lại trong source checkout đã nhận:

```bash
ASI_LINUX_LOG_ROOT="$HOME/asi-sv2-review-v2-logs-$(date -u +%Y%m%dT%H%M%S)" \
bash ml/scripts/reproduce_week3_sv2_linux.sh
```

PASS trên WSL vẫn là kiểm chứng máy tác giả; SV2 phải chạy lại trên máy nhận
và ghi rõ policy để xác nhận nghiệm thu.
