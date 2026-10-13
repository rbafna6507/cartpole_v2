import unittest
from pendulum_vision import metrics


class MetricsTests(unittest.TestCase):
    def test_skips_invalid_geometry_and_velocity_warmup_are_separate(self):
        rows = [dict(t=i*.0125, seq=seq, detected=i!=2, calibrated=True,
                     angle_valid=i!=2, omega_rad_s=1 if i==3 else None,
                     processing_ms=5+i, host_read_to_result_ms=8+i)
                for i, seq in enumerate([10,11,13,14])]
        self.assertTrue(hasattr(metrics, 'summarize'))
        s=metrics.summarize(rows,80)
        self.assertEqual(s['skipped_camera_frames'],1)
        self.assertEqual(s['detected_frames'],3)
        self.assertEqual(s['velocity_frames'],1)
        self.assertAlmostEqual(s['geometry_coverage'],.6)
        self.assertAlmostEqual(s['angle_coverage_calibrated'],.6)
        self.assertAlmostEqual(s['velocity_coverage_calibrated'],.2)
        self.assertAlmostEqual(s['processed_fps'],80)
        self.assertAlmostEqual(s['processing_ms']['p50'],6.5)

    def test_uncalibrated_and_empty_are_not_velocity_failures(self):
        self.assertTrue(hasattr(metrics,'summarize'))
        self.assertIsNone(metrics.summarize([],80)['velocity_coverage_calibrated'])
        row=dict(t=0,seq=1,detected=True,calibrated=False,angle_valid=False,omega_rad_s=None)
        self.assertIsNone(metrics.summarize([row],80)['velocity_coverage_calibrated'])

    def test_stale_recent_rates_are_zero_and_history_is_bounded(self):
        self.assertTrue(hasattr(metrics,'MeasurementMetrics'))
        m=metrics.MeasurementMetrics(80)
        for i in range(1000):
            m.observe(dict(t=i/80,seq=i,detected=True,calibrated=True,angle_valid=True,omega_rad_s=1))
        r=m.report(1000/80)
        self.assertAlmostEqual(r['recent']['velocity_fps'],80)
        self.assertLessEqual(len(m.rows),800)
        self.assertEqual(m.report(15)['recent']['velocity_fps'],0)
        self.assertEqual(r['totals']['processed_frames'],1000)


if __name__ == '__main__': unittest.main()
