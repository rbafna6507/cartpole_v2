import sys,json,math,importlib.util,hashlib
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('base','/Users/rbafna/projects/cartpole_v2/evidence/encoder-tightening-20261021/analyze.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
t=b.load_trial(Path('/tmp/cartpole-tuning-resume/data/runs/encoder-tuning-resume-20261021/bw8-auto25-03'));s=t['states'];host=t['host'];auto=host[next(i for i,x in enumerate(s) if x['mode'] in [2,3])];tt=host-auto;q=np.array([x['angle_hat'] for x in s]);w=np.array([x['omega'] for x in s]);x=np.array([z['x'] for z in s]);v=np.array([z['velocity'] for z in s]);a=np.array([z['acceleration'] for z in s]);mode=np.array([z['mode'] for z in s]);mask=(tt>=8)&(tt<=24)&(mode==2);E=.5*.124/9.81*w*w+np.cos(q);phase=w*np.cos(q);pump=4*(E-1)*np.tanh(phase/2);center=-40*x;velocity=-2*v
turns=[]
for i in range(1,len(s)):
 if mask[i] and w[i-1]*w[i]<=0 and (not turns or tt[i]-turns[-1]['t_s']>.2):
  local=np.flatnonzero(mask&(abs(tt-tt[i])<.06));j=local[np.argmin(abs(q[local]))];turns.append(dict(t_s=float(tt[j]),observer_angle_deg=math.degrees(q[j]),raw_deg=math.degrees(s[j]['theta']),energy=float(E[j]),cart_m=float(x[j])))
rows=b.paired(t,-.017);pp=[r for r in rows if 8<=r['encoder_query_host_s']-auto<=24 and r['mode']==2]
def stats(y):return dict(min=float(np.min(y)),median=float(np.median(y)),max=float(np.max(y)),rms=float(np.sqrt(np.mean(np.asarray(y)**2))))
report=dict(window_after_auto_s=[8,24],all_recorded_modes_in_window=sorted(set(int(z) for z in mode[(tt>=8)&(tt<=24)])),state_n=int(mask.sum()),encoder_min_abs_angle_deg=math.degrees(min(abs(q[mask]))),camera_min_abs_image_angle_deg=math.degrees(min(abs(r['camera_rad']) for r in pp)),normalised_encoder_energy=stats(E[mask]),cart_position_m=stats(x[mask]),rate_rad_s=stats(w[mask]),pump_request=stats(pump[mask]),center_request=stats(center[mask]),velocity_request=stats(velocity[mask]),turns=turns,
 interpretation='The late cycle does not approach the14.3deg capture-angle window or45.8deg approach zone. Capture velocity/rate restrictions cannot directly change this late trajectory; only avoiding early failed catch/rail recovery could change the later path. Normalized energy and component demands are encoder/model-based diagnostics, not independent mechanical energy.')
Path('/tmp/cartpole-tuning-review/late-cycle.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
