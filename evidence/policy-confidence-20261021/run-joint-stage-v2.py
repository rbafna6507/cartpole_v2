#!/usr/bin/env python3
"""Reproducible offline joint-task experiment. Run with the project's RL Python.

train --arm ppo|retained --seed N --output NEW
 evaluate RUN --step N --output NEW --seeds N ... --seconds 60 [--numeric] [--stress]
No hardware access. Training/evaluation inputs and sources are pinned in every run.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import sys
import time
import zipfile

import numpy as np
import torch
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure

from cartpole_sdk.learning.diagnostics import preserved_rng, _source_snapshot
from cartpole_sdk.learning.error_training import load_profile, _weights_hash
from cartpole_sdk.learning.ppo import _write_new, experiment_identity, export_actor, TrainingEnv
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.learning.retained_ppo import RetainedPPO
from cartpole_sdk.learning import robust_swing as robust
from cartpole_sdk.learning.transfer_checks import _episode
from cartpole_sdk.learning.training_recipe import validate_randomization
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

def hashfile(path): return sha256(Path(path).read_bytes()).hexdigest()

def sources():
    return dict(robust=robust.source_identity(), driver=hashfile(__file__),
        retained_ppo=hashfile(ROOT/'src/cartpole_sdk/learning/retained_ppo.py'))

def atomic(path, value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    tmp.replace(path)

def anchors(model, warm, spec, destination):
    """Frozen actor targets on training trajectories plus independent balance states."""
    recipe=json.loads(warm['files']['run/recipe.json'].read_text())
    rng=np.random.default_rng(spec['seed'])
    with np.load(warm['files']['run/demonstrations.npz'],allow_pickle=False) as data:
        eligible=np.flatnonzero(np.isin(data['episode'],recipe['demonstrations']['train_episodes']))
        indices=rng.choice(eligible,size=spec['trajectory_rows'],replace=False)
        observed={key:np.array(data[key][indices],dtype=np.float32) for key in ('state','valid','age_s')}
        episodes=data['episode'][indices].copy()
    n=spec['synthetic_balance_rows']
    x,v,theta,omega,acc=[rng.uniform(-r,r,n) for r in (.12,.3,.25,2.,3.)]
    state=np.column_stack((x,v,np.sin(theta),np.cos(theta),omega,acc,np.zeros(n))).astype(np.float32)
    synthetic=dict(state=state,valid=np.ones((n,7),dtype=np.float32),age_s=rng.uniform(0,.02,(n,7)).astype(np.float32))
    observed={key:np.concatenate((observed[key],synthetic[key])) for key in observed}
    with torch.no_grad():
        tensor,_=model.policy.obs_to_tensor(observed)
        target=model.policy.get_distribution(tensor).distribution.mean.cpu().numpy()
    np.savez_compressed(destination,**observed,target=target,trajectory_indices=indices,trajectory_episodes=episodes)
    return observed,target,dict(sha256=hashfile(destination),source_demo_sha256=hashfile(warm['files']['run/demonstrations.npz']),
        train_episode_ids=recipe['demonstrations']['train_episodes'],spec=spec,rows=len(target),
        target='Frozen initialized actor Gaussian mean in normalized action coordinates; never evaluation observations.')

def scenarios(experiment, stress=False):
    nominal=dict(name='nominal',expected='task_success',angle_offset_rad=0.,observation_override={},randomization=None)
    rows=[nominal]
    if not stress:return rows
    obs=experiment['observation_config']
    for sign in (-1,1):
        for combined in (False,True):
            recipe=dict(schema='cartpole-training-randomization-v1',rationale='Declared engineering point, not measured uncertainty.',
                plant=dict(effective_length_scale=[1.+sign*.05 if combined else 1.]*2,
                    angular_damping_scale=[1.+sign*.2 if combined else 1.]*2,
                    coulomb_friction_scale=[1.+sign*.2 if combined else 1.]*2),
                observation={key:[value,value] for key,value in dict(angle_noise_std=.003 if combined else obs['angle_noise_std'],
                    telemetry_delay_steps=5 if combined else obs['telemetry_delay_steps'],
                    command_delay_steps=3 if combined else obs['command_delay_steps']).items()},
                encoder=dict(encoder_bias_rad=[sign*math.pi/180]*2,
                    encoder_sin_error_rad=[sign*4*math.pi/180 if combined else 0.]*2,
                    encoder_cos_error_rad=[sign*5*math.pi/180 if combined else 0.]*2))
            rows.append(dict(nominal,name=('combined' if combined else 'encoder-bias')+('-minus' if sign<0 else '-plus'),
                randomization=validate_randomization(recipe)))
    return rows

class NumericPredictor:
    def __init__(self, path):
        self.policy=load_neural_policy(path,channels=rig_channels(angle_source='raw'))
        self.scale=self.policy.actor['action_scale_m_s2']
    def predict(self, observation, deterministic=True):
        return np.array([self.policy.predict_encoded(observation)/self.scale]),None

def evaluate(model, experiment, output, seeds, seconds, checkpoint_sha256, *, numeric=False, stress=False):
    out=Path(output);out.mkdir(parents=True,exist_ok=False);(out/'traces').mkdir()
    exp=deepcopy(experiment);exp['simulation_config']['max_steps']=round(seconds*100)
    identity=sources();weights=_weights_hash(model);episodes=[]
    predictor=model
    if numeric:
        actor=export_actor(model,dict(experiment=experiment,experiment_sha256=experiment_identity(experiment),
            checkpoint_sha256=checkpoint_sha256,action_scale_m_s2=25.))
        _write_new(out/'actor.json',actor);predictor=NumericPredictor(out/'actor.json')
    matrix=scenarios(exp,stress)
    _write_new(out/'recipe.json',dict(seeds=seeds,seconds=seconds,scenarios=matrix,experiment=exp,
        source=identity,weights_sha256=weights,checkpoint_sha256=checkpoint_sha256,numeric=numeric,hardware_accepted=False))
    with preserved_rng():
        for scenario in matrix:
            env=TrainingEnv(exp,seeds,randomization=scenario['randomization'],randomization_seed=0)
            try:
                for seed in seeds:
                    for start in ('hanging','upright'):
                        result=_episode(predictor,env,seed=seed,start=start,scenario=scenario,root=out)
                        rows=[json.loads(line) for line in (out/result['trace_path']).open()]
                        tail=[row for row in rows if row['elapsed_since_reset_s']>seconds-5]
                        result['tail_theta_rms_deg']=(float(np.sqrt(np.mean([row['ground_truth_after']['theta']**2 for row in tail]))*180/math.pi) if tail and result['final_window_complete'] else None)
                        result['rail_margin_m']=exp['simulation_config']['rail_half_m']-result['max_abs_x_m']
                        episodes.append(result)
            finally:env.close()
    if sources()!=identity or _weights_hash(model)!=weights:raise ValueError('evaluation changed source or weights')
    summary=[]
    for scenario in matrix:
        for start in ('hanging','upright'):
            selected=[row for row in episodes if row['scenario']==scenario['name'] and row['start']==start]
            captures=[row['first_one_second_capture_s'] for row in selected if row['first_one_second_capture_s'] is not None]
            summary.append(dict(scenario=scenario['name'],start=start,episodes=len(selected),holds=sum(row['hold_success'] for row in selected),
                faults=sum(row['fault_reason'] is not None for row in selected),captures=len(captures),
                mean_capture_s=float(np.mean(captures)) if captures else None,
                mean_longest_dwell_s=float(np.mean([row['longest_balance_dwell_s'] for row in selected])),
                worst_max_abs_x_m=max(row['max_abs_x_m'] for row in selected),
                mean_tail_x_rms_m=float(np.mean([row['final_window_x_rms_m'] for row in selected])) if all(row['final_window_x_rms_m'] is not None for row in selected) else None))
    report=dict(completed=True,hardware_accepted=False,numeric=numeric,recipe_sha256=hashfile(out/'recipe.json'),episodes=episodes,summary=summary)
    _write_new(out/'report.json',report);return report

def train(args):
    protocol_path=(Path(args.protocol).resolve() if args.protocol else HERE/'joint-protocol.json')
    protocol=json.loads(protocol_path.read_text())
    objective=protocol.get('objective','finite-dwell')
    if objective not in ('finite-dwell','dense-continuing'):raise ValueError('unknown training objective')
    if args.seed not in protocol['optimizer_seeds'] and not args.smoke:raise ValueError('optimizer seed absent from frozen protocol')
    exp,inputs=load_profile(ROOT/protocol['profile'],seconds=protocol['training_seconds'])
    warm=robust.load_warm_start(ROOT/protocol['warm_run'],ROOT/protocol['warm_parity'])
    train_seeds=list(range(protocol['training_seeds'][0],protocol['training_seeds'][1]+1))
    if set(train_seeds+protocol['development_seeds'])&set(warm['used_seeds']):raise ValueError('training/evaluation overlap warm data')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);(out/'checkpoints').mkdir()
    inputs[str(protocol_path)]=hashfile(protocol_path)
    identity=sources();began=time.monotonic()
    steps=8 if args.smoke else protocol['steps'];every=steps if args.smoke else protocol['checkpoint_every']
    eval_steps=(0,steps) if args.smoke else protocol['evaluate_at']
    setting=protocol['randomization']
    env_class=robust.RobustSwingEnv
    if objective=='dense-continuing':
        from cartpole_sdk.learning.continuing_swing import ContinuingSwingEnv
        env_class=ContinuingSwingEnv
        module_path=ROOT/'src/cartpole_sdk/learning/continuing_swing.py'
        inputs[str(module_path)]=hashfile(module_path)
    env=env_class(exp,train_seeds,randomized=setting is not None,bias_degrees=0.,randomization_seed=args.seed,randomization=setting)
    torch.set_num_threads(1)
    klass=RetainedPPO if args.arm=='retained' else EquilibriumPPO
    model=klass('MultiInputPolicy',env,seed=args.seed,device='cpu',verbose=0,n_steps=8 if args.smoke else 1024,
        batch_size=4 if args.smoke else 64,n_epochs=1 if args.smoke else 10,gamma=.999,gae_lambda=.98,
        learning_rate=protocol['learning_rate'],policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=math.log(protocol['policy_std'])))
    model.set_logger(configure(str(out/'logs'),['csv']))
    copied=robust.copy_actor_weights(model,warm['actor'],action_scale=env.action_scale)
    migration=robust.migration_parity(model,warm['actor'],exp)
    if not migration['pass']:raise ValueError('actor migration failed')
    projection=model.project_equilibrium()
    observations,targets,anchor_info=anchors(model,warm,protocol['anchors'],out/'anchors.npz')
    if args.arm=='retained':model.configure_retention(observations,targets,**protocol['retention'])
    recipe=dict(schema='cartpole-confidence-joint-run-v1',protocol=protocol,source=identity,inputs=inputs,experiment=exp,
        experiment_sha256=experiment_identity(exp),warm_binding=warm['binding'],copied_actor_weights=copied,
        migration=migration,initial_projection=projection,arm=args.arm,seed=args.seed,anchors=anchor_info,smoke=args.smoke,
        actual_steps=steps,training_objective=objective,hardware_accepted=False)
    _write_new(out/'recipe.json',recipe);_source_snapshot(out/'source.zip')
    with zipfile.ZipFile(out/'source.zip','a',zipfile.ZIP_DEFLATED) as archive:
        archive.write(__file__,'confidence/run-joint-stage.py');archive.write(protocol_path,'confidence/joint-protocol.json')
        for path in inputs:archive.write(path,'confidence/inputs/'+Path(path).name)
    for name,path in warm['files'].items():
        target=out/'warm-start'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    report=dict(completed=False,recipe_sha256=hashfile(out/'recipe.json'),source_zip_sha256=hashfile(out/'source.zip'),checkpoints=[],evaluations=[])
    class Episodes(BaseCallback):
        def _on_step(self):
            for info in self.locals.get('infos',[]):
                if 'episode_result' in info:
                    with (out/'training-episodes.jsonl').open('a') as stream:stream.write(json.dumps(dict(timesteps=int(self.num_timesteps),**info['episode_result']),allow_nan=False)+'\n')
            return True
    try:
        for step in range(0,steps+1,every):
            if step:
                model.learn(total_timesteps=every,reset_num_timesteps=step==every,callback=Episodes(),log_interval=1)
                model.logger.record('time/total_timesteps',int(model.num_timesteps));model.logger.dump(step=int(model.num_timesteps))
            if sources()!=identity or any(hashfile(path)!=pin for path,pin in inputs.items()):raise ValueError('pinned training source/input changed')
            cp=out/'checkpoints'/f'step-{step:09d}.zip';model.save(cp)
            row=dict(step=step,path=str(cp.relative_to(out)),sha256=hashfile(cp),actor_weights_sha256=robust.actor_weights_hash(model))
            report['checkpoints'].append(row);atomic(out/'report.json',report)
            if step in eval_steps:
                seconds=.05 if args.smoke else protocol['evaluation_seconds']
                evaluation=evaluate(model,exp,out/f'eval-{step:09d}',protocol['development_seeds'],seconds,row['sha256'])
                report['evaluations'].append(dict(step=step,path=f'eval-{step:09d}/report.json',sha256=hashfile(out/f'eval-{step:09d}/report.json'),summary=evaluation['summary']))
            atomic(out/'report.json',report)
            print(json.dumps(dict(arm=args.arm,seed=args.seed,step=step,evaluation=report['evaluations'][-1]['summary'] if step in eval_steps else None)),flush=True)
        report.update(completed=True,wall_seconds=time.monotonic()-began);atomic(out/'report.json',report)
    except BaseException as exc:
        report['error']=str(exc);atomic(out/'report.json',report);raise
    finally:env.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('train');t.add_argument('--arm',choices=('ppo','retained'),required=True);t.add_argument('--seed',type=int,required=True)
    t.add_argument('--output',type=Path,required=True);t.add_argument('--smoke',action='store_true');t.add_argument('--protocol',type=Path)
    e=sub.add_parser('evaluate');e.add_argument('run',type=Path);e.add_argument('--step',type=int,required=True);e.add_argument('--output',type=Path,required=True)
    e.add_argument('--seeds',type=int,nargs='+',required=True);e.add_argument('--seconds',type=float,default=60.);e.add_argument('--numeric',action='store_true');e.add_argument('--stress',action='store_true')
    args=p.parse_args();torch.set_num_threads(1)
    if args.command=='train':return train(args)
    recipe=json.loads((args.run/'recipe.json').read_text());report=json.loads((args.run/'report.json').read_text())
    if not report['completed'] or hashfile(args.run/'recipe.json')!=report['recipe_sha256'] or sources()!=recipe['source']:raise ValueError('run incomplete or source/recipe changed')
    seeds=recipe['protocol']['training_seeds'];prior=set(range(seeds[0],seeds[1]+1))|set(recipe['protocol']['development_seeds'])|robust.PRIOR_USED_SEEDS
    if len(set(args.seeds))!=len(args.seeds) or set(args.seeds)&prior:raise ValueError('evaluation seeds must be fresh')
    if not 5<=args.seconds<=60:raise ValueError('evaluation seconds must be 5..60')
    checkpoint=next(row for row in report['checkpoints'] if row['step']==args.step)
    cp=args.run/checkpoint['path']
    if cp.parent.resolve()!=(args.run/'checkpoints').resolve() or hashfile(cp)!=checkpoint['sha256']:raise ValueError('checkpoint binding mismatch')
    klass=RetainedPPO if recipe['arm']=='retained' else EquilibriumPPO
    model=klass.load(cp,device='cpu')
    evaluation=evaluate(model,recipe['experiment'],args.output,args.seeds,args.seconds,checkpoint['sha256'],numeric=args.numeric,stress=args.stress)
    print(json.dumps(evaluation['summary'],indent=2))

if __name__=='__main__':main()
