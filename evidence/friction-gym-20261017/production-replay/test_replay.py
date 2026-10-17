"""Focused checks for the evidence replay, including off-grid timestamps."""
import importlib.util
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

SCRIPT = Path(__file__).with_name('replay.py')


def load_replay():
    spec = importlib.util.spec_from_file_location('production_replay', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_can_describe_its_inputs():
    result = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for option in ('--freeze', '--source', '--annotations', '--output'):
        assert option in result.stdout


def test_equivalent_rod_conversion_preserves_frozen_acceleration_coefficients():
    replay = load_replay()
    config, phase, inertia = replay.make_config([49.05, .2, 0., 1.5], max_steps=25)
    assert math.isclose(config.effective_length_m, .2)
    assert math.isclose(inertia, .0006825)
    assert math.isclose(config.hinge_damping, .0001365)
    assert math.isclose(config.hinge_coulomb_friction_nm, .00102375)
    assert config.hinge_friction_velocity_scale_rad_s == .05
    assert config.control_steps == 1
    assert config.physics_dt_ns == 1_000_000
    assert config.rail_half_m == .308962494
    assert config.max_force_n == 20.
    assert phase == 0.


def test_fractional_samples_interpolate_fixed_one_ms_production_steps():
    replay = load_replay()
    config, phase, _ = replay.make_config([49.05, .2, 0., 1.5], max_steps=25)
    times = np.array([13., 13.001, 13.0025, 13.004])
    actual = replay.replay_on_sample_times(config, phase, [0., .1], times)
    q, omega = 0., .1
    tick_angles = [q]
    for _ in range(4):
        alpha = 49.05 * math.sin(q) - .2 * omega - 1.5 * math.tanh(omega / .05)
        omega += .001 * alpha
        q += .001 * omega
        tick_angles.append(q)
    expected = [tick_angles[0], tick_angles[1], (tick_angles[2] + tick_angles[3]) / 2,
                tick_angles[4]]
    np.testing.assert_allclose(actual['predicted_raw_rad'], expected, rtol=0., atol=1e-13)
    assert actual['timing']['fractional_sample_count'] == 1
    assert actual['physics_steps'] == 4
    assert actual['force_saturation_count'] == 0
    assert actual['max_abs_cart_position_m'] < 1e-12


def test_replay_rejects_repeated_or_reversed_timestamps():
    replay = load_replay()
    config, phase, _ = replay.make_config([49.05, .2, 0., 1.5], max_steps=25)
    for times in ([0., 0.], [0., -.001]):
        try:
            replay.replay_on_sample_times(config, phase, [0., .1], np.array(times))
        except ValueError:
            pass
        else:
            raise AssertionError('nonincreasing timestamps accepted')
