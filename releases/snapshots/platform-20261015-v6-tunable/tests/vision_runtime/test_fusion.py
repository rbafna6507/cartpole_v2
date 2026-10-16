import math
import unittest
from cartpole_vision.fusion import AngleFusion, ClockMapper

class FusionTests(unittest.TestCase):
    def test_clock_tracks_board_time_despite_receipt_jitter_and_reboot(self):
        c=ClockMapper()
        times=[c.map(i*10,100+i*.01+j) for i,j in enumerate([.01,0,.04,0,.02])]
        self.assertAlmostEqual(times[-1],100.04,places=6)
        self.assertLess(times[-1],100.06)
        c.map(1000,101)
        self.assertAlmostEqual(c.map(0,102),102)
    def test_constant_motion_wrap_and_vision_bias_correction(self):
        f=AngleFusion()
        for i in range(300):
            t=i*.01; angle=2.8+t*.8
            f.observe('encoder',t,math.atan2(math.sin(angle+.06),math.cos(angle+.06)))
            if i%2==0:f.observe('vision',t,math.atan2(math.sin(angle),math.cos(angle)),variance=.0001)
        s=f.snapshot(2.99)
        self.assertLess(abs(s['theta']-(2.8+2.99*.8)),.025)
        self.assertAlmostEqual(s['bias'],.06,delta=.02)
        self.assertAlmostEqual(s['omega'],.8,delta=.1)
        self.assertEqual(s['source'],'both')
    def test_delayed_vision_replays_at_measurement_time(self):
        a,b=AngleFusion(),AngleFusion()
        for i in range(200):
            t=i*.01; theta=.6*math.sin(2*t)
            a.observe('encoder',t,theta+.04)
            a.observe('vision',t,theta,variance=.0001)
            b.observe('encoder',t,theta+.04)
            if i>=5:
                old=t-.05
                b.observe('vision',old,.6*math.sin(2*old),variance=.0001)
        for i in range(195,200):
            t=i*.01;b.observe('vision',t,.6*math.sin(2*t),variance=.0001)
        self.assertAlmostEqual(a.snapshot(1.99)['theta'],b.snapshot(1.99)['theta'],places=5)
    def test_outlier_does_not_drag_estimate_and_dropout_is_labelled(self):
        f=AngleFusion()
        for i in range(100):
            f.observe('encoder',i*.01,.1)
            f.observe('vision',i*.01,.1)
        f.observe('vision',1.,2.5)
        self.assertAlmostEqual(f.snapshot(1.)['theta'],.1,delta=.02)
        self.assertGreater(f.snapshot(1.)['rejected_vision'],0)
        for i in range(100,140):f.observe('encoder',i*.01,.1)
        self.assertEqual(f.snapshot(1.39)['source'],'encoder only')
        self.assertEqual(f.snapshot(1.55)['source'],'prediction')
        self.assertIsNone(f.snapshot(1.8)['theta'])
    def test_late_and_nonfinite_samples_cannot_corrupt_state(self):
        f=AngleFusion()
        f.observe('encoder',10,.2)
        self.assertFalse(f.observe('vision',8,.1))
        self.assertFalse(f.observe('encoder',10.1,float('nan')))
        self.assertAlmostEqual(f.snapshot(10)['theta'],.2)
    def test_reset_discards_old_reference(self):
        f=AngleFusion();f.observe('encoder',1,1.5)
        f.reset();f.observe('encoder',2,-.2)
        self.assertAlmostEqual(f.snapshot(2)['theta'],-.2)

if __name__=='__main__':unittest.main()
