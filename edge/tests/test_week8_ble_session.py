"""HOST orchestration test with fake BLE/worker, never radio/DPU evidence."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'edge/server/week8'))
import ble_service as service
import export_g2
from common import seal


class SessionTests(unittest.TestCase):
    def test_one_connection_four_logs_and_export(self):
        state = {'clients': 0, 'workers': 0, 'sent': 0}
        device = types.SimpleNamespace(address='C8:F6:EE:EF:02:CF')

        class Scanner:
            @staticmethod
            async def find_device_by_filter(filter_fn, **kw):
                assert filter_fn(device, types.SimpleNamespace(
                    local_name='ASI-SV1', service_uuids=[service.SERVICE]))
                return device

        class Client:
            def __init__(self, *a, **kw):
                state['clients'] += 1
                self._backend = self
                self.mtu_size = 247
                self.is_connected = True
                self.on_disconnect = kw['disconnected_callback']
            async def _acquire_mtu(self):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                self.is_connected = False
            async def start_notify(self, uuid, callback):
                self.callback = callback
                asyncio.get_running_loop().call_soon(callback, None, b'frame')
            async def write_gatt_char(self, *a, **kw):
                state['sent'] += 1
                if state['sent'] < 212:
                    asyncio.get_running_loop().call_soon(self.callback, None, b'frame')
                else:
                    asyncio.get_running_loop().call_soon(self.on_disconnect, self)

        class Worker:
            metadata = {}
            def __init__(self, *a):
                state['workers'] += 1
            def close(self):
                state['closed'] = True

        class Receiver:
            def __init__(self, *a):
                pass
            def handle(self, peer, frame, t_rx):
                i = state['sent']
                return b'R'*64, {
                    'request_id': i+1, 'rho': 'P0' if i == 0 or (i > 1 and i % 2 == 0) else 'P1',
                    'result': 'OK', 'cache_hit': False, 't_rx_ms': t_rx,
                    'q_sha256': 'q', 'scale_sha256': 'fp32', 'scale_fp16_sha256': 'fp16',
                    'logits_float': [1., 2., 3., 4., 5.], 'label': 4,
                }

        fake = types.SimpleNamespace(BleakClient=Client, BleakScanner=Scanner)
        async def inline_handle(fn, *args):
            # This tests stage orchestration; thread/cache behavior has its own tests.
            return fn(*args)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            # Deliberately fake key, outside the project; never open the user's key.
            (path/'fake_key').write_bytes(bytes(range(32)))
            args = types.SimpleNamespace(output=path/'session', mode='inference',
                worker='fake', deploy='fake', cpu_ops='fake', key_file=path/'fake_key',
                sv1_session=True, mtu=247, adapter='hci0', address=device.address,
                max_s=30, expect=212)
            with patch.dict(sys.modules, {'bleak': fake}), \
                    patch('importlib.metadata.version', return_value='0.22.3'), \
                    patch('platform.system', return_value='Linux'), \
                    patch('platform.machine', return_value='aarch64'), \
                    patch.object(service, 'Worker', Worker), \
                    patch.object(service, 'Receiver', Receiver), \
                    patch.object(service.asyncio, 'to_thread', inline_handle), \
                    patch.object(service.ble.Reassembler, 'feed', return_value=(1, b'frame')), \
                    patch('builtins.print'):
                asyncio.run(service.run(args))
            self.assertEqual(state, {'clients': 1, 'workers': 1, 'sent': 212, 'closed': True})
            for name, count in service.STAGES:
                rows = [json.loads(x) for x in (args.output/(name+'.jsonl')).read_text().splitlines()]
                self.assertEqual(len(rows), count)
                self.assertTrue(all(r['scale_sha256'] == 'fp16' for r in rows))
                self.assertTrue(all(r['t_tx_done_ms'] >= r['t_rx_ms'] for r in rows))
            with patch.object(sys, 'argv', ['export_g2', '--session', str(args.output),
                                           '--output', str(path/'g2')]):
                export_g2.main()
            self.assertEqual(len((path/'g2/peer.jsonl').read_text().splitlines()), 200)
            original = [json.loads(x) for x in (args.output/'peer.jsonl').read_text().splitlines()]
            for failure in ('incomplete', 'reconnected', 'unsent', 'wrong_stage'):
                copy = json.loads(json.dumps(original))
                if failure == 'incomplete': copy.pop()
                elif failure == 'reconnected': copy[-1]['connection'] = 1
                elif failure == 'unsent': copy[-1]['response_sent'] = False
                else: copy[-1]['stage'] = 'pairs_5'
                folder = path/failure;folder.mkdir()
                (folder/'peer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in copy))
                seal(folder)
                with patch.object(sys, 'argv', ['export_g2', '--session', str(folder),
                                               '--output', str(path/(failure+'_output'))]):
                    with self.assertRaises(ValueError): export_g2.main()
            # A modified request log must fail its saved checksum before export.
            with (args.output/'peer.jsonl').open('a') as f:
                f.write('{}\n')
            with patch.object(sys, 'argv', ['export_g2', '--session', str(args.output),
                                           '--output', str(path/'bad')]):
                with self.assertRaises(ValueError):
                    export_g2.main()
            self.assertFalse((path/'bad').exists())


if __name__ == '__main__':
    unittest.main()
