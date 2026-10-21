#!/usr/bin/env python3
"""Recheck frozen BAL transfer traces/checkpoint; no new training or episodes."""
from hashlib import sha256
from pathlib import Path
import json,math
import torch
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_experiment import source_identity
from cartpole_sdk.learning.candidate_parity import model_weights_sha256
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels
P=Path(__file__).resolve().parent
digest=lambda p:sha256(p.read_bytes()).hexdigest()
protocol=json.loads((P/'protocol.json').read_text());report=json.loads((P/'final-report.json').read_text());sim=json.loads((P/'simulation-report.json').read_text())
assert source_identity()==protocol['source']
assert digest(P/'run.py')==protocol['script_sha256']
assert digest(P/'source.zip')==protocol['source_zip_sha256']==report['source_zip_sha256']
for key,path in [('protocol','protocol.json'),('teacher_law_audit','teacher-law-audit.json'),('fit_report','fit-report.json'),('simulation_report','simulation-report.json'),('linearization','linearization.json')]:
 assert digest(P/path)==report[key+'_sha256']
checkpoint=Path(report['checkpoint_path']);assert digest(checkpoint)==report['checkpoint_sha256']
torch.set_num_threads(1);model=EquilibriumPPO.load(checkpoint,device='cpu')
assert model.num_timesteps==0 and model._n_updates==0 and not model.policy.optimizer.state_dict()['state']
assert model_weights_sha256(model)==report['model_weights_sha256']
actor=Path(report['candidate_path']);assert digest(actor)==report['actor_file_sha256']
policy=load_neural_policy(actor,channels=rig_channels(angle_source='filtered'));numeric=NumpyActorBackend(policy.actor)
assert policy.actor['content_sha256']==report['actor_content_sha256']
try:load_neural_policy(actor,channels=rig_channels(angle_source='raw'))
except ValidationError:raw_rejected=True
else:raise AssertionError('filtered actor unexpectedly accepted raw channels')
k=protocol['teacher']['gains'];count=0;mlp_count=0;maxerr=0.;holds=0
for episode in sim['episodes']:
 trace=P/episode['trace_path'];assert digest(trace)==episode['trace_sha256'];rows=[json.loads(l) for l in trace.open()];assert len(rows)==1000
 assert all(r['fault'] is None for r in rows)
 for r in rows:
  x,v,s,c,w,_,_=r['observed']['state'];teacher=max(-25.,min(25.,k['position_gain']*x+k['velocity_gain']*v+k['theta_gain']*math.atan2(s,c)+k['omega_gain']*w))
  assert abs(teacher-r['analytic_BAL_on_same_observation_m_s2'])<1e-12
  if episode['arm']=='MLP_BAL_filtered':maxerr=max(maxerr,abs(numeric.predict_encoded(r['observed'])-r['raw_command_m_s2']));mlp_count+=1
  else:assert teacher==r['raw_command_m_s2']
  truth=r['truth'];assert r['balanced']==(abs(truth['x'])<.12 and abs(truth['theta'])<.15 and abs(truth['omega'])<1)
  count+=1
 assert all(r['balanced'] for r in rows[-500:]) and episode['hold_success'];holds+=1
assert maxerr<=1e-5
result=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,completed=True,episodes=holds,commands_rechecked=count,mlp_commands_replayed=mlp_count,
 max_numpy_vs_saved_model_raw_difference_m_s2=maxerr,strict_filtered_loader_pass=True,raw_channel_mismatch_rejected=raw_rejected,
 checkpoint_ppo_steps=model.num_timesteps,checkpoint_ppo_updates=model._n_updates,ppo_optimizer_state_empty=True,
 source_and_actor_hashes_unchanged=True,all_trace_hashes_verified=True,all_final_hold_windows_verified=True,
 model_caveat='Local linearization unstable; all bounded nonlinear development runs meet final hold tolerance. No asymptotic stability or hardware qualification claim.',
 final_report_sha256=digest(P/'final-report.json'),verification_script_sha256=digest(Path(__file__)))
with (P/'verification.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps(result,indent=2))
for arm in protocol['development']['arms']:
 rows=[r for r in sim['episodes'] if r['arm']==arm]
 print(json.dumps(dict(arm=arm,worst_tail_x_rms_m=max(r['final_window_x_rms_m'] for r in rows),worst_tail_theta_rms_deg=math.degrees(max(r['final_window_theta_rms_rad'] for r in rows)),worst_max_x_m=max(r['max_abs_x_m'] for r in rows))))
