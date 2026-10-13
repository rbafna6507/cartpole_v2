import math
import unittest
from pendulum_vision.state import Derivative, StateEstimator
from test_state import pose


class MotionTests(unittest.TestCase):
    def test_velocity_remains_available_at_30_40_and_80_fps(self):
        for fps in (30, 40, 80):
            d = Derivative(angular=True)
            for i in range(80):
                t = i/fps + (.001 if i % 2 else 0)
                v = d.observe(t, math.atan2(math.sin(3+2*t), math.cos(3+2*t)))
                if i >= 5:
                    self.assertIsNotNone(v, (fps, i))
                    self.assertAlmostEqual(v, 2, places=6)

    def test_exact_25fps_window_boundary_is_stable(self):
        d=Derivative()
        for i in range(2000):
            t=i/25
            v=d.observe(t,2*t)
            if i>=3:
                self.assertIsNotNone(v)
                self.assertAlmostEqual(v,2,places=6)

    def test_80fps_velocity_delay_is_at_most_30ms(self):
        d = Derivative()
        for i in range(20):
            t = i/80
            d.observe(t, t*t)
        self.assertLessEqual(t-d.effective_t, .030)

    def test_one_missing_frame_is_invalid_then_recovers_without_warmup(self):
        s = StateEstimator(); s.home_angle = 0; s.home_length = 180
        for i in range(12):
            s.update(pose(.5*i/80), i/80)
        lost = s.update(None, 12/80)
        self.assertFalse(lost['angle_valid'])
        self.assertIsNone(lost['omega_rad_s'])
        recovered = s.update(pose(.5*13/80), 13/80)
        self.assertIsNotNone(recovered['omega_rad_s'])
        self.assertAlmostEqual(recovered['omega_rad_s'], -.5, places=6)

    def test_long_loss_and_bad_geometry_restart_velocity(self):
        s = StateEstimator(); s.home_angle = 0; s.home_length = 180
        for i in range(12): s.update(pose(i/80), i/80)
        for i in range(12, 30): s.update(None, i/80)
        self.assertIsNone(s.update(pose(30/80), 30/80)['omega_rad_s'])
        for i in range(31, 45): s.update(pose(i/80), i/80)
        s.update(pose(45/80, length=80), 45/80)
        self.assertIsNone(s.update(pose(46/80), 46/80)['omega_rad_s'])


if __name__ == '__main__': unittest.main()
