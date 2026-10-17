"""Training variation must preserve physics units, leases and reproducibility."""
import importlib
import json
import pytest

from cartpole_sdk.sim.config import SimulationConfig
from cartpole_sdk.sim.rig_gym_env import RigObservationConfig


def recipe_api():
    assert importlib.util.find_spec('cartpole_sdk.learning.training_recipe'), 'training recipe missing'
    return importlib.import_module('cartpole_sdk.learning.training_recipe')


def test_randomization_preserves_damping_and_friction_acceleration_units():
    recipe = recipe_api()
    settings = recipe.default_randomization()
    settings['plant'] = dict(effective_length_scale=[1.1, 1.1],
                            angular_damping_scale=[1.2, 1.2],
                            coulomb_friction_scale=[.8, .8])
    config = SimulationConfig(control_steps=10, hinge_damping=.002, hinge_coulomb_friction_nm=.003)
    plant, observed = recipe.sample_configs(config, RigObservationConfig(), settings, seed=42, episode=3)
    assert plant.effective_length_m == pytest.approx(.1364)
    assert plant.hinge_damping == pytest.approx(.002904)
    assert plant.hinge_coulomb_friction_nm == pytest.approx(.002904)
    for name in ('rail_half_m', 'max_acceleration_m_s2', 'max_force_n', 'max_action_ttl_ns'):
        assert getattr(plant, name) == getattr(config, name)
    assert observed.telemetry_delay_steps + observed.command_delay_steps <= 10


def test_episode_sampling_is_reproducible_and_does_not_mutate_nominal_model():
    recipe = recipe_api()
    config = SimulationConfig(control_steps=10)
    obs = RigObservationConfig()
    settings = recipe.default_randomization()
    first = recipe.sample_configs(config, obs, settings, seed=123, episode=0)
    repeated = recipe.sample_configs(config, obs, settings, seed=123, episode=0)
    serialized = recipe.sample_configs(config, obs, json.loads(json.dumps(settings, sort_keys=True)), seed=123, episode=0)
    later = recipe.sample_configs(config, obs, settings, seed=123, episode=1)
    assert first == repeated
    assert first == serialized
    assert first != later
    assert config.effective_length_m == .124 and obs.angle_noise_std == 0.
    assert recipe.sample_configs(config, obs, None, seed=123, episode=1) == (config, obs)


@pytest.mark.parametrize('mutation', ['lease', 'negative', 'unknown', 'nan'])
def test_randomization_rejects_unusable_or_unsupported_ranges(mutation):
    recipe = recipe_api()
    settings = recipe.default_randomization()
    if mutation == 'lease':
        settings['observation']['telemetry_delay_steps'] = [0, 9]
        settings['observation']['command_delay_steps'] = [0, 2]
    elif mutation == 'negative':
        settings['plant']['effective_length_scale'] = [-1., 1.]
    elif mutation == 'unknown':
        settings['plant']['max_force_n'] = [10., 30.]
    else:
        settings['observation']['angle_noise_std'] = [0., float('nan')]
    with pytest.raises(ValueError):
        recipe.validate_randomization(settings)


def test_camera_variation_is_explicit_reproducible_and_independent_of_executor_delay():
    recipe = recipe_api()
    settings = recipe.default_randomization(angle_source='vision')
    settings['camera'] = dict(vision_frame_period_ns=[12_500_000, 12_500_000],
        vision_latency_ns=[30_000_000, 30_000_000], vision_angle_noise_std=[.005, .005],
        vision_dropout_probability=[.02, .02])
    config = SimulationConfig(control_steps=10)
    obs = RigObservationConfig(angle_source='vision', angle_frame_id='sim:shared-angle')
    plant, sampled = recipe.sample_configs(config, obs, settings, seed=5, episode=2)
    assert sampled.vision_frame_period_ns == 12_500_000
    assert sampled.vision_latency_ns == 30_000_000
    assert sampled.vision_angle_noise_std == .005
    assert sampled.vision_dropout_probability == .02
    assert sampled.telemetry_delay_steps + sampled.command_delay_steps <= 10
    assert plant.max_action_ttl_ns == config.max_action_ttl_ns
    assert (plant, sampled) == recipe.sample_configs(config, obs,
        json.loads(json.dumps(settings, sort_keys=True)), seed=5, episode=2)
    assert 'camera' not in recipe.default_randomization()


@pytest.mark.parametrize('name,value', [('vision_frame_period_ns', [0, 25_000_000]),
    ('vision_latency_ns', [0., 30_000_000.]), ('vision_dropout_probability', [0., 1.1])])
def test_camera_randomization_rejects_unbounded_or_wrong_unit_values(name, value):
    recipe = recipe_api()
    settings = recipe.default_randomization(angle_source='fused')
    settings['camera'][name] = value
    with pytest.raises(ValueError):
        recipe.validate_randomization(settings)
