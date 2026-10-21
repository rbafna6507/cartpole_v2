import json,sys,math,importlib.util,subprocess
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('base','/Users/rbafna/projects/cartpole_v2/evidence/encoder-tightening-20261021/analyze.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
out=Path('/tmp/cartpole-tuning-review');report=json.load(open(out/'compare.json'));lines=[];metadata=[]
for r in report['trials']:
 name=r['trial'];state=r['first_BAL_state'];qcam=r['capture_stages'][1]['local_camera_fit_at_target_rad'];rows=[('capture',state['angle_hat'],state['omega']),('capture_raw',state['theta'],state['omega'])]
 if qcam is not None:rows.append(('capture_camera',qcam,state['omega']))
 for suffix,q,w in rows:lines.append(f"{name}_{suffix} 0 {q} {w} {state['x']} {state['velocity']} {state['acceleration']}")
 tr=base.load_trial(Path('/tmp/cartpole-tuning-resume/data/runs/encoder-tuning-resume-20261021')/name);auto=r['auto_host_s'];states=tr['states'];host=tr['host'];pairs=base.paired(tr,-.017)
 for h,s in zip(host,states):
  if s['mode']==2 and abs(s['angle_hat'])<.6:
   lines.append(f"{name}_swing {h-auto} {s['angle_hat']} {s['omega']} {s['x']} {s['velocity']} {s['acceleration']}")
 # Descending/inbound runs in the swing state, grouped while |observer angle|<45deg.
 ix=np.flatnonzero([s['mode']==2 and abs(s['angle_hat'])<math.pi/4 for s in states]);groups=[]
 for i in ix:
  if not groups or i>groups[-1][-1]+1:groups.append([i])
  else:groups[-1].append(i)
 arcs=[]
 for group in groups:
  if len(group)<3:continue
  i=min(group,key=lambda i:abs(states[i]['angle_hat']));s=states[i];loc=[p for p in pairs if abs(p['encoder_query_host_s']-host[i])<.025]
  arcs.append(dict(time_s=float(host[i]-auto),duration_s=float(host[group[-1]]-host[group[0]]),closest_observer_angle_deg=math.degrees(s['angle_hat']),raw_angle_deg=math.degrees(s['theta']),omega=s['omega'],x=s['x'],velocity=s['velocity'],acceleration=s['acceleration'],demand=s['demand'],camera_near_angle_deg=None if not loc else float(np.degrees(base.circular_summary([p['camera_rad'] for p in loc])['median'])),energy=.5*.124/9.81*s['omega']**2+math.cos(s['angle_hat'])))
 metadata.append(dict(trial=name,upright_arcs=arcs))
(out/'forecast-inputs.txt').write_text('\n'.join(lines)+'\n');run=subprocess.run([str(out/'forecast')],input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True);(out/'forecast-output.txt').write_text(run.stdout)
keys=['case','t','pz','gates','capture','capture_v0p15','demand','q180','w180','x180','v180','a180','lyapunov_ratio','brake180','diverge180','max_abs_q180','max_abs_x180'];rows=[]
for line in run.stdout.splitlines():
 parts=line.split();rows.append(dict(zip(keys,[parts[0]]+list(map(float,parts[1:])))))
(out/'forecast.json').write_text(json.dumps(dict(rows=rows,arcs=metadata,gate_bits={'angle':1,'rate':2,'cart_position':4,'cart_velocity':8,'demand':16,'demand_accel_difference':32,'outbound':64},cautions=['Native firmware180ms feasibility model, not hardware or motor-tracking prediction.','Counterfactual pz only recomputes instantaneous gain/forecast; it does not reproduce changed approach trajectory.','Camera-substituted angle retains firmware rate and camera image vertical proxy; diagnostic only.']),indent=2)+'\n')
for row in rows:
 if not row['case'].endswith('_swing'):print(row)
for arc in metadata:print('ARCS',json.dumps(arc))
