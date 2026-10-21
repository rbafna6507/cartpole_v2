#!/usr/bin/env python3
"""Verify saved commands, summarize and plot; no new simulation or fitting."""
from hashlib import sha256
from pathlib import Path
import json,math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cartpole_sdk.learning.balance_experiment import source_identity
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels
P=Path(__file__).resolve().parent
digest=lambda p:sha256(p.read_bytes()).hexdigest()
protocol=json.loads((P/'protocol.json').read_text());report=json.loads((P/'report.json').read_text());hardware=json.loads((P/'hardware-comparison.json').read_text())
assert source_identity()==protocol['source'] and report['protocol_sha256']==digest(P/'protocol.json')
assert protocol['script_sha256']==digest(P/'run.py')
actors={a['name']:a for a in protocol['actors']};backends={}
for name,a in actors.items():
 assert digest(Path(a['path']))==a['file_sha256'] and digest(Path(a['checkpoint_path']))==a['checkpoint_sha256']
 backends[name]=NumpyActorBackend(load_neural_policy(a['path'],channels=rig_channels()).actor)
count=0;maximum=0.;traces={}
for episode in report['episodes']:
 path=P/episode['trace_path'];assert digest(path)==episode['trace_sha256']
 rows=[json.loads(l) for l in path.open()];assert len(rows)==500
 assert episode['startup']['first_decision_time_ns']==3000000
 for i,row in enumerate(rows):
  sample=row['summary_sample'];assert abs(sample['elapsed_s']-i*.01)<1e-12
  assert row['ground_truth_before']['time_ns']==3000000+i*10000000
  assert row['ground_truth_after']['time_ns']==3000000+(i+1)*10000000
  assert row['post_step_diagnostics']['fault_reason'] is None
  expected=backends[episode['actor']].predict_encoded(row['encoded_observation'])
  maximum=max(maximum,abs(expected-sample['raw_command_m_s2']));count+=1
  assert abs(sample['raw_command_m_s2']-row['post_step_diagnostics']['raw_acceleration_m_s2'])<1e-12
 traces[(episode['actor'],episode['case'],episode['seed'])]=[r['summary_sample'] for r in rows]
assert count==6000 and maximum<1e-5
hw_rows=[json.loads(l) for l in Path(protocol['hardware_trace_path']).open()]
assert digest(Path(protocol['hardware_trace_path']))==protocol['hardware_trace_sha256']
origin=hardware['origin_tick'];hw=[]
for r in hw_rows:
 if r['type']!='state':continue
 s=r['state'];t=(s['unwrapped_tick']-origin)/1000.
 if 0<=t<=5:hw.append(dict(elapsed_s=t,observed_theta_rad=s['theta'],raw_command_m_s2=s['demand'],x_m=s['x']))
summary=[]
for case in protocol['cases']:
 for actor in protocol['actors']:
  episodes=[e for e in report['episodes'] if e['actor']==actor['name'] and e['case']==case['name']]
  summary.append(dict(actor=actor['name'],case=case['name'],episodes=len(episodes),
   first1s_peak_abs_observed_angle_deg=max(e['summary']['first1s_peak_abs_observed_angle_deg'] for e in episodes),
   first1s_peak_abs_raw_command_m_s2=max(e['summary']['first1s_peak_abs_raw_command_m_s2'] for e in episodes),
   first_over5deg_s=[e['summary']['first_observed_abs_angle_over5deg_s'] for e in episodes],
   first_over12cm_s=[e['summary']['first_abs_x_over012m_s'] for e in episodes],
   first_rail_braking_s=[e['summary']['first_rail_braking_s'] for e in episodes],
   maximum_cart_excursion_m=max(e['summary']['peak_abs_x_m'] for e in episodes),final_cart_positions_m=[e['final_ground_truth']['x'] for e in episodes],
   first_second_quarter_peaks_deg=[[q['peak_abs_observed_theta_deg'] for q in e['summary']['first_second_quarter_windows']] for e in episodes]))
fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True)
series=[('Hardware centered',hw,'#c23b32',1.)]
for name,color in [('centered','#246ea4'),('original47','#68747b')]:
 for seed in (94000,94007):
  series.append((name+' sim: +9-count bias'+(' (two seeds)' if seed==94000 else ''),traces[(name,'true_upright_plus9counts_bias',seed)],color,.85 if seed==94000 else .45))
for label,records,color,alpha in series:
 t=[r['elapsed_s'] for r in records];lab=label if not(label.endswith('bias')) else '_nolegend_'
 axes[0].plot(t,[math.degrees(r['observed_theta_rad']) for r in records],color=color,alpha=alpha,label=lab,lw=1.6)
 axes[1].plot(t,[r['raw_command_m_s2'] for r in records],color=color,alpha=alpha,lw=1.6)
 axes[2].plot(t,[r['x_m']*100 for r in records],color=color,alpha=alpha,lw=1.6)
axes[0].set_ylabel('Measured angle (degrees)');axes[1].set_ylabel('Raw demand (m/s²)');axes[2].set_ylabel('Cart position (cm)');axes[2].set_xlabel('Seconds from first active hardware sample / first sim decision')
axes[0].axhline(5,color='#999',ls=':',lw=.8);axes[0].axhline(-5,color='#999',ls=':',lw=.8)
axes[2].axhline(12,color='#999',ls=':',lw=.8);axes[2].axhline(-12,color='#999',ls=':',lw=.8)
for ax in axes:ax.grid(alpha=.2);ax.set_xlim(0,1.5)
axes[0].legend(loc='upper left',fontsize=8)
fig.suptitle('Frozen actors, unchanged model: hardware grows rapidly; +0.791° simulated bias does not\nSimulation starts true upright; no motor-enable disturbance or I2C fault injected',fontsize=11)
fig.tight_layout(rect=(0,0,1,.94));fig.savefig(P/'first-1p5s-comparison.png',dpi=180);plt.close(fig)
result=dict(status='DEVELOPMENT_ONLY',simulation_only=True,hardware_accepted=False,deployable=False,completed=True,
 interpretation='The unchanged model does not reproduce centered hardware subsecond angular instability under either reference-bias or real-tilt hypothesis. +9-count bias predicts centering loss, not the recorded rapidly growing first-second oscillation. This exposes a dynamics/startup/sensing gap, without identifying which physical or timing mechanism causes it.',
 unchanged_model_parameters=protocol['experiment']['simulation_config'],unchanged_observation_config=protocol['experiment']['observation_config'],
 verification=dict(trace_count=len(report['episodes']),commands_replayed=count,max_numpy_vs_recorded_raw_difference_m_s2=maximum,physical_timeline_and_startup_verified=True,source_and_actors_unchanged=True),
 simulation_summary=summary,hardware_summary={k:hardware['summary'][k] for k in ('first_observed_abs_angle_over5deg_s','first_abs_x_over012m_s','first_rail_braking_s','first1s_peak_abs_observed_angle_deg','first1s_peak_abs_raw_command_m_s2','first1s_peak_abs_observed_omega_rad_s','first_second_quarter_windows')},
 hardware_first_fault_s=hardware['first_fault_s'],protocol_sha256=digest(P/'protocol.json'),report_sha256=digest(P/'report.json'),
 hardware_comparison_sha256=digest(P/'hardware-comparison.json'),plot_sha256=digest(P/'first-1p5s-comparison.png'),verification_script_sha256=digest(Path(__file__)),limitations=protocol['limitations'])
with (P/'analysis.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps(dict(analysis_sha256=digest(P/'analysis.json'),verification=result['verification'],simulation_summary=summary,hardware_first_fault_s=hardware['first_fault_s']),indent=2))
