"""Offline corruption tests on actual evidence; never fabricates passing MCU data."""
import argparse
import copy
from pathlib import Path
import unittest
from accept_week5_mcu import read, validate_chain, validate_session, sizes
from week5_common import sha, write_json

class Tests(unittest.TestCase):
    def test_receipt_chain(self):
        validate_chain(*self.arguments)

    def test_receipt_corruption(self):
        mutations = [
            (0,'verified_source_commit','0'*40),(0,'flash','PASS'),
            (2,'origin','SIMULATED'),(2,'exit_code',1),(2,'preparation_sha256','0'*64),(2,'port','COM999'),
            (3,'origin','SIMULATED'),(3,'commands_completed',235),(3,'capture_sha256','0'*64),
            (3,'firmware_id','0'*64),(3,'preparation_sha256','0'*64),(3,'port','COM999'),
            (3,'collected_utc','2000-01-01T00:00:00+00:00'),(5,'exit_code',1)]
        for index,key,value in mutations:
            with self.subTest(index=index,key=key):
                args = copy.deepcopy(self.arguments)
                args[index][key] = value
                with self.assertRaises(ValueError): validate_chain(*args)
        args = copy.deepcopy(self.arguments)
        args[2]['application']['sha256'] = '0'*64
        with self.assertRaises(ValueError): validate_chain(*args)
        args = copy.deepcopy(self.arguments)
        args[5]['arguments'][3] = 'COM999'
        with self.assertRaises(ValueError): validate_chain(*args)

    def test_payload_and_scales_sizes(self):
        mapping = [dict(split_point_s=9,cut_name='NC test',shape=[1,32],layout='NC',num_elements=32,channels=32)]
        row = sizes(mapping)[0]
        self.assertEqual((row['fp32_bytes'],row['int8_payload_bytes'],row['fp16_scale_bytes'],row['int8_plus_fp16_bytes']), (128,32,64,96))
        self.assertEqual(row['payload_reduction_factor'],4)
        self.assertAlmostEqual(row['total_reduction_factor'],4/3)
        self.assertEqual(row['total_reduction_percent'],25)

    def test_independent_actual_capture_acceptance(self):
        result = validate_session(self.session,self.preparation)
        self.assertEqual(result['scope'],'REAL_MCU_CAPTURE')
        self.assertEqual((result['primary_cases'],result['mixed_cases'],result['historical_p2']['primary_cases']),(220,16,20))
        self.assertEqual(result['image_source_sha'],self.arguments[0]['verified_source_commit'])
        self.assertEqual(result['accuracy_offline']['full_test_on_mcu'],'NOT_RUN')
        self.assertEqual(result['runtime_stack'],'NOT_MEASURED')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--preparation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    Tests.session,Tests.preparation = a.session.resolve(),a.preparation.resolve()
    prepared = read(a.preparation)
    dfu = next(read(p) for p in (a.session/'dfu').glob('dfu-*.json') if read(p).get('exit_code') == 0)
    Tests.arguments = [prepared,sha(a.preparation),dfu,read(a.session/'week5_capture.receipt.json'),
        sha(a.session/'week5_capture.txt'),read(a.session/'collect.command.json'),read(a.session/'ports-before.json'),read(a.session/'ports-after-dfu.json')]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    write_json(a.output,{'status':'PASS' if result.wasSuccessful() else 'FAIL','scope':'OFFLINE_TESTS_USING_REAL_EVIDENCE',
        'tests_run':result.testsRun,'tool_sha256':sha(__file__),'acceptance_tool_sha256':sha(Path(__file__).with_name('accept_week5_mcu.py'))})
    raise SystemExit(0 if result.wasSuccessful() else 1)
