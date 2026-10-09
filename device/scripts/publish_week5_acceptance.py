"""Publish compact technical evidence after all real Week 5 gates have passed."""
import argparse
import copy
import csv
import datetime as dt
from pathlib import Path
import subprocess
from accept_week5_mcu import read, publish, IMAGE_SOURCE
from week5_common import ROOT, need, sha, write_json
from verify_week5_package import verify_package

def publish_results(session, preparation):
    prepared = verify_package(preparation)
    result = read(session/'acceptance/week5_mcu_validation.json')
    optimized = read(session/'acceptance-O/week5_mcu_validation.json')
    normal_compare, opt_compare = copy.deepcopy(result), copy.deepcopy(optimized)
    normal_compare.pop('optimized_python'); opt_compare.pop('optimized_python')
    need(normal_compare == opt_compare, 'Normal/-O acceptance differs')
    need(result['status'] == 'SV1_WEEK5_TECHNICAL_ACCEPTANCE_PASS' and result['image_source_sha'] == IMAGE_SOURCE and
         result['preparation_snapshot_sha256'] == sha(preparation), 'Technical acceptance invalid or preparation changed')
    required = ['real-mcu-recheck','technical-acceptance','acceptance-negative-tests','package-preflight','current-gate',
                'current-policy','handoff-policy','python-quantization','historical-capture','parser-regression']
    commands = {}
    for name in required:
        for suffix in ('','-O'):
            path = session/'commands'/f'{name}{suffix}.json'
            command = read(path)
            need(command['exit_code'] == 0 and path.with_suffix('.log').exists(), f'Required acceptance/regression failed: {name}{suffix}')
            commands[name+suffix] = {**command,'receipt_sha256':sha(path),'log_sha256':sha(path.with_suffix('.log'))}
    for name in ('acceptance-tests.json','acceptance-tests-O.json'):
        test = read(session/name)
        need(test['status'] == 'PASS' and test['acceptance_tool_sha256'] == sha(ROOT/'device/scripts/accept_week5_mcu.py') and
             test['tool_sha256'] == sha(ROOT/'device/scripts/test_week5_acceptance.py'), 'Acceptance tests stale/failed')
    for name in ('parser-regression','parser-regression-O'):
        need(read(session/name/'tests.json')['status'] == 'PASS', 'Parser regression failed')
    need(result['acceptance_tooling_sha256']['device/scripts/accept_week5_mcu.py'] == sha(ROOT/'device/scripts/accept_week5_mcu.py'), 'Analysis code changed after validation')
    branch = subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    need(branch == 'dev/device-sv1','Wrong branch')
    protected = subprocess.check_output(['git','diff',IMAGE_SOURCE,'--name-only','--','device/week5','device/src','ml','contracts',
                                        'device/generated','device/CMakeLists.txt','device/Kconfig','device/overlay-week4.conf'],cwd=ROOT,text=True)
    need(not protected.strip(),'Image/model/historical inventory changed')
    output = ROOT/'results/week5'
    need(not output.exists(),'Week 5 results already exist; refuse overwrite')
    report_path = ROOT/'docs/sv1_device_week5_report.md'
    need(not report_path.exists(),'Week 5 report already exists')
    full = copy.deepcopy(result)
    full.update(validated_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat(),
                regressions={'status':'PASS','commands':commands},
                analysis_tooling_sha256={f'device/scripts/{name}':sha(ROOT/'device/scripts'/name) for name in
                    ('accept_week5_mcu.py','run_week5_acceptance.py','test_week5_acceptance.py','publish_week5_acceptance.py')},
                git_integration={'status':'PENDING_AT_REPORT_CREATION','image_source_sha':IMAGE_SOURCE,
                    'report_commit_sha':None,'merge_sha':None,'final_receipt_path':str(session/'git/git_integration_final.json')},
                decisions={'quantization':'INT8 symmetric per sample/channel over L; zero-point 0; FP16 stored scale; q uses stored FP16 expanded to FP32',
                    'i1_v1_wire_scales':'FP32 little-endian, exact expansion of stored FP16; wire implementation PENDING',
                    'i2_v1':'NCL descriptor/profile N,C,L; s9/s10 adapter L=1; inverse I2 before dequantization; firmware integration PENDING',
                    'model_splits':'s=0..10 unchanged; wire split_id requires explicit registry mapping, not assigned here',
                    'accuracy_gate':'strict drop <0.5 percentage points at every split; relative percent additionally reported'},
                limitations={'timing':'NOT_MEASURED','runtime_ram':'NOT_MEASURED','runtime_stack':'NOT_MEASURED',
                    'full_accuracy_on_dongle':'NOT_RUN','p1_c':'NOT_RUN','radio':'NOT_RUN','device_edge_integration':'NOT_RUN','i1_frozen':False})
    publish(output,full)
    compact = copy.deepcopy(full)
    compact.pop('primary_rows'); compact.pop('mixed_rows')
    compact['case_tables'] = {name:{'path':f'results/week5/{name}','sha256':sha(output/name)} for name in
                              ('validation_20x11.csv','validation_mixed.csv','tensor_sizes.csv','accuracy_offline.csv','golden_difference_analysis.json')}
    write_json(output/'week5_mcu_validation.json',compact)
    report = documentation(full,session,preparation)
    report_path.write_text(report,encoding='utf-8')
    readme = ['# SV1 tuần 5 — đã nghiệm thu kỹ thuật trên Dongle', '',
              f'Phiên `{session.name}`; source image `{IMAGE_SOURCE}`. DFU thật exit 0, MCU 220/220 primary + 16/16 mixed PASS.',
              'FP32 strict `<1e-3`, s0 bitwise, INT8/FP16 oracle và P2 tuần 3 bitwise 20/20 đều PASS. Accuracy offline đủ 8.544 × 11 đạt ngưỡng; không chạy cả tập này trên Dongle.', '',
              '- [Báo cáo cho thầy](../../docs/sv1_device_week5_report.md)',
              '- [JSON nghiệm thu và provenance](week5_mcu_validation.json)',
              '- [220 primary cases](validation_20x11.csv) và [16 mixed cases](validation_mixed.csv)',
              '- [Kích thước FP32/INT8/scales](tensor_sizes.csv)',
              '- [Accuracy offline](accuracy_offline.csv)',
              '- [Phân tích sai khác với golden SV3](golden_difference_analysis.json)', '',
              'Chỉ payload INT8 giảm đúng 4×. Tổng INT8 + scale FP16 giảm tùy split; bảng chưa gồm header/I1 wire scales.',
              'Timing, RAM/stack runtime: NOT_MEASURED. P1 C, radio và tích hợp Device–Edge chưa thực hiện; I1 chưa FROZEN.', '',
              f'Raw capture, DFU receipt, collection receipt và logs: `{session}`. Binaries/build vẫn trong `{preparation.parent}`. Các hashes nằm trong JSON.',
              'preparation.json giữ nguyên snapshot NOT_RUN/PENDING trước nạp; kết quả thật được ghi riêng.',
              f'Trạng thái tích hợp Git tại commit báo cáo này: chưa merge. PR, commit báo cáo, merge SHA và đối chiếu bốn refs được lưu sau tích hợp tại `{session / "git/git_integration_final.json"}`.',
              'Source của image đã đo luôn là SHA 51ef9c9 ở trên; commit báo cáo/merge không thay source SHA đó.', '']
    (output/'README.md').write_text('\n'.join(readme),encoding='utf-8')
    write_json(session/'technical_report_receipt.json',{'scope':'REAL_MCU_CAPTURE','status':'TECHNICAL_ACCEPTANCE_PASS',
        'image_source_sha':IMAGE_SOURCE,'preparation_snapshot_sha256':sha(preparation),
        'report_files_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in [report_path,*sorted(output.glob('*'))] if p.is_file()},
        'git_integration':'PENDING'})
    print(f'PUBLISHED TECHNICAL ACCEPTANCE: {output}; report={report_path}; Git integration PENDING')

def documentation(r,session,preparation):
    worst = max(r['accuracy_offline']['rows'],key=lambda x:x['accuracy_drop_pp'])
    lines = ['# Báo cáo SV1 tuần 5 — lượng tử hóa activation trên nRF52840 Dongle', '',
        f'Nghiệm thu kỹ thuật: **PASS**, scope **REAL_MCU_CAPTURE**, ngày {r["validated_at"][:10]} (Asia/Saigon).',
        f'Source dùng để build/nạp/đo: `{r["image_source_sha"]}`. Firmware ID `{r["firmware_binding"]["firmware_id"]}`.',
        'Source kernel CNN FP32, checkpoint, preprocessing, mapping s=0..10 và mọi tài sản/bằng chứng tuần 3–4 giữ nguyên. App tuần 5 độc lập; không build lại vì source/artifact vẫn đúng.', '',
        '| Gate | Kết quả |', '|---|---|',
        '| Preflight source/ELF/HEX/ZIP/application | PASS thường và -O |',
        f'| Nordic application USB DFU | PASS, exit 0, bootloader {r["flash"]["port"]} |',
        f'| MCU capture thật | 220/220 primary + 16/16 mixed, ứng dụng {r["collection"]["port"]} |',
        f'| FP32 finite/strict <1e-3 và s0 bitwise | PASS; max abs error {r["max_fp32_abs_error"]:.12g}; s0 20/20 bitwise |',
        '| INT8/FP16 trên chính FP32 MCU | Oracle exact 236/236, không tolerance/whitelist |',
        f'| P2 so capture MCU tuần 3 có provenance | PASS; {r["historical_p2"]["bitwise_cases"]}/20 bitwise; max error {r["historical_p2"]["max_abs_error"]} |',
        '| Checker độc lập và guard provenance | PASS thường và -O; các negative tests PASS |',
        '| Regression hiện hành/quantization/parser/capture lịch sử | PASS thường và -O |',
        '| Accuracy offline | 8.544 × 11, baseline 8.393; mọi split strict drop <0,5 pp |',
        '| Timing / RAM / stack runtime | NOT_MEASURED |', '',
        'Các trường hash/source/command/exit-code trong JSON nối snapshot chuẩn bị → REAL_USB_DFU → collection receipt → capture → checker thường/-O → P2 lịch sử → nghiệm thu.',
        f'DFU UTC: `{r["flash"]["timestamp_utc"]}`; collection UTC: `{r["collection"]["timestamp_utc"]}`.',
        'Bootloader USB `VID_1915/PID_521F`; CDC `VID_2FE3/PID_0004`, product `Adaptive Split Inference SV1`. Cổng được xác định từ thiết bị thực tế mỗi giai đoạn.', '',
        '## Sai khác số học đã phân tích', '',
        'Mọi byte INT8 MCU khớp cả golden SV3. Ba scale FP16 khác golden tại s10 được kiểm lại trên capture thật; không sử dụng whitelist từ Host C.',
        '| Mẫu | Kênh | Raw scale golden FP32 | Raw scale MCU FP32 | Midpoint FP16 | Bits golden → MCU |', '|---:|---:|---:|---:|---:|---|']
    for case in r['golden_difference_analysis']:
        for d in case['scale_details']:
            lines.append(f'| {case["sample_index"]} | {d["channel"]} | {d["golden_raw_scale_fp32"]:.12g} | {d["mcu_raw_scale_fp32"]:.12g} | {d["fp16_rounding_midpoint"]:.12g} | 0x{d["golden_scale_bits"]:04x} → 0x{d["mcu_scale_bits"]:04x} |')
    lines.extend(['', 'Sai số head FP32 làm raw scale đi qua midpoint FP16. Python reference trên đúng activation MCU tạo chính bytes/bits MCU đã gửi. Unexplained mismatch = 0.', '',
                  '## Accuracy toàn bộ tập test — offline', '',
                  'Tái sử dụng kết quả head FP32 chuẩn → quantization/dequantization C → tail frozen: source hashes, checkpoint, dataset receipts và tail đều không đổi. Không dùng 20 mẫu thay tập accuracy và không tuyên bố chạy 8.544 mẫu trên Dongle.',
                  '| s | FP32 đúng/8544 | INT8+FP16 đúng/8544 | Accuracy (%) | Giảm (pp) | Giảm tương đối (%) |', '|---:|---:|---:|---:|---:|---:|'])
    for a in r['accuracy_offline']['rows']:
        lines.append(f'| {a["split_point_s"]} | {a["correct_fp32"]} | {a["correct_int8_fp16"]} | {a["accuracy_int8_fp16_percent"]:.6f} | {a["accuracy_drop_pp"]:.6f} | {a["accuracy_drop_relative_percent"]:.6f} |')
    lines.extend(['', f'Baseline 8393/8544 = 98,232678%. Worst s{worst["split_point_s"]}: giảm {worst["accuracy_drop_pp"]:.6f} pp; giảm tương đối {worst["accuracy_drop_relative_percent"]:.6f}%. s5 cải thiện nên giữ drop âm.', '',
                  '## Kích thước tensor và scales offline', '',
                  '| s | Shape | FP32 B | INT8 B | FP16 scale B | Tổng B | Giảm tổng (%) |', '|---:|---|---:|---:|---:|---:|---:|'])
    for s in r['tensor_sizes']:
        lines.append(f'| {s["split"]} | {s["shape"]} {s["layout"]} | {s["fp32_bytes"]} | {s["int8_payload_bytes"]} | {s["fp16_scale_bytes"]} | {s["int8_plus_fp16_bytes"]} | {s["total_reduction_percent"]:.6f} |')
    lines.extend(['', 'FP32 = 4 × elements; INT8 = elements; scale FP16 = 2 × channels. Chỉ payload INT8 giảm đúng 4×; tổng cộng scale giảm 25%–74,861111% tùy split. Chưa tính header hoặc wire I1.', '',
                  '## Quyết định hiện hành và giới hạn', '',
                  '- INT8 symmetric per sample/channel trên L, zero-point=0, q trong [-127,127]; scale lưu FP16; q dùng scale_effective đọc lại từ FP16. FP32 và FP16 đều làm tròn nearest ties-to-even theo reference.',
                  '- I1 v1 khi triển khai: scales FP32 little-endian, là giá trị FP16 đã lưu mở rộng chính xác sang FP32. Wire protocol giữ nguyên; I1 chưa FROZEN và Device–Edge chưa PASS.',
                  '- I2/1: NCL, descriptor/profile N,C,L; s9/s10 thêm L=1; đảo I2 trước dequantize. Model s=0..10 giữ nguyên; wire split_id phải có mapping registry rõ ràng, chưa gán trong tuần này.',
                  '- Accuracy chính: strict giảm <0,5 điểm phần trăm mỗi split; mức giảm tương đối là thông tin bổ sung.',
                  '- Không có BENCH; timing và RAM/stack runtime NOT_MEASURED. Không lấy số tuần 4 thay cho tuần 5. PPK2, radio, P1 C, KV260 và tuần 6 chưa bắt đầu.', '',
                  '## Hiện vật và các SHA độc lập', '',
                  f'Snapshot trước nạp giữ nguyên `{preparation}`; SHA256 `{r["preparation_snapshot_sha256"]}`; trạng thái bên trong vẫn NOT_RUN/PENDING. Kết quả thật nằm trong receipts/báo cáo riêng.',
                  f'Phiên raw/logs/receipts: `{session}`. Capture SHA256 `{r["evidence_sha256"][str(session/"week5_capture.txt")]}`.',
                  f'P2 cũ được pin vào tree `{IMAGE_SOURCE}`, package v2 manifest `{r["historical_p2"]["manifest_sha256"]}`, capture `{r["historical_p2"]["capture_sha256"]}` và anchor báo cáo R3 đã chấp nhận.', ''])
    for name in ('elf','hex','zip'):
        entry = r['artifacts'][name]
        lines.append(f'- {name.upper()}: `{entry["path"]}`; SHA256 `{entry["sha256"]}`.')
    lines.extend([f'- Application trong ZIP: SHA256 `{r["application"]["sha256"]}`; {r["application"]["bytes"]} B.', '',
                  'Bảng đầy đủ 220 case, 16 mixed case, kích thước, accuracy và JSON provenance nằm tại `results/week5/`.',
                  f'Commit báo cáo và merge SHA được ghi riêng sau tích hợp trong `{session/"git/git_integration_final.json"}`. Tại thời điểm tạo commit báo cáo, tích hợp Git còn PENDING; không thay image source SHA bằng report/merge SHA.', ''])
    return '\n'.join(lines)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--preparation',type=Path,required=True)
    a = p.parse_args()
    publish_results(a.session.resolve(),a.preparation.resolve())
