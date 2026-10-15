"""Only externally anchored approval can reach mapping/descriptor verification."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_week5_interfaces import test_registry
from week5_registry_acceptance_v2 import approved_registry
from week5_delivery_scope_v2 import sha


class RegistryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry_path, self.approval_path = self.root/'registry.json', self.root/'approval.json'
        # Fabricated public unit-test approval; never stored as deployment evidence.
        self.registry = test_registry()
        self.registry.update(status='APPROVED', revision='PUBLIC_TEST_ONLY-fixture',
                             sender_scope={'sender_ids':[1], 'key_id':1, 'nonce_lifecycle':'PUBLIC_TEST_ONLY'},
                             buffer_limits={s:{'payload_bytes':5760,'channels':64} for s in ('device','edge')})
        for row in self.registry['splits']:
            row['max_payload_bytes'] = 5760
        self.approval = dict(schema='week5-registry-approval/1', decision='APPROVED',
                             approved_by=['Châu','Trung'], revision='PUBLIC_TEST_ONLY-fixture',
                             device_revision='PUBLIC_TEST_ONLY-fixture',edge_revision='PUBLIC_TEST_ONLY-fixture')

    def check(self):
        self.registry_path.write_text(json.dumps(self.registry), encoding='utf-8')
        self.approval['registry_sha256'] = sha(self.registry_path)
        self.approval_path.write_text(json.dumps(self.approval), encoding='utf-8')
        return approved_registry(self.registry_path,self.approval_path,sha(self.approval_path))

    def test_explicit_nonproposal_mapping_descriptor(self):
        _, proof = self.check()
        self.assertEqual(len(proof['mapping_descriptor']),11)
        self.assertEqual(proof['mapping_descriptor'][3]['wire_split_id'],122)

    def test_ids_alone_do_not_pass(self):
        self.registry = test_registry()
        with self.assertRaises(ValueError): self.check()

    def test_shared_revision_and_approval_required(self):
        for field,value in [('decision','PENDING'),('approved_by',['Trung']),('device_revision','other')]:
            original = copy.deepcopy(self.approval)
            self.approval[field] = value
            with self.assertRaises(ValueError): self.check()
            self.approval = original

    def test_mapping_buffers_and_key_scope_rejected(self):
        mutations = [lambda r:r['splits'][1].update(wire_split_id=r['splits'][0]['wire_split_id']),
                     lambda r:r['splits'][1].update(i2_shape_NCL=[1,32,180]),
                     lambda r:r['splits'][1].update(head_endpoint='wrong-layer'),
                     lambda r:r['buffer_limits']['device'].update(payload_bytes=327),
                     lambda r:r['buffer_limits']['edge'].update(channels=32),
                     lambda r:r['sender_scope'].update(key_id=2),
                     lambda r:r.update(checkpoint_sha256='0'*64)]
        for mutate in mutations:
            original = copy.deepcopy(self.registry)
            mutate(self.registry)
            with self.assertRaises(ValueError): self.check()
            self.registry = original

    def test_trust_anchor_and_registry_bytes(self):
        self.check()
        with self.assertRaises(ValueError):
            approved_registry(self.registry_path,self.approval_path,'0'*64)
        self.registry_path.write_bytes(self.registry_path.read_bytes()+b'\n')
        with self.assertRaises(ValueError):
            approved_registry(self.registry_path,self.approval_path,sha(self.approval_path))


if __name__ == '__main__':
    unittest.main(verbosity=2)
