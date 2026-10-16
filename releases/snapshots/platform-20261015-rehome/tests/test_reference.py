import math
import unittest
from dataclasses import replace
from cartpole_sdk.control import ReferenceController, ControllerParameters, load_tuned_parameters, gains
from cartpole_sdk.control.motion import State, advance, stopping_distance

class ReferenceTests(unittest.TestCase):
    def test_saved_gains_and_immutable_parameters(self):
        p = load_tuned_parameters()
        k = gains(p)
        self.assertAlmostEqual(k.k1, -20.83007, places=4)
        self.assertAlmostEqual(gains(p, upright=True).k1, -19.4853382, places=5)
        self.assertEqual(p.rail, .26)
        with self.assertRaises(AttributeError): p.pw = 6

    def test_governor_first_tick_and_rail_stop(self):
        s = advance(State(), 0, 1, 1.5, 25, 25, 150, .26, .001)
        self.assertAlmostEqual(s.acceleration, .15)
        self.assertAlmostEqual(s.velocity, .00015)
        self.assertGreater(stopping_distance(1, 0, 25, 150), .08)
        s = advance(State(), .246, 1, 1.5, 25, 25, 150, .26, .001)
        self.assertEqual(s.brake_direction, 1)

    def test_hanging_startup_kick_and_stop_does_not_reset_estimator(self):
        c = ReferenceController(); c.reset(math.pi)
        o = c.tick(math.pi, 0, now_us=0, command='auto')
        self.assertEqual(o.mode, 2); self.assertTrue(o.enabled)
        self.assertEqual(o.demand, 1)
        for name in ('theta','angle_hat','rate_hat','velocity','acceleration','demand','energy'): self.assertIs(type(getattr(o,name)),float)
        self.assertAlmostEqual(o.acceleration, .15)
        c.tick(math.pi-.01, 0, now_us=1000)
        rate = c.output.rate_hat
        o = c.tick(math.pi-.01, 0, now_us=2000, command='stop')
        self.assertEqual(o.mode, 0); self.assertFalse(o.enabled)
        self.assertNotEqual(o.rate_hat, 0); self.assertNotEqual(rate, 0)

    def test_capture_loss_and_upright_never_automatically_restarts(self):
        c = ReferenceController(); o = c.tick(0, 0, now_us=0, command='auto')
        self.assertEqual(o.mode, 3)
        for i in range(1, 40): o = c.tick(1, 0, now_us=i*1000)
        self.assertEqual(o.mode, 2)
        c.reset(); self.assertTrue(c.tick(0, 0, now_us=0, command='bal').upright_only)
        o = c.tick(1, .05, now_us=1000)
        self.assertEqual(o.mode, 11)
        self.assertEqual(c.tick(0, .05, now_us=2000, command='auto').mode, 11)
        for i in range(3, 300): o = c.tick(0, 0, now_us=i*1000)
        self.assertEqual(o.mode, 0); self.assertFalse(o.enabled)

    def test_health_threshold_and_host_timeout_are_firmware_thresholds(self):
        c = ReferenceController(); c.reset(math.pi)
        c.tick(math.pi, 0, now_us=0, command='auto')
        held_theta = c.output.theta
        for i in range(1, 5):
            o = c.tick(0, 0, now_us=i*1000, encoder_ok=False)
            self.assertEqual(o.mode, 2); self.assertEqual(o.theta, held_theta)
        self.assertEqual(c.tick(0, 0, now_us=5000, encoder_ok=False).mode, 4)
        c.reset(math.pi); c.tick(math.pi, 0, now_us=0, command='auto')
        self.assertEqual(c.tick(math.pi, 0, now_us=1500000, host_fresh=False).mode, 2)
        self.assertEqual(c.tick(math.pi, 0, now_us=1501000, host_fresh=False).mode, 4)

    def test_public_validation_is_atomic(self):
        c = ReferenceController(); c.tick(0, 0, now_us=0)
        for args in [dict(theta=math.nan,x=0,now_us=1000),dict(theta=0,x=math.inf,now_us=1000),dict(theta=0,x=1e300,now_us=1000),dict(theta=0,x=0,now_us=0),dict(theta=0,x=0,now_us=-1),dict(theta=0,x=0,now_us=1000,command='on'),dict(theta=0,x=0,now_us=1000,encoder_ok=1)]:
            with self.assertRaises((ValueError, TypeError)): c.tick(**args)
        self.assertEqual(c.tick(0,0,now_us=1000).mode,0)
        with self.assertRaises(ValueError): ControllerParameters(jmax=0)
        with self.assertRaises(ValueError): ControllerParameters(spin_resume_rad_s=151)

if __name__ == '__main__': unittest.main()
