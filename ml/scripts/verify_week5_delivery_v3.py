"""Final acceptance: portable science + project allocation + fresh offline SV1 gates."""
import argparse
from pathlib import Path
import sys

from week5_delivery_scope_v2 import ROOT, need, read, sha, safe_path, write_new
from verify_week5_delivery_v2 import verify as portable_verify, check_receipt
from week5_registry_acceptance_v3 import approved_registry, same


def bound_result(evidence, name, script, result_path):
    proof = check_receipt(evidence, name, script)
    record = read(evidence/f'{name}.command.json')
    key = result_path.resolve().relative_to(ROOT).as_posix()
    need(key in record['result_files_sha256'], f'Unbound result: {name}')
    for path, expected in record['result_files_sha256'].items():
        need(sha(safe_path(ROOT, path)) == expected, f'Result raw bytes changed: {name}/{path}')
    need(record['result_files_sha256'][key] == sha(result_path), f'Result hash differs: {name}')
    return read(result_path), proof, record['command']


def argument(command, flag, expected):
    need(command.count(flag) == 1, f'Expected one {flag}')
    need(Path(command[command.index(flag)+1]).resolve() == expected.resolve(), f'Wrong {flag}')


def check_sv1_result(result, optimized):
    need(result['status'] == 'SV1_WEEK5_TECHNICAL_ACCEPTANCE_PASS'
         and result['scope'] == 'REAL_MCU_CAPTURE' and result['primary_cases'] == 220
         and result['mixed_cases'] == 16 and result['oracle_exact_cases'] == 236
         and result['unexplained_mismatches'] == 0 and result['max_fp32_abs_error'] < 1e-3
         and result['optimized_python'] is optimized, 'Incomplete SV1 acceptance')
    primary, mixed = result['primary_rows'], result['mixed_rows']
    need(len(primary) == 220 and len(mixed) == 16
         and {(r['split'], r['sample_index']) for r in primary} == {(s,i) for s in range(11) for i in range(20)},
         'SV1 coverage differs')
    need(all(r['max_abs_error'] < 1e-3 and r['int8_oracle_exact'] is True
             and r['fp16_oracle_exact'] is True for r in primary+mixed), 'SV1 FP32/quantization oracle failed')
    need(all(r['max_abs_error'] == 0 for r in primary if r['split'] == 0)
         and result['historical_p2']['primary_cases'] == result['historical_p2']['bitwise_cases'] == 20,
         'SV1 s0/P2 bitwise gate failed')
    accuracy = result['accuracy_offline']
    need(accuracy['status'] == 'PASS_REUSED_UNCHANGED_SOURCE_AND_FROZEN_ASSETS'
         and accuracy['num_samples'] == 8544 and accuracy['splits'] == 11, 'C accuracy reuse invalid')
    for path, expected in result['evidence_sha256'].items():
        need(sha(Path(path)) == expected, f'SV1 original evidence changed: {path}')


def verify(evidence, portable, registry_path, approval_path, anchor, preparation, session):
    registry, allocation = approved_registry(registry_path, approval_path, anchor)
    science = portable_verify(portable, portable/'accuracy')
    need(science['status'] == 'BLOCKED' and science['gates']['deployment_registry'] == 'BLOCKED'
         and all(v == 'PASS' for k,v in science['gates'].items() if k != 'deployment_registry'),
         'Historical portable baseline is not science PASS / allocation-only BLOCKED')
    real_path = evidence/'approved_real_220.json'
    real, real_proof, command = bound_result(evidence, 'approved_real', 'ml/scripts/verify_week5_registry_v3.py', real_path)
    argument(command, '--registry', registry_path)
    argument(command, '--approval', approval_path)
    argument(command, '--output', real_path)
    need(command.count('--expected-approval-sha256') == 1
         and command[command.index('--expected-approval-sha256')+1] == anchor, 'Wrong approval anchor invocation')
    same(real['registry_used'], registry, 'executed approved registry')
    same(real['approval_proof'], allocation, 'executed approval proof')
    need(real['status'] == 'PASS' and real['tensors_executed'] == 220 and real['failed_tensors'] == 0
         and real['per_split_counts'] == {str(s):20 for s in range(11)}
         and real['deployment_registry_status'] == 'APPROVED_MAPPING_REAL_TAIL_CHECKED'
         and real['golden_manifest_sha256'] == sha(ROOT/'ml/artifacts/week5/quantization20/manifest.json')
         and len(real['wire_scale_checks']) == 220
         and real['key_execution_scope'].startswith('PUBLIC_TEST_ONLY;'), 'Approved real tensor coverage failed')
    records = {'approved_real': real_proof}
    for optimized in (False, True):
        suffix = '_O' if optimized else ''
        for name, script in [('allocation_policy','ml/scripts/test_week5_allocation_v3.py'),
                             ('preflight','device/scripts/verify_week5_package.py')]:
            records[name+suffix] = check_receipt(evidence, name+suffix, script)
        preflight = read(evidence/f'preflight{suffix}.command.json')
        argument(preflight['command'], '--preparation', preparation)
        name = 'sv1_acceptance'+suffix
        result, proof, command = bound_result(evidence, name, 'device/scripts/accept_week5_mcu.py',
                                              evidence/name/'week5_mcu_validation.json')
        argument(command, '--preparation', preparation)
        argument(command, '--session', session)
        argument(command, '--output', evidence/name)
        check_sv1_result(result, optimized)
        need(result['preparation_snapshot_sha256'] == sha(preparation), 'Wrong SV1 preparation')
        records[name] = proof
    return {'schema': 'week5-final-delivery/3', 'status': 'PASS', 'CURRENT_WEEK': 5,
            'scope': registry['scope'], 'allocation': allocation,
            'gates': {**{k:v for k,v in science['gates'].items() if k != 'deployment_registry'},
                      'project_allocation': 'PASS', 'approved_real_220': 'PASS',
                      'authority_regressions_normal_O': 'PASS', 'compatibility_SV1_normal_O': 'PASS'},
            'baseline_v2_status': 'BLOCKED/exit2; historical null-ID baseline only',
            'portable_proof': science, 'final_receipts': records,
            'reuse': ['authenticated historical preservation audit',
                      'original MCU/DFU/capture evidence', 'source-bound C accuracy; full test on MCU NOT_RUN'],
            'limits': registry['runtime'], 'packet_planning': registry['packet_planning'],
            'week6_firmware': 'NOT_RUN', 'timing_runtime_RAM_stack': 'NOT_MEASURED'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--portable', type=Path, required=True)
    p.add_argument('--registry', type=Path, required=True)
    p.add_argument('--approval', type=Path, required=True)
    p.add_argument('--expected-approval-sha256', required=True)
    p.add_argument('--preparation', type=Path, required=True)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    need(not a.output.exists(), 'Use a new final output path')
    try:
        result = verify(a.evidence.resolve(), a.portable.resolve(), a.registry.resolve(), a.approval.resolve(),
                        a.expected_approval_sha256, a.preparation.resolve(), a.session.resolve())
        code = 0
    except FileNotFoundError as error:
        result, code = {'schema':'week5-final-delivery/3','status':'BLOCKED','reason':str(error)}, 2
    except (ValueError, KeyError, TypeError, IndexError, UnicodeError) as error:
        result, code = {'schema':'week5-final-delivery/3','status':'FAIL','reason':str(error)}, 1
    write_new(a.output, result)
    print(result['status']+': '+result.get('reason','ASI testbed allocation, science and SV1 compatibility accepted'))
    return code


if __name__ == '__main__':
    sys.exit(main())
