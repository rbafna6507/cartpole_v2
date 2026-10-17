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
