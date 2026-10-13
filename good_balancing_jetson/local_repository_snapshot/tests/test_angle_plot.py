import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from angle_plot import angle_series


class CircularPlotTest(unittest.TestCase):
    def test_encoder_zero_rollover_both_directions(self):
        for source, expected in [([4094,4095,0,1],[4094,4095,4096,4097]),
                                 ([1,0,4095,4094],[1,0,-1,-2])]:
            _, actual=angle_series([0,.04,.08,.12],source,unwrap=True,period=4096)
            self.assertEqual(actual,expected)

    def test_wrapped_angle_seam_keeps_samples_but_breaks_line(self):
        x,y=angle_series([0,.04,.08],[3.12,-3.12,-3.1])
        self.assertTrue(math.isnan(x[1]) and math.isnan(y[1]))
        self.assertEqual([v for v in y if math.isfinite(v)],[3.12,-3.12,-3.1])
        _,continuous=angle_series([0,.04,.08],[3.12,-3.12,-3.1],unwrap=True)
        self.assertAlmostEqual(continuous[-1],2*math.pi-3.1)

    def test_true_zero_crossing_is_continuous(self):
        self.assertEqual(angle_series([0,.04,.08],[-.1,0,.1]),([0,.04,.08],[-.1,0,.1]))

    def test_gaps_resets_and_invalid_samples_do_not_infer_turns(self):
        x,y=angle_series([0,.04,1,1.04,1.08,0],[3.12,-3.12,-3.1,float('nan'),.2,.3],unwrap=True)
        self.assertAlmostEqual(y[1],2*math.pi-3.12)
        self.assertTrue(math.isnan(y[2]));self.assertEqual(y[3],-3.1)
        self.assertEqual(y[-1],.3);self.assertTrue(math.isnan(y[-2]))

    def test_shape_and_scale_checks(self):
        with self.assertRaises(ValueError):angle_series([0],[])
        with self.assertRaises(ValueError):angle_series([0],[0],period=0)


if __name__=='__main__':unittest.main()
