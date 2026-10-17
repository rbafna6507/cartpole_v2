import json, math, time
from pathlib import Path
from dataclasses import asdict
import numpy as np
from cartpole_sdk.learning.model_experiment import build_experiment, validate_experiment
from cartpole_sdk.learning.ppo import TrainingEnv
from cartpole_sdk.policies import HostRatePolicy, HostPolicyParameters
ROOT=Path('/Users/rbafna/projects/cartpole_v2')
P=ROOT/'training/profiles/rl-encoder-20261017'
read=lambda name: json.loads((P/name).read_text())
exp=build_experiment(P/'model.json',executor_parameters=read('executor-parameters.json'),observation_config=read('observation-config.json'),prior_parameters=read('prior-parameters.json'),development_only=True,seconds=10.)
config,parameters,observations,prior=validate_experiment(exp)
print(json.dumps({'config':asdict(config),'parameters':asdict(parameters),'observations':asdict(observations)}),flush=True)
# State ordered x, v, theta, omega; theta positive toward positive x.
L=config.effective_length_m
I=.75*config.pole_mass_kg*L*L
c=config.hinge_damping/I
A=np.array([[0,1,0,0],[0,0,0,0],[0,0,0,1],[0,0,9.81/L,-c]])
B=np.array([[0],[1],[0],[-1/L]])
Q=np.diag([20.,1.,10.,1.])
R=np.array([[.1]])
M=np.zeros((5,5)); M[:4,:4]=A; M[:4,4:]=B
Md=np.eye(5); term=np.eye(5)
for j in range(1,30):
 term=term@(M*.01)/j
 Md+=term
Ad,Bd=Md[:4,:4],Md[:4,4:]
Pq=Q.copy()
for _ in range(10000):
 K=np.linalg.solve(R+Bd.T@Pq@Bd,Bd.T@Pq@Ad)
 Pnew=Q+Ad.T@Pq@Ad-Ad.T@Pq@Bd@K
 if np.max(np.abs(Pnew-Pq))<1e-10: break
 Pq=Pnew
print('LQR_K',K.tolist(),flush=True)
results=[]
for name in ('host_prior','observed_lqr'):
 for seed in (21001,21002,21003,21004):
  for start in ('upright','hanging'):
   if name=='observed_lqr' and start=='hanging': continue
   env=TrainingEnv(exp,[seed])
   obs,info=env.reset(options={'episode_seed':seed,'start':start})
   policy=HostRatePolicy(env.core.channels[:4],rate_hz=100,parameters=prior)
   policy.reset(env.core.session)
   stats=[]
   began=time.monotonic()
   while True:
    if name=='host_prior':
     intent=policy.act(env.core.sdk_observation)
     if intent is None: raise RuntimeError(policy.fault_reason)
     raw=intent.acceleration_m_s2
    else:
     x,v,s,c,w,a,b=obs['state']
     raw=float((-K@np.array([x,v,math.atan2(s,c),w]))[0])
     raw=float(np.clip(raw,-env.action_scale,env.action_scale))
    obs,r,t,tr,info=env.step([raw/env.action_scale])
    truth=env.core.ground_truth
    stats.append([*obs['state'],truth.theta,truth.omega,raw,env.core.diagnostics.executed_acceleration_m_s2])
    if t or tr: break
   result=dict(controller=name,**env.result(),wall_seconds=time.monotonic()-began)
   result['feature_abs_max']=np.max(np.abs(stats),axis=0).tolist()
   results.append(result)
   print(json.dumps(result),flush=True)
   env.close()
Path('/tmp/cartpole_feasibility_audit.json').write_text(json.dumps({'experiment':exp,'K':K.tolist(),'episodes':results},indent=2))
