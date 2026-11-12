"""Read-only audit of KV260 btmon btsnoop v1 / monitor datalink 2001."""
import argparse
import json
from pathlib import Path
import struct

def audit(path):
    data=path.read_bytes()
    if len(data)<16 or data[:8]!=b'btsnoop\x00':raise ValueError('Missing btsnoop header')
    if struct.unpack('>II',data[8:16])!=(1,2001):raise ValueError('Unexpected version/datalink; inspect collector version')
    i=16; counts=dict(records=0,connection=0,phy_update=0,data_length=0,connection_update=0,disconnect=0,acl=0)
    times=[]
    while i<len(data):
        if i+24>len(data):raise ValueError('Partial record header; stop collector cleanly first')
        original,included,flags,drops,t=struct.unpack('>IIIIQ',data[i:i+24]);i+=24
        if included>original or i+included>len(data):raise ValueError('Partial/invalid btsnoop record')
        payload=data[i:i+included];i+=included;counts['records']+=1;times.append(t)
        opcode=flags & 0xffff
        if opcode in (4,5):counts['acl']+=1
        if opcode==3 and len(payload)>=2:
            if payload[0]==5:counts['disconnect']+=1
            if payload[0]==0x3e and len(payload)>=3:
                sub=payload[2]
                if sub in (1,10):counts['connection']+=1
                if sub==12:counts['phy_update']+=1
                if sub==7:counts['data_length']+=1
                if sub==3:counts['connection_update']+=1
    return dict(**counts,file_bytes=len(data),datalink=2001,
        capture_span_s=None if not times else (max(times)-min(times))/1e6,
        scope='presence counters only; inspect status/handle/value/time in decoded trace')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path)
    p.add_argument('--require-session',action='store_true');a=p.parse_args()
    r=audit(a.trace);print(json.dumps(r,indent=2))
    if a.require_session and not all(r[k]>0 for k in ('connection','phy_update','data_length','disconnect','acl')):
        raise ValueError('Incomplete session events; preserve capture and review before acceptance')

if __name__=='__main__':main()
