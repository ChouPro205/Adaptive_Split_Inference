"""Verify sealed logs and produce queue/MQTT tables without running hardware."""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import statistics

def verify(folder):
    inventory=folder/'sha256sum_results.txt'
    listed=set()
    for line in inventory.read_text().splitlines():
        digest,name=line.split('  ',1)
        parts=PurePosixPath(name)
        if parts.is_absolute() or '..' in parts.parts or name in listed:
            raise ValueError('Unsafe/duplicate checksum path')
        path=folder/name
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError('Checksum target escapes folder')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Checksum mismatch: '+name)
        listed.add(name)
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()
            and p.name != 'sha256sum_results.txt'}
    # Parent seals include a nested queue seal. A queue seal has no nested output.
    if listed!=actual: raise ValueError('Checksum inventory differs from actual files')
    return listed

def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]

def stats(values):
    values=sorted(values)
    if not values:return dict(n=0,mean=None,std=None,p95=None,max=None)
    return dict(n=len(values),mean=statistics.mean(values),
                std=statistics.stdev(values) if len(values)>1 else 0.,
                p95=values[max(0,math.ceil(len(values)*.95)-1)],max=max(values))

def analyze(run, receiver=None):
    verify(run)
    meta=json.loads((run/'queue_run.json').read_text())
    jobs=rows(run/'jobs.jsonl')
    finished=[r for r in jobs if r['event']=='finished' and not r['cancelled'] and r['error'] is None]
    result=dict(scope='saved evidence; acceptance requires SV1 review',run_id=meta['config']['run_id'],
        backend=meta['backend'],queue=json.loads((run/'queue_summary.json').read_text()),
        foreground_queue_wait_ms=stats([r['queue_wait_ms'] for r in finished if r['kind']=='foreground']),
        background_queue_wait_ms=stats([r['queue_wait_ms'] for r in finished if r['kind']=='background']),
        service_ms=stats([r['service_ms'] for r in finished]),
        background_arrival_late_ms=stats([(r['enqueued_ns']-r['planned_ns'])/1e6 for r in jobs
            if r['event']=='enqueue' and r['kind']=='background']))
    if not (run/'mqtt_sent.jsonl').exists():
        result['mqtt']={'status':'NOT_RECORDED'};return result
    sent=rows(run/'mqtt_sent.jsonl')
    acks=rows(run/'mqtt_ack.jsonl') if (run/'mqtt_ack.jsonl').exists() else []
    sent_by={r['seq_number']:r for r in sent}
    if len(sent_by)!=len(sent):raise ValueError('Duplicate publisher seq')
    ack_by={r['seq_number']:r for r in acks}
    if len(ack_by)!=len(acks):raise ValueError('Duplicate ACK seq')
    for seq,ack in ack_by.items():
        if seq not in sent_by or ack['publisher_send_ns']!=sent_by[seq]['publisher_monotonic_ns']:
            raise ValueError('ACK does not match publisher status')
        expected=(ack['publisher_ack_ns']-ack['publisher_send_ns'])/1e6
        if expected<0 or expected!=ack['ack_rtt_ms']:raise ValueError('Invalid ACK timing')
    latency=stats([r['ack_rtt_ms'] for r in acks])
    rec=None
    if receiver:
        verify(receiver)
        receive=[r for r in rows(receiver/'received.jsonl') if r['state']['run_id']==result['run_id']]
        rec={r['state']['seq_number']:r for r in receive}
        if len(rec)!=len(receive):raise ValueError('Duplicate receiver seq')
        for seq,row in rec.items():
            if seq not in sent_by or row['state']!={k:v for k,v in sent_by[seq].items()
                    if k not in ('publish_rc','schedule_late_ms')}:
                raise ValueError('Receiver payload differs from publisher')
            if row['receiver_id']!=meta['config']['receiver_id'] or row['retained']:
                raise ValueError('Wrong receiver or stale retained payload')
    complete=bool(sent) and set(ack_by)==set(sent_by) and rec is not None and set(rec)==set(sent_by)
    errors=any(r['publish_rc']!=0 for r in sent) or (run/'mqtt_errors.jsonl').exists()
    result['mqtt']=dict(sent=len(sent),acked=len(acks),receiver_rows=None if rec is None else len(rec),
        matching_complete=complete,ack_rtt_ms=latency,
        publish_interval_ms=stats([(b['publisher_monotonic_ns']-a['publisher_monotonic_ns'])/1e6
                                  for a,b in zip(sent,sent[1:])]),
        period_target_ms=100,period_tolerance='not specified; report raw intervals, do not silently choose a limit',
        status='DELIVERY_UPPER_BOUND_LT20MS_ALL_RECORDED' if complete and not errors and latency['max']<20
               else 'NOT_YET_PROVEN',
        meaning='ACK RTT upper-bounds status delivery; RTT>=20ms does not prove one-way>=20ms')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True,help='The sealed queue subdirectory')
    p.add_argument('--receiver',type=Path)
    p.add_argument('--peer',type=Path,help='Optional sealed BLE peer.jsonl for SV1 export')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=analyze(a.run,a.receiver)
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for name in ('jobs.jsonl','mqtt_sent.jsonl','mqtt_ack.jsonl'):
        if (a.run/name).exists():
            import shutil
            shutil.copyfile(a.run/name,a.output/name)
    if a.peer:
        verify(a.peer.parent)
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'week8'))
        from sv1_log import sv1_row
        (a.output/'peer_sv1.jsonl').write_text(''.join(json.dumps(sv1_row(r),allow_nan=False)+'\n'
            for r in rows(a.peer)))
    (a.output/'source_paths.json').write_text(json.dumps(dict(run=str(a.run.resolve()),
        receiver=None if a.receiver is None else str(a.receiver.resolve())),indent=2)+'\n')
    from hashlib import sha256
    (a.output/'sha256sum_results.txt').write_text(''.join(sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n'
        for f in sorted(a.output.iterdir()) if f.is_file()))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
