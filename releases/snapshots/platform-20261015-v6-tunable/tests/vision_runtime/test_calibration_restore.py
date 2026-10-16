import json, tempfile, unittest
from pathlib import Path
from cartpole_vision.app import Engine
class CalibrationRestoreTests(unittest.TestCase):
    def test_restore_preserves_latest_saved_reference_and_rejects_wrong_geometry(self):
        e=Engine()
        self.assertTrue(hasattr(e,'restore_calibration'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'calibration.json'
            p.write_text(json.dumps(dict(frame_width=960,frame_height=600,rotation=180,calibration=dict(home_angle_rad=.03,home_length_px=185,cart_a_px=None,cart_b_px=None,cart_span_mm=None))))
            e.restore_calibration(p,960,600,180)
            self.assertEqual(e.estimator.home_angle,.03)
            with self.assertRaises(ValueError):e.restore_calibration(p,640,480,180)
            self.assertEqual(e.estimator.home_angle,.03)
            e.estimator.home_angle=.04;e.save_event('home')
            self.assertEqual(json.loads(p.read_text())['calibration']['home_angle_rad'],.04)
    def test_invalid_calibration_never_partially_applies(self):
        e=Engine()
        self.assertTrue(hasattr(e,'restore_calibration'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'calibration.json'
            p.write_text(json.dumps(dict(frame_width=960,frame_height=600,rotation=180,calibration=dict(home_angle_rad=.03,home_length_px=float('nan'),cart_a_px=None,cart_b_px=None,cart_span_mm=None))))
            with self.assertRaises(ValueError):e.restore_calibration(p,960,600,180)
            self.assertIsNone(e.estimator.home_angle)
