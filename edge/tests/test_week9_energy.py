"""HOST mocks only. No real key, radio, VART/DPU or energy evidence."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'edge/server/week9_energy'))
import ble_energy as service
import phy

class SessionTests(unittest.TestCase):
    def trial(self, stop=200, gate_fails=False, disconnect=True, send_fails=False):
        state=dict(scan=0,clients=0,notify=0,gate=0,sent=0,infer=0)
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        path=Path(tmp.name);session=path/'session';session.mkdir()
        (session/'preparation.json').write_text(json.dumps(dict(service_commit='HOST_FIXTURE_ONLY')))
        (session/'expected_backend.json').write_text('{}')
        key=path/'fake_key';key.write_bytes(bytes(range(32)))
        device=types.SimpleNamespace(address='C8:F6:EE:EF:02:CF')
        class Scanner:
            @staticmethod
            async def find_device_by_filter(fn,**kwargs):
                state['scan']+=1
                assert fn(device,types.SimpleNamespace(local_name='ASI-SV1',service_uuids=[service.SERVICE]))
                return None if state['scan']<3 else device
        class Client:
            def __init__(self,*args,**kwargs):
                state['clients']+=1;self.callback=kwargs['disconnected_callback']
                self._backend=self;self.mtu_size=247;self.is_connected=True
            async def __aenter__(self):return self
            async def __aexit__(self,*args):self.is_connected=False
            async def _acquire_mtu(self):pass
            async def start_notify(self,uuid,cb):
                assert state['gate']==1
                state['notify']+=1;self.notified=cb
                asyncio.get_running_loop().call_soon(cb,None,b'frame')
            async def write_gatt_char(self,*args,**kwargs):
                if send_fails:raise RuntimeError('FAKE_SEND_FAILURE')
                state['sent']+=1
                if state['sent']<stop:
                    asyncio.get_running_loop().call_soon(self.notified,None,b'frame')
                elif disconnect:
                    self.is_connected=False
                    asyncio.get_running_loop().call_soon(self.callback,self)
        class Worker:
            metadata={}
            def __init__(self,*args):pass
            def close(self):state['closed']=True
        class Receiver:
            def __init__(self,*args):pass
            def handle(self,peer,packet,t_rx):
                state['infer']+=1;i=state['infer']-1
                return b'response',dict(request_id=i+1,rho='P1' if i%2==0 else 'P0',
                    sequence=i//2+1 if i%2==0 else None,result='OK',q_sha256='FAKE',
                    scale_fp16_sha256='FAKE',scale_sha256='FAKE',logits_float=[1.,0.,0.,0.,0.],
                    label=0,t_rx_ms=t_rx,len=3116,cache_hit=False)
        def gate(*args):
            state['gate']+=1
            if gate_fails:raise ValueError('FAKE_GATE_REJECTED')
            return 513
        async def inline(fn,*args):return fn(*args)
        a=types.SimpleNamespace(session=session,output=path/'run',worker='FAKE',deploy='FAKE',cpu_ops='FAKE',
            key_file=key,adapter='hci0',address=device.address,mtu=247,max_s=5,disconnect_s=.01)
        fake=types.SimpleNamespace(BleakScanner=Scanner,BleakClient=Client)
        with patch.dict(sys.modules,{'bleak':fake}),patch.object(service,'version',return_value='0.22.3'), \
             patch.object(service.platform,'system',return_value='Linux'),patch.object(service.platform,'machine',return_value='aarch64'), \
             patch.object(service,'Worker',Worker),patch.object(service,'Receiver',Receiver), \
             patch.object(service,'gate',side_effect=gate),patch.object(service.asyncio,'to_thread',inline), \
             patch.object(service.ble.Reassembler,'feed',return_value=(1,b'packet')), \
             patch.object(service.ble,'fragment',return_value=[b'fragment']),patch('builtins.print'):
            error=None
            try:asyncio.run(service.run(a))
            except Exception as e:error=e
        return state,a,error

    def test_200_rows_gate_before_notify_one_connection_no_extra_inference(self):
        state,a,error=self.trial()
        self.assertIsNone(error)
        self.assertEqual((state['scan'],state['clients'],state['gate'],state['infer'],state['sent']),(3,1,1,200,200))
        rows=[json.loads(s) for s in (a.output/'requests.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),200);self.assertEqual({r['connection'] for r in rows},{0})
        self.assertTrue(all(len(r['logits'])==5 and r['t_tx_done_ms']>=r['t_rx_ms'] for r in rows))
        summary=json.loads((a.output/'summary.json').read_text())
        self.assertEqual(summary['status'],'CAPTURE_COMPLETE_REVIEW_REQUIRED')
        self.assertTrue(summary['device_disconnect_observed'])
        self.assertTrue((a.output/'sha256sum_results.txt').exists())

    def test_early_disconnect_sealed_incomplete_without_reconnect(self):
        state,a,error=self.trial(stop=10)
        self.assertIsInstance(error,ValueError);self.assertEqual(state['clients'],1)
        self.assertEqual(state['scan'],3)
        self.assertEqual(json.loads((a.output/'summary.json').read_text())['requests'],10)

    def test_gate_reject_never_subscribes(self):
        state,a,error=self.trial(gate_fails=True)
        self.assertIsInstance(error,ValueError);self.assertEqual(state['notify'],0)
        self.assertEqual(state['infer'],0)

    def test_missing_device_disconnect_is_not_complete(self):
        state,a,error=self.trial(disconnect=False)
        self.assertIsInstance(error,TimeoutError)
        self.assertEqual(json.loads((a.output/'summary.json').read_text())['status'],'INCOMPLETE_REVIEW_REQUIRED')
        self.assertEqual(state['infer'],200)

    def test_send_error_still_logs_request_as_failed(self):
        state,a,error=self.trial(send_fails=True)
        self.assertIsInstance(error,ValueError)
        row=json.loads((a.output/'requests.jsonl').read_text().strip())
        self.assertEqual(row['result'],'SEND_FAILED');self.assertIsNone(row['t_tx_done_ms'])

class PhyTests(unittest.TestCase):
    def test_logs_each_read_actual_values_and_handle_little_endian(self):
        calls=[];reads=[b'\x01\x01',b'\x02\x02']
        def run(args,**kwargs):
            calls.append(args)
            if args[-1]=='con':text=' < LE C8:F6:EE:EF:02:CF handle 513 state 1 lm MASTER\n'
            elif '0x0032' in args:text='> HCI Event: 0x0f plen 4\n 00 01 32 20\n'
            else:
                value=reads.pop(0);text='> HCI Event: 0x0e plen 8\n 01 30 20 00 01 02 %02x %02x\n'%tuple(value)
            return types.SimpleNamespace(stdout=text,stderr='',returncode=0,check_returncode=lambda:None)
        with tempfile.TemporaryDirectory() as t,patch.object(phy.subprocess,'run',side_effect=run),patch.object(phy.time,'sleep'):
            self.assertEqual(phy.gate('hci0','C8:F6:EE:EF:02:CF',Path(t)),513)
            rows=[json.loads(s) for s in (Path(t)/'phy.jsonl').read_text().splitlines()]
            self.assertEqual([r['tx_phy'] for r in rows],['1M','2M'])
            self.assertTrue(all(r['event']=='read_phy' and isinstance(r['t_ms'],int) for r in rows))
            self.assertEqual([a for a in calls if '0x0032' in a][0][-7:-5],['0x01','0x02'])

    def test_rejected_set_stops_before_notify_gate(self):
        def run(args,**kwargs):
            text=(' < LE C8:F6:EE:EF:02:CF handle 16 state 1 lm MASTER\n' if args[-1]=='con'
                  else '> HCI Event: 0x0f plen 4\n 0c 01 32 20\n')
            return types.SimpleNamespace(stdout=text,stderr='',returncode=0,check_returncode=lambda:None)
        with tempfile.TemporaryDirectory() as t,patch.object(phy.subprocess,'run',side_effect=run):
            with self.assertRaises(ValueError):phy.gate('hci0','C8:F6:EE:EF:02:CF',Path(t))
            self.assertFalse((Path(t)/'phy.jsonl').exists())

if __name__=='__main__':unittest.main()
