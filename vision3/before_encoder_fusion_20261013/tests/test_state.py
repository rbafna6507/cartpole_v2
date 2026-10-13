import math
import unittest
from pendulum_vision.detector import Pose
from pendulum_vision.state import StateEstimator, Derivative


def pose(a=0,p=(300,100),length=180):
    return Pose(p,(p[0]+length*math.sin(a),p[1]+length*math.cos(a)),a,length,.9,.3)

class StateTests(unittest.TestCase):
    def test_irregular_time_velocity_across_wrap(self):
        d=Derivative(angular=True)
        for t in [0,.011,.028,.044,.067,.088,.105]:
            v=d.observe(t,math.atan2(math.sin(3.1+2*t),math.cos(3.1+2*t)))
        self.assertAlmostEqual(v,2,places=6)
    def test_velocity_effective_time_is_exposed_for_acceleration(self):
        d=Derivative()
        for i in range(9):v=d.observe(i*.01,(i*.01)**2)
        self.assertAlmostEqual(v,2*d.effective_t,places=6)
        self.assertLess(d.effective_t,.08)

    def test_gap_duplicate_and_loss_reset_derivative(self):
        d=Derivative()
        for i in range(10):d.observe(i*.01,3*i*.01)
        self.assertIsNone(d.observe(.09,.27))
        self.assertIsNone(d.observe(1,3))
        d.clear()
        self.assertIsNone(d.observe(1.01,3.03))
    def test_home_requires_consecutive_stationary_samples(self):
        s=StateEstimator()
        for i in range(25):s.update(pose(.2*math.sin(i)),i*.02)
        with self.assertRaises(ValueError):s.home()
        s.update(None,.5)
        for i in range(25):s.update(pose(.05),.52+i*.02)
        s.home()
        result=s.update(pose(.05),1.04)
        self.assertTrue(result['angle_valid'])
        self.assertAlmostEqual(abs(result['theta_rad']),math.pi)
        self.assertIsNone(result['omega_rad_s'])
    def test_position_scale_and_velocity(self):
        s=StateEstimator()
        for i in range(25):s.update(pose(p=(100,100)),i*.02)
        s.mark_cart('a')
        for i in range(25):s.update(pose(p=(500,100)),1+i*.02)
        s.mark_cart('b',400)
        for i in range(12):r=s.update(pose(p=(280+i*2,100)),2+i*.02)
        self.assertTrue(r['cart_valid'])
        self.assertAlmostEqual(r['cart_x_m'],.002,places=6)
        self.assertAlmostEqual(r['cart_v_m_s'],.1,places=6)
    def test_missing_arm_independent_cart_still_valid(self):
        s=StateEstimator();s.cart_a=[100,100];s.cart_b=[500,100];s.cart_span_mm=400
        r=s.update(None,0,cart_pivot=(300,100))
        self.assertFalse(r['angle_valid']);self.assertTrue(r['cart_valid'])
        self.assertEqual(r['cart_x_m'],0)
    def test_length_outlier_and_stale_clear_values(self):
        s=StateEstimator();s.home_angle=0;s.home_length=180
        self.assertFalse(s.update(pose(length=90),0)['angle_valid'])
        s.update(pose(),.02)
        r=s.snapshot(.5)
        self.assertFalse(r['angle_valid']);self.assertIsNone(r['theta_rad'])
        self.assertIsNone(r['cart_x_m'])
    def test_rejected_geometry_cannot_calibrate_or_measure_cart(self):
        s=StateEstimator();s.home_angle=0;s.home_length=180
        s.cart_a=[100,100];s.cart_b=[500,100];s.cart_span_mm=400
        r=s.update(pose(length=90),0)
        self.assertFalse(r["cart_valid"])
        self.assertEqual(len(s.cart_samples),0)
        r=s.update(pose(length=90),.02,cart_pivot=(300,100))
        self.assertTrue(r["cart_valid"])

    def test_source_change_restarts_cart_velocity(self):
        s=StateEstimator();s.cart_a=[100,100];s.cart_b=[500,100];s.cart_span_mm=400
        for i in range(12):s.update(pose(p=(300+i,100)),i*.02)
        r=s.update(None,.24,cart_pivot=(312,100))
        self.assertIsNone(r["cart_v_m_s"])

    def test_nonfinite_times_rejected(self):
        with self.assertRaises(ValueError):StateEstimator().update(pose(),float('nan'))
    def test_wrong_cart_reference_is_rejected(self):
        s=StateEstimator()
        for i in range(25):s.update(pose(),i*.02)
        with self.assertRaises(ValueError):s.mark_cart('b',400)
        s.mark_cart('a')
        with self.assertRaises(ValueError):s.mark_cart('b',400)

if __name__=='__main__':unittest.main()
