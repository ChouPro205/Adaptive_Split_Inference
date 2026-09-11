# Adaptive Split Inference

Adaptive Split Inference là dự án nghiên cứu hệ thống suy luận thích nghi được phân chia giữa thiết bị đầu cuối và edge. Mục tiêu là đo lường, lựa chọn và thực thi điểm chia mô hình phù hợp với tài nguyên, độ trễ, năng lượng và điều kiện truyền thông.

## Cấu trúc và trách nhiệm

- `device`: firmware nRF52840 Dongle PCA10059 của Châu/SV1.
- `edge`: KV260, Tail DNN, queue và server của SV2.
- `ml`: mô hình, lượng tử hóa và protection của SV3.
- `contracts`: hợp đồng giao diện I1-I4, packet format và test vector dùng chung.
- `experiments`: cấu hình thí nghiệm, dữ liệu đo đã xử lý và kết quả.
- `docs`: tài liệu kỹ thuật, tiến độ và báo cáo.
- `tools`: công cụ dùng chung của nhóm.

Thiết bị đầu cuối hiện tại là Nordic nRF52840 Dongle PCA10059 revision 2.1.1. Firmware dùng nRF Connect SDK v3.4.0 LTS với board target `nrf52840dongle/nrf52840`; không dùng biến thể `/bare`.

Mỗi thành viên chỉ chỉnh sửa phần thuộc trách nhiệm của mình và phối hợp thay đổi giao diện qua `contracts`. Không commit build cache, dataset lớn, model artifact lớn, file khóa, `.env` hoặc thông tin bí mật.

Project này không tự động flash thiết bị. Quy trình nạp firmware phải được thực hiện ở một bước riêng sau khi artifact được kiểm tra.
