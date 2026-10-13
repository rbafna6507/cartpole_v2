from pathlib import Path
import json,csv,hashlib,io
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'analysis/sep18'
log=OUT/'run_20260918_103825.csv';side=log.with_name(log.stem+'_events.jsonl')
b=log.read_bytes();b=b[:b.rfind(b'\n')+1];log.write_bytes(b)
b=side.read_bytes();b=b[:b.rfind(b'\n')+1];side.write_bytes(b)
r=np.genfromtxt(log,delimiter=',',names=True);es=[json.loads(l) for l in b.decode().splitlines()];h0=es[0]['host_time_s'];t=(r['t_ms']-r['t_ms'][0])/1000;dt=np.r_[np.diff(t),0]
par={};trials=[];start=None
for e in es:
 f=e['text'].split();tt=e['host_time_s']-h0
 if e['direction']=='rx' and len(f)==3 and f[0]=='=':
  try:par[f[1]]=float(f[2])
  except ValueError:pass
 if e['direction']=='rx' and e['text']=='# SWINGUP':start=tt;settings=par.copy()
 if start is not None and ((e['direction']=='rx' and e['text']=='# STOP') or e==es[-1]):
  end=tt;mask=(t>=start)&(t<=end)&np.isin(r['mode'],[2,3,5,6]);ids=np.where(mask)[0]
  if not len(ids):continue
  captures=[]
  for j,a in enumerate(es):
   if start<=a['host_time_s']-h0<=end and a['text']=='# caught -> BALANCE':
    z=next((z for z in es[j+1:] if z['direction']=='rx' and any(z['text'].startswith(k) for k in ['# rail recovery','# lost it','# STOP','!'])),None)
    if z:captures.append({'at':a['host_time_s']-h0-start,'duration':z['host_time_s']-a['host_time_s'],'exit':z['text']})
  first=ids[0];last=ids[-1]
  tr={'name':f'Sep 18 · trial {len(trials)+1}','start_s':start,'end_s':end,'partial':e==es[-1],'params':settings,'initialAngle':float(np.degrees(np.arctan2(np.sin(r['theta'][first]-np.pi),np.cos(r['theta'][first]-np.pi)))),'initialOmega':float(r['theta_dot'][first]),'initialX':float(r['x'][first]),'captures':captures,'summary':{'samples':len(ids),'duration_s':float(t[last]-t[first]),'balance_entries':len(captures),'longest_balance_s':max([x['duration'] for x in captures],default=0),'rail_fraction':float(sum(dt[mask & np.isin(r['mode'],[5,6])])/sum(dt[mask])),'max_command_speed_m_s':float(max(abs(r['v'][mask]))),'max_pulse_position_m':float(max(abs(r['x'][mask]))),'max_command_acceleration_m_s2':float(max(abs(r['accel'][mask]))),'max_angle_from_down_deg':float(max(180-abs(r['theta'][mask])*180/np.pi))},'points':[[round(float(t[i]-t[first]),4),float(r['theta'][i]),float(r['theta_dot'][i]),float(r['x'][i]),float(r['v'][i]),float(r['accel'][i]),int(r['mode'][i])] for i in ids]}
  trials.append(tr);start=None
bundle={'schema':1,'source':str(log.relative_to(ROOT)),'sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'events_source':str(side.relative_to(ROOT)),'events_sha256':hashlib.sha256(side.read_bytes()).hexdigest(),'point_columns':['t','theta_upright','omega_filtered','pulse_x','command_v','command_a','mode'],'trials':trials}
(OUT/'recorded_trials.json').write_text(json.dumps(bundle,indent=2)+'\n')
print('length',t[-1],'parse errors',sum(e['direction']=='parse_error' for e in es))
for tr in trials:print(tr['name'],tr['start_s'],tr['end_s'],tr['initialAngle'],tr['initialX'],tr['summary'],{k:tr['params'].get(k) for k in ['vmax','amax_s','amax_b','jmax','ke','kpx','kdx','phase_soft','rail']})
if __name__=='__main__':
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 fig,ax=plt.subplots(3,1,figsize=(12,8),layout='constrained')
 down=np.arctan2(np.sin(r['theta']-np.pi),np.cos(r['theta']-np.pi));down[np.r_[False,abs(np.diff(down))>np.pi]]=np.nan
 ax[0].plot(t,np.degrees(down));ax[0].set_ylabel('Angle from down (°)');ax[1].plot(t,r['theta_dot']);ax[1].set_ylabel('Filtered rate (rad/s)');ax[2].plot(t,r['x']*1000);ax[2].set_ylabel('Pulse x (mm)');ax[2].set_xlabel('Seconds from log start')
 for a in ax:a.grid(alpha=.2)
 fig.savefig(OUT/'overview.png',dpi=140)
