"""HOST tests only: no radio, native worker, real key or DPU."""
import json
from pathlib import Path
import random
import statistics
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server/week9'))
import queue_sim as q
import analyze

ROOT=next(p for p in [Path.cwd(),*Path(__file__).resolve().parents]
          if (p/'edge/server/week8/ble_service.py').is_file())

class QueueTests(unittest.TestCase):
    def test_piecewise_poisson_seed_boundaries_and_mean(self):
        a=list(q.arrivals([(10,0),(10,5),(10,0)],42))
        self.assertEqual(a,list(q.arrivals([(10,0),(10,5),(10,0)],42)))
        self.assertTrue(all(10<=t<20 for t in a))
        counts=[len(list(q.arrivals([(10,5)],s))) for s in range(1000)]
        self.assertLess(abs(statistics.mean(counts)-50),1)
        self.assertLess(abs(statistics.variance(counts)-50),7)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'scenario.csv'
            for text in ('duration_s,lambda_jobs_per_s\n0,5\n',
                         'duration_s,lambda_jobs_per_s\n10,-1\n',
                         'duration_s,lambda_jobs_per_s\n10,nan\n'):
                p.write_text(text)
                with self.assertRaises(ValueError):q.scenario(p)

    def test_fifo_serialization_bounded_background_foreground_reserved(self):
        entered=threading.Event(); release=threading.Event(); calls=[]
        class Backend:
            def infer(self,x):
                calls.append(x)
                if x=='active': entered.set(); release.wait(2)
                return dict(logits=[0]*5,tail_ms=1.)
            def close(self):pass
        with tempfile.TemporaryDirectory() as t:
            d=q.Dispatcher(Backend(),Path(t),max_background=1)
            first=d.submit('active',background=True)
            self.assertTrue(entered.wait(1))
            second=d.submit('pending',background=True)
            self.assertIsNone(d.submit('dropped',background=True))
            foreground=d.submit('ble')
            self.assertEqual(d.snapshot()['queue_length_jobs'],2)
            release.set();self.assertTrue(foreground.done.wait(2))
            d.close()
            self.assertEqual(calls,['active','pending','ble'])
            summary=json.loads((Path(t)/'queue_summary.json').read_text())
            self.assertEqual(summary['background_dropped'],1)
            self.assertEqual(summary['completed'],3)

    def test_cancelled_job_does_not_run(self):
        entered=threading.Event(); release=threading.Event();calls=[]
        class Backend:
            def infer(self,x):
                calls.append(x);entered.set();release.wait(2)
                return dict(logits=[0]*5,tail_ms=1)
            def close(self):pass
        with tempfile.TemporaryDirectory() as t:
            d=q.Dispatcher(Backend(),Path(t),1)
            d.submit('active',True); self.assertTrue(entered.wait(1))
            job=d.submit('cancelled')
            with d.lock:job.cancelled=True
            release.set();self.assertTrue(job.done.wait(2));d.close()
            self.assertEqual(calls,['active'])
            self.assertIsInstance(job.error,TimeoutError)

class GateTests(unittest.TestCase):
    def test_rejected_phy_command_stops_gate(self):
        import phy_gate
        repo=ROOT
        sys.path.insert(0,str(repo/'edge/server/week8'))
        def run(args,**kwargs):
            text=(' < LE C8:F6:EE:EF:02:CF handle 16 state 1 lm MASTER\n' if args[-1]=='con'
                  else '> HCI Event: 0x0f plen 4\n 0c 01 32 20\n')
            class R:
                stdout=text;stderr='';returncode=0
                def check_returncode(self):pass
            return R()
        with tempfile.TemporaryDirectory() as t, patch('phy_gate.subprocess.run',side_effect=run):
            with self.assertRaises(ValueError):phy_gate.verify('hci0','C8:F6:EE:EF:02:CF',Path(t))
            self.assertFalse(any(r['event']=='PHY_GATE_OK' for r in analyze.rows(Path(t)/'phy_gate.jsonl')))

    def test_set_read_gate_and_handle_refresh(self):
        import phy_gate
        # Reuse the actual HCI parser from this checkout, not an imitation.
        repo=ROOT
        sys.path.insert(0,str(repo/'edge/server/week8'))
        peer='C8:F6:EE:EF:02:CF'; state={'handle':16};commands=[]
        def run(args,**kwargs):
            commands.append(args)
            if args[-1]=='con':
                text='Connections:\n < LE %s handle %d state 1 lm MASTER\n'%(peer,state['handle'])
            elif '0x0032' in args:
                text='> HCI Event: 0x0f plen 4\n 00 01 32 20\n'
            else:
                h=state['handle'];text='> HCI Event: 0x0e plen 8\n 01 30 20 00 %02x %02x 02 02\n'%(h&255,h>>8)
            class Result:
                stdout=text;stderr='';returncode=0
                def check_returncode(self):pass
            return Result()
        with tempfile.TemporaryDirectory() as t, patch('phy_gate.subprocess.run',side_effect=run):
            phy_gate.verify('hci0',peer,Path(t))
            state['handle']=513
            phy_gate.verify('hci0',peer,Path(t))
            reads=[a for a in commands if '0x0030' in a]
            self.assertEqual(reads[0][-2:],['0x10','0x00'])
            self.assertEqual(reads[1][-2:],['0x01','0x02'])
            events=analyze.rows(Path(t)/'phy_gate.jsonl')
            self.assertEqual(sum(r['event']=='PHY_GATE_OK' for r in events),2)

class AnalysisTests(unittest.TestCase):
    def test_fixture_not_acceptance_and_tamper_rejected(self):
        import hashlib
        def seal(p):
            (p/'sha256sum_results.txt').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n'
                for f in sorted(p.iterdir()) if f.is_file() and f.name!='sha256sum_results.txt'))
        with tempfile.TemporaryDirectory() as t:
            run=Path(t)/'queue';rec=Path(t)/'receiver';run.mkdir();rec.mkdir()
            (run/'queue_run.json').write_text(json.dumps(dict(config=dict(run_id='FIXTURE',receiver_id='SV1_PC'),backend='FAKE')))
            (run/'jobs.jsonl').write_text('');(run/'queue_summary.json').write_text('{}')
            state=dict(run_id='FIXTURE',seq_number=0,publisher_monotonic_ns=1_000_000_000)
            (run/'mqtt_sent.jsonl').write_text(json.dumps(dict(**state,publish_rc=0,schedule_late_ms=0))+'\n')
            ack=dict(run_id='FIXTURE',seq_number=0,publisher_send_ns=1_000_000_000,publisher_ack_ns=1_010_000_000,ack_rtt_ms=10)
            (run/'mqtt_ack.jsonl').write_text(json.dumps(ack)+'\n')
            (rec/'received.jsonl').write_text(json.dumps(dict(state=state,receiver_id='SV1_PC',retained=False))+'\n')
            seal(run);seal(rec)
            result=analyze.analyze(run,rec)
            self.assertEqual(result['mqtt']['status'],'DELIVERY_UPPER_BOUND_LT20MS_ALL_RECORDED')
            self.assertEqual(result['backend'],'FAKE')
            self.assertEqual(analyze.analyze(run)['mqtt']['status'],'NOT_YET_PROVEN')
            ack.update(publisher_ack_ns=1_030_000_000,ack_rtt_ms=30)
            (run/'mqtt_ack.jsonl').write_text(json.dumps(ack)+'\n');seal(run)
            self.assertEqual(analyze.analyze(run,rec)['mqtt']['status'],'NOT_YET_PROVEN')
            with (rec/'received.jsonl').open('a') as f:f.write('{}\n')
            with self.assertRaises(ValueError):analyze.analyze(run,rec)

class TraceTests(unittest.TestCase):
    def test_advertising_only_is_not_session_and_truncation_rejected(self):
        import struct,trace_check
        def record(payload):
            return struct.pack('>IIIIQ',len(payload),len(payload),3,0,1000000)+payload
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'trace.btsnoop'
            header=b'btsnoop\0'+struct.pack('>II',1,2001)
            p.write_bytes(header+record(b'\x3e\x01\x0d'))
            self.assertEqual(trace_check.audit(p)['connection'],0)
            p.write_bytes(header+record(b'\x3e\x01\x0a')+record(b'\x3e\x01\x0c'))
            self.assertEqual(trace_check.audit(p)['phy_update'],1)
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaises(ValueError):trace_check.audit(p)

class SnapshotTests(unittest.TestCase):
    def test_snapshot_ble_gate_precedes_notify_and_failure_does_not_subscribe(self):
        import asyncio,importlib.util,types
        prep_spec=importlib.util.spec_from_file_location('w9_prepare_under_test',ROOT/'edge/server/week9/prepare_runtime.py')
        prepare=importlib.util.module_from_spec(prep_spec);prep_spec.loader.exec_module(prepare)
        reference=ROOT/'edge/build_vai25/ket_qua_hien_tai/week8/g2/inputs/reference_s2.npz'
        if not reference.exists():self.skipTest('Verified reference NPZ is outside Git')
        before=(ROOT/'edge/server/week8/ble_service.py').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out=prepare.prepare(ROOT,Path(tmp)/'prepared',reference)
            self.assertEqual(before,(out/'source/edge/server/week8/ble_service.py').read_bytes())
            spec=importlib.util.spec_from_file_location('w9_snapshot_service',out/'source/edge/server/week9/ble_service.py')
            service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
            device=types.SimpleNamespace(address='C8:F6:EE:EF:02:CF')
            state={'gate':0,'notify':0}
            class Scanner:
                @staticmethod
                async def find_device_by_filter(*a,**kw):return device
            class Client:
                def __init__(self,*a,**kw):self._backend=self;self.mtu_size=247;self.is_connected=True
                async def __aenter__(self):return self
                async def __aexit__(self,*a):self.is_connected=False
                async def _acquire_mtu(self):pass
                async def start_notify(self,char,callback):
                    self.assert_gate=state['gate']
                    if not self.assert_gate:raise AssertionError('Subscribed before gate')
                    state['notify']+=1;asyncio.get_running_loop().call_soon(callback,None,b'frame')
                async def write_gatt_char(self,*a,**kw):pass
            def gate(*a):state['gate']+=1
            async def inline(fn,*a):return fn(*a)
            a=types.SimpleNamespace(output=Path(tmp)/'ble_ok',mode='echo',adapter='hci0',mtu=247,
                sv1_session=False,max_s=5,expect=1,address=device.address)
            fake=types.SimpleNamespace(BleakClient=Client,BleakScanner=Scanner)
            with patch.dict(sys.modules,{'bleak':fake}),patch('importlib.metadata.version',return_value='0.22.3'), \
                 patch('platform.system',return_value='Linux'),patch('platform.machine',return_value='aarch64'), \
                 patch.object(service.asyncio,'to_thread',inline),patch.object(service,'verify_phy',side_effect=gate), \
                 patch.object(service.ble.Reassembler,'feed',return_value=(2,b'frame')), \
                 patch.object(service.i1,'parse_envelope'),patch.object(service.ble,'fragment',return_value=[b'R']), \
                 patch('builtins.print'):
                asyncio.run(service.run(a))
                self.assertEqual(state,dict(gate=1,notify=1))
                a.output=Path(tmp)/'ble_rejected'
                with patch.object(service,'verify_phy',side_effect=ValueError('Controller rejected')):
                    with self.assertRaises(ValueError):asyncio.run(service.run(a))
                self.assertEqual(state['notify'],1)
            self.assertEqual(before,(ROOT/'edge/server/week8/ble_service.py').read_bytes())

if __name__=='__main__':unittest.main()
