import importlib.util
import time
import unittest
from .test_detector import scene
from cartpole_vision.app import Engine


class PreviewTests(unittest.TestCase):
    def test_preview_encodes_latest_bundle_outside_tracking_thread(self):
        self.assertIsNotNone(importlib.util.find_spec('cartpole_vision.preview'))
        from cartpole_vision.preview import PreviewWorker
        engine=Engine();frame=scene();engine.process(frame,time.monotonic(),1)
        worker=PreviewWorker(engine,40)
        try:
            deadline=time.monotonic()+2
            while engine.preview_seq!=1 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(engine.preview_seq,1)
            self.assertTrue(engine.jpg.startswith(b'\xff\xd8'))
            self.assertIsNone(engine.error)
        finally:worker.close()
        self.assertFalse(worker.thread.is_alive())
