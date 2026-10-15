"""ASI project-lead authority v2; raw-byte approval, never key provisioning."""
import hashlib
import json
from pathlib import Path
import struct

from week5_common_v2 import CHECKPOINT, mapping
from week5_delivery_scope_v2 import ROOT, need, sha
from week5_interfaces import active_profile
from p1 import descriptor

REVISION = 'mitdb-week5-i2-registry-v1-r1'
SCOPE = {'namespace': 'ASI/MIT-BIH', 'environment': 'internal-team-testbed',
         'protocol': 'I2/1', 'production_authorized': False, 'external_systems_authorized': False}
LIMITS = {'payload_bytes': 5760, 'channels': 64, 'fp16_scale_array_bytes': 128,
          'fp32_le_scale_array_bytes': 256, 'per_channel_quant_metadata_bytes': 516}
NONCE = {'encoding': 'sender_id:uint32_le || sequence:uint64_le', 'initial_sequence': 1,
         'persist_reserve_before_transmit': True, 'reboot': 'discard-unused-reserved-range',
         'retry': 'resend-identical-bytes-without-reprotect',
         'persistence_failure': 'stop-until-valid-new-key-and-sender-provisioned; relabeling-key_id-insufficient',
         'uint64_exhaustion': 'rotate-key-and-sender', 'runtime_acceptance': 'NOT_ACCEPTED'}
CONFIRMATION = {'person': 'Trung', 'source': 'Reported by Châu in the direct authorization',
    'type': 'conditional Edge technical confirmation',
    'conditions': ['internal ASI/MIT-BIH I2/1 model/profile/revision scope',
                   'Edge executable tails s0..s9; s10 Device-only/empty-tail',
                   'separate payload/scales/metadata ceilings; packet budget remains design-only',
                   'runtime key provisioning, nonce persistence/reboot and transport not accepted'],
    'final_registry_or_approval_hash_independently_attested': False}


def same(actual, expected, label):
    """JSON comparison including types (true must not stand in for integer 1)."""
    need(type(actual) is type(expected), f'{label}: type differs')
    if isinstance(expected, dict):
        need(actual.keys() == expected.keys(), f'{label}: missing/unknown fields')
        for k, value in expected.items():
            same(actual[k], value, f'{label}/{k}')
    elif isinstance(expected, list):
        need(len(actual) == len(expected), f'{label}: length differs')
        for i, value in enumerate(expected):
            same(actual[i], value, f'{label}/{i}')
    else:
        need(actual == expected, f'{label}: value differs')


def read_canonical(path):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, f'Duplicate JSON key: {k}')
            result[k] = v
        return result
    raw = Path(path).read_bytes()
    def invalid_constant(value):
        raise ValueError(f'Nonfinite JSON number: {value}')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    need(isinstance(value, dict), 'Expected JSON object')
    canonical = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
    need(raw == canonical, 'Require canonical UTF-8, two-space indentation, LF and final newline')
    return value


def approved_registry(registry_path, approval_path, expected_approval_sha256):
    need(isinstance(expected_approval_sha256, str) and len(expected_approval_sha256) == 64
         and all(c in '0123456789abcdef' for c in expected_approval_sha256), 'Invalid approval anchor')
    need(sha(approval_path) == expected_approval_sha256, 'Approval raw SHA256 differs')
    a, r = read_canonical(approval_path), read_canonical(registry_path)
    expected_approval = {
        'schema': 'asi-project-registry-approval/2', 'authority_policy': 'asi-project-lead/1',
        'decision': 'APPROVED', 'approved_by': ['Lê Hải Châu'],
        'approver_role': 'ASI project lead; final project authority', 'recorded_by': 'Codex',
        'authorization': 'Direct authorization by Lê Hải Châu in this session, 2026-10-15 Asia/Saigon',
        'attestation_type': 'delegated decision record; not a cryptographic signature or manual user hash attestation',
        'scope': SCOPE, 'revision': REVISION, 'device_revision': REVISION, 'edge_revision': REVISION,
        'registry_sha256': sha(registry_path), 'technical_confirmation': CONFIRMATION,
        'independent_final_hash_attestation_by_ky_anh': False}
    same(a, expected_approval, 'approval')
    frozen = read_canonical(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
    expected = dict(frozen)
    expected.update(schema_version=2, schema='asi-project-registry/2', status='APPROVED',
        authority='asi-project-lead/1', revision=REVISION, scope=SCOPE,
        model_profile_id=1296651265, key_id=65537,
        sender_scope={'sender_ids': [131073], 'owner': 'Device SV1', 'key_id': 65537,
            'protocol': 'I2/1', 'namespace': 'ASI/MIT-BIH', 'model_profile_id': 1296651265,
            'revision': REVISION, 'key_id_is_public_label': True, 'nonce_lifecycle': NONCE},
        buffer_limits={s: LIMITS for s in ('device', 'edge')},
        packet_planning={'i1_version': 2, 'protected_budget_bytes': 6380,
            'status': 'DESIGN_ONLY; packet-buffer/parser/transport NOT_ACCEPTED'},
        runtime={'provisioning': 'NOT_ACCEPTED', 'nonce_persistence_reboot': 'NOT_ACCEPTED',
            'p1_transmission_authorized': False, 'i1_status': 'REVIEW_CANDIDATE'})
    expected['splits'] = []
    for row in frozen['splits']:
        s = row['split_point_s']
        expected['splits'].append({**row, 'wire_split_id': 256+s, 'max_payload_bytes': 5760,
            'device_buffer_limit_status': 'APPROVED_PROJECT_PROFILE_CEILING',
            'execution': 'Device-only/empty-tail' if s == 10 else 'Device-head/Edge-tail',
            'edge_tail_executable': s < 10,
            'reference_tail': 'identity/empty-tail' if s == 10 else 'frozen-model-tail'})
    same(r, expected, 'registry')
    need(r['model_name'] == r['model_version'] == 'mitdb_week2_cnn_v1'
         and r['checkpoint_sha256'] == CHECKPOINT, 'Frozen model/checkpoint differs')
    checked = []
    for row, m in zip(r['splits'], mapping()):
        s, channels, payload = m['split_point_s'], m['channels'], m['num_elements']
        same(row['shape_original'], m['shape'], f's{s} original shape')
        same(row['i2_shape_NCL'], m['quantization_shape'], f's{s} wire shape')
        need(row['split_point_s'] == s and row['head_endpoint'] == m['cut_name']
             and row['layout_original'] == m['layout'], f'Frozen mapping differs s{s}')
        for side in ('device', 'edge'):
            limits = r['buffer_limits'][side]
            need(payload <= row['max_payload_bytes'] <= limits['payload_bytes']
                 and channels <= limits['channels'] and 2*channels <= limits['fp16_scale_array_bytes']
                 and 4*channels <= limits['fp32_le_scale_array_bytes']
                 and 4+8*channels <= limits['per_channel_quant_metadata_bytes'], f'{side} capacity s{s}')
        profile = active_profile(r, s, m['quantization_shape'], CHECKPOINT)
        fields = struct.unpack('<BBBBIHHHHIII', descriptor(profile))
        need(fields[4] == 1296651265 and fields[5] == 256+s and fields[6:8] == (1, channels)
             and fields[9] == m['quantization_shape'][2] and fields[11] == payload, f'Descriptor s{s}')
        checked.append({'s': s, 'wire_split_id': profile.split_id, 'payload_bytes': payload,
                        'descriptor_hex': descriptor(profile).hex()})
    return r, {'authority_policy': 'asi-project-lead/1', 'revision': REVISION,
               'registry_sha256': sha(registry_path), 'approval_sha256': sha(approval_path),
               'mapping_descriptor': checked}
