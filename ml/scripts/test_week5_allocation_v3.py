"""Reject tampered authority, bytes and project contracts under normal/-O Python."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from week5_registry_acceptance_v3 import approved_registry, read_canonical
from week5_delivery_scope_v2 import ROOT, sha
from verify_week5_delivery_v3 import check_sv1_result


class AllocationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.rp, self.ap = self.directory/'registry.json', self.directory/'approval.json'
        # Copies of the delegated project record for mutation testing only.
        self.registry = read_canonical(ROOT/'contracts/sv3_week5_approved_registry_v2.json')
        self.approval = read_canonical(ROOT/'contracts/sv3_week5_allocation_approval_v2.json')

    def write(self):
        for path, value in ((self.rp,self.registry), (self.ap,self.approval)):
            if path == self.ap:
                value['registry_sha256'] = sha(self.rp)
            path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))
        return sha(self.ap)

    def check(self):
        return approved_registry(self.rp,self.ap,self.write())

    def test_approved_mapping_descriptor_and_s10(self):
        r, proof = self.check()
        self.assertEqual([v['wire_split_id'] for v in proof['mapping_descriptor']], list(range(256,267)))
        self.assertEqual(r['model_profile_id'],1296651265)
        self.assertEqual(r['key_id'],65537)
        self.assertEqual(r['sender_scope']['sender_ids'],[131073])
        self.assertFalse(r['splits'][10]['edge_tail_executable'])
        self.assertEqual(r['splits'][10]['reference_tail'],'identity/empty-tail')

    def test_authority_scope_revision_and_false_attestation_rejected(self):
        mutations = [lambda a:a.update(schema='week5-registry-approval/1'),
            lambda a:a.update(approved_by=['Trung']), lambda a:a.update(approved_by=['Lê Hải Châu','Trung']),
            lambda a:a.update(authority_policy='unrestricted'),lambda a:a.update(recorded_by='Trung'),
            lambda a:a['scope'].update(environment='production'),lambda a:a['scope'].update(production_authorized=True),
            lambda a:a.update(revision='other'),lambda a:a.update(device_revision='other'),
            lambda a:a.update(edge_revision='other'),lambda a:a.update(decision='PENDING'),
            lambda a:a['technical_confirmation'].update(final_registry_or_approval_hash_independently_attested=True),
            lambda a:a.update(independent_final_hash_attestation_by_ky_anh=True)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                original=copy.deepcopy(self.approval)
                mutation(self.approval)
                with self.assertRaises(ValueError): self.check()
                self.approval=original

    def test_registry_mapping_capacity_key_sender_nonce_and_s10_rejected(self):
        mutations = [lambda r:r.update(checkpoint_sha256='0'*64),lambda r:r.update(model_version='other'),
            lambda r:r.update(model_profile_id=1296651266),lambda r:r.update(key_id=1),
            lambda r:r.update(key_id=True),lambda r:r.update(revision='other'),
            lambda r:r['scope'].update(namespace='outside'),lambda r:r.update(authority='other'),
            lambda r:r['sender_scope'].update(sender_ids=[131074]),lambda r:r['sender_scope'].update(key_id=1),
            lambda r:r['sender_scope'].update(model_profile_id=1),lambda r:r['sender_scope'].update(revision='other'),
            lambda r:r['sender_scope']['nonce_lifecycle'].update(initial_sequence=True),
            lambda r:r['sender_scope']['nonce_lifecycle'].update(persist_reserve_before_transmit=False),
            lambda r:r['splits'][1].update(wire_split_id=256),lambda r:r['splits'][1].update(wire_split_id=1),
            lambda r:r['splits'][1].update(i2_shape_NCL=[1,32,180]),
            lambda r:r['splits'][1].update(head_endpoint='wrong'),lambda r:r['splits'][1].update(max_payload_bytes=32768),
            lambda r:r['buffer_limits']['device'].update(payload_bytes=32768),
            lambda r:r['buffer_limits']['edge'].update(payload_bytes=5759),
            lambda r:r['buffer_limits']['edge'].update(channels=63),
            lambda r:r['buffer_limits']['device'].update(fp16_scale_array_bytes=127),
            lambda r:r['buffer_limits']['edge'].update(fp32_le_scale_array_bytes=255),
            lambda r:r['buffer_limits']['edge'].update(per_channel_quant_metadata_bytes=515),
            lambda r:r['packet_planning'].update(protected_budget_bytes=5760),
            lambda r:r['runtime'].update(p1_transmission_authorized=True),
            lambda r:r['splits'][10].pop('execution'),lambda r:r['splits'][10].update(edge_tail_executable=True),
            lambda r:r['splits'][10].update(reference_tail='tail_s10'),lambda r:r['splits'].pop()]
        for mutation in mutations:
            original=copy.deepcopy(self.registry)
            mutation(self.registry)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check()
            self.registry=original

    def test_missing_fields_rejected(self):
        for kind in ('registry','approval'):
            value=getattr(self,kind)
            # registry_sha256 is supplied by write(); exercise its omission below.
            for field in list(value):
                if field == 'registry_sha256': continue
                original=copy.deepcopy(value)
                value.pop(field)
                with self.subTest(kind=kind,field=field), self.assertRaises(ValueError): self.check()
                value.clear(); value.update(original)
        anchor=self.write()
        a=read_canonical(self.ap); a.pop('registry_sha256')
        self.ap.write_bytes((json.dumps(a,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        with self.assertRaises(ValueError): approved_registry(self.rp,self.ap,sha(self.ap))

    def test_raw_hashes_and_malformed_json_rejected(self):
        anchor=self.write()
        with self.assertRaises(ValueError): approved_registry(self.rp,self.ap,'0'*64)
        self.rp.write_bytes(self.rp.read_bytes()+b'\n')
        with self.assertRaises(ValueError): approved_registry(self.rp,self.ap,anchor)
        self.write(); self.ap.write_bytes(self.ap.read_bytes()+b'\n')
        with self.assertRaises(ValueError): approved_registry(self.rp,self.ap,anchor)
        for raw in (b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{', b'[]\n', b'\xef\xbb\xbf{}\n'):
            self.ap.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError): read_canonical(self.ap)

    def test_missing_approval_is_blocked_and_never_pass(self):
        anchor=self.write(); self.ap.unlink()
        output=self.directory/'final.json'
        command=[sys.executable,'-B',*(['-O'] if sys.flags.optimize else []),
            str(ROOT/'ml/scripts/verify_week5_delivery_v3.py'),'--evidence',str(self.directory),
            '--portable',str(self.directory),'--registry',str(self.rp),'--approval',str(self.ap),
            '--expected-approval-sha256',anchor,'--preparation',str(self.directory/'preparation'),
            '--session',str(self.directory),'--output',str(output)]
        child=subprocess.run(command,cwd=ROOT,capture_output=True)
        self.assertEqual(child.returncode,2,child.stderr.decode(errors='replace'))
        self.assertEqual(json.loads(output.read_text())['status'],'BLOCKED')

    def test_sv1_strict_boundary_coverage_and_oracle_rejected(self):
        row=lambda s,i:{'split':s,'sample_index':i,'max_abs_error':0,
                        'int8_oracle_exact':True,'fp16_oracle_exact':True}
        valid={'status':'SV1_WEEK5_TECHNICAL_ACCEPTANCE_PASS','scope':'REAL_MCU_CAPTURE',
            'primary_cases':220,'mixed_cases':16,'oracle_exact_cases':236,'unexplained_mismatches':0,
            'max_fp32_abs_error':0,'optimized_python':False,
            'primary_rows':[row(s,i) for s in range(11) for i in range(20)],'mixed_rows':[row(0,i) for i in range(16)],
            'historical_p2':{'primary_cases':20,'bitwise_cases':20},
            'accuracy_offline':{'status':'PASS_REUSED_UNCHANGED_SOURCE_AND_FROZEN_ASSETS','num_samples':8544,'splits':11},
            'evidence_sha256':{}}
        check_sv1_result(valid,False)
        for mutation in (lambda r:r.update(max_fp32_abs_error=1e-3),lambda r:r['primary_rows'].pop(),
                         lambda r:r['primary_rows'][1].update(int8_oracle_exact=False),
                         lambda r:r['historical_p2'].update(bitwise_cases=19),lambda r:r.update(oracle_exact_cases=235)):
            result=copy.deepcopy(valid); mutation(result)
            with self.assertRaises(ValueError): check_sv1_result(result,False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
