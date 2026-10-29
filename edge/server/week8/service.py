"""Stateful s2 I1 receiver: normative codec, bounded retry cache and P1 sequence checks."""
from __future__ import annotations
import json,struct,sys,threading,time
from pathlib import Path
from common import ROOT,sha,hex_logits
sys.path.insert(0,str(ROOT/'contracts/i1v2_ref'))
import i1v2_reference as i1

class Receiver:
    def __init__(self,worker,key=None,clock=time.monotonic):
        self.worker=worker;self.profile=i1.load_profile(ROOT/'contracts/sv3_week5_approved_registry_v2.json')
        if key is not None and len(key)!=32:raise ValueError('Bench key must be 32 raw bytes')
        self.keys={} if key is None else {self.profile.key_id:key}
        self.clock=clock;self.cache={};self.highwater={};self.lock=threading.Lock();self.busy=False
    def handle(self,peer,packet,t_rx_ms):
        row={'request_id':None,'rho':None,'sequence':None,'len':len(packet),'sha256':sha(packet),
             'q_sha256':None,'scale_sha256':None,'scale_fp16_sha256':None,'logits':None,'logits_hex_le':None,'label':None,
             'result':'STARTED','t_rx_ms':t_rx_ms,'clock':'HOST_MONOTONIC_MS','peer':peer}
        def error(name,rid):
            row['result']=name;return i1.encode_error(rid,i1.STATUS[name]),row
        try:h=i1.parse_envelope(packet,self.profile.max_packet)
        except i1.Drop as e:row.update(result='DROP',reason=str(e));return None,row
        rid=h.request_id;row['request_id']=rid
        # Only B1..B3 precede duplicate lookup (I1 section 7.2).
        for bad,name in [(h.version!=2,'UNSUPPORTED_VERSION'),(h.message_type!=1,'INVALID_MESSAGE_TYPE'),(rid==0,'INVALID_REQUEST_ID')]:
            if bad:return error(name,rid)
        cachekey=(peer,rid); now=self.clock()
        with self.lock:
            for k,v in list(self.cache.items()):
                if v['done'] and now-v['created']>=60:del self.cache[k]
            old=self.cache.get(cachekey)
            if old:
                if old['sha']!=row['sha256']:return error('DUPLICATE_CONFLICT',rid)
                event=old['event'];owner=False
            else:
                if self.busy:return error('EDGE_BUSY',rid)
                if len(self.cache)>=16:
                    eligible=[k for k,v in self.cache.items() if v['done'] and (k[0]==peer and k[1]!=rid)]
                    if not eligible:return error('EDGE_BUSY',rid)
                    del self.cache[min(eligible,key=lambda k:self.cache[k]['created'])]
                old={'sha':row['sha256'],'created':now,'done':False,'event':threading.Event()}
                self.cache[cachekey]=old;event=old['event'];owner=True;self.busy=True
        if not owner:
            if not event.wait(4.5):return error('EDGE_BUSY',rid)
            cached=dict(old['row']);cached.update(t_rx_ms=t_rx_ms,cache_hit=True)
            return old['response'],cached
        response=None
        try:
            req=i1.parse_request(packet,self.profile);row['rho']='P1' if req.transformed else 'P0'
            row['split_s']=req.split.split_point
            if req.split.split_point!=2:raise i1.Reject('UNSUPPORTED_SPLIT',rid)
            q=i1.recover_q(req,self.keys)
            row['q_sha256']=sha(q)
            # Canonical ORIGINAL-channel wire scales, float32 little endian.
            row['scale_sha256']=sha(struct.pack('<%df'%len(req.scales),*req.scales))
            # Additional sender-review convention; leave the original FP32 hash intact.
            row['scale_fp16_sha256']=sha(struct.pack('<%de'%len(req.scales),*req.scales))
            if req.transformed:
                sender,sequence=struct.unpack('<IQ',req.nonce);row['sequence']=sequence
                sequence_key=(peer,self.profile.key_id,sender)
                if sequence<=self.highwater.get(sequence_key,0):raise i1.Reject('INVALID_NONCE',rid)
                self.highwater[sequence_key]=sequence
            result=self.worker.infer(i1.dequantize(req,q));response=i1.encode_response(rid,result['logits'])
            kind,logits=i1.parse_response(response,rid,self.profile.max_packet)
            row.update(logits=hex_logits(logits),logits_hex_le=hex_logits(logits),logits_float=logits,
                label=i1.predicted_class(logits),result=kind,tail_ms=result['tail_ms'],cache_hit=False)
        except i1.Reject as e:response,row=error(e.name,rid)
        except TimeoutError:response,row=error('TIMEOUT',rid)
        except Exception as e:
            response,row=error('INFERENCE_FAILED',rid);row['reason']=type(e).__name__
        finally:
            with self.lock:
                old.update(done=True,response=response,row=dict(row));self.busy=False;event.set()
        return response,row
