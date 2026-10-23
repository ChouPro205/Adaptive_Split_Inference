#!/usr/bin/env python3
"""Week 7 file transport. Actual reference or native root GraphRunner backend; no lookup logits."""
from __future__ import annotations
import argparse, hashlib, json, math, os, platform, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
# On BOARD use --repo pointing to the transferred snapshot.
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, obj):
    with Path(p).open('x') as f: json.dump(obj, f, indent=2, allow_nan=False); f.write('\n')
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',type=Path,default=ROOT)
    ap.add_argument('--request',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--backend',choices=['reference','kv260'],required=True)
    ap.add_argument('--model-package',type=Path)
    ap.add_argument('--deploy',type=Path)
    ap.add_argument('--runner',type=Path)
    ap.add_argument('--cpu-op-dir',type=Path)
    ap.add_argument('--public-test-key',action='store_true')
    ap.add_argument('--key-file',type=Path)
    a=ap.parse_args(); repo=a.repo.resolve()
    sys.path.insert(0,str(repo/'contracts/i1v2_ref'))
    import i1v2_reference as i1
    if a.public_test_key and a.key_file: ap.error('Choose one key source')
    if a.backend=='kv260' and platform.machine()!='aarch64': ap.error('KV260 backend requires aarch64')
    profile=i1.load_profile(repo/'contracts/sv3_week5_approved_registry_v2.json')
    key=bytes(range(32)) if a.public_test_key else (a.key_file.read_bytes() if a.key_file else None)
    if key is not None and len(key)!=32: ap.error('Key must contain 32 bytes')
    keys={} if key is None else {profile.key_id:key}
    a.output.mkdir(parents=True,exist_ok=False)
    with a.request.open('rb') as f: packet=f.read(profile.max_packet+1)
    record={'backend':a.backend,'request_sha256':hashlib.sha256(packet).hexdigest(),
            'source_sha256':sha(__file__),'scope':'FILE_TRANSPORT; no BLE/cache/server throughput',
            'numeric_acceptance':'PENDING','status':'STARTED'}
    try:
        req=i1.parse_request(packet,profile)
    except i1.Drop as e:
        record.update(status='DROP',reason=str(e)); save(a.output/'result.json',record); return 0
    except i1.Reject as e:
        (a.output/'response.bin').write_bytes(i1.encode_error(e.request_id,e.status))
        record.update(status='ERROR',reason=e.name); save(a.output/'result.json',record); return 0
    record.update(request_id=req.request_id,split=req.split.split_point)
    model=None
    if a.backend=='reference':
        if a.model_package is None: ap.error('reference requires --model-package')
        sys.path.insert(0,str(repo/'ml/scripts'))
        from week3_sv2_common import authenticate,configure,load_frozen,wrappers
        authenticate(a.model_package,'a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6')
        configure(); model=load_frozen(a.model_package).float().eval()
    def tail(split,values):
        s=split.split_point
        z=np.asarray(values,dtype='<f4').reshape(1,split.channels,split.length)
        if s==9: z=z.reshape(1,32)
        if a.backend=='reference':
            import torch
            _,t=wrappers(model,s)
            with torch.inference_mode(): return t(torch.from_numpy(z.copy())).numpy()[0].tolist()
        if not all([a.deploy,a.runner,a.cpu_op_dir]): raise ValueError('Missing deploy/runner/cpu-op-dir')
        compiled=a.deploy/'release/models'/('tail_s%d.xmodel'%s)
        manifest=json.loads((a.deploy/'release/provenance/compile_manifest.json').read_text())
        expected=next(r['xmodel_sha256'] for r in manifest['splits'] if r['split']==s)
        if sha(compiled)!=expected: raise ValueError('Model hash mismatch')
        # Single input NPY; no duplication into a fake 20-sample golden.
        np.save(a.output/'input.npy',z,allow_pickle=False)
        env=os.environ.copy(); env['LD_LIBRARY_PATH']=str(a.cpu_op_dir)+':'+env.get('LD_LIBRARY_PATH','')
        command=[str(a.runner.resolve()),'--model',str(compiled.resolve()),'--input',str((a.output/'input.npy').resolve()),
                 '--split',str(s),'--samples','1','--output',str((a.output/'runner.json').resolve())]
        record.update(model_sha256=expected,runner_sha256=sha(a.runner),command=command,
                      plugins={p.name:sha(p) for p in a.cpu_op_dir.glob('libvart_op_imp_*.so')})
        with (a.output/'runner.log').open('x') as log:
            r=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=4)
        if r.returncode: raise RuntimeError('Native runner exit %d'%r.returncode)
        result=json.loads((a.output/'runner.json').read_text())
        if result['execution']!='root_graph' or result['split']!=s or len(result['samples'])!=1:
            raise ValueError('Invalid runner result')
        return result['samples'][0]['logits']
    try:
        # Keep exact normative validation/recovery/identity and response semantics.
        response=i1.receive_request(packet,profile,keys,tail=tail)
    except subprocess.TimeoutExpired:
        response=i1.encode_error(req.request_id,i1.STATUS['TIMEOUT']); record['error']='Runner timeout (4 s process budget)'
    except Exception as e:
        response=i1.encode_error(req.request_id,i1.STATUS['INFERENCE_FAILED']); record['error']=str(e)
    if response is not None:
        (a.output/'response.bin').write_bytes(response)
        kind,value=i1.parse_response(response,req.request_id,profile.max_packet)
        record.update(status=kind,response_sha256=hashlib.sha256(response).hexdigest())
        if kind=='OK': record.update(logits=value,predicted_class=i1.predicted_class(value))
        else: record['reason']=i1.STATUS_NAME[value]
    save(a.output/'result.json',record)
    print(json.dumps(record,indent=2))
    return 0 if record['status']=='OK' else 1
if __name__=='__main__': sys.exit(main())
