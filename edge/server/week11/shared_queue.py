"""One FIFO for background/foreground tails; no device access at import."""
from collections import deque
import json
import threading
import time


class Dispatcher:
    def __init__(self, backend, folder, limit=8, deadline=4):
        self.backend, self.limit, self.deadline = backend, limit, deadline
        self.cv = threading.Condition()
        self.pending = deque()
        self.active = self.failure = None
        self.closed = False
        self.counter = 0
        self.local = threading.local()
        self.folder = folder
        self.counts = dict(background_arrived=0, background_dropped=0, foreground_arrived=0)
        self.completed = 0
        self.log = (folder/'jobs.jsonl').open('x')
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def record(self, **row):
        self.log.write(json.dumps(row, allow_nan=False)+'\n')
        self.log.flush()

    def snapshot(self):
        with self.cv:
            return dict(queue_length_jobs=len(self.pending), active_job=self.active is not None,
                        active_job_id=self.active, snapshot_ns=time.monotonic_ns())

    def submit(self, split, values, background=False, planned_ns=None, context=None):
        with self.cv:
            if self.closed or self.failure:
                raise RuntimeError('FIFO closed/faulted: '+str(self.failure))
            self.counter += 1
            kind = 'background' if background else 'foreground'
            self.counts[kind+'_arrived'] += 1
            row = dict(job_id=self.counter, kind=kind, split_s=split, planned_ns=planned_ns,
                       enqueued_ns=time.monotonic_ns(), queue_length_before_enqueue=len(self.pending),
                       active_before_enqueue=self.active, **(context or {}))
            count = sum(j['kind'] == kind for j in self.pending)
            if count >= (self.limit if background else 1):
                if background: self.counts['background_dropped'] += 1
                self.record(event='drop_capacity', **row)
                if background: return None
                raise RuntimeError('Foreground FIFO capacity exceeded')
            job = dict(row, values=values, done=threading.Event(), result=None, error=None, cancelled=False)
            self.pending.append(job)
            self.record(event='enqueue', queue_length_jobs=len(self.pending), **row)
            self.cv.notify()
            return job

    def infer(self, split, values):
        job = self.submit(split, values, context=getattr(self.local, 'context', {}))
        if not job['done'].wait(self.deadline):
            with self.cv: job['cancelled'] = True
            raise TimeoutError('Foreground queue+tail exceeded deadline')
        if job['error']: raise job['error']
        self.local.last = job['result']
        return job['result']

    def loop(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.pending or self.closed)
                if not self.pending: return
                job = self.pending.popleft()
                self.active = job['job_id']
                start = time.monotonic_ns()
                cancel = job['cancelled'] or self.failure is not None
            try:
                if cancel: raise TimeoutError('Job cancelled/backend previously failed')
                result = self.backend.infer(job['split_s'], job['values'])
                end = time.monotonic_ns()
                job['result'] = dict(result, job_id=job['job_id'], enqueue_ns=job['enqueued_ns'],
                    tail_start_ns=start, tail_end_ns=end, queue_wait_ms=(start-job['enqueued_ns'])/1e6,
                    dispatch_and_tail_ms=(end-start)/1e6)
            except BaseException as exc:
                end = time.monotonic_ns()
                job['error'] = exc
                with self.cv: self.failure = repr(exc)
            with self.cv:
                self.record(event='finished', **{k:v for k,v in job.items()
                    if k not in ('values','done','result','error','cancelled')},
                    start_ns=start, end_ns=end, queue_wait_ms=(start-job['enqueued_ns'])/1e6,
                    service_ms=(end-start)/1e6, cancelled=job['cancelled'], error=None if job['error'] is None else repr(job['error']),
                    native_tail_ms=None if job['result'] is None else job['result'].get('tail_ms'))
                if job['error'] is None and not job['cancelled']: self.completed += 1
                self.active = None
                job['done'].set()
                self.cv.notify_all()

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()
        self.thread.join(40)
        if self.thread.is_alive(): raise RuntimeError('FIFO did not drain; preserve unsealed output')
        self.log.close()
        with (self.folder/'queue_summary.json').open('x') as f:
            json.dump(dict(**self.counts, completed=self.completed, failure=self.failure,
                scope='shared FIFO; capacity counts pending jobs, active job excluded'), f, indent=2)


