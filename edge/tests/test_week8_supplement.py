"""Supplemental PHY HOST fixtures; no controller writes, radio or real keys."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'edge/server/week8'))
import ble_service
import supplemental_link as supp
from common import seal,hex_logits,save


class SupplementTests(unittest.TestCase):
    def test_handle_bytes_and_hci_status(self):
        con='Connections:\n\t< LE C8:F6:EE:EF:02:CF handle 291 state 1 lm MASTER\n'
        h=supp.handle_for(con,'C8:F6:EE:EF:02:CF')
        self.assertEqual(h,291)
        self.assertEqual(supp.phy_args(h,'set-2m'),['0x08','0x0032','0x23','0x01','0x00','0x02','0x02','0x00','0x00'])
        with self.assertRaises(ValueError):supp.handle_for(con,'00:11:22:33:44:55')
        with self.assertRaises(ValueError):supp.handle_for(con+con,'C8:F6:EE:EF:02:CF')
        self.assertEqual(supp.command_status('> HCI Event: 0x0f plen 4\n 00 01 32 20\n',0x2032),(0,b''))
        self.assertEqual(supp.command_status('> HCI Event: 0x0f plen 4\n 0C 01 32 20\n',0x2032)[0],12)
        self.assertEqual(supp.command_status('> HCI Event: 0x0e plen 8\n 01 30 20 00 23 01 02 02\n',0x2030)[1],b'\x23\x01\x02\x02')
        with self.assertRaises(ValueError):supp.command_status('> HCI Event: 0x0e plen 4\n 01 01 10 00\n',0x2032)

    def test_default_phy_preserves_primary_bredr(self):
        text=('Supported phys: BR1M1SLOT EDR2M1SLOT LE1MTX LE1MRX LE2MTX LE2MRX\n'
              'Configurable phys: EDR2M1SLOT LE2MTX LE2MRX\n'
              'Selected phys: BR1M1SLOT EDR2M1SLOT LE1MTX LE1MRX\n')
        state=supp.parse_phys(text);desired=supp.allow_2m(state)
        self.assertIn('BR1M1SLOT',desired);self.assertIn('EDR2M1SLOT',desired)
        self.assertTrue({'LE1MTX','LE1MRX','LE2MTX','LE2MRX'}<=set(desired))
        state['supported'].remove('LE2MRX')
        with self.assertRaises(ValueError):supp.allow_2m(state)
        self.assertEqual(supp.parse_phys('Supported phys: LE1MTX LE1MRX\nConfigurable phys: \nSelected phys: LE1MTX LE1MRX\n')['configurable'],[])

    def test_one_and_ten_log_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,count in [('trial1',1),('trial2',10)]:
                folder=root/name;folder.mkdir();rows=[]
                for i in range(count):
                    rows.append(dict(request_id=i+1,rho='P0' if i%2==0 else 'P1',result='OK',
                        sequence=None if i%2==0 else 100+i,
                        response_sent=True,cache_hit=False,connection=0,q_sha256=str(i//2),
                        scale_fp16_sha256='fixture',logits_float=[1.,2.,3.,4.,5.],
                        logits_hex_le=hex_logits([1,2,3,4,5]),tail_ms=45.5))
                (folder/'peer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                save(folder/'run.json',{'backend':{'scope':'FIXTURE'}});seal(folder)
            with patch('builtins.print'):supp.export(types.SimpleNamespace(root=root,output=root/'export'))
            out=[json.loads(x) for x in (root/'export/trial2_sv1.jsonl').read_text().splitlines()]
            self.assertEqual(len(out),10);self.assertEqual(out[0]['tail_us'],45500.)
            self.assertEqual(out[0]['logits'],[1.,2.,3.,4.,5.])
            self.assertEqual(out[0]['scale_sha256'],'fixture')
            import shutil
            shutil.copytree(root/'trial2',root/'trial4_2m')
            with patch('builtins.print'):
                supp.export(types.SimpleNamespace(root=root,output=root/'export_124',trial4='trial4_2m'))
            summary=json.loads((root/'export_124/summary.json').read_text())
            self.assertEqual(summary['trials']['trial4']['source_folder'],'trial4_2m')
            self.assertEqual(len((root/'export_124/supp4_pairs5_2M.jsonl').read_text().splitlines()),10)
            self.assertTrue((root/'export_124/supp1_one_p0.jsonl').is_file())
            self.assertTrue((root/'export_124/supp2_pairs5_1M.jsonl').is_file())
            info=json.loads((root/'export_124/service_info.json').read_text())
            self.assertIsNone(info['trial4']['ble_service_sha256_recorded'])
            self.assertIn('DERIVED',(root/'export_124/READ_FIRST.txt').read_text())
            (root/'trial4_2m/peer.jsonl').write_text('{}\n')
            with self.assertRaises(ValueError):
                supp.export(types.SimpleNamespace(root=root,output=root/'bad',trial4='trial4_2m'))
            self.assertFalse((root/'bad').exists())

    def test_count_reached_keeps_connection_until_disconnect(self):
        state={'held':False};device=types.SimpleNamespace(address='C8:F6:EE:EF:02:CF')
        class Scanner:
            @staticmethod
            async def find_device_by_filter(*args,**kw):return device
        class Client:
            def __init__(self,*args,**kw):
                self._backend=self;self.mtu_size=247;self.is_connected=True;self.callback=kw['disconnected_callback']
            async def _acquire_mtu(self):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):self.is_connected=False
            async def start_notify(self,char,notify):asyncio.get_running_loop().call_soon(notify,None,b'frame')
            async def write_gatt_char(self,*args,**kw):
                def later():
                    state['held']=not state['task'].done()
                    if state.get('cancel'):state['task'].cancel()
                    else:self.is_connected=False;self.callback(self)
                asyncio.get_running_loop().call_later(.02,later)
        class Worker:
            metadata={}
            def __init__(self,*args):pass
            def close(self):state['closed']=True
        class Receiver:
            def __init__(self,*args):pass
            def handle(self,*args):return b'R'*64,{'result':'OK','request_id':1,'t_rx_ms':0}
        async def inline(fn,*args):return fn(*args)
        with tempfile.TemporaryDirectory() as tmp:
            a=types.SimpleNamespace(output=Path(tmp)/'trial',mode='inference',worker='fixture',deploy='fixture',cpu_ops='fixture',
                key_file=None,sv1_session=False,hold_after_count=True,mtu=247,adapter='hci0',address=None,max_s=2,expect=1)
            async def exercise():
                state['task']=asyncio.create_task(ble_service.run(a));await state['task']
            with patch.dict(sys.modules,{'bleak':types.SimpleNamespace(BleakClient=Client,BleakScanner=Scanner)}), \
                    patch('platform.system',return_value='Linux'),patch('platform.machine',return_value='aarch64'), \
                    patch('importlib.metadata.version',return_value='0.22.3'), \
                    patch.object(ble_service,'Worker',Worker),patch.object(ble_service,'Receiver',Receiver), \
                    patch.object(ble_service.asyncio,'to_thread',inline), \
                    patch.object(ble_service.ble.Reassembler,'feed',return_value=(1,b'frame')),patch('builtins.print'):
                asyncio.run(exercise())
            self.assertTrue(state['held']);self.assertTrue(state['closed'])
            self.assertEqual(json.loads((a.output/'summary.json').read_text())['rows'],1)
            a.output=Path(tmp)/'trial_cancel';state['cancel']=True
            with patch.dict(sys.modules,{'bleak':types.SimpleNamespace(BleakClient=Client,BleakScanner=Scanner)}), \
                    patch('platform.system',return_value='Linux'),patch('platform.machine',return_value='aarch64'), \
                    patch('importlib.metadata.version',return_value='0.22.3'), \
                    patch.object(ble_service,'Worker',Worker),patch.object(ble_service,'Receiver',Receiver), \
                    patch.object(ble_service.asyncio,'to_thread',inline), \
                    patch.object(ble_service.ble.Reassembler,'feed',return_value=(1,b'frame')),patch('builtins.print'):
                with self.assertRaises(asyncio.CancelledError):asyncio.run(exercise())
            self.assertTrue((a.output/'sha256sum_results.txt').is_file())
            self.assertEqual(len((a.output/'peer.jsonl').read_text().splitlines()),1)


if __name__=='__main__':unittest.main()
