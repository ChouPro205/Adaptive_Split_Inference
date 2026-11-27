S0c v1: định nghĩa S0 nén chuẩn (gom 46 mẫu + Rice). SV1 lập ngày 25/11/2026.

Đây là định nghĩa đã dùng trong phép thử nén 20/11 (codec_probe.py, SHA 2a538a34…), tách thành mã tham chiếu chỉ dùng numpy. Mã tham chiếu là chuẩn: thiết bị (C) và edge phải cho đúng các đầu ra của nó trên bộ golden.

File
- s0c_v1_ref.py: mã tham chiếu và đặc tả (docstring, bước 1–8). Hàm encode() cho phía thiết bị, decode() cho phía edge.
- s0c_v1_golden20.npz / .json: 20 nhịp golden của gói A (luật chọn ghi trong JSON). Gồm x (360 mẫu FP32 đã chuẩn hóa), 46 giá trị sau gom, q INT8, scale FP16, byte Rice (hex), 46 giá trị sau giải lượng tử, 360 mẫu khôi phục.
- s0c_v1_check_ds1val.json: kết quả kiểm trên 9.523 nhịp DS1 validation.
- build_s0c_v1.py, codec_probe.py, check_wire.py: để tái tạo. Đặt bốn file .py vào cùng một thư mục sâu ba cấp dưới gốc repo (ví dụ ml/provenance/s0c-v1/), rồi chạy từ gốc repo:
  ml/.venv/Scripts/python.exe -B -X utf8 ml/provenance/s0c-v1/build_s0c_v1.py --archive <SV3_M1_V4_GRID_RESULT_20261103.zip> --out <thư mục mới>
  Đã chạy lại theo đúng cách này: ba file đầu ra trùng từng byte.

Kết quả kiểm (DS1 validation, 4 bản ghi, 9.523 nhịp; DS2 không mở)
- So với đường PyTorch của phép thử 20/11: 46 giá trị sau gom, q, byte Rice và 360 mẫu khôi phục trùng từng bit ở 9.523/9.523 nhịp; giải mã Rice khôi phục đúng q ở 9.523/9.523 nhịp.
- Macro-F1 của C5 (checkpoint A, SHA fcf3f846…) trên 360 mẫu khôi phục: 0,568057, bằng đúng số của phép thử. Nhãn trùng 9.523/9.523.
- Thân Rice: trung bình 36,44 B, p95 41 B, tối đa 44 B (chưa tính scale FP16 2 B và phần đầu khung I1).

Dùng cho protocol tấn công (Kỳ Anh)
- Gắn SHA-256 của s0c_v1_ref.py và hai file golden (xem SHA256SUMS.txt) vào s0c_definition trước khi khóa.
- Kiểm golden: x trong s0c_v1_golden20.npz phải bằng golden/z_s0.npy[:, 0, :] của gói A. Máy SV1 không có bản giải nén của gói A nên chưa kiểm được bước này; nếu lệch thì dừng và báo SV1.
- Tensor kẻ tấn công thấy ở S0c: 46 giá trị sau giải lượng tử (decode()[0]); x_c là 360 mẫu khôi phục (decode()[1]).
- C0c: cộng nhiễu vào 46 giá trị sau bước 2 (reduce46), rồi làm tiếp bước 3–4 (quantize, rice_encode). Số byte Rice ở mỗi mức nhiễu lấy bằng len(rice_encode(q)).

Dùng cho edge (Trung)
- decode() là bộ giải chuẩn cho kiểu payload S0c. Kiểu payload và vị trí của scale trong khung I1 chốt trong contract I1 (SV1 + SV2).
- codec_probe.py cũng chứa bộ nén S1 cố định đã thử ngày 20/11 (s1_basis, gom 23 bin mỗi kênh, 2 kênh, 46 B): dùng để đo thời gian giải mã + tail S1 cho cổng K, không phải payload chính thức.
