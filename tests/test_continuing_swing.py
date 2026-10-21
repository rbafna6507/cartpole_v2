"""Continuing horizon changes reward/ending semantics, never plant transitions."""
from dataclasses import asdict
import importlib.util
import json

import numpy as np
import pytest

pytest.importorskip('stable_baselines3')
pytest.importorskip('mujoco')

from cartpole_sdk.learning.robust_swing import RobustSwingEnv
from test_ppo_training import make_experiment
from test_robust_swing import fixed_randomization


def continuing_class():
    assert importlib.util.find_spec('cartpole_sdk.learning.continuing_swing'), 'continuing horizon ablation missing'
    from cartpole_sdk.learning.continuing_swing import ContinuingSwingEnv
    return ContinuingSwingEnv


def make_pair(experiment, *, randomized=False):
    kwargs = dict(randomized=randomized, bias_degrees=1. if randomized else 0.,
                  randomization_seed=77,
                  randomization=fixed_randomization() if randomized else None)
    return (RobustSwingEnv(experiment, (51,), **kwargs),
            continuing_class()(experiment, (51,), **kwargs))


def assert_observations_equal(first, second):
    assert set(first) == set(second) == {'state', 'valid', 'age_s'}
    for key in first:
        np.testing.assert_array_equal(first[key], second[key])


def assert_physics_equal(base, treatment):
    assert base.core.ground_truth == treatment.core.ground_truth
    assert base.core.sdk_observation == treatment.core.sdk_observation
    assert base.core.diagnostics == treatment.core.diagnostics
    assert base.core._commands == treatment.core._commands
    assert base.core._sequence == treatment.core._sequence
    assert base.episode_parameters == treatment.episode_parameters
    assert base.total_training_steps == treatment.total_training_steps


@pytest.mark.parametrize('start', ['hanging', 'upright'])
@pytest.mark.parametrize('randomized', [False, True])
def test_dense_rewards_observed_inputs_and_action_execution_match_through_horizon(tmp_path, start, randomized):
    experiment = make_experiment(tmp_path)
    base, treatment = make_pair(experiment, randomized=randomized)
    try:
        first, first_info = base.reset(seed=5, options=dict(episode_seed=51, start=start))
        second, second_info = treatment.reset(seed=5, options=dict(episode_seed=51, start=start))
        assert_observations_equal(first, second)
        assert first_info == second_info
        for index, action in enumerate((.02, -.03, .01, 0., .015)):
            first, old_reward, old_end, old_truncated, old_info = base.step([action])
            second, new_reward, new_end, new_truncated, new_info = treatment.step([action])
            assert_observations_equal(first, second)
            assert_physics_equal(base, treatment)
            assert base.core.diagnostics.raw_acceleration_m_s2 == pytest.approx(action * base.action_scale)
            if index < 4:
                assert (new_reward, new_end, new_truncated, new_info) == (old_reward, old_end, old_truncated, old_info)
            else:
                assert (old_end, old_truncated) == (True, False)
                assert (new_end, new_truncated) == (False, True)
                assert new_reward == pytest.approx(old_reward - base.dwell * 100 * base.reward_scale)
                assert new_info['episode_result'] == treatment.result()
                assert {k: v for k, v in new_info.items() if k != 'episode_result'} == {
                    k: v for k, v in old_info.items() if k != 'episode_result'}
    finally:
        base.close()
        treatment.close()


@pytest.mark.parametrize('steps', [5, 600])
def test_removes_only_terminal_bonus_and_updates_score_without_changing_hold_metrics(tmp_path, steps):
    experiment = make_experiment(tmp_path)
    experiment['simulation_config']['max_steps'] = steps
    base, treatment = make_pair(experiment)
    try:
        for env in (base, treatment):
            env.reset(seed=5, options=dict(episode_seed=51, start='upright'))
            # Exact unstable equilibrium, as used by the existing hold-metric test.
            env.core.reset(seed=1, options={'state': (0., 0., 0., 0.)})
        old_rewards, new_rewards = [], []
        for _ in range(steps):
            _, reward, _, _, old_info = base.step([0.])
            old_rewards.append(reward)
            _, reward, _, _, new_info = treatment.step([0.])
            new_rewards.append(reward)
        assert new_rewards == pytest.approx([.03] * steps)
        assert old_rewards[-1] == pytest.approx(.03 + steps * .01)
        assert treatment.total_reward == pytest.approx(3. * steps)
        assert base.total_reward - treatment.total_reward == pytest.approx(float(steps))
        assert sum(new_rewards) / treatment.reward_scale == pytest.approx(treatment.total_reward)
        assert new_info['episode_result']['score'] == pytest.approx(3.)
        assert old_info['episode_result']['score'] == pytest.approx(4.)
        assert {k: v for k, v in new_info['episode_result'].items() if k != 'score'} == {
            k: v for k, v in old_info['episode_result'].items() if k != 'score'}
        assert treatment.result()['final_balance_dwell_s'] == pytest.approx(steps / 100)
        assert treatment.result()['hold_success'] is (steps == 600)
        with pytest.raises(RuntimeError, match='reset'):
            treatment.step([0.])
        treatment.reset(seed=5)
        assert treatment.total_reward == 0.
        assert treatment.dwell == 0.
        assert treatment.step([0.])[2:4] == (False, False)
    finally:
        base.close()
        treatment.close()


@pytest.mark.parametrize('steps', [1, 5])
def test_real_force_saturation_fault_remains_terminal_even_at_horizon(tmp_path, steps):
    experiment = make_experiment(tmp_path)
    from cartpole_sdk.learning.model_experiment import build_experiment, digest
    model_path = tmp_path / 'model.json'
    model = json.loads(model_path.read_text())
    model['simulation_config']['max_force_n'] = .001
    model.pop('content_sha256')
    model['content_sha256'] = digest(model)
    model_path.write_text(json.dumps(model))
    experiment = build_experiment(model_path, executor_parameters=experiment['executor_parameters'],
        observation_config=experiment['observation_config'], prior_parameters=experiment['prior_parameters'],
        development_only=True)
    experiment['simulation_config']['max_steps'] = steps
    base, treatment = make_pair(experiment)
    try:
        for env in (base, treatment):
            env.reset(seed=5, options=dict(episode_seed=51, start='hanging'))
        first = base.step([1.])
        second = treatment.step([1.])
        assert_observations_equal(first[0], second[0])
        assert first[1:] == second[1:]
        assert second[2:4] == (True, False)
        assert second[4]['fault_reason'] == 'force saturation: tracking model unsupported'
        assert base.total_reward == treatment.total_reward
        assert base.result() == treatment.result()
        assert_physics_equal(base, treatment)
        truth = treatment.core.ground_truth
        dense = (np.cos(truth.theta) - .3 * (truth.x / treatment.core.config.rail_half_m) ** 2
                 - .001 * truth.omega ** 2 - .0002 * treatment.action_scale ** 2)
        # Hanging fixture has no dwell bonus; all omitted horizon penalties remain.
        assert treatment.dwell == 0.
        assert second[1] == pytest.approx((dense - 3 * (steps - 1)) * treatment.reward_scale)
        with pytest.raises(RuntimeError, match='reset'):
            treatment.step([0.])
    finally:
        base.close()
        treatment.close()


def test_invalid_telemetry_keeps_terminal_fault_penalty_and_does_not_advance_physics(tmp_path):
    experiment = make_experiment(tmp_path)
    experiment['observation_config']['dropout_probability'] = 1.
    base, treatment = make_pair(experiment)
    try:
        for env in (base, treatment):
            env.reset(seed=5)
            assert env.step([0.])[2:4] == (False, False)
        before = asdict(treatment.core.ground_truth)
        first = base.step([0.])
        second = treatment.step([0.])
        assert_observations_equal(first[0], second[0])
        assert first[1:] == second[1:]
        assert second[2:4] == (True, False)
        assert treatment.fault is not None
        assert second[1] == pytest.approx(-.12)
        assert treatment.steps == 1
        assert asdict(treatment.core.ground_truth) == before
        assert base.result() == treatment.result()
        with pytest.raises(RuntimeError, match='reset'):
            treatment.step([0.])
    finally:
        base.close()
        treatment.close()


def test_actual_sb3_ppo_bootstraps_horizon_value_and_can_train(tmp_path):
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback

    class RecordRewards(BaseCallback):
        def __init__(self):
            super().__init__()
            self.rewards, self.truncated = [], []

        def _on_step(self):
            self.rewards.append(float(self.locals['rewards'][0]))
            self.truncated.append(self.locals['infos'][0]['TimeLimit.truncated'])
            return True

    experiment = make_experiment(tmp_path)
    experiment['simulation_config']['max_steps'] = 4
    env = continuing_class()(experiment, (51,), randomized=False, bias_degrees=0., randomization_seed=77)
    try:
        model = PPO('MultiInputPolicy', env, seed=17, n_steps=8, batch_size=4,
                    n_epochs=1, gamma=.9, learning_rate=0., device='cpu',
                    policy_kwargs=dict(net_arch=dict(pi=[8], vf=[8])))
        with torch.no_grad():
            model.policy.value_net.weight.zero_()
            model.policy.value_net.bias.fill_(2.)
        callback = RecordRewards()
        model.learn(8, callback=callback)
        assert model.num_timesteps == 8
        assert callback.truncated == [False, False, False, True, False, False, False, True]
        increment = model.rollout_buffer.rewards[:, 0] - np.array(callback.rewards)
        np.testing.assert_allclose(increment, [0., 0., 0., 1.8, 0., 0., 0., 1.8], atol=1e-7)
    finally:
        env.close()
