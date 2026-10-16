import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import cv2
from cartpole_vision.capture import ArrivalStats, RawRecorder, BufferedRecorder

class CaptureTests(unittest.TestCase):
    def test_actual_rate_not_requested_rate(self):
        stats=ArrivalStats(target_fps=80)
        for i in range(161):stats.observe(i*.02)
        report=stats.report()
        self.assertAlmostEqual(report['delivered_fps'],50)
        self.assertFalse(report['target_rate_met'])
        fast=ArrivalStats(target_fps=80)
        for i in range(241):fast.observe(i/80)
        self.assertAlmostEqual(fast.report()['delivered_fps'],80)
        self.assertTrue(fast.report()['target_rate_met'])
    def test_stalls_show_up_in_tail_interval(self):
        stats=ArrivalStats(80)
        for t in [0,.0125,.025,.0375,.2]:stats.observe(t)
        self.assertGreater(stats.report()['arrival_interval_p95_ms'],100)
    def test_buffered_recorder_drains_on_close(self):
        with tempfile.TemporaryDirectory() as temp:
            rec=BufferedRecorder(Path(temp),80,capacity=64)
            for i in range(20):rec.write(np.full((48,64,3),i,np.uint8),i,i/80)
            rec.close()
            rows=(Path(temp)/'raw_times.jsonl').read_text().splitlines()
            self.assertEqual(len(rows),20)
            self.assertEqual(rec.dropped,0)
            self.assertIsNone(rec.error)

    def test_raw_recording_has_matching_timestamps(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rec=RawRecorder(root,80)
            for seq,t in [(1,12.0),(3,12.025),(4,12.04)]:
                rec.write(np.full((48,64,3),seq,np.uint8),seq,t)
            rec.close()
            rows=[json.loads(s) for s in (root/'raw_times.jsonl').read_text().splitlines()]
            self.assertEqual([r['seq'] for r in rows],[1,3,4])
            self.assertEqual([r['t'] for r in rows],[12,12.025,12.04])
            cap=cv2.VideoCapture(str(root/'raw.avi'))
            self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),3);cap.release()
if __name__=='__main__':unittest.main()
