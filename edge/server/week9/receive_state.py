"""Run on SV1 PC: record status and ACK only after its row was written."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time

TOPIC = 'adaptive_split/edge/KV260_NODE_01/status'

def main():
    import paho.mqtt.client as mqtt
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=1885)
    p.add_argument('--receiver-id', default='SV1_PC')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    log = (a.output/'received.jsonl').open('x')
    ready = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='w9-'+a.receiver_id)
    def connect(c,u,f,reason,props):
        if reason == 0:
            c.subscribe(TOPIC, qos=0)
    def subscribed(c,u,mid,reasons,props):
        ready.set(); print('SV1_MQTT_SUBSCRIBED', flush=True)
    def message(c,u,msg):
        t = time.monotonic_ns()
        row = json.loads(msg.payload)
        log.write(json.dumps(dict(receive_unix_ns=time.time_ns(), receive_monotonic_ns=t,
            receiver_id=a.receiver_id, retained=bool(msg.retain), state=row))+'\n')
        log.flush()
        c.publish(TOPIC+'/ack', json.dumps(dict(run_id=row['run_id'],
            seq_number=row['seq_number'], receiver_id=a.receiver_id)), qos=0, retain=False)
    client.on_connect=connect; client.on_subscribe=subscribed; client.on_message=message
    client.connect(a.host, a.port, 30); client.loop_start()
    try:
        if not ready.wait(10): raise RuntimeError('No SUBACK; stop before experiment')
        while True: time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect(); client.loop_stop(); log.close()
        (a.output/'sha256sum_results.txt').write_text(
            hashlib.sha256((a.output/'received.jsonl').read_bytes()).hexdigest()+'  received.jsonl\n')

if __name__ == '__main__': main()
