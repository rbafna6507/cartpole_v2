#!/usr/bin/env python3
"""Evidence-only filtered BAL actor transfer into existing combined PPO components."""
import argparse
from copy import deepcopy
from hashlib import sha256
import io,json,math
from pathlib import Path
import time,zipfile
import numpy as np
import torch
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure
from cartpole_sdk.learning.candidate_parity import check_candidate,model_weights_sha256
from cartpole_sdk.learning.diagnostics import preserved_rng
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.learning.ppo import TrainingEnv,experiment_identity,export_actor
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.learning.retained_ppo import RetainedPPO
from cartpole_sdk.learning.robust_swing import _actor_layers,actor_weights_hash
from cartpole_sdk.learning.transfer_checks import _episode
from cartpole_sdk.policies.neural import load_neural_policy,validate_actor
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import contract_from_config,rig_channels
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'pyproject.toml').exists())
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def atomic(p,v):
    temporary=Path(p).with_suffix('.tmp');temporary.write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n');temporary.replace(p)
def validate_seed_partitions(protocol):
    groups=[protocol[k] for k in ('training_seeds','anchor_seeds','development_seeds','confirmation_seeds')]
    if any(not x or len(set(x))!=len(x) or any(type(v) is not int or v<0 for v in x) for x in groups):raise ValueError('invalid seed partition')
    for i,a in enumerate(groups):
        for b in groups[i+1:]:
            if set(a)&set(b):raise ValueError('seed partitions overlap')
def copy_filtered_actor(model,actor,experiment):
    _,parameters,observations,_=validate_experiment(experiment)
    if observations.angle_source!='filtered' or actor.get('angle_source')!='filtered':raise ValueError('filtered actor and experiment required')
    validate_actor(actor)
    if actor['observation_contract']!=contract_from_config(experiment['observation_config']) or actor['action_scale_m_s2']!=25.:raise ValueError('actor contract or scale mismatch')
    if min(experiment['simulation_config']['max_acceleration_m_s2'],max(parameters.amax_s,parameters.amax_b))!=25.:raise ValueError('environment action scale mismatch')
    layers=_actor_layers(model)
    with torch.no_grad():
        for layer,source in zip(layers,actor['layers']):
            layer.weight.copy_(torch.as_tensor(source['weights'],dtype=layer.weight.dtype,device=layer.weight.device))
            layer.bias.copy_(torch.as_tensor(source['bias'],dtype=layer.bias.dtype,device=layer.bias.device))
    return actor_weights_hash(model)
def protocol(path):
    p=json.loads(Path(path).read_text());validate_seed_partitions(p)
    if p['schema']!='cartpole-filtered-combined-research-v1':raise ValueError('unsupported protocol')
    for name,pin in p['bindings'].items():
        if digest(ROOT/name)!=pin:raise ValueError('input/source changed: '+name)
    return p

def foundation(p):
    policy=load_neural_policy(ROOT/p['actor'],channels=rig_channels(angle_source='filtered'))
    checkpoint=ROOT/p['checkpoint']
    if digest(checkpoint)!=policy.actor['checkpoint_sha256']:raise ValueError('actor/checkpoint binding mismatch')
    with zipfile.ZipFile(checkpoint) as archive:
        state=torch.load(io.BytesIO(archive.read('policy.pth')),weights_only=True,map_location='cpu')
    for source,prefix in zip(policy.actor['layers'],('mlp_extractor.policy_net.0','mlp_extractor.policy_net.2','action_net')):
        for source_key,dest_key in (('weights','weight'),('bias','bias')):
            if not np.array_equal(np.asarray(source[source_key]),state[prefix+'.'+dest_key].numpy()):raise ValueError('actor/checkpoint weights differ')
    return policy

def model_for(p,arm,seed,env,*,smoke=False):
    if arm not in p['arms'] or seed not in p['optimizer_seeds']:raise ValueError('arm/seed absent from protocol')
    klass=RetainedPPO if arm=='retained' else EquilibriumPPO
    h=p['hyperparameters']
    model=klass('MultiInputPolicy',env,seed=seed,device='cpu',verbose=0,
        n_steps=64 if smoke else h['n_steps'],batch_size=32 if smoke else h['batch_size'],n_epochs=1 if smoke else h['n_epochs'],
        gamma=h['gamma'],gae_lambda=h['gae_lambda'],learning_rate=h['learning_rate'],
        policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=math.log(h['policy_std'])))
    copy_filtered_actor(model,foundation(p).actor,p['experiment'])
    return model

def anchor_arrays(p):
    path=ROOT/p['anchors']
    with np.load(path,allow_pickle=False) as data:
        observed={k:np.array(data[k],copy=True) for k in ('state','valid','age_s')};targets=data['target'].copy()
        if set(data['episode'].tolist())-set(p['anchor_seeds']):raise ValueError('anchor includes undeclared episode')
    return observed,targets

class NumericPredictor:
    def __init__(self,actor):self.backend=NumpyActorBackend(actor)
    def predict(self,observation,deterministic=True):return np.array([self.backend.predict_encoded(observation)/25.]),None

def evaluate(model,p,out,*,seconds,stress=False,seeds=None,numeric=False,checkpoint_sha256=None,protocol_sha256=None):
    for name,value in [('checkpoint_sha256',checkpoint_sha256),('protocol_sha256',protocol_sha256)]:
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('explicit '+name+' required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);(out/'traces').mkdir()
    selected=p['development_seeds'] if seeds is None else seeds
    if set(selected)&set(p['training_seeds']+p['anchor_seeds']):raise ValueError('evaluation/training seed overlap')
    scenarios=p['stress_scenarios'] if stress else p['stress_scenarios'][:1]
    results=[];before=model_weights_sha256(model);predictor=model
    if numeric:
        actor=export_actor(model,dict(experiment=p['experiment'],experiment_sha256=experiment_identity(p['experiment']),checkpoint_sha256=checkpoint_sha256,action_scale_m_s2=25.))
        write(out/'actor.json',actor);predictor=NumericPredictor(load_neural_policy(out/'actor.json',channels=rig_channels(angle_source='filtered')).actor)
    modes=[(module,module.training) for module in model.policy.modules()]
    try:
        with preserved_rng():
            for scenario in scenarios:
                experiment=deepcopy(p['experiment']);experiment['simulation_config']['max_steps']=round(seconds*100)
                experiment['observation_config'].update(scenario['upstream_overrides'])
                env=TrainingEnv(experiment,selected,reward_scale=.01)
                try:
                    for seed in selected:
                        for start in ('hanging','upright'):
                            result=_episode(predictor,env,seed=seed,start=start,scenario=dict(name=scenario['name'],expected='task_success',angle_offset_rad=0.),root=out)
                            results.append(result)
                finally:env.close()
    finally:
        for module,training in modes:module.training=training
    if model_weights_sha256(model)!=before:raise ValueError('evaluation changed model')
    summary=[]
    for scenario in scenarios:
        for start in ('hanging','upright'):
            rows=[r for r in results if r['scenario']==scenario['name'] and r['start']==start]
            captures=[r['first_one_second_capture_s'] for r in rows if r['first_one_second_capture_s'] is not None]
            summary.append(dict(scenario=scenario['name'],start=start,episodes=len(rows),holds=sum(r['hold_success'] for r in rows),
                faults=sum(r['fault_reason'] is not None for r in rows),captures=len(captures),
                mean_capture_s=float(np.mean(captures)) if captures else None,
                min_final_dwell_s=min(r['final_balance_dwell_s'] for r in rows),
                worst_max_x_m=max(r['max_abs_x_m'] for r in rows),
                episodes_with_rail_braking=sum(r['rail_braking_control_steps']>0 for r in rows)))
    result=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,seconds=seconds,seeds=selected,numeric=numeric,
        checkpoint_sha256=checkpoint_sha256,protocol_sha256=protocol_sha256,model_weights_sha256=before,
        experiment_sha256=experiment_identity(p['experiment']),adapter_sha256=digest(__file__),
        inference_scope='NumPy backend under TrainingEnv guards' if numeric else 'SB3 deterministic inference under TrainingEnv guards',
        actual_sdk_act_parity='Separate check_candidate path exercises normal NeuralPolicy.reset/act.',scenarios=scenarios,summary=summary,episodes=results)
    write(out/'report.json',result);return result

class Episodes(BaseCallback):
    def __init__(self,path):super().__init__();self.path=path
    def _on_step(self):
        for info in self.locals.get('infos',[]):
            if 'episode_result' in info:
                with self.path.open('a') as f:f.write(json.dumps(dict(timesteps=int(self.num_timesteps),**info['episode_result']),allow_nan=False)+'\n')
        return True

def train_one(path,output,*,arm,seed,budget='pilot',smoke=False):
    p=protocol(path);torch.set_num_threads(1);policy=foundation(p)
    out=Path(output);out.mkdir(parents=True,exist_ok=False);(out/'checkpoints').mkdir()
    exp=deepcopy(p['experiment'])
    if smoke:exp['simulation_config']['max_steps']=32
    env=TrainingEnv(exp,p['training_seeds'],reward_scale=.01)
    began=time.monotonic();model=model_for(p,arm,seed,env,smoke=smoke)
    model.set_logger(configure(str(out/'logs'),['csv']))
    obs,targets=anchor_arrays(p)
    migration=[]
    with preserved_rng():
        for start in ('hanging','upright'):
            o,_=env.reset(options=dict(episode_seed=p['training_seeds'][0],start=start))
            migration.append(abs(float(model.predict(o,deterministic=True)[0][0])*25.-policy.predict_encoded(o)))
    if max(migration)>1e-5:raise ValueError('filtered migration parity failed')
    if arm=='retained':model.configure_retention(obs,targets,**p['retention'])
    planned=p['budgets'][budget];steps=128 if smoke else planned['steps'];every=64 if smoke else planned['checkpoint_every']
    evaluations=[0,steps] if smoke else planned['evaluate_at']
    report=dict(status='DEVELOPMENT_ONLY',completed=False,hardware_accepted=False,protocol_sha256=digest(path),
        arm=arm,optimizer_seed=seed,budget=budget,actual_steps=steps,smoke=smoke,
        foundation_actor_content_sha256=policy.actor['content_sha256'],foundation_checkpoint_sha256=policy.actor['checkpoint_sha256'],
        migration_max_abs_raw_error_m_s2=max(migration),optimizer_resume=False,
        transfer='Only exact filtered actor weights copied; critic, optimizer and exploration freshly seeded.',
        evaluations=[],checkpoints=[],retention=model.retention_record() if arm=='retained' else None)
    write(out/'recipe.json',dict(protocol=p,arm=arm,seed=seed,budget=budget,smoke=smoke))
    try:
        for step in range(0,steps+1,every):
            if step:model.learn(total_timesteps=every,reset_num_timesteps=step==every,callback=Episodes(out/'training-episodes.jsonl'))
            protocol(path)
            cp=out/'checkpoints'/f'step-{step:09d}.zip';model.save(cp)
            row=dict(step=step,path=str(cp.relative_to(out)),sha256=digest(cp),actor_weights_sha256=actor_weights_hash(model),weights_sha256=model_weights_sha256(model))
            report['checkpoints'].append(row);atomic(out/'report.json',report)
            if step in evaluations:
                seconds=.05 if smoke else p['development_seconds']
                result=evaluate(model,p,out/f'eval-{step:09d}',seconds=seconds,seeds=p['smoke_seeds'] if smoke else None,checkpoint_sha256=row['sha256'],protocol_sha256=digest(path))
                report['evaluations'].append(dict(step=step,path=f'eval-{step:09d}/report.json',sha256=digest(out/f'eval-{step:09d}/report.json'),summary=result['summary']))
            model.logger.record('time/total_timesteps',int(model.num_timesteps));model.logger.dump(step=int(model.num_timesteps))
            atomic(out/'report.json',report)
            print(json.dumps(dict(arm=arm,seed=seed,step=step,summary=report['evaluations'][-1]['summary'] if step in evaluations else None)),flush=True)
        klass=RetainedPPO if arm=='retained' else EquilibriumPPO
        reloaded=klass.load(cp,device='cpu')
        if model_weights_sha256(reloaded)!=model_weights_sha256(model):raise ValueError('checkpoint roundtrip mismatch')
        if arm=='retained' and reloaded.retention_record()!=model.retention_record():raise ValueError('retention state lost on reload')
        parity=check_candidate(reloaded,p['experiment'],out/'final-emission-parity',checkpoint_sha256=digest(cp),seeds=p['smoke_seeds'] if smoke else p['development_seeds'][:2],seconds=.05 if smoke else 5.)
        if not parity['emission_parity_pass'] or parity['rejected_inputs']:raise ValueError('final emission parity failed')
        report.update(completed=True,wall_seconds=time.monotonic()-began,checkpoint_roundtrip=True,
            final_emission_parity=dict(passed=True,max_abs_raw_error_m_s2=parity['max_abs_raw_discrepancy_m_s2']),
            retention_diagnostics=model.retention_diagnostics if arm=='retained' else None,
            actor_changed_by_training=report['checkpoints'][0]['actor_weights_sha256']!=report['checkpoints'][-1]['actor_weights_sha256'])
        atomic(out/'report.json',report);return report
    except BaseException as exc:report.update(error=str(exc));atomic(out/'report.json',report);raise
    finally:env.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    t=sub.add_parser('train');t.add_argument('--protocol',type=Path,default=HERE/'protocol.json');t.add_argument('--output',type=Path,required=True)
    t.add_argument('--arm',choices=('ppo','retained'),required=True);t.add_argument('--seed',type=int,required=True);t.add_argument('--budget',choices=('pilot','long'),default='pilot');t.add_argument('--smoke',action='store_true')
    e=sub.add_parser('evaluate');e.add_argument('--protocol',type=Path,default=HERE/'protocol.json');e.add_argument('--run',type=Path,required=True);e.add_argument('--step',type=int,required=True);e.add_argument('--output',type=Path,required=True);e.add_argument('--confirmation',action='store_true');e.add_argument('--stress',action='store_true');e.add_argument('--numeric',action='store_true')
    args=parser.parse_args()
    if args.command=='train':train_one(args.protocol,args.output,arm=args.arm,seed=args.seed,budget=args.budget,smoke=args.smoke);return
    p=protocol(args.protocol);r=json.loads((args.run/'report.json').read_text())
    if not r['completed'] or r['protocol_sha256']!=digest(args.protocol):raise ValueError('incomplete or mismatched training run')
    cp=next(v for v in r['checkpoints'] if v['step']==args.step);path=args.run/cp['path']
    if digest(path)!=cp['sha256']:raise ValueError('checkpoint changed')
    klass=RetainedPPO if r['arm']=='retained' else EquilibriumPPO;model=klass.load(path,device='cpu');torch.set_num_threads(1)
    evaluate(model,p,args.output,seconds=60. if args.confirmation else 25.,stress=args.stress,
        seeds=p['confirmation_seeds'] if args.confirmation else p['development_seeds'],numeric=args.numeric,checkpoint_sha256=cp['sha256'],protocol_sha256=digest(args.protocol))
if __name__=='__main__':main()
