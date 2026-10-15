"""Final Week 5 acceptance of real, source-bound captures; never accesses serial."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from week5_common import ROOT, PACKAGE, authenticate, firmware_binding, need, sha, write_json, quantize_per_channel, to_ncl
from week5_capture import CaptureParser, sequence
from verify_week5_package import verify_package
from generate_week3_inputs import check_inventory, TRUSTED_MANIFEST
from check_week3_capture import read_capture

IMAGE_SOURCE = '51ef9c966e052bfd63c8e416dcfad3d6af30e755'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.tzinfo is not None, 'Evidence timestamp must include timezone')
    return parsed

def validate_chain(prepared, preparation_sha, dfu, collection, capture_sha, command, ports_before, ports_after):
    need(prepared['verified_source_commit'] == IMAGE_SOURCE and prepared['flash'] == 'NOT_RUN' and
         prepared['mcu_validation'] == 'PENDING', 'Preparation snapshot/source must remain unchanged')
    need(dfu['origin'] == 'REAL_USB_DFU' and dfu['exit_code'] == 0, 'No successful real USB DFU receipt')
    need(dfu['preparation_sha256'] == preparation_sha and collection['preparation_sha256'] == preparation_sha, 'Preparation receipt hash mismatch')
    need(dfu['package'] == prepared['artifacts']['zip'] and dfu['application'] == prepared['application'], 'Wrong flashed package/application')
    need(collection['origin'] == 'REAL_MCU_CAPTURE' and collection['commands_completed'] == 236 and
         collection['capture_sha256'] == capture_sha and collection['firmware_id'] == prepared['firmware_binding']['firmware_id'], 'Invalid real collection receipt')
    need(command['exit_code'] == 0, 'Collector command did not finish successfully')
    expected_args = ['-B','device/scripts/collect_week5.py','--port',collection['port'],'--preparation',dfu['preparation']]
    args = command['arguments']
    need(args[:6] == expected_args and len(args) == 10 and args[6] == '--capture' and args[8] == '--report',
         'Collector command does not match receipt')
    before = ports_before if isinstance(ports_before, list) else [ports_before]
    after = ports_after if isinstance(ports_after, list) else [ports_after]
    boot = [p for p in before if 'VID_1915&PID_521F' in p['InstanceId'] and f'({dfu["port"]})' in p['FriendlyName'] and p['Status'] == 'OK']
    app = [p for p in after if 'VID_2FE3&PID_0004' in p['instance_id'] and f'({collection["port"]})' in p['name'] and p['status'] == 'OK']
    need(len(boot) == len(app) == 1, 'Actual USB identities/ports are not uniquely bound')
    descriptions = [p['Data'] for p in app[0]['properties'] if p['KeyName'] == 'DEVPKEY_Device_BusReportedDeviceDesc']
    need(descriptions == ['Adaptive Split Inference SV1'], 'Wrong CDC USB product')
    need(timestamp(prepared['prepared_at']) <= timestamp(dfu['timestamp']) <= timestamp(command['started_utc']) <=
         timestamp(collection['collected_utc']) <= timestamp(command['finished_utc']), 'Evidence chronology mismatch')

def historical_p2():
    package = ROOT / 'ml/artifacts/week3/mitdb-week3-fp32-20260925-v2'
    check_inventory(package)
    report_name = 'results/week3/week3_mcu_validation_20x5.json'
    report_path = ROOT / report_name
    pinned = subprocess.check_output(['git','show',f'{IMAGE_SOURCE}:{report_name}'], cwd=ROOT)
    need(report_path.read_bytes().replace(b'\r\n', b'\n') == pinned.replace(b'\r\n', b'\n'), 'Historical Week 3 report differs from pinned image-source tree')
    old = read(report_path)
    old_capture = ROOT / 'results/week3/logs/week3_capture_20x5.txt'
    w4 = read(ROOT / 'results/week4/week4_mcu_validation.json')
    # authenticate() has checked the immutable R3 report anchor before this read.
    need(old['manifest_sha256'] == TRUSTED_MANIFEST and old['mcu_20_of_20'] == 'PASS' and
         sha(old_capture) == old['capture_sha256'] == w4['week3_mcu_capture_sha256'], 'Historical P2 evidence binding failed')
    tensors, _ = read_capture(old_capture, full_trace=True)
    with (package / 'samples.csv').open(encoding='utf-8', newline='') as handle:
        ids = [r['sample_id'] for r in csv.DictReader(handle)]
    old_inputs = np.load(package / 'inputs.npy', allow_pickle=False)
    current_inputs = np.load(ROOT / PACKAGE / 'golden/z_s0.npy', allow_pickle=False)
    need(old_inputs.tobytes() == current_inputs.tobytes(), 'Week 3/5 sample inputs differ')
    return tensors, ids, {'status':'PASS', 'manifest_sha256':TRUSTED_MANIFEST,
        'report_sha256':sha(report_path), 'report_pinned_git_commit':IMAGE_SOURCE,
        'capture_sha256':sha(old_capture), 'capture_path':str(old_capture)}

class AcceptanceParser(CaptureParser):
    def __init__(self, binding, manifest, goldens, old_tensors, old_ids):
        super().__init__(binding, manifest, goldens, simulated=False)
        self.observations, self.differences = [], []
        self.old_tensors, self.old_ids = old_tensors, old_ids

    def validate(self, n, s, entry):
        super().validate(n, s, entry)
        actual = np.array(self.head_bits, '<u4').view('<f4').reshape(entry['shape_original'])
        golden = self.goldens[s][n:n+1]
        q = np.array(self.q_bits, np.uint8).view(np.int8).reshape(entry['quantization_shape_NCL'])
        scales = np.array(self.scale_bits, '<u2').view('<f2').reshape(1,-1)
        qg, sg = quantize_per_channel(to_ncl(golden, s))
        row = {**self.rows[-1], 'phase':'primary' if self.case_index < 220 else 'mixed',
               'int8_oracle_exact':True, 'fp16_oracle_exact':True, 'identity_bitwise':s == 0,
               'golden_q_difference_count':int(np.count_nonzero(q != qg)),
               'golden_scale_difference_count':int(np.count_nonzero(scales.view('<u2') != sg.view('<u2'))),
               'p2_historical_max_abs_error':None, 'p2_historical_bitwise':None}
        if s == 2:
            need(entry['sample_id'] == self.old_ids[n], 'Historical P2 sample_id differs')
            old = self.old_tensors[n, 'P2']
            error = float(np.max(np.abs(actual.astype(np.float64)-old.astype(np.float64))))
            need(error < 1e-3, f'Historical P2 strict gate failed n{n}: {error}')
            row.update(p2_historical_max_abs_error=error, p2_historical_bitwise=actual.tobytes() == old.tobytes())
        self.observations.append(row)
        if row['golden_q_difference_count'] or row['golden_scale_difference_count']:
            zc, zg = to_ncl(actual, s), to_ncl(golden, s)
            length = zc.shape[-1]
            details = []
            for i in np.flatnonzero(q.ravel() != qg.ravel()):
                c = int(i)//length
                details.append({'offset':int(i), 'channel':c, 'golden_fp32':float(zg.ravel()[i]),
                    'mcu_fp32':float(zc.ravel()[i]), 'golden_ratio_fp32':float(zg.ravel()[i]/np.float32(sg[0,c])),
                    'mcu_ratio_fp32':float(zc.ravel()[i]/np.float32(scales[0,c])),
                    'golden_q':int(qg.ravel()[i]), 'mcu_q':int(q.ravel()[i])})
            scale_details = []
            for c in np.flatnonzero(scales.view('<u2').ravel() != sg.view('<u2').ravel()):
                scale_details.append({'channel':int(c), 'golden_raw_scale_fp32':float(np.max(np.abs(zg[0,c]))/np.float32(127)),
                    'mcu_raw_scale_fp32':float(np.max(np.abs(zc[0,c]))/np.float32(127)),
                    'fp16_rounding_midpoint':float((np.float32(sg[0,c])+np.float32(scales[0,c]))*np.float32(.5)),
                    'golden_scale_bits':int(sg.view('<u2')[0,c]), 'mcu_scale_bits':int(scales.view('<u2')[0,c])})
            self.differences.append({'sample_index':n,'sample_id':entry['sample_id'],'split':s,'phase':row['phase'],
                                    'int8_details':details,'scale_details':scale_details,
                                    'explanation':'Python quantization on the exact MCU FP32 input matches every transmitted INT8 byte/FP16 bit; golden differences come from the FP32 head.'})

def sizes(mapping):
    rows = []
    for m in mapping:
        fp, payload, scale = 4*m['num_elements'], m['num_elements'], 2*m['channels']
        rows.append({'split':m['split_point_s'], 'cut_name':m['cut_name'], 'shape':'x'.join(map(str,m['shape'])),
            'layout':m['layout'], 'channels':m['channels'], 'num_elements':m['num_elements'], 'fp32_bytes':fp,
            'int8_payload_bytes':payload,'fp16_scale_bytes':scale,'int8_plus_fp16_bytes':payload+scale,
            'payload_reduction_factor':fp/payload,'total_reduction_factor':fp/(payload+scale),
            'total_reduction_percent':100*(1-(payload+scale)/fp)})
    return rows

def validate_session(session, preparation):
    prepared = verify_package(preparation)
    manifest, authentication, history = authenticate()
    need(prepared['verified_source_commit'] == IMAGE_SOURCE, 'Unexpected image source')
    capture = session/'week5_capture.txt'
    dfu_paths = list((session/'dfu').glob('dfu-*.json'))
    successful = [(p,read(p)) for p in dfu_paths if read(p).get('exit_code') == 0]
    need(len(successful) == 1, 'Session requires exactly one successful DFU receipt')
    dfu_path, dfu = successful[0]
    collection_path = capture.with_suffix('.receipt.json')
    collection, command = read(collection_path), read(session/'collect.command.json')
    validate_chain(prepared, sha(preparation), dfu, collection, sha(capture), command,
                   read(session/'ports-before.json'), read(session/'ports-after-dfu.json'))
    need(command['arguments'][command['arguments'].index('--capture')+1] == str(capture), 'Command/capture path differs')
    need(command['arguments'][command['arguments'].index('--report')+1] == str(session/'week5_mcu_validation.json'), 'Command/report path differs')
    old_tensors, old_ids, p2_proof = historical_p2()
    goldens = [np.load(ROOT / PACKAGE / f'golden/z_s{s}.npy', allow_pickle=False) for s in range(11)]
    parser = AcceptanceParser(firmware_binding(), manifest, goldens, old_tensors, old_ids)
    with capture.open('rb') as handle:
        for chunk in iter(lambda:handle.read(4093), b''):
            parser.feed(chunk)
    result = parser.finish()
    for name in ('week5_mcu_validation.json','week5_mcu_recheck.json','week5_mcu_recheck_O.json'):
        checked = read(session/name)
        need(checked['status'] == 'PASS' and checked['scope'] == 'REAL_MCU_CAPTURE' and checked['mcu_validation'] == 'PASS' and
             checked['primary_cases'] == 220 and checked['mixed_cases'] == 16 and checked['capture_sha256'] == sha(capture) and
             checked['firmware_binding'] == prepared['firmware_binding'] and checked['rows'] == parser.rows, 'Independent checker or collector report differs')
    p2_rows = [r for r in parser.observations[:220] if r['split'] == 2]
    need(len(p2_rows) == 20, 'Historical P2 primary coverage incomplete')
    accuracy_path = Path(preparation).parent/'evidence/accuracy/evaluation.json'
    accuracy = read(accuracy_path)
    need(sha(accuracy_path) == prepared['reports']['accuracy']['sha256'], 'Prepared accuracy report changed')
    need(accuracy['status'] == 'PASS' and accuracy['num_samples'] == 8544 and accuracy['splits'] == 11 and
         accuracy['baseline_correct'] == 8393 and accuracy['c_oracle_exact_cases'] == 93984 and
         all(r['accuracy_drop_pp'] < .5 for r in accuracy['rows']), 'Full-test offline accuracy gate incomplete')
    for source, expected in accuracy['source_sha256'].items():
        need(sha(ROOT/source) == expected, f'Accuracy reuse source drift: {source}')
    for source, expected in accuracy['provenance']['source_files_sha256'].items():
        need(sha(ROOT/source) == expected, f'Frozen ML/tail source drift: {source}')
    hashes = {str(p):sha(p) for p in [preparation,dfu_path,collection_path,capture,accuracy_path,session/'collect.command.json',
        session/'ports-before.json',session/'ports-after-dfu.json', *[session/n for n in ('week5_mcu_validation.json','week5_mcu_recheck.json','week5_mcu_recheck_O.json')]]}
    result.update(status='SV1_WEEK5_TECHNICAL_ACCEPTANCE_PASS', scope='REAL_MCU_CAPTURE', image_source_sha=IMAGE_SOURCE,
        firmware_binding=prepared['firmware_binding'], artifacts=prepared['artifacts'], application=prepared['application'],
        preparation_snapshot_sha256=sha(preparation), flash={'status':'PASS', 'receipt':str(dfu_path),'port':dfu['port'],'exit_code':0,'timestamp_utc':dfu['timestamp']},
        collection={'status':'PASS','receipt':str(collection_path),'port':collection['port'],'timestamp_utc':collection['collected_utc']},
        evidence_sha256=hashes, handoff_authentication=authentication, accepted_r3_provenance=history,
        historical_p2={**p2_proof,'primary_cases':20,'max_abs_error':max(r['p2_historical_max_abs_error'] for r in p2_rows),
                       'bitwise_cases':sum(r['p2_historical_bitwise'] for r in p2_rows)},
        max_fp32_abs_error=max(r['max_abs_error'] for r in parser.rows), oracle_exact_cases=236, unexplained_mismatches=0,
        golden_difference_analysis=parser.differences, primary_rows=parser.observations[:220], mixed_rows=parser.observations[220:],
        accuracy_offline={'status':'PASS_REUSED_UNCHANGED_SOURCE_AND_FROZEN_ASSETS','scope':accuracy['scope'],
            'num_samples':8544,'splits':11,'baseline_correct':8393,'rows':accuracy['rows'], 'evaluation_sha256':sha(accuracy_path),
            'checkpoint_sha256':accuracy['provenance']['checkpoint_sha256'], 'full_test_on_mcu':'NOT_RUN'},
        tensor_sizes=sizes(manifest['mapping']), timing='NOT_MEASURED', runtime_ram='NOT_MEASURED', runtime_stack='NOT_MEASURED',
        git_integration='PENDING', acceptance_tooling_sha256={Path(__file__).relative_to(ROOT).as_posix():sha(__file__)},
        optimized_python=bool(sys.flags.optimize))
    result.pop('rows')
    return result

def write_csv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)

def publish(output, result):
    need(not output.exists(), 'Use a new acceptance output directory')
    output.mkdir(parents=True)
    write_json(output/'week5_mcu_validation.json', result)
    columns = ['phase','sample_index','sample_id','split','max_abs_error','int8_oracle_exact','fp16_oracle_exact',
               'golden_q_difference_count','golden_scale_difference_count','p2_historical_max_abs_error','p2_historical_bitwise']
    for name, rows in [('validation_20x11.csv',result['primary_rows']),('validation_mixed.csv',result['mixed_rows'])]:
        write_csv(output/name,[{k:r[k] for k in columns} for r in rows])
    write_csv(output/'tensor_sizes.csv',result['tensor_sizes'])
    write_csv(output/'accuracy_offline.csv',result['accuracy_offline']['rows'])
    write_json(output/'golden_difference_analysis.json',result['golden_difference_analysis'])

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--preparation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    r = validate_session(a.session.resolve(),a.preparation.resolve())
    publish(a.output.resolve(),r)
    print(f'SV1_WEEK5_TECHNICAL_ACCEPTANCE_PASS: primary=220 mixed=16 oracle=236 P2=20; max FP32={r["max_fp32_abs_error"]}; MCU PASS; timing/RAM/stack NOT_MEASURED')
