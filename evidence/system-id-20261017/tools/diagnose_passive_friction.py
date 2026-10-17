#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3"]
# ///
"""Offline diagnostic: separate initial-velocity sensitivity from model residual.

Uses frozen train02 coefficients/intervals. Old heldout01 is development evidence
once inspected here; any revised candidate needs new independent validation.
No physics or acceptance gate is changed. Centered derivative is an oracle
sensitivity diagnostic using future samples, never an admissible predictor.
"""
import argparse,gzip,hashlib,importlib.util,json,math
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise ValueError('output exists')
base=a.repo/'evidence/system-id-20261016/analysis';spec=importlib.util.spec_from_file_location('frozen',base/'heldout/evaluate_passive.py');ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev);fit,summary,manifest=ev.verify_freeze(base)
train=json.loads(gzip.decompress((base/'manual-ringdown-train-02-selected.json.gz').read_bytes()))['training_episodes'];data=json.loads(gzip.decompress((base.parent/'data/manual-ringdown-heldout-01-columns.json.gz').read_bytes()));annot=json.loads((base/'heldout/manual-ringdown-heldout-01-annotations.json').read_text());s,dupes=ev.canonical_states(data['states']);t=(s[:,0]-s[0,0])/1e6;q=np.unwrap(s[:,3]);valid=[]
for ep in annot['episodes']:
 lo,hi=ep['board_relative_s'];ix=(t>=lo)&(t<=hi);valid.append(dict(run_id=data['report']['raw_log_sha256'],episode_id=ep['episode_id'],t_s=t[ix].tolist(),theta_rad=q[ix].tolist()))
c=summary['magnetic_reports']['viscous']['parameters']['linear_coefficients'];cfg=summary['magnetic_reports']['viscous']['provenance']['config']

def score(eps,window,degree,centered=False):
 allerrors=[];episodes=[]
 for ts,qs,identity in fit.segments(eps,cfg):
  i=max(10,int(np.searchsorted(ts,ts[0]+.1)));errors=[];windows=0
  while i+8<len(ts):
   end=int(np.searchsorted(ts,ts[i]+cfg['prediction_horizon_s'],side='right'))
   if ts[end-1]-ts[i]<.9*cfg['prediction_horizon_s']:break
   lo=np.searchsorted(ts,ts[i]-window-1e-9);hi=np.searchsorted(ts,ts[i]+window+1e-9,side='right') if centered else i+1
   w=float(np.polyfit(ts[lo:hi]-ts[i],qs[lo:hi],degree)[-2]);pred=float(qs[i])
   for j in range(i+1,end):
    dt=ts[j]-ts[j-1];n=max(1,math.ceil(dt/.001));h=dt/n
    for _ in range(n):pred,w=fit.advance(pred,w,h,c)
    errors.append(math.atan2(math.sin(pred-qs[j]),math.cos(pred-qs[j])))
   windows+=1;i=end
  allerrors.extend(errors);ee=np.array(errors);episodes.append(dict(id=identity[-1],windows=windows,rmse_rad=float(np.sqrt(np.mean(ee**2))),p95_rad=float(np.quantile(abs(ee),.95))))
 e=np.array(allerrors);return dict(rmse_rad=float(np.sqrt(np.mean(e**2))),p95_rad=float(np.quantile(abs(e),.95)),samples=len(e),episodes=episodes)
# Constrain physical damping/friction by enumerating the active sets. This is
# training-only model exploration; the previous heldout is development data.
x,y=fit.matrix(fit.segments(train,cfg),cfg,'viscous_coulomb')
candidates=[]
for active in [(),(1,),(3,),(1,3)]:
    columns=[i for i in range(4) if i not in active]
    scale=np.linalg.norm(x[:,columns],axis=0)
    value=np.linalg.lstsq(x[:,columns]/scale,y,rcond=None)[0]/scale
    coef=np.zeros(4);coef[columns]=value
    if coef[1]<0 or coef[3]<0:continue
    candidates.append((float(np.mean((x@coef-y)**2)),active,coef))
loss,active,c=min(candidates,key=lambda item:item[0]);c=c.tolist()
out=dict(scope='training-constrained friction candidate; old validation is now development, new independent validation required',
    coefficients=c,active_zero_constraints=list(active),effective_length_m=9.81/math.hypot(c[0],c[2]),
    angle_offset_rad=math.atan2(-c[2],c[0]),angular_damping_per_s=c[1],coulomb_rad_per_s2=c[3],
    training_integral_nrmse=fit.nrmse(x,y,c),training=score(train,.04,2),old_validation_as_development=score(valid,.04,2),
    accepted=False,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
