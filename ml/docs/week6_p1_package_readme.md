# SV3 Week 6 — 50 vector P1 chính thức

Gói chuẩn **PUBLIC_TEST_ONLY** cho SV1 kiểm P1 C và SV2 kiểm đầu vào I1 v2.
Key public 32 byte `00 01 ... 1f` nằm trong `vectors.json`; tuyệt đối không dùng
key này để provision bench/vận hành. Gói không chứa key bench/vận hành.

## Nguồn và cách chọn

50 tensor thật được lấy nguyên q/scale từ 220 cặp validation tuần 5, manifest
SHA-256 `8e20ed054462dda8f99815f20c817de36d21fdc1c5bf112cd2da5f67cdbf29bd`.
Chúng không phải 50 mẫu test accuracy độc lập. Chọn theo s tăng dần: sample
index 0..4 tại s0..s5, 0..3 tại s6..s10. Tổng 50, phủ 11 split.
Giữ nguyên checkpoint và scale FP16; không train, lượng tử hóa lại hay sửa q.
Manifest tuần 5 vẫn có `not_week6_p1_vectors=true`: đó là nhãn của gói nguồn
lịch sử, không bị sửa. Gói mới này là tuyển chọn 50 vector tuần 6 có nonce/P1
và bằng chứng mới, không đổi nhãn hiện vật cũ.

Registry/approval nguyên bytes nằm trong `inputs/`, với model profile
`1296651265`, key label `65537`, sender `131073`, wire split ID `256..266`.
Chỉ số s và wire ID được lưu tách riêng; descriptor dùng wire ID.
Sequence cố định `vector_index+1`, 1..50, không trùng dù đổi split;
nonce = sender:uint32_le || sequence:uint64_le. Đây là vector offline tái lập,
không cấp nonce cho truyền radio và không chứng nhận persistence NVS.

## Cách đọc một vector

`vectors.json` có `vectors[0..49]`. Mỗi hàng ghi sample ID MIT-BIH, index nguồn,
s, wire ID, shape, scale bits, sequence và đường dẫn tương đối tới:

- `q.i8.bin`: q INT8 two's complement, C-contiguous NCL `[1,C,L]`, không -128.
- `scale.f16le.bin`: C scale FP16, mỗi scale là uint16 little-endian; thứ tự
  theo kênh **gốc**. `scale_uint16_bits` cho phép đối chiếu trực tiếp.
- `descriptor.i2.bin`: đúng 28 B, little-endian theo I2/1.
- `nonce.bin`: đúng 12 B.
- `transformed.bin`: byte chuẩn từ `ml/src/p1.py`; có byte 0x80 tự nhiên,
  không chèn/sửa byte để tạo ca thử. Byte 0x80 trong transformed là hợp lệ.
- `request.i1v2.bin`: request tham chiếu đầy đủ, gồm CRC. Scale FP32 trên wire
  là mở rộng chính xác từ FP16 đã lưu, không phải scale_raw trước làm tròn.
- `logits.quantized.f32le.bin`: 5 logits host tham chiếu tuần 5 của tensor
  đã dequantize; `logits.fp32.f32le.bin`: baseline FP32 trước lượng tử hóa.

s9/s10 vốn NC, được reshape `[1,C] -> [1,C,1]` để đi trên wire; thứ tự và q
bytes không đổi. Sau unprotect mới dequantize bằng scale kênh gốc; s9 reshape
về `[1,32]` cho tail. s10 là 5 logits identity sau dequantize, không có tail_s10.
Logits theo thứ tự **N,S,V,F,Q**, không softmax; argmax hòa lấy index nhỏ nhất.
Byte-exact của q/P1 tách khỏi so sánh float và sai số lượng tử hóa với FP32.

## Xác thực và tái lập

Lấy source commit từ `vectors.json -> provenance.source_commit`, checkout đúng
commit trong clone đầy đủ hoặc hậu duệ có cùng source bindings. Hash manifest
phải lấy từ receipt bàn giao/kênh tin cậy độc lập; không tự tính hash một gói
chưa được xác thực rồi dùng nó làm anchor. Hash ZIP nằm ngoài gói trong `.sha256`.

`manifest.json` băm SHA-256 raw bytes mọi regular file trong gói ngoại trừ
chính root manifest.json. Verifier yêu cầu đúng inventory, không thiếu/thừa,
không symlink/path traversal; manifest không tự tham chiếu. Mọi path trong gói
là tương đối; có thể giải nén ở thư mục khác máy sinh.

Từ repository (Python môi trường dự án, GCC trên PATH hoặc `--compiler`):

```powershell
python -B ml/scripts/verify_week6_p1.py --package <package> --expected-manifest-sha256 <trusted-manifest-SHA256> --output <new-A.json>
python -B ml/scripts/verify_week6_output.py --package <package> --expected-manifest-sha256 <trusted-manifest-SHA256> --output <new-B.json>
```

A chạy C reference hiện có trên chính 50 vector này, không chỉ vector mẫu C.
B cần model package đã hydrate để chạy frozen reference tails; không cần chạy
KV260. Hydrate theo `ml/docs/week5_delivery_v2.md` với bốn ZIP release gốc đã
xác thực, dùng `setup_week5_delivery_v2.py --asset-cache <4-ZIP-cache>`.

```powershell
python -B ml/scripts/generate_week6_p1.py --source-commit <implementation-SHA> --output <new-parent>/mitdb-week6-p1-50-20261016-v1
python -B ml/scripts/package_week6_p1.py --package <package> --expected-manifest-sha256 <trusted-manifest-SHA256> --output <new.zip>
```

Generator từ chối source khác commit và output đã tồn tại. Không có timestamp
hoặc absolute path trong vector payload; ZIP dùng thứ tự/timestamp cố định.
Hai lần sinh từ cùng source/environment cho cùng nội dung và ZIP bytes.

## SV1 dùng ngay / giới hạn

SV1 đọc q/descriptor/nonce/key public và so transformed SHA-256 của C trên MCU
với từng file chuẩn, rồi unprotect so q raw bytes 50/50. Capture phải có
vector_index và kết quả từng ca; host C PASS chưa phải MCU PASS. Không dùng key
public và sequence bộ vector này cho BLE bench, không thay state nonce thực.

SV2 có thể dùng request chuẩn để kiểm parser/recovery và output semantics.
Accuracy/sai số tail DPU vẫn cần backend KV260 thật của SV2 và tập test chính
thức; gói validation 50 vector và host FP32 không chứng nhận DPU hoặc accuracy.
Nghiệm thu toàn tuần 6 còn phụ thuộc MCU/BLE/nonce và KV260 của nhóm.
