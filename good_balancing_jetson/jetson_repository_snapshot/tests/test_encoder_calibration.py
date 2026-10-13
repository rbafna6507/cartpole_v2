import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import calibrate_encoder as E

def sample(raw, **kwargs):
    return dict(dict(raw=raw,valid=1,enabled=0,status=32,zero_raw=0,agc=80,i2c_errors=0),**kwargs)

class FakeLink:
    def __init__(self,*args,**kwargs):
        self.lock=threading.Lock();self.encoder_sequence=0;self.encoder_samples=[]
        self.port_name='fake';self.commands=[];self.closed=False
    def send(self,command):
        self.commands.append(command)
        if command=='enc':
            self.encoder_sequence+=1
            self.encoder_samples.append(sample([4000,850,1940,3000][(self.encoder_sequence-1)%4]))
    def close(self):self.closed=True

class CalibrationTest(unittest.TestCase):
    def test_one_reading_and_wraparound_mean(self):
        self.assertAlmostEqual(E.summarize_pose(90,[sample(123)])['raw_mean'],123)
        self.assertAlmostEqual(E.summarize_pose(0,[sample(4095),sample(1)])['raw_mean']%4096,0)
    def test_movement_and_sensor_flags_are_saved(self):
        readings=[sample(20,valid=0,status=0),sample(600,status=24)]
        pose=E.summarize_pose(180,readings)
        self.assertEqual(pose['samples'],readings)
        self.assertGreater(pose['span_deg'],2)
    def test_unreadable_reply_retried(self):
        link=FakeLink()
        with patch.object(E,'wait_until',side_effect=[TimeoutError(),None]):
            pose=E.capture(link,90,1)
        self.assertEqual(link.commands,['enc','enc'])
        self.assertEqual(pose['raw_values'],[850])
    def test_missing_replies_report_failure_without_fabricating_value(self):
        link=FakeLink()
        with patch.object(E,'wait_until',side_effect=TimeoutError()):
            with self.assertRaisesRegex(TimeoutError,'5 requests'):E.capture(link,0,1)
        self.assertEqual(len(link.commands),5)
    def test_four_prompts_save_raw_mapping_without_angle_validation(self):
        link=FakeLink()
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'capture.json'
            with patch.object(sys,'argv',['calibrate_encoder.py','--output',str(output)]),patch.object(E,'Link',return_value=link),patch.object(E,'stop_and_wait'),patch.object(E,'wait_until'),patch('builtins.input',return_value=''):
                E.main()
            saved=json.loads(output.read_text())
            self.assertTrue(saved['complete'])
            self.assertEqual([p['reference_deg'] for p in saved['calibration']['points']],[0,90,180,270])
            for p,raw in zip(saved['calibration']['points'],[4000,850,1940,3000]):self.assertAlmostEqual(p['raw'],raw)
            self.assertTrue(link.closed)
    def test_partial_report_preserves_raw_data(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.json';pose=E.summarize_pose(0,[sample(4095)])
            E.save_report(p,[pose],'fake',230400)
            report=json.loads(p.read_text())
            self.assertFalse(report['complete'])
            self.assertEqual(report['poses'][0]['raw_values'],[4095])
            self.assertFalse(p.with_suffix('.json.tmp').exists())
if __name__=='__main__':unittest.main()
