# Hợp đồng bàn giao mô hình Tuần 3: SV3 → SV1

**Quy cách gói bàn giao: SV1 chốt, phiên bản `w3-sv1-handoff-v1`. Gói SV3 đã phát hành và verify PASS; SV1 package review/MCU validation PENDING.** Tài liệu này quy định đầu vào để SV1 chạy hai lớp `Conv1d` đầu trên nRF52840 Dongle và so với PyTorch. Gói chính thức `mitdb-week3-fp32-20260925-v1` và toàn bộ bằng chứng nằm trong [biên bản release](../ml/docs/week3_release.md). Việc phát hành gói không phải kết quả nghiệm thu trên nRF52840; MCU 20/20 **NOT YET TESTED**.

## 1. Phạm vi và nguồn ràng buộc

| Nguồn | Ràng buộc áp dụng cho bàn giao này |
|---|---|
| [`contracts/README.md`](README.md) | `contracts/` lưu giao diện và test vector dùng chung. |
| [I1 v1](i1_device_edge_packet_v1.md), mục 6–8, 11, 18–19 | I1 là giao thức Device–Edge ở trạng thái `REVIEW_CANDIDATE`. Model input không đồng nghĩa activation tại split; protocol golden vector mục 19 chỉ kiểm codec/CRC. I1 v1 bắt buộc `flags = 0`, `nonce_length = 0`, không có protected payload. |
| [I2/1 đã chốt quy cách kỹ thuật](i2_protection_v1.md) | PR #7 đã vào `main`; bản đề xuất I2 trong đó được thay bằng đặc tả này. I2/1 là phép biến đổi đảo ngược trên activation INT8 NCL, `N=1`; **payload tensor** giữ nguyên số byte, descriptor/nonce thêm overhead. Chưa có tích hợp Device–Edge hoặc tính bảo mật mật mã. FP32 vẫn là tham chiếu so sánh mô hình Tuần 3. |
| [Hợp đồng dữ liệu ML Tuần 1](../ml/docs/week1_data_contract.md), [quy trình dữ liệu](../ml/docs/week1_data_protocol.md) | Chỉ dữ liệu/tiền xử lý đã khóa: MIT-BIH hoặc PTB-XL, các manifest và thống kê chuẩn hóa có hash. Các tài liệu đó chưa khóa kiến trúc, tensor name, split hay lượng tử hóa. |

Đây là phép thử **cục bộ FP32** của hai Conv, không định nghĩa `split_id`, `model_profile_id`, packet, nonce, key hay thuật toán bảo vệ. Không được đặt output hai Conv vào `PROTECTED_PAYLOAD` của I1 v1. Nếu sau này dùng output làm activation Device–Edge, SV1/SV2/SV3 phải chốt profile I1 và một revision giao thức được duyệt riêng; mục tiêu I2 INT8 không tự sửa I1 v1.

[Ứng viên SV3 Tuần 2 đã merge trong PR #7](../ml/docs/week2_baseline.md) ban đầu chưa khóa mô hình Tuần 3. SV3 sau đó xác nhận dùng đúng checkpoint historical, các verifier PASS; SV3 và SV1 đã xác nhận riêng boundary P2 (mục 7). Giá trị Tuần 3 được kiểm từ checkpoint, graph thực thi và package thực; không suy từ báo cáo Tuần 2. Checkpoint được giao nguyên byte trong gói ngoài Git. Firmware hiện tại chưa có kernel hai Conv; [báo cáo SV1 Tuần 2](../docs/sv1_device_week2_report.md) không phải số đo firmware Tuần 3.

## 2. Quy tắc gói và định danh đã chốt

SV3 bàn giao **một thư mục đủ hiện vật để SV1 kiểm tensor và chạy hai Conv** tại `ml/artifacts/week3/<handoff_id>/` (đường dẫn từ Git root; có thể chuyển nguyên thư mục ngoài Git). Việc tái xuất input từ dữ liệu gốc cần bộ dữ liệu theo hợp đồng Tuần 1, không giả định raw data nằm trong gói. `handoff_id` do SV3 cấp, duy nhất cho một revision, chỉ gồm chữ thường ASCII, số, `_`, `-`; không đổi nội dung dưới cùng ID. `README.md` trong gói ghi nơi nhận thực tế. Đường dẫn trong **danh mục file của gói** ở `manifest.json` là tương đối bên trong gói, dùng dấu `/`, không có `..` hay đường dẫn tuyệt đối. Tham chiếu upstream riêng là đường dẫn từ Git root kèm commit/hash. Không dùng file từ gói khác để lấp chỗ thiếu.

SV3 ghi vào `manifest.json` UTF-8 JSON các trường bắt buộc sau; **schema/trường là quy cách đã chốt, giá trị đang chờ SV3**:

| Nhóm | Trường bắt buộc / ý nghĩa |
|---|---|
| Định danh | `contract_version = "w3-sv1-handoff-v1"`, `handoff_id`, `model_name`, `model_version`, `dataset_profile` (`MIT-BIH/1.0.0` hoặc `PTB-XL/1.0.3`), `precision = "fp32"`. Chỉ một dataset profile trong một gói. |
| Nguồn mô hình | `source_commit` của mã định nghĩa/train mô hình, đường dẫn và SHA-256 của `model/train_config.json`, framework/PyTorch và dependency versions, seed và trạng thái eval, tên/loại checkpoint cùng SHA-256. Commit dữ liệu Tuần 1 không tự là commit mô hình. |
| Dữ liệu | Đường dẫn, SHA-256 và phương pháp hash của dataset config, normalization và manifest tương ứng; tên split/quy tắc chọn 20 mẫu; danh sách bước từ dữ liệu gốc tới `M0`, nêu phép biến đổi bổ sung hoặc xác nhận không có. |
| Tensor | Tham chiếu `model/graph.json`, danh sách mọi file trong gói với `path`, `size_bytes`, `sha256`, `format`, `dtype`, `shape` khi là tensor; SHA-256 là 64 ký tự hex thường, `shape` là mảng số nguyên dương. `M_final` là ID mốc có thật trong graph. Manifest không tự hash chính nó. |

File nhị phân và **từng file đã giao** được kiểm SHA-256 trên byte thực (`sha256_raw_bytes`); text trong gói lưu UTF-8 LF để hash ổn định. Hash upstream của dữ liệu Tuần 1 tiếp tục dùng đúng chính sách của [quy trình dữ liệu](../ml/docs/week1_data_protocol.md) (text UTF-8 chuẩn hóa LF, binary raw bytes). SV3 không thay hash upstream bằng hash của bản copy mà không giải thích. Bất kỳ checkpoint, graph, preprocessing, mẫu hoặc tham số nào đổi đều cần `handoff_id` mới, xuất lại toàn bộ input, weight và golden, rồi SV1 nghiệm thu lại.

## 3. File SV3 phải giao

Các tên sau là **quy cách SV1 đã chốt**, không phải khẳng định file đã tồn tại. `manifest.json` liệt kê và hash mọi file thực (trừ chính nó); file theo điều kiện phải có hoặc được ghi rõ là `absent`/`folded` trong graph, không được bỏ qua im lặng.

| Đường dẫn trong gói | Nội dung bắt buộc |
|---|---|
| `README.md` | Lệnh tái tạo/kiểm tra, môi trường, cách lấy dữ liệu/checkpoint, bảng mốc, cách SV1 đọc output và đối chiếu `sample_id`; giải thích mọi ngoại lệ có duyệt. |
| `manifest.json` | Metadata, danh mục file/hash và liên kết revision như mục 2. |
| `model/checkpoint.pt` | Checkpoint PyTorch **thực đã chọn**, chỉ rõ full checkpoint hay `state_dict`, cách load an toàn, epoch/trạng thái eval và hash. Không dùng tên file này để suy ra có checkpoint. |
| `model/train_config.json` | Bản chụp cấu hình train/export của đúng checkpoint, UTF-8 JSON; ghi rõ cấu hình nào chỉ có trong source commit nếu có. |
| `model/graph.json` | Danh sách op/mốc theo thứ tự thực thi và bảng shape/layout/metadata chi tiết tại mục 4; tên module và checkpoint key thật. |
| `samples.csv` | UTF-8 CSV header + đúng 20 dòng; định danh và thứ tự theo mục 5. |
| `inputs.npy` | NumPy `.npy` version ghi trong manifest, mảng C-contiguous `<f4`, shape `(20,C,L)` theo profile đã chọn, là **M0 đã chuẩn hóa, đã cast** và sẵn sàng đưa vào Conv #1. |
| `weights/conv1.weight.npy`, `weights/conv2.weight.npy` | Mỗi file là trọng số FP32 **hiệu dụng SV1 phải chạy**, C-contiguous `<f4`; shape, trục, checkpoint key và phép fold nếu có trong graph. |
| `weights/conv1.bias.npy`, `weights/conv2.bias.npy` | Bắt buộc khi Conv hiệu dụng có bias; `<f4`, shape `(C_out,)`. Khi không có bias, graph ghi `absent`; không tạo bias giả. |
| `weights/<op_id>.<parameter>.npy` | Mỗi tham số của BN/op khác **chưa fold** mà SV1 phải chạy; `<f4`, tên op/key/shape ghi trong graph. Không xuất tham số thừa làm SV1 đoán dùng file nào. |
| `firmware/head_parameters.h` | C99 header tự đủ cho **mọi** tham số hiệu dụng của đoạn graph được chạy; quy tắc bit/layout ở mục 4. |
| `golden/<milestone_id>.npy` | Một file cho từng mốc output thực từ `M1` đến `M_final`, gồm op ở giữa/nếu có; mảng C-contiguous `<f4`, trục đầu dài 20. Nếu `M_final` trùng mốc trước, graph dùng cùng ID/file, không cần bản sao. |
| `scripts/export_week3.py`, `scripts/verify_week3.py` | Script UTF-8 và lệnh chạy trong README; export từ checkpoint + nguồn mẫu Tuần 1, verify lại hash, schema, 20 ID, giá trị hữu hạn, tham số C và golden tái tính bằng PyTorch eval trên `inputs.npy`. README ghi rõ chế độ nào cần raw data bên ngoài. |

`.npy` là định dạng trao đổi trên PC, không được nạp cả header `.npy` vào firmware như tensor raw. Header C là representation duy nhất cho tham số firmware trong gói này. SV1 quyết định stream hay lưu từng input trên dongle sau khi tính Flash/RAM; `sample_id` và giá trị logic phải giữ nguyên.

## 4. Metadata hai Conv, graph và định dạng tensor

`model/graph.json` phải ghi một `ops` array theo đúng thứ tự inference, từ `M0` tới `M_final`: mỗi op có `op_id`, loại, tên module PyTorch, input/output milestone ID, checkpoint key liên quan, tham số, shape/dtype/layout của input và output. ID mốc, `op_id` và tên tham số dùng trong tên file/C chỉ gồm `[A-Za-z][A-Za-z0-9_]*`, không trùng nhau trong cùng loại ID; checkpoint key gốc vẫn được ghi nguyên dạng. Ghi cả BN, activation, pooling, reshape/transpose, residual và op khác **nếu thực sự có**; nếu không có thì ghi rõ trong README. Hai Conv đầu được đánh số **theo thứ tự chạy** là `conv1`, `conv2`, không theo tên module suy đoán. `M1` là output ngay sau Conv hiệu dụng #1; `M2` tương tự #2. Nếu BN đã fold vào Conv, `M1`/`M2` tương ứng output **sau Conv+BN** của PyTorch; nếu BN tách rời, mốc BN sau Conv có ID/file golden riêng. `M_final` là một mốc output duy nhất do SV3 chỉ định sau các op thuộc đoạn hai Conv và Kỳ Anh/SV1 xác nhận; không tự giả định `M_final = M2`.

Với **mỗi Conv**, graph ghi `in_channels`, `out_channels`, `groups`, `kernel_size`, `stride`, `padding` (hai phía và mode), `dilation`, `bias` có/không, input/output length, tên checkpoint key gốc, shape weight gốc/hiệu dụng, thứ tự cộng bias và mọi op kề. Weight `Conv1d` hiệu dụng có trục `(C_out, C_in/groups, K)`; shape release: Conv1 `(16,1,5)`, Conv2 `(16,16,5)`, bias `(16,)` cho mỗi Conv; chi tiết trong `model/graph.json` của gói release. Nếu có BN, ghi `eps`, running mean/variance, gamma/beta hoặc non-affine, eval mode, vị trí và trạng thái fold. Khi fold, script phải tạo weight/bias hiệu dụng từ checkpoint, graph nêu công thức và golden lấy ở vị trí PyTorch tương đương; nếu BN chưa fold, xuất đủ tham số và mốc BN riêng. Với activation/pooling/op khác, ghi đúng loại, thứ tự, tham số (gồm pooling stride/padding/dilation/ceil mode nếu áp dụng) và shape trước/sau. Không điền shape hay op giả từ kiến trúc ứng viên Tuần 2.

| Tensor | Quy cách đã chốt | Giá trị SV3 phải điền trong graph/manifest |
|---|---|---|
| `M0`, mọi activation/mốc | FP32 IEEE-754, `.npy` little-endian `<f4`, C-contiguous; activation `Conv1d` dùng trục NCL, offset phần tử `((n*C+c)*L+l)`. Golden có `N=20`; MCU xử lý `N=1` và so hàng `sample_index`. Nếu op đổi trục/rank, graph ghi công thức offset và phép đổi trước khi so. | Shape bằng số tại từng mốc, dtype, số phần tử/byte, tên tensor, vị trí hook và offset firmware. `M0` chọn MIT-BIH `(20,1,360)` hoặc PTB-XL `(20,12,1000)` theo profile đã chọn. |
| `conv1/conv2` weight | `<f4`, C-contiguous theo `(out_channel, in_channel_per_group, kernel)`; offset `((oc*(C_in/groups)+ic_local)*K+k)`. Không transpose ngầm. | Shape bằng số, key gốc, hash, byte count, fold status và mapping từ checkpoint tới weight hiệu dụng. |
| Bias/BN và tham số op khác | `<f4`, một file/mảng mỗi tensor, thứ tự phần tử và shape khai báo tường minh. Bias Conv theo `out_channel`. | Có/không, tên key, shape bằng số, hash, byte count và thứ tự áp dụng. |
| `firmware/head_parameters.h` | `static const float` C99; mảng 1D theo đúng offset trên, dùng **hexadecimal float literal có hậu tố `f`** để giữ chính xác bit FP32; khai báo tên `sv3_conv1_weight`, `sv3_conv2_weight`, bias và op khác theo `op_id`, cùng hằng số shape/count. Export/verify phải round-trip từng phần tử về bit FP32 của `.npy`. | Tên mảng và kích thước thực, compiler/build đã dùng để xác minh, Flash/RAM phát sinh. |

Không suy layout trọng số/buffer C từ layout payload I1. Nếu firmware cần biểu diễn khác với bảng này, phải sửa phiên bản hợp đồng và xuất lại gói **trước** khi nghiệm thu; không có hai layout cùng được xem là chuẩn. Tuần 3 dùng FP32; `INT8` trong I1/I2 không đổi dtype hoặc ngưỡng so sánh này. Chuyển sang INT8 đòi hỏi chốt riêng scale, zero point, axis, rounding, clamp, bias/requantization, mốc và ngưỡng.

## 5. Đánh số và đối chiếu đúng 20 mẫu golden

SV3 chọn **đúng 20 mẫu thật, 20 định danh nguồn khác nhau** thuộc cùng dataset profile, công bố split, quy tắc chọn có thể tái lập, seed nếu có, thứ tự và tiêu chí loại trừ. `samples.csv` có cột chung `sample_index,sample_id,dataset_profile,split,patient_id`; `sample_index` là số thập phân 0–19 liên tiếp theo thứ tự file, `sample_id` duy nhất và bất biến trong `handoff_id`. Với MIT-BIH bổ sung `record_id,r_peak_sample,lead_name,lead_index` từ [metadata processed](../ml/src/build_mitdb_processed.py); khóa nguồn là `(record_id,r_peak_sample,lead_name)`, `sample_id` có dạng `MIT-BIH:<record_id>:<r_peak_sample>:<lead_name>`. Với PTB-XL bổ sung `ecg_id,strat_fold,waveform_path` từ [metadata PTB-XL](../ml/src/ptbxl_common.py); khóa nguồn là `ecg_id`, `sample_id` có dạng `PTB-XL:<ecg_id>`. Các dấu `<...>` là trường thay bằng giá trị nguồn thực, không phải mẫu có sẵn. Cột không áp dụng để trống, không tự tạo định danh bệnh nhân/nhãn mới. SV3 chỉ ra hàng metadata/manifest gốc tương ứng và hash của chúng.

`inputs.npy[i]` và `golden/<milestone_id>.npy[i]` **luôn** thuộc dòng `sample_index=i` của CSV. Mỗi golden có đúng 20 hàng, cùng thứ tự, shape tail/dtype được graph khai báo; không ghép bằng vị trí nếu CSV thiếu/trùng ID. Script verify kiểm đủ 20 khóa nguồn khác nhau, so input với pipeline dữ liệu đã chọn và chạy **chính những input được giao** qua checkpoint ở `eval()` để tạo lại mọi golden; dropout/BN phải ở chế độ inference. Mỗi mốc golden phải trỏ tới đúng hook/op trong graph. Giá trị mẫu, ID, shape Conv và golden thực đã có trong gói release; [biên bản](../ml/docs/week3_release.md) ghi inventory/hash và kết quả verify.

Đầu vào MIT-BIH kế thừa MLII theo tên, cửa sổ 360 điểm quanh R-peak, Z-score scalar train-only và view `(N,1,360)`; PTB-XL kế thừa đủ 12 lead đúng thứ tự, 1000 điểm/lead ở 100 Hz, Z-score từng lead train folds 1–8 và view `(N,12,1000)`. Các nguồn là [hợp đồng dữ liệu](../ml/docs/week1_data_contract.md) và [quy trình](../ml/docs/week1_data_protocol.md). Không chuẩn hóa lần hai `inputs.npy`. Nếu mô hình có bước bổ sung sau Tuần 1, SV3 khai báo chính xác bước, tham số và bên thực hiện trước `M0`; việc thay pipeline đã khóa cần được duyệt và cấp gói mới.

## 6. Tiêu chí SV1 nghiệm thu

1. **Kiểm gói trước khi chạy:** đủ file theo graph, JSON/CSV/NPY đọc được; `contract_version`, ID, checkpoint/commit, dataset config/normalization/manifest, hash/size và mỗi shape/dtype/count khớp; 20 sample index, ID và khóa nguồn hợp lệ; mọi input/weight/golden hữu hạn. Sai hoặc thiếu bất kỳ mục bắt buộc nào: **FAIL, chưa chạy MCU**.
2. **Kiểm tham số và tham chiếu:** `verify_week3.py` tái tạo input/golden từ checkpoint ở eval; từng bit FP32 trong C header khớp `.npy` hiệu dụng theo offset đã khai báo; graph có đủ mốc, kể cả BN/op giữa hai Conv; nguồn golden và firmware dùng cùng revision. Không khớp: **FAIL**.
3. **Chạy và thu output:** SV1 chạy đủ 20 `sample_id` trên firmware hai Conv, thu output đầy đủ với `handoff_id`, `sample_index`, `sample_id`, `milestone_id`, shape/dtype/count; cách dump qua console/file phải tránh cắt hoặc làm tròn làm sai so sánh. USB CDC demo hiện tại không mặc nhiên là transport I1. Giải mã buffer MCU về đúng shape logic rồi so từng phần tử cùng mẫu/mốc; ghi `max(abs(MCU - PyTorch))` từng mẫu/mốc. Thiếu phần tử, NaN/Inf, sai ID/shape hoặc không thể thu đủ: **FAIL**.
4. **Quyết định FP32:** tại `M_final`, **từng mẫu trong 20 mẫu** phải có `max(abs(MCU - PyTorch)) < 1e-3` (dấu `<` nghiêm ngặt); sai số mốc trung gian phải ghi để định vị lỗi. Chỉ công bố `20/20 PASS` khi cả 20 đạt cùng các gate trên. Không tự áp ngưỡng này cho INT8.
5. **Biên bản:** ghi bảng 20 dòng theo `sample_index/sample_id`, sai số mỗi mốc, max toàn bộ ở `M_final`, phiên bản/commit firmware, toolchain, target `nrf52840dongle/nrf52840`, Flash/RAM image và peak buffer/workspace/stack nếu đo được, cách nạp 20 input, lý do mọi FAIL. SV1 kiểm image thực vừa Flash/RAM; số Active/Idle Tuần 2 không thay phép đo này. Golden và gói SV3 đã verify PASS; firmware hai Conv và biên bản thiết bị chưa có nên **MCU 20/20 NOT YET TESTED; chưa có số đo firmware Tuần 3**.

## 7. Việc Kỳ Anh (SV3) cần xác nhận và bàn giao

**Audit local ngày 2026-09-25:** [báo cáo SV3 trước freeze](../ml/docs/week3_audit.md)
đã kiểm checkpoint historical, provenance và graph thực thi. SV3 đã xác nhận
trong phiên làm việc: **“Xác nhận freeze candidate này nếu verifier PASS”**;
các verifier Week 1/2 đã PASS. Quyết định và checkpoint cụ thể nằm trong
[`week3_model_freeze.json`](../ml/configs/week3_model_freeze.json):
`mitdb_week2_cnn_v1`, MIT-BIH/1.0.0, L=10 learned layers, epoch 3,
source `8e98a0e4851abc979feb5fd5b97ece612b02cfaa`, full checkpoint SHA-256
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Model freeze: **CONFIRMED theo xác nhận SV3 nói trên**; không suy ra GV/SV1
đã nghiệm thu thiết bị. Verifier historical PASS không thay cho nghiệm thu Tuần 3.
`M_final=P2`: **SV3 CONFIRMED; SV1 CONFIRMED; BOUNDARY CONFIRMED**.
Xác nhận SV1 được người dùng cung cấp làm thẩm quyền trong phiên ngày 2026-09-25:

> SV1 CONFIRMED: M_final = P2, là output sau features.4 (MaxPool1d),
> shape PyTorch với N=1 là (1, 16, 180).
>
> Mình chốt phạm vi port Week 3 là
> Conv1 → ReLU1 → Conv2 → ReLU2 → MaxPool1d,
> với P2 là tensor đầu ra để SV1 bàn giao cho phần tiếp theo.

Cả hai xác nhận riêng được lưu trong config. Đây là duyệt boundary, không phải
SV1 package review hoặc MCU acceptance. Gói chính thức:
`ml/artifacts/week3/mitdb-week3-fp32-20260925-v1/`, manifest raw SHA-256
`437a2a7db9f58d5d6896e8f50102c8b9b0a43b585d41c363420a1e9ca7309f2d`.
Model name/version `mitdb_week2_cnn_v1`, precision FP32, quantization
`not_applicable`; không có INT8 metadata. [Manifest versioned](../ml/provenance/week3/mitdb-week3-fp32-20260925-v1.manifest.json)
liệt kê mọi file trong gói ngoài Git.
Đã có [gói review với 20 input/golden, C header và export/verify](../ml/docs/week3_review_evidence.md),
kiểm kỹ thuật PASS; r2 vẫn giữ nguyên trạng thái lịch sử `PROPOSAL_ONLY`,
không sửa hoặc relabel. Gói chính thức dùng ID mới nêu trên; exporter/verifier
không có `--review` đã PASS, 14 negative tests PASS, reproduction PASS.
ONNX cho SV2: **BLOCKED_ON_SV2_INTERFACE**;
các quyết định còn thiếu được liệt kê trong audit. Chưa có MCU acceptance.

- [x] Chốt dataset profile và mô hình Tuần 3 thực dùng; cung cấp checkpoint, source commit, train config, môi trường, hash và bằng chứng `eval()`; xác nhận ứng viên Tuần 2 có/không được dùng. Bằng chứng: quyết định SV3, audit và gói review nêu trên; chưa đồng nghĩa phát hành gói cuối.
- [x] Xác nhận graph thực, thứ tự/hook của hai Conv, mọi BN/activation/pooling/op, fold status và `M_final`; điền **shape số thực**, checkpoint key, tham số, byte count cho từng tensor. Graph/golden tái tính từ checkpoint và input đã giao; boundary có hai xác nhận.
- [x] Xác nhận 20 nguồn mẫu, split, quy tắc chọn, metadata/manifest/hash và `inputs.npy` FP32 sau đúng pipeline; ký nhận thứ tự `sample_index` 0–19. CSV/input giữ nguyên từng byte so với r2, 20 nguồn riêng biệt, raw-derived input verify PASS.
- [x] Xuất đúng các file mục 3, golden từng mốc, C header, scripts và hash; tự chạy verify tái tạo và đối chiếu bit tham số. Gói release 29 file, GCC C99 1392 phần tử khớp bit, 5 golden milestone PASS.
- [ ] Cùng SV1 xác nhận điểm thu output, khả năng RAM/Flash của graph thực và mốc `M_final` trước phép so MCU; mọi đề nghị INT8 hoặc Device–Edge là thay đổi hợp đồng/protocol riêng.

**Chưa nghiệm thu** cho đến khi các ô trên có giá trị, gói được kiểm và SV1 có biên bản 20 mẫu. Khi gói đổi, SV3 phát hành ID mới; không sửa âm thầm gói đã dùng làm bằng chứng.

Mục cuối vẫn chưa hoàn tất: boundary đã xác nhận nhưng khả năng Flash/RAM của
firmware thực và phép so MCU chưa được đo. Các số 5568 B tham số, 23040 B tensor
lớn nhất và 46080 B hai buffer chỉ là ước tính logic. SV1 package review PENDING;
SV1 MCU validation PENDING; MCU 20/20 NOT YET TESTED.
