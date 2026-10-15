"""Consume an externally approved registry, never approve or allocate one."""
from week5_common_v2 import CHECKPOINT, mapping, need
from week5_delivery_scope_v2 import sha, read
from week5_interfaces import active_profile
from p1 import descriptor
import struct


def approved_registry(registry_path, approval_path, expected_approval_sha256):
    need(sha(approval_path) == expected_approval_sha256, 'Approval trust anchor differs')
    approval, registry = read(approval_path), read(registry_path)
    need(approval['schema'] == 'week5-registry-approval/1', 'Approval schema differs')
    need(approval['registry_sha256'] == sha(registry_path), 'Approved registry bytes differ')
    need(approval['decision'] == 'APPROVED' and registry['status'] == 'APPROVED', 'Allocation not approved')
    need(set(approval['approved_by']) == {'Châu', 'Trung'}, 'Châu/Trung confirmation missing')
    revision = registry.get('revision')
    need(isinstance(revision, str) and revision and approval['revision'] == revision
         and approval['device_revision'] == approval['edge_revision'] == revision, 'Shared revision missing')
    need(registry['model_name'] == registry['model_version'] == 'mitdb_week2_cnn_v1'
         and registry['checkpoint_sha256'] == CHECKPOINT, 'Approved model/checkpoint differs')
    scope = registry.get('sender_scope')
    need(isinstance(scope, dict) and scope.get('sender_ids') and scope.get('nonce_lifecycle'), 'Sender/nonce scope missing')
    need(all(type(v) is int and 0 < v <= 0xffffffff for v in scope['sender_ids'])
         and len(set(scope['sender_ids'])) == len(scope['sender_ids']), 'Invalid sender IDs')
    need(scope['key_id'] == registry['key_id'], 'Sender key scope differs')
    need(len(registry['splits']) == 11 and {r['split_point_s'] for r in registry['splits']} == set(range(11)),
         'Incomplete/duplicate approved mapping')
    from week5_interfaces import load_registry
    from week5_delivery_scope_v2 import ROOT
    frozen = load_registry(ROOT/'contracts/sv3_week5_ml_registry_v1.json')
    for field in ('quantization_version', 'quantization_scheme', 'quantization_reference'):
        need(registry[field] == frozen[field], f'Quantization contract differs: {field}')
    checked = []
    for row in registry['splits']:
        s = row['split_point_s']
        expected = mapping()[s]
        shape = expected['quantization_shape']
        need(row['head_endpoint'] == expected['cut_name'] and row['shape_original'] == expected['shape']
             and row['layout_original'] == expected['layout'] and row['i2_shape_NCL'] == shape,
             f'Approved frozen mapping differs: s{s}')
        payload, channels = expected['num_elements'], expected['channels']
        for side in ('device', 'edge'):
            limits = registry['buffer_limits'][side]
            need(type(limits['payload_bytes']) is int and payload <= limits['payload_bytes']
                 and type(limits['channels']) is int and channels <= limits['channels'], f'{side} buffer too small s{s}')
            need(row['max_payload_bytes'] <= limits['payload_bytes'], f'I2 profile ceiling exceeds {side} capacity')
        profile = active_profile(registry, s, shape, CHECKPOINT)
        fields = struct.unpack('<BBBBIHHHHIII', descriptor(profile))
        need(fields[4] == registry['model_profile_id'] and fields[5] == row['wire_split_id']
             and fields[6:8] == (1, channels) and fields[9] == shape[2] and fields[11] == payload,
             f'Descriptor mapping differs s{s}')
        checked.append({'s': s, 'wire_split_id': profile.split_id, 'payload_bytes': payload,
                        'descriptor_hex': descriptor(profile).hex()})
    return registry, {'revision': revision, 'registry_sha256': sha(registry_path),
                      'approval_sha256': sha(approval_path), 'mapping_descriptor': checked}
