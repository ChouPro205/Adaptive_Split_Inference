# Shared Tools

Nơi lưu các script và công cụ dùng chung đã được nhóm thống nhất. Công cụ riêng của firmware PCA10059 vẫn nằm trong `device/scripts`.

`week4_handoff_auth.py` là policy xác thực dùng chung cho device và ML:
anchors R3/R4, các source lịch sử cố định, bộ ba source PR22 đã kiểm, payload
parity và binding báo cáo MCU R3. Lệnh hiện hành ở
[`ml/docs/week4_current_verification.md`](../ml/docs/week4_current_verification.md).
