"""MQTT status + matching receiver ACK; RTT is an upper bound on delivery delay."""
import json
import threading
import time
from pathlib import Path

TOPIC = 'adaptive_split/edge/KV260_NODE_01/status'
ACK = TOPIC+'/ack'

class Telemetry:
    def __init__(self, config, output, snapshot):
        import paho.mqtt.client as mqtt
        self.output = Path(output)
        self.snapshot = snapshot
        self.stop = threading.Event()
        self.connected = threading.Event()
        self.lock = threading.Lock()
        self.pending = {}
        self.run_id = config['run_id']
        self.receiver = config['receiver_id']
        self.sent = self.acked = self.failed = self.expired = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id='w9-edge-'+self.run_id[-20:])
        def connect(client, userdata, flags, reason, properties):
            if reason == 0:
                client.subscribe(ACK, qos=0)
                self.connected.set()
        self.client.on_connect = connect
        self.client.on_message = self.message
        import socket
        def low_latency_socket(client, userdata, sock):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) != 1:
                raise RuntimeError('TCP_NODELAY not enabled')
            print('MQTT_TCP_NODELAY=1', flush=True)
        self.client.on_socket_open = low_latency_socket
        self.client.connect(config['broker_host'], config['broker_port'], 30)
        self.client.loop_start()
        if not self.connected.wait(10):
            self.client.disconnect(); self.client.loop_stop()
            raise RuntimeError('MQTT connect failed; no measurement')
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def write(self, filename, row):
        with (self.output/filename).open('a') as f:
            f.write(json.dumps(row, allow_nan=False)+'\n')

    def message(self, client, userdata, msg):
        end = time.monotonic_ns()
        try:
            row = json.loads(msg.payload)
            if row['run_id'] != self.run_id or row['receiver_id'] != self.receiver:
                return
            seq = row['seq_number']
            with self.lock:
                start = self.pending.pop(seq, None)
            if start is not None:
                self.acked += 1
                self.write('mqtt_ack.jsonl', dict(seq_number=seq, run_id=self.run_id,
                    receiver_id=self.receiver, publisher_send_ns=start, publisher_ack_ns=end,
                    ack_rtt_ms=(end-start)/1e6,
                    meaning='upper bound for this status delivery to receiver; not one-way measurement'))
        except (KeyError, ValueError, TypeError):
            self.write('mqtt_errors.jsonl', dict(event='invalid_ack', monotonic_ns=end))

    def loop(self):
        seq = 0
        target = time.monotonic()
        try:
            while not self.stop.is_set():
                now = time.monotonic_ns()
                with self.lock:
                    expired = [s for s,t in self.pending.items() if now-t > 2_000_000_000]
                    for s in expired:
                        del self.pending[s]
                    self.expired += len(expired)
                    self.pending[seq] = now
                row = dict(schema_version='1.0.0', edge_id='KV260_NODE_01',
                    timestamp_unix_ms=time.time_ns()//1_000_000, seq_number=seq,
                    run_id=self.run_id, publisher_monotonic_ns=now, **self.snapshot())
                info = self.client.publish(TOPIC, json.dumps(row, allow_nan=False), qos=0, retain=False)
                self.sent += 1
                if info.rc != 0:
                    self.failed += 1
                self.write('mqtt_sent.jsonl', dict(**row, publish_rc=info.rc,
                    schedule_late_ms=max(0., (time.monotonic()-target)*1000)))
                seq += 1
                target += .1
                # No catch-up burst if the OS suspended the process.
                if target < time.monotonic():
                    target = time.monotonic()+.1
                self.stop.wait(max(0., target-time.monotonic()))
        except BaseException as e:
            self.failed += 1
            self.write('mqtt_errors.jsonl', dict(event='publisher_stopped', error=repr(e)))

    def close(self):
        self.stop.set(); self.thread.join(5)
        time.sleep(.3)
        self.client.disconnect(); self.client.loop_stop()
        with self.lock:
            unacked = self.expired+len(self.pending)
        self.write('mqtt_summary.jsonl', dict(sent=self.sent, acked=self.acked,
            publish_errors=self.failed, unacked=unacked, receiver_id=self.receiver,
            acceptance='REQUIRES_RECEIVER_LOG_AND_REVIEW'))
