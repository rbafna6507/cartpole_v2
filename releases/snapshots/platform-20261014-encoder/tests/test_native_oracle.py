"""Required tests of the original firmware under native peripheral stubs."""
import json
import math
from pathlib import Path
import unittest

from oracle_support import NativeOracle

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / 'archive/good_balancing_jetson/settings.json').read_text())
PRESET = {k: v for k, v in SETTINGS['settings'].items() if k not in {'zvmax', 'zamax', 'ztravel'}}


class NativeOracleTests(unittest.TestCase):
    def setUp(self):
        self.oracle = NativeOracle().__enter__()
        self.addCleanup(self.oracle.close)
        self.oracle.set_parameters(PRESET)

    def test_compiles_original_sketch_and_starts_hanging_kick(self):
        self.oracle.reset(math.pi)
        out = self.oracle.tick(math.pi, 0, now_us=1000, command='auto')
        self.assertEqual(out['mode'], 2)
        self.assertTrue(out['enabled'])
        self.assertAlmostEqual(out['demand'], 1, places=5)
        self.assertAlmostEqual(out['acceleration'], .15, places=6)

    def test_native_saved_gains_match_archived_values(self):
        gains = self.oracle.probe('gains')
        for key, expected in SETTINGS['computed_gains'].items():
            self.assertAlmostEqual(gains[key], expected, delta=1e-5)

    def test_original_encoder_failure_hold_and_fifth_error_fault(self):
        self.oracle.reset(.1)
        self.oracle.tick(.1, 0, now_us=1000, command='manual')
        for i in range(1, 6):
            out = self.oracle.tick(.8, 0, now_us=(i+1)*1000, encoder_ok=False)
            self.assertAlmostEqual(out['theta'], .1, places=6)
            self.assertEqual(out['mode'], 4 if i == 5 else 1)
        self.assertFalse(out['enabled'])

    def test_host_timeout_is_strictly_after_1500_ms(self):
        self.oracle.reset()
        self.oracle.tick(0, 0, now_us=0, command='manual')
        self.assertEqual(self.oracle.tick(0, 0, now_us=1_500_000, host_fresh=False)['mode'], 1)
        out = self.oracle.tick(0, 0, now_us=1_501_000, host_fresh=False)
        self.assertEqual(out['mode'], 4)
        self.assertFalse(out['enabled'])

    def test_original_commands_balance_and_stop(self):
        self.oracle.reset()
        out = self.oracle.tick(0, 0, now_us=0, command='bal')
        self.assertEqual(out['mode'], 3)
        self.assertTrue(out['upright_only'])
        out = self.oracle.tick(0, 0, now_us=1000, command='stop')
        self.assertEqual(out['mode'], 0)
        self.assertFalse(out['enabled'])
        self.oracle.reset(math.pi)
        out = self.oracle.tick(math.pi, 0, now_us=0, command='bal')
        self.assertEqual(out['mode'], 0)

    def test_native_primitives_and_signed_rail_braking(self):
        out = self.oracle.probe('estimate', .1, 0, 0, 30, .001)
        self.assertAlmostEqual(out['angle_hat'], .0376991, places=6)
        self.assertAlmostEqual(out['rate_hat'], 3.55306, places=5)
        self.assertAlmostEqual(self.oracle.probe('stopping', 1, 0, 25, 150)['distance'], .0816497, places=6)
        for sign in [-1, 1]:
            out = self.oracle.probe('motion', sign*.3, 0, 0, sign*.24, sign*10, 1.5, 25, 25, 150, .26, .001)
            self.assertEqual(out['brake_direction'], sign)
            self.assertEqual(math.copysign(1, out['acceleration']), -sign)

    def test_encoder_bus_recovery_and_command_health(self):
        self.oracle.reset(.2)
        out = self.oracle.tick(.3, 0, now_us=0, encoder_ok=False, command='auto')
        self.assertEqual(out['mode'], 0)
        for i in range(1, 50):
            out = self.oracle.tick(.3, 0, now_us=i*1000, encoder_ok=False)
        self.assertEqual(out['encoder_recoveries'], 1)
        self.assertEqual(out['encoder_consecutive_errors'], 0)
        out = self.oracle.tick(.3, 0, now_us=50_000, command='auto')
        self.assertTrue(out['encoder_ok'])
        self.assertTrue(out['enabled'])
        self.assertAlmostEqual(out['theta'], .3, places=6)

    def test_original_rail_return_handoff_and_hard_limit(self):
        for sign in (-1, 1):
            self.oracle.reset(math.pi)
            out = self.oracle.tick(math.pi, sign*.246, now_us=0, command='manual')
            self.assertEqual(out['mode'], 6)
            self.assertEqual(math.copysign(1, out['demand']), -sign)
            out = self.oracle.tick(math.pi, sign*.239, now_us=1000)
            self.assertEqual(out['mode'], 1)
            out = self.oracle.tick(math.pi, sign*.251, now_us=2000)
            self.assertEqual(out['mode'], 4)
            self.assertFalse(out['enabled'])

    def test_capture_loss_spin_and_upright_stop(self):
        self.oracle.reset()
        self.assertEqual(self.oracle.tick(0, 0, now_us=0, command='auto')['mode'], 3)
        self.assertEqual(self.oracle.tick(3, 0, now_us=1000)['mode'], 2)
        self.assertEqual(self.oracle.tick(3, 0, now_us=2000)['mode'], 7)
        out = self.oracle.tick(3, 0, now_us=3000, command='manual')
        self.assertEqual(out['mode'], 9)  # recovery command cannot bypass latch
        self.oracle.reset()
        self.oracle.tick(0, 0, now_us=0, command='bal')
        out = self.oracle.tick(1, 0, now_us=1000)
        self.assertEqual(out['mode'], 0)  # fallen while already centered: stop
        self.assertFalse(out['enabled'])
        self.assertFalse(out['upright_only'])

    def test_host_timeout_across_millis_uint32_rollover(self):
        start = (2**32-100)*1000
        self.oracle.reset(now_us=start)
        self.oracle.tick(0, 0, now_us=start, command='manual')
        self.assertEqual(self.oracle.tick(0, 0, now_us=start+1_500_000, host_fresh=False)['mode'], 1)
        self.assertEqual(self.oracle.tick(0, 0, now_us=start+1_501_000, host_fresh=False)['mode'], 4)

    def test_reset_clears_motion_fault_and_estimator_history(self):
        self.oracle.reset(math.pi)
        for i in range(3):
            self.oracle.tick(math.pi, 0, now_us=i*1000, command='auto' if i == 0 else None)
        out = self.oracle.reset(.25, now_us=42)
        self.assertEqual(out['mode'], 0)
        self.assertEqual(out['energy'], -1)
        for key in ('velocity', 'acceleration', 'demand', 'brake_direction', 'rate_hat'):
            self.assertEqual(out[key], 0)
        self.assertAlmostEqual(out['angle_hat'], .25, places=6)
        self.assertFalse(out['enabled'])
        self.assertEqual(self.oracle.tick(.25, 0, now_us=42)['mode'], 0)
        with self.assertRaises(ValueError):
            self.oracle.tick(.25, 0, now_us=42)
        with self.assertRaises(ValueError):
            self.oracle.tick(.25, 0, now_us=41)

    def test_compile_failure_is_required_failure(self):
        with self.assertRaises(RuntimeError):
            NativeOracle(compiler='/nonexistent/cartpole-compiler').__enter__()


if __name__ == '__main__':
    unittest.main()
