"""App-level MQTT one-way estimates with continuous four-timestamp clock calibration.
No system clock changes. Delay intervals are conditional on an affine clock model.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import platform
import socket
import socketserver
import statistics
import threading
import time
import uuid


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(folder):
    folder=Path(folder)
    (folder/'sha256sum_results.txt').write_text(''.join(sha(p)+'  '+p.relative_to(folder).as_posix()+'\n'
        for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='sha256sum_results.txt'))


def verify(folder):
    folder=Path(folder).resolve();listed=set()
    for line in (folder/'sha256sum_results.txt').read_text().splitlines():
        digest,name=line.split('  ',1);p=folder/name
        if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or name in listed or p.is_symlink() or not p.resolve().is_relative_to(folder):
            raise ValueError('Unsafe checksum path')
        if sha(p)!=digest:raise ValueError('Checksum mismatch: '+str(p))
        listed.add(name)
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.name!='sha256sum_results.txt'}
    if listed!=actual:raise ValueError('Inventory differs from actual files')


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def stats(values):
    v=sorted(values)
    if not v:return dict(n=0,mean=None,std=None,p50=None,p95=None,p99=None,max=None,min=None)
    return dict(n=len(v),mean=statistics.mean(v),std=statistics.stdev(v) if len(v)>1 else 0.,
                p50=v[max(0,math.ceil(.50*len(v))-1)],p95=v[max(0,math.ceil(.95*len(v))-1)],p99=v[max(0,math.ceil(.99*len(v))-1)],max=max(v),min=min(v))


def info(name):
    obj=time.get_clock_info(name)
    return dict(implementation=obj.implementation,resolution_ns=obj.resolution*1e9,
                monotonic=obj.monotonic,adjustable=obj.adjustable)


def clock_server(args):
    stop_file=getattr(args,'stop_file',None)
    if stop_file and stop_file.exists():raise ValueError('Stop file already exists; use a new session')
    output=args.output;output.mkdir(parents=True,exist_ok=False)
    identity=str(uuid.uuid4())
    metadata=dict(clock_id=identity,hostname=socket.gethostname(),machine=platform.machine(),
        python=platform.python_version(),clock=info('monotonic'),source_sha256=sha(__file__),
        endpoint='127.0.0.1:'+str(args.port),status='STARTED')
    if not metadata['clock']['monotonic']:raise ValueError('Monotonic clock required')
    save(output/'server.json',metadata)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(10);self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            while True:
                try:line=self.rfile.readline(4096)
                except (TimeoutError,OSError):return
                if not line:return
                b2=time.monotonic_ns()
                try:request=json.loads(line)
                except (ValueError,UnicodeDecodeError):return
                if not isinstance(request,dict) or not isinstance(request.get('seq'),int):return
                response=dict(seq=request['seq'],b2_ns=b2,clock_id=identity,clock=metadata['clock'],hostname=metadata['hostname'])
                response['b3_ns']=time.monotonic_ns()
                try:self.wfile.write((json.dumps(response)+'\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError,OSError):return
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address=True
        daemon_threads=True
    try:
        with Server(('127.0.0.1',args.port),Handler) as server:
            print('CLOCK_SERVER_READY',metadata['endpoint'],metadata['hostname'],flush=True)
            if stop_file:
                server.timeout=.2
                while not stop_file.exists():server.handle_request()
                metadata['status']='STOPPED_BY_OPERATOR'
            else:server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:metadata['status']='STOPPED_BY_OPERATOR'
    except BaseException:
        metadata['status']='FAILED';raise
    finally:
        save(output/'server.json',metadata);seal(output)


class Probes:
    def __init__(self,host,port,folder):
        self.host=host;self.port=port;self.folder=folder;self.stop=threading.Event();self.ready=threading.Event()
        self.count=0;self.errors=0;self.identity=None;self.mixed=False
        self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        seq=0
        with (self.folder/'clock_probes.jsonl').open('x') as log,(self.folder/'clock_errors.jsonl').open('x') as errors:
            while not self.stop.is_set():
                try:
                    with socket.create_connection((self.host,self.port),timeout=2) as sock:
                        sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                        with sock.makefile('rb') as f:
                            while not self.stop.is_set():
                                message=(json.dumps({'seq':seq})+'\n').encode()
                                s1=time.perf_counter_ns();sock.sendall(message)
                                line=f.readline(4096);s4=time.perf_counter_ns()
                                response=json.loads(line)
                                if response['seq']!=seq:raise ValueError('Probe sequence mismatch')
                                identity=response['clock_id']
                                if self.identity is None:self.identity=identity
                                if identity!=self.identity:self.mixed=True;raise ValueError('Clock server restarted')
                                log.write(json.dumps(dict(response,s1_ns=s1,s4_ns=s4))+'\n');log.flush()
                                seq+=1;self.count+=1
                                if self.count>=10:self.ready.set()
                                self.stop.wait(.05 if self.count<10 else .2)
                except (OSError,ValueError,KeyError) as e:
                    self.errors+=1;errors.write(json.dumps(dict(error=repr(e),local_perf_ns=time.perf_counter_ns()))+'\n');errors.flush()
                    if self.mixed:return
                    self.stop.wait(.2)
    def close(self):
        self.stop.set();self.thread.join(5)
        if self.thread.is_alive():raise RuntimeError('Probe writer did not stop; do not seal incomplete files')


def receive(args):
    import paho.mqtt.client as mqtt
    stop_file=getattr(args,'stop_file',None)
    if stop_file and stop_file.exists():raise ValueError('Stop file already exists; use a new capture')
    output=args.output;output.mkdir(parents=True,exist_ok=False)
    receiver_id=args.receiver_id
    if not receiver_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in receiver_id):
        raise ValueError('Use a non-empty ASCII receiver identifier')
    metadata=dict(status='STARTED',receiver_id=receiver_id,role=args.role,network_label=args.network_label,hostname=socket.gethostname(),python=platform.python_version(),platform=platform.system(),machine=platform.machine(),
        receive_clock=info('perf_counter'),source_sha256=sha(__file__),broker=dict(host=args.host,port=args.port),
        calibration=dict(host=args.clock_host,port=args.clock_port,clock_model='affine mapping; causal four-timestamp constraints; no equal-path assumption'),
        timestamp_boundary='perf_counter_ns at entry to MQTT on_message; before parse/write/ACK')
    log=(output/'received.jsonl').open('x');probes=Probes(args.clock_host,args.clock_port,output)
    subscribed=threading.Event();callback_errors=[]
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='w9-'+receiver_id)
    topic='adaptive_split/edge/KV260_NODE_01/status'
    def connect(c,u,f,reason,props):
        if reason==0:c.subscribe(topic,qos=0)
    def subscribe(c,u,mid,reasons,props):
        if reasons and all(not r.is_failure for r in reasons):subscribed.set()
    def message(c,u,msg):
        perf=time.perf_counter_ns()
        try:
            state=json.loads(msg.payload)
            log.write(json.dumps(dict(receive_perf_ns=perf,receive_unix_ns=time.time_ns(),receive_monotonic_ns=time.monotonic_ns(),
                receiver_id=receiver_id,retained=bool(msg.retain),state=state))+'\n');log.flush()
            c.publish(topic+'/ack',json.dumps(dict(run_id=state['run_id'],seq_number=state['seq_number'],receiver_id=receiver_id)),qos=0,retain=False)
        except BaseException as e:callback_errors.append(repr(e))
    client.on_connect=connect;client.on_subscribe=subscribe;client.on_message=message
    metadata['tcp_nodelay_requested']=args.tcp_nodelay
    if args.tcp_nodelay:
        def socket_open(c,u,sock):
            sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            metadata['tcp_nodelay_actual']=sock.getsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY)
            if metadata['tcp_nodelay_actual']!=1:raise RuntimeError('Receiver TCP_NODELAY not active')
            print('MQTT_TCP_NODELAY=1',flush=True)
        client.on_socket_open=socket_open
    probes.thread.start()
    try:
        if not probes.ready.wait(15):raise RuntimeError('No clock calibration; do not start publisher')
        if probes.mixed:raise RuntimeError('Clock server identity changed')
        if getattr(args,'expected_clock_id',None) and probes.identity!=args.expected_clock_id:
            raise RuntimeError('Clock restarted since preflight; do not start publisher')
        client.connect(args.host,args.port,30);client.loop_start()
        if not subscribed.wait(10):raise RuntimeError('No MQTT SUBACK; do not start publisher')
        print(('SV1_ONEWAY_READY' if receiver_id=='SV1_PC' else 'GATEWAY_ONEWAY_READY')+' receiver='+receiver_id+'; MQTT subscribed and clock probes active',flush=True)
        while True:
            time.sleep(.2)
            if probes.mixed or callback_errors:raise RuntimeError('Capture failed: '+str(callback_errors))
            if stop_file and stop_file.exists():
                metadata['status']='STOPPED_BY_OPERATOR';break
    except KeyboardInterrupt:metadata['status']='STOPPED_BY_OPERATOR'
    except BaseException:
        metadata['status']='FAILED';raise
    finally:
        client.disconnect();client.loop_stop()
        # Continue calibration after last MQTT callback to bracket its timestamp.
        time.sleep(1);probes.close();log.close()
        metadata.update(probe_count=probes.count,probe_errors=probes.errors,clock_id=probes.identity,mixed_clock=probes.mixed,callback_errors=callback_errors)
        save(output/'receiver.json',metadata);seal(output)
        print('ONEWAY_RECEIVER_SAVED',output,flush=True)


def clip(poly,A,B,C):
    """Intersect polygon with A*x+B*y<=C. Variables: relative clock slope, offset ms."""
    result=[]
    if not poly:return result
    prev=poly[-1];pv=A*prev[0]+B*prev[1]-C
    for curr in poly:
        cv=A*curr[0]+B*curr[1]-C
        if (pv<=1e-9)!=(cv<=1e-9):
            ratio=pv/(pv-cv);result.append((prev[0]+ratio*(curr[0]-prev[0]),prev[1]+ratio*(curr[1]-prev[1])))
        if cv<=1e-9:result.append(curr)
        prev,pv=curr,cv
    return result


def clock_model(probes,receiver_resolution_ns):
    if len(probes)<2:raise ValueError('Need calibration before and after capture')
    if len({p['clock_id'] for p in probes})!=1:raise ValueError('Mixed board clocks')
    if len({p['hostname'] for p in probes})!=1:raise ValueError('Mixed board hosts')
    s0=probes[0]['s1_ns'];b0=probes[0]['b2_ns'];lower=[];upper=[]
    for p in probes:
        if not (p['s1_ns']<p['s4_ns'] and p['b2_ns']<=p['b3_ns']):raise ValueError('Invalid probe time order')
        eps=(receiver_resolution_ns+p['clock']['resolution_ns'])/1e6
        x1=(p['s1_ns']-s0)/1e6;x4=(p['s4_ns']-s0)/1e6
        y2=(p['b2_ns']-b0)/1e6;y3=(p['b3_ns']-b0)/1e6
        # B(S)=B0+(S-S0)+d*(S-S0)+c. All transport delays non-negative.
        lower.append((x4,y3-x4-eps));upper.append((x1,y2-x1+eps))
    dlo=-1.;dhi=float('inf')
    for xl,lo in lower:
        for xu,hi in upper:
            dx=xu-xl;dy=hi-lo
            if abs(dx)<1e-12:
                if dy < -1e-9:raise ValueError('CLOCK_MODEL_INCONSISTENT')
            elif dx>0:dhi=min(dhi,dy/dx)
            else:dlo=max(dlo,dy/dx)
    if not math.isfinite(dhi) or dlo>dhi:raise ValueError('CLOCK_MODEL_INCONSISTENT')
    xl,lo=lower[0];xu,hi=upper[0]
    cmin=min(lo-dlo*xl,lo-dhi*xl);cmax=max(hi-dlo*xu,hi-dhi*xu)
    poly=[(dlo,cmin),(dhi,cmin),(dhi,cmax),(dlo,cmax)]
    for x,value in lower:poly=clip(poly,-x,-1,-value)
    for x,value in upper:poly=clip(poly,x,1,value)
    if not poly:raise ValueError('CLOCK_MODEL_INCONSISTENT')
    return dict(s0_ns=s0,b0_ns=b0,vertices=poly,s_min_ns=min(p['s1_ns'] for p in probes),s_max_ns=max(p['s4_ns'] for p in probes),
        drift_ppm_interval=[min(d for d,c in poly)*1e6,max(d for d,c in poly)*1e6],
        model='affine relation during capture; all causal probe intervals feasible; not external traceable synchronization',
        asymmetry='No equal forward/reverse network delay assumption; interval includes observed calibration path ambiguity',
        limitation='Clock nonlinearity between probes and unmodelled timestamp accuracy cannot be ruled out by this software alone')


def causal_clock_model(probes,receiver_resolution_ns):
    """Bounds from event order only; no constant cross-clock rate assumption."""
    if len(probes)<2:raise ValueError('Need calibration before and after capture')
    if len({p['clock_id'] for p in probes})!=1 or len({p['hostname'] for p in probes})!=1:
        raise ValueError('Mixed board clocks/hosts')
    for i,p in enumerate(probes):
        if not (p['s1_ns']<p['s4_ns'] and p['b2_ns']<=p['b3_ns']):
            raise ValueError('Invalid probe time order')
        if i and (p['s1_ns']<=probes[i-1]['s4_ns'] or p['b2_ns']<probes[i-1]['b3_ns']):
            raise ValueError('Probe clock order invalid')
    return dict(method='causal_order_bounds',anchors=probes,
        model='Causal event order on monotonic clocks; no affine rate fit',
        limitation='Milliseconds use receiver clock; its physical accuracy is not externally verified. No point latency estimate.')


def bound_delay(model,receive_ns,send_ns,receive_resolution_ns):
    if model.get('method')=='causal_order_bounds':
        # A probe replied before publication implies s1 <= publication.
        # A probe handled after publication implies publication <= s4.
        # Both inequalities are expressed on the receiver clock, without
        # converting board time differences to receiver time differences.
        before=[p['s1_ns'] for p in model['anchors'] if p['b3_ns']+p['clock']['resolution_ns']<send_ns]
        after=[p['s4_ns'] for p in model['anchors'] if p['b2_ns']-p['clock']['resolution_ns']>send_ns]
        if not before or not after:raise ValueError('Publication outside causal calibration coverage')
        first=max(before);last=min(after)
        if first>last:raise ValueError('Causal clock order inconsistent')
        eps=2*receive_resolution_ns/1e6
        lo=max(0.,(receive_ns-last)/1e6-eps)
        hi=(receive_ns-first)/1e6+eps
        if hi<lo:raise ValueError('Receive precedes causal publication bound')
        return lo,None,hi
    if not model['s_min_ns']<=receive_ns<=model['s_max_ns']:raise ValueError('Receive outside calibration coverage')
    x=(receive_ns-model['s0_ns'])/1e6
    delta_ms=(model['b0_ns']-send_ns)/1e6+x
    values=[delta_ms+d*x+c for d,c in model['vertices']]
    lo=min(values)-receive_resolution_ns/1e6;hi=max(values)+receive_resolution_ns/1e6
    if hi < -1e-6:raise ValueError('Negative delay inconsistent with calibrated clock/model')
    lo=max(0.,lo);hi=max(0.,hi)
    return lo,(lo+hi)/2,hi


def analyze(args):
    verify(args.run);verify(args.receiver)
    meta=json.loads((args.run/'queue_run.json').read_text());recv_meta=json.loads((args.receiver/'receiver.json').read_text())
    if recv_meta['status']!='STOPPED_BY_OPERATOR' or recv_meta['mixed_clock'] or recv_meta['callback_errors']:raise ValueError('Receiver did not finish cleanly')
    if getattr(args,'clock_server',None):
        verify(args.clock_server)
        server=json.loads((args.clock_server/'server.json').read_text())
        if server['clock_id']!=recv_meta['clock_id'] or server['source_sha256']!=recv_meta['source_sha256']:
            raise ValueError('Server/receiver clock identity or source mismatch')
        if server['status']!='STOPPED_BY_OPERATOR':raise ValueError('Clock server receipt not closed cleanly')
    sent=rows(args.run/'mqtt_sent.jsonl');received=rows(args.receiver/'received.jsonl')
    if not sent:raise ValueError('No sent messages')
    rid=meta['config']['run_id']
    if {r['state']['run_id'] for r in received}!={rid}:raise ValueError('Wrong/multiple receiver run_ids')
    send_by={r['seq_number']:r for r in sent};rec_by={r['state']['seq_number']:r for r in received}
    if len(send_by)!=len(sent) or len(rec_by)!=len(received):raise ValueError('Duplicate sequence')
    for seq,r in rec_by.items():
        if seq not in send_by or r['retained'] or r['receiver_id']!=meta['config']['receiver_id']:raise ValueError('Wrong receiver/retained/unmatched sequence')
        if r['state']!={k:v for k,v in send_by[seq].items() if k not in ('publish_rc','schedule_late_ms')}:raise ValueError('Receiver payload differs from source')
    probes=rows(args.receiver/'clock_probes.jsonl')
    causal=getattr(args,'clock_method','affine')=='causal'
    model=(causal_clock_model if causal else clock_model)(probes,recv_meta['receive_clock']['resolution_ns'])
    calibration_gaps=[(b['s1_ns']-a['s1_ns'])/1e6 for a,b in zip(probes,probes[1:])]
    if any(g<=0 for g in calibration_gaps):raise ValueError('Calibration counter order invalid')
    if recv_meta['clock_id']!={p['clock_id'] for p in probes}.pop():raise ValueError('Clock metadata mismatch')
    per=[]
    for seq,r in sorted(rec_by.items()):
        lo,estimate,hi=bound_delay(model,r['receive_perf_ns'],send_by[seq]['publisher_monotonic_ns'],recv_meta['receive_clock']['resolution_ns'])
        per.append(dict(seq_number=seq,run_id=rid,lower_ms=lo,estimate_ms=estimate,upper_ms=hi,
            comparison='BELOW_20_WITHIN_CLOCK_MODEL' if hi<20 else 'AT_OR_ABOVE_20_WITHIN_CLOCK_MODEL' if lo>=20 else 'UNCERTAIN_AROUND_20'))
    complete=set(send_by)==set(rec_by)
    receive_times=[r['receive_perf_ns'] for r in received]
    if any(b<a for a,b in zip(receive_times,receive_times[1:])):raise ValueError('Receiver clock went backwards')
    gaps=[(b-a)/1e6 for a,b in zip(receive_times,receive_times[1:])]
    acks=rows(args.run/'mqtt_ack.jsonl') if (args.run/'mqtt_ack.jsonl').exists() else []
    seen_ack=set()
    for a in acks:
        seq=a['seq_number']
        if seq in seen_ack or seq not in send_by or a['receiver_id']!=meta['config']['receiver_id'] or a['run_id']!=rid:
            raise ValueError('ACK identity/sequence mismatch')
        if a['publisher_send_ns']!=send_by[seq]['publisher_monotonic_ns'] or a['publisher_ack_ns']<a['publisher_send_ns'] or a['ack_rtt_ms']!=(a['publisher_ack_ns']-a['publisher_send_ns'])/1e6:
            raise ValueError('ACK timing mismatch')
        seen_ack.add(seq)
    result=dict(scope='application publication loop timestamp on KV260 -> entry to receiver MQTT callback; ACK excluded',run_id=rid,
        receiver=dict(id=recv_meta.get('receiver_id',meta['config']['receiver_id']),role=recv_meta.get('role','unspecified'),hostname=recv_meta.get('hostname','not recorded'),network_label=recv_meta.get('network_label','not recorded')),
        status='ONEWAY_ESTIMATES_REVIEW_REQUIRED',percentile_method='nearest rank',group_acceptance='PDF does not specify mean/p95/max or allowed failure fraction; no automatic WEEK9_PASS/FAIL',
        backend=meta['backend'],queue=json.loads((args.run/'queue_summary.json').read_text()),
        matching=dict(sent=len(sent),received=len(received),complete=complete,publish_errors=sum(r['publish_rc']!=0 for r in sent)),
        publish_interval_ms=stats([(b['publisher_monotonic_ns']-a['publisher_monotonic_ns'])/1e6 for a,b in zip(sent,sent[1:])]),
        receive_interval_ms=stats(gaps),
        ack_rtt_diagnostic_ms=stats([a['ack_rtt_ms'] for a in acks]),
        ack_diagnostic=dict(count=len(acks),complete=set(send_by)==seen_ack,n_at_or_above_20=sum(a['ack_rtt_ms']>=20 for a in acks),meaning='diagnostic round trip only; not the one-way acceptance criterion'),
        one_way_ms=stats([p['estimate_ms'] for p in per if p['estimate_ms'] is not None]),lower_ms=stats([p['lower_ms'] for p in per]),upper_ms=stats([p['upper_ms'] for p in per]),
        interval_width_ms=stats([p['upper_ms']-p['lower_ms'] for p in per]),
        threshold_20ms=dict(below=sum(p['upper_ms']<20 for p in per),at_or_above=sum(p['lower_ms']>=20 for p in per),uncertain=sum(p['lower_ms']<20<=p['upper_ms'] for p in per)),
        calibration=dict(probes=len(probes),errors=recv_meta['probe_errors'],hostname=probes[0]['hostname'],max_probe_gap_ms=max(calibration_gaps,default=0),receive_clock=recv_meta['receive_clock'],model={k:v for k,v in model.items() if k!='anchors'}),
        measurement_limitations=['Intervals conditional on affine monotonic-clock relation and reported clock resolutions; not an externally synchronized instrument.',
            'Calibration traffic is additional to the MQTT session and is recorded.',
            'Original publisher timestamp precedes payload construction/publish; this includes that small application overhead.',
            'Incomplete receive/publish errors must be reported even when delay statistics look good.'])
    if causal:
        result['status']='CAUSAL_BOUNDS_ONLY_REVIEW_REQUIRED'
        result['measurement_limitations'][0]=model['model']+'. '+model['limitation']
        result['measurement_limitations'].append('No affine point estimates: one_way_ms fields and estimate_ms are null. Wide intervals may not resolve 20 ms.')
    if (args.run/'jobs.jsonl').exists():
        jobs=rows(args.run/'jobs.jsonl')
        done=[r for r in jobs if r.get('event')=='finished' and not r.get('cancelled') and r.get('error') is None]
        result['service_ms']=stats([r['service_ms'] for r in done])
        result['background_queue_wait_ms']=stats([r['queue_wait_ms'] for r in done if r['kind']=='background'])
    args.output.mkdir(parents=True,exist_ok=False)
    save(args.output/'summary.json',result)
    (args.output/'oneway_samples.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in per))
    save(args.output/'source_paths.json',dict(run=str(args.run.resolve()),receiver=str(args.receiver.resolve()),clock_server=None if not getattr(args,'clock_server',None) else str(args.clock_server.resolve()),analyzer_sha256=sha(__file__)))
    seal(args.output)
    print(json.dumps(result,indent=2));return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('clock-server');a.add_argument('--port',type=int,default=1890);a.add_argument('--output',type=Path,required=True);a.add_argument('--stop-file',type=Path)
    a=sub.add_parser('receive');a.add_argument('--host',default='127.0.0.1');a.add_argument('--port',type=int,default=1885);a.add_argument('--clock-host',default='127.0.0.1');a.add_argument('--clock-port',type=int,default=1890);a.add_argument('--tcp-nodelay',action='store_true');a.add_argument('--receiver-id',default='SV1_PC');a.add_argument('--role',choices=['sv1','gateway','unspecified'],default='unspecified');a.add_argument('--network-label',default='not recorded');a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('analyze');a.add_argument('--run',type=Path,required=True);a.add_argument('--receiver',type=Path,required=True);a.add_argument('--clock-server',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    sub.choices['receive'].add_argument('--stop-file',type=Path)
    a=p.parse_args()
    if a.command=='clock-server':clock_server(a)
    elif a.command=='receive':receive(a)
    else:analyze(a)
if __name__=='__main__':main()
