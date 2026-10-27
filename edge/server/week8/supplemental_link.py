#!/usr/bin/env python3
"""Supplemental PHY trials: handle-safe HCI commands and derived numeric logs."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from common import save, seal, sha, hex_logits
from summarize import verify
from sv1_log import sv1_row

PHY_NAMES = set('BR1M1SLOT BR1M3SLOT BR1M5SLOT EDR2M1SLOT EDR2M3SLOT EDR2M5SLOT EDR3M1SLOT EDR3M3SLOT EDR3M5SLOT LE1MTX LE1MRX LE2MTX LE2MRX LECODEDTX LECODEDRX'.split())


def parse_phys(text):
    result={}
    for label in ('Supported','Configurable','Selected'):
        m=re.search(r'(?m)^'+label+r' phys:[ \t]*([^\n]*)$',text)
        if not m:raise ValueError('Missing '+label+' phys output')
        values=m[1].split()
        if not values or set(values)-PHY_NAMES:
            # Configurable may be empty on controllers with no optional PHYs.
            if label!='Configurable' or values:raise ValueError('Unrecognized PHY names')
        result[label.lower()]=values
    return result


def allow_2m(current):
    if not {'LE2MTX','LE2MRX'}<=set(current['supported']):
        raise ValueError('Controller does not advertise 2M TX/RX support; keep 1M and review')
    # Kernel 5.15 requires all unconfigurable primary PHYs (including BR1M1SLOT
    # on dual-mode adapters). Preserve BR/EDR selections instead of clearing them.
    return [p for p in current['selected'] if not p.startswith('LE')]+['LE1MTX','LE1MRX','LE2MTX','LE2MRX']


def config(a):
    if not re.fullmatch(r'hci[0-9]+',a.adapter):raise ValueError('Invalid adapter')
    index=str(int(a.adapter[3:]))
    def call(*args):
        r=subprocess.run(['btmgmt','-i',index,*args],text=True,capture_output=True,timeout=15)
        print(r.stdout,flush=True);print(r.stderr,flush=True)
        if r.returncode:raise RuntimeError('btmgmt failed; preserve log')
        return r.stdout
    current=parse_phys(call('phy'))
    if a.mode=='snapshot':
        save(a.state,{'adapter':a.adapter,'configuration':current});print('PHY_SNAPSHOT_SAVED');return
    con=subprocess.run(['hcitool','-i',a.adapter,'con'],text=True,capture_output=True,check=True,timeout=10)
    print(con.stdout,flush=True)
    if re.search(r'(?m)^\s*[<>]\s+',con.stdout):raise ValueError('Disconnect every connection on this adapter first')
    info=call('info')
    if not re.search(r'current settings:.*\bpowered\b',info):
        raise ValueError('Kernel 5.15 requires the controller powered ON to set default PHY')
    saved=json.loads(a.state.read_text())
    if saved['adapter']!=a.adapter:raise ValueError('Snapshot adapter differs')
    if a.mode=='allow-2m':desired=allow_2m(current)
    else:
        desired=saved['configuration']['selected']
        if not set(desired)<=PHY_NAMES:raise ValueError('Unrecognized saved PHY values')
    print('REQUESTED_SELECTED_PHYS='+' '.join(desired),flush=True)
    call('phy',*desired)
    actual=parse_phys(call('phy'))
    if set(actual['selected'])!=set(desired):raise ValueError('Selected PHYs did not match request')
    print('DEFAULT_PHY_CONFIGURATION_SET; active connection PHY must be checked separately')


def handle_for(text, peer):
    found = re.findall(r'(?m)^\s*[<>]\s+LE\s+'+re.escape(peer)+r'\s+handle\s+(\d+)\b', text, re.I)
    if len(found) != 1:
        raise ValueError('Need exactly one active LE connection to '+peer+'; inspect hcitool con')
    handle = int(found[0])  # hcitool con prints DECIMAL, not hex.
    if not 0 <= handle <= 0x0eff:
        raise ValueError('Invalid HCI connection handle')
    return handle


def phy_args(handle, action):
    if action not in ('read', 'set-2m'):
        raise ValueError('Unknown action')
    params = [f'0x{handle & 255:02x}', f'0x{handle >> 8:02x}']
    return ['0x08', '0x0030' if action == 'read' else '0x0032']+params+(
        [] if action == 'read' else ['0x00', '0x02', '0x02', '0x00', '0x00'])


def command_status(text, opcode):
    match = re.search(r'> HCI Event: 0x([0-9a-f]+) plen (\d+)\s*\n(.*)', text, re.I|re.S)
    if not match:
        raise ValueError('No HCI event captured; preserve output and inspect btmon')
    data = bytes(int(x,16) for x in re.findall(r'\b[0-9a-f]{2}\b',match[3],re.I))
    event = int(match[1],16)
    if event == 0x0e and len(data)>=4 and int.from_bytes(data[1:3],'little')==opcode:
        return data[3],data[4:]
    if event == 0x0f and len(data)>=4 and int.from_bytes(data[2:4],'little')==opcode:
        return data[0],b''
    raise ValueError('HCI event belongs to another command; verify the trace before proceeding')


def phy(a):
    if not re.fullmatch(r'hci[0-9]+',a.adapter) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',a.peer):
        raise ValueError('Invalid adapter or peer address')
    con=subprocess.run(['hcitool','-i',a.adapter,'con'],check=True,text=True,capture_output=True,timeout=10)
    print(con.stdout,flush=True)
    handle=handle_for(con.stdout,a.peer)
    args=phy_args(handle,a.action)
    print('handle_decimal=%d handle_hex=0x%04x; cmd=%s'%(handle,handle,' '.join(args)),flush=True)
    result=subprocess.run(['hcitool','-i',a.adapter,'cmd',*args],text=True,capture_output=True,timeout=10)
    print(result.stdout,flush=True);print(result.stderr,flush=True)
    if result.returncode:raise RuntimeError('hcitool failed; inspect output')
    status,payload=command_status(result.stdout,0x2030 if a.action=='read' else 0x2032)
    if status:raise RuntimeError('Controller rejected command: status=0x%02x'%status)
    if a.action=='set-2m':
        print('SET_PHY_REQUEST_ACCEPTED; actual PHY requires PHY Update Complete/Read PHY/Device confirmation')
    else:
        if len(payload)!=4 or int.from_bytes(payload[:2],'little')!=handle:
            raise ValueError('Unexpected LE Read PHY response')
        names={1:'1M',2:'2M',3:'Coded'}
        print('ACTUAL_PHY_AT_READ TX=%s RX=%s'%(names.get(payload[2],str(payload[2])),names.get(payload[3],str(payload[3]))))


def export(a):
    trials=[];backend=None;service_info={}
    selected=[('trial1','trial1',1),('trial2','trial2',10)]
    trial4=getattr(a,'trial4',None)
    if trial4:
        if not re.fullmatch(r'trial[0-9]+(?:_[a-zA-Z0-9]+)*',trial4) or trial4 in ('trial1','trial2'):
            raise ValueError('Invalid or reused trial4 source folder')
        selected.append(('trial4',trial4,10))
    for name,source,count in selected:
        folder=a.root/source;verify(folder)
        listed={line.split(maxsplit=1)[1].lstrip('* ') for line in (folder/'sha256sum_results.txt').read_text().splitlines()}
        if not {'peer.jsonl','run.json'}<=listed:raise ValueError('Missing sealed peer/run entries')
        rows=[json.loads(x) for x in (folder/'peer.jsonl').read_text().splitlines()]
        run=json.loads((folder/'run.json').read_text())
        service_info[name]={
            'source_folder':source,
            'ble_service_sha256_recorded':run.get('source_sha256'),
            'run_json_sha256':sha((folder/'run.json').read_bytes()),
            'run_metadata':run,
            'note':'Recorded hash identifies executed service; CLI/config differences require command logs. Do not substitute current checkout hash.'}
        if backend is None:backend=run['backend']
        elif backend!=run['backend']:raise ValueError('Model/worker/plugins differ between trials')
        if len(rows)!=count or any(r.get('result')!='OK' or not r.get('response_sent') or r.get('cache_hit') for r in rows):
            raise ValueError(name+': wrong count/errors/retry; preserve raw evidence for review')
        if len({r['connection'] for r in rows})!=1:
            raise ValueError(name+': reconnected; review before calling trial complete')
        if name=='trial1' and rows[0]['rho']!='P0':raise ValueError('Trial1 must be P0')
        if name in ('trial2','trial4'):
            for i in range(0,10,2):
                x,y=rows[i:i+2]
                if {x['rho'],y['rho']}!={'P0','P1'} or (x['q_sha256'],x['scale_fp16_sha256'])!=(y['q_sha256'],y['scale_fp16_sha256']):
                    raise ValueError('Trial2 does not contain five matching P0/P1 pairs')
            sequences=[r.get('sequence') for r in rows if r['rho']=='P1']
            if not all(isinstance(s,int) for s in sequences) or not all(y>x for x,y in zip(sequences,sequences[1:])):
                raise ValueError('Trial2 P1 sequence missing or not increasing')
        converted=[]
        for r in rows:
            v=sv1_row(r)
            if len(v.get('logits') or [])!=5 or not v['scale_sha256']:
                raise ValueError('Missing numeric logits/FP16 hash')
            if hex_logits(v['logits'])!=r['logits_hex_le']:
                raise ValueError('Response numeric logits differ from saved FP32 bits')
            v.update(trial=name,tail_us=r['tail_ms']*1000,
                     tail_us_origin='converted from saved native steady_clock tail_ms')
            converted.append(v)
        trials.append((name,converted,sha((folder/'sha256sum_results.txt').read_bytes()),source))
    a.output.mkdir(parents=True,exist_ok=False)
    delivery_names={'trial1':'supp1_one_p0.jsonl','trial2':'supp2_pairs5_1M.jsonl','trial4':'supp4_pairs5_2M.jsonl'}
    for name,rows,_,_ in trials:
        filename=delivery_names[name] if trial4 else name+'_sv1.jsonl'
        (a.output/filename).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    save(a.output/'service_info.json',service_info)
    (a.output/'READ_FIRST.txt').write_text(
        'Numeric JSONL files are DERIVED by script from sealed raw peer.jsonl, not raw service outputs.\n'
        'Original service files, run.json, command logs and inventories must accompany delivery unchanged.\n'
        'scale_sha256 is FP16 little-endian; raw peer.jsonl uses FP32 scale hash and hex logits.\n'
        'Numeric logits are checked against original response FP32 bits; tail_us converts saved tail_ms.\n'
        'PHY names in delivery filenames reflect the SV1-reported trial mapping, not an exporter PHY verdict.\n'
        'PEER_LOG_FIELDS definition was not available locally: receiver schema completeness still needs checking.\n'
        'Missing historical command timestamps cannot be recreated using file mtime or current time.\n')
    save(a.output/'summary.json',{'scope':'SUPPLEMENTAL_1_2_4_NOT_ORIGINAL_212' if trial4 else 'SUPPLEMENTAL_1_PLUS_10_NOT_ORIGINAL_212_REQUEST_SESSION',
        'trials':{name:{'rows':len(rows),'source_inventory_sha256':digest,'source_folder':source} for name,rows,digest,source in trials},
        'phy_dle_interval_acceptance':'PENDING_TRACE_AND_DEVICE_REVIEW',
        'note':'PHY configuration or command acceptance alone does not prove active 2M; do not backfill original G2'})
    seal(a.output);print('SUPPLEMENT_LOGS_EXPORTED_REVIEW_REQUIRED')


def main():
    ap=argparse.ArgumentParser(description=__doc__);subs=ap.add_subparsers(dest='command',required=True)
    p=subs.add_parser('phy');p.add_argument('--adapter',default='hci0');p.add_argument('--peer',default='C8:F6:EE:EF:02:CF')
    p.add_argument('--action',choices=['read','set-2m'],required=True);p.set_defaults(func=phy)
    p=subs.add_parser('export');p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--trial4',help='Actual folder for the SV1-confirmed final 10-request trial; does not rename raw evidence')
    p.set_defaults(func=export)
    p=subs.add_parser('config');p.add_argument('--adapter',default='hci0');p.add_argument('--mode',choices=['snapshot','allow-2m','restore'],required=True)
    p.add_argument('--state',type=Path,required=True);p.set_defaults(func=config)
    args=ap.parse_args();args.func(args)


if __name__=='__main__':main()
