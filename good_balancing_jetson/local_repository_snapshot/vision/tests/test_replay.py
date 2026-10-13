import json
from pathlib import Path
import tempfile
import unittest
import cv2
from test_detector import scene
from pendulum_vision.replay import replay

class ReplayTests(unittest.TestCase):
    def test_video_creates_finite_measurements_and_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);src=root/'input.avi'
            writer=cv2.VideoWriter(str(src),cv2.VideoWriter_fourcc(*'MJPG'),50,(800,600))
            self.assertTrue(writer.isOpened())
            for i in range(30):writer.write(scene(.01*i))
            writer.release()
            summary=replay(src,root/'result',home_angle=0)
            self.assertEqual(summary['frames'],30)
            self.assertGreater(summary['detected_frames'],27)
            rows=[json.loads(x) for x in (root/'result'/'states.jsonl').read_text().splitlines()]
            self.assertGreater(rows[-1]['t'],rows[0]['t'])
            self.assertAlmostEqual(rows[-1]['omega_rad_s'],-.5,delta=.1)
            self.assertNotIn('NaN',(root/'result'/'states.jsonl').read_text())
    def test_nonexistent_source_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):replay('/does-not-exist.avi',Path(temp)/'out')
if __name__=='__main__':unittest.main()
