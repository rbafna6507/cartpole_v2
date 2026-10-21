"""Sensor distortion is upstream of filtering, never a physical plant change."""
from dataclasses import asdict, replace
import math
import numpy as np
import pytest

from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.sim.config import SimulationConfig
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv, RigObservationConfig
from cartpole_sdk.learning.model_experiment import complete_config
from cartpole_sdk.learning.training_recipe import default_randomization, sample_configs, validate_randomization

ERROR_KEYS = ("encoder_bias_rad", "encoder_sin_error_rad", "encoder_cos_error_rad")


def env_for(observation):
    return RigCartpoleEnv(SimulationConfig(control_steps=10, rail_half_m=.309075, max_steps=100),
        parameters=ControllerParameters(rail=.309075, bw=10.), observation_config=observation)


@pytest.mark.parametrize("angle,error", [(0., .01), (math.pi/2, .03), (-math.pi/2, -.05), (math.pi, -.03)])
def test_cardinal_sensor_error_has_upright_anchor_and_expected_shape(angle, error):
    env = env_for(RigObservationConfig(encoder_bias_rad=.01, encoder_sin_error_rad=.04,
                                      encoder_cos_error_rad=.02))
    try:
        obs, _ = env.reset(seed=1, options={"state": (0., 0., angle, 0.)})
        actual = math.atan2(obs['state'][2], obs['state'][3])
        residual = math.atan2(math.sin(actual-angle), math.cos(actual-angle))
        assert residual == pytest.approx(error, abs=math.pi/4096)
        assert env.ground_truth.theta == pytest.approx(angle)
    finally:
        env.close()


@pytest.mark.parametrize("source,bw", [('raw', 8.), ('filtered', 10.)])
def test_distorted_samples_drive_native_rate_estimator_without_changing_motion(source, bw):
    from oracle_support import NativeOracle
    from cartpole_sdk.contracts import ActionRequest
    from cartpole_sdk.sim.backend import MujocoBackend
    cfg = RigObservationConfig(angle_source=source, encoder_sin_error_rad=.07, encoder_cos_error_rad=.08)
    env = env_for(cfg)
    env.parameters = replace(env.parameters, bw=bw)
    clean = env_for(replace(cfg, encoder_sin_error_rad=0., encoder_cos_error_rad=0.))
    clean.parameters = replace(clean.parameters, bw=bw)
    plant = MujocoBackend(replace(env.config, control_steps=1))
    state = (0., 0., 1., 2.)
    quantum = 2*math.pi/4096
    try:
        obs, _ = env.reset(seed=3, options={'state': state})
        clean.reset(seed=3, options={'state': state})
        plant.reset(seed=3, state=state)
        angle, rate = math.atan2(obs['state'][2], obs['state'][3]), 0.
        with NativeOracle() as native:
            for _ in range(8):
                distorted = env.step([0.])[0]
                neutral = clean.step([0.])[0]
                for _ in range(10):
                    o = plant.observation
                    plant.step(ActionRequest(o.session_id, o.clock_id, o.sequence, o.sequence,
                        o.available_ns, o.available_ns+1_000_000, 0.))
                    theta = plant.ground_truth.theta
                    raw = round((theta+.07*math.sin(theta)+.08*(math.cos(theta)-1))/quantum)*quantum
                    result = native.probe('estimate', raw, angle, rate, bw, .001)
                    angle, rate = result['angle_hat'], result['rate_hat']
                assert distorted['state'][4] == pytest.approx(rate, abs=5e-5)
                if source == 'filtered':
                    assert math.atan2(distorted['state'][2], distorted['state'][3]) == pytest.approx(angle, abs=5e-6)
                assert env.ground_truth == clean.ground_truth
            assert abs(distorted['state'][4]-neutral['state'][4]) > .01
    finally:
        env.close(); clean.close(); plant.close()


def test_legacy_full_sensor_config_loads_neutrally_but_partial_new_fields_fail():
    old = {k:v for k,v in asdict(RigObservationConfig()).items() if k not in ERROR_KEYS}
    restored = complete_config(old, RigObservationConfig, 'observation_config')
    assert all(getattr(restored, k) == 0. for k in ERROR_KEYS)
    old[ERROR_KEYS[0]] = .01
    with pytest.raises(ValueError, match='explicit fields'):
        complete_config(old, RigObservationConfig, 'observation_config')


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), True, .18, -.18])
def test_encoder_error_bounds_reject_undefined_or_extreme_mapping(bad):
    for key in ERROR_KEYS:
        with pytest.raises(ValueError):
            RigObservationConfig(**{key:bad})


def test_encoder_randomization_is_reproducible_and_keeps_old_plant_draws():
    recipe = default_randomization()
    changed = dict(recipe, encoder={key: [-.03, .03] for key in ERROR_KEYS})
    config, obs = SimulationConfig(control_steps=10), RigObservationConfig()
    legacy = sample_configs(config, obs, recipe, seed=73, episode=4)
    first = sample_configs(config, obs, changed, seed=73, episode=4)
    again = sample_configs(config, obs, changed, seed=73, episode=4)
    other = sample_configs(config, obs, changed, seed=73, episode=5)
    assert first == again and first != other
    assert first[0] == legacy[0]
    for key, value in asdict(legacy[1]).items():
        if key not in ERROR_KEYS:
            assert getattr(first[1], key) == value
    assert all(-.03 <= getattr(first[1], k) <= .03 for k in ERROR_KEYS)
    assert all(getattr(obs, k) == 0. for k in ERROR_KEYS)
    for bad in ({}, {ERROR_KEYS[0]: [-.01,.01]}, {key:[-.2,.2] for key in ERROR_KEYS}):
        with pytest.raises(ValueError):
            validate_randomization(dict(recipe, encoder=bad))


def test_camera_truth_stays_independent_of_magnetic_error():
    # Camera angle is generated from true pose; magnetic distortion must not be
    # applied a second time to camera or secretly replace its rate source.
    envs = [env_for(RigObservationConfig(angle_source='vision', angle_frame_id='sim:shared-angle',
        vision_warmup_steps=500, encoder_cos_error_rad=value)) for value in (0., .08)]
    try:
        pairs = [env.reset(seed=22, options={'state':(0.,0.,.1,.2)}) for env in envs]
        for _ in range(3):
            for key in pairs[0][0]:
                np.testing.assert_array_equal(pairs[0][0][key], pairs[1][0][key])
            assert envs[0].ground_truth == envs[1].ground_truth
            pairs = [env.step([0.]) for env in envs]
    finally:
        for env in envs: env.close()


def test_fused_angle_uses_camera_correction_but_rate_still_reflects_encoder_distortion():
    from cartpole_sdk.policies.rig_observation import select_rig_observation
    cfg = RigObservationConfig(angle_source='fused', angle_frame_id='sim:shared-angle',
        encoder_sin_error_rad=.07, encoder_cos_error_rad=.04)
    env = env_for(cfg)
    try:
        obs, _ = env.reset(seed=27, options={'state':(0.,0.,1.,2.)})
        for _ in range(8):
            obs, _, ended, _, _ = env.step([0.])
            assert not ended
        selected = select_rig_observation(env.sdk_observation, env.channels, contract=env.observation_contract)
        assert selected[3].value == pytest.approx(env._rate_hat)
        assert math.atan2(obs['state'][2], obs['state'][3]) != pytest.approx(env._raw_angle, abs=1e-5)
        assert all(s.validity == 'valid' for s in selected)
        # Disable future valid camera corrections. Fusion eventually expires;
        # it cannot fall back silently to the distorted magnetic angle.
        env.observation_config = replace(cfg, vision_dropout_probability=1.)
        for _ in range(25):
            obs, _, ended, _, _ = env.step([0.])
            if ended or not obs['valid'][2]:
                break
        assert not obs['valid'][2] or ended
    finally:
        env.close()
