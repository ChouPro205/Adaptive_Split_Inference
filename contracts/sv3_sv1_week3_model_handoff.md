# Bàn giao mô hình và 20 mẫu kiểm thử SV3 → SV1, Tuần 3

Trạng thái: **DRAFT – chờ SV3 cung cấp hiện vật và SV1/SV3 chốt các điểm mở**. Tài liệu này là yêu cầu bàn giao để chạy và xác minh hai lớp convolution đầu trên nRF52840 Dongle; các ô chưa có không phải kết quả đã nghiệm thu.

## Quan hệ với các hợp đồng hiện có

| Tài liệu | Quy định được kế thừa | Phần tài liệu này bổ sung |
|---|---|---|
| [`contracts/README.md`](README.md) | `contracts/` quản lý giao diện và test vector dùng chung. | Một hồ sơ bàn giao riêng cho SV3 → SV1 trong Tuần 3. |
| [`contracts/i1_device_edge_packet_v1.md`](i1_device_edge_packet_v1.md), mục 6–8, 11, 16–18 | I1 v1 là packet Device–Edge ở trạng thái `REVIEW_CANDIDATE`: số đa byte little-endian, `FLOAT32`/`INT8` là enum wire, payload tensor C-contiguous/row-major theo layout khai báo; input MIT-BIH/PTB-XL khác activation tại split. `model_profile_id`, `split_id`, activation profile, quantization và protection triển khai còn mở. | Bàn giao tensor và tham số để kiểm thử **cục bộ** hai Conv trên MCU; không gán `split_id`, không thay đổi wire I1, không dùng protocol golden vector ở mục 19 làm golden ML. Nếu sau này truyền output sang SV2, profile và packet phải được chốt theo I1. |
| [`ml/docs/week1_data_contract.md`](../ml/docs/week1_data_contract.md), [`ml/docs/week1_data_protocol.md`](../ml/docs/week1_data_protocol.md) | Hợp đồng dữ liệu trước model: nguồn, sampling, segmentation, chuẩn hóa, nhãn và model input view của từng bộ dữ liệu. | Khóa đúng dataset/profile dùng cho 20 input, chỉ rõ trạng thái tiền xử lý của chúng, rồi gắn với checkpoint và golden output Tuần 3. |

Chưa có hợp đồng riêng trong `contracts/` cho layout trọng số C/firmware, tên tensor mô hình, cơ chế protection hoặc quy tắc đặt tên hiện vật bàn giao. [`docs/README.md`](../docs/README.md) chỉ quy định tên **báo cáo** tiến độ, không quy định tên model artifact. Vì vậy các đường dẫn hiện vật bên dưới là **vị trí dự kiến**, chưa phải quy ước đã duyệt; SV3 và SV1 phải chốt trước khi xuất file dùng cho firmware.

## Ranh giới thông tin đã xác nhận

- [`ml/README.md`](../ml/README.md) và [`ml/docs/week1_verification.md`](../ml/docs/week1_verification.md) mới xác minh pipeline dữ liệu Tuần 1; repository hiện chưa có checkpoint, graph 1D-CNN, script export hoặc golden activation của hai Conv. **20 lần đo** trong [`device/src/main.c`](../device/src/main.c) là benchmark vòng lặp rỗng, không phải 20 mẫu ML.
- [`device/CMakeLists.txt`](../device/CMakeLists.txt) hiện chọn `main.c` hoặc `main_idle.c` và `markers.c`; chưa có inference kernel. Target đã xác nhận là `nrf52840dongle/nrf52840` trong [`device/README.md`](../device/README.md). [`docs/sv1_device_week2_report.md`](../docs/sv1_device_week2_report.md) ghi số Flash/RAM của bản Active/Idle cũ; phải đo lại trên **firmware có hai Conv và bộ mẫu thực**.
- Các shape input ở mục I1 16–17 là **model input**, không xác định shape của Conv hoặc split activation. `NCL`/row-major của I1 là quy tắc payload I1; không tự suy ra layout mảng C hoặc layout trọng số từ đó.

## 1. Định danh phiên bản mô hình

SV3 điền các giá trị thực và SHA-256 trước khi SV1 triển khai; cùng một mã bàn giao phải trỏ đến một bộ checkpoint, graph, preprocessing, 20 mẫu và golden không đổi.

| Mục bắt buộc | Giá trị hiện tại / yêu cầu bàn giao |
|---|---|
| Dataset/profile được chọn cho Tuần 3 | `CẦN NHÓM CHỐT` – MIT-BIH v1.0.0 hay PTB-XL v1.0.3; không ghép hai input profile thành một tensor. |
| `handoff_id`, `model_name`, `model_version`; liên hệ với `model_profile_id` I1 nếu áp dụng | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; `model_profile_id` triển khai I1 còn `CẦN NHÓM CHỐT`. |
| Checkpoint: đường dẫn tương đối từ Git root, loại checkpoint, SHA-256, trạng thái train/eval | `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |
| Commit nguồn **của mã định nghĩa/train model**, cấu hình train và dependency/PyTorch version | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; commit xác minh dữ liệu Tuần 1 không tự động là commit của model. |
| Script xuất input, tham số và golden; lệnh chạy, commit và SHA-256 | `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |
| Kiến trúc đã chốt: tên module/layer thật, graph thực thi, hai Conv đầu, mọi op nằm giữa/sau đến mốc so sánh cuối | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; trạng thái duyệt kiến trúc `CẦN NHÓM CHỐT`. |
| Trạng thái BatchNorm: đã fold vào Conv nào, công thức/hệ số fold, hay giữ riêng | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; SV1 và SV3 xác nhận representation dùng chung. |

## 2. Bộ 20 input cố định và tiền xử lý

SV3 chọn **đúng 20 mẫu thật từ 20 định danh nguồn khác nhau**, gán `sample_id` duy nhất, ổn định trong một `handoff_id`, và công bố quy tắc chọn tái lập được: dataset/version, split, danh sách định danh nguồn, thứ tự lấy, seed nếu dùng ngẫu nhiên, tiêu chí loại trừ và lý do chọn. Nguồn/quy tắc/20 `sample_id` hiện là `CHƯA CÓ – SV3 CẦN CUNG CẤP`. Không thay mẫu sau khi tính golden mà vẫn giữ cùng `handoff_id`.

| Profile nếu được chọn | Các bước/giá trị **đã chốt** cần kế thừa | View trước model |
|---|---|---|
| MIT-BIH | Theo [hợp đồng dữ liệu](../ml/docs/week1_data_contract.md), [protocol](../ml/docs/week1_data_protocol.md) và [config](../ml/configs/mitdb_week1_config.json): WFDB physical mV, 360 Hz, chọn lead `MLII` **theo tên**, cửa sổ 360 điểm quanh annotation (180 trước, 180 sau), bỏ cửa sổ thiếu ở biên, không pad/không thêm filter; Z-score scalar fit train với mean/std trong [`ml/configs/mitdb_normalization.json`](../ml/configs/mitdb_normalization.json), sau đó cast `float32`. Stored `X` là `(N,360)`. | `(N,1,360)`; một mẫu có `N=1`. |
| PTB-XL | Theo [hợp đồng dữ liệu](../ml/docs/week1_data_contract.md), [protocol](../ml/docs/week1_data_protocol.md) và [config](../ml/configs/ptbxl_week1_config.json): record `filename_lr` 10 giây, 100 Hz, 1000 điểm/lead, đủ 12 lead theo thứ tự `I, II, III, AVR, AVL, AVF, V1, V2, V3, V4, V5, V6`; WFDB `(L=1000,C=12)` mV, không beat segmentation/giảm lead; Z-score riêng từng lead bằng thống kê train folds 1–8 trong [`ml/configs/ptbxl_normalization.json`](../ml/configs/ptbxl_normalization.json), cast `float32`, chuyển sang view model. | `(N,12,1000)`; một mẫu có `N=1`. |

`samples.csv` dự kiến có 20 dòng theo thứ tự cố định, ít nhất có `sample_id`, dataset/version và split, cùng định danh nguồn **đúng theo metadata hiện có**: MIT-BIH dùng `patient_id`, `record_id`, `r_peak_sample`, `lead_name`, `lead_index` từ [`build_mitdb_processed.py`](../ml/src/build_mitdb_processed.py); PTB-XL dùng `ecg_id`, `patient_id`, `strat_fold`, `waveform_path` từ [`ptbxl_common.py`](../ml/src/ptbxl_common.py). SV3 ghi rõ cách nối với metadata gốc, config hash, normalization hash và manifest hash theo [hợp đồng dữ liệu](../ml/docs/week1_data_contract.md). Dòng thứ *i* của CSV ứng với phần tử thứ *i* ở trục batch của **mọi** file input/golden `.npy`; không nối dữ liệu bằng vị trí nếu thiếu hoặc trùng `sample_id`.

SV3 phải xác nhận riêng: 20 input xuất ra đã đi đến bước nào (mV raw, đã cắt/đổi trục, đã Z-score, đã cast, hay đã lượng tử hóa), dtype thực, shape thực, channel order và thứ tự phần tử trong `.npy`. Trạng thái này hiện là `CHƯA CÓ – SV3 CẦN CUNG CẤP`. Liệt kê theo thứ tự mọi bước từ nguồn đến Conv #1, gồm phép biến đổi bổ sung sau profile Tuần 1 nếu có, với tham số/dtype của từng bước; nếu không có bước bổ sung thì xác nhận rõ. Mọi bước còn lại phải được nêu rõ cùng bên thực hiện; không chuẩn hóa lại input đã chuẩn hóa. Nếu chọn FP32 và xuất sau chuẩn hóa, input phải khớp `float32` và view của dataset đã chọn. Layout và ánh xạ chỉ số cho buffer C là `CẦN NHÓM CHỐT`; định nghĩa đó phải đi kèm script export/kiểm tra, không suy từ WFDB time-major hay payload I1.

## 3. Graph và các mốc so sánh

SV3 cung cấp graph ở chế độ inference/eval theo **đúng thứ tự thực thi**, tên module PyTorch và tên mốc duy nhất. Điền mỗi op thật trên đường từ input đến đầu ra sau Conv #2, kể cả BatchNorm, activation, pooling, reshape/transpose, residual, bias add hoặc op khác nếu có; ghi rõ op nào **không có**. Không giả định hai Conv kề nhau hay mặc nhiên đặt ReLU/pooling. Mốc cuối là tensor thực sau tất cả phép toán mà nhóm xác định thuộc “hai lớp convolution đầu”, và phải được SV1/SV3 cùng xác nhận trước khi so sánh.

| Mốc/nhóm mốc phải điền | Mô tả bắt buộc | Hiện trạng |
|---|---|---|
| `M0` – input của Conv #1 | Tên tensor, preprocessing đã hoàn tất, shape/dtype/layout. | Dataset/view có hai lựa chọn ở mục 2; lựa chọn thật `CẦN NHÓM CHỐT`. |
| `M1` – sau Conv #1 | Tên Conv; output ngay sau phép tích chập và bias, hoặc output Conv+BN nếu firmware dùng tham số đã fold. Phân biệt rõ hai ý nghĩa này. | `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |
| Các mốc giữa Conv #1 và Conv #2 | Một mốc cho **từng** BN/activation/pooling/op thật, theo thứ tự; giữ mốc trước và sau op khi cần định vị lỗi. | `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |
| `M2` – sau Conv #2 | Tên Conv; cùng quy tắc trước/sau BN như `M1`. | `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |
| Các mốc sau Conv #2 và `M_final` | Mọi op được tính vào đầu ra hai lớp; đánh dấu một `M_final` duy nhất cho tiêu chí nghiệm thu. Nếu không có op sau Conv #2, `M_final = M2`. | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; phạm vi cuối `CẦN NHÓM CHỐT`. |

Với **mỗi Conv**, SV3 ghi tên tham số/checkpoint key, weight và bias (hoặc xác nhận không có bias), kernel size, stride, padding (kể cả mode/asymmetric nếu có), dilation, groups, số channel vào/ra, phép cộng bias và thứ tự với các op kề. Với **mỗi BatchNorm**, ghi vị trí, `eps`, running mean/variance, affine gamma/beta hoặc xác nhận không affine, chế độ eval và trạng thái fold. Nếu fold, bàn giao cả tham số Conv hiệu dụng cho firmware và cách tạo chúng; golden ở mốc fold phải lấy sau Conv+BN tương ứng trong PyTorch. Với **mỗi activation/pooling**, ghi loại, tham số (pool kernel/stride/padding/dilation/ceil mode nếu áp dụng) và vị trí. Mọi op còn lại cần khai báo đầy đủ tham số, phép đổi shape và thứ tự. Giá trị cụ thể của toàn bộ graph/params: `CHƯA CÓ – SV3 CẦN CUNG CẤP`.

### Bảng shape/layout bắt buộc trong bản bàn giao đã điền

Trong bảng dưới, SV3 điền **shape thực bằng số** theo PyTorch (kể cả batch) và SV1/SV3 cùng chốt shape, thứ tự trục, công thức ánh xạ chỉ số sang offset tuyến tính, dtype, số phần tử/số byte của buffer C. Chép thêm dòng cho **mỗi** op thực và mọi tham số của op đó; các dòng `M1.x`/`M2.x` chỉ là vị trí trống, không khẳng định graph có op đó. Đối chiếu tensor theo shape logic sau khi áp dụng đúng phép đổi layout đã ghi.

| Tensor/mốc | PyTorch shape; layout/thứ tự trục; dtype | C/firmware shape; layout/offset; dtype | Trạng thái |
|---|---|---|---|
| `M0` input, từng mẫu | MIT-BIH `(1,1,360)` hoặc PTB-XL `(1,12,1000)`; view `N,C,L`, `float32` nếu dùng profile đầu vào Tuần 1. | `CẦN NHÓM CHỐT` – buffer C và offset; nếu INT8 phải định nghĩa representation mới. | Chọn dataset và precision còn mở. |
| Conv #1 weight | `CHƯA CÓ – SV3 CẦN CUNG CẤP` – shape PyTorch **thực** và thứ tự trục. | `CẦN NHÓM CHỐT` – shape, thứ tự trục, offset và packing. | Chưa có model. |
| Conv #1 bias / tham số BN nếu có | `CHƯA CÓ – SV3 CẦN CUNG CẤP` – từng tensor và shape. | `CẦN NHÓM CHỐT`; nếu BN fold, ghi tensor hiệu dụng. | Chưa có model. |
| `M1` Conv #1 output | `CHƯA CÓ – SV3 CẦN CUNG CẤP` – shape, layout, dtype và vị trí so với BN. | `CẦN NHÓM CHỐT`. | Chưa có model. |
| `M1.x` – mỗi op giữa hai Conv, input/output và tham số nếu có | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; thêm một dòng cho từng mốc thật. | `CẦN NHÓM CHỐT`. | Chưa có graph. |
| Conv #2 weight | `CHƯA CÓ – SV3 CẦN CUNG CẤP` – shape PyTorch **thực** và thứ tự trục. | `CẦN NHÓM CHỐT` – shape, thứ tự trục, offset và packing. | Chưa có model. |
| Conv #2 bias / tham số BN nếu có | `CHƯA CÓ – SV3 CẦN CUNG CẤP` – từng tensor và shape. | `CẦN NHÓM CHỐT`; nếu BN fold, ghi tensor hiệu dụng. | Chưa có model. |
| `M2` Conv #2 output | `CHƯA CÓ – SV3 CẦN CUNG CẤP` – shape, layout, dtype và vị trí so với BN. | `CẦN NHÓM CHỐT`. | Chưa có model. |
| `M2.x` – mỗi op sau Conv #2; `M_final` | `CHƯA CÓ – SV3 CẦN CUNG CẤP`; thêm từng mốc thật, chỉ rõ mốc cuối. | `CẦN NHÓM CHỐT`. | Chưa có graph. |

## 4. Danh sách file SV3 phải bàn giao

Các đường dẫn **dự kiến** dưới `ml/artifacts/week3/<handoff_id>/` là vị trí của gói bàn giao do SV3 tạo sau này, không phải file đang tồn tại. `handoff_id`, tên file cuối cùng và cách đặt artifact vào firmware: `CẦN NHÓM CHỐT`. SV3 ghi đường dẫn thực, SHA-256 raw-byte, format/version và kích thước từng file vào hướng dẫn bàn giao; file text cần ghi chính sách hash phù hợp [`ml/docs/week1_data_protocol.md`](../ml/docs/week1_data_protocol.md). Những `.npy` dành cho PC theo cách lưu mảng đang dùng ở [`ml/src/build_mitdb_processed.py`](../ml/src/build_mitdb_processed.py); firmware-ready representation chỉ được xuất sau khi chốt layout C. Dấu `<...>` trong bảng là chỗ điền, không phải tên giá trị thật.

| Đường dẫn dự kiến | Format; dtype; shape cần công bố | Liên kết `sample_id` / mục đích |
|---|---|---|
| `ml/artifacts/week3/<handoff_id>/model/checkpoint.pt` | PyTorch checkpoint; dtype/shape từng tham số `CHƯA CÓ – SV3 CẦN CUNG CẤP`. | Gắn `model_version`, commit, hash; nguồn của mọi tham số/golden. |
| `ml/artifacts/week3/<handoff_id>/samples.csv` | UTF-8 CSV; 20 dòng dữ liệu, `sample_id` duy nhất và metadata nguồn như mục 2; dtype scalar/shape không áp dụng. | Dòng thứ *i* ánh xạ cùng trục batch *i* của input và mọi golden. |
| `ml/artifacts/week3/<handoff_id>/inputs.npy` | NumPy `.npy`; shape `(20,C,L)` theo dataset đã chốt, dtype `float32` **nếu** FP32 sau chuẩn hóa; trạng thái thực `CHƯA CÓ – SV3 CẦN CUNG CẤP`. | 20 input cố định theo thứ tự `samples.csv`; ghi layout/strides và độ sâu preprocessing. |
| `ml/artifacts/week3/<handoff_id>/weights/conv1.weight.npy`, `conv2.weight.npy` | NumPy `.npy`; dtype, shape và thứ tự trục PyTorch thực `CHƯA CÓ – SV3 CẦN CUNG CẤP`. | Tham số dùng chung cho cả 20 mẫu; checkpoint key/hashes liên kết trong hướng dẫn. |
| `ml/artifacts/week3/<handoff_id>/weights/<bias_or_bn_parameter>.npy` | Một file `.npy` cho mỗi bias/BN parameter cần thiết; nếu vắng/fold phải ghi rõ; dtype/shape `CHƯA CÓ – SV3 CẦN CUNG CẤP`. | Không theo `sample_id`; liên kết layer, checkpoint key và fold status. |
| `ml/artifacts/week3/<handoff_id>/firmware/head_parameters.h` | Dự kiến C header chứa **đủ** Conv weights/bias hiệu dụng và tham số BN chưa fold; dtype, shape, layout mảng và bit/byte representation `CẦN NHÓM CHỐT`. | Dùng chung cho 20 mẫu; SV1 xác minh hash và ánh xạ từng phần tử với `.npy`. |
| `ml/artifacts/week3/<handoff_id>/golden/<milestone_id>.npy` | Một NumPy `.npy` cho **mỗi mốc thực** từ `M1` đến `M_final`; dtype/shape `(20, ...)` theo bảng đã điền, hiện `CHƯA CÓ – SV3 CẦN CUNG CẤP`. | Dòng *i* ứng với `sample_id` dòng *i*; tên mốc phải khớp graph. Golden lưu/so sánh trên PC, không mặc định đưa 20 golden vào Flash. |
| `ml/artifacts/week3/<handoff_id>/scripts/export_week3.py`, `verify_week3.py` | Python source UTF-8; dtype/shape không áp dụng. | Lệnh export tái lập từ checkpoint/20 nguồn; verify hash, số mẫu, dtype/shape, và tạo/đối chiếu golden. `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |
| `ml/artifacts/week3/<handoff_id>/README.md` | Markdown UTF-8; dtype/shape không áp dụng. | Hướng dẫn chạy ngắn, bảng mốc, mapping `sample_id`, phiên bản môi trường, danh sách hash, lệnh export và verify. `CHƯA CÓ – SV3 CẦN CUNG CẤP`. |

Nếu định dạng firmware khác C header, đổi **một** đường dẫn trong bảng sau khi SV1/SV3 duyệt và ghi rõ cách đọc/kiểm chứng; không duy trì hai layout firmware ngầm cạnh tranh. Có thể stream từng input hoặc nạp bộ mẫu theo cách SV1 chọn sau khi đo Flash/RAM; metadata `sample_id` và phép so sánh phải giữ nguyên.

## 5. Nghiệm thu hai Conv trên nRF52840

1. SV1 kiểm SHA-256, đúng `handoff_id`, checkpoint/commit, dataset config + normalization + manifest hashes, đúng 20 `sample_id` duy nhất, shape/dtype/element count và mọi giá trị hữu hạn trước khi chạy. Thiếu file, thiếu mẫu hoặc mapping không khớp là **FAIL**.
2. SV3 chạy script PyTorch ở chế độ eval trên đúng 20 input đã bàn giao và xuất golden theo **từng mốc thực**. SV1 chạy cùng 20 input trên firmware hai Conv, thu đầy đủ output MCU và `sample_id` của từng lần chạy. Định dạng/kênh thu log hoặc dump output MCU phải được SV1/SV3 chốt để không mất phần tử; USB CDC hiện tại chỉ là console demo, không phải transport I1 đã duyệt.
3. Trên PC, chuyển layout MCU về shape logic PyTorch theo bảng ánh xạ đã chốt; so sánh từng phần tử của cùng `sample_id` và mốc. Kiểm cả shape, dtype, số phần tử; tính và ghi `max(abs(output_mcu - output_pytorch))` cho **mỗi** mẫu ở mỗi mốc, đặc biệt mốc trung gian để định vị lỗi. Không trừ theo buffer tuyến tính nếu chưa kiểm ánh xạ trục.
4. Nếu nhóm chốt **FP32**, mỗi mẫu phải có `max(abs(output_mcu - output_pytorch)) < 1e-3` tại `M_final` (dấu `<` nghiêm ngặt). Bất kỳ NaN/Inf ở input/output, sai shape, thiếu phần tử, thiếu mẫu hoặc sai số cuối không đạt đều **FAIL**. Mốc trung gian phải ghi sai số; ngưỡng quyết định bắt buộc nêu ở đây áp dụng cho mốc cuối hai lớp.
5. Biên bản kết quả ghi số đạt trên 20 (`20/20` chỉ khi thực đạt), sai số lớn nhất toàn bộ mẫu tại `M_final`, bảng sai số từng mẫu/mốc, phiên bản/commit firmware, toolchain, build profile, Flash/RAM dùng và peak RAM/buffer nếu đo được. Trạng thái hiện tại: golden `CHƯA CÓ – SV3 CẦN CUNG CẤP`; cách thu và báo cáo kết quả MCU/tài nguyên `CẦN NHÓM CHỐT`, phép đo chưa thực hiện, **chưa có PASS**.

## Cần chốt trước khi triển khai

- **FP32 hay INT8 cho Tuần 3:** yêu cầu Tuần 3 trong đề bài là sai số float tại hai Conv, trong khi lượng tử hóa INT8 được đặt ở Tuần 5. SV3, SV1 và thầy chốt bằng văn bản precision thực dùng cho Tuần 3 và phạm vi so sánh. Nếu chọn FP32, áp dụng tiêu chí mục 5; input dữ liệu Tuần 1 đã có `float32`. Nếu chọn INT8, phải chốt quantization của **input, weights, bias, activation**, scale/zero point/axis, rounding, clamp, requantize, BN fold, mốc so sánh (giá trị lượng tử hay dequantized), cách tính sai số và ngưỡng riêng; quy tắc I1 mục 8 chỉ áp dụng khi biểu diễn tensor trên wire I1. **Không áp ngưỡng FP32 `1e-3` cho INT8 khi chưa thống nhất.** Quyết định: `CẦN NHÓM CHỐT`.
- **Khả thi bộ nhớ nRF52840:** SV3 cung cấp kích thước byte của mỗi tensor/weight, peak activation và yêu cầu workspace theo graph/precision thật; SV1 tính phần Flash cho mã + tham số + input lưu trên dongle (nếu chọn lưu), phần RAM cho input/activation/workspace/stack/console, rồi build/đo trên `nrf52840dongle/nrf52840`. Phải ghi Flash/RAM còn dư của image Tuần 3. Quyết định lưu cả 20 input hay stream từng mẫu: `CẦN NHÓM CHỐT`; **không** giả định 20 golden nằm trong Flash.
- **Layout firmware và điểm cắt cuối:** SV3/SV1 chốt bảng trục, offset/packing của tham số, input/output và graph/mốc `M_final` trước khi viết kernel hoặc export C. Nếu output Tuần 3 sau này thành I1 activation, còn phải chốt `(model_profile_id, split_id)` và profile I1 với SV2; thử hai Conv cục bộ không tự cấp quyền gửi I1.

## Điểm cần nhóm chốt

| Điểm mở | Người cần chốt | Vì sao đang mở |
|---|---|---|
| Dataset/profile, checkpoint, graph và 20 nguồn mẫu | SV3, SV1 | Repository ML hiện chỉ có dữ liệu Tuần 1; không có model/golden Tuần 3. |
| Precision, ngưỡng/đối chiếu INT8 nếu dùng, BatchNorm fold và mốc cuối | SV3, SV1, thầy | Tuần 3 yêu cầu sai số float; INT8 nằm ở lộ trình Tuần 5; graph thực chưa có. |
| Layout C, file tham số firmware, cách thu output, budget Flash/RAM | SV3, SV1 | I1 không định nghĩa layout weight hay buffer C; firmware hiện chưa có inference. |
| I1 deployment profile, transport và protection **nếu** triển khai trao đổi với Edge | SV3, SV1, SV2 | I1 mục 11, 18, 22 còn mở; `PROTECTED_PAYLOAD` hiện reserved và `flags` phải bằng 0. |

Đối chiếu các hợp đồng hiện có với mã nguồn hiện tại **chưa phát hiện mâu thuẫn trực tiếp**. Việc I1 hỗ trợ enum `INT8` trên wire không phải quyết định dùng INT8 ở Tuần 3; việc I1 có protocol golden vector không phải bằng chứng có golden ML. Nếu về sau phát hiện hợp đồng cũ mâu thuẫn nhau hoặc trái mã nguồn, ghi cụ thể đường dẫn/mục, giá trị hai phía, ảnh hưởng và người cần duyệt tại đây; không tự sửa hợp đồng cũ hoặc chọn ngầm một bên.

## Checklist bàn giao và thay đổi phiên bản

**SV3 – xuất và bàn giao**

- [ ] Chốt dataset/profile, precision, kiến trúc, `M_final` cùng SV1/thầy; điền toàn bộ bảng shape/layout và thứ tự op.
- [ ] Ghi checkpoint path/hash, source commit, model version, export script, dependency và trạng thái BN fold.
- [ ] Chọn và khóa đúng 20 mẫu thật; ghi `sample_id`, metadata nguồn, quy tắc chọn, config/normalization/manifest hash và trạng thái preprocessing.
- [ ] Xuất đủ input, tham số PyTorch, firmware-ready weight/bias/BN theo layout đã duyệt, golden cho từng mốc, script export/verify, README và hash từng file.
- [ ] Tự chạy verify: đúng 20 mẫu, không NaN/Inf, shape/dtype/count khớp, tái tạo golden từ checkpoint và mọi liên kết `sample_id` đúng.

**SV1 – tiếp nhận và kiểm tra**

- [ ] Kiểm tra toàn bộ file/hash, checkpoint/commit/profile, 20 `sample_id`, trạng thái preprocessing và bảng tensor; từ chối phần còn bỏ trống ảnh hưởng triển khai.
- [ ] Đối chiếu từng phần tử tham số firmware với PyTorch theo ánh xạ đã chốt; tính budget và đo Flash/RAM của firmware hai Conv.
- [ ] Chạy cùng 20 input, thu đủ output MCU theo `sample_id`/mốc, so sánh từng phần tử, ghi sai số trung gian và quyết định PASS/FAIL ở `M_final` theo precision đã chốt.
- [ ] Lưu biên bản 20/20, sai số lớn nhất, firmware version/commit, Flash/RAM và các trường hợp FAIL.

**Khi checkpoint, graph, preprocessing hoặc tập mẫu đổi:** SV3 tạo `handoff_id`/version mới, ghi lý do và diff nguồn, cập nhật bảng mốc/shape/hash, xác nhận lại 20 nguồn và `sample_id`, xuất lại **toàn bộ** 20 input, tham số firmware và golden cho mọi mốc từ cùng revision, chạy lại script kiểm tra; SV1 bỏ kết quả nghiệm thu cũ và chạy lại đủ 20 mẫu. Nếu chỉ checkpoint đổi, có thể giữ 20 định danh nguồn nhưng vẫn phải phát hành gói mới và tạo lại golden. Gói cũ giữ nguyên để truy xuất; không thay file âm thầm dưới cùng `handoff_id`.
