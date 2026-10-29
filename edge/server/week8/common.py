"""Week 8 saved data, evidence and persistent native transport. Python 3.9+."""
from __future__ import annotations
import hashlib,json,math,os,select,struct,subprocess,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
REFERENCE_SHA='e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5'
BUNDLE_SHA='41fe3388db89bdb0d1759e4bc7b6b926af1fb8d87bd8c71d880505695ce14a44'
def sha(data): return hashlib.sha256(data).hexdigest()
def file_sha(path): return sha(Path(path).read_bytes())
def save(path,obj):
    with Path(path).open('x',encoding='utf-8') as f: json.dump(obj,f,indent=2,allow_nan=False); f.write('\n')
def seal(folder):
    folder=Path(folder)
    with (folder/'sha256sum_results.txt').open('x') as f:
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.name!='sha256sum_results.txt': f.write(file_sha(p)+'  '+p.relative_to(folder).as_posix()+'\n')
def hex_logits(values): return [struct.pack('<f',float(x)).hex() for x in values]
def load_reference(path,expected=REFERENCE_SHA):
    if file_sha(path)!=expected: raise ValueError('Reference SHA256 differs; never relabel a different package')
    with np.load(path,allow_pickle=False) as z: data={k:z[k] for k in z.files}
    shapes={'sample_id':(100,),'test_index':(100,),'label_ref':(100,),'x':(100,1,360),
            'q':(100,16,180),'scale_f16':(100,16),'logits':(100,5)}
    for k,s in shapes.items():
        if k not in data or data[k].shape!=s: raise ValueError('Wrong reference shape: '+k)
    if data['q'].dtype!=np.dtype('int8') or np.any(data['q']==-128): raise ValueError('Invalid q')
    if data['scale_f16'].dtype!=np.dtype('float16'): raise ValueError('Scale must be float16')
    for k in ['x','scale_f16','logits']:
        if not np.isfinite(data[k]).all(): raise ValueError('Nonfinite '+k)
    if np.any(data['scale_f16']<2**-14) or np.any(data['scale_f16']>65504): raise ValueError('Scale outside contract')
    if len(set(data['sample_id'].tolist()))!=100 or len(set(data['test_index'].tolist()))!=100: raise ValueError('Duplicate samples')
    if not np.array_equal(data['logits'].argmax(1),data['label_ref']): raise ValueError('Reference labels differ from logits')
    return data
class Worker:
    """Loads model once. A timeout poisons/kills the worker; no unsafe late reuse."""
    def __init__(self,binary,deploy,cpu_ops,log_path):
        if file_sha(Path(deploy)/'sha256sum_bundle.txt')!=BUNDLE_SHA:
            raise ValueError('Bundle inventory differs from authenticated Week 5 pin')
        subprocess.run(['sha256sum','-c','sha256sum_bundle.txt'],cwd=deploy,
                       stdout=subprocess.DEVNULL,check=True)
        self.model=Path(deploy)/'release/models/tail_s2.xmodel'
        manifest=json.loads((Path(deploy)/'release/provenance/compile_manifest.json').read_text())
        expected=next(r['xmodel_sha256'] for r in manifest['splits'] if r['split']==2)
        if file_sha(self.model)!=expected: raise ValueError('Model hash differs from deploy manifest')
        self.metadata={'backend':'KV260_ROOT_CPU_DPU','split':2,'model_sha256':expected,'bundle_inventory_sha256':BUNDLE_SHA,
          'worker_sha256':file_sha(binary),'plugins':{p.name:file_sha(p) for p in Path(cpu_ops).glob('libvart_op_imp_*.so')}}
        if not self.metadata['plugins']: raise ValueError('Missing CPU plugins')
        self.log=Path(log_path).open('xb'); self.buffer=b'';self.alive=True
        env=os.environ.copy();env['LD_LIBRARY_PATH']=str(cpu_ops)+':'+env.get('LD_LIBRARY_PATH','')
        self.process=subprocess.Popen([str(Path(binary).resolve()),str(self.model.resolve())],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.log,env=env,bufsize=0)
        try:
            ready=self.line(30)
            if ready.get('ready') is not True or ready.get('execution')!='root_graph':raise ValueError('Worker not ready')
        except BaseException:self.close();raise
    def line(self,timeout):
        end=time.monotonic()+timeout
        while True:
            if b'\n' in self.buffer:
                raw,self.buffer=self.buffer.split(b'\n',1)
                try:return json.loads(raw)
                except (ValueError,UnicodeError):self.log.write(raw+b'\n');continue
            remaining=end-time.monotonic()
            if remaining<=0:raise TimeoutError('Native worker deadline exceeded')
            if not select.select([self.process.stdout],[],[],remaining)[0]:raise TimeoutError('Native worker deadline exceeded')
            chunk=os.read(self.process.stdout.fileno(),65536)
            if not chunk:raise RuntimeError('Native worker exited; inspect worker.log')
            self.buffer+=chunk
            if len(self.buffer)>1048576:raise RuntimeError('Native stdout overflow')
    def infer(self,values):
        if not self.alive:raise RuntimeError('Worker is faulted; end session and inspect log')
        data=np.asarray(values,dtype='<f4').reshape(1,16,180).tobytes()
        try:
            pending=memoryview(struct.pack('<I',len(data))+data)
            while pending:
                written=os.write(self.process.stdin.fileno(),pending)
                if written<=0:raise RuntimeError('Native input pipe closed')
                pending=pending[written:]
            r=self.line(4)
            if len(r.get('logits',[]))!=5 or not all(math.isfinite(x) for x in r['logits']):raise ValueError('Invalid native output')
            return r
        except BaseException:self.close();raise
    def close(self):
        self.alive=False
        if hasattr(self,'process'):
            if self.process.poll() is None:self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        if hasattr(self,'log'):self.log.close()
def backend_args(ap):
    ap.add_argument('--worker',type=Path,required=True);ap.add_argument('--deploy',type=Path,required=True)
    ap.add_argument('--cpu-ops',type=Path,required=True)
