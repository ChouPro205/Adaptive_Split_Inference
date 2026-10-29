"""HOST contract/cache tests; mock tail, no radio or DPU evidence."""
import sys,json,struct,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'edge/server/week8'))
from service import Receiver,i1
from common import hex_logits
from sv1_log import stage_for,sv1_row
sys.path.insert(0,str(ROOT/'contracts/i2_ref'))
import i2_reference as i2
class Backend:
    def __init__(self):self.calls=0
    def infer(self,values):
        self.calls+=1
        return {'logits':[1.,1.,0.,-1.,-2.],'tail_ms':0.0}
class Week8Tests(unittest.TestCase):
    def setUp(self):
        self.backend=Backend();self.clock=[0.];self.key=bytes(range(32))
        self.r=Receiver(self.backend,self.key,clock=lambda:self.clock[0])
        self.split=self.r.profile.splits[258]
    def packet(self,rid=1,seq=None,q=None):
        q=bytes([1]*2880) if q is None else q
        descriptor=nonce=None
        if seq is not None:
            p=i2.Profile(self.r.profile.model_profile_id,258,16,180,65537,2880)
            descriptor=i2.descriptor(p);nonce=struct.pack('<IQ',131073,seq)
            q=i2.protect(q,descriptor,nonce,self.key,p)
        return i1.encode_request(rid,self.r.profile.model_profile_id,258,16,180,[.5]*16,q,descriptor,nonce)
    def test_plain_response_tie_and_hash_encodings(self):
        response,row=self.r.handle('device',self.packet(),10)
        self.assertEqual(len(response),64);self.assertEqual(row['label'],0)
        self.assertEqual(row['logits'],hex_logits([1,1,0,-1,-2]));self.assertEqual(row['rho'],'P0')
        self.assertEqual(i1.parse_response(response,1,6380)[0],'OK')
    def test_sv1_hash_and_log_adapter(self):
        import hashlib
        response,row=self.r.handle('device',self.packet(),10)
        self.assertEqual(row['scale_fp16_sha256'],hashlib.sha256(struct.pack('<16e',*([.5]*16))).hexdigest())
        row.update(response_sent=True,t_tx_done_ms=12,connection=0)
        log=sv1_row(row)
        self.assertEqual(log['scale_sha256'],row['scale_fp16_sha256'])
        self.assertEqual(log['logits'],[1.,1.,0.,-1.,-2.])
        self.assertEqual(log['ev'],'request');self.assertEqual(log['result'],'OK')
        row['response_sent']=False;row['t_tx_done_ms']=None
        self.assertEqual(sv1_row(row)['result'],'SEND_FAILED')
        self.assertIsNone(sv1_row(row)['t_tx_done_ms'])
        self.assertEqual([stage_for(i) for i in (0,1,2,11,12,211)],
                         ['one_p0','one_p1','pairs_5','pairs_5','pairs_100','pairs_100'])
        with self.assertRaises(ValueError):stage_for(212)
    def test_retry_after_reconnect_and_conflict(self):
        p=self.packet();first,_=self.r.handle('device',p,10);again,row=self.r.handle('device',p,20)
        self.assertEqual(first,again);self.assertTrue(row['cache_hit']);self.assertEqual(self.backend.calls,1)
        _,row=self.r.handle('device',self.packet(q=bytes([2]*2880)),30)
        self.assertEqual(row['result'],'DUPLICATE_CONFLICT');self.assertEqual(self.backend.calls,1)
    def test_p1_retry_then_sequence_reuse(self):
        p=self.packet(seq=5);first,row=self.r.handle('device',p,10)
        self.assertEqual(row['result'],'OK');self.assertEqual(row['sequence'],5)
        retry,row=self.r.handle('device',p,20);self.assertEqual(first,retry)
        _,row=self.r.handle('device',self.packet(rid=2,seq=5),30)
        self.assertEqual(row['result'],'INVALID_NONCE');self.assertEqual(self.backend.calls,1)
    def test_missing_key_crc_and_negative_q(self):
        r=Receiver(self.backend)
        _,row=r.handle('d',self.packet(seq=1),0);self.assertEqual(row['result'],'KEY_UNAVAILABLE')
        p=bytearray(self.packet());p[-1]^=1
        response,row=r.handle('d',bytes(p),0);self.assertIsNone(response);self.assertEqual(row['result'],'DROP')
        _,row=r.handle('d',self.packet(rid=2,q=bytes([128]*2880)),0)
        self.assertEqual(row['result'],'UNSUPPORTED_QUANTIZATION')
    def test_inprogress_attaches_and_new_request_busy(self):
        entered=threading.Event();release=threading.Event();responses=[]
        original=self.backend.infer
        def delayed(z):entered.set();release.wait(2);return original(z)
        self.backend.infer=delayed;p=self.packet()
        t=threading.Thread(target=lambda:responses.append(self.r.handle('d',p,0)[0]));t.start();self.assertTrue(entered.wait(1))
        _,row=self.r.handle('d',self.packet(rid=2),1);self.assertEqual(row['result'],'EDGE_BUSY')
        t2=threading.Thread(target=lambda:responses.append(self.r.handle('d',p,2)[0]));t2.start()
        release.set();t.join();t2.join();self.assertEqual(responses[0],responses[1]);self.assertEqual(self.backend.calls,1)
    def test_cache_bound_and_expiry(self):
        for i in range(1,19):self.r.handle('d',self.packet(rid=i),i)
        self.assertLessEqual(len(self.r.cache),16)
        self.clock[0]=61;self.r.handle('other',self.packet(),1)
        self.assertEqual(len(self.r.cache),1)
    def test_bad_semantics_are_cached_in_normative_order(self):
        p=bytearray(self.packet());p[10]=1;p=i1.recrc(bytes(p))
        first,row=self.r.handle('d',p,0);self.assertEqual(row['result'],'INVALID_LENGTH')
        again,row=self.r.handle('d',p,1);self.assertEqual(first,again);self.assertTrue(row['cache_hit'])
if __name__=='__main__':unittest.main()
