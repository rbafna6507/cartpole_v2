#!/usr/bin/env python3
"""Bounded frozen-actor simulation diagnosis; unchanged physical model and source."""
from dataclasses import asdict,replace
from hashlib import sha256
import argparse,json,math
from pathlib import Path
import numpy as np
from cartpole_sdk.learning.balance_experiment import source_identity
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import encode_rig_observation
from cartpole_sdk.sim.rig_gym_env import RigCartpoleEnv
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LIVE=ROOT/'runs/policy-confidence-20261021/hardware-live/centered-run25-rr10-01'
CENTER=HERE.parent/'centered-initialization'
BASE=ROOT/'runs/policy-confidence-20261021/balance/teacher-seed47'
SEEDS=(94000,94007)
def digest(path):return sha256(path.read_bytes()).hexdigest()
def write_new(path,value):
 with path.open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
def declare():
 hardware=json.loads((LIVE/'report.json').read_text());base=json.loads((BASE/'recipe.json').read_text());center=json.loads((CENTER/'final-report.json').read_text())
 assert source_identity()==base['provenance']
 bias=(hardware['before_info']['encoder_raw']-hardware['before_info']['encoder_upright_raw'])*2*math.pi/4096
 actors=[]
 for name,directory,checkpoint in [('centered','balance-20261021-centered',Path(center['checkpoint_path'])),('original47','balance-20261021-confidence',BASE/'checkpoints/step-000020480.zip')]:
  path=ROOT/'training/candidates'/directory/'actor.json';actor=json.loads(path.read_text());assert actor['checkpoint_sha256']==digest(checkpoint)
  actors.append(dict(name=name,path=str(path),file_sha256=digest(path),content_sha256=actor['content_sha256'],checkpoint_path=str(checkpoint),checkpoint_sha256=digest(checkpoint)))
 cases=[dict(name='true_upright_zero_bias',initial_state=[0.,0.,0.,0.],encoder_bias_rad=0.),
        dict(name='true_upright_plus9counts_bias',initial_state=[0.,0.,0.,0.],encoder_bias_rad=bias),
        dict(name='observed_angle_is_true_tilt',initial_state=[0.,0.,hardware['before_state']['theta'],hardware['before_state']['omega']],encoder_bias_rad=0.)]
 protocol=dict(status='DEVELOPMENT_ONLY',simulation_only=True,hardware_accepted=False,deployable=False,
  hypothesis='Does the unchanged model predict the observed subsecond growing angle oscillation under a +9-count reference-bias hypothesis or an equivalent real-tilt hypothesis?',
  actors=actors,cases=cases,seeds=list(SEEDS),seed_semantics='Only unchanged sensor/backend RNG; explicit physical initial state replaces random pose generation.',
  experiment=base['experiment'],seconds=5.,steps=500,workers=1,rate_hz=100,
  fixed_startup='Literal (x,v,theta,omega) is installed at physical t=0. Encoder raw/angle_hat initialize from biased/noisy/quantized measurement; observer rate=0. Existing zero-demand ARM lease and actual 3ms acquisition ticks occur before first policy command at physical t=3ms. Policy then runs every10ms; command delay1ms, TTL20ms. No synthetic sensor history or motor-enable impulse.',
  time_origin='Simulation elapsed t=0 is first policy decision after reset acquisition; literal plant initial time0 and reset warmup time are retained separately.',
  source=source_identity(),script_sha256=digest(Path(__file__)),base_recipe_sha256=digest(BASE/'recipe.json'),base_source_zip_sha256=digest(BASE/'source.zip'),
  centered_report_sha256=digest(CENTER/'final-report.json'),hardware_report_path=str(LIVE/'report.json'),hardware_report_sha256=digest(LIVE/'report.json'),
  hardware_trace_path=str(next(LIVE.glob('rig-*.jsonl'))),hardware_trace_sha256=digest(next(LIVE.glob('rig-*.jsonl'))),
  hardware_before_state=hardware['before_state'],hardware_before_info=hardware['before_info'],hardware_parameters=hardware['parameters'],
  bias_hypothesis=dict(raw=hardware['before_info']['encoder_raw'],saved_raw=hardware['before_info']['encoder_upright_raw'],counts=9,degrees=math.degrees(bias),radians=bias),
  limitations=['Encoder difference does not establish true tilt versus reference bias. These are diagnostic hypotheses.',
   'Current model assumes ideal acceleration tracking and its free-swing-fitted friction near upright; neither is reidentified here.',
   'No hardware enable motion, physical backlash/slip, host scheduling stalls, or later I2C fault is injected.',
   'Original frozen profile rail is0.309074998m; recorded hardware rail is0.309037507m (37.491micrometre difference); profile is intentionally unchanged.',
   'Two reused noise seeds and5s are a bounded diagnosis, not qualification or candidate selection.'])
 write_new(HERE/'protocol.json',protocol);print(json.dumps(dict(protocol_sha256=digest(HERE/'protocol.json'),cases=cases),indent=2))
def summarize(records):
 def first(predicate):return next((r['elapsed_s'] for r in records if predicate(r)),None)
 def peak(field,limit=None):return max(abs(r[field]) for r in records if limit is None or r['elapsed_s']<=limit+1e-9)
 out=dict(first_observed_abs_angle_over5deg_s=first(lambda r:abs(r['observed_theta_rad'])>math.radians(5)),
  first_true_abs_angle_over5deg_s=first(lambda r:r.get('true_theta_rad') is not None and abs(r['true_theta_rad'])>math.radians(5)),
  first_abs_x_over012m_s=first(lambda r:abs(r['x_m'])>=.12),first_rail_braking_s=first(lambda r:r['rail_braking']),
  peak_abs_observed_angle_deg=math.degrees(peak('observed_theta_rad')),peak_abs_x_m=peak('x_m'),
  first1s_peak_abs_observed_angle_deg=math.degrees(peak('observed_theta_rad',1.)),first1s_peak_abs_raw_command_m_s2=peak('raw_command_m_s2',1.),
  first1s_peak_abs_observed_omega_rad_s=peak('observed_omega_rad_s',1.),final_record=records[-1],
  first_second_quarter_windows=[])
 for lo,hi in [(0.,.25),(.25,.5),(.5,.75),(.75,1.)]:
  group=[r for r in records if lo<=r['elapsed_s']<hi]
  out['first_second_quarter_windows'].append(dict(start_s=lo,end_s=hi,peak_abs_observed_theta_deg=max(abs(math.degrees(r['observed_theta_rad'])) for r in group),
   theta_peak_to_peak_deg=math.degrees(max(r['observed_theta_rad'] for r in group)-min(r['observed_theta_rad'] for r in group)),
   raw_command_rms_m_s2=float(np.sqrt(np.mean([r['raw_command_m_s2']**2 for r in group])))))
 for value in (.1,.2,.3,.4,.5,.6,.67,.7,.8,.9,1.,1.36,2.,3.,4.,5.):
  row=min(records,key=lambda r:abs(r['elapsed_s']-value));out.setdefault('samples',[]).append(dict(requested_s=value,**row))
 return out

def hardware_comparison(protocol):
 rows=[json.loads(line) for line in Path(protocol['hardware_trace_path']).open()]
 states=[r['state'] for r in rows if r['type']=='state'];first=next(s for s in states if s['mode']==12);origin=first['unwrapped_tick']
 records=[dict(elapsed_s=(s['unwrapped_tick']-origin)/1000.,observed_theta_rad=s['theta'],observed_omega_rad_s=s['omega'],x_m=s['x'],
  raw_command_m_s2=s['demand'],executed_acceleration_m_s2=s['acceleration'],rail_braking=bool(s['brake_direction']),fault=s['fault'],mode=s['mode'])
  for s in states if 0<=(s['unwrapped_tick']-origin)/1000.<=5.]
 return dict(time_origin='First recorded mode12 state; unwrapped board millisecond tick.',origin_tick=origin,first_state=first,
  first_fault_s=next(((s['unwrapped_tick']-origin)/1000. for s in states if s['unwrapped_tick']>=origin and s['fault']),None),summary=summarize(records))

def episode(protocol,actor,case,seed):
 config,parameters,observations,_=validate_experiment(protocol['experiment']);config=replace(config,max_steps=500)
 observations=replace(observations,encoder_bias_rad=case['encoder_bias_rad'])
 env=RigCartpoleEnv(config,parameters=parameters,observation_config=observations,ttl_ms=protocol['experiment']['ttl_ms'])
 trace=HERE/'traces'/f"{actor['name']}-{case['name']}-{seed}.jsonl";trace.parent.mkdir(exist_ok=True)
 try:
  encoded,info=env.reset(seed=seed,options=dict(state=case['initial_state']));warmup=env.ground_truth.time_ns
  policy=load_neural_policy(actor['path'],channels=env.channels);policy.reset(env.session)
  startup=dict(literal_initial_state=case['initial_state'],literal_initial_time_ns=0,first_decision_time_ns=warmup,first_ground_truth=asdict(env.ground_truth),first_encoded_observation=encode_rig_observation(env.sdk_observation,env.channels),reset_info=info)
  records=[];fault=None
  with trace.open('x') as stream:
   while not(env.terminated or env.truncated):
    observed=encode_rig_observation(env.sdk_observation,env.channels);before=asdict(env.ground_truth);t=(env.ground_truth.time_ns-warmup)/1e9
    intent=policy.act(env.sdk_observation)
    if intent is None:fault=policy.fault_reason or 'policy emitted no action';break
    raw=intent.acceleration_m_s2
    row=dict(elapsed_s=t,observed_theta_rad=math.atan2(observed['state'][2],observed['state'][3]),observed_omega_rad_s=observed['state'][4],
     true_theta_rad=before['theta'],true_omega_rad_s=before['omega'],x_m=before['x'],raw_command_m_s2=raw,
     executed_acceleration_m_s2=env.diagnostics.executed_acceleration_m_s2,rail_braking=env.diagnostics.rail_braking,fault=env.fault_reason)
    encoded,_,_,_,after_info=env.step([raw]);records.append(row)
    stream.write(json.dumps(dict(summary_sample=row,encoded_observation=observed,sdk_observation=asdict(env.sdk_observation),ground_truth_before=before,
     ground_truth_after=asdict(env.ground_truth),post_step_diagnostics=asdict(env.diagnostics),physical_time_after_ns=env.ground_truth.time_ns),sort_keys=True,allow_nan=False)+'\n')
  assert len(records)==500 and fault is None and env.fault_reason is None
  return dict(actor=actor['name'],case=case['name'],seed=seed,encoder_bias_rad=case['encoder_bias_rad'],encoder_bias_degrees=math.degrees(case['encoder_bias_rad']),startup=startup,
   steps=len(records),elapsed_physical_s=(env.ground_truth.time_ns-warmup)/1e9,policy_fault=fault,simulator_fault=env.fault_reason,
   final_ground_truth=asdict(env.ground_truth),summary=summarize(records),trace_path=str(trace.relative_to(HERE)),trace_sha256=digest(trace))
 finally:env.close()

def run():
 protocol=json.loads((HERE/'protocol.json').read_text());assert source_identity()==protocol['source'] and digest(Path(__file__))==protocol['script_sha256']
 assert digest(Path(protocol['hardware_trace_path']))==protocol['hardware_trace_sha256']
 hardware=hardware_comparison(protocol);write_new(HERE/'hardware-comparison.json',hardware)
 episodes=[]
 for case in protocol['cases']:
  for seed in protocol['seeds']:
   pair=[]
   for actor in protocol['actors']:
    assert digest(Path(actor['path']))==actor['file_sha256'] and digest(Path(actor['checkpoint_path']))==actor['checkpoint_sha256']
    result=episode(protocol,actor,case,seed);episodes.append(result);pair.append(result)
    print(json.dumps(dict(actor=result['actor'],case=result['case'],seed=seed,**{k:result['summary'][k] for k in ('first_observed_abs_angle_over5deg_s','first_true_abs_angle_over5deg_s','first_abs_x_over012m_s','first_rail_braking_s','first1s_peak_abs_observed_angle_deg','peak_abs_x_m')})),flush=True)
   assert pair[0]['startup']==pair[1]['startup']
 assert source_identity()==protocol['source']
 report=dict(status='DEVELOPMENT_ONLY',simulation_only=True,hardware_accepted=False,deployable=False,completed=True,protocol_sha256=digest(HERE/'protocol.json'),
  hardware_comparison_sha256=digest(HERE/'hardware-comparison.json'),episodes=episodes,source_identity_unchanged=True,
  actors_unchanged=all(digest(Path(a['path']))==a['file_sha256'] for a in protocol['actors']),limitations=protocol['limitations'])
 write_new(HERE/'report.json',report);print(json.dumps(dict(report_sha256=digest(HERE/'report.json'),hardware_summary=hardware['summary']),indent=2),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('declare','run'));args=parser.parse_args();declare() if args.mode=='declare' else run()
