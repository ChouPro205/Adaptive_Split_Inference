#!/usr/bin/env python3
"""BlueZ central; echo or persistent real s2 tail. No lookup reference backend."""
from __future__ import annotations
import argparse,asyncio,json,platform,sys,time
from pathlib import Path
from common import ROOT,Worker,save,seal,sha
from service import Receiver
from sv1_log import STAGES,stage_for,sv1_row
sys.path.insert(0,str(ROOT/'contracts/i1v2_ref'))
import i1_ble_binding as ble
import i1v2_reference as i1
NAME='ASI-SV1';SERVICE='74e40001-0994-465c-bcd4-b94671a54935'
RX='74e40002-0994-465c-bcd4-b94671a54935';TX='74e40003-0994-465c-bcd4-b94671a54935'
def now():return int(time.monotonic()*1000)
async def run(a):
    from bleak import BleakClient,BleakScanner
    from importlib.metadata import version
    if version('bleak')!='0.22.3':raise ValueError('Use the pinned Bleak 0.22.3 venv for the tested MTU API')
    if platform.system()!='Linux' or platform.machine()!='aarch64':raise ValueError('Official service requires KV260 Linux aarch64')
    a.output.mkdir(parents=True,exist_ok=False)
    worker=None;receiver=None; rows=[];events=(a.output/'events.jsonl').open('x');peerlog=(a.output/'peer.jsonl').open('x')
    stage_logs={}
    if a.sv1_session:
        stage_logs={name:(a.output/(name+'.jsonl')).open('x') for name,_ in STAGES}
    def event(kind,**fields):
        events.write(json.dumps({'event':kind,'t_ms':now(),**fields})+'\n');events.flush()
    if a.mode=='inference':
        if not all([a.worker,a.deploy,a.cpu_ops]):raise ValueError('Inference needs worker/deploy/cpu-ops')
        key=None if a.key_file is None else a.key_file.read_bytes()
        if key is not None and len(key)!=32:raise ValueError('Invalid key length')
        worker=Worker(a.worker,a.deploy,a.cpu_ops,a.output/'worker.log');receiver=Receiver(worker,key)
    save(a.output/'run.json',{'scope':'KV260_BLE_'+a.mode.upper(),'target_mtu':a.mtu,'adapter':a.adapter,
        'source_sha256':sha(Path(__file__).read_bytes()),'sequence_scope':'in-memory per service lifetime; not authentication',
        'logits_encoding':'five float32 little-endian byte strings; label index 0..4',
        'scale_hash_encoding':'original-channel float32 little-endian bytes',
        'sv1_session':a.sv1_session,'target_address':a.address,
        'sv1_scale_hash_encoding':'original-channel float16 little-endian bytes',
        'tx_done_scope':'all fragments submitted via BlueZ Write Without Response; not proof of dongle reception',
        'stage_assignment':'ordered request counts 1,1,10,200; abort and review on any error/retry/missing request',
        'backend':None if worker is None else worker.metadata})
    deadline=time.monotonic()+a.max_s;attempts=0
    try:
        while time.monotonic()<deadline and (not a.expect or len(rows)<a.expect):
            print('SCANNING ASI-SV1',flush=True)
            device=await BleakScanner.find_device_by_filter(lambda d,v:
                v.local_name==NAME and SERVICE in [u.lower() for u in (v.service_uuids or [])]
                and (a.address is None or d.address.upper()==a.address.upper()),
                timeout=10,adapter=a.adapter)
            if device is None:event('scan_timeout');continue
            disconnected=asyncio.Event();reasm=ble.Reassembler(streams=frozenset({2 if a.mode=='echo' else 1}))
            queue=asyncio.Queue(maxsize=1);tids=ble.TransferIds();generation=attempts;attempts+=1
            def notified(_char,data):
                frame=reasm.feed(bytes(data),now())
                if frame:
                    try:queue.put_nowait((frame,now()))
                    except asyncio.QueueFull:event('rx_busy',peer=device.address)
            try:
                async with BleakClient(device,adapter=a.adapter,disconnected_callback=lambda c:disconnected.set()) as client:
                    # Bleak 0.22.3 BlueZ reports fallback MTU unless AcquireWrite/Notify is used.
                    # Pin API/version; acquisition occurs BEFORE start_notify and only for MTU.
                    await client._backend._acquire_mtu()
                    actual_mtu=client.mtu_size
                    if actual_mtu!=a.mtu:raise ValueError('MTU actual=%d target=%d; retain log, fix before G2'%(actual_mtu,a.mtu))
                    await client.start_notify(TX,notified)
                    event('connected',peer=device.address,att_mtu=actual_mtu)
                    print('BLE_READY peer=%s MTU=%d mode=%s'%(device.address,actual_mtu,a.mode),flush=True)
                    while client.is_connected and time.monotonic()<deadline and (not a.expect or len(rows)<a.expect):
                        try:(stream,frame),t_rx=await asyncio.wait_for(queue.get(),0.2)
                        except asyncio.TimeoutError:reasm.tick(now());continue
                        if a.mode=='echo':
                            try:i1.parse_envelope(frame,6380);response=frame;row={'result':'ECHO_OK','len':len(frame),'sha256':sha(frame),'t_rx_ms':t_rx}
                            except i1.Drop:response=None;row={'result':'DROP','t_rx_ms':t_rx}
                        else:response,row=await asyncio.to_thread(receiver.handle,device.address,frame,t_rx)
                        row.update(connection=generation,response_sent=False,t_tx_done_ms=None)
                        if response is not None:
                            try:
                                for fragment in ble.fragment(response,stream,tids.next(),actual_mtu):
                                    await client.write_gatt_char(RX,fragment,response=False)
                                row['response_sent']=True
                                row['t_tx_done_ms']=now()
                            except Exception as e:row['send_error']=type(e).__name__
                        if a.sv1_session:
                            stage=stage_for(len(rows));row['stage']=stage
                            stage_logs[stage].write(json.dumps(sv1_row(row),allow_nan=False)+'\n');stage_logs[stage].flush()
                        peerlog.write(json.dumps(row,allow_nan=False)+'\n');peerlog.flush();rows.append(row)
                        print('REQUEST %d result=%s'%(len(rows),row['result']),flush=True)
                        if a.sv1_session:
                            if row['result']!='OK' or not row['response_sent'] or row.get('cache_hit'):
                                raise ValueError('SV1 stage error/retry; stop and reconcile logs before another trial')
                            if len(rows) in (1,2,12,212):
                                print('STAGE_CAPTURED '+stage+'; SV1 must confirm dongle reception before next command',flush=True)
                            if len(rows)==212:
                                # Do not immediately tear down the last queued Write Without Response.
                                try:await asyncio.wait_for(disconnected.wait(),5)
                                except asyncio.TimeoutError:event('final_response_grace_elapsed',ms=5000)
                    event('connection_end',peer=device.address,reassembly=reasm.counters)
            except Exception as e:
                event('connection_error',error=str(e));print('BLE_ERROR '+str(e),flush=True)
                if isinstance(e,ValueError):raise
                await asyncio.sleep(1)
        status='CAPTURE_COMPLETE_REVIEW_REQUIRED' if a.expect and len(rows)==a.expect else 'STOPPED_REVIEW_REQUIRED'
        save(a.output/'summary.json',{'status':status,'mode':a.mode,'rows':len(rows),
            'ok':sum(r['result'] in ['OK','ECHO_OK'] and r['response_sent'] for r in rows),
            'connections':attempts,'expected':a.expect,'g2_acceptance':'PENDING_DEVICE_LOG_AND_CHECKER'})
    finally:
        if worker:worker.close()
        for stream in stage_logs.values():stream.close()
        events.close();peerlog.close();seal(a.output)
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['echo','inference'],required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--adapter',default='hci0');ap.add_argument('--mtu',type=int,default=247)
    ap.add_argument('--expect',type=int,default=0);ap.add_argument('--max-s',type=float,default=900)
    ap.add_argument('--worker',type=Path);ap.add_argument('--deploy',type=Path);ap.add_argument('--cpu-ops',type=Path)
    ap.add_argument('--key-file',type=Path)
    ap.add_argument('--address',help='Optional confirmed BLE peer address filter')
    ap.add_argument('--sv1-session',action='store_true',help='ONE P0, ONE P1, PAIRS 5, PAIRS 100 in one connection; 212 requests')
    a=ap.parse_args()
    if a.sv1_session:
        if a.mode!='inference' or a.key_file is None:ap.error('SV1 session requires inference and bench key')
        if a.expect not in (0,212):ap.error('SV1 session requires --expect 212')
        a.expect=212
    if a.expect<0 or a.max_s<=0 or not 23<=a.mtu<=517:ap.error('Invalid limits')
    try:asyncio.run(run(a))
    except KeyboardInterrupt:print('Stopped; preserve logs; no G2 acceptance claimed')
if __name__=='__main__':main()
