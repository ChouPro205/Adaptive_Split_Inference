"""Protocol fixtures on HOST; these are not 50 real vectors or KV260 evidence."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'contracts/i1v2_ref'))
import i1v2_reference as i1
V=json.loads((ROOT/'contracts/i1v2_ref/vectors.json').read_text())
SERVICE=ROOT/'edge/server/week7/serve.py'
class Checks(unittest.TestCase):
 def run_packet(self,packet,key=False):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'request.bin').write_bytes(packet)
   cmd=[sys.executable,'-B',str(SERVICE),'--repo',str(ROOT),'--request',str(p/'request.bin'),'--output',str(p/'out'),
        '--backend','reference','--model-package',str(ROOT/'ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1')]
   if key:cmd+=['--public-test-key']
   r=subprocess.run(cmd,capture_output=True,text=True)
   self.assertTrue((p/'out/result.json').is_file(),r.stderr)
   return json.loads((p/'out/result.json').read_text()),(p/'out/response.bin').read_bytes() if (p/'out/response.bin').exists() else None
 def test_identity_plain_and_p1(self):
  for name,key in [('plain_s10',False),('i2_s10',True)]:
   r,b=self.run_packet(bytes.fromhex(V['golden'][name]['packet_hex']),key)
   self.assertEqual(r['status'],'OK');self.assertEqual(r['logits'],[63.5,-31.75,0,2,-.125]);self.assertEqual(len(b),64)
 def test_crc_silent_drop(self):
  p=bytearray.fromhex(V['golden']['plain_s10']['packet_hex']);p[-1]^=1
  r,b=self.run_packet(bytes(p));self.assertEqual(r['status'],'DROP');self.assertIsNone(b)
 def test_version_error(self):
  p=bytearray.fromhex(V['golden']['plain_s10']['packet_hex']);p[4]=1
  r,b=self.run_packet(i1.recrc(bytes(p)));self.assertEqual(r['reason'],'UNSUPPORTED_VERSION');self.assertEqual(len(b),44)
 def test_missing_key(self):
  r,b=self.run_packet(bytes.fromhex(V['golden']['i2_s10']['packet_hex']))
  self.assertEqual(r['reason'],'KEY_UNAVAILABLE')
 def test_official_negative_and_pipeline_vectors(self):
  for case in V['request_negative']+V['pipeline']:
   with self.subTest(case=case['id']):
    r,b=self.run_packet(bytes.fromhex(case['packet_hex']),case.get('keys')=='public')
    actual=r['status'] if r['status'] in ('OK','DROP') else r.get('reason')
    self.assertEqual(actual,case['expected'])
 def test_negative_q(self):
  p=bytearray.fromhex(V['golden']['plain_s10']['packet_hex']);p[-5]=128
  r,b=self.run_packet(i1.recrc(bytes(p)));self.assertEqual(r['reason'],'UNSUPPORTED_QUANTIZATION')
if __name__=='__main__':unittest.main()
