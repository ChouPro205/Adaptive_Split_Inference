# Week 6 fresh evidence

Xem [báo cáo bàn giao](../../docs/week6_p1_delivery.md).

`final/` là các run A+B/hồi quy/tái lập mới. Lượt `generate` ban đầu exit 1 do typo SHA nền trong code mới, được giữ nguyên; `generate-fixed` tại 766a3cf exit 0. Hai `cli_negative_*` exit 1 là expected rejection. Không relabel receipt tuần 5.

`delivery-assets.json` ghi checksum/size; `release-publication.json` xác nhận upload và download byte-identical. Delivery commit chứa file này là hậu duệ của implementation, không tự pin chính commit chứa metadata.
