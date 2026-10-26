"""Offline projected PPO experiment with immutable checkpoints and numeric export."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import numpy as np
import torch
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure
from cartpole_sdk.policies.neural import validate_actor
from cartpole_sdk.policies.rig_observation import contract_from_config
from cartpole_sdk.sim.profiles import PROFILE_ID, load_profile, profile_experiment
from .controlled_swing import ControlledSwingEnv, OBJECTIVE, controlled_randomization
from .ppo import _save_checkpoint, _write_new, experiment_identity, provenance
from .projected_ppo import EquilibriumPPO
from .robust_swing import _actor_layers
from .candidate_parity import check_candidate, model_weights_sha256
from .diagnostics import preserved_rng

TRAINING_SEEDS = tuple(range(108000,108128))
DEVELOPMENT_SEEDS = (109400,109401)
CONFIRMATION_SEEDS = tuple(range(109500,109516))


def evaluate(model, experiment, seeds, *, randomization=None):
    episodes=[]
    env=ControlledSwingEnv(experiment,seeds,randomization=randomization,randomization_seed=9401,reward_scale=.01)
    try:
        with preserved_rng():
            for seed in seeds:
                for start in ('hanging','upright'):
                    observation,_=env.reset(options=dict(episode_seed=seed,start=start))
                    while True:
                        action,_=model.predict(observation,deterministic=True)
                        observation,_,terminated,truncated,_=env.step(action)
                        if terminated or truncated:break
                    episodes.append(env.result())
    finally:env.close()
    return dict(episodes=episodes,hold_successes=sum(e['hold_success'] for e in episodes),
                faults=sum(e['fault_reason'] is not None for e in episodes),
                mean_score=float(np.mean([e['score'] for e in episodes])),
                randomization=randomization)


def train(output, *, steps=102400, checkpoint_every=25600, seconds=25., seed=11,
          init_actor=None, evaluation_seeds=DEVELOPMENT_SEEDS, n_steps=1024,
          randomized=True, profile_id=PROFILE_ID):
    if any(type(v) is not int or v<=0 for v in (steps,checkpoint_every,n_steps)) or n_steps%64 or steps%n_steps or checkpoint_every%n_steps or steps%checkpoint_every:
        raise ValueError('steps and checkpoint interval must divide exactly in rollout blocks; n_steps multiple of64')
    if not evaluation_seeds or any(type(s) is not int or s<0 for s in evaluation_seeds) or set(evaluation_seeds)&set(TRAINING_SEEDS):
        raise ValueError('evaluation seeds must be disjoint nonnegative integers')
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    experiment=profile_experiment(profile_id,seconds=seconds)
    randomization=controlled_randomization() if randomized else None
    torch.set_num_threads(1)
    env=ControlledSwingEnv(experiment,TRAINING_SEEDS,randomization=randomization,randomization_seed=seed,reward_scale=.01)
    settings=dict(n_steps=n_steps,batch_size=64,n_epochs=10,learning_rate=3e-6,gamma=.999,gae_lambda=.98,
                  policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=float(np.log(.05))))
    model=EquilibriumPPO('MultiInputPolicy',env,seed=seed,device='cpu',**settings)
    source_actor=None
    if init_actor is not None:
        source_actor=json.loads(Path(init_actor).read_text());validate_actor(source_actor)
        if source_actor['observation_contract']!=contract_from_config(experiment['observation_config']) or source_actor['action_scale_m_s2']!=env.action_scale:
            raise ValueError('initial actor observation contract/action scale mismatch')
        with torch.no_grad():
            for layer,source in zip(_actor_layers(model),source_actor['layers']):
                layer.weight.copy_(torch.as_tensor(source['weights'],dtype=layer.weight.dtype))
                layer.bias.copy_(torch.as_tensor(source['bias'],dtype=layer.bias.dtype))
    output.mkdir(parents=True)
    model.set_logger(configure(str(output/'logs'),['csv']))
    extra={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('controlled_training.py','controlled_swing.py','projected_ppo.py')}
    common=dict(schema='cartpole-ppo-checkpoint-v1',algorithm='EquilibriumPPO',status='DEVELOPMENT_ONLY',hardware_accepted=False,
        simulation_only=True,experiment=experiment,experiment_sha256=experiment_identity(experiment),provenance=provenance(),
        experiment_sources_sha256=extra,profile_id=profile_id,profile_content_sha256=load_profile(profile_id)['content_sha256'],
        training_seeds=list(TRAINING_SEEDS),evaluation_seeds=list(evaluation_seeds),confirmation_seeds=list(CONFIRMATION_SEEDS),seed=seed,
        action_scale_m_s2=env.action_scale,objective=OBJECTIVE,training_recipe=dict(randomization=randomization,reward_scale=.01,
        transfer='Actor-only; fresh critic, optimizer and RNG. Not continuation of old training.',
        initial_actor_content_sha256=None if source_actor is None else source_actor['content_sha256'],
        hyperparameters={k:v for k,v in settings.items() if k!='policy_kwargs'},log_std_init=float(np.log(.05)),network=[21,64,64,1]))
    _write_new(output/'recipe.json',common)
    if source_actor is not None:_write_new(output/'initial-actor.json',source_actor)
    report=dict(completed=False,steps=0,hardware_accepted=False,evaluations=[],checkpoints=[])
    class Episodes(BaseCallback):
        def _on_step(self):
            for info in self.locals.get('infos',[]):
                if 'episode_result' in info:
                    with (output/'episodes.jsonl').open('a') as stream:stream.write(json.dumps(dict(timesteps=int(self.num_timesteps),**info['episode_result']))+'\n')
            return True
    try:
        for step in range(0,steps+1,checkpoint_every):
            if step:model.learn(checkpoint_every,reset_num_timesteps=step==checkpoint_every,callback=Episodes())
            for name,pin in extra.items():
                if sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=pin:raise ValueError('experiment source changed during training')
            checkpoint=output/'checkpoints'/f'step-{step:09d}'
            manifest=_save_checkpoint(model,checkpoint,common)
            # Reload through projected class to preserve the algorithm for future continuation.
            restored=EquilibriumPPO.load(checkpoint/'checkpoint.zip',device='cpu')
            if model_weights_sha256(restored)!=model_weights_sha256(model):raise ValueError('checkpoint weight roundtrip mismatch')
            evaluations=dict(step=step,nominal=evaluate(model,experiment,evaluation_seeds),
                             randomized=evaluate(model,experiment,evaluation_seeds,randomization=randomization))
            _write_new(checkpoint/'evaluation.json',evaluations)
            report['evaluations'].append(evaluations);report['checkpoints'].append(str(checkpoint.relative_to(output)))
            report['steps']=step
            temporary=output/'progress.tmp';temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(output/'progress.json')
            print(json.dumps(dict(steps=step,nominal_holds=evaluations['nominal']['hold_successes'],randomized_holds=evaluations['randomized']['hold_successes'])),flush=True)
        parity=check_candidate(restored,experiment,output/'numeric-parity',checkpoint_sha256=manifest['checkpoint_sha256'],seeds=evaluation_seeds[:1],seconds=min(seconds,.2))
        report['numeric_parity']=parity
        if not parity['emission_parity_pass'] or parity['rejected_inputs']:raise ValueError('numeric SDK emission parity failed')
        shutil.copyfile(checkpoint/'actor.json',output/'actor.json')
        report['completed']=True
        _write_new(output/'report.json',report)
        return report
    finally:env.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--steps',type=int,default=102400)
    parser.add_argument('--checkpoint-every',type=int,default=25600)
    parser.add_argument('--seconds',type=float,default=25.)
    parser.add_argument('--seed',type=int,default=11)
    parser.add_argument('--init-actor',type=Path)
    parser.add_argument('--profile',dest='profile_id',default=PROFILE_ID)
    parser.add_argument('--evaluation-seeds',nargs='+',type=int,default=DEVELOPMENT_SEEDS)
    parser.add_argument('--nominal-training',action='store_true')
    args=vars(parser.parse_args());args['randomized']=not args.pop('nominal_training')
    train(**args)

if __name__=='__main__':main()
