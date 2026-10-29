#!/usr/bin/env python3
"""Compare persistent and SAVED single-input native runners on identical s2 tensors."""
import argparse,json,os,platform,subprocess
from pathlib import Path
import numpy as np
from common import Worker,backend_args,load_reference,save,seal,hex_logits

def main():
    ap=argparse.ArgumentParser(description=__doc__);backend_args(ap)
    ap.add_argument('--single-runner',required=True);ap.add_argument('--reference',required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--count',type=int,default=3)
    a=ap.parse_args()
    if platform.machine()!='aarch64' or not 1<=a.count<=100:ap.error('KV260 and count 1..100 required')
    data=load_reference(a.reference);a.output.mkdir(parents=True,exist_ok=False);rows=[]
    worker=None
    try:
        # Finish every single-input process before reserving the persistent DPU runner.
        old_results=[]
        for i in range(a.count):
            z=(data['q'][i].astype('<f4')*data['scale_f16'][i].astype('<f4')[:,None])[None]
            case=a.output/('sample_%03d'%i);case.mkdir();np.save(case/'input.npy',z,allow_pickle=False)
            env=os.environ.copy();env['LD_LIBRARY_PATH']=str(a.cpu_ops)+':'+env.get('LD_LIBRARY_PATH','')
            cmd=[a.single_runner,'--model',str(a.deploy/'release/models/tail_s2.xmodel'),'--input',str(case/'input.npy'),
                 '--split','2','--samples','1','--output',str(case/'single.json')]
            with (case/'single.log').open('x') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=10,check=True)
            old_results.append(json.loads((case/'single.json').read_text())['samples'][0]['logits'])
        worker=Worker(a.worker,a.deploy,a.cpu_ops,a.output/'worker.log')
        for i,old in enumerate(old_results):
            z=np.load(a.output/('sample_%03d'%i)/'input.npy',allow_pickle=False)
            new=worker.infer(z)['logits']
            rows.append({'sample_index':i,'bit_exact':hex_logits(old)==hex_logits(new),'single':old,'persistent':new})
        save(a.output/'comparison.json',rows)
        save(a.output/'summary.json',{'compared':len(rows),'bit_exact':all(r['bit_exact'] for r in rows),'scope':'NATIVE_RUNNER_PARITY_NOT_BLE'})
        if not all(r['bit_exact'] for r in rows):raise ValueError('Persistent runner differs; stop before G2')
    finally:
        if worker is not None:worker.close()
        seal(a.output)
    print('NATIVE_PARITY_OK count='+str(len(rows)))
if __name__=='__main__':main()
