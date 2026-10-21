"""Retention changes only actor weights and survives a deterministic resume."""
import copy
import importlib.util
import random

import numpy as np
import pytest

pytest.importorskip('stable_baselines3')
import gymnasium as gym
from gymnasium import spaces
import torch
from stable_baselines3.common.logger import configure
from stable_baselines3.common.utils import set_random_seed

from cartpole_sdk.learning.projected_ppo import EquilibriumPPO, equilibrium_observation


class ObservedEnv(gym.Env):
    """Tiny deterministic observed-channel environment for optimizer tests."""
    observation_space = spaces.Dict({
        key: spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float32)
        for key in ('state', 'valid', 'age_s')
    })
    action_space = spaces.Box(-1., 1., shape=(1,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.steps = 0
        return self.observation(), {}

    def observation(self):
        obs = {k: v.astype(np.float32) for k, v in equilibrium_observation().items()}
        obs['state'][0] = .1 + .01 * self.steps
        obs['state'][2] = .2
        return obs

    def step(self, action):
        self.steps += 1
        return self.observation(), -float((action[0] - .2) ** 2), self.steps == 8, False, {}


def retained_class():
    assert importlib.util.find_spec('cartpole_sdk.learning.retained_ppo'), 'actor retention module is missing'
    from cartpole_sdk.learning.retained_ppo import RetainedPPO
    return RetainedPPO


def make_model(cls=None):
    model = (cls or retained_class())(
        'MultiInputPolicy', ObservedEnv(), seed=13, device='cpu', n_steps=8,
        batch_size=4, n_epochs=1, learning_rate=1e-4,
        policy_kwargs=dict(net_arch=dict(pi=[8], vf=[8])),
    )
    model.set_logger(configure(folder=None, format_strings=[]))
    model.project_equilibrium()
    return model


def anchors(count=64):
    rng = np.random.default_rng(170)
    return dict(state=rng.normal(size=(count, 7)).astype(np.float32),
                valid=np.ones((count, 7), dtype=np.float32),
                age_s=np.zeros((count, 7), dtype=np.float32))


def means(model, observations):
    tensors, _ = model.policy.obs_to_tensor(observations)
    with torch.no_grad():
        return model.policy.get_distribution(tensors).distribution.mean.cpu().numpy().copy()


def perturb_actor(model):
    with torch.no_grad():
        model.policy.action_net.weight.add_(.1)
    model.project_equilibrium()


def snapshot_rng():
    return random.getstate(), copy.deepcopy(np.random.get_state()), torch.get_rng_state().clone()


def assert_rng_equal(before, after):
    assert before[0] == after[0]
    assert before[1][0] == after[1][0]
    np.testing.assert_array_equal(before[1][1], after[1][1])
    assert before[1][2:] == after[1][2:]
    assert torch.equal(before[2], after[2])


def assert_policy_equal(first, second):
    for name, value in first.policy.state_dict().items():
        assert torch.equal(value, second.policy.state_dict()[name]), name


def test_retention_reduces_anchor_error_preserving_critic_std_and_ppo_optimizer():
    model = make_model()
    model.learn(8)
    obs = anchors()
    target = means(model, obs)
    record = model.configure_retention(obs, target, updates=30, batch_size=64, learning_rate=.003, seed=401)
    perturb_actor(model)
    before = {k: v.clone() for k, v in model.policy.state_dict().items()}
    ppo_optimizer_before = copy.deepcopy(model.policy.optimizer.state_dict())
    nonactor_grads = {name: parameter.grad.clone() for name, parameter in model.policy.named_parameters()
                      if parameter.grad is not None
                      and not name.startswith(('mlp_extractor.policy_net.', 'action_net.'))}
    model.policy.set_training_mode(True)
    metrics = model.retain_actor()
    assert model.policy.training
    assert record['samples'] == 64
    assert len(record['anchor_sha256']) == 64
    assert metrics['mse_final'] < metrics['mse_initial'] * .5
    assert metrics['rmse_final'] == pytest.approx(metrics['mse_final'] ** .5)
    assert metrics['update_loss_normalized'] >= 0.
    assert abs(model.predict(equilibrium_observation(), deterministic=True)[0][0]) < 1e-7
    changed = []
    for name, value in model.policy.state_dict().items():
        if not torch.equal(value, before[name]):
            changed.append(name)
            assert name.startswith(('mlp_extractor.policy_net.', 'action_net.')), name
    assert changed
    torch.testing.assert_close(model.policy.optimizer.state_dict(), ppo_optimizer_before, rtol=0, atol=0)
    for name, parameter in model.policy.named_parameters():
        if name in nonactor_grads:
            assert torch.equal(parameter.grad, nonactor_grads[name]), name
    assert model.logger.name_to_value['train/retention_mse_final'] == metrics['mse_final']


def test_retention_uses_frozen_copied_anchors_and_private_randomness():
    model = make_model()
    obs = anchors()
    target = means(model, obs)
    rng_before = snapshot_rng()
    record = model.configure_retention(obs, target, updates=3, batch_size=7, seed=402)
    assert_rng_equal(rng_before, snapshot_rng())
    perturb_actor(model)
    pinned_obs, pinned_target = copy.deepcopy(obs), target.copy()
    obs['state'][:] = 1234.
    target[:] = 999.
    before_error = np.mean((means(model, pinned_obs) - pinned_target) ** 2)
    rng_before = snapshot_rng()
    metrics = model.retain_actor()
    assert_rng_equal(rng_before, snapshot_rng())
    assert metrics['mse_initial'] == pytest.approx(before_error, rel=1e-6)
    assert model.retention_record() == record


def test_checkpoint_restores_targets_private_rng_and_adam_continuation(tmp_path):
    model = make_model()
    obs = anchors()
    model.configure_retention(obs, means(model, obs), updates=5, batch_size=11, learning_rate=.002, seed=403)
    perturb_actor(model)
    model.retain_actor()
    path = tmp_path / 'retained.zip'
    model.save(path)
    loaded = retained_class().load(path, device='cpu')
    loaded.set_logger(configure(folder=None, format_strings=[]))
    assert_policy_equal(model, loaded)
    assert loaded.retention_record() == model.retention_record()
    # Continuing the same next minibatches needs both Adam moments and RNG state.
    first = model.retain_actor()
    second = loaded.retain_actor()
    assert first == second
    assert_policy_equal(model, loaded)


@pytest.mark.parametrize('configured', [False, True])
def test_disabled_retention_exactly_matches_equilibrium_ppo(configured):
    baseline = make_model(EquilibriumPPO)
    retained = make_model()
    if configured:
        obs = anchors()
        retained.configure_retention(obs, means(retained, obs), updates=0)
    set_random_seed(51)
    baseline.learn(8)
    baseline_rng = snapshot_rng()
    set_random_seed(51)
    retained.learn(8)
    assert_policy_equal(baseline, retained)
    assert_rng_equal(baseline_rng, snapshot_rng())
    assert not any('retention_' in name for name in retained.logger.name_to_value)


def test_train_applies_retention_and_restores_equilibrium_without_touching_critic():
    baseline = make_model(EquilibriumPPO)
    retained = make_model()
    obs = anchors()
    target = means(retained, obs)
    retained.configure_retention(obs, target, updates=4, batch_size=16, learning_rate=.001)
    set_random_seed(52)
    baseline.learn(8)
    set_random_seed(52)
    retained.learn(8)
    actor_differs = False
    for name, value in baseline.policy.state_dict().items():
        if name.startswith(('mlp_extractor.policy_net.', 'action_net.')):
            actor_differs |= not torch.equal(value, retained.policy.state_dict()[name])
        else:
            assert torch.equal(value, retained.policy.state_dict()[name]), name
    assert actor_differs
    assert abs(retained.predict(equilibrium_observation(), deterministic=True)[0][0]) < 1e-7
    assert retained.retention_diagnostics['mse_final'] >= 0.


@pytest.mark.parametrize('problem', ['missing_key', 'extra_key', 'wrong_shape', 'row_count', 'empty',
                                    'target_shape', 'obs_nan', 'target_inf'])
def test_rejects_invalid_anchor_data_without_replacing_existing_configuration(problem):
    model = make_model()
    obs = anchors()
    targets = means(model, obs)
    record = model.configure_retention(obs, targets)
    if problem == 'missing_key':
        del obs['valid']
    elif problem == 'extra_key':
        obs['truth'] = np.ones((64, 7))
    elif problem == 'wrong_shape':
        obs['state'] = obs['state'][:, :6]
    elif problem == 'row_count':
        obs['valid'] = obs['valid'][:-1]
    elif problem == 'empty':
        obs = {k: v[:0] for k, v in obs.items()}
        targets = targets[:0]
    elif problem == 'target_shape':
        targets = targets[:, 0]
    elif problem == 'obs_nan':
        obs['state'][0, 0] = np.nan
    elif problem == 'target_inf':
        targets[0, 0] = np.inf
    with pytest.raises(ValueError):
        model.configure_retention(obs, targets)
    assert model.retention_record() == record


@pytest.mark.parametrize('kwargs', [dict(updates=-1), dict(updates=1.5), dict(batch_size=0),
                                   dict(learning_rate=0), dict(learning_rate=np.nan),
                                   dict(weight=-1), dict(weight=np.inf), dict(seed=-1)])
def test_rejects_invalid_retention_settings(kwargs):
    model = make_model()
    obs = anchors()
    with pytest.raises(ValueError):
        model.configure_retention(obs, means(model, obs), **kwargs)


@pytest.mark.parametrize('settings', [None, dict(updates=0), dict(weight=0.)])
def test_disabled_checkpoint_roundtrip_and_direct_step_are_exact_noops(tmp_path, settings):
    model = make_model()
    if settings is not None:
        obs = anchors()
        model.configure_retention(obs, means(model, obs), **settings)
    path = tmp_path / 'disabled.zip'
    model.save(path)
    loaded = retained_class().load(path, device='cpu')
    before_rng = snapshot_rng()
    assert loaded.retain_actor() == {}
    assert_rng_equal(before_rng, snapshot_rng())
    assert_policy_equal(model, loaded)
    assert loaded.retention_record() == model.retention_record()
