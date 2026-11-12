"""Native Windows receiver and clock preflight; no system clock changes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import time
from types import SimpleNamespace
import zipfile


def measurement():
    p=Path(__file__).with_name('oneway.py')
    spec=importlib.util.spec_from_file_location('native_oneway',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def unique(p):
    base=p;n=2
    while p.exists():
        name=(base.stem+'_lan_'+str(n)+base.suffix) if base.suffix=='.zip' else (base.name+'_lan_'+str(n))
        p=base.with_name(name);n+=1
    return p


def verify_source(root):
    for line in (root/'sha256sum_windows.txt').read_text().splitlines():
        digest,name=line.split('  ',1);p=(root/name).resolve()
        if not p.is_relative_to(root.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Windows source checksum mismatch: '+name)


def assess(m,probes,samples,budget_ms=5):
    if len(samples)<2:raise ValueError('Not enough local clock samples')
    perf=samples[-1]['perf_ns']-samples[0]['perf_ns']
    wall=samples[-1]['wall_ns']-samples[0]['wall_ns']
    if wall<=0 or perf<=0:raise ValueError('Local clock order invalid')
    ratio=perf/wall
    if abs(ratio-1)>.001:raise ValueError('LOCAL_CLOCK_RATE_MISMATCH; perf/wall='+str(ratio))
    model=m.clock_model(probes,time.get_clock_info('perf_counter').resolution*1e9)
    widths=[]
    for p in probes:
        x=(p['s1_ns']-model['s0_ns'])/1e6
        values=[d*x+c for d,c in model['vertices']]
        widths.append(max(values)-min(values))
    width=max(widths)
    if width>budget_ms:raise ValueError('CALIBRATION_TOO_WIDE; max width ms='+str(width))
    return dict(status='READY_FOR_CAPTURE_NOT_ACCEPTANCE',local_perf_wall_ratio=ratio,
        model=model,max_alignment_width_ms=width,readiness_budget_ms=budget_ms,
        limitation='5 ms is an engineering readiness budget, not a PDF requirement. Wall clock comparison is diagnostic only; not synchronization or external clock validation.')


def probe(root,seconds):
    m=measurement();out=unique(root/'captures/preflight');out.mkdir(parents=True)
    probes=m.Probes('127.0.0.1',1906,out);samples=[];failure=None
    probes.thread.start()
    try:
        deadline=time.perf_counter()+seconds
        while time.perf_counter()<deadline:
            samples.append(dict(perf_ns=time.perf_counter_ns(),wall_ns=time.time_ns()))
            time.sleep(.1)
    finally:probes.close()
    m.save(out/'local_clocks.json',samples)
    try:
        if probes.errors or probes.mixed:raise ValueError('Probe transport/identity errors')
        result=assess(m,m.rows(out/'clock_probes.jsonl'),samples)
    except ValueError as exc:
        failure=exc;result=dict(status='NOT_READY',error=str(exc))
    result.update(platform=platform.system(),hostname=platform.node(),python=platform.python_version(),
        probe_count=probes.count,clock_id=probes.identity,source_sha256=m.sha(__file__))
    m.save(out/'preflight.json',result);m.seal(out)
    (root/'last_preflight.txt').write_text(str(out)+'\n')
    print(json.dumps(result,indent=2));print('PREFLIGHT_SAVED',out,flush=True)
    if failure:raise failure


def receive(root,kind):
    m=measurement();config=json.loads((root/'windows_config.json').read_text())
    preflight=Path((root/'last_preflight.txt').read_text().strip()).resolve()
    if not preflight.is_relative_to(root/'captures'):raise ValueError('Preflight outside capture folder')
    m.verify(preflight);ready=json.loads((preflight/'preflight.json').read_text())
    if ready['status']!='READY_FOR_CAPTURE_NOT_ACCEPTANCE':raise ValueError('Preflight not ready')
    if ready['hostname']!=platform.node() or ready['source_sha256']!=m.sha(__file__):raise ValueError('Preflight host/source differs')
    out=unique(root/'captures'/kind);out.parent.mkdir(exist_ok=True)
    stop=root/('stop_'+out.name+'.flag')
    if stop.exists():raise ValueError('Old stop flag; create a new session instead of overwriting evidence')
    (root/('last_'+kind+'.txt')).write_text(str(out)+'\n')
    print('CAPTURE_OUTPUT',out,flush=True)
    m.receive(SimpleNamespace(host='127.0.0.1',port=config['broker_local_port'],clock_host='127.0.0.1',clock_port=config['clock_local_port'],
        tcp_nodelay=True,receiver_id=config['receiver_id'],role=config['role'],network_label=config['network_label'],output=out,stop_file=stop,expected_clock_id=ready['clock_id']))
    saved=json.loads((out/'receiver.json').read_text())
    if saved['clock_id']!=ready['clock_id']:raise ValueError('Clock restarted since preflight; preserve capture, repeat preflight')


def stop(root,kind):
    p=Path((root/('last_'+kind+'.txt')).read_text().strip()).resolve()
    if not p.is_relative_to(root/'captures'):raise ValueError('Capture outside session')
    if (p/'sha256sum_results.txt').exists():
        print('ALREADY_SAVED',p);return
    with (root/('stop_'+p.name+'.flag')).open('x') as f:f.write('operator requested clean stop\n')
    print('STOP_REQUESTED; wait for SAVED and exit code in receiver window')


def export(root):
    m=measurement();folders={}
    for phase in ('idle','varying'):
        p=Path((root/('last_'+phase+'.txt')).read_text().strip()).resolve()
        if not p.is_relative_to(root/'captures'):raise ValueError('Capture outside session')
        m.verify(p)
        meta=json.loads((p/'receiver.json').read_text())
        if meta['status']!='STOPPED_BY_OPERATOR':raise ValueError('Capture not finished cleanly')
        folders[phase]=p
    p=Path((root/'last_preflight.txt').read_text().strip()).resolve()
    if not p.is_relative_to(root/'captures'):raise ValueError('Preflight outside session')
    m.verify(p);folders['preflight']=p
    archive=unique(root/'ket_qua_windows.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for kind,p in folders.items():
            for f in sorted(p.rglob('*')):
                if f.is_file():z.write(f,kind+'/'+f.relative_to(p).as_posix())
        for name in ('windows_config.json','native_receiver.py','oneway.py','sha256sum_windows.txt'):
            z.write(root/name,'source/'+name)
        if (root/'network.txt').is_file():z.write(root/'network.txt','network.txt')
    archive.with_name(archive.name+'.sha256.txt').write_text(m.sha(archive)+'  '+archive.name+'\n')
    (root/'last_export.txt').write_text(str(archive)+'\n')
    print('WINDOWS_EXPORT_SAVED',archive)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('probe');a.add_argument('--seconds',type=float,default=30)
    for name in ('receive','stop'):
        a=sub.add_parser(name);a.add_argument('--kind',choices=['idle','varying'],required=True)
    sub.add_parser('export')
    a=p.parse_args();root=Path(__file__).resolve().parent
    verify_source(root)
    if platform.system()!='Windows':raise ValueError('Use native Windows Python, not WSL')
    if a.command=='probe':
        if not 10<=a.seconds<=600:raise ValueError('Use 10..600 seconds')
        probe(root,a.seconds)
    elif a.command=='receive':receive(root,a.kind)
    elif a.command=='stop':stop(root,a.kind)
    else:export(root)


if __name__=='__main__':main()
