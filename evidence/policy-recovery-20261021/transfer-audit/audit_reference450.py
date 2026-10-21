#!/usr/bin/env python3
"""Offline source-bound native reference450 audit; no hardware or production edits.

Run from repo root with --snapshot local.jsonl.gz --output NEW_DIR.
The approved immutable decompressed snapshot hash is checked before parsing.
"""
import argparse,gzip,json,math
from pathlib import Path
from hashlib import sha256
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXPECTED_RAW_SHA='39442b6753c8dd9360cf7272fed2deff7ef51defd4f201b3e82a0abe58868eb7'

def stats(a):
 a=np.asarray(a,float);assert len(a)and np.isfinite(a).all()
 return dict(n=len(a),min=float(a.min()),max=float(a.max()),span=float(np.ptp(a)),mean=float(a.mean()),rms=float(np.sqrt(np.mean(a*a))))
def load_rows(raw):return [json.loads(line)for line in raw.splitlines()]
def distinct_states(rows):
 seen=set();out=[]
 for r in rows:
  if r['type']!='state':continue
  s=r['state'];key=(s['sid'],s['unwrapped_tick'])
  if key in seen:continue
  seen.add(key);out.append(s)
 return out

def episode(rows,cmd,label):
 states=distinct_states(rows)
 following=[s for s in states if s['received_ns']>=cmd['host_monotonic_ns']-2_000_000]
 first=next(s for s in following if s['flags']&2 and s['mode']in(2,3));t0=first['unwrapped_us'];active=[];after=None
 for s in following:
  if s['unwrapped_tick']<first['unwrapped_tick']:continue
  if not s['flags']&2:after=s;break
  active.append(s)
 assert after is not None and active
 before=[s for s in states if s['unwrapped_tick']<first['unwrapped_tick']]
 assert before and not before[-1]['flags']&2
 pre=[s for s in before if first['received_ns']-250_000_000<=s['received_ns']]
 relative=lambda s:(s['unwrapped_us']-t0)/1e6
 transitions=[];previous=None;segments=[];begin=None
 for s in active+[after]:
  signature=(s['mode'],s['fault'],bool(s['flags']&2))
  if signature!=previous:transitions.append(dict(t_s=relative(s),mode=s['mode'],fault=s['fault'],enabled=bool(s['flags']&2),theta_deg=math.degrees(s['theta']),x_step_m=s['x']));previous=signature
  if s['mode']==3 and s['flags']&2 and begin is None:begin=relative(s)
  if (s['mode']!=3 or not s['flags']&2)and begin is not None:segments.append(dict(start_s=begin,end_s=relative(s),duration_s=relative(s)-begin));begin=None
 def summarize(sub):
  theta=np.rad2deg(np.unwrap([s['theta']for s in sub]));delta=np.rad2deg([math.atan2(math.sin(s['theta']-s['angle_hat']),math.cos(s['theta']-s['angle_hat']))for s in sub])
  return dict(raw_theta_deg=stats(theta),raw_minus_filtered_deg=stats(delta),omega_observer=stats([s['omega']for s in sub]),counted_x_m=stats([s['x']for s in sub]),commanded_velocity=stats([s['velocity']for s in sub]),governed_acceleration=stats([s['acceleration']for s in sub]),requested_demand=stats([s['demand']for s in sub]),faults=sorted({s['fault']for s in sub}),rail_brake_samples=sum(bool(s['brake_direction'])for s in sub))
 windows=[]
 for lo,hi in [(0,.04),(0,.1),(.1,.25),(0,1)]:
  sub=[s for s in active if lo<=relative(s)<hi]
  windows.append(dict(interval_s=[lo,hi],semantics='half-open board-time window',**summarize(sub)))
 balanced=[s for s in active if s['mode']==3];band=next((relative(s)for s in balanced),None)
 details=[dict(t_s=relative(s),theta_deg=math.degrees(s['theta']),filtered_deg=math.degrees(s['angle_hat']),omega=s['omega'],x_step_m=s['x'],velocity_commanded=s['velocity'],acceleration_governed=s['acceleration'],demand=s['demand'],mode=s['mode'],fault=s['fault'],brake=s['brake_direction'])for s in active]
 last_info=None;params={}
 for r in rows:
  if r['host_monotonic_ns']>cmd['host_monotonic_ns']:continue
  if r['type']=='info':last_info=r['info']
  if r['type']=='parameter':params[r['name']]=r['value']
 requests=[r for r in rows if r['type']=='command' and cmd['host_monotonic_ns']<=r['host_monotonic_ns']<=after['received_ns']+5_000_000 and any(token in r['payload']for token in [' STOP ',' MODE ',' PARAM ','CALIBRATE'])]
 return dict(label=label,command=cmd,first_enabled_state=first,first_disabled_state=after,latest_info_before_command=last_info,latest_parameter_readbacks_before_command=params,requested_duration_s=int(cmd['payload'].split()[-1])/1000,enabled_to_first_disabled_s=relative(after),sampled_active_span_s=relative(active[-1]),active_samples=len(active),board_interval_ms=stats(np.diff([s['unwrapped_us']for s in active])/1000),transitions=transitions,balance_segments=segments,total_balance_mode_s=sum(s['duration_s']for s in segments),longest_balance_mode_s=max((s['duration_s']for s in segments),default=0),first_balance_s=band,balance_metrics=None if not balanced else summarize(balanced),startup_windows=windows,prearm_250ms=None if not pre else summarize(pre),first_100ms_states=[s for s in details if s['t_s']<=.100001],recorded_control_commands=requests),details

def main():
 p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 compressed=a.snapshot.read_bytes();raw=gzip.decompress(compressed);assert sha256(raw).hexdigest()==EXPECTED_RAW_SHA
 rows=load_rows(raw);reference=None;selected=[];calibrations=[]
 for r in rows:
  if r['type']=='info':reference=r['info']['encoder_upright_raw']
  if r['type']=='command'and 'CALIBRATE'in r['payload']:calibrations.append(r)
  if r['type']=='command'and ' MODE 'in r['payload']and reference==450:selected.append(r)
 assert len(selected)==3 and selected[-1]['payload'].endswith('bal 10000')
 summaries=[];details={}
 for label,cmd in zip(['ref450_auto_upright_10s','ref450_auto_hanging_55s_requested','ref450_bal_10s'],selected):
  report,trace=episode(rows,cmd,label);summaries.append(report);details[label]=trace
 oldfolder=ROOT/'runs/policy-recovery-20261021/hardware-live/native-bal-01';old=next(oldfolder.glob('rig-*.jsonl'));oldraw=old.read_bytes();oldrows=load_rows(oldraw);oldcmd=next(r for r in oldrows if r['type']=='command'and ' MODE 'in r['payload']);report,trace=episode(oldrows,oldcmd,'ref553_failed_agent_bal');summaries.append(report);details[report['label']]=trace
 # Four exact invariants independently guard episode association and duration.
 assert summaries[2]['latest_info_before_command']['encoder_upright_raw']==450
 assert summaries[2]['first_disabled_state']['fault']==3
 assert abs(summaries[2]['total_balance_mode_s']-10)<1e-6
 assert abs(summaries[3]['first_100ms_states'][1]['theta_deg']-(-2.636718541639931))<1e-8
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'source-prefix.jsonl.gz').write_bytes(compressed)
 result=dict(schema='cartpole-reference450-native-comparison-v1',hardware_activity=False,source=dict(original_path=str(a.snapshot),preserved_file='source-prefix.jsonl.gz',compressed_sha256=sha256(compressed).hexdigest(),uncompressed_sha256=sha256(raw).hexdigest(),uncompressed_bytes=len(raw),records=len(rows),session_id=selected[-1]['payload'].split()[2]),failed_source=dict(path=str(old.relative_to(ROOT)),sha256=sha256(oldraw).hexdigest()),script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),episodes=summaries,calibration_commands=calibrations,user_confirmation='Parent relayed user confirmation that upright calibration was the issue and that native AUTO/BAL now work.',limitations=['Mode3 durations are firmware balance-mode occupancy; angle/omega and cart-position metrics are reported separately.','Counted x and governed velocity/acceleration are not independent physical cart measurements.','Camera is not included in this final snapshot comparison.','Native AUTO55s requested duration was stopped early; report observed intervals only.','The initial calibration/pose and run conditions differ; this is a descriptive comparison and does not independently isolate a single causal mechanism.','Latest parameter readbacks may precede a HOME; latest INFO carries measured home geometry independently.'])
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True)
 for label,color in [('ref553_failed_agent_bal','tab:red'),('ref450_bal_10s','tab:blue')]:
  d=[r for r in details[label]if r['t_s']<=.2];tt=[r['t_s']for r in d]
  for ax,key in zip(axes,['theta_deg','omega','acceleration_governed']):ax.plot(tt,[r[key]for r in d],'.-',color=color,label=label)
 for ax,title in zip(axes,['raw encoder angle (deg)','MCU observer rate (rad/s)','governed acceleration (m/s²)']):ax.set_ylabel(title);ax.grid(alpha=.2);ax.legend();ax.axvline(.04,ls=':',color='gray');ax.axvline(.1,ls=':',color='gray')
 axes[-1].set_xlabel('board seconds after first enabled telemetry');fig.suptitle('Native BAL startup: preserved reference553 failure vs final reference450 run');fig.tight_layout();fig.savefig(a.output/'startup-comparison.png',dpi=150);plt.close(fig)
 (a.output/'traces.json').write_text(json.dumps(details,sort_keys=True,allow_nan=False)+'\n');result['outputs_sha256']={n:sha256((a.output/n).read_bytes()).hexdigest()for n in ['traces.json','startup-comparison.png']};(a.output/'analysis.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
 print(json.dumps([dict(label=r['label'],first_balance_s=r['first_balance_s'],longest_balance_mode_s=r['longest_balance_mode_s'],startup40_span_deg=r['startup_windows'][0]['raw_theta_deg']['span'],startup100_span_deg=r['startup_windows'][1]['raw_theta_deg']['span'],balance_theta_rms_deg=r['balance_metrics']['raw_theta_deg']['rms'],end_fault=r['first_disabled_state']['fault'])for r in summaries]))
if __name__=='__main__':main()
