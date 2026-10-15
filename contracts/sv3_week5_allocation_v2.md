# Allocation ASI/MIT-BIH — quyết định hiện hành

Ngày 15/10/2026 (Asia/Saigon), Lê Hải Châu, trưởng nhóm và người có quyền quyết
định cuối cùng, phê duyệt allocation trong testbed nội bộ ASI/MIT-BIH và trực tiếp
ủy quyền Codex ghi hồ sơ, tích hợp, kiểm thử, push PR25 và merge khi các gate đạt.
Policy có version `asi-project-lead/1` thay policy hai người của approval schema v1.
Verifier v2 và registry baseline giữ nguyên; entrypoint final là
`ml/scripts/verify_week5_delivery_v3.py`, không thay exit2 lịch sử bằng PASS.

Revision chung Device/Edge: `mitdb-week5-i2-registry-v1-r1`.
Model/version `mitdb_week2_cnn_v1`, checkpoint
`9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.
Model profile `1296651265`, key label `65537`, sender Device SV1 `131073`.

| Split | Wire ID | Thực thi |
|---|---:|---|
| s0 | 256 | Device head / Edge tail |
| s1 | 257 | Device head / Edge tail |
| s2 | 258 | Device head / Edge tail |
| s3 | 259 | Device head / Edge tail |
| s4 | 260 | Device head / Edge tail |
| s5 | 261 | Device head / Edge tail |
| s6 | 262 | Device head / Edge tail |
| s7 | 263 | Device head / Edge tail |
| s8 | 264 | Device head / Edge tail |
| s9 | 265 | Device head / Edge tail |
| s10 | 266 | Device-only; reference identity/empty-tail; không có tail_s10 |

Ceilings hai phía: INT8 payload 5760 B; C64; FP16 scale array128 B; FP32-LE
scale array256 B; metadata per-channel đầy đủ516 B (quant_count/scales/zero-points).
I1 v2 protected packet6380 B là planning budget. Không suy ra packet buffer/parser/
transport đã nghiệm thu hoặc Device hỗ trợ trần I2 32768 B.

Nonce design: `sender_id:uint32_le || sequence:uint64_le`, sequence khởi đầu1;
persist/reserve trước phát, reboot bỏ range chưa dùng, retry giữ nguyên bytes;
mất bảo đảm persistence thì dừng tới khi provisioning key/sender mới phù hợp
(đổi nhãn key_id không đủ); hết uint64 phải rotate. Runtime provisioning,
persistence/reboot và P1 transmission chưa nghiệm thu/cho phép bởi hồ sơ này.
Không cấp production/hệ thống ngoài nhóm, không tuyên bố I1 FROZEN.

Trung chỉ được ghi là xác nhận kỹ thuật Edge có điều kiện do Châu cung cấp:
scope model/profile/revision trên, Edge tails s0..s9, s10 empty-tail, các ceiling
riêng và runtime còn mở. Không khẳng định Trung/Kỳ Anh ký hoặc kiểm độc lập hash
file cuối. Approval JSON do Codex tạo theo ủy quyền; không phải chữ ký mật mã hay
bằng chứng Châu tự chạy hash thủ công. Không chứa khóa bí mật; execution dùng public test key.

Hai file dùng UTF-8 không BOM, indent2, LF và một newline cuối, IDs decimal integers:

- [Registry](sv3_week5_approved_registry_v2.json), raw SHA256
  `79392b6db73cde6d83eadb1f265f14102888ebdbf8ea1b72b6c127c5566eed24`.
- [Approval](sv3_week5_allocation_approval_v2.json), raw SHA256
  `a84b5caf89ffb7f8e11be2b308e2d4e1947e4d4f7ed291c47df083d0e15c7a7d`.

Approval ràng buộc bytes registry; registry không tự chứa hash. Khi dùng CLI,
approval hash phải đối chiếu anchor trong hồ sơ này. Verifier không chứng minh
chữ ký người dùng; nó kiểm đúng quyết định được version control và anchor đã pin.

Sau setup portable v2 bằng bốn ZIP gốc, dùng venv dự án và output mới repo-relative
(có thể dùng `.cache/` ignored). Chạy full runner v2 để thu science receipts trên
toàn source tree hiện tại; kết quả `BLOCKED/2` chỉ mô tả baseline lịch sử.
Chạy `test_week5_allocation_v3.py` thường/-O; `verify_week5_registry_v3.py` với
`--registry`, `--approval`, `--expected-approval-sha256` trên và `--output` mới.
Qua logger `run_week5_logged_v2.py`, đặt tên receipt `allocation_policy`/`allocation_policy_O`,
`approved_real`, `preflight`/`preflight_O`, `sv1_acceptance`/`sv1_acceptance_O`.
Preflight gọi `device/scripts/verify_week5_package.py --preparation <original-preparation.json>`;
acceptance gọi `device/scripts/accept_week5_mcu.py --preparation <original-preparation.json>
--session <original-session> --output <evidence>/sv1_acceptance[_O]`.
Logger phải nhận `--result-path` cho approved real và acceptance outputs.

```powershell
python -B ml/scripts/verify_week5_delivery_v3.py --evidence .cache/final --portable .cache/portable --registry contracts/sv3_week5_approved_registry_v2.json --approval contracts/sv3_week5_allocation_approval_v2.json --expected-approval-sha256 a84b5caf89ffb7f8e11be2b308e2d4e1947e4d4f7ed291c47df083d0e15c7a7d --preparation D:/HUST/ASI_week5_prepare/20261009-sv1-prepare01/preparation.json --session D:/HUST/ASI_week5_mcu/20261009-212416 --output .cache/final-result.json
```

Final exit0=PASS, exit1=FAIL, exit2=BLOCKED do thiếu dữ liệu. Không có approval không
thể PASS. Final kiểm portable dependencies/preservation/source/log/result hashes,
P1 10000, real220, accuracy8544×11 strict<0,5pp, authority/registry/descriptor,
approved real220 và bốn gate SV1 mới thường/-O. Accuracy C và MCU/capture/DFU gốc
là authenticated reuse, không gọi là đo mới. Timing/RAM/stack chưa đo; tuần6 firmware chưa chạy.
