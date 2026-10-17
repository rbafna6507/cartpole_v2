"""Local CPU development probe; no hardware or cloud connection."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import time

repo = Path('/Users/rbafna/projects/cartpole_v2')
output = Path(tempfile.mkdtemp(prefix='cartpole-training-pilot-'))
shutil.copytree(repo / 'src', output / 'src', ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(repo / 'training/profiles/passive-20261017', output / 'inputs')
shutil.copy2(__file__, output / 'benchmark.py')
sys.path.insert(0, str(output / 'src'))
print('BENCHMARK_OUTPUT', output, flush=True)

import numpy as np
import torch
from stable_baselines3 import PPO
from cartpole_sdk.learning.model_experiment import build_experiment
from cartpole_sdk.learning.ppo import TrainingEnv, train_ppo, evaluate_ppo
from cartpole_sdk.learning.training_recipe import DEFAULT_TRAINING_SEEDS, default_randomization

profile = output / 'inputs'
read = lambda name: json.loads((profile / name).read_text())
parameters = read('executor-parameters.json')
parameters = parameters.get('parameters', parameters)
experiment = build_experiment(profile / 'model.json', executor_parameters=parameters,
    observation_config=read('observation-config.json'), prior_parameters=read('prior-parameters.json'),
    development_only=True, seconds=25.)
torch.set_num_threads(1)
env = TrainingEnv(experiment, DEFAULT_TRAINING_SEEDS,
                  randomization=default_randomization(), randomization_seed=20261017)
model = PPO('MultiInputPolicy', env, seed=20261017, device='cpu', verbose=0,
    n_steps=1024, batch_size=64, n_epochs=10, learning_rate=.0003, gamma=.999,
    gae_lambda=.98, clip_range=.2, ent_coef=0., vf_coef=.5, max_grad_norm=.5,
    policy_kwargs=dict(net_arch=dict(pi=[64,64], vf=[64,64]), activation_fn=torch.nn.Tanh))
baseline = []
evaluation = TrainingEnv(experiment, (1001,1002))
try:
    for seed in (1001,1002):
        for start in ('hanging','upright'):
            observation, _ = evaluation.reset(options=dict(episode_seed=seed,start=start))
            while True:
                action, _ = model.predict(observation, deterministic=True)
                observation, _, terminated, truncated, _ = evaluation.step(action)
                if terminated or truncated:
                    break
            baseline.append(evaluation.result())
finally:
    evaluation.close()
    env.close()
(output/'before.json').write_text(json.dumps(baseline,indent=2))
print('BEFORE', json.dumps([dict(start=row['start'],score=row['score'],success=row['success'],
    hold_success=row['hold_success'],fault=row['fault_reason']) for row in baseline]),flush=True)
began = time.perf_counter()
manifest = train_ppo(experiment, output/'run', seed=20261017,total_timesteps=51200,
    n_steps=1024,batch_size=64,n_epochs=10,checkpoint_every=10240,randomization=default_randomization())
training_seconds = time.perf_counter()-began
after = evaluate_ppo(output/'run',seeds=(1001,1002),hold_seconds=5.)
(output/'after.json').write_text(json.dumps(after,indent=2))
rows=[json.loads(line) for line in (output/'run/episodes.jsonl').read_text().splitlines()]
summary=dict(development_only=True,source_snapshot=str(output/'src'),
    limitation='Four development episodes and a short pilot do not establish convergence or hardware transfer.',
    timesteps=manifest['timesteps_completed'],training_seconds=training_seconds,
    training_control_steps_per_second=manifest['timesteps_completed']/training_seconds,
    before_mean_score=float(np.mean([row['score'] for row in baseline])),
    before_successes=sum(row['success'] for row in baseline),
    before_hold_successes=sum(row['hold_success'] for row in baseline),
    after_mean_score=after['mean_score'],after_successes=after['successes'],
    after_hold_successes=after['hold_successes'],after_by_start=after['by_start'],
    training_episodes=len(rows),training_successes=sum(row['success'] for row in rows),
    training_hold_successes=sum(row['hold_success'] for row in rows),
    training_faults=sum(row['fault_reason'] is not None for row in rows),
    first_ten_training_mean_score=float(np.mean([row['score'] for row in rows[:10]])),
    last_ten_training_mean_score=float(np.mean([row['score'] for row in rows[-10:]])))
(output/'summary.json').write_text(json.dumps(summary,indent=2))
print('SUMMARY',json.dumps(summary),flush=True)
