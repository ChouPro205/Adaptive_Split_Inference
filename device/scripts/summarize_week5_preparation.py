"""Bind all completed gates to exact source/build/package; archive evidence externally."""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
from week5_common import ROOT, authenticate, firmware_binding, source_hashes, sha, need, write_json
from verify_week5_package import package_metadata, verify_artifacts

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def summarize(output, evidence, refresh_git=False):
    preparation_path = output / 'preparation.json'
    if refresh_git:
        data = verify_artifacts(read(preparation_path))
        need(not git('status','--porcelain'), 'Commit and clean working tree required')
        for name in data['source_sha256']:
            if git('ls-files', '--', name):
                raw = subprocess.check_output(['git','show',f'HEAD:{name}'], cwd=ROOT)
                need(raw.replace(b'\r\n',b'\n') == (ROOT/name).read_bytes().replace(b'\r\n',b'\n'), f'Committed content differs: {name}')
        data['verified_source_commit'] = git('rev-parse','HEAD')
        data['committed_source_matches_tested_bytes'] = True
        data['working_tree'] = 'CLEAN'
        data['push'] = 'VERIFIED' if git('rev-parse','origin/dev/device-sv1') == data['verified_source_commit'] else 'PENDING'
        write_json(preparation_path, data)
        report(output, data)
        return
    need(not preparation_path.exists(), 'Summary exists; preserve it or use --refresh-git after commit')
    _, proof, history = authenticate()
    need(git('branch','--show-current') == 'dev/device-sv1', 'Wrong branch')
    need(not git('diff','--name-only','--','ml','results','contracts','tools','device/CMakeLists.txt','device/Kconfig','device/overlay-week4.conf','device/src'), 'Protected historical sources changed')
    subprocess.run(['git','diff','--check'], cwd=ROOT, check=True)
    hashes = source_hashes()
    required = ['current-gate','current-gate-O','week4-host','quantization-tests','quantization-tests-O',
                'week5-host','week5-host-O','accuracy','capture-tests','capture-tests-O','checker-fixture','checker-fixture-O','package-tests','package-tests-O',
                'memory-audit','powershell-syntax','collector-dependency']
    for name in ['current-regressions','current-policy','handoff-policy','python-quantization','historical-capture','historical-tamper']:
        required.extend([name,name+'-O'])
    commands = {}
    for name in required:
        path = evidence/'commands'/f'{name}.json'
        data = read(path)
        need(data['exit_code'] == 0 and path.with_suffix('.log').exists(), f'Required command not PASS: {name}')
        commands[name] = {**data, 'log_sha256':sha(path.with_suffix('.log'))}
    for name in ['binding','build','memory','pkg-generate','pkg-display']:
        data = read(output/f'{name}.command.json')
        need(data['exit_code'] == 0, f'Build/package command not PASS: {name}')
        commands[name] = {**data, 'log_sha256':sha(output/f'{name}.log')}
    reports = {}
    for name, rel in [('unit','unit/tests.json'),('unit-O','unit-O/tests.json'),('host','host/week5_host.json'),
                     ('host-O','host-O/week5_host.json'),('accuracy','accuracy/evaluation.json'),
                     ('capture-tests','capture-tests/tests.json'),('capture-tests-O','capture-tests-O/tests.json'),
                     ('package-tests','package-tests.json'),('package-tests-O','package-tests-O.json')]:
        data = read(evidence/rel)
        need(data['status'] == 'PASS' and data['source_sha256'] == hashes, f'Stale or failed gate: {name}')
        reports[name] = {'relative_path':rel, 'sha256':sha(evidence/rel)}
    host, accuracy = read(evidence/'host/week5_host.json'), read(evidence/'accuracy/evaluation.json')
    need(host['layer_a_exact_cases'] == 220 and host['layer_b_oracle_exact_cases'] == 220 and host['unexplained_mismatches'] == 0, 'Host gate incomplete')
    need(accuracy['num_samples'] == 8544 and accuracy['splits'] == 11 and accuracy['baseline_correct'] == 8393 and accuracy['c_oracle_exact_cases'] == 93984 and
         all(r['accuracy_drop_pp'] < .5 for r in accuracy['rows']), 'Accuracy gate incomplete')
    w4 = read(evidence/'week4-host/week4_host_validation.json')
    need(w4['status']=='PASS' and w4['primary_tensors']==220 and w4['reverse_order_tensors']==220 and w4['week3_p2_bitwise_samples']==20, 'Historical host gate incomplete')
    binding = read(output/'generated/binding.json')['firmware_binding']
    need(binding == firmware_binding(), 'Build binding stale')
    memory = read(evidence/'memory-audit/memory.json')
    need(memory['status'] == 'PASS', 'Memory gate failed')
    need(memory['audit_source_sha256'] == sha(ROOT/'device/scripts/inspect_week5_memory.py'), 'Final memory audit source changed')
    for name, expected in memory['artifacts_sha256'].items():
        need(sha(output/'build/zephyr'/name) == expected, 'Audited artifact changed')
    compile_commands = read(output/'build/compile_commands.json')
    app_commands = [r for r in compile_commands if '/device/week5/' in r['file'].replace('\\','/') or '/device/src/' in r['file'].replace('\\','/')]
    need(len(app_commands) == 5 and all('-ffp-contract=off' in r['command'] and '-fno-fast-math' in r['command'] and '-ffast-math' not in r['command'] for r in app_commands), 'Actual compilation flags invalid')
    need(binding['firmware_id'].encode() in (output/'build/zephyr/zephyr.elf').read_bytes(), 'ELF banner identity absent')
    package = package_metadata(output)
    display = (output/'pkg-display.log').read_text(encoding='utf-8-sig')
    need('fw_version: 0x00000005 (5)' in display and 'hw_version 0x00000034 (52)' in display and 'sd_req: 0x00' in display and
         'type: APPLICATION' in display and 'hash_type: SHA256' in display and
         bytes.fromhex(package['application']['sha256'])[::-1].hex() in display, 'DFU init metadata/hash differs')
    # Dependencies are checked without opening a device.
    import serial
    need(serial.VERSION == '3.5', 'Collector dependency unavailable')
    archive = output/'evidence'
    need(not archive.exists(), 'Evidence archive already exists')
    shutil.copytree(evidence, archive)
    shutil.copyfile(evidence/'memory-audit/memory.json', output/'memory-final.json')
    data = {'status':'READY_TO_FLASH', 'scope':'SV1_WEEK5_PREPARATION',
            'prepared_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).isoformat(),
            'branch':'dev/device-sv1', 'validation_execution_head':git('rev-parse','HEAD'),
            'verified_source_commit':None, 'committed_source_matches_tested_bytes':False,
            'working_tree':'UNCOMMITTED_PREPARATION', 'push':'PENDING', 'source_sha256':hashes,
            'firmware_binding':binding, **package, 'memory':memory, 'host':{'exact_golden_cases':220,'oracle_cases':220,
                'max_abs_error':host['max_head_abs_error'],'golden_differing_cases':host['golden_differing_cases'],
                'difference_analysis':host['difference_analysis'],'unexplained_mismatches':0},
            'accuracy':accuracy['rows'], 'commands':commands, 'reports':reports,
            'build_metadata_sha256':{str(output/p):sha(output/p) for p in ['generated/week5_build.h','generated/binding.json','build/compile_commands.json','memory-final.json']},
            'handoff_authentication':proof, 'accepted_r3_provenance':history,
            'flash':'NOT_RUN','mcu_validation':'PENDING','runtime_ram':'PENDING','runtime_stack':'PENDING','mcu_timing':'PENDING',
            'collector_dependency':'pyserial 3.5 installed in ml/.venv; no port opened', 'blockers':[],
            'skips':[{'gate':'Week 3/4 rebuild','reason':'Independent Week 5 app; all old CMake/Kconfig/config/source/generated headers unchanged; historical host/provenance/capture regressions PASS'}]}
    verify_artifacts(data)
    write_json(preparation_path,data)
    report(output,data)
    print(f'READY_TO_FLASH: {preparation_path}; flash=NOT_RUN; MCU=PENDING')

def report(output,data):
    lines = ['# SV1 Week 5 firmware preparation', '', f'Status: **{data["status"]}**. Prepared {data["prepared_at"]}.',
             f'Branch: `{data["branch"]}`. Verified source commit: `{data["verified_source_commit"]}`; push: {data["push"]}; tree: {data["working_tree"]}.',
             f'Commands ran with HEAD `{data["validation_execution_head"]}` before commit; source hashes bind the exact tested files. Commit content matches tested files: {data["committed_source_matches_tested_bytes"]}.',
             '', '| Gate | Result | Evidence |', '|---|---|---|',
             '| Current provenance / R3 historical anchors | PASS, normal and -O | evidence/commands/current-gate*.log |',
             '| C quantization on golden FP32 | 220 INT8 + 220 FP16 byte/bits exact; reverse/repeat PASS | evidence/host/week5_host.json |',
             f'| Head C -> C quantization | 220 oracle exact; reverse/repeat PASS; FP32 max {data["host"]["max_abs_error"]:.9g} < 1e-3 | evidence/host/week5_host.json |',
             '| Frozen full test offline | 8544 x 11; baseline 8393; all 93984 C/reference predictions equal | evidence/accuracy/ |',
             '| Week 4 host + reverse + Week 3 P2 | 220 + 220; P2 bitwise 20; PASS | evidence/week4-host/ |',
             '| Provenance/numerical/historical capture/tamper regressions | PASS normal and -O | evidence/commands/ |',
             '| Independent PCA10059 build / memory / partitions / DFU | PASS | build.log, memory.json, pkg-*.log |',
             '| Parser/collector offline | 236 SIMULATED HOST cases; 1/7/4096/65536-byte chunks + negative tests; PASS normal/-O | evidence/capture-tests*/ |',
             '| Package/source corruption preflight | PASS normal/-O | evidence/package-tests*.json |',
             '| Flash / MCU validation / timing / runtime RAM/stack | NOT_RUN / PENDING | No device access |', '',
             'Standard FP32 head -> actual portable C quantization and dequantization -> frozen tail. This offline accuracy evaluation does not certify MCU head/quantization.', '',
             '| s | FP32 correct | C quantized correct | Accuracy (%) | Drop (pp) | Relative drop (%) |', '|---:|---:|---:|---:|---:|---:|']
    for row in data['accuracy']:
        lines.append(f'| {row["split_point_s"]} | {row["correct_fp32"]} | {row["correct_int8_fp16"]} | {row["accuracy_int8_fp16_percent"]:.9f} | {row["accuracy_drop_pp"]:.9f} | {row["accuracy_drop_relative_percent"]:.9f} |')
    lines.extend(['', 'Every drop is strict <0.5 pp. Negative drop at s5 is preserved.', '',
                  'Three explained FP16 differences versus the SV3 golden package (INT8 all identical):', '',
                  '| Sample | Split | Channel | Golden raw scale | Head C raw scale | FP16 midpoint | Bits golden -> C |', '|---:|---:|---:|---:|---:|---:|---|'])
    for case in data['host']['difference_analysis']:
        for d in case['scale_details']:
            lines.append(f'| {case["sample_index"]} | {case["split"]} | {d["channel"]} | {d["golden_raw_scale_fp32"]:.12g} | {d["head_c_raw_scale_fp32"]:.12g} | {d["fp16_rounding_midpoint"]:.12g} | 0x{d["golden_scale_bits"]:04x} -> 0x{d["head_c_scale_bits"]:04x} |')
    lines.extend(['', 'Each raw scale crosses the binary16 rounding boundary because the head accumulation differs slightly; C output matches Python on the actual C activation in every case. No unexplained mismatch.', '',
                  '| Static region | Used B | Limit B | Remaining B |', '|---|---:|---:|---:|'])
    for name, region in data['memory']['regions'].items():
        lines.append(f'| {name} | {region["used_bytes"]} | {region["limit_bytes"]} | {region["remaining_bytes"]} |')
    lines.extend(['', f'Application allowed `[0x1000,0xe0000)`, actual HEX ends `{data["memory"]["hex_end_exclusive"]:#x}`. Every HEX record checked, no MBR/bootloader/UICR writes.',
                  '20 const weight arrays = 438612 B, single copy; inputs 28800 B in Flash; activation buffers 2 x 23040 B; quantized 5760 B + scales 128 B; heap pool zero; main usable stack 4096 B.',
                  'ELF/static linker allocation includes stacks and USB data. Runtime RAM/stack/timing are PENDING.', '', 'Exact artifacts:', ''])
    for name, entry in data['artifacts'].items():
        lines.append(f'- {name}: `{entry["path"]}`; SHA256 `{entry["sha256"]}` ({entry["bytes"]} B).')
    lines.extend(['', f'ZIP application SHA256 `{data["application"]["sha256"]}`; {data["application"]["bytes"]} B. Nordic init SHA256 is validated against pkg display; hw=52, sd_req=0, app version=5.',
                  f'Firmware identity: `{data["firmware_binding"]["firmware_id"]}`.',
                  'Source/generated headers/model/checkpoint/manifests SHA256, full commands/exit codes and build metadata are in preparation.json.',
                  'Fixture outputs are explicitly SIMULATED/HOST and keep MCU status PENDING. All historical ML/assets/reports and accepted firmware sources are preserved.',
                  'Old Week 3/4 rebuild: SKIP because the independent app changes no old target/config/source; historical host and captures rechecked.',
                  '', 'Next device session: follow `device/week5_prepare_guide.md`; discover actual bootloader/application ports, run read-only package preflight, then separately flash and collect. These steps have not been executed.',
                  'I1 v1 still uses FP32 scales; FP16 here is the offline/debug acceptance format. P1 C, radio and Device-Edge integration remain later work.'])
    (output/'preparation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--evidence', type=Path)
    p.add_argument('--refresh-git', action='store_true')
    a = p.parse_args()
    need(a.refresh_git or a.evidence is not None, '--evidence required')
    summarize(a.output.resolve(), a.evidence.resolve() if a.evidence else None, a.refresh_git)
