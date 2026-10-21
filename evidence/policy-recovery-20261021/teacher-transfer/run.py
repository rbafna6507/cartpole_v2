#!/usr/bin/env python3
"""One bounded transfer of actual filtered BAL feedback; supervised, zero PPO."""
import argparse
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
import json,math
from pathlib import Path
import zipfile
import numpy as np
import torch
from cartpole_sdk.contracts import Sample,Observation,Session,UNITS
from cartpole_sdk.control.parameters import ControllerParameters,gains
from cartpole_sdk.control.reference import balance
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels,encode_rig_observation,select_rig_observation
from cartpole_sdk.learning.balance_experiment import fit_teacher,source_identity
from cartpole_sdk.learning.candidate_parity import check_candidate,model_weights_sha256
from cartpole_sdk.learning.diagnostics import DiagnosticEnv,_source_snapshot
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.learning.projected_ppo import EquilibriumPPO,equilibrium_observation
from cartpole_sdk.learning.rollout import initial_state
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BASE=ROOT/'runs/policy-confidence-20261021/balance/teacher-seed47'
HISTORY=ROOT/'runs/console-policy-learning-20261021/matrix-01'
CANDIDATE=ROOT/'training/candidates/balance-recovery-20261021'
SEEDS=(94000,94007);BIASES=(0.,-.25,.25)
def digest(path):return sha256(path.read_bytes()).hexdigest()
def write(path,value):
 with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def coefficients(parameters,upright=True):
 g=gains(parameters,upright=upright)
 return dict(position_gain=-g.k3,velocity_gain=-g.k4,theta_gain=-g.k1,omega_gain=-g.k2)
def target(state,k):
 x,v,s,c,w,_,_=state
 return float(np.clip(k['position_gain']*x+k['velocity_gain']*v+k['theta_gain']*math.atan2(s,c)+k['omega_gain']*w,-25.,25.))
def law_audit(experiment,k):
 parameters=ControllerParameters(**experiment['executor_parameters']);channels=rig_channels(angle_source='filtered');raw=rig_channels()[2]
 def obs(q,seq):
  t=seq*10000000;values=(q[0],q[1],q[2],q[3],q[4],0.)
  samples=tuple(Sample(c.entity,c.quantity,c.source,float(value),UNITS[c.quantity],c.frame_id,'audit','valid',None,'estimated',t,t,t) for c,value in zip(channels,values))
  samples+=(Sample('pole','angle',raw.source,float(q[2]),'rad',raw.frame_id,'audit','valid',None,'measured',t,t,t),)
  return Observation('audit','clock',seq,t,'audit',samples)
 maximum=0.;n=1024;rng=np.random.default_rng(97200)
 for q in rng.uniform([-.12,-.3,-.25,-2.,-3.],[.12,.3,.25,2.,3.],(n,5)):
  policy=ExecutorFeedbackPolicy(channels,parameters=parameters,start_mode='bal',rate_hz=100,raw_angle_channel=raw);policy.reset(Session('audit','clock'))
  assert policy.act(obs([0.]*5,0)) is not None
  observation=obs(q,1);intent=policy.act(observation);assert intent is not None,policy.fault_reason
  state=encode_rig_observation(observation,channels)['state'];maximum=max(maximum,abs(intent.acceleration_m_s2-target(state,k)))
 assert maximum<1e-10
 return dict(points=n,seed=97200,reference='actual ExecutorFeedbackPolicy.start_mode=bal at100Hz, filtered channel, raw safety channel, zero start then random bounded state',max_raw_difference_m_s2=maximum,
  domain=dict(x=[-.12,.12],v=[-.3,.3],theta=[-.25,.25],omega=[-2.,2.],a=[-3.,3.],brake=0),
  scope='Within this bounded domain speed/rail/angle guards do not alter the raw BAL demand. Neural transfer is the balance feedback, not native state machine, return, or1kHz timing.')
def linearization(experiment,k):
 c=experiment['simulation_config'];p=experiment['executor_parameters'];L=c['effective_length_m'];I=.75*c['pole_mass_kg']*L*L
 friction=(c['hinge_damping']+c['hinge_coulomb_friction_nm']/c['hinge_friction_velocity_scale_rad_s'])/I;w=2*math.pi*p['bw']
 a=np.array([k['position_gain'],k['velocity_gain'],0.,0.,k['theta_gain'],k['omega_gain']]);A=np.zeros((6,6))
 A[0,1]=1;A[1]=a;A[2,3]=1;A[3]=-a/L;A[3,2]+=9.81/L;A[3,3]-=friction;A[4]=[0,0,2*w,0,-2*w,1];A[5]=[0,0,w*w,0,-w*w,0]
 eig=np.linalg.eigvals(A)
 return dict(states=['x','v','theta','omega','angle_hat','rate_hat'],matrix=A.tolist(),eigenvalues=[dict(real=float(v.real),imag=float(v.imag)) for v in eig],max_real=float(max(v.real for v in eig)),
  hinge_viscous_nm_per_rad_s=c['hinge_damping'],hinge_coulomb_nm=c['hinge_coulomb_friction_nm'],tanh_width_rad_s=c['hinge_friction_velocity_scale_rad_s'],pivot_inertia_kg_m2=I,local_angular_damping_per_s=friction,
  scope='Continuous local ideal acceleration model + actual filtered observer; nonlinear governed sim follows. Quantization/jerk/delay omitted here. Free-swing-fitted friction near upright remains unvalidated.')
def declare():
 base=json.loads((BASE/'recipe.json').read_text());exp=deepcopy(base['experiment']);exp['observation_config']['angle_source']='filtered'
 p=ControllerParameters(**exp['executor_parameters']);k=coefficients(p)
 assert not CANDIDATE.exists()
 sources=source_identity();_source_snapshot(HERE/'source.zip')
 extra=['src/cartpole_sdk/policies/executor_feedback.py','firmware/teensy_executor/swing_controller.h','firmware/teensy_executor/teensy_executor.ino']
 with zipfile.ZipFile(HERE/'source.zip','a',zipfile.ZIP_DEFLATED) as archive:
  archive.write(Path(__file__),'teacher-transfer/run.py')
  for name in extra:archive.write(ROOT/name,'teacher-transfer-reference/'+name)
 protocol=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,simulation_only=True,label='Supervised approximation of actual filtered BAL feedback; zero PPO updates; hardware diagnostic research candidate, no qualification.',
  teacher=dict(mode='bal',upright=True,gains=k,auto_gains_for_comparison=coefficients(p,False),angle_source='filtered',rate_hz=100,observer_bandwidth_hz=p.bw),
  experiment=exp,base_recipe_sha256=digest(BASE/'recipe.json'),source=sources,source_zip_sha256=digest(HERE/'source.zip'),script_sha256=digest(Path(__file__)),
  reference_source_sha256={name:digest(ROOT/name) for name in extra},history=dict(recipe_sha256=digest(HISTORY/'recipe.json'),report_sha256=digest(HISTORY/'report.json'),
   finding='Prior native-MLP17 used gains(parameters) default upright=False/AUTO pw3, not BAL bal_pw4.5. All8 raw and all8 filtered MLP trials failed final holds. It is not repeated here.'),
  fit=dict(seed=47,updates=1500,samples=8192,validation_samples=4096,train_seed=51000,validation_seed=51001,minibatch_seed=51002,routine='existing fit_teacher + once project_equilibrium',architecture=[21,64,64,1],ppo_updates=0),
  development=dict(seeds=list(SEEDS),seconds=10.,bias_degrees=list(BIASES),arms=['analytic_BAL_filtered','MLP_BAL_filtered'],episodes=12),
  numerical_gates=dict(heldout_raw_rmse_m_s2=.1,heldout_max_abs_error_m_s2=.5,local_gain_relative_error=.1,emission_parity_m_s2=1e-5,numpy_parity_m_s2=1e-5),
  task_gate_policy='Simulated holds are reported, not a promotion gate: parent explicitly authorized research export despite failures when the unchanged model disagrees with the actual controller, only if imitation and runtime parity pass. No simulated or hardware qualification claim.',
  candidate_path=str(CANDIDATE),workers=1,torch_threads=1,
  limitations=['BAL feedback transfer does not reproduce native1kHz timing; first test uses existing100Hz runtime contract.',
   'No physical fit changes. Existing passive friction model predicts local instability for actual BAL feedback; simulation mismatch is retained.',
   'Development poses are previously inspected; no fresh held-out qualification or PPO improvement claim.',
   'Raw safety guard and filtered hardware wrapper integration belong to parent; no dirty console/runtime files edited here.'])
 write(HERE/'protocol.json',protocol);write(HERE/'teacher-law-audit.json',law_audit(exp,k));write(HERE/'linearization.json',linearization(exp,k))
 print(json.dumps(dict(protocol_sha256=digest(HERE/'protocol.json'),gains=k,teacher_law_audit=json.loads((HERE/'teacher-law-audit.json').read_text()),max_local_real=json.loads((HERE/'linearization.json').read_text())['max_real']),indent=2))
def approximation(model,k):
 rng=np.random.default_rng(97201);q=rng.uniform([-.12,-.3,-.25,-2.,-3.],[.12,.3,.25,2.,3.],(4096,5));x,v,t,w,a=q.T
 states=np.stack((x,v,np.sin(t),np.cos(t),w,a,np.zeros(len(q))),axis=1);obs=dict(state=states,valid=np.ones_like(states),age_s=rng.uniform(0.,.02,states.shape))
 predicted,_=model.predict(obs,deterministic=True);expected=np.array([target(s,k) for s in states]);errors=predicted[:,0].astype(float)*25.-expected
 base=equilibrium_observation();local={};expected_slopes=dict(x=k['position_gain'],v=k['velocity_gain'],theta=k['theta_gain'],omega=k['omega_gain'])
 for name,index in [('x',0),('v',1),('theta',2),('omega',4),('acceleration',5)]:
  plus={key:val.copy() for key,val in base.items()};minus={key:val.copy() for key,val in base.items()};eps=1e-3
  if name=='theta':plus['state'][2:4]=[math.sin(eps),math.cos(eps)];minus['state'][2:4]=[-math.sin(eps),math.cos(eps)]
  else:plus['state'][index]=eps;minus['state'][index]=-eps
  local[name]=(float(model.predict(plus,deterministic=True)[0][0])-float(model.predict(minus,deterministic=True)[0][0]))*25/(2*eps)
 relative={key:abs(local[key]-value)/abs(value) for key,value in expected_slopes.items()}
 return dict(seed=97201,points=4096,raw_rmse_m_s2=float(np.sqrt(np.mean(errors**2))),max_abs_raw_error_m_s2=float(np.max(np.abs(errors))),local_raw_slopes=local,expected_local_raw_slopes=expected_slopes,local_gain_relative_errors=relative)
def episode(model,protocol,arm,seed,bias):
 exp=protocol['experiment'];config,p,obs,_=validate_experiment(exp);config=replace(config,max_steps=1000);obs=replace(obs,encoder_bias_rad=math.radians(bias))
 env=RigCartpoleEnv(config,parameters=p,observation_config=obs,ttl_ms=exp['ttl_ms']);path=HERE/'traces'/f'{arm}-bias{bias:+.2f}-seed{seed}.jsonl';path.parent.mkdir(exist_ok=True)
 try:
  initial=initial_state(seed,'upright');encoded,_=env.reset(seed=seed,options={'state':initial});reset_ns=env.ground_truth.time_ns
  k=protocol['teacher']['gains'];records=[];dwell=0.;fault=None;maxx=abs(initial[0]);disagreement=[]
  with path.open('x') as stream:
   while not(env.terminated or env.truncated):
    select_rig_observation(env.sdk_observation,env.channels,contract=env.observation_contract);observed=encode_rig_observation(env.sdk_observation,env.channels)
    teacher=target(observed['state'],k);raw=teacher if arm=='analytic_BAL_filtered' else float(model.predict(encoded,deterministic=True)[0][0])*25.
    before=env.ground_truth.time_ns;encoded,_,_,_,_=env.step([raw]);truth=asdict(env.ground_truth);t=(env.ground_truth.time_ns-reset_ns)/1e9
    balanced=abs(truth['x'])<.12 and abs(truth['theta'])<.15 and abs(truth['omega'])<1;dwell=dwell+(env.ground_truth.time_ns-before)/1e9 if balanced else 0.
    row=dict(t=t,observed=observed,truth=truth,raw_command_m_s2=raw,analytic_BAL_on_same_observation_m_s2=teacher,executed_acceleration_m_s2=env.diagnostics.executed_acceleration_m_s2,
     rail_braking=env.diagnostics.rail_braking,balanced=balanced,fault=env.fault_reason)
    records.append(row);disagreement.append(raw-teacher);maxx=max(maxx,abs(truth['x']));stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
  complete=len(records)==1000 and env.fault_reason is None;tail=records[-500:] if complete else []
  return dict(arm=arm,seed=seed,bias_degrees=bias,literal_initial_state=list(initial),reset_warmup_ns=reset_ns,steps=len(records),fault=env.fault_reason,full_horizon_complete=complete,
   hold_success=bool(complete and dwell>=5.-1e-9),final_balance_dwell_s=dwell,max_abs_x_m=maxx,
   final_window_x_rms_m=float(np.sqrt(np.mean([r['truth']['x']**2 for r in tail]))) if tail else None,
   final_window_theta_rms_rad=float(np.sqrt(np.mean([r['truth']['theta']**2 for r in tail]))) if tail else None,
   first_angle_over5deg_s=next((r['t'] for r in records if abs(r['truth']['theta'])>math.radians(5)),None),
   teacher_disagreement_raw_rmse_m_s2=float(np.sqrt(np.mean(np.square(disagreement)))),teacher_disagreement_max_abs_m_s2=float(max(map(abs,disagreement))),
   trace_path=str(path.relative_to(HERE)),trace_sha256=digest(path))
 finally:env.close()
def run():
 protocol=json.loads((HERE/'protocol.json').read_text());assert digest(Path(__file__))==protocol['script_sha256'] and source_identity()==protocol['source']
 torch.set_num_threads(1);exp=protocol['experiment'];k=protocol['teacher']['gains'];env=DiagnosticEnv(exp,tuple(range(12000,12128)),variant='upright')
 try:
  model=EquilibriumPPO('MultiInputPolicy',env,seed=47,device='cpu',verbose=0,n_steps=1024,batch_size=64,n_epochs=10,gamma=.999,gae_lambda=.98,learning_rate=3e-6,
   policy_kwargs=dict(net_arch=dict(pi=[64,64],vf=[64,64]),activation_fn=torch.nn.Tanh,log_std_init=math.log(.02)))
  before={key:value.detach().clone() for key,value in model.policy.state_dict().items()};fit=fit_teacher(model,k,25.,updates=1500,samples=8192);projection=model.project_equilibrium()
  assert all(torch.equal(value,before[name]) for name,value in model.policy.state_dict().items() if not name.startswith(('mlp_extractor.policy_net.','action_net.')))
  assert model.num_timesteps==0 and model._n_updates==0
  checkpoint=HERE/'bal-filtered-supervised-seed47.zip';model.save(checkpoint);weights=model_weights_sha256(model);errors=approximation(model,k)
  numeric_gate=errors['raw_rmse_m_s2']<=.1 and errors['max_abs_raw_error_m_s2']<=.5 and max(errors['local_gain_relative_errors'].values())<=.1
  write(HERE/'fit-report.json',dict(status='DEVELOPMENT_ONLY',label=protocol['label'],fit=fit,projection_normalized=projection,approximation=errors,numerical_imitation_gate_pass=numeric_gate,
   checkpoint_sha256=digest(checkpoint),model_weights_sha256=weights,critic_std_unchanged=True,ppo_updates=0,environment_training_steps=0))
  print(json.dumps(dict(fit_complete=True,imitation_gate=numeric_gate,approximation=errors,checkpoint_sha256=digest(checkpoint))),flush=True)
  rows=[]
  for bias in BIASES:
   for seed in SEEDS:
    for arm in protocol['development']['arms']:
     row=episode(model,protocol,arm,seed,bias);rows.append(row);print(json.dumps({key:row[key] for key in ('arm','seed','bias_degrees','hold_success','max_abs_x_m','teacher_disagreement_raw_rmse_m_s2')}),flush=True)
  summaries=[dict(arm=arm,bias_degrees=bias,holds=sum(r['hold_success'] for r in rows if r['arm']==arm and r['bias_degrees']==bias),episodes=2,
   faults=sum(r['fault'] is not None for r in rows if r['arm']==arm and r['bias_degrees']==bias)) for bias in BIASES for arm in protocol['development']['arms']]
  write(HERE/'simulation-report.json',dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,summaries=summaries,episodes=rows))
  assert model_weights_sha256(model)==weights and source_identity()==protocol['source']
  if not numeric_gate:
   write(HERE/'final-report.json',dict(exported=False,reason='Predeclared numerical imitation gate failed',simulation_summary=summaries));return
  parity=check_candidate(model,exp,HERE/'emission-parity',checkpoint_sha256=digest(checkpoint),seeds=SEEDS,seconds=5.)
  assert parity['emission_parity_pass'] and not parity['rejected_inputs']
  actorpath=HERE/'emission-parity/actor.json';policy=load_neural_policy(actorpath,channels=rig_channels(angle_source='filtered'));backend=NumpyActorBackend(policy.actor);maxerr=0.;count=0
  for e in parity['episodes']:
   for line in (HERE/'emission-parity'/e['trace_path']).open():
    record=json.loads(line);o=record['encoded_observation'];maxerr=max(maxerr,abs(policy.predict_encoded(o)-backend.predict_encoded(o)));count+=1
  assert maxerr<=1e-5 and source_identity()==protocol['source'] and model_weights_sha256(model)==weights
  final=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,simulation_only=True,exported=True,research_candidate_only=True,label=protocol['label'],
   protocol_sha256=digest(HERE/'protocol.json'),source_zip_sha256=digest(HERE/'source.zip'),teacher_law_audit_sha256=digest(HERE/'teacher-law-audit.json'),
   fit_report_sha256=digest(HERE/'fit-report.json'),simulation_report_sha256=digest(HERE/'simulation-report.json'),linearization_sha256=digest(HERE/'linearization.json'),
   checkpoint_path=str(checkpoint),checkpoint_sha256=digest(checkpoint),model_weights_sha256=weights,actor_file_sha256=digest(actorpath),actor_content_sha256=policy.actor['content_sha256'],
   candidate_path=str(CANDIDATE/'actor.json'),observation_contract=policy.observation_contract,ppo_updates=0,environment_training_steps=0,
   simulation_summary=summaries,simulation_failures_retained=True,simulator_task_qualified=False,numerical_imitation_gate_pass=numeric_gate,
   emission_parity_report_sha256=digest(HERE/'emission-parity/report.json'),emission_max_raw_difference_m_s2=parity['max_abs_raw_discrepancy_m_s2'],
   numpy_parity=dict(observations=count,max_abs_raw_difference_m_s2=maxerr,passed=True),source_identity_unchanged=True,limitations=protocol['limitations'])
  CANDIDATE.mkdir(parents=True,exist_ok=False)
  with (CANDIDATE/'actor.json').open('xb') as f:f.write(actorpath.read_bytes())
  load_neural_policy(CANDIDATE/'actor.json',channels=rig_channels(angle_source='filtered'))
  write(HERE/'final-report.json',final);write(CANDIDATE/'receipt.json',dict(final,evidence_report_sha256=digest(HERE/'final-report.json')))
  print(json.dumps(final,indent=2),flush=True)
 finally:env.close()
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('declare','run'));args=parser.parse_args();declare() if args.mode=='declare' else run()
