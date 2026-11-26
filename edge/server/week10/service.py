"""Multi-split I1 v2 receiver, separate bounded response cache and model cache.

Offline/adapter core; no BLE transport or durable replay protection is claimed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'contracts/i1v2_ref'))
import i1v2_reference as i1


def hex_logits(values):
    return [struct.pack('<f', float(x)).hex() for x in values]


class Receiver:
    def __init__(self, backend, key=None, clock=time.monotonic):
        self.backend = backend
        self.profile = i1.load_profile(ROOT / 'contracts/sv3_week5_approved_registry_v2.json')
        if key is not None and len(key) != 32:
            raise ValueError('Key must contain 32 raw bytes')
        self.keys = {} if key is None else {self.profile.key_id: key}
        self.clock = clock
        self.cache, self.highwater = {}, {}
        self.lock = threading.Lock()
        self.busy = False

    def handle(self, peer, packet, t_rx_ms):
        started_ns = time.monotonic_ns()
        row = dict(request_id=None, rho=None, sequence=None, split_s=None,
                   packet_sha256=hashlib.sha256(packet).hexdigest(), t_rx_ms=t_rx_ms,
                   clock='BOARD_MONOTONIC_MS', result='STARTED', peer=peer,
                   response_cache_hit=False, model_cache_hit=None,
                   switch_ms=None, tail_ms=None, logits_hex_le=None)

        def error(name, rid):
            row['result'] = name
            return i1.encode_error(rid, i1.STATUS[name]), row

        try:
            h = i1.parse_envelope(packet, self.profile.max_packet)
        except i1.Drop as e:
            row.update(result='DROP', reason=str(e))
            return None, row
        rid = h.request_id
        row['request_id'] = rid
        for bad, name in ((h.version != 2, 'UNSUPPORTED_VERSION'),
                          (h.message_type != 1, 'INVALID_MESSAGE_TYPE'),
                          (rid == 0, 'INVALID_REQUEST_ID')):
            if bad:
                return error(name, rid)
        cache_key = (peer, rid)
        now = self.clock()
        with self.lock:
            for k, v in list(self.cache.items()):
                if v['done'] and now - v['created'] >= 60:
                    del self.cache[k]
            old = self.cache.get(cache_key)
            if old is not None:
                if old['sha'] != row['packet_sha256']:
                    return error('DUPLICATE_CONFLICT', rid)
                owner = False
            else:
                if self.busy:
                    return error('EDGE_BUSY', rid)
                if len(self.cache) >= 16:
                    candidates = [k for k, v in self.cache.items() if v['done'] and k[0] == peer]
                    if not candidates:
                        return error('EDGE_BUSY', rid)
                    del self.cache[min(candidates, key=lambda k: self.cache[k]['created'])]
                old = dict(sha=row['packet_sha256'], created=now, done=False, event=threading.Event())
                self.cache[cache_key] = old
                self.busy = True
                owner = True
        if not owner:
            if not old['event'].wait(4.5):
                return error('EDGE_BUSY', rid)
            cached = dict(old['row'])
            cached.update(t_rx_ms=t_rx_ms, response_cache_hit=True, switch_ms=None,
                          tail_ms=None, native_select_ms=None, load_ms=None,
                          service_ms=(time.monotonic_ns() - started_ns) / 1e6)
            return old['response'], cached
        response = None
        try:
            req = i1.parse_request(packet, self.profile)
            row.update(split_s=req.split.split_point, rho='P1' if req.transformed else 'P0',
                       model_profile_id=req.model_profile_id)
            q = i1.recover_q(req, self.keys)
            row['q_sha256'] = hashlib.sha256(q).hexdigest()
            row['scale_sha256'] = hashlib.sha256(struct.pack('<%df' % len(req.scales), *req.scales)).hexdigest()
            if req.transformed:
                sender, sequence = struct.unpack('<IQ', req.nonce)
                sequence_key = (peer, self.profile.key_id, sender)
                row['sequence'] = sequence
                if sequence <= self.highwater.get(sequence_key, 0):
                    raise i1.Reject('INVALID_NONCE', rid)
                self.highwater[sequence_key] = sequence
            values = i1.dequantize(req, q)
            result = self.backend.infer(req.split.split_point, values)
            # s10 must remain identity even for a faulty adapter implementation.
            if req.split.split_point == 10 and hex_logits(result['logits']) != hex_logits(values):
                raise ValueError('s10 backend changed identity logits')
            response = i1.encode_response(rid, result['logits'])
            kind, logits = i1.parse_response(response, rid, self.profile.max_packet)
            for k in ('previous_s', 'switch_ms', 'native_select_ms', 'load_ms', 'tail_ms',
                      'worker_pid', 'context_id', 'load_count', 'contexts_count', 'model_cache_hit'):
                row[k] = result.get(k)
            row.update(result=kind, logits=logits, logits_hex_le=hex_logits(logits),
                       label=i1.predicted_class(logits))
        except i1.Reject as e:
            response, row = error(e.name, rid)
        except TimeoutError as e:
            response, row = error('TIMEOUT', rid)
            row['reason'] = str(e)
        except Exception as e:
            response, row = error('INFERENCE_FAILED', rid)
            row['reason'] = type(e).__name__ + ': ' + str(e)
        finally:
            row['service_ms'] = (time.monotonic_ns() - started_ns) / 1e6
            with self.lock:
                old.update(done=True, response=response, row=dict(row))
                self.busy = False
                old['event'].set()
        return response, row
