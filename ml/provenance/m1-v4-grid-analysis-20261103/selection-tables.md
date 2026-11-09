## Bảng 1. Sáu cấu hình (mean và SD trên 3 seed, SD mẫu ddof=1)

| Cấu hình | Chế độ | cap | lr | Mean macro-F1 (thô) | Mean làm tròn 4 | SD ddof=1 | Seed triển khai | Gate N / V / S tại seed triển khai |
|---|---|---:|---:|---:|---:|---:|---:|---|
| C0 | weighted CE | 10 | 0,001 | 0,477375 | 0,4774 | 0,043629 | 20261030 | đạt / đạt / đạt |
| C1 | weighted CE | 10 | 0,0003 | 0,510199 | 0,5102 | 0,059670 | 20261030 | đạt / đạt / đạt |
| C2 | weighted CE | 50 | 0,001 | 0,458706 | 0,4587 | 0,080602 | 20261101 | đạt / đạt / đạt |
| C3 | weighted CE | 50 | 0,0003 | 0,508123 | 0,5081 | 0,072530 | 20261101 | đạt / đạt / đạt |
| C4 | K-balanced sampler | — | 0,001 | 0,493990 | 0,4940 | 0,097512 | 20261101 | đạt / đạt / đạt |
| **C5** (chọn) | K-balanced sampler | — | 0,0003 | 0,512870 | 0,5129 | 0,088619 | 20261101 | đạt / đạt / đạt |

## Bảng 2. 18 slot: epoch chọn, macro-F1, gate N/V/S của cả 3 seed

Số liệu trên toàn bộ validation DS1 cố định (9.523 nhịp), checkpoint của epoch được chọn, giá trị chưa làm tròn. ΔN = tỉ lệ dự đoán N − tỉ lệ N thật (gate N: ΔN ≤ 0,10). Chỉ gate tại seed triển khai quyết định chọn cấu hình; gate của hai seed còn lại chỉ để báo.

| Cấu hình | Seed | Epoch chạy | Epoch chọn | Macro-F1 K (thô) | Làm tròn 4 | N | V | S | ΔN | Se S | +P S | Se V | +P V |
|---|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|
| C0 | 20261030 ★ | 13 | 3 | 0,527743 | 0,5277 | đạt | đạt | đạt | 0,0282 | 0,2965 | 0,3148 | 0,6932 | 0,9444 |
| C0 | 20261031 | 23 | 13 | 0,453037 | 0,4530 | đạt | đạt | **không** | 0,0191 | 0,1977 | 0,1210 | 0,5637 | 0,7818 |
| C0 | 20261101 | 16 | 6 | 0,451344 | 0,4513 | đạt | đạt | **không** | -0,1214 | 0,5233 | 0,0589 | 0,6016 | 0,9557 |
| C1 | 20261030 ★ | 16 | 6 | 0,576124 | 0,5761 | đạt | đạt | đạt | 0,0171 | 0,3605 | 0,4460 | 0,7729 | 0,8992 |
| C1 | 20261031 | 23 | 13 | 0,459888 | 0,4599 | đạt | **không** | **không** | -0,0292 | 0,1686 | 0,2302 | 0,6145 | 0,4794 |
| C1 | 20261101 | 33 | 23 | 0,494587 | 0,4946 | đạt | đạt | đạt | -0,0525 | 0,4593 | 0,3305 | 0,7082 | 0,5163 |
| C2 | 20261030 | 21 | 11 | 0,371634 | 0,3716 | đạt | **không** | **không** | -0,1284 | 0,0233 | 0,0635 | 0,7380 | 0,3279 |
| C2 | 20261031 | 14 | 4 | 0,473772 | 0,4738 | đạt | đạt | **không** | -0,0720 | 0,2035 | 0,0621 | 0,7779 | 0,6334 |
| C2 | 20261101 ★ | 29 | 19 | 0,530712 | 0,5307 | đạt | đạt | đạt | -0,0342 | 0,3488 | 0,1386 | 0,7839 | 0,8444 |
| C3 | 20261030 | 35 | 25 | 0,425926 | 0,4259 | đạt | đạt | **không** | -0,2249 | 0,1686 | 0,1648 | 0,7829 | 0,5535 |
| C3 | 20261031 | 33 | 23 | 0,535313 | 0,5353 | đạt | đạt | đạt | -0,0131 | 0,7267 | 0,2551 | 0,6165 | 0,9794 |
| C3 | 20261101 ★ | 31 | 21 | 0,563129 | 0,5631 | đạt | đạt | đạt | -0,0066 | 0,5756 | 0,2612 | 0,7082 | 0,9582 |
| C4 | 20261030 | 13 | 3 | 0,382495 | 0,3825 | đạt | **không** | đạt | -0,2524 | 0,2907 | 0,2128 | 0,9233 | 0,2900 |
| C4 | 20261031 | 19 | 9 | 0,536131 | 0,5361 | đạt | đạt | **không** | 0,0122 | 0,1279 | 0,2037 | 0,8157 | 0,8835 |
| C4 | 20261101 ★ | 18 | 8 | 0,563343 | 0,5633 | đạt | đạt | đạt | 0,0035 | 0,5233 | 0,2848 | 0,7699 | 0,9885 |
| C5 | 20261030 | 27 | 17 | 0,410659 | 0,4107 | đạt | **không** | đạt | -0,2243 | 0,2616 | 0,4091 | 0,9203 | 0,2882 |
| C5 | 20261031 | 33 | 23 | 0,559728 | 0,5597 | đạt | đạt | đạt | 0,0044 | 0,2849 | 0,2882 | 0,8327 | 0,8922 |
| C5 | 20261101 ★ | 14 | 4 | 0,568222 | 0,5682 | đạt | đạt | đạt | 0,0114 | 0,4070 | 0,3004 | 0,7709 | 0,9872 |

★ = seed triển khai của cấu hình (macro-F1 làm tròn 4 cao nhất, hòa thì seed nhỏ hơn).

## Bảng 3. SHA-256 checkpoint được chọn của 18 slot

Đường dẫn tương đối từ gốc repo, nằm trong `ml/data/` (bị Git bỏ qua, không có trong ZIP). Danh sách đầy đủ dạng `sha256sum -c`: `selected-checkpoints.sha256`.

| Slot | Vai trò | Checkpoint | Bytes | SHA-256 |
|---|---|---|---:|---|
| C0-seed20261030 | — | `C0-seed20261030/attempt-1/checkpoint-epoch-003.pt` | 446457 | `955a00626e1521dd39c4ad247656aa26a39699ce9c43acb7e42aa06609ac492d` |
| C0-seed20261031 | — | `C0-seed20261031/attempt-1/checkpoint-epoch-013.pt` | 446457 | `42416c5a9923868024e29d1ef3f54891d1a30849aee3ac60eb355ae2ef624af9` |
| C0-seed20261101 | — | `C0-seed20261101/attempt-1/checkpoint-epoch-006.pt` | 446457 | `12dd8643eb9afb48c239c682aaa40fc05340698dba41bd61bc730234e185a273` |
| C1-seed20261030 | — | `C1-seed20261030/attempt-1/checkpoint-epoch-006.pt` | 446457 | `35e2ff1df486c9c6acec9cfb78d0274f1446190cc72f0b8b696c8f7bd93a87c8` |
| C1-seed20261031 | — | `C1-seed20261031/attempt-1/checkpoint-epoch-013.pt` | 446457 | `36f0faa27fabedbd5372a1dde8a6057164c1e85ae28fa666a052fbe20515e45a` |
| C1-seed20261101 | — | `C1-seed20261101/attempt-1/checkpoint-epoch-023.pt` | 446457 | `1e55ca45dbdb4ea63cdd5f551635ff814ffe2ccbe3273b81ca41f01ece06acf8` |
| C2-seed20261030 | — | `C2-seed20261030/attempt-1/checkpoint-epoch-011.pt` | 446457 | `7be3931e3864aefa448d89bad9c8458b25d4d103cc84fd3d3e29222aaaa83317` |
| C2-seed20261031 | — | `C2-seed20261031/attempt-1/checkpoint-epoch-004.pt` | 446457 | `4ab3c83cd3fde46162fd67445b7a442d7997362d5398fa3274d83eb297ec9a05` |
| C2-seed20261101 | — | `C2-seed20261101/attempt-1/checkpoint-epoch-019.pt` | 446457 | `b0f0e47fc2b6fff3b7772001ef15364b1bb358a10857f71f5d7a7fd4c713a732` |
| C3-seed20261030 | — | `C3-seed20261030/attempt-1/checkpoint-epoch-025.pt` | 446457 | `5e84dd781526640aa44fe53d714664b5c1e058a2cf6994b0dd5cb5a379a84558` |
| C3-seed20261031 | — | `C3-seed20261031/attempt-1/checkpoint-epoch-023.pt` | 446457 | `ae0d62e289fd722865e4c958121a7ae8ba750e57ccfacc1aefb6e9a74e905985` |
| C3-seed20261101 | — | `C3-seed20261101/attempt-1/checkpoint-epoch-021.pt` | 446457 | `009d4d1b5364bfdd3771314768a50a8629cae367c42dcd7eef8d651d743e906e` |
| C4-seed20261030 | — | `C4-seed20261030/attempt-1/checkpoint-epoch-003.pt` | 446457 | `409720fba11b6ab007344646feae1735c63f0cda5fc7a2716249f7e2a1292671` |
| C4-seed20261031 | — | `C4-seed20261031/attempt-1/checkpoint-epoch-009.pt` | 446457 | `e3aeceaaf3db93429bf272e9b0be8ead8504b2988ede1121fc1722f088cb3572` |
| C4-seed20261101 | — | `C4-seed20261101/attempt-1/checkpoint-epoch-008.pt` | 446457 | `c7a546fd73dcc591ab059e0d8e3f95270a26397d65e0781393b1b8993af2bcd2` |
| C5-seed20261030 | seed của cấu hình chọn | `C5-seed20261030/attempt-1/checkpoint-epoch-017.pt` | 446457 | `fc60aa7092f81fc53a95a6f7fc83704df51daf631a0f722100ca31e50129408e` |
| C5-seed20261031 | seed của cấu hình chọn | `C5-seed20261031/attempt-1/checkpoint-epoch-023.pt` | 446457 | `19fe7a4a9136d4f5cbdd7683705b14efd5c7950129d7a6ed9f989111cebf0f8f` |
| C5-seed20261101 | **checkpoint triển khai** | `C5-seed20261101/attempt-1/checkpoint-epoch-004.pt` | 446457 | `fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c` |
