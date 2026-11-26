import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server/week9'))
import oneway as m

S0=9_000_000_000_000_000
B0=3_000_000_000_000

def probes(drift=.00002,forward_ms=.1,reverse_ms=.2):
    result=[]
    for index in range(16):
        t=index*10_000_000_000
        f=int(forward_ms*1e6);r=int(reverse_ms*1e6);proc=50_000
        result.append(dict(s1_ns=S0+t,s4_ns=S0+t+f+proc+r,
            b2_ns=B0+round((1+drift)*(t+f)),b3_ns=B0+round((1+drift)*(t+f+proc)),
            clock_id='fixture',hostname='kv260-fixture',clock={'resolution_ns':1}))
    return result

class Tests(unittest.TestCase):
    def test_stop_file_finishes_receiver_cleanly_without_keyboard_interrupt(self):
        import importlib.util
        if importlib.util.find_spec('paho') is None:self.skipTest('Paho required')
        import paho.mqtt.client as mqtt
        import threading
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'recv';flag=root/'stop.flag'
            class Client:
                def __init__(self,*args,**kwargs):pass
                def connect(self,*args):self.on_connect(self,None,None,0,None)
                def subscribe(self,*args,**kwargs):self.on_subscribe(self,None,1,[SimpleNamespace(is_failure=False)],None)
                def loop_start(self):pass
                def disconnect(self):pass
                def loop_stop(self):pass
            ready=threading.Event();ready.set()
            probes=SimpleNamespace(thread=SimpleNamespace(start=lambda:None),ready=ready,mixed=False,count=10,errors=0,identity='fixture',close=lambda:None)
            args=SimpleNamespace(output=out,receiver_id='SV1_PC',role='sv1',network_label='MOCK',host='localhost',port=1905,clock_host='localhost',clock_port=1906,tcp_nodelay=False,stop_file=flag,expected_clock_id='fixture')
            def sleep(seconds):
                if seconds==.2:flag.write_text('stop')
            with patch.object(mqtt,'Client',Client),patch.object(m,'Probes',return_value=probes),patch.object(m.time,'sleep',side_effect=sleep),contextlib.redirect_stdout(io.StringIO()):m.receive(args)
            self.assertEqual(json.loads((out/'receiver.json').read_text())['status'],'STOPPED_BY_OPERATOR')
            m.verify(out)
            with self.assertRaisesRegex(ValueError,'already exists'):m.receive(args)
    def test_causal_bounds_allow_nonlinear_clock_without_point_estimate(self):
        # Local time -> board time is nonlinear but strictly increasing.
        p=probes(drift=0,forward_ms=1,reverse_ms=2)
        for q in p:
            for key in ('b2_ns','b3_ns'):
                t=(q[key]-B0)/1e9
                q[key]=B0+round((t+.001*t*t)*1e9)
        with self.assertRaisesRegex(ValueError,'CLOCK_MODEL_INCONSISTENT'):
            m.clock_model(p,1)
        model=m.causal_clock_model(p,1)
        # Publication at local t=55s, callback 8ms later.
        send=B0+round((55+.001*55*55)*1e9)
        lo,estimate,hi=m.bound_delay(model,S0+55_008_000_000,send,1)
        self.assertIsNone(estimate)
        self.assertLessEqual(lo,8);self.assertGreaterEqual(hi,8)
        with self.assertRaisesRegex(ValueError,'coverage'):
            m.bound_delay(model,S0,B0-1,1)
    def test_causal_analysis_has_null_point_statistics(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,recv=self.fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                result=m.analyze(SimpleNamespace(run=run,receiver=recv,output=root/'out',clock_method='causal'))
            self.assertEqual(result['status'],'CAUSAL_BOUNDS_ONLY_REVIEW_REQUIRED')
            self.assertEqual(result['one_way_ms']['n'],0)
            self.assertIsNone(result['one_way_ms']['mean'])
            self.assertEqual(result['threshold_20ms']['uncertain'],1)
            m.verify(root/'out')
    def test_causal_probe_reversal_rejected(self):
        p=probes();p[4]['b2_ns']=p[2]['b2_ns']
        with self.assertRaises(ValueError):m.causal_clock_model(p,1)
    def test_affine_drift_and_asymmetric_path_bound_true_delay(self):
        p=probes(forward_ms=1,reverse_ms=9);model=m.clock_model(p,1)
        for t in (1_000_000_000,55_000_000_000,149_000_000_000):
            send=B0+round(1.00002*(t-8_000_000))
            lo,est,hi=m.bound_delay(model,S0+t,send,1)
            self.assertLessEqual(lo,8.00016);self.assertGreaterEqual(hi,8.00016)
        self.assertLessEqual(model['drift_ppm_interval'][0],20)
        self.assertGreaterEqual(model['drift_ppm_interval'][1],20)
    def test_precise_calibration_does_not_add_ack_return_delay(self):
        model=m.clock_model(probes(drift=0),1)
        lo,est,hi=m.bound_delay(model,S0+50_000_000_000,B0+49_992_000_000,1)
        self.assertLess(hi,20);self.assertGreater(lo,7)
    def test_non_affine_step_is_rejected(self):
        p=probes();p[7]['b2_ns']+=1_000_000_000;p[7]['b3_ns']+=1_000_000_000
        with self.assertRaises(ValueError):m.clock_model(p,1)
    def test_restart_and_extrapolation_rejected(self):
        p=probes();p[3]['clock_id']='restart'
        with self.assertRaises(ValueError):m.clock_model(p,1)
        model=m.clock_model(probes(),1)
        with self.assertRaises(ValueError):m.bound_delay(model,S0-100,B0,1)
    def fixture(self,root):
        run=root/'queue';recv=root/'recv';run.mkdir();recv.mkdir()
        state=dict(run_id='fixture-run',seq_number=0,publisher_monotonic_ns=B0+49_992_000_000)
        (run/'mqtt_sent.jsonl').write_text(json.dumps(dict(state,publish_rc=0,schedule_late_ms=0))+'\n')
        # RTT intentionally enormous: one-way classification must ignore it.
        (run/'mqtt_ack.jsonl').write_text(json.dumps(dict(seq_number=0,run_id='fixture-run',receiver_id='SV1_PC',publisher_send_ns=state['publisher_monotonic_ns'],publisher_ack_ns=state['publisher_monotonic_ns']+900_000_000,ack_rtt_ms=900))+'\n')
        m.save(run/'queue_run.json',dict(config=dict(run_id='fixture-run',receiver_id='SV1_PC'),backend={'scope':'FIXTURE'}))
        m.save(run/'queue_summary.json',dict(completed=0))
        (recv/'received.jsonl').write_text(json.dumps(dict(state=state,receive_perf_ns=S0+50_000_000_000,receiver_id='SV1_PC',retained=False))+'\n')
        (recv/'clock_probes.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in probes(drift=0)))
        m.save(recv/'receiver.json',dict(status='STOPPED_BY_OPERATOR',mixed_clock=False,callback_errors=[],probe_errors=0,clock_id='fixture',receive_clock={'resolution_ns':1},source_sha256='fixture-source'))
        m.seal(run);m.seal(recv);return run,recv
    def test_analysis_matches_and_keeps_raw_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,recv=self.fixture(root);before={p:p.read_bytes() for base in (run,recv) for p in base.rglob('*') if p.is_file()}
            args=SimpleNamespace(run=run,receiver=recv,output=root/'analysis')
            with contextlib.redirect_stdout(io.StringIO()):result=m.analyze(args)
            self.assertEqual(result['threshold_20ms']['below'],1)
            self.assertEqual(result['matching']['complete'],True)
            self.assertNotIn('PASS',result['status']);m.verify(args.output)
            for p,b in before.items():self.assertEqual(p.read_bytes(),b)
            with self.assertRaises(FileExistsError):m.analyze(args)
    def test_server_receipt_identity_matched(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,recv=self.fixture(root);server=root/'server';server.mkdir()
            m.save(server/'server.json',dict(clock_id='fixture',source_sha256='fixture-source',status='STOPPED_BY_OPERATOR'))
            m.seal(server)
            args=SimpleNamespace(run=run,receiver=recv,clock_server=server,output=root/'out')
            with contextlib.redirect_stdout(io.StringIO()):result=m.analyze(args)
            self.assertTrue(result['matching']['complete'])
    def test_server_receipt_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,recv=self.fixture(root);server=root/'server';server.mkdir()
            m.save(server/'server.json',dict(clock_id='another-server',source_sha256='fixture-source',status='STOPPED_BY_OPERATOR'))
            m.seal(server)
            with self.assertRaises(ValueError):m.analyze(SimpleNamespace(run=run,receiver=recv,clock_server=server,output=root/'out'))
    def test_payload_tamper_and_wrong_run_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,recv=self.fixture(root)
            row=json.loads((recv/'received.jsonl').read_text());row['state']['run_id']='wrong'
            (recv/'received.jsonl').write_text(json.dumps(row)+'\n');m.seal(recv)
            with self.assertRaises(ValueError):m.analyze(SimpleNamespace(run=run,receiver=recv,output=root/'out'))
    def test_gateway_identity_and_label_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,recv=self.fixture(root)
            meta=json.loads((run/'queue_run.json').read_text());meta['config']['receiver_id']='GW_TRUNG';m.save(run/'queue_run.json',meta)
            row=json.loads((recv/'received.jsonl').read_text());row['receiver_id']='GW_TRUNG';(recv/'received.jsonl').write_text(json.dumps(row)+'\n')
            rm=json.loads((recv/'receiver.json').read_text());rm.update(receiver_id='GW_TRUNG',role='gateway',network_label='PC_WIFI_KV260_LAN',hostname='host-fixture');m.save(recv/'receiver.json',rm)
            ack=json.loads((run/'mqtt_ack.jsonl').read_text());ack['receiver_id']='GW_TRUNG';(run/'mqtt_ack.jsonl').write_text(json.dumps(ack)+'\n');m.seal(run);m.seal(recv)
            with contextlib.redirect_stdout(io.StringIO()):r=m.analyze(SimpleNamespace(run=run,receiver=recv,output=root/'out'))
            self.assertEqual(r['receiver']['id'],'GW_TRUNG');self.assertEqual(r['receiver']['role'],'gateway')
            self.assertEqual(r['one_way_ms']['p99'],r['one_way_ms']['max'])
            self.assertEqual(r['ack_diagnostic']['n_at_or_above_20'],1)
            self.assertEqual(r['threshold_20ms']['below'],1)
    def test_receiver_callback_uses_gateway_identity_and_writes_before_ack(self):
        import importlib.util
        if importlib.util.find_spec('paho') is None:self.skipTest('Paho required for callback API fixture')
        from unittest.mock import patch
        import paho.mqtt.client as mqtt
        import threading
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'receiver';published=[]
            class Sock:
                value=0
                def setsockopt(self,*args):self.value=args[-1]
                def getsockopt(self,*args):return self.value
            class Client:
                def __init__(self,*args,**kwargs):self.client_id=kwargs['client_id']
                def connect(self,*args):
                    self.on_socket_open(self,None,Sock());self.on_connect(self,None,None,0,None)
                def subscribe(self,*args,**kwargs):self.on_subscribe(self,None,1,[SimpleNamespace(is_failure=False)],None)
                def loop_start(self):self.on_message(self,None,SimpleNamespace(payload=json.dumps(dict(run_id='fixture',seq_number=0)).encode(),retain=False))
                def publish(self,topic,payload,**kwargs):
                    row=json.loads((out/'received.jsonl').read_text());assert row['receiver_id']=='GW_TRUNG'
                    published.append(json.loads(payload))
                def disconnect(self):pass
                def loop_stop(self):pass
            ready=threading.Event();ready.set()
            probes=SimpleNamespace(thread=SimpleNamespace(start=lambda:None),ready=ready,mixed=False,count=10,errors=0,identity='fixture',close=lambda:None)
            args=SimpleNamespace(output=out,receiver_id='GW_TRUNG',role='gateway',network_label='HOST_FIXTURE_ONLY',host='127.0.0.1',port=1891,clock_host='127.0.0.1',clock_port=1893,tcp_nodelay=True)
            with patch.object(mqtt,'Client',Client),patch.object(m,'Probes',return_value=probes),patch.object(m.time,'sleep',side_effect=[KeyboardInterrupt,None]),contextlib.redirect_stdout(io.StringIO()):m.receive(args)
            self.assertEqual(published[0]['receiver_id'],'GW_TRUNG')
            meta=json.loads((out/'receiver.json').read_text());self.assertEqual(meta['role'],'gateway');self.assertEqual(meta['tcp_nodelay_actual'],1)
            self.assertEqual(meta['callback_errors'],[])
    def test_unsealed_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            run,recv=self.fixture(Path(d));(recv/'received.jsonl').write_text('tampered')
            with self.assertRaises(ValueError):m.verify(recv)
if __name__=='__main__':unittest.main()
