import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from cartpole_deploy.identification import fit_decay, validate_decay, export_fit, inspect_capture
from cartpole_deploy.config import RigConfig


def decay_file(path, amplitude=.3, length=.119, damping=.7, duration=8):
    t = np.linspace(0, duration, int(duration*100)+1)
    solution = solve_ivp(lambda t, y: [y[1], -9.81/length * np.sin(y[0])-damping*y[1]],
                         (0, duration), [amplitude, 0], t_eval=t, rtol=1e-10, atol=1e-11)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['device_elapsed_s', 'theta_rad', 'flags', 'x_m', 'v_m_s'])
        writer.writeheader()
        for tt, angle in zip(t, solution.y[0]):
            writer.writerow(dict(device_elapsed_s=tt, theta_rad=(angle+math.pi+math.pi)%(2*math.pi)-math.pi,
                                 flags=1, x_m=0, v_m_s=0))


class IdentificationTests(unittest.TestCase):
    def test_long_holdout_keeps_initial_state_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d)/'train.csv', Path(d)/'long-validation.csv'
            decay_file(p)
            decay_file(q, amplitude=-.5, duration=40)
            fit = fit_decay(p, release_s=0, cart_clamped=True)
            validation = validate_decay(q, fit, release_s=0, cart_clamped=True)
            self.assertLess(validation['rmse_rad'], .001)

    def test_recovers_parameters_and_validates_different_release(self):
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d)/'train.csv', Path(d)/'validation.csv'
            decay_file(p)
            decay_file(q, amplitude=-.5)
            fit = fit_decay(p, release_s=0, cart_clamped=True)
            self.assertAlmostEqual(fit['effective_length_m'], .119, delta=.001)
            self.assertAlmostEqual(fit['damping_per_s'], .7, delta=.03)
            validation = validate_decay(q, fit, release_s=0, cart_clamped=True)
            self.assertLess(validation['rmse_rad'], .01)
            with self.assertRaises(ValueError):
                validate_decay(p, fit, release_s=0, cart_clamped=True)
            output = Path(d)/'new.json'
            export_fit(RigConfig(), fit, output, validation)
            self.assertAlmostEqual(RigConfig.load(output).effective_length_m, .119, delta=.001)
            with self.assertRaises(FileExistsError):
                export_fit(RigConfig(), fit, output, validation)

    def test_rejects_missing_release_or_unclamped_cart(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.csv'
            decay_file(p)
            with self.assertRaises(ValueError):
                fit_decay(p, release_s=None, cart_clamped=True)
            with self.assertRaises(ValueError):
                fit_decay(p, release_s=0, cart_clamped=False)

    def test_stationary_or_invalid_trace_is_not_calibration(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'still.csv'
            decay_file(p, amplitude=0)
            with self.assertRaises(ValueError):
                fit_decay(p, release_s=0, cart_clamped=True)
            p.write_text('device_elapsed_s,theta_rad,flags,x_m,v_m_s\n0,nan,0,0,0\n.1,0,0,0,0\n')
            with self.assertRaises(ValueError):
                fit_decay(p, release_s=0, cart_clamped=True)

    def test_quality_reports_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.csv'
            decay_file(p)
            quality = inspect_capture(p)
            self.assertEqual(quality['invalid_sensor_samples'], 0)
            self.assertAlmostEqual(quality['median_sample_interval_s'], .01)
