"""Actual tiny PPO learning, checkpoint resume and dependency-free SDK parity."""
import importlib.util
import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

import pytest

pytest.importorskip('stable_baselines3')

from cartpole_sdk.control.parameters import ControllerParameters
from cartpole_sdk.policies import HostPolicyParameters
from cartpole_sdk.sim import SimulationConfig
from cartpole_sdk.sim.rig_gym_env import RigObservationConfig, RigCartpoleEnv
from cartpole_sdk.learning.model_experiment import digest, build_experiment


def api():
    assert importlib.util.find_spec('cartpole_sdk.learning.ppo'), 'PPO training is missing'
    from cartpole_sdk.learning.ppo import train_ppo, evaluate_ppo, load_checkpoint
    return train_ppo, evaluate_ppo, load_checkpoint


def make_experiment(tmp_path):
    config = SimulationConfig(control_steps=10, max_steps=5)
    model = dict(schema='cartpole-development-model-v1', status='DEVELOPMENT_ONLY',
                 simulation_config=asdict(config), rationale='Synthetic PPO software smoke only.',
                 limitations=['Not physical evidence.'])
    model['content_sha256'] = digest(model)
    path = tmp_path / 'model.json'
    path.write_text(json.dumps(model))
    return build_experiment(path, executor_parameters=asdict(ControllerParameters(bw=6.)),
        observation_config=asdict(RigObservationConfig()), prior_parameters=asdict(HostPolicyParameters()),
        development_only=True)


def test_actual_ppo_checkpoint_resume_heldout_and_sdk_actor_parity(tmp_path):
    train, evaluate, load = api()
    exp = make_experiment(tmp_path)
    run = tmp_path / 'run'
    kwargs = dict(training_seeds=(11, 12), seed=7, total_timesteps=32,
                  n_steps=16, batch_size=8, n_epochs=1, checkpoint_every=16)
    manifest = train(exp, run, **kwargs)
    assert manifest['algorithm'] == 'PPO'
    assert manifest['timesteps_completed'] == 32
    assert manifest['hardware_accepted'] is False
    assert manifest['status'] == 'DEVELOPMENT_ONLY'
    assert (run / 'checkpoints' / 'step-000000016' / 'manifest.json').exists()
    model, frozen = load(run)
    assert frozen == manifest
    assert sha256((run / 'checkpoint.zip').read_bytes()).hexdigest() == manifest['checkpoint_sha256']
    report = evaluate(run, seeds=(101,))
    assert report['episodes_count'] == 2
    assert report['model_content_sha256'] == exp['admission']['model']['content_sha256']
    with pytest.raises(ValueError, match='overlap'):
        evaluate(run, seeds=(11,))
    from cartpole_sdk.policies.neural import load_neural_policy
    from cartpole_sdk.policies.rig_observation import simulation_channels
    env = RigCartpoleEnv(SimulationConfig(**exp['simulation_config']),
                        parameters=ControllerParameters(**exp['executor_parameters']))
    try:
        obs, _ = env.reset(seed=77, options={'state': (.01, 0., .15, -.1)})
        policy = load_neural_policy(run / 'actor.json', channels=simulation_channels())
        policy.reset(env.session)
        action, _ = model.predict(obs, deterministic=True)
        actual = policy.act(env.sdk_observation)
        assert actual.acceleration_m_s2 == pytest.approx(float(action[0]) * manifest['action_scale_m_s2'], abs=1e-5)
        assert policy.act(env.sdk_observation) is None  # Replay latches closed.
    finally:
        env.close()
    resumed = train(exp, tmp_path / 'resumed', resume=run, **kwargs)
    assert resumed['timesteps_completed'] == 64
    assert resumed['resumed_from_checkpoint_sha256'] == manifest['checkpoint_sha256']
    changed = json.loads(json.dumps(exp))
    changed['executor_parameters']['bw'] = 7.
    with pytest.raises(ValueError, match='resume.*configuration'):
        train(changed, tmp_path / 'bad-resume', resume=run, **kwargs)
    with pytest.raises(FileExistsError):
        train(exp, run, **kwargs)
    # A corrupted archive must fail before SB3 deserializes it.
    with (run / 'checkpoint.zip').open('ab') as stream:
        stream.write(b'tamper')
    with pytest.raises(ValueError, match='checkpoint.*hash'):
        load(run)


def test_ppo_cli_has_runnable_subcommands_and_actor_import_is_dependency_free(tmp_path):
    api()
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'examples/train_ppo.py'), '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'train' in result.stdout and 'evaluate' in result.stdout
    result = subprocess.run([sys.executable, '-S', '-c',
        "import sys; sys.path.insert(0,'src'); import cartpole_sdk.policies.neural; "
        "assert 'torch' not in sys.modules and 'numpy' not in sys.modules and 'mujoco' not in sys.modules"],
        cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_finite_objective_horizon_is_terminal_without_sb3_bootstrap(tmp_path):
    api()
    import numpy as np
    from cartpole_sdk.learning.ppo import TrainingEnv
    from stable_baselines3.common.vec_env import DummyVecEnv
    exp = make_experiment(tmp_path)
    env = DummyVecEnv([lambda: TrainingEnv(exp, (11,))])
    try:
        env.reset()
        for _ in range(exp['simulation_config']['max_steps']):
            _, _, done, infos = env.step(np.array([[0.]], dtype=np.float32))
        assert done[0]
        assert infos[0]['TimeLimit.truncated'] is False
    finally:
        env.close()


def test_randomized_training_records_recipe_optimizer_and_separate_hold_evaluation(tmp_path):
    train, evaluate, load = api()
    from cartpole_sdk.learning.training_recipe import default_randomization
    exp = make_experiment(tmp_path)
    kwargs = dict(training_seeds=(11, 12), seed=7, total_timesteps=16,
                  n_steps=8, batch_size=4, n_epochs=1, checkpoint_every=16,
                  gamma=.999, gae_lambda=.98, learning_rate=.0002, reward_scale=.02,
                  randomization=default_randomization())
    run = tmp_path / 'randomized'
    manifest = train(exp, run, **kwargs)
    model, _ = load(run)
    assert model.gamma == .999 and model.gae_lambda == .98
    assert manifest['hyperparameters']['reward_scale'] == .02
    assert manifest['training_recipe']['randomization'] == kwargs['randomization']
    assert (run / 'logs' / 'progress.csv').exists()
    rows = [json.loads(line) for line in (run / 'episodes.jsonl').read_text().splitlines()]
    assert rows and rows[0]['episode_parameters']['simulation_config'] != exp['simulation_config']
    report = evaluate(run, seeds=(101,), hold_seconds=5.)
    assert report['hold_seconds'] == 5.
    assert report['successes'] == 0 and report['hold_successes'] == 0
    assert report['by_start']['hanging']['episodes_count'] == 1
    assert report['by_start']['upright']['episodes_count'] == 1
    assert all(episode['final_window_balanced_fraction'] <= 1. for episode in report['episodes'])
    assert all(episode['episode_parameters']['simulation_config'] == exp['simulation_config'] for episode in report['episodes'])
    with pytest.raises(ValueError, match='resume configuration'):
        train(exp, tmp_path / 'bad-recipe', resume=run, **dict(kwargs, randomization=None))
    with pytest.raises(ValueError, match='resume configuration'):
        train(exp, tmp_path / 'bad-gamma', resume=run, **dict(kwargs, gamma=.99))
    with pytest.raises(ValueError, match='resume configuration'):
        train(exp, tmp_path / 'bad-reward-scale', resume=run, **dict(kwargs, reward_scale=.01))


def test_training_env_randomizes_per_episode_with_reproducible_reset_history(tmp_path):
    api()
    from cartpole_sdk.learning.ppo import TrainingEnv
    from cartpole_sdk.learning.training_recipe import default_randomization
    exp = make_experiment(tmp_path)
    environments = [TrainingEnv(exp, (11,), randomization=default_randomization(), randomization_seed=17) for _ in range(2)]
    histories = []
    try:
        for env in environments:
            configs = []
            for _ in range(3):
                _, info = env.reset()
                configs.append(info['episode_parameters'])
            histories.append(configs)
        assert histories[0] == histories[1]
        assert histories[0][0]['simulation_config'] != histories[0][2]['simulation_config']
        assert environments[0].core.parameters.rail == exp['executor_parameters']['rail']
    finally:
        for env in environments:
            env.close()


def test_cli_supplies_wide_seed_pool_and_training_options(tmp_path):
    api()
    import subprocess
    import sys
    exp = make_experiment(tmp_path)
    paths = {}
    for name in ('executor_parameters', 'observation_config', 'prior_parameters'):
        paths[name] = tmp_path / (name + '.json')
        paths[name].write_text(json.dumps(exp[name]))
    run = tmp_path / 'cli-run'
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / 'examples/train_ppo.py'), 'train',
        '--model', str(tmp_path / 'model.json'), '--development-only',
        '--output', str(run), '--seed', '5', '--steps', '8', '--n-steps', '8',
        '--batch-size', '4', '--epochs', '1', '--gamma', '.998', '--reward-scale', '.03', '--randomize']
    for name, path in paths.items():
        command += ['--' + name.replace('_', '-'), str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((run / 'manifest.json').read_text())
    assert len(manifest['training_seeds']) >= 128
    assert manifest['hyperparameters']['gamma'] == .998
    assert manifest['hyperparameters']['reward_scale'] == .03
    assert manifest['training_recipe']['randomization'] is not None


def test_sustained_hold_distinguishes_short_balancing_from_full_window(tmp_path):
    api()
    import numpy as np
    from cartpole_sdk.learning.ppo import TrainingEnv
    exp = make_experiment(tmp_path)
    exp['simulation_config']['max_steps'] = 600
    env = TrainingEnv(exp, (11,))
    try:
        env.reset()
        # Exact unstable equilibrium is a deterministic physical fixture: no
        # demand preserves it, giving hand-countable balanced control periods.
        env.core.reset(seed=1, options={'state': (0., 0., 0., 0.)})
        for _ in range(600):
            env.step(np.array([0.], dtype=np.float32))
        report = env.result(hold_seconds=5.)
        assert report['success'] and report['hold_success']
        assert report['first_one_second_capture_s'] == 1.
        assert report['final_window_balanced_fraction'] == 1.
        assert report['final_window_complete']
        assert report['longest_balance_dwell_s'] == pytest.approx(6.)
        assert not env.result(hold_seconds=7.)['hold_success']
        assert not env.result(hold_seconds=7.)['final_window_complete']
    finally:
        env.close()


@pytest.mark.parametrize('mode', ['vision', 'fused'])
def test_camera_mode_actual_learning_export_parity_and_heldout(tmp_path, mode):
    train, evaluate, load = api()
    from cartpole_sdk.learning.training_recipe import default_randomization
    from cartpole_sdk.policies.neural import load_neural_policy
    exp = make_experiment(tmp_path)
    exp['observation_config'] = asdict(RigObservationConfig(angle_source=mode,
        angle_frame_id='physical-upright', vision_frame_period_ns=12_500_000,
        vision_latency_ns=20_000_000, vision_angle_noise_std=.003))
    run = tmp_path / mode
    manifest = train(exp, run, seed=7, total_timesteps=64, n_steps=16,
        batch_size=8, n_epochs=1, checkpoint_every=64,
        randomization=default_randomization(angle_source=mode))
    model, _ = load(run)
    env = RigCartpoleEnv(SimulationConfig(**exp['simulation_config']),
        parameters=ControllerParameters(**exp['executor_parameters']),
        observation_config=RigObservationConfig(**exp['observation_config']))
    try:
        obs, info = env.reset(seed=77, options={'state': (.01, 0., .15, -.1)})
        assert info['reset_warmup_ns'] > 0
        policy = load_neural_policy(run / 'actor.json', channels=env.channels)
        policy.reset(env.session)
        action, _ = model.predict(obs, deterministic=True)
        actual = policy.act(env.sdk_observation)
        assert actual is not None, policy.fault_reason
        assert actual.acceleration_m_s2 == pytest.approx(
            float(action[0]) * manifest['action_scale_m_s2'], abs=1e-5)
        assert policy.actor['observation_contract']['angle_source'] == mode
        assert policy.actor['executor_parameters'] == exp['executor_parameters']
    finally:
        env.close()
    report = evaluate(run, seeds=(101,))
    assert report['episodes_count'] == 2
    assert all(row['fault_reason'] is None and row['steps'] == 5 for row in report['episodes'])


def test_reward_scaling_changes_optimizer_input_without_changing_benchmark(tmp_path):
    api()
    import numpy as np
    from cartpole_sdk.learning.ppo import TrainingEnv
    exp = make_experiment(tmp_path)
    nominal = TrainingEnv(exp, (11,))
    scaled = TrainingEnv(exp, (11,), reward_scale=.01)
    try:
        nominal.reset()
        scaled.reset()
        for _ in range(5):
            first = nominal.step(np.array([.25], dtype=np.float32))
            second = scaled.step(np.array([.25], dtype=np.float32))
            assert second[1] == pytest.approx(first[1] * .01)
            np.testing.assert_array_equal(first[0]['state'], second[0]['state'])
        assert nominal.result() == scaled.result()
    finally:
        nominal.close()
        scaled.close()
