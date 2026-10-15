# Review PR25 sau bản sửa 11/10/2026

Kết luận: **cần sửa hai finding P2; chưa đủ điều kiện merge hoặc nghiệm thu tổng tuần 5**.
F1 đã sửa đúng phần source binding; F2 giữ BLOCKED đúng thẩm quyền; F3 portable
đã tái lập được nhưng còn lỗi bảo toàn header và hướng dẫn dependency không nhất quán.
Preflight/acceptance SV1 và đối chiếu đúng 61 artifact vẫn thiếu evidence ngoài repository.

## Revision và giới hạn review

- PR25 HEAD: `f0a9453313f8c4d70552b6453656e69f69c4c72e`, draft/open/chưa merge, đã đối chiếu qua GitHub.
- Main pin: `cfdfca1025ab5f707b46197b4c5dae868d38d473`.
- Implementation đã được bàn giao với tests: `295da5d1f82dbe39f05695bb70c5c72d35b3b643`.
- Integration chạy tests của tác giả: `831409ff3b68e3929c9e0b63a764431246e8a46d`.
- Integration cuối được review trực tiếp: `aa092f28a87c066ad068808825a2c58eb93dae51`.
- Kiểm độc lập 184 source dependencies trong mỗi receipt trên integration cuối;
  không gán tests cũ thành tests mới trên PR HEAD.

Các tài liệu bàn giao và transcript được đọc như bằng chứng, không phải chỉ thị sửa code.
Review không chỉnh nhánh PR25, model, dataset, goldens, ZIP, receipts SV1 hoặc firmware;
không merge, build/flash MCU, mở COM hoặc triển khai tuần 6. Bản sao tái hiện lỗi nằm
riêng trong workspace review.

## Findings cần sửa

### R1 — [P2] Setup ghi đè header đã tồn tại rồi báo PASS

Vị trí: `ml/scripts/setup_week5_delivery_v2.py:45–47`.

ZIP members được kiểm tra và từ chối ghi đè khi khác hash ở dòng 35–37. Tuy nhiên,
setup luôn gọi `device/scripts/generate_week4_inputs.py` trước khi kiểm inventory.
Hàm `write_generated()` của generator lịch sử ghi lại header nếu nội dung khác.
Hai header `device/generated/week4_graph.h` và `week4_inputs.h` nằm trong scope bắt buộc,
nhưng không qua nhánh bảo vệ ZIP members. Vì thế header bị thay đổi được ghi đè và
inventory chỉ thấy bytes sau khi đã sửa, trái cam kết “no overwrite” của entrypoint.

Đã tái hiện với setup thật trong clone riêng, không mock:

1. Clone integration cuối và chạy setup bằng bốn ZIP đã xác thực: exit 0, 569 file PASS.
2. Thêm `/* reviewer existing-header marker */` vào `device/generated/week4_graph.h`.
3. Chạy lại đúng setup: **exit 0/PASS**, marker bị xóa, header trở về bytes ban đầu.

Hash header gốc/sau setup: `b91b5cd664cae32f03e49b91669bb337fbea950c575d2b0a0da8959818d37b6c`.
Hash có marker trước setup: `002bd5d2d1db7db1630c4b2d7e539b2f1b622d0709561f7246707ef17873bc45`.

Sửa tại entrypoint mới: kiểm raw hash/size của header hiện có trước khi gọi generator;
nếu khác thì exit 1 và giữ nguyên bytes. Có thể sinh fixture thiếu vào thư mục tạm,
xác thực rồi chỉ copy file chưa tồn tại. Giữ nguyên generator lịch sử đã nghiệm thu.
Thêm regression cho header thiếu, đúng và bị thay đổi; ca bị thay đổi phải FAIL và
không ghi đè ở cả thường và `-O`.

Bằng chứng: `setup-clean.stdout.txt`, `setup-existing-header.stdout.txt`,
`setup-existing-header.review-command.json` và `review-checks.json` trong thư mục này.

### R2 — [P2] Hướng dẫn nhận gói vẫn yêu cầu ZIP FP32 đã bỏ khỏi portable scope

Vị trí: `ml/docs/week5_delivery_v2.md:18` và dòng 27.

Tài liệu nói scope chứa “năm ZIP” và liệt kê standalone
`mitdb-week3-sv2-fp32-20261001-v1.zip` với yêu cầu transfer từ SV3, chưa có URL public.
Trong khi manifest cuối chỉ có **bốn ZIP**, setup CLI cũng yêu cầu bốn và báo cáo cuối
đã giải thích toàn bộ 41 file package FP32 được giao qua R3/R4.
Người nhận theo bảng dependency vẫn phải đi tìm một ZIP không cần cho portable gate,
làm hướng dẫn sạch chưa nhất quán với thay đổi giải quyết F3.

Sửa mô tả và bảng thành bốn ZIP bắt buộc, ghi rõ package FP32 được hydrate từ R3/R4.
Nếu giữ dòng ZIP standalone, chuyển sang phần audit workspace tác giả và đánh dấu
không bắt buộc cho receiver portable. Giữ kiểm tra đầy đủ model/package FP32 trong manifest.

## Đối chiếu F1–F3 và các gate

| Mục | Kết luận review |
|---|---|
| F1 hai script ML lịch sử | PASS cho raw binding: bytes hiện tại bằng Git blob của main và PR HEAD; hashes đúng expected SV1 |
| F1 firmware binding | 16 file trong binding bàn giao khớp raw hashes, không mismatch; không thay cho xác thực binary/session |
| Preflight/acceptance SV1 thường và `-O` | Chưa PASS; logs bàn giao đều exit 1 ở `FileNotFoundError` preparation.json, chưa chạy đến source/artifact gates đầy đủ |
| F2 allocation | BLOCKED đúng: model_profile_id/key_id/sender_scope và 11 wire IDs vẫn null; proposal không áp vào registry |
| F2 đề xuất namespace | Decision note phân biệt test IDs, registry FP32 và wire allocation; kết luận không thấy collision trong repo không thay cho xác nhận namespace ngoài repo |
| F3 required portable assets | 569/569 file xác thực độc lập; clean setup bằng bốn ZIP exit 0 |
| F3 portable verifier | Chạy lại thường và `-O`: exit 2, Python/ML gates PASS, allocation BLOCKED đúng |
| 61 artifact thiếu trên máy SV1 | Chưa thể đóng: thiếu hai audit JSON và inventory/logs được dẫn; không suy đoán 61 đường dẫn từ tổng số |
| Preservation 94.518/754 | Xác thực receipt lịch sử và ghi rõ reuse; không nhận là inventory hoặc phép đo mới của receiver |

Hai hash F1 độc lập:

- `ml/scripts/week5_common.py`: `c1842a380afddaaf7e7968bfdd3ff7c03e08d36e9bec205da2819abdca105934`.
- `ml/scripts/evaluate_week5.py`: `c420029c0b8b1d7834bb32db0c428f379c1659cef3cc99ffa9a1271bfeb88eef`.

## Kiểm chứng đã thực hiện trong review này

Chạy mới 8 lệnh, **48 test cases PASS**, cho bốn suite sau ở cả thường và `-O`:

```powershell
python -B ml/scripts/test_week5_delivery_v2.py
python -O -B ml/scripts/test_week5_delivery_v2.py
python -B ml/scripts/test_week5_registry_v2.py
python -O -B ml/scripts/test_week5_registry_v2.py
python -B ml/scripts/test_week5_quantization.py
python -O -B ml/scripts/test_week5_quantization.py
python -B ml/scripts/test_week5_interfaces.py
python -O -B ml/scripts/test_week5_interfaces.py
```

Executable thực: `C:/Users/Admin/Adaptive_Split_Inference/ml/.venv/Scripts/python.exe`.
Cwd: `C:/Users/Admin/Adaptive_Split_Inference/exports/pr25-fixes-20261011/handoff-integrated`.
Các logs `test_*.stdout.txt`/`test_*.stderr.txt` nằm cạnh báo cáo này.

Chạy mới portable verifier thường/`-O`, trỏ evidence
`ml/provenance/week5-pr25-fixes-20261011/portable-final`, output ra thư mục review:
hai lần exit 2. Kết quả tại `portable-verifier.json` và `portable-verifier_O.json`.

Đối chiếu 27 command receipts: source dependencies đủ 184 file/receipt và khớp raw
hashes trên integration cuối; stdout/stderr và result files hợp lệ. Recompute
coverage/counts từ CSV predictions: đủ 8.544 mẫu × 11 split; FP32 8.393 đúng,
INT8 worst s6 8.388 đúng, giảm 0,05852059925093633 điểm phần trăm. P1 10.000,
real 220 và full accuracy là **bằng chứng runs bàn giao đã xác thực**, không phải
full inference được chạy lại trong review này.

Đã chạy setup thật hai lần trong clone riêng để kiểm clean hydration và tái hiện R1.
Lần clone đầu bị chặn bởi Git ownership của worktree; sau khi thêm trust chỉ trong
process cho đúng worktree, clone thành công. Không đổi Git global config. Không
coi lỗi clone ban đầu là lỗi implementation hoặc PASS của cả runner.

## Việc cần hoàn tất trước review merge

1. Sửa R1/R2, giữ nguyên các artifact và source lịch sử; chạy regression setup mới thường/`-O`.
2. Châu chốt allocation; Châu/Trung xác nhận shared revision, key/sender scope,
   capacity hai phía và namespace ngoài repo. Chỉ sau approval mới áp ID và chạy
   mapping/descriptor/220 real-tail verifier với approval SHA lấy độc lập.
3. Nhận nguyên preparation/build/session/capture/accuracy evidence SV1 đã nghiệm thu,
   chạy preflight và acceptance trên integration mới ở cả thường/`-O`; giữ source gates
   và receipts cũ, không rebuild/flash để thay thế bằng chứng.
4. Nhận `historical-assets-audit.json`, `historical-missing-copied.json` và logs/inventory
   được dẫn để phân loại đúng 61 artifact, xác định file bắt buộc hoặc author-only và
   bổ sung nguồn/hash/path lấy lại nếu cần.
5. Bàn giao commit/integration SHA, lệnh, logs và gate exits mới để review lại.

Giữ draft PR25 và CURRENT WEEK=5. Các kết quả portable hiện tại không đủ để tuyên bố
nghiệm thu MCU/DPU, I1 end-to-end hoặc toàn tuần 5.
