"""Offline recorded-action gate audit; no serial/service/hardware imports."""
import argparse,collections,copy,dataclasses,gzip,hashlib,json,math,statistics,subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'source'))
from cartpole_sdk.control.parameters import ControllerParameters,gains
from cartpole_sdk.control.reference import can_capture,approach,balance
from cartpole_sdk.control.forecast import can_capture_fast
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy
from cartpole_sdk.contracts import Sample,Observation,Channel,Session,UNITS

parser=argparse.ArgumentParser()
parser.add_argument('--input',default='input.json.gz')
parser.add_argument('--prefix',default='')
args=parser.parse_args()
output_prefix=args.prefix
d=json.loads(gzip.decompress((BASE/args.input).read_bytes()))
p=ControllerParameters(**d['report']['parameters']);k=gains(p)
rows=d['rows'];t0=rows[0]['state']['unwrapped_us']/1e6
param_names=list(d['report']['parameters'])
cpp='''#include <iostream>\n#include "swing_controller.h"\nint main(){swing_control::Parameters p; float q,w,x,v,a;while(std::cin'''+''.join(' >> p.'+name for name in param_names)+''' >> q >> w >> x >> v >> a){auto k=swing_control::gains(p);std::cout << swing_control::canCapture(p,k,q,w,x,v,a) << '\\n';}}\n'''
(BASE/'native.cpp').write_text(cpp)
subprocess.run(['c++','-std=c++17','-O2','-fno-fast-math','-I',str(BASE/'headers'),str(BASE/'native.cpp'),'-o',str(BASE/'native')],capture_output=True,text=True,check=True)
native_input=[]
for row in rows:
 s=row['state'];native_input.append(' '.join(format(v,'.17g') for v in [*(getattr(p,name) for name in param_names),s['angle_hat'],s['omega'],s['x'],s['velocity'],s['acceleration']]))
native=subprocess.run([str(BASE/'native')],input='\n'.join(native_input)+'\n',capture_output=True,text=True,check=True)
native_outputs=[bool(int(s)) for s in native.stdout.splitlines()]
assert len(native_outputs)==len(rows)

def stats(values):
 values=sorted(values);n=len(values)
 return dict(n=n,min=values[0] if n else None,max=values[-1] if n else None,mean=statistics.mean(values) if n else None,p50=statistics.median(values) if n else None,p95=values[min(n-1,int(.95*n))] if n else None)
def gate_reasons(s):
 q,w,x,v,a=[s[name] for name in ['angle_hat','omega','x','velocity','acceleration']]
 b=balance(k,q,w,x,v)
 conditions=dict(angle=abs(q)>=p.catch_a,rate=abs(w)>=p.catch_r,position=abs(x)>=min(.12,p.rail-2*p.rail_margin),velocity=abs(v)>=min(p.catch_v,p.vmax,p.vmax_b),demand=abs(b)>=p.amax_b,acceleration_mismatch=abs(b-a)>p.catch_da,outbound=abs(q)>.20 and q*w>0)
 return [name for name,bad in conditions.items() if bad],b
def trace_fast(args):
 result={}
 def tracer(frame,event,arg):
  if frame.f_code is can_capture_fast.__code__ and event=='return':
   result.update(return_line=frame.f_lineno,locals={key:frame.f_locals[key] for key in ['initial','final','limit','q','w','xx','velocity','a','target','request','settled_v','error','remaining'] if key in frame.f_locals})
  return tracer
 sys.settrace(tracer)
 try:ok=can_capture_fast(*args)
 finally:sys.settrace(None)
 result['accepted']=ok;return result

Q=('position','velocity','angle','angular_velocity','acceleration','brake_direction')
def observation(s):
 t=s['unwrapped_us']*1000
 values=(s['x'],s['velocity'],s['angle_hat'],s['omega'],s['acceleration'],s['brake_direction'])
 samples=tuple(Sample('pole' if q in ('angle','angular_velocity') else 'cart',q,'magnetic_filtered' if q=='angle' else 'magnetic' if q=='angular_velocity' else 'step',float(value),UNITS[q],'encoder-zero' if q in ('angle','angular_velocity') else 'cart-step-home','recorded','valid',None,'estimated',t,t,t) for q,value in zip(Q,values))
 samples+=(Sample('pole','angle','magnetic',s['theta'],'rad','encoder-zero','recorded','valid',None,'measured',t,t,t),)
 req=rows[0]['request']
 return Observation(req['session_id'],req['clock_id'],s['unwrapped_tick'],t,'board acquisition snapshot proxy',samples)
first=observation(rows[0]['state']);policy=ExecutorFeedbackPolicy(tuple(x.channel for x in first.samples[:6]),parameters=p,rate_hz=250,start_mode='auto',raw_angle_channel=first.samples[-1].channel)
policy.reset(Session(first.session_id,first.clock_id))
details=[];fast_true=[];ref_true=[];cpp_true=[];differences=[];shadow_errors=[];host_latencies=[];command_age_ticks=[]
for i,row in enumerate(rows):
 s=row['state'];q,w,x,v,a=[s[name] for name in ['angle_hat','omega','x','velocity','acceleration']]
 reasons,b=gate_reasons(s);args=(p,k,q,w,x,v,a)
 fast=can_capture_fast(*args);ref=can_capture(*args);native=native_outputs[i]
 if fast:fast_true.append(i)
 if ref:ref_true.append(i)
 if native:cpp_true.append(i)
 if fast!=ref or fast!=native:differences.append(i)
 shadow=policy.act(observation(s))
 if shadow is None:shadow_errors.append(dict(i=i,fault=policy.fault_reason))
 else:shadow_errors.append(shadow.acceleration_m_s2-row['request']['acceleration_m_s2'])
 delay_ms=(row['send_record_ns']-s['received_ns'])/1e6
 host_latencies.append(delay_ms)
 energy=.5*p.leff/9.81*w*w+math.cos(q)-1
 pump=p.ke*energy*math.tanh(w*math.cos(q)/p.phase_soft)-p.kpx*x-p.kdx*v
 clipped_pump=max(-p.amax_s,min(p.amax_s,pump))
 native_approach=approach(p,q,w,x,v,a,clipped_pump,.001,k)
 host_approach=approach(p,q,w,x,v,a,clipped_pump,.004,k)
 inbound=q*w<0 or abs(q)<.15
 weight=max(0,min(1,(p.approach_angle-abs(q))/max(.05,p.approach_angle-p.catch_a))) if inbound else 0
 item=dict(index=i,t_s=s['unwrapped_us']/1e6-t0,board_tick=s['unwrapped_tick'],raw_theta=s['theta'],theta=q,omega=w,x=x,v=v,a=a,recorded_demand=row['request']['acceleration_m_s2'],balance_demand=b,acceleration_mismatch=abs(b-a),energy_error=energy,brake=s['brake_direction'],initial_rejections=reasons,fast_capture=fast,reference_capture=ref,native_capture=native,inbound=inbound,approach_weight=weight,native_dt_approach=float(native_approach),host_dt_approach=float(host_approach),receive_to_send_record_ms=delay_ms)
 if not reasons:item['fast_forecast']=trace_fast(args)
 details.append(item)

def bouts(predicate):
 groups=[];active=[]
 for item in details:
  if predicate(item):active.append(item)
  elif active:groups.append(active);active=[]
 if active:groups.append(active)
 return groups
def bout_summary(group):
 atzero=min(group,key=lambda r:abs(r['theta']))
 return dict(start_s=group[0]['t_s'],end_s=group[-1]['t_s'],samples=len(group),closest=atzero,rate_range=[min(r['omega'] for r in group),max(r['omega'] for r in group)],velocity_range=[min(r['v'] for r in group),max(r['v'] for r in group)],x_range=[min(r['x'] for r in group),max(r['x'] for r in group)],energy_error_range=[min(r['energy_error'] for r in group),max(r['energy_error'] for r in group)],rejection_counts=dict(collections.Counter(reason for row in group for reason in row['initial_rejections'])),all_initial_guards_pass=sum(not row['initial_rejections'] for row in group))
near=[r for r in details if abs(r['theta'])<p.catch_a]
initial_pass=[r for r in details if not r['initial_rejections']]
failed_event=next((event for event in d['events'] if event['type']=='policy_failure'),None)
failure_candidates=[]
for event in d.get('failure_timeline',[]):
 if event['type']!='state' or event['host_monotonic_ns']>=failed_event['host_monotonic_ns']:continue
 s=event['state']
 if s['unwrapped_tick']<=rows[-1]['state']['unwrapped_tick']:continue
 candidate=copy.deepcopy(policy)
 intent=candidate.act(observation(s))
 failure_candidates.append(dict(board_tick=s['unwrapped_tick'],gap_us=s['unwrapped_us']-rows[-1]['state']['unwrapped_us'],fault_reason=candidate.fault_reason,action=None if intent is None else intent.acceleration_m_s2))
summary=dict(source_manifest=d['source_manifest'],parameters=dataclasses.asdict(p),gains=dataclasses.asdict(k),samples=len(details),duration_s=details[-1]['t_s'],events=d['events'],fast_capture_indices=fast_true,reference_capture_indices=ref_true,native_capture_indices=cpp_true,forecast_disagreement_indices=differences,all_initial_guards_pass=len(initial_pass),initial_pass_samples=initial_pass,near_upright_samples=len(near),near_upright_bouts=[bout_summary(g) for g in bouts(lambda r:abs(r['theta'])<p.catch_a)],approach_bouts=[bout_summary(g) for g in bouts(lambda r:abs(r['theta'])<p.approach_angle)],near_upright_rejection_counts=dict(collections.Counter(reason for row in near for reason in row['initial_rejections'])),receive_to_send_record_ms=stats(host_latencies),action_intervals_ms=stats([(rows[i]['state']['unwrapped_us']-rows[i-1]['state']['unwrapped_us'])/1000 for i in range(1,len(rows))]),shadow_policy_max_abs_action_difference=max(abs(x) for x in shadow_errors if type(x) in (float,int)),shadow_policy_faults=[x for x in shadow_errors if isinstance(x,dict)],shadow_final_mode=policy.mode,native_vs_host_approach_delta_near=stats([r['host_dt_approach']-r['native_dt_approach'] for r in details if abs(r['theta'])<p.approach_angle]),limitations=['Native C++ header compiled on Mac is a binary32 control oracle, not a replay of actual 1kHz sensor/motor timing.','Recorded theta/omega and cart motion states are encoder/command estimates; no independent physical trajectory.','receive_to_send_record is a host logging proxy, not board command application latency.','No sample at an unrecorded intermediate 1ms tick can be reconstructed exactly.','No parameters, thresholds or live control changed.'],source_hashes={str(path.relative_to(BASE)):hashlib.sha256(path.read_bytes()).hexdigest() for root in [BASE/'source',BASE/'headers'] for path in root.rglob('*') if path.is_file()},hardware_activity=False)
summary['failure_candidate_replays']=failure_candidates
(BASE/(output_prefix+'summary.json')).write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
(BASE/(output_prefix+'sample-diagnostics.json.gz')).write_bytes(gzip.compress(json.dumps(details,separators=(',',':'),allow_nan=False).encode()))
print(json.dumps({key:summary[key] for key in ['samples','duration_s','forecast_disagreement_indices','all_initial_guards_pass','near_upright_samples','receive_to_send_record_ms','action_intervals_ms','shadow_policy_max_abs_action_difference','shadow_policy_faults','shadow_final_mode','native_vs_host_approach_delta_near']},indent=2))
