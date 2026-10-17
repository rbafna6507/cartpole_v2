import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'evidence/system-id-20261017/tools/diagnose_turning_point_initialization.py'


def tool():
    assert SCRIPT.exists(), 'turning-point diagnostic not implemented'
    spec = importlib.util.spec_from_file_location('turning_point_study', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_first_clear_extremum_is_local_and_quantization_tolerant():
    m = tool()
    t = np.arange(0, 2., .004)
    q = np.round((3. + .6 * np.cos(2 * np.pi * (t - .32))) / .001534) * .001534
    found = m.first_turning_point(t, q)
    assert found['vertex_t_s'] == pytest.approx(.32, abs=.004)
    assert found['initial_raw_angle_rad'] == pytest.approx(3.6, abs=.003)
    assert found['initial_omega_rad_s'] == 0.
    assert found['support_end_s'] - found['support_start_s'] <= .120000001
    assert found['support_end_s'] > found['vertex_t_s']
    assert found['vertex_t_s'] - t[0] < 1.2


def test_static_monotonic_late_or_gapped_data_do_not_supply_turn():
    m = tool()
    t = np.arange(0, 2., .004)
    for q in [np.ones(len(t)), 3. + t, 3. - (t - 1.5) ** 2]:
        with pytest.raises(ValueError, match='clear turning point'):
            m.first_turning_point(t, q)
    with pytest.raises(ValueError, match='ordered contiguous'):
        m.first_turning_point(np.r_[t[:50], t[75:]], np.cos(np.r_[t[:50], t[75:]]))


def test_scored_future_cannot_change_extremum_or_predictions():
    m = tool()
    fitter, _, _, _ = m.frozen_method(REPO)
    c = [60., .5, 6.]
    ep = synthetic(fitter, c)
    original = m.compare_episode(ep, c, fitter)
    support = original['turning_point']['support_end_s']
    changed = dict(ep, theta_rad=[q + (.17 if t > support else 0.) for t, q in zip(ep['t_s'], ep['theta_rad'])])
    again = m.compare_episode(changed, c, fitter)
    assert again['turning_point'] == original['turning_point']
    assert np.asarray(again['readings'])[:, 3] == pytest.approx(np.asarray(original['readings'])[:, 3])
    assert original['first_scored_t_s'] > support
    assert np.asarray(original['readings'])[:, 0].tolist() == np.asarray(again['readings'])[:, 0].tolist()
    assert original['parameters_refitted'] is False


def synthetic(fitter, coefficients):
    t = np.arange(0., 2.004, .004)
    q, w = math.pi + .8, -2.
    values = [q]
    for _ in t[1:]:
        for __ in range(4):
            q, w = fitter.advance(q, w, .001, coefficients)
        values.append(q)
    return dict(run_id='synthetic', episode_id='release', t_s=t.tolist(), theta_rad=values)


def test_turning_point_exposes_manufactured_initial_velocity_error():
    m = tool()
    fitter, _, _, _ = m.frozen_method(REPO)
    c = [60., .5, 6.]
    ep = synthetic(fitter, c)
    # Contaminate only the original initializer's past 40 ms; the endpoint angle
    # and later freely evolving signal remain the known same ODE trajectory.
    ep['theta_rad'] = [q - 3. * (t - .1) if .06 - 1e-9 <= t <= .1 + 1e-9 else q for t, q in zip(ep['t_s'], ep['theta_rad'])]
    result = m.compare_episode(ep, c, fitter)
    assert result['baseline']['rmse_rad'] > .1
    assert result['turn_initialized']['rmse_rad'] < .02
    assert result['baseline']['samples'] == result['turn_initialized']['samples'] == len(result['readings'])
