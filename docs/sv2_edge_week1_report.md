# Báo cáo công việc Week 1 – Máy chủ biên (KV260)


## 1. Mục tiêu Week 1

Theo kế hoạch gốc, Week 1 của vai trò SV2 (Edge) là giai đoạn khởi tạo phần cứng KV260: ghi thẻ SD Ubuntu, boot board, cài `xlnx-config`, bật SSH, đặt IP tĩnh. Trên thực tế, phần cứng KV260 đã được GVHD chuẩn bị và cấu hình sẵn trước khi giao cho nhóm, nên các bước thiết lập phần cứng nêu trên không phát sinh công việc trong tuần này. Mục tiêu thực tế của Week 1 được điều chỉnh thành:

1. Đọc và nắm vững tài liệu nền tảng của dự án để hiểu kiến trúc hệ thống và phạm vi công việc của vai trò SV2.
2. Chuẩn bị công cụ phần mềm cần thiết cho việc thao tác với KV260 ở các tuần tiếp theo.
 

## 2. Bối cảnh: vì sao phạm vi công việc khác kế hoạch gốc

- KV260 được nhận ở trạng thái đã cài hệ điều hành và cấu hình mạng cơ bản do GVHD thực hiện trước.
- Do đó các mục "ghi thẻ SD", "boot KV260", "cài xlnx-config", "bật SSH/đặt IP tĩnh" trong kế hoạch Tuần 1 gốc không có công việc thực hiện tương ứng trong tuần này.


## 3. Công việc đã thực hiện

- Đọc tài liệu tổng quan dự án Adaptive Split Inference (mục tiêu, kiến trúc thiết bị–edge–controller).
- Đọc tài liệu quy ước làm việc và định dạng dữ liệu dùng chung (ASI-CONVENTION-001): cấu trúc thư mục repository, quy ước commit/PR, các hợp đồng giao diện I1–I4.
- Đọc sơ đồ kiến trúc hệ thống, nắm luồng dữ liệu: Thiết bị (SV1) → Kênh truyền BLE → Máy chủ biên (SV2) → Bộ điều khiển.
- Đọc hướng dẫn công việc hàng tuần dành cho vai trò SV2, nắm lộ trình 24 tuần và các mốc nghiệm thu (Gate G2, G5...).

Nội dung chính đã nắm được:
- Phạm vi sở hữu của SV2: toàn bộ khối Máy chủ biên (nhận gói tin, dequantize, unprotect, chạy Tail DNN trên DPU, quản lý hàng đợi, publish trạng thái, trả kết quả).
- Hai hợp đồng giao diện liên quan trực tiếp đến SV2: I1 (định dạng gói tin Device ↔ Edge) và I4 (thông điệp trạng thái Edge → Device/Controller qua MQTT).
- Quy tắc làm việc chung: không push trực tiếp vào `main`, mọi thay đổi vào `protocol/` phải có review của bên liên quan, mỗi commit theo định dạng `<type>(<scope>): <mô tả>`.


## 4. Kết quả

- Đã hiểu rõ kiến trúc tổng thể của hệ thống và vị trí công việc của vai trò SV2 trong đó, làm nền tảng để triển khai Week 2 (cài Kria-PYNQ, chạy notebook DPU mẫu, phối hợp chốt Hợp đồng I1 cùng SV1).
- Máy cá nhân đã sẵn sàng công cụ SSH (PuTTY) để thao tác với KV260 khi cần trong Week 2.


## 5. Hạn chế và lưu ý

- Các bước thiết lập phần cứng ban đầu (ghi thẻ SD, cấu hình xlnx-config, SSH, IP tĩnh) không do SV2 tự thực hiện trong tuần này.
- Báo cáo Week 1 tập trung vào phần đọc hiểu tài liệu và chuẩn bị công cụ; chưa có sản phẩm code hoặc số liệu đo lường.


## 6. Hướng tuần 2

- Cài đặt Vitis AI 3.5 bằng Docker trên máy tính cá nhân.
- Thử lượng tử hóa (quantize) một mô hình nhỏ để làm quen với bước đầu của luồng công cụ: PyTorch → quantize → compile ra file .xmodel.

