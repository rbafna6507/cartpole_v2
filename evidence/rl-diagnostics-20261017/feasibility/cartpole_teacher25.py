import json,math,time
from pathlib import Path
import numpy as np
from cartpole_sdk.learning.model_experiment import build_experiment
from cartpole_sdk.learning.ppo import TrainingEnv
from cartpole_sdk.policies import HostRatePolicy,HostPolicyParameters
ROOT=Path('/Users/rbafna/projects/cartpole_v2')
P=ROOT/'training/profiles/rl-encoder-20261017'
read=lambda name:json.loads((P/name).read_text())
exp=build_experiment(P/'model.json',executor_parameters=read('executor-parameters.json'),observation_config=read('observation-config.json'),prior_parameters=read('prior-parameters.json'),development_only=True,seconds=25.)
results=[]
for seed in (41000,41001,41002,41003):
 env=TrainingEnv(exp,[seed]);obs,_=env.reset(options={'episode_seed':seed,'start':'upright'})
 policy=HostRatePolicy(env.core.channels[:4],rate_hz=100,parameters=HostPolicyParameters(**exp['prior_parameters']));policy.reset(env.core.session)
 rows=[];pole_dwell=0.;longest_pole=0.;start=time.monotonic()
 while True:
  intent=policy.act(env.core.sdk_observation)
  if intent is None:raise RuntimeError(policy.fault_reason)
  obs,reward,t,tr,info=env.step([intent.acceleration_m_s2/env.action_scale])
  truth=env.core.ground_truth
  theta_ok=abs(truth.theta)<.15;omega_ok=abs(truth.omega)<1.;x_ok=abs(truth.x)<.12
  pole_dwell=pole_dwell+.01 if theta_ok and omega_ok else 0.
  longest_pole=max(longest_pole,pole_dwell)
  rows.append(dict(step=env.steps,t_s=env.steps/100.,x=truth.x,v=truth.v,theta=truth.theta,omega=truth.omega,raw=intent.acceleration_m_s2,executed=env.core.diagnostics.executed_acceleration_m_s2,observed_x=float(obs['state'][0]),theta_ok=theta_ok,omega_ok=omega_ok,x_ok=x_ok,strict_dwell=env.dwell,pole_dwell=pole_dwell))
  if t or tr:break
 summary=dict(**env.result(),wall_seconds=time.monotonic()-start,final_pole_only_dwell_s=pole_dwell,longest_pole_only_dwell_s=longest_pole)
 for label,values in [('all',rows),('last5s',rows[-500:])]:
  summary[label]=dict(steps=len(values),theta_violations=sum(not r['theta_ok'] for r in values),omega_violations=sum(not r['omega_ok'] for r in values),x_violations=sum(not r['x_ok'] for r in values),strict_violations=sum(not(r['theta_ok'] and r['omega_ok'] and r['x_ok']) for r in values),max_abs_x=max(abs(r['x']) for r in values),max_abs_theta=max(abs(r['theta']) for r in values),max_abs_omega=max(abs(r['omega']) for r in values),x_min=min(r['x'] for r in values),x_max=max(r['x'] for r in values))
 summary['first_violation']=next((r for r in rows if not(r['theta_ok'] and r['omega_ok'] and r['x_ok'])),None)
 summary['boundary_crossings']=[dict(step=r['step'],t_s=r['t_s'],x=r['x'],v=r['v'],theta=r['theta'],omega=r['omega'],entering_valid=r['x_ok']) for i,r in enumerate(rows) if i>0 and rows[i-1]['x_ok']!=r['x_ok']]
 results.append(dict(summary=summary,trajectory=rows));env.close()
 print(json.dumps(summary),flush=True)
Path('/tmp/cartpole_teacher25.json').write_text(json.dumps(dict(source_commit='bb032fc957d754fab93502791cb0638a023aed6f',experiment=exp,episodes=results),indent=2))
