# SV3 — Phạm vi và checklist nghiệm thu tuần 5

Ngày lập/cập nhật: 2026-10-09 (Asia/Saigon). CURRENT WEEK = 5. Phiên bản checklist: 1.1.

Trạng thái: đã cập nhật theo quyết định kỹ thuật SV1 do người dùng cung cấp. Chưa kiểm tra repository/code/log hiện tại, chưa đánh dấu implementation là PASS. Thứ tự thực hiện: hoàn thiện → kiểm thử và xác định PASS kỹ thuật tuần 5 → người dùng yêu cầu review tổng thể sau đó. PASS kiểm thử không thay thế review/phê duyệt merge.

## 1. Nguồn và cách đọc kết luận

- **S1:** `Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx`, A.3, giai đoạn 1, hàng tuần 5–6; A.1 tuần 5; A.2 tuần 5; B.4 phần kiến thức tuần 5.
- **S2:** `Huong1_Bao_cao_trien_khai_3SV.docx`, bảng tiến độ tuần 4–6.
- **S3:** `06_Huong1_Adaptive_Split_Inference_Lo_trinh.docx`, Bài 7, mục 7.1, tầng P1.
- **S4:** `Huong1_Phan_cong_nhom_nghien_cuu.docx` và `Huong1_Phan_cong_nhom_nghien_cuu_1.docx`, nhiệm vụ C2/C3 và hợp đồng I2. Hai bản nhất quán ở các nội dung này. SV-C tương ứng SV3, SV-A tương ứng SV1, SV-B tương ứng SV2.
- **S5:** `QUY_UOC_LAM_VIEC_VA_DINH_DANG_DU_AN_v1.0(2).txt`, mục 1.2, 2.2–2.3, 3, 6–7, 11.4, 12–14.
- **S6:** nội dung quyết định kỹ thuật SV1 gửi lại, được người dùng cung cấp trong cuộc hội thoại ngày 2026-10-09. S6 chốt scale FP16/FP32, I2/1 và descriptor NCL, split registry, ngưỡng accuracy, decision note và trách nhiệm; yêu cầu giữ nguyên tài sản đã nghiệm thu. Đây là nguồn cập nhật trực tiếp cho checklist 1.1, không phải bằng chứng đã đọc hoặc kiểm thử implementation trong repository.

Nhãn:

- **[EXPLICIT]:** nguồn nói trực tiếp.
- **[CHỐT-SV1]:** S6 đã chốt kỹ thuật; triển khai/bằng chứng vẫn cần đối chiếu với reference, schema/header và vectors hiện hành.
- **[DERIVED]:** bước cần thiết hoặc cách kiểm chứng đề xuất để thực hiện requirement; không phải một requirement mới được trích từ nguồn.
- **[CHƯA XÁC ĐỊNH]:** cần kiểm tra hợp đồng/quyết định và hiện trạng repository; không tự chọn một bản đề xuất làm chuẩn đã phê duyệt.

S6 xác định hợp đồng I2/1 hiện hành tại `contracts/i2_protection_v1.md` cùng reference và registry liên quan. Dùng quyết định S6 để đối chiếu các nguồn hiện hành được hợp đồng dẫn tới. Những đề xuất cũ trong S5 phải được ghi rõ chưa áp dụng/đã bị thay thế; không coi chữ ký I2 chỉ biết tổng số byte là API chuẩn. Nếu nội dung repository mâu thuẫn S6, ghi chính xác khác biệt và không tự sửa đặc tả hoặc goldens để xóa mâu thuẫn. I1 v1 có quy tắc scale trên wire được chốt; điều này không đồng nghĩa toàn bộ I1 FROZEN hoặc Device–Edge đã nghiệm thu.

## 2. Công việc chính xác của tuần 5

**[EXPLICIT — S1, A.3, tuần 5]**

> • Hiện thực P1 (hoán vị kênh + mặt nạ affine) bản Python
> • Dùng PRNG có khóa (xoshiro128** hoặc ChaCha20)
> • Chứng minh khả nghịch

Tiêu chí nghiệm thu nguyên văn:

> unprotect(protect(z)) == z bit-exact trên 10.000 tensor

**[EXPLICIT — S1, B.4]** Kiến thức cần học tuần 5: PRNG có khóa, nonce, nguyên tắc Kerckhoffs; số học modulo và ánh xạ khả nghịch, đặc biệt vì sao hệ số nhân phải lẻ để khả nghịch mod 256.

**[EXPLICIT — S3, 7.1]** P1 đổi thứ tự kênh, rồi dùng affine theo từng kênh trên miền byte. Phép nhân sử dụng hệ số lẻ. Hai phía phải tái tạo cùng tham số để đảo được biến đổi.

**[EXPLICIT — S1, tuần 6; S4, C3]** Port P1 sang C, tối ưu Cortex-M và bàn giao chính thức cho SV1/SV2 kèm 50 vector kiểm thử thuộc tuần 6. Điều kiện tuần 6: C và Python có cùng kết quả trên 50 vector. Không chuyển điều kiện này thành gate bắt buộc của tuần 5.

Mục tiêu tuần 5: P1 Python đúng I2/1, lập luận khả nghịch, bằng chứng 10.000 tensor; ML metadata/reference/vector khớp quyết định S6, accuracy đủ 8.544 mẫu tại mọi s=0..10 đạt ngưỡng; decision note có version và hồ sơ bàn giao đủ để SV1/SV2 triển khai. Đây là phạm vi triển khai và kiểm thử SV3, tách khỏi nghiệm thu phần cứng và review tổng thể sau khi PASS.

## 3. Đầu vào cần có và cần nhận từ ai

| Đầu vào | Nguồn/người cung cấp | Vai trò trong tuần 5 | Nhãn |
| --- | --- | --- | --- |
| Kiến trúc, checkpoint, danh sách điểm cắt và shape/layout từng điểm cắt đã chốt | Artefact SV3 tuần 3–4 | Tạo tensor thật và bảo đảm P1 đúng với biểu diễn của mô hình hiện hành | [DERIVED], dựa trên S1 tuần 3–4 |
| Tensor INT8 ở các điểm cắt; metadata lượng tử hóa và cách diễn giải byte | Pipeline/artefact SV3; đối chiếu SV1/SV2 | Đầu vào thực tế cho protect/unprotect; không cần chờ MCU để bắt đầu kiểm thử Python | [DERIVED] |
| I2/1, reference và descriptor/active_profile | `contracts/i2_protection_v1.md` và các file hiện hành được dẫn tới | Dùng đúng API/PRNG/metadata đã áp dụng, không thiết kế API thay thế | [CHỐT-SV1]; file thực tế chưa được đọc trong phiên này |
| Model/split registry, mapping wire split_id, test frozen và reference lượng tử hóa đã review | Artefact hiện hành của nhóm | Kiểm đủ 8.544 mẫu, s=0..10; xác minh mapping và scale | [CHỐT-SV1] |
| Scale lưu FP16, zero-point=0; quy tắc mở rộng scale sang FP32 trên wire | S6; đối chiếu reference/schema/header/vector hiện hành | Tính q bằng scale FP16 đọc lại và giữ giá trị đó khi truyền | [CHỐT-SV1] |
| Danh sách split compile được/lỗi; lớp DPU không hỗ trợ; phương án DPU hoặc DPU+PS | SV2 | Xác định SV3 có cần hỗ trợ export/model nào; ghi dependency | [DERIVED] về nhận báo cáo, dựa trên công việc [EXPLICIT] của SV2 tuần 5 |

**Không có yêu cầu trong nguồn rằng SV3 phải nhận một gói phần cứng mới từ SV1/SV2 rồi mới được làm P1 Python.** Có thể bắt đầu với dữ liệu tổng hợp và artefact mô hình của chính SV3. Báo cáo phần cứng giúp phối hợp, không tự động trở thành điều kiện chặn toàn bộ tuần 5.

Nếu thiếu tensor thật do artefact trước chưa sẵn sàng, vẫn học/chốt đặc tả và kiểm thử tổng hợp; ghi riêng dependency chưa giải quyết, không mô tả kiểm thử tổng hợp là đã xác nhận tương thích tensor thực tế.

## 4. Cần bàn giao hoặc hỗ trợ gì

| Bên nhận | Nội dung tuần 5 | Điều kiện kiểm tra | Phân loại |
| --- | --- | --- | --- |
| SV1 | Xác nhận bộ 20 mẫu kiểm số học/bytes và đủ 8.544 mẫu test frozen cho accuracy | Trỏ tới tài sản hiện có, input/label/baseline đúng phiên bản; không dùng 20 mẫu kết luận accuracy | [EXPLICIT] từ S1, [CHỐT-SV1] từ S6 |
| SV1 | Kết quả đối chiếu ML metadata/reference/vector và bảng accuracy 11 split | Scale/zero-point/layout đúng S6, mọi split giảm <0,5 điểm phần trăm | [CHỐT-SV1] |
| SV2 — Trung | Decision note có version, tham chiếu I2/1/reference/descriptor/registry; xác nhận mô hình đã bàn giao | Trung triển khai phía nhận: đảo I2 → dequantize bằng scale đúng → trả shape phù hợp trước tail | [CHỐT-SV1]; không nhận thay implementation phía nhận |
| SV1 và SV2 | Hồ sơ P1 Python và log 10.000 tensor; hướng dẫn chạy và danh sách quyết định áp dụng | Chuẩn bị cho bàn giao; review tổng thể sau khi tuần 5 PASS theo yêu cầu người dùng | [DERIVED], không phải bàn giao C chính thức |
| SV1 và SV2, tuần 6 | P1 bản C + API/đặc tả + 50 vector đối chiếu Python–C | 50/50 kết quả giống hệt | [EXPLICIT], mốc tương lai, chưa triển khai trong tuần 5 |

Nếu đầu vào đã bàn giao và còn đúng phiên bản thì tái sử dụng; không tạo thêm revision chỉ để thay tên hoặc đóng gói lại.

## 5. Các quyết định đã chốt — chuyển thành điều kiện đối chiếu

### 5.1. Scale FP16 hay FP32

**[CHỐT-SV1 — S6]** INT8 per-channel, zero-point=0. Scale lưu FP16; tính q bằng chính giá trị FP16 đã lưu và đọc lại. Rounding/clipping và cách xử lý scale phải theo reference đã review, không tự dựng reference mới.

Khi triển khai I1 v1, mỗi scale trên wire là FP32 little-endian, mang giá trị scale FP16 đã lưu được mở rộng sang FP32. Không tính lại scale từ dữ liệu, không gửi scale_raw trước làm tròn, không truyền trực tiếp FP16 dưới nhãn I1 v1.

**Kiểm tra SV3:** đối chiếu q/scale với reference và goldens; kiểm tra biểu diễn FP32 little-endian của giá trị mở rộng bằng test thành phần thích hợp. Không triển khai toàn bộ transport hoặc coi kiểm tra thành phần scale là I1 end-to-end PASS. Scale wire đã có quyết định, không còn BLOCKED vì chưa rõ FP16/FP32.

### 5.2. API I2 và metadata kênh

**[CHỐT-SV1 — S6]** Dùng I2/1 trong `contracts/i2_protection_v1.md`, reference đi kèm, `active_profile` và descriptor chứa N,C,L. I2 dùng NCL `[1,C,L]`, descriptor phải khớp model/split registry. Không suy C/L từ tổng số byte và không dùng API đề xuất cũ.

Với s9/s10 có tensor NC: thêm L=1 khi đưa vào I2, rồi trả về shape gốc trước tail theo reference. Điểm cắt mô hình là s=0..10; wire split_id dùng mapping trong registry. Không lấy mapping s+1 từ test làm mapping triển khai.

Scale gắn với kênh gốc: bên nhận phải khôi phục q bằng unprotect trước, rồi mới dequantize. Không dùng scale kênh gốc để dequantize tensor đang bị hoán vị/affine. NCL là layout của I2; không tự sửa layout I1 đã được đặc tả chỉ vì I2 dùng NCL.

**Kiểm tra SV3:** đối chiếu descriptor/registry/shape adapter; kiểm trường hợp metadata sai theo hành vi quy định trong hợp đồng; xác minh chuỗi q → protect → unprotect → dequantize → shape phù hợp → tail. Không thiết kế lại I2.

### 5.3. Ý nghĩa ngưỡng accuracy < 0.5%

**[CHỐT-SV1 — S6]** Ngưỡng chính nghiêm ngặt:

`Accuracy_FP32 (%) − Accuracy_INT8 (%) < 0,5 điểm phần trăm`.

Kiểm trên đủ **8.544 mẫu test frozen tại mọi s=0..10**. Mọi split phải đạt; không dùng trung bình qua các split để che một split fail. Tính gate từ số liệu chưa làm tròn. Nếu chênh lệch đúng 0,5 thì FAIL. Tỷ lệ giảm tương đối báo thêm nhưng không thay gate chính. Bộ 20 mẫu chỉ kiểm số học/bytes.

**Kiểm tra SV3:** dùng đúng checkpoint/test frozen/reference được duyệt; báo số mẫu đúng, tổng mẫu, accuracy FP32/INT8, chênh điểm phần trăm và PASS/FAIL cho từng split. Đây là gate ML reference theo S6, không phải bằng chứng MCU đã chạy đủ tập test.

“Kích thước tensor giảm đúng 4×” áp dụng cho vùng dữ liệu FP32 → INT8 cùng số phần tử. Không mặc định tổng gói tin gồm scale, header, nonce, CRC cũng giảm đúng 4×.

### 5.4. Decision note, trách nhiệm và tài sản lịch sử

**[CHỐT-SV1 — S6]** Ghi các quyết định thành note có version trong `contracts/`, dẫn tới đúng reference, schema/header và test vectors hiện hành; chỉ rõ đề xuất cũ chưa áp dụng/đã bị thay thế. Version của decision note không tự động đổi version I1/I2.

SV3 đối chiếu ML metadata/reference/vector. Trung triển khai phía nhận. Thay đổi đặc tả tiếp theo cần SV1 chốt trước; không hỏi lại ba quyết định đã được S6 chốt.

Giữ nguyên gói ML, goldens, manifest và tài sản lịch sử đã nghiệm thu. Không re-export chỉ để cập nhật quyết định. Code/doc mới và báo cáo kiểm thử mới dùng đường dẫn mới thích hợp; đối chiếu hash để chứng minh tài sản cũ không đổi. Khi phát hiện bất nhất với tài sản chuẩn, báo FAIL/BLOCKED cụ thể; không sửa chuẩn cho khớp code.

## 6. Checklist theo LEARN → UNDERSTAND → PLAN → IMPLEMENT → VERIFY → DELIVER

Chưa đánh dấu checkbox nào: quyết định đã chốt không có nghĩa implementation đã PASS. Các mục LEARN ghi việc chuẩn bị giải thích/kiến thức; Codex không tự xác nhận người dùng đã học hiểu. Người dùng đã chọn hoàn thành implementation và kiểm thử trước, học/review sau; việc này không chặn Codex thực hiện phần kỹ thuật được ủy quyền.

### LEARN

- [ ] **W5-01 [EXPLICIT]:** học PRNG có khóa, nonce và Kerckhoffs. Đạt khi giải thích được vì sao hai phía phải dùng cùng key/nonce và quy tắc sinh tham số; không dựa vào việc giấu code.
- [ ] **W5-02 [EXPLICIT]:** học số học modulo và phép đảo. Đạt khi giải thích được vì sao hệ số nhân lẻ có nghịch đảo mod 256, hệ số chẵn không bảo đảm điều đó.

### UNDERSTAND

- [ ] **W5-03 [CHỐT-SV1]:** xác định INT8 per-channel, zero-point=0, scale FP16 lưu/đọc lại; I2 NCL `[1,C,L]` và descriptor/active_profile. Đạt khi metadata khớp reference và registry hiện hành; không suy kênh từ payload length.
- [ ] **W5-04 [DERIVED]:** phân biệt lượng tử hóa và P1. Đạt khi mô tả đúng: lượng tử hóa → protect → unprotect → dequantize → tail; P1 phải khôi phục đúng byte INT8.
- [ ] **W5-05 [EXPLICIT về giới hạn, S3/S5]:** giải thích giới hạn P1. Đạt khi không khẳng định affine/hoán vị là mã hóa mạnh, không tuyên bố chống replay/xác thực nếu chưa có cơ chế và bằng chứng; edge có khóa có thể khôi phục tensor.

### PLAN

- [ ] **W5-06 [CHỐT-SV1, EXPLICIT S1]:** đọc I2/1 cùng reference và giữ PRNG/key/nonce/thứ tự biến đổi hiện hành. Đạt khi code Python tương thích, không chọn lại thuật toán hoặc sửa API đã chốt.
- [ ] **W5-07 [CHỐT-SV1]:** đối chiếu s=0..10, registry mapping wire split_id và adapter NC ↔ NCL cho s9/s10. Đạt khi mọi descriptor khớp, L=1 dùng đúng và shape được trả về trước tail; không lấy s+1 từ test làm mapping triển khai.
- [ ] **W5-08 [DERIVED]:** lập kế hoạch 10.000 tensor với seed, phân bố shape và nhóm dữ liệu được ghi rõ. Đạt khi có cách tái tạo và bao phủ hợp lý tensor thực tế cùng giá trị biên. Nguồn không ấn định quota từng nhóm.

### IMPLEMENT

- [ ] **W5-09 [EXPLICIT, CHỐT-SV1]:** hoàn thiện protect P1 Python theo I2/1: hoán vị kênh + affine modulo 256. Tái sử dụng code đã đúng; chỉ sửa lỗi có bằng chứng. Đạt khi khớp reference/vectors hiện hành.
- [ ] **W5-10 [EXPLICIT, CHỐT-SV1]:** hoàn thiện unprotect P1 Python theo I2/1. Đạt khi đảo đúng thứ tự, khôi phục byte q trước dequantize; scale vẫn thuộc kênh gốc.
- [ ] **W5-11 [DERIVED]:** viết runner kiểm thử và báo cáo. Đạt khi lệnh chạy tự tính PASS/FAIL, báo tổng tensor và số tensor lỗi, không chỉ in kết quả kỳ vọng.

### VERIFY

- [ ] **W5-12 [EXPLICIT]:** chứng minh khả nghịch. Đạt khi trình bày được hoán vị có phép đảo và affine có phép đảo do hệ số lẻ; áp dụng đúng thứ tự nghịch đảo.
- [ ] **W5-13 [EXPLICIT]:** round-trip bit-exact trên 10.000 tensor. Đạt khi ít nhất 10.000 tensor được kiểm thử, 0 tensor sai dtype/shape/byte theo đặc tả round-trip; không dùng so sánh gần đúng.
- [ ] **W5-14 [DERIVED]:** kiểm tra PRNG/thuật toán thực sự làm theo đặc tả. Đạt khi cùng input/key/nonce/metadata sinh cùng output; cách sinh tham số và nhóm vector nhỏ có thể kiểm tra độc lập. Round-trip tự nó chưa chứng minh hai phía triển khai cùng thuật toán.
- [ ] **W5-15 [DERIVED theo S6]:** kiểm trên tensor INT8 thực ở s=0..10 và đường tham chiếu unprotect → dequantize → trả shape → tail. Đạt khi q sau unprotect bit-exact, scale/shape đúng; đối chiếu kết quả trước/sau P1 theo reference.
- [ ] **W5-16 [DERIVED]:** thử giá trị INT8 biên, tensor toàn 0/hằng, một kênh và các trường hợp hợp lệ khác theo đặc tả. Đạt khi giữ chính xác mẫu bit; trường hợp không hỗ trợ bị từ chối theo quy tắc đã ghi. Bộ vector C 50 ca vẫn là mốc tuần 6.

### DELIVER

- [ ] **W5-17 [EXPLICIT S1, CHỐT-SV1]:** xác nhận tập 20 mẫu số học/bytes và test frozen 8.544 mẫu đã có đúng phiên bản. Đạt khi input/label/baseline/lệnh chạy rõ; không tạo lại gói lịch sử hoặc dùng 20 mẫu kết luận accuracy.
- [ ] **W5-18 [CHỐT-SV1]:** chuẩn bị hồ sơ metadata/reference/vector cho SV1 và Trung; xác nhận artefact mô hình SV2 hiện có. Đạt khi references đúng, responsibilities rõ; Trung triển khai phía nhận, SV3 không nhận thay phần đó.
- [ ] **W5-19 [EXPLICIT — S5 11.4]:** cập nhật README, lệnh chạy, phiên bản môi trường, code và bằng chứng; commit/push đúng nhánh. Đạt khi một thành viên khác có thể chạy lại và kết quả không phá giao diện đã chốt.
- [ ] **W5-20 [EXPLICIT S5, chỉ đạo người dùng]:** chuẩn bị draft PR và báo cáo kỹ thuật tổng hợp sau kiểm thử. Đạt khi đủ link commit/PR/log, status của từng gate và limitation; REVIEW_STATUS=PENDING. Review tổng thể sau khi PASS, chưa merge/main và chưa chuyển tuần 6.
- [ ] **W5-21 [CHỐT-SV1]:** kiểm accuracy đủ 8.544 mẫu test frozen cho cả 11 split s=0..10. Đạt khi mọi split có `Accuracy_FP32 − Accuracy_INT8 < 0,5` điểm phần trăm, xét số liệu chưa làm tròn; báo thêm giảm tương đối. Không cần chứng minh MCU đã chạy đủ 8.544 mẫu để gọi ML reference PASS.
- [ ] **W5-22 [CHỐT-SV1]:** bảo toàn gói ML/goldens/manifest/tài sản lịch sử. Đạt khi inventory/hash trước/sau và diff chứng minh không đổi; báo cáo mới không ghi đè bản đã nghiệm thu. Không re-export chỉ vì cập nhật decision.
- [ ] **W5-23 [CHỐT-SV1, cách kiểm DERIVED]:** đối chiếu q dùng scale FP16 đọc lại; kiểm scale wire là FP32 little-endian mở rộng từ đúng giá trị FP16. Đạt khi metadata/reference/vector và test thành phần khớp; không tuyên bố I1 end-to-end/FROZEN.
- [ ] **W5-24 [CHỐT-SV1]:** tạo/cập nhật decision note có version trong `contracts/`. Đạt khi ghi đủ S6, dẫn đúng contract/reference/schema/header/vectors/registry, đánh dấu đề xuất cũ superseded/non-applied; không đổi spec I1/I2.

## 7. Cách quyết định PASS

Các tên trạng thái dưới đây là **[DERIVED]**, dùng để theo dõi rõ trách nhiệm; không phải tên gate có sẵn trong tài liệu.

### P1 Python

Chỉ ghi PASS khi đồng thời có:

1. Protect/unprotect Python thực hiện đúng P1/I2/1 hiện hành, descriptor và registry đúng S6.
2. PRNG có khóa và quy tắc key/nonce khớp reference đã áp dụng.
3. Lập luận khả nghịch đúng.
4. Ít nhất 10.000 tensor round-trip bit-exact; số tensor sai bằng 0.
5. Code, log, lệnh chạy và môi trường đủ để tái tạo; commit/push đúng nhánh theo Definition of Done.

### ML reference và đối chiếu giao diện

PASS khi scale/zero-point/q đúng reference và S6; shape/registry/NC adapter/ordering đúng; đủ 8.544 mẫu ở mọi s=0..10 đạt ngưỡng nghiêm ngặt <0,5 điểm phần trăm. Tách kết quả này khỏi P1 round-trip và kết quả phần cứng.

### Phối hợp/bàn giao của SV3

PASS khi có đủ tập kiểm thử/reference hiện hành, decision note có version, metadata/vector đã đối chiếu và hướng dẫn tái tạo cho SV1/SV2; tài sản lịch sử không đổi. Không báo BLOCKED vì scale/shape/ngưỡng chưa chốt: S6 đã giải quyết các quyết định đó. Nếu thiếu file/data/reference thực tế hoặc phát hiện conflict, ghi BLOCKED/FAIL cụ thể ở mục đó.

### PASS kỹ thuật triển khai SV3 tuần 5 và review sau đó

Chỉ ghi PASS kỹ thuật khi P1, ML reference, preservation, regression liên quan và đầu ra bàn giao thuộc SV3 đều đạt, có commit/push và hồ sơ bằng chứng. Không gọi PASS nếu một split accuracy fail, chưa đủ dữ liệu, hay chỉ chạy bộ 20 mẫu. Các mục học của người dùng và review độc lập không tự được đánh dấu đã hoàn thành vì test PASS.

Sau khi PASS: chuẩn bị kết quả cho người dùng, giữ `REVIEW_STATUS=PENDING`; review tổng thể do người dùng yêu cầu ở bước tiếp theo. Không bắt đầu audit toàn bộ lịch sử, merge, tự tăng CURRENT WEEK hoặc làm tuần 6 trong bước này.

### Kết quả phần cứng của SV1/SV2

- SV1: triển khai lượng tử hóa MCU và nghiệm thu accuracy/kích thước theo ngưỡng của SV1.
- SV2: compile tail, xử lý lớp không hỗ trợ và báo split chạy DPU hoặc DPU+PS. S2 ghi hoàn tất compile toàn bộ; S1 chi tiết cho phép phương án lai và yêu cầu ghi nhận.
- Các kết quả này ghi riêng. Không yêu cầu SV3 tự chạy PPK2, tự compile mọi `.xmodel`, hay chứng minh MCU PASS mới được công nhận P1 Python.

## 8. Artefact nên có vào cuối tuần

Đây là danh mục **[DERIVED]**, không ép đổi tên/cấu trúc repository hiện có:

| Artefact | Nội dung cần có |
| --- | --- |
| Module P1 Python | Protect/unprotect, PRNG và quy tắc dữ liệu theo đặc tả |
| Đặc tả P1 và lập luận khả nghịch | Dẫn I2/1 hiện hành; thứ tự biến đổi, modulo, descriptor NCL, key/nonce, giới hạn bảo vệ |
| Kế hoạch + runner + log 10.000 tensor | Seed, shape/split được phủ, số kiểm thử, số lỗi, môi trường/commit |
| Bảng accuracy đủ 8.544 mẫu × 11 split | Số mẫu đúng/tổng, accuracy FP32/INT8, chênh điểm phần trăm và giảm tương đối; gate chưa làm tròn |
| Decision note có version trong contracts/ | Quyết định S6 và liên kết đúng reference/schema/header/vectors/registry; đề xuất cũ superseded/non-applied |
| Bằng chứng preservation | Hash/inventory/diff trước/sau của tài sản đã nghiệm thu; giữ nguyên bản lịch sử |
| README | Lệnh chạy, đầu vào/đầu ra, cách đọc PASS/FAIL |
| Bản ghi phối hợp | Tập kiểm thử SV1, artefact SV2, quyết định giao diện, dependency còn mở |

Không bắt buộc tạo báo cáo Word/PDF hoặc phát hành revision mới nếu nhóm chưa yêu cầu. S6 đã xác định 11 điểm cắt s=0..10 và 8.544 mẫu; đường dẫn/tên artefact cụ thể và mapping wire phải lấy từ repository/registry, không đoán.

## 9. Điểm bắt đầu và phạm vi dừng của tuần 5

Theo chỉ đạo mới của người dùng: Codex đọc hợp đồng và quyết định S6, xác định phần đã có, hoàn thiện implementation và chạy verification đến khi PASS trước; không dừng để dạy hoặc yêu cầu review giữa chừng. Chuẩn bị phần giải thích/kiến thức cho bước học/review sau.

Tuần 5 chưa triển khai P1 C, tối ưu Cortex-M, NoPeek/P2, decoder/GAN, LUT/controller hay thí nghiệm năng lượng chính thức. Nguồn đặt các việc đó vào giai đoạn sau hoặc giao vai trò khác. Các con số chi phí P1 minh họa trong lộ trình không phải ngưỡng nghiệm thu tuần 5.

Checklist này xác định công việc và bằng chứng cần có; không khẳng định những việc trước đây đã làm phải làm lại. Khi có code/log hiện tại, đối chiếu từng mục và tái sử dụng bằng chứng còn đúng phiên bản.

## 10. Trạng thái thực thi 2026-10-09 — Codex

Nội dung mục 1–9 giữ bản checklist 1.1 do người dùng cung cấp, gồm trạng thái
chưa kiểm ở thời điểm gửi. Bảng này là cập nhật implementation/verification
hiện hành. `CURRENT WEEK=5`, `REVIEW_STATUS=PENDING`, **TECHNICAL_STATUS=BLOCKED**.
Không tick các checkbox LEARN hoặc xác nhận người dùng đã hiểu vì viết tài liệu.

Bằng chứng chung: [hồ sơ kỹ thuật](../ml/docs/week5_technical_20261009.md),
[decision note v1](../contracts/sv3_week5_decisions_v1.md),
[receipts/logs](../ml/provenance/week5-20261009-v1/),
[accuracy 11 splits](../ml/results/week5-20261009-v1-final/accuracy.csv).
Các tên evidence rút gọn bên dưới thuộc thư mục receipts/logs này, trừ khi có
path Git root. Pin commit/PR sau publish tại
`ml/provenance/week5-20261009-v1/delivery_publication.json`.

| Mục | Trạng thái | Bằng chứng/ý nghĩa |
|---|---|---|
| W5-01 | NOT_RUN | Kiến thức/khả năng giải thích của người dùng chưa nghiệm thu; tài liệu sẵn ở decision note. |
| W5-02 | NOT_RUN | Người dùng chưa xác nhận học hiểu modulo; không tự tick checkbox. |
| W5-03 | BLOCKED | Scale và shape ML PASS; registry wire chưa cấp model_profile_id/split IDs. |
| W5-04 | PASS | Tài liệu và tests đúng thứ tự q→protect→unprotect→dequant→restore→tail; không xác nhận người dùng học hiểu. |
| W5-05 | NOT_RUN | Giới hạn bảo vệ đã viết ở decision note; khả năng giải thích của người dùng chưa đánh giá. |
| W5-06 | PASS | Giữ I2/1/reference/API/key32/nonce12/ChaCha20; `interfaces_final_v2.*`, `i2_existing.*`. |
| W5-07 | BLOCKED | Adapter NC/NCL và cuts s0..10 PASS; mapping wire thực thiếu, không dùng s+1 test. |
| W5-08 | PASS | Seed20261005, 16 public keys, histogram shapes trong `p1_10000.json`; real quota20/s. |
| W5-09 | PASS | `ml/src/p1.py` reuse reference protect không sửa; vectors chuẩn và rejection/endian tests PASS. |
| W5-10 | PASS | unprotect q bit-exact trước dequantize, `real_220_final_v2.json` và ordering test. |
| W5-11 | PASS | Runner/log receipts/exit codes; accuracy count gate tự PASS/FAIL, aggregate báo BLOCKED khi thiếu registry. |
| W5-12 | PASS | Lập luận khả nghịch permutation + hệ số lẻ mod256 tại decision note v1. |
| W5-13 | PASS | 10000 synthetic +220 real =10220 tensor kiểm actual, 0 lỗi byte/dtype/shape; test-only profiles. |
| W5-14 | PASS | 2 vectors chuẩn, RFC8439 host tests, stream a/b/endian/rejection và deterministic checks. |
| W5-15 | PASS | 220 cặp INT8 thật đủ s0..10; q/FP16/wire/shape/tail giống golden; registry dùng test-only rõ ràng. |
| W5-16 | PASS | Biên -128/127, zero/hằng/random, single-channel/32768B và lỗi metadata theo reference. |
| W5-17 | PASS | 20 samples/220 entries, frozen8544 hashes theo external_assets; không tái tạo goldens hoặc ZIP. |
| W5-18 | BLOCKED | Hồ sơ/reference/vector/model SV2 chuẩn bị đủ; wire registry thật chưa cấp. MCU/DPU receipt tuần5 NOT_RUN. |
| W5-19 | PASS | README/code/environment/lệnh/receipts trên nhánh SV3; commit/push pin trong delivery_publication.json. |
| W5-20 | PASS | Draft PR và hồ sơ gate/log; publication receipt. REVIEW_STATUS=PENDING; review tổng thể NOT_RUN. |
| W5-21 | PASS | `ml/results/week5-20261009-v1-final/accuracy.csv`: đủ8544×11, từng split strict<0.5pp từ integer counts. |
| W5-22 | PASS | `preservation_before.json.gz`, `preservation_after.json`:94518 file gốc không đổi;754 asset copy khớp. |
| W5-23 | PASS | FP16 stored/reloaded q, FP32 LE wire expanded;220 real pairs +component tests thường/-O; I1 E2E NOT_RUN. |
| W5-24 | PASS | `contracts/sv3_week5_decisions_v1.md`; nguồn/schema/header/registry/vectors, proposal chưa áp dụng, không tăng protocol. |

Regression cuối PASS; các setup failures ban đầu được giữ log và được giải quyết
bằng args/fixture/copy mới, không sửa expected output. Suite cache bổ sung có
1 SKIP OS privilege tạo symlink, ghi riêng; mocked guard PASS. MCU/DPU tuần5
và I1 end-to-end NOT_RUN. Chưa đủ điều kiện PASS tổng vì registry wire thiếu,
không vì ba quyết định scale/shape/accuracy chưa chốt. Đề xuất allocation chưa
áp dụng ở decision note để SV1 quyết định; không gửi tin nhắn cho SV1/Trung.
