#!/usr/bin/env python3
"""Offline Q episode/rail analysis from recorded clocks, with no hardware IO."""
from pathlib import Path
import json,hashlib,math
import numpy as np
BASE=Path('/tmp/cartpole-retune-20261015');SRC=BASE/'cart-poles-q-comparison';OUT=BASE/'jerk-analysis';R=180/np.pi;ANCHOR=-.009445365634260372
wrap=lambda x:(np.asarray(x)+np.pi)%(2*np.pi)-np.pi
prior={r['name']:r for r in json.loads((OUT/'cart-poles-q-results.json').read_text())['trials']}

def stopping_distance(v,a,amax,j):
 v=max(0.,v);a=max(-amax,min(amax,a))
 if a<0 and v<a*a/(2*j):
  tt=2*v/(-a+math.sqrt(max(0,a*a-2*j*v)));return max(0,v*tt+.5*a*tt*tt+j*tt**3/6)
 peak=min(amax,math.sqrt(j*v+.5*a*a));t1=max(0,(a+peak)/j);v1=v+a*t1-.5*j*t1*t1;hold=max(0,(v1-peak*peak/(2*j))/peak) if peak else 0
 d1=v*t1+.5*a*t1*t1-j*t1**3/6;d2=v1*hold-.5*peak*hold*hold;v2=v1-peak*hold;t3=peak/j
 return max(0,d1+d2+v2*t3-.5*peak*t3*t3+j*t3**3/6)

def analyze(d):
 rep=json.loads((d/'report.json').read_text());ss=[]
 for line in next(d.glob('rig-*.jsonl')).read_text().splitlines():
  e=json.loads(line)
  if e['type']=='state' and (not ss or e['state']['unwrapped_us']!=ss[-1]['unwrapped_us']):ss.append(e['state'])
 start=rep['motion_start']['unwrapped_us']/1e6;duration=rep['requested_s'];t=np.array([s['unwrapped_us']/1e6-start for s in ss]);m=np.array([s['mode'] for s in ss]);x=np.array([s['x'] for s in ss]);v=np.array([s['velocity'] for s in ss]);a=np.array([s['acceleration'] for s in ss]);dem=np.array([s['demand'] for s in ss]);theta=np.array([s['theta'] for s in ss]);omega=np.array([s['omega'] for s in ss]);offset=float(np.quantile(np.array([s['received_ns']/1e9 for s in ss])-t,.01));jmax=rep['parameters']['jmax']
 def state(i):return {k:ss[i][k] for k in ['mode','theta','angle_hat','omega','x','velocity','acceleration','demand','brake_direction','tick','unwrapped_us','received_ns']}
 transitions=[]
 for i in range(1,len(ss)):
  if m[i]!=m[i-1] and 0<=t[i]<=duration+.01:transitions.append({'at_s':float(t[i]),'from':int(m[i-1]),'to':int(m[i]),'previous':state(i-1),'current':state(i)})
 camera=json.loads((d/'camera.json').read_text());pairs=[];seen=set()
 for c in camera:
  if c.get('seq') in seen:continue
  seen.add(c.get('seq'))
  if not c.get('angle_valid',c.get('detected')) or c.get('stale',False) or c.get('theta_rad') is None or c['receipt_s']-c['t']>.1:continue
  ct=c['t']-.019-offset;i=np.searchsorted(t,ct)
  if i<=0 or i>=len(t) or t[i]-t[i-1]>.03:continue
  camangle=float(wrap(c['theta_rad']-ANCHOR));enc=float(wrap(np.interp(ct,t,np.unwrap(theta))));pairs.append([ct,camangle*R,float(wrap(camangle-enc))*R])
 pairs=np.array(pairs)
 def window_metrics(ix):
  tt=t[ix];w=np.diff(tt)
  if not len(w):return None
  mean=lambda vals:float(np.average(vals[:-1],weights=w));xx=x[ix];slope,intercept=np.polyfit(tt-tt[0],xx,1);path=float(sum(abs(np.diff(xx))));sg=[]
  for vv in v[ix]:
   sign=1 if vv>.05 else -1 if vv<-.05 else 0
   if sign and (not sg or sg[-1]!=sign):sg.append(sign)
  cp=pairs[(pairs[:,0]>=tt[0])&(pairs[:,0]<=tt[-1])] if len(pairs) else np.empty((0,3))
  return {'start_s':float(tt[0]),'end_s':float(tt[-1]),'duration_s':float(tt[-1]-tt[0]),'net_dx_m':float(xx[-1]-xx[0]),'net_speed_m_s':float((xx[-1]-xx[0])/(tt[-1]-tt[0])),'linear_x_slope_m_s':float(slope),'detrended_x_rms_m':float(np.sqrt(np.mean((xx-(slope*(tt-tt[0])+intercept))**2))),'cart_path_m':path,'velocity_reversals':max(0,len(sg)-1),'x_min_max':[float(min(xx)),float(max(xx))],'v_min_max':[float(min(v[ix])),float(max(v[ix]))],'native_theta_mean_deg':mean(theta[ix]*R),'native_theta_rms_deg':math.sqrt(mean((theta[ix]*R)**2)),'omega_rms':math.sqrt(mean(omega[ix]**2)),'demand_minus_a_rms':math.sqrt(mean((dem[ix]-a[ix])**2)),'near_jerk_cap_fraction':float(sum(w*(abs(np.diff(a[ix])/w)>=.95*jmax))/sum(w)),'camera_n':len(cp),'camera_working_theta_mean_deg':float(np.mean(cp[:,1])) if len(cp) else None,'camera_working_theta_rms_deg':float(np.sqrt(np.mean(cp[:,1]**2))) if len(cp) else None,'camera_minus_encoder_median_deg':float(np.median(cp[:,2])) if len(cp) else None}
 groups=[]
 for i in np.where((m==3)&(t>=0)&(t<=duration))[0]:
  if not groups or i!=groups[-1][-1]+1 or t[i]-t[i-1]>.03:groups.append([i])
  else:groups[-1].append(i)
 episodes=[]
 for group in groups:
  ix=np.array(group);first=ix[0];last=ix[-1];out={'entry_bracket_s':[float(t[first-1]),float(t[first])],'exit_bracket_s':[float(t[last]),float(t[last+1])],'first_state':state(first),'last_state':state(last),'next_state':state(last+1),'full':window_metrics(ix),'first_second':window_metrics(ix[t[ix]<=t[first]+1]),'last_second':window_metrics(ix[t[ix]>=t[last]-1]),'deadline_censored':bool(t[last]>=duration-.0041)}
  if m[last+1]==5:
   edge=rep['parameters']['rail']-.015;sgn=ss[last+1]['brake_direction'];sd=stopping_distance(v[last]*sgn,a[last]*sgn,25,jmax);out['recorded_rail_context']={'outward_direction':sgn,'old_boundary_m':edge,'last_balance_outward_x_m':float(x[last]*sgn),'last_balance_stopping_distance_m':sd,'last_balance_outward_x_plus_stop_m':float(x[last]*sgn+sd),'note':'Static stoppingDistance calculation at last observed balance state; exact governor uses one-tick prospective state and hidden 1kHz updates. It is not a counterfactual trajectory.','nominal_proposed_boundary_m':.294,'extra_room_m':.294-edge,'extra_room_divided_by_outward_speed_s':(.294-edge)/(v[last]*sgn) if v[last]*sgn>0 else None}
  episodes.append(out)
 return {'name':d.name,'motion_start_board_us':rep['motion_start']['unwrapped_us'],'parameters':rep['parameters'],'reported_duration_s':duration,'transitions':transitions,'episodes':episodes,'baseline_summary':prior[d.name],'hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [d/'report.json',d/'camera.json',next(d.glob('rig-*.jsonl'))]}}

runs=[analyze(d) for d in SRC.iterdir() if (d/'report.json').exists()];runs.sort(key=lambda r:r['motion_start_board_us'])
out={'schema':'q-envelope-episodes-v1','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'camera_convention':'Current working anchor, fixed descriptive19ms effective lag, source host-read semantics; no angle map. Camera statistics are available-sample summaries, not time-continuous guarantees.','governor_reference':'Archived v5-jerk-release.tar.gz firmware/teensy_executor/cart_motion.h stoppingDistance lines38–54; Python translation, not bit-exact float32 firmware replay.','geometry':{'measured_switch_span_m':.6190875,'old_normal_width_m':.49,'old_fraction':.49/.6190875,'proposed_normal_width_m':.588,'proposed_fraction':.588/.6190875},'runs':runs};(OUT/'q-envelope-results.json').write_text(json.dumps(out,indent=2)+'\n')
for r in runs:
 print('\n',r['name'])
 for e in r['episodes']:
  print('episode',e['entry_bracket_s'],e['exit_bracket_s'],'to',e['next_state']['mode'],'capture',{k:e['first_state'][k] for k in ['theta','omega','x','velocity','acceleration','demand']});print('FULL',e['full']);print('FIRST',e['first_second']);print('LAST',e['last_second']);print('RAIL',e.get('recorded_rail_context'))
