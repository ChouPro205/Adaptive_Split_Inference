"""Synthetic HOST fixtures only; no Device, BLE, offline-repeat or DPU evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'edge/server/week8'))
from common import hex_logits, save, seal, file_sha
import review_after_g2 as review
from sv1_log import stage_for


class ReviewTests(unittest.TestCase):
    def test_derived_rows_repeat_and_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for name in ('first', 'second'):
                path = base/name;path.mkdir()
                rows = [{'sample_index': i, 'sample_id': str(i), 'test_index': i,
                         'logits': [1., 0., 0., 0., 0.], 'logits_hex_le': hex_logits([1, 0, 0, 0, 0]),
                         'label': 0, 'class_match': True} for i in range(100)]
                (path/'predictions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                save(path/'run.json', dict(reference_sha256='fixture', model_sha256='fixture',
                                           worker_sha256='fixture', plugins={'fixture': 'fixture'}))
                seal(path)
            session = base/'session';session.mkdir();rows = [];seq = 0
            for i in range(212):
                rho = 'P0' if i == 0 or (i >= 2 and i % 2 == 0) else 'P1'
                if rho == 'P1': seq += 1
                rows.append(dict(request_id=i+1, rho=rho, sequence=seq if rho == 'P1' else None,
                    stage=stage_for(i), result='OK', response_sent=True, connection=0,
                    cache_hit=False, logits_float=[1., 0., 0., 0., 0.],
                    logits_hex_le=hex_logits([1, 0, 0, 0, 0]), q_sha256='fixture',
                    scale_fp16_sha256='fixture', t_rx_ms=i*100, t_tx_done_ms=i*100+48,
                    tail_ms=45.7, label=0, len=3000))
            (session/'peer.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            save(session/'run.json', {'backend': dict(model_sha256='fixture', worker_sha256='fixture',
                                                     plugins={'fixture': 'fixture'})})
            seal(session)
            before = file_sha(session/'peer.jsonl')
            argv = ['review', '--session', str(session), '--offline-first', str(base/'first'),
                    '--offline-second', str(base/'second'), '--output', str(base/'out')]
            with patch.object(sys, 'argv', argv), patch('builtins.print'): review.main()
            summary = json.loads((base/'out/summary.json').read_text())
            self.assertEqual(summary['offline_repeat_bit_matches'], 100)
            self.assertTrue(summary['p1_monotonic'])
            self.assertEqual(summary['edge_elapsed_shorter_than_tail_requests'], [])
            derived = [json.loads(x) for x in (base/'out/requests_212_sv1.jsonl').read_text().splitlines()]
            self.assertEqual(len(derived), 212);self.assertEqual(derived[0]['tail_us'], 45700.)
            self.assertEqual(derived[0]['logits'], [1., 0., 0., 0., 0.])
            self.assertEqual(file_sha(session/'peer.jsonl'), before)
            self.assertIn('PENDING', summary['acceptance'])
            with (session/'peer.jsonl').open('a') as f: f.write('{}\n')
            with patch.object(sys, 'argv', argv[:-1]+[str(base/'tampered')]):
                with self.assertRaises(ValueError): review.main()
            self.assertFalse((base/'tampered').exists())


if __name__ == '__main__': unittest.main()
