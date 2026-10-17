"""External-mode Gym fidelity, using physical behavior and the native observer."""
from dataclasses import replace
import importlib.util
import math
import warnings

import numpy as np
import pytest

pytest.importorskip('mujoco')
pytest.importorskip('gymnasium')
from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.sim.config import SimulationConfig


def api():
    assert importlib.util.find_spec('cartpole_sdk.sim.rig_gym_env'), 'governed rig Gym adapter missing'
    from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv, RigObservationConfig
    return RigCartpoleEnv, RigObservationConfig


def make(**kwargs):
    Env, _ = api()
    p = kwargs.pop('parameters', ControllerParameters(rail=.308962494, bw=6.))
    config = kwargs.pop('config', SimulationConfig(rail_half_m=p.rail, control_steps=10, max_steps=100))
    return Env(config, parameters=p, **kwargs)


def test_raw_action_runs_exactly_one_governor_and_100hz_decisions():
    env = make()
    env.reset(seed=1)
    observation, _, ended, truncated, _ = env.step([25.])
    assert not ended and not truncated
    assert env.ground_truth.time_ns == 10_000_000
    assert observation['state'][1] == pytest.approx(.00825, abs=1e-7)
    assert observation['state'][5] == pytest.approx(1.5, abs=1e-6)
    assert env.diagnostics.raw_acceleration_m_s2 == 25.
    assert env.session == env.backend.session


def test_observed_rate_starts_at_zero_and_tracks_native_encoder_observer():
    from oracle_support import NativeOracle
    from cartpole_sdk.sim.backend import MujocoBackend
    from cartpole_sdk.contracts import ActionRequest
    env = make()
    plant = MujocoBackend(replace(env.config, control_steps=1))
    plant.reset(seed=3, state=(0., 0., .2, 2.))
    obs, _ = env.reset(seed=3, options={'state': (0., 0., .2, 2.)})
    assert obs['state'][4] == 0.  # Physical velocity cannot initialize the estimator.
    assert env.ground_truth.omega == 2.
    angle = math.atan2(obs['state'][2], obs['state'][3])
    rate = 0.
    with NativeOracle() as native:
        for _ in range(4):
            env.step([0.])
            for _ in range(10):
                o = plant.observation
                plant.step(ActionRequest(o.session_id, o.clock_id, o.sequence, o.sequence,
                                         o.available_ns, o.available_ns+1_000_000, 0.))
                sample = round(plant.ground_truth.theta/(2*math.pi/4096))*(2*math.pi/4096)
                result = native.probe('estimate', sample, angle, rate, 6., .001)
                angle, rate = result['angle_hat'], result['rate_hat']
            samples = {s.quantity: s for s in env.sdk_observation.samples}
            assert samples['angular_velocity'].value == pytest.approx(rate, abs=5e-5)
            assert abs(env.ground_truth.omega - rate) > .1


def test_filtered_angle_selection_and_quantization_are_explicit():
    _, Obs = api()
    raw = make()
    filtered = make(observation_config=Obs(angle_source='filtered'))
    for env in (raw, filtered):
        env.reset(seed=1, options={'state': (0., 0., .2, 2.)})
    a = raw.step([0.])[0]['state']
    b = filtered.step([0.])[0]['state']
    assert a[4] == pytest.approx(b[4])
    assert a[2] != pytest.approx(b[2])
    angle = math.atan2(a[2], a[3])
    assert angle / (2*math.pi/4096) == pytest.approx(round(angle/(2*math.pi/4096)), abs=1e-9)


def test_delayed_snapshot_keeps_all_channels_same_age():
    _, Obs = api()
    env = make(observation_config=Obs(telemetry_delay_steps=3))
    obs, _ = env.reset(seed=1)
    assert obs['valid'].all()
    assert env.ground_truth.time_ns == 3_000_000
    # First decision is paced by first snapshot delivery, as on the rig.
    obs, *_ = env.step(None)
    assert obs['valid'].all()
    assert np.all(obs['age_s'] == 0.)  # SDK board snapshot proxies hide transport age.
    assert obs['state'][1] == 0.
    assert obs['state'][5] == 0.
    assert {s.effective_ns for s in env.sdk_observation.samples} == {10_000_000}
    assert env.sdk_observation.available_ns == 10_000_000


def test_command_delay_holds_old_lease_and_does_not_apply_action_early():
    _, Obs = api()
    env = make(observation_config=Obs(command_delay_steps=3))
    env.reset(seed=1)
    obs, *_ = env.step([25.])
    assert obs['state'][5] == pytest.approx(1.05, abs=1e-6)
    assert env.diagnostics.expires_at_ns == 20_000_000
    env.step(None)
    _, _, ended, _, info = env.step(None)
    assert ended and env.ground_truth.time_ns == 20_000_000
    assert info['fault_reason'] == 'action lease expired'


def test_limits_use_live_profile_and_invalid_actions_are_atomic():
    env = make(parameters=ControllerParameters(rail=.31, jmax=300., bw=6.))
    env.reset(seed=1)
    for action in ([26.], [True], [float('nan')], [0., 1.], ['1']):
        with pytest.raises(ValueError): env.step(action)
        assert env.ground_truth.time_ns == 0
    assert env.step([25.])[0]['state'][5] == pytest.approx(3., abs=2e-6)
    env.reset(seed=1, options={'state': (.301, 0., math.pi, 0.)})
    _, _, ended, _, info = env.step([0.])
    assert ended and info['fault_reason'] == 'rail exceeded'
    Env, _ = api()
    with pytest.raises(ValueError): Env(SimulationConfig(), parameters=env.parameters)


def test_seed_repeatability_gym_api():
    from gymnasium.utils.env_checker import check_env
    env = make(config=SimulationConfig(rail_half_m=.308962494, control_steps=10, max_steps=2))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        check_env(env, skip_render_check=True)
    obs, _ = env.reset(seed=4)
    assert env.observation_space.contains(obs)
    env.step([0.])
    assert env.step([0.])[3]
    with pytest.raises(RuntimeError): env.step([0.])
    env.close()


def test_force_cap_cannot_train_on_unsupported_physical_command_divergence():
    env = make(config=SimulationConfig(rail_half_m=.308962494, control_steps=10, max_force_n=.001))
    env.reset(seed=2)
    _, _, ended, _, info = env.step([25.])
    assert ended and env.ground_truth.time_ns == 1_000_000
    assert info['diagnostics']['force_saturated']
    assert info['fault_reason'] == 'force saturation: tracking model unsupported'
    with pytest.raises(RuntimeError): env.step([0.])


def test_command_arriving_after_anchored_ttl_is_not_renewed():
    _, Obs = api()
    env = make(observation_config=Obs(command_delay_steps=11), ttl_ms=10)
    env.reset(seed=2)
    env.step([25.])
    _, _, ended, _, info = env.step(None)
    assert ended and env.ground_truth.time_ns == 11_000_000
    assert info['fault_reason'] == 'stale action at executor arrival'
    assert env.ground_truth.v == pytest.approx(0., abs=1e-15)


def test_encoder_noise_is_seeded_before_rate_estimation():
    _, Obs = api()
    env = make(observation_config=Obs(angle_noise_std=.003))
    first, _ = env.reset(seed=41)
    then = env.step([0.])[0]
    again, _ = env.reset(seed=41)
    repeated = env.step([0.])[0]
    for key in first:
        np.testing.assert_array_equal(first[key], again[key])
        np.testing.assert_array_equal(then[key], repeated[key])
    assert abs(then['state'][4]) > 0.


def test_lower_speed_limit_governs_raw_acceleration_without_velocity_clipping():
    env = make(parameters=ControllerParameters(rail=.31, vmax=.1, vmax_s=.1, vmax_b=.1, bw=6.))
    env.reset(seed=3)
    accelerations = [0.]
    velocities = []
    for _ in range(20):
        observation, _, ended, _, _ = env.step([25.])
        assert not ended
        accelerations.append(observation['state'][5])
        velocities.append(observation['state'][1])
    assert max(velocities) <= .102
    assert velocities[-1] == pytest.approx(.1, abs=.002)
    assert max(abs(a-b) for a, b in zip(accelerations, accelerations[1:])) <= 1.50001


def test_shared_codec_accepts_actual_sdk_channels_with_identical_policy_input():
    assert importlib.util.find_spec('cartpole_sdk.policies.rig_observation'), 'shared SDK observation codec missing'
    from cartpole_sdk.policies.rig_observation import encode_rig_observation, rig_channels
    env = make()
    obs, _ = env.reset(seed=5, options={'state': (.01, 0., .2, 2.)})
    wire = env.sdk_observation
    # Actual SDK exposes these six channels in control_observation().
    selected = rig_channels(angle_source='raw')
    samples = tuple(replace(s, source=c.source, frame_id=c.frame_id)
                    for s, c in zip(wire.samples, selected))
    actual_sdk = replace(wire, samples=samples)
    encoded = encode_rig_observation(actual_sdk, selected)
    for key in obs: np.testing.assert_array_equal(encoded[key], obs[key])
    filtered = replace(samples[2], source='magnetic_filtered', value=.7)
    both = replace(actual_sdk, samples=actual_sdk.samples+(filtered,))
    chosen = encode_rig_observation(both, rig_channels(angle_source='filtered'))
    assert chosen['state'][2] == pytest.approx(math.sin(.7))


def test_shared_codec_preserves_unknown_and_age_without_true_state_fallback():
    assert importlib.util.find_spec('cartpole_sdk.policies.rig_observation'), 'shared SDK observation codec missing'
    from cartpole_sdk.policies.rig_observation import encode_rig_observation, simulation_channels
    env = make()
    env.reset(seed=5)
    sample = env.sdk_observation.samples[3]
    missing = replace(sample, validity='unknown', reason='missing', value=None,
                      acquired_ns=None, effective_ns=None, received_ns=None)
    packet = replace(env.sdk_observation, available_ns=7_000_000,
                     samples=env.sdk_observation.samples[:3]+(missing,)+env.sdk_observation.samples[4:])
    encoded = encode_rig_observation(packet, simulation_channels())
    assert encoded['state'][4] == 0. and encoded['valid'][4] == 0 and encoded['age_s'][4] == -1.
    assert encoded['age_s'][0] == .007


def test_delayed_telemetry_and_commands_keep_hardware_decision_phase():
    _, Obs = api()
    env = make(observation_config=Obs(telemetry_delay_steps=3, command_delay_steps=3))
    env.reset(seed=5)
    for _ in range(10):
        observation, _, ended, _, info = env.step([0.])
        assert not ended
        assert info['telemetry_transport_age_ns'] == 3_000_000
        assert not observation['age_s'].any()
    assert env.ground_truth.time_ns == 103_000_000


def test_numeric_gym_action_on_missing_telemetry_sends_nothing_and_expires():
    _, Obs = api()
    env = make(observation_config=Obs(dropout_probability=1.))
    first, _ = env.reset(seed=5)
    assert first['valid'].all()  # Initial stopped healthy preflight snapshot.
    missing, *_ = env.step([25.])
    assert not missing['valid'].any()
    _, _, ended, _, info = env.step([25.])
    assert not ended
    assert info['action_ignored_reason'] == 'unusable telemetry'
    _, _, ended, _, info = env.step([25.])
    assert ended and info['fault_reason'] == 'action lease expired'


def test_declared_action_space_endpoint_stays_inside_exact_sdk_limit():
    env = make(config=SimulationConfig(rail_half_m=.308962494, control_steps=10,
                                      max_acceleration_m_s2=.3))
    env.reset(seed=2)
    _, _, ended, _, _ = env.step(env.action_space.high)
    assert not ended and env.ground_truth.time_ns == 10_000_000
    assert env.diagnostics.raw_acceleration_m_s2 <= .3


@pytest.mark.parametrize('mode', ['vision', 'fused'])
def test_camera_modes_warm_causally_and_use_shared_sdk_pipeline(mode):
    from cartpole_sdk.policies.rig_observation import encode_rig_observation, select_rig_observation
    _, Obs = api()
    env = make(observation_config=Obs(angle_source=mode, angle_frame_id='upright',
        vision_frame_period_ns=30_000_000, vision_latency_ns=12_000_000,
        vision_angle_quantum_rad=.01))
    obs, info = env.reset(seed=5, options={'state': (0., 0., .2, 2.)})
    assert info['reset_warmup_ns'] >= (100_000_000 if mode == 'vision' else 20_000_000)
    selected = select_rig_observation(env.sdk_observation, env.channels, contract=env.observation_contract)
    assert all(s.validity == 'valid' for s in selected)
    for key, values in encode_rig_observation(env.sdk_observation, env.channels).items():
        np.testing.assert_array_equal(values, obs[key])
    if mode == 'vision':
        assert selected[3].effective_ns < selected[2].effective_ns < env.sdk_observation.available_ns
        assert abs(selected[3].value-env.ground_truth.omega) > .01
    else:
        assert env._camera_observer.fusion.accepted_vision >= 1
    for _ in range(5):
        _, _, terminated, _, _ = env.step([0.])
        assert not terminated


def test_camera_dropout_never_exposes_encoder_angle_and_expires_action_lease():
    _, Obs = api()
    env = make(observation_config=Obs(angle_source='vision', angle_frame_id='upright'))
    first, _ = env.reset(seed=2)
    assert first['valid'].all()
    # Loss starts after real pre-arm acquisition; later invalid frames cannot
    # select the still healthy magnetic angle or ground-truth angular velocity.
    env.observation_config = replace(env.observation_config, vision_dropout_probability=1.)
    for _ in range(20):
        obs, _, ended, _, info = env.step([0.])
        if ended:
            break
    assert ended and info['fault_reason'] == 'action lease expired'
    assert not obs['valid'][2] and not obs['valid'][4]
    assert obs['state'][2] == 0. and obs['state'][4] == 0.


def test_camera_noise_and_asynchronous_capture_are_seeded():
    _, Obs = api()
    env = make(observation_config=Obs(angle_source='vision', angle_frame_id='upright',
        vision_frame_period_ns=16_666_667, vision_latency_ns=7_000_000,
        vision_angle_noise_std=.003, vision_dropout_probability=.05))
    first, _ = env.reset(seed=52)
    after = env.step([0.])[0]
    repeated, _ = env.reset(seed=52)
    again = env.step([0.])[0]
    for key in first:
        np.testing.assert_array_equal(first[key], repeated[key])
        np.testing.assert_array_equal(after[key], again[key])
