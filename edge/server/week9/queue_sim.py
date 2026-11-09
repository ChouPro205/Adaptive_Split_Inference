"""Piecewise-constant Poisson arrivals and one bounded FIFO shared with BLE."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import queue
import random
import sys
import threading
import time

def scenario(path):
    with Path(path).open() as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['duration_s', 'lambda_jobs_per_s']:
            raise ValueError('Expected duration_s,lambda_jobs_per_s')
        rows = [(float(r['duration_s']), float(r['lambda_jobs_per_s'])) for r in reader]
    if not rows or any(not math.isfinite(x) or x < 0 for r in rows for x in r) or any(d<=0 for d,l in rows):
        raise ValueError('Need finite positive durations and nonnegative rates')
    return rows

def arrivals(rows, seed):
    rng = random.Random(seed)
    start = 0.
    for duration, rate in rows:
        end = start+duration
        t = start
        if rate:
            while True:
                t += rng.expovariate(rate)
                if t >= end: break
                yield t
        start = end

class Job:
    def __init__(self, kind, values, planned_ns=None):
        self.kind=kind; self.values=values; self.planned_ns=planned_ns
        self.enqueued_ns=time.monotonic_ns(); self.done=threading.Event()
        self.cancelled=False; self.result=None; self.error=None

class Dispatcher:
    """Only this thread calls infer. Up to N background waiting jobs + one BLE slot."""
    def __init__(self, backend, output, max_background=8):
        if not 1 <= max_background <= 64: raise ValueError('Background bound must be 1..64')
        self.backend=backend; self.output=Path(output)
        self.limit=max_background; self.q=queue.Queue(); self.lock=threading.Lock()
        self.pending_background=0; self.pending_foreground=0; self.active=False
        self.stopping=False; self.failure=None; self.completed=0; self.total_ms=0.
        self.counts=dict(background_arrived=0, background_dropped=0, foreground_arrived=0)
        self.log=(self.output/'jobs.jsonl').open('x')
        self.thread=threading.Thread(target=self.loop, daemon=True); self.thread.start()

    def write(self, row):
        # Caller holds the lock.
        self.log.write(json.dumps(row, allow_nan=False)+'\n'); self.log.flush()

    def submit(self, values, background=False, planned_ns=None):
        kind='background' if background else 'foreground'
        job=Job(kind, values, planned_ns)
        with self.lock:
            self.counts[kind+'_arrived'] += 1
            if self.stopping or self.failure:
                raise RuntimeError('Dispatcher stopped/faulted')
            if background and self.pending_background >= self.limit:
                self.counts['background_dropped'] += 1
                self.write(dict(event='drop_capacity', kind=kind, enqueued_ns=job.enqueued_ns,
                                planned_ns=planned_ns))
                return None
            if not background and self.pending_foreground:
                raise RuntimeError('Only one foreground request may wait; check I1 receiver')
            if background: self.pending_background += 1
            else: self.pending_foreground += 1
            self.write(dict(event='enqueue',kind=kind,enqueued_ns=job.enqueued_ns,planned_ns=planned_ns,
                            queue_length_jobs=self.pending_background+self.pending_foreground))
            self.q.put(job)
        return job

    def infer(self, values):
        job=self.submit(values)
        if not job.done.wait(4):
            with self.lock: job.cancelled=True
            raise TimeoutError('Foreground total queue+service exceeded 4 seconds')
        if job.error: raise job.error
        return job.result

    def loop(self):
        while True:
            job=self.q.get()
            if job is None: return
            start=time.monotonic_ns()
            with self.lock:
                if job.kind=='background': self.pending_background -= 1
                else: self.pending_foreground -= 1
                cancel=job.cancelled or self.stopping or bool(self.failure)
                self.active=not cancel
            if cancel: job.error=TimeoutError('Cancelled before execution')
            else:
                try: job.result=self.backend.infer(job.values)
                except BaseException as e:
                    job.error=e
                    with self.lock: self.failure=repr(e)
            end=time.monotonic_ns()
            with self.lock:
                if not cancel and job.error is None:
                    self.completed += 1; self.total_ms += (end-start)/1e6
                self.active=False
                self.write(dict(event='finished',kind=job.kind,enqueued_ns=job.enqueued_ns,
                    start_ns=start,end_ns=end,planned_ns=job.planned_ns,
                    queue_wait_ms=(start-job.enqueued_ns)/1e6,service_ms=(end-start)/1e6,
                    cancelled=bool(cancel or job.cancelled),error=None if job.error is None else repr(job.error),
                    native_tail_ms=None if job.result is None else job.result.get('tail_ms')))
            job.done.set()

    def snapshot(self):
        with self.lock:
            qlen=self.pending_background+self.pending_foreground
            return dict(queue_length_jobs=qlen,
                t_edge_service_mean_ms=None if not self.completed else self.total_ms/self.completed,
                dpu_utilization_ratio=None,
                status='error' if self.failure else ('busy' if qlen or self.active else 'ready'),
                active_job=bool(self.active), background_dropped_count=self.counts['background_dropped'])

    def close(self):
        with self.lock: self.stopping=True
        self.q.put(None); self.thread.join(10)
        if self.thread.is_alive(): raise RuntimeError('Worker did not stop; preserve unsealed output')
        self.backend.close(); self.log.close()
        (self.output/'queue_summary.json').write_text(json.dumps(dict(**self.counts,
            completed=self.completed, failure=self.failure,
            scope='shared FIFO; capacity counts pending jobs, active job excluded'),indent=2)+'\n')

class SessionWorker:
    """Drop-in Worker for a separately prepared Week9 BLE source snapshot."""
    def __init__(self, binary, deploy, cpu_ops, log_path):
        import platform
        if platform.system()!='Linux' or platform.machine()!='aarch64':
            raise ValueError('Real queue service requires KV260 Linux aarch64')
        from common import Worker as Native, load_reference
        config_path=Path(os.environ['W9_CONFIG']).resolve()
        self.config=json.loads(config_path.read_text())
        for name in ('scenario_csv','reference_npz'):
            self.config[name]=str((config_path.parent/self.config[name]).resolve())
        self.config['run_id']=Path(log_path).parent.name+'-'+__import__('uuid').uuid4().hex[:12]
        self.output=Path(log_path).parent/'queue'
        self.output.mkdir(exist_ok=False)
        self.stop=threading.Event(); self.producer_error=None
        rows=scenario(self.config['scenario_csv'])
        self.duration=sum(d for d,l in rows)
        reference=load_reference(self.config['reference_npz'])
        self.inputs=(reference['q'].astype('float32')*reference['scale_f16'].astype('float32')[:,:,None])
        backend=Native(binary,deploy,cpu_ops,log_path)
        expected=json.loads((config_path.parent/'expected_backend.json').read_text())
        if any(backend.metadata.get(k)!=v for k,v in expected.items()):
            backend.close()
            raise ValueError('Worker/model/plugins differ from verified Week8 baseline')
        warm_start=time.monotonic_ns()
        try:
            for i in range(20): backend.infer(self.inputs[i%len(self.inputs)])
        except BaseException:
            backend.close(); raise
        (self.output/'warmup.json').write_text(json.dumps(dict(count=20,
            elapsed_ms=(time.monotonic_ns()-warm_start)/1e6,
            scope='excluded from queue timing and MQTT publication'))+'\n')
        self.metadata=dict(backend.metadata, week9_queue='single shared FIFO; real background tails')
        self.dispatch=Dispatcher(backend,self.output,self.config['max_background'])
        self.telemetry=None
        try:
            if self.config['mqtt_enabled']:
                from telemetry import Telemetry
                self.telemetry=Telemetry(self.config,self.output,self.dispatch.snapshot)
            self.start_ns=time.monotonic_ns()
            (self.output/'queue_run.json').write_text(json.dumps(dict(config=self.config,
                backend=self.metadata, start_monotonic_ns=self.start_ns,start_unix_ns=time.time_ns(),
                scenario=scenario(self.config['scenario_csv']),
                source_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='real KV260 root CPU+DPU; background uses saved dequantized q/scale; not new patient data'),indent=2)+'\n')
            self.producer=threading.Thread(target=self.produce,args=(rows,),daemon=True)
            self.producer.start()
        except BaseException:
            if self.telemetry: self.telemetry.close()
            self.dispatch.close()
            raise

    def produce(self, rows):
        try:
            for i,t in enumerate(arrivals(rows,self.config['seed'])):
                planned=self.start_ns+int(t*1e9)
                if self.stop.wait(max(0.,(planned-time.monotonic_ns())/1e9)): return
                self.dispatch.submit(self.inputs[i%len(self.inputs)],background=True,planned_ns=planned)
        except BaseException as e:
            self.producer_error=repr(e)
            with self.dispatch.lock: self.dispatch.failure=self.producer_error

    def infer(self, values): return self.dispatch.infer(values)

    def close(self):
        self.stop.set(); self.producer.join(5)
        self.dispatch.close()
        if self.telemetry: self.telemetry.close()
        from common import seal
        seal(self.output)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',type=Path,required=True)
    p.add_argument('--deploy',type=Path,required=True)
    p.add_argument('--cpu-ops',type=Path,required=True)
    a=p.parse_args()
    # Prepared source layout: edge/server/week9 next to the reviewed week8 snapshot.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'week8'))
    os.environ['W9_CONFIG']=str(a.config.resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    worker=SessionWorker(a.worker,a.deploy,a.cpu_ops,a.output/'worker.log')
    try:
        worker.stop.wait(worker.duration)
        if worker.producer_error: raise RuntimeError(worker.producer_error)
        # Stop arrivals, then drain the bounded FIFO before closing.
        worker.producer.join(2)
        end=time.monotonic()+10
        while worker.dispatch.snapshot()['queue_length_jobs'] or worker.dispatch.snapshot()['active_job']:
            if time.monotonic()>end: raise TimeoutError('Drain deadline')
            time.sleep(.05)
        if worker.dispatch.failure: raise RuntimeError(worker.dispatch.failure)
    finally:
        worker.close()
    from common import seal
    seal(a.output)
    print('QUEUE_RUN_SAVED_REVIEW_REQUIRED')

if __name__=='__main__': main()
