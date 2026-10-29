#!/usr/bin/env python3
"""Run exact 100 s2 q/scale through ONE native root GraphRunner. No BLE."""
import argparse,csv,platform
import numpy as np
from common import Worker,backend_args,load_reference,save,seal,hex_logits,REFERENCE_SHA

def main():
    ap=argparse.ArgumentParser(description=__doc__);backend_args(ap)
    ap.add_argument('--reference',required=True);ap.add_argument('--output',type=__import__('pathlib').Path,required=True)
    a=ap.parse_args()
    if platform.machine()!='aarch64':ap.error('Run on KV260 aarch64; no fake board result')
    data=load_reference(a.reference);a.output.mkdir(parents=True,exist_ok=False);rows=[]
    worker=Worker(a.worker,a.deploy,a.cpu_ops,a.output/'worker.log')
    try:
        save(a.output/'run.json',{'scope':'OFFLINE_100_NOT_BLE','reference_sha256':REFERENCE_SHA,**worker.metadata})
        with (a.output/'predictions.jsonl').open('x') as stream:
            for i in range(100):
                z=data['q'][i].astype('<f4')*data['scale_f16'][i].astype('<f4')[:,None]
                result=worker.infer(z);logits=np.asarray(result['logits'],dtype='<f4');label=int(logits.argmax())
                row={'sample_index':i,'sample_id':str(data['sample_id'][i]),'test_index':int(data['test_index'][i]),
                     'logits':logits.tolist(),'logits_hex_le':hex_logits(logits),'label':label,
                     'label_ref':int(data['label_ref'][i]),'class_match':label==int(data['label_ref'][i]),
                     'max_abs_error':float(np.abs(logits.astype(float)-data['logits'][i]).max()),'tail_ms':result['tail_ms']}
                rows.append(row);stream.write(__import__('json').dumps(row)+'\n');stream.flush()
                print('%d/100 label=%d ref=%d'%(i+1,label,row['label_ref']),flush=True)
        save(a.output/'summary.json',{'scope':'OFFLINE_100_NOT_BLE','executed':100,
            'class_matches':sum(r['class_match'] for r in rows),'mismatches':[r['sample_index'] for r in rows if not r['class_match']],
            'max_abs_error':max(r['max_abs_error'] for r in rows),'status':'EXECUTED_REVIEW_REQUIRED',
            'note':'Do not calibrate/tune models or remove samples using these test results'})
        with (a.output/'predictions.csv').open('x',newline='') as f:
            keys=['sample_index','sample_id','test_index','label','label_ref','class_match','max_abs_error','tail_ms']
            w=csv.DictWriter(f,keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    finally:worker.close()
    seal(a.output)
if __name__=='__main__':main()
