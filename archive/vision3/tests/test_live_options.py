import unittest
from pendulum_vision import live


class LiveOptionsTests(unittest.TestCase):
    def test_measurement_and_video_rates_can_be_selected_independently(self):
        self.assertTrue(hasattr(live,'arguments'))
        a=live.arguments(['--fps','80','--video-fps','60','--detector-width','640','--no-video'])
        self.assertEqual((a.fps,a.video_fps,a.detector_width),(80,60,640))
        self.assertTrue(a.no_video)

    def test_video_defaults_follow_capture_and_bad_values_fail_before_camera(self):
        self.assertTrue(hasattr(live,'arguments'))
        self.assertEqual(live.arguments(['--fps','10']).video_fps,10)
        for args in (['--video-fps','0'],['--detector-width','0'],['--opencv-threads','0']):
            with self.assertRaises(SystemExit):live.arguments(args)
