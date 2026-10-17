#!/usr/bin/env python3
"""Offline supervised balance-law diagnostic, not an RL or deployment claim.

Run via uv run --extra rl python THIS --profile ... --output NEW --seed 3.
The teacher is the existing host balance linear feedback, sampled on synthetic
local observed states. It is never called during neural-policy evaluation.
"""
import argparse,json,math,time
from hashlib import sha256
from pathlib import Path
import numpy as np
import torch
from stable_baselines3 import PPO
from cartpole_sdk.learning.diagnostics import DiagnosticEnv,evaluate_model,preserved_rng,diagnostic_provenance
from cartpole_sdk.learning.model_experiment import build_experiment,read_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--profile',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--seed',type=int,required=True)
p.add_argument('--updates',type=int,default=1500)
a=p.parse_args()
if a.updates<1 or a.seed<0: p.error('positive updates and nonnegative seed required')
a.output.mkdir(parents=True,exist_ok=False)
read=lambda name:read_json(a.profile/(name+'.json'))[0]
exp=build_experiment(a.profile/'model.json',executor_parameters=read('executor-parameters'),
 observation_config=read('observation-config'),prior_parameters=read('prior-parameters'),development_only=True,seconds=5.)
prior=exp['prior_parameters']
recipe=dict(schema='cartpole-supervised-balance-probe-v1',algorithm='supervised imitation of existing balance law',seed=a.seed,
 updates=a.updates,train_samples=8192,validation_samples=4096,batch_size=512,adam_lr=.001,initial_policy_std=.05,
 training_bounds=dict(x=[-.12,.12],v=[-.3,.3],theta=[-.25,.25],omega=[-2,2],acceleration=[-3,3]),
 teacher_gains={k:prior[k] for k in ('position_gain','velocity_gain','theta_gain','omega_gain')},
 evaluation_role='Development after first inspection; reused longer poses are regression, not fresh confirmation.',
 development_seeds=[40000,40001],longer_evaluation_seeds=[41000,41001,41002,41003],longer_evaluation_seconds=25,
 experiment=exp,provenance=diagnostic_provenance(),script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
 hardware_accepted=False,deployable=False,note='Teacher labels use observed state, never simulator truth. No hardware, swing-up teacher or on-policy RL update.')
(a.output/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
torch.set_num_threads(1)
env=DiagnosticEnv(exp,tuple(range(10000,10128)),variant='upright-lowstd')
model=PPO('MultiInputPolicy',env,seed=a.seed,device='cpu',verbose=0,n_steps=1024,batch_size=64,n_epochs=10,
 gamma=.999,gae_lambda=.98,learning_rate=.0003,policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=math.log(.05)))
def dataset(n,seed):
 rng=np.random.default_rng(seed)
 q=rng.uniform([-0.12,-.3,-.25,-2,-3],[.12,.3,.25,2,3],size=(n,5))
 x,v,t,w,acc=q.T
 state=np.stack((x,v,np.sin(t),np.cos(t),w,acc,np.zeros(n)),axis=1)
 target=(prior['position_gain']*x+prior['velocity_gain']*v+prior['theta_gain']*t+prior['omega_gain']*w)/env.action_scale
 obs=dict(state=torch.tensor(state,dtype=torch.float32),valid=torch.ones((n,7)),age_s=torch.zeros((n,7)))
 return obs,torch.tensor(target[:,None],dtype=torch.float32)
train,y=dataset(8192,50000)
valid,vy=dataset(4096,50001)
trace=[]
began=time.monotonic()
try:
 # A fixed seed/data split across network initializations. Only actor gradients.
 optimizer=torch.optim.Adam(list(model.policy.mlp_extractor.policy_net.parameters())+list(model.policy.action_net.parameters()),lr=.001)
 with preserved_rng():
  generator=torch.Generator().manual_seed(50002)
  for step in range(a.updates):
   indices=torch.randint(len(y),(512,),generator=generator)
   observations={k:v[indices] for k,v in train.items()}
   mean=model.policy.get_distribution(observations).distribution.mean
   loss=((mean-y[indices])*env.action_scale).square().mean()
   optimizer.zero_grad();loss.backward();optimizer.step()
   if step%100==0 or step==a.updates-1:
    with torch.no_grad():
     error=(model.policy.get_distribution(valid).distribution.mean-vy)*env.action_scale
     trace.append(dict(update=step+1,train_raw_mse=float(loss.item()),validation_raw_rmse=float(error.square().mean().sqrt().item())))
 model.save(a.output/'imitation-checkpoint.zip')
 print(json.dumps(dict(seed=a.seed,fit=trace[-1])),flush=True)
 report=dict(recipe,fit_trace=trace,fit_wall_seconds=time.monotonic()-began)
 report['development']=evaluate_model(model,exp,variant='upright-lowstd',seeds=(40000,40001),seconds=10.,traces=True)
 print(json.dumps(dict(seed=a.seed,development=report['development']['by_start'])),flush=True)
 report['longer_evaluation']=evaluate_model(model,exp,variant='upright-lowstd',seeds=(41000,41001,41002,41003),seconds=25.,traces=True)
 report['wall_seconds']=time.monotonic()-began
 report['checkpoint_sha256']=sha256((a.output/'imitation-checkpoint.zip').read_bytes()).hexdigest()
 (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 print(json.dumps(dict(seed=a.seed,longer_evaluation=report['longer_evaluation']['by_start'])),flush=True)
finally:env.close()
