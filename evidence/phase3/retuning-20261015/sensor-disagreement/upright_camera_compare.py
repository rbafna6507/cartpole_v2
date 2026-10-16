"""Offline raw image orientation vs encoder. No physical vertical assumption."""
from pathlib import Path
import gzip,json,hashlib
import numpy as np
from scipy.optimize import least_squares
P=Path('/tmp/cartpole-retune-20261015')
SOURCES=['upright370-partial.json.gz','upright370-cameras.json.gz']
reports=json.loads(gzip.decompress((P/SOURCES[0]).read_bytes()))
cams=json.loads(gzip.decompress((P/SOURCES[1]).read_bytes()))
by_path={x['path'].removesuffix('/camera.json'):x['camera'] for x in cams}
wrap=lambda x:np.arctan2(np.sin(x),np.cos(x))
rms=lambda x:float(np.sqrt(np.mean(np.asarray(x)**2))) if len(x) else None
basis=lambda q:np.column_stack([np.ones_like(q),np.sin(q),np.cos(q),np.sin(2*q),np.cos(2*q)])
output={'sources_sha256':{n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in SOURCES},'runs':[], 'method':{'camera_angle':'atan2(bob_x-pivot_x,pivot_y-bob_y), raw coordinates; stored theta_rad ignored','lag_convention':'encoder evaluation time = camera t + lag; negative means image is older than read timestamp','lag_fit':'first6s swing mode2 samples with |omega|>.5, jointly fit periodic angle map; frozen for later swing and all balance','geometry':'per-run constant plus sin(q),cos(q),sin(2q),cos(2q); an empirical disagreement map, not identified encoder correction','holdout':'later6-12s swing and all balance samples; no heldout refit','camera_filter':'detected, confidence>=.7, raw marker separation>50px, age<.2s','reference':'direct upright370 preserved; no gravity-zero inference'}}
for z in reports:
 r=z['report'];states=r['states'];c=by_path[r['path']]
 board=np.array([s['unwrapped_us'] for s in states])/1e6;host=np.array([s['received_ns'] for s in states])/1e9
 bt=board-board[0];ht=host-host[0];slope=np.polyfit(bt,ht,1)[0];base=np.median(host-slope*bt);st=base+slope*bt
 rawq=np.array([s['theta'] for s in states]);uq=np.unwrap(rawq);m=np.array([s['mode'] for s in states]);ww=np.array([s['omega'] for s in states]);xx=np.array([s['x'] for s in states]);vv=np.array([s['velocity'] for s in states])
 c=[a for a in c if a.get('detected') and a.get('confidence',0)>=.7 and a.get('pivot_px') and a.get('bob_px') and (a.get('age_since_host_read_s') or 0)<.2 and np.linalg.norm(np.subtract(a['bob_px'],a['pivot_px']))>50]
 ct=np.array([a['t'] for a in c]);pivot=np.array([a['pivot_px'] for a in c]);bob=np.array([a['bob_px'] for a in c]);cq=np.arctan2(bob[:,0]-pivot[:,0],pivot[:,1]-bob[:,1]);rel=ct-st[0]
 def values(lag):
  ti=ct+lag;idx=np.searchsorted(st,ti,side='right')-1;idx=np.clip(idx,0,len(st)-1);q=wrap(np.interp(ti,st,uq));w=np.interp(ti,st,ww);x=np.interp(ti,st,xx);v=np.interp(ti,st,vv);mode=m[idx];return q,w,x,v,mode,ti
 def train_for(lag):
  q,w,x,v,mode,ti=values(lag);train=(rel>.15)&(rel<6)&(mode==2)&(abs(w)>.5)&(ti>st[0])&(ti<st[-1]);return train
 train=train_for(-.02)
 def fun(par):
  lag=par[0];q,w,x,v,mode,ti=values(lag);return wrap(cq[train]-q[train]-basis(q[train])@par[1:])
 opts=[]
 for lag in [-.06,-.03,0,.03,.06]:
  q,*_=values(lag);d=wrap(cq[train]-q[train]);beta=np.linalg.lstsq(basis(q[train]),d,rcond=None)[0]
  fit=least_squares(fun,np.r_[lag,beta],bounds=(np.r_[-.12,[-.6]*5],np.r_[.12,[.6]*5]),loss='soft_l1',f_scale=.03,max_nfev=300)
  opts.append(fit)
 fit=min(opts,key=lambda z:sum(fun(z.x)**2));lag=float(fit.x[0]);beta=fit.x[1:];q,w,x,v,mode,ti=values(lag);d=wrap(cq-q);train=train_for(lag)
 # Final linear coefficients at fixed frozen lag, with a circular residual range far below pi.
 beta=np.linalg.lstsq(basis(q[train]),d[train],rcond=None)[0];const=float(np.mean(d[train]));pred=basis(q)@beta
 masks={'training_swing':train,'heldout_swing':(rel>=6)&(rel<12)&(mode==2),'balance':mode==3,'idle':mode==0}
 row={'run':z['result']['run'],'candidate':z['result']['candidate'],'reference':r['info']['encoder_upright_raw'],'clock_scale':float(slope),'clock_residual_95pct_s':np.quantile(host-st,[.025,.975]).tolist(),'lag_s':lag,'empirical_coefficients_rad':beta.tolist(),'train_constant_rad':const,'camera_dt_median_s':float(np.median(np.diff(ct))),'groups':{}}
 for name,mask in masks.items():
  mask=mask&(ti>st[0])&(ti<st[-1]);dd=d[mask];b={'samples':int(sum(mask))}
  if len(dd):b.update(raw_difference_mean_rad=float(np.mean(dd)),constant_train_corrected_rms_rad=rms(wrap(dd-const)),periodic_train_corrected_rms_rad=rms(wrap(dd-pred[mask])),raw_difference_p05_p95_rad=np.quantile(dd,[.05,.95]).tolist(),angle_range_rad=[float(min(q[mask])),float(max(q[mask]))],camera_mean_pivot_x=float(np.mean(pivot[mask,0])),camera_range_pivot_x=[float(min(pivot[mask,0])),float(max(pivot[mask,0]))],encoder_mean_v=float(np.mean(v[mask])))
  row['groups'][name]=b
 # Quasistatic points and direction-resolved bin errors expose timing/hysteresis.
 row['angle_bins']=[]
 for mid in np.arange(-np.pi+np.pi/8,np.pi,np.pi/4):
  mask=(abs(wrap(q-mid))<np.pi/8)&(rel<12)&((mode==2)|(mode==3));b={'mid_rad':float(mid),'samples':int(sum(mask))}
  if sum(mask):b.update(difference_mean_rad=float(np.mean(d[mask])),difference_std_rad=float(np.std(d[mask])))
  for label,sgn in [('positive',1),('negative',-1)]:
   mm=mask&(sgn*w>.5)
   if sum(mm)>=3:b[label+'_difference_mean_rad']=float(np.mean(d[mm]));b[label+'_samples']=int(sum(mm))
  row['angle_bins'].append(b)
 row['balance_pairs']=[{'t_s':float(t),'encoder_rad':float(a),'camera_raw_rad':float(b),'difference_rad':float(dd),'pivot_x_px':float(px),'step_x_m':float(sx)} for t,a,b,dd,px,sx in zip(rel[mode==3],q[mode==3],cq[mode==3],d[mode==3],pivot[mode==3,0],x[mode==3])]
 # Independent motion check: within auto, linear camera cart position against emitted step position.
 mask=(rel>0)&(rel<12);coef=np.polyfit(x[mask],pivot[mask,0],1);res=pivot[mask,0]-np.polyval(coef,x[mask]);row['cart_camera_on_step']={'samples':int(sum(mask)),'slope_px_per_m':float(coef[0]),'correlation':float(np.corrcoef(x[mask],pivot[mask,0])[0,1]),'residual_rms_px':rms(res)}
 output['runs'].append(row)
(P/'upright370-camera-comparison.json').write_text(json.dumps(output,indent=2)+'\n')
for r in output['runs']:
 print(r['run'],r['candidate'],'lagms',round(r['lag_s']*1000,1),'beta',np.round(r['empirical_coefficients_rad'],3),'groups', {k:(v['samples'],round(v['raw_difference_mean_rad'],3),round(v['constant_train_corrected_rms_rad'],3),round(v['periodic_train_corrected_rms_rad'],3)) for k,v in r['groups'].items() if v['samples']},'cart',r['cart_camera_on_step'])
