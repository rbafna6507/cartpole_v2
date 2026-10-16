#!/usr/bin/env python3
"""Conditional passive-tail diagnostic, never an accepted identification report.

Zero commanded/step-derived motion does NOT establish physically fixed cart.
No device imports or calls. Reads historical recordings only.
"""
import json, math, hashlib
from pathlib import Path
from dataclasses import replace
import numpy as np
import fit
BASE=Path(__file__).resolve().parent
plan=json.loads((BASE/'analysis-plan.json').read_text())
cfg=replace(fit.FitConfig(),angle_offset_rad=plan['runs']['a1']['settling']['mean_down_angle'])
data={}
for key,desc in plan['runs'].items():
    path=next(Path(desc['path']).glob('rig-*.jsonl'))
    records=[json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    session=next(r['session'] for r in records if r['type']=='session')
    groups=[];active=[];seen=set()
    for r in records:
        if r['type']!='state':continue
        s=r['state']
        if s['unwrapped_tick'] in seen:continue
        seen.add(s['unwrapped_tick'])
        eligible=s['mode']==0 and s['flags']&5==5 and not s['flags']&2 and not s['fault'] and s['velocity']==0 and s['acceleration']==0
        if eligible:active.append(s)
        elif active:groups.append(active);active=[]
    if active:groups.append(active)
    selected=groups[-1]
    rows=[dict(t_s=s['unwrapped_us']/1e6,theta_rad=s['theta'],cart_acceleration_m_s2=0.,valid=True,source='magnetic',acceleration_kind='commanded',run_id=session['session_id'],clock_id=session['clock_id'],calibration_id='executor-v6-measuredrail:upright:330',frame_id='encoder-upright/cart-home:9') for s in selected]
    seg=fit._segments(rows,'magnetic','commanded',cfg)
    x,y=fit._windows(seg,0.,cfg)
    coef,_,rank,condition=fit._solve(x[:,:2],y)
    nuisance_x,_=fit._windows(seg,0.,cfg,include_offset=True)
    nc,_,nr,nk=fit._solve(nuisance_x[:,[0,1,3]],y)
    data[key]=dict(rows=rows,segments=seg,coef=coef,x=x,y=y,summary=dict(raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),canonical_sha256=fit._hash(rows),duration_s=rows[-1]['t_s']-rows[0]['t_s'],samples=len(rows),window_count=len(y),rank=rank,condition=condition,conditional_effective_length_m=9.81/float(coef[0]),conditional_gamma_per_s=float(coef[1]),integral_nrmse=float(np.sqrt(np.mean((y-x[:,:2]@coef)**2))/np.std(y)),nuisance_gravity_offset_rad=math.atan2(-float(nc[2]),float(nc[0])),nuisance_rank=nr,nuisance_condition=nk))

coef=np.array([data['a1']['coef'][0],data['a1']['coef'][1],0.])
validation={}
for key in ['a2','b1','c1','c2','c3']:
    d=data[key]
    check=fit._predict(d['segments'],coef,0.,cfg)
    check['integral_nrmse']=float(np.sqrt(np.mean((d['y']-d['x']@coef)**2))/np.std(d['y']))
    validation[key]=check
result=dict(status='diagnostic only, not accepted or recommended',not_acceptance=True,hardware_activity=False,offset_rad=cfg.angle_offset_rad,offset_source='A1 recorded pretrial only; identically applied to all tails; no independently established global angle calibration',training='a1',validation=validation,per_run_independent_fits_for_repeatability_only={k:d['summary'] for k,d in data.items()},limitations=['Only four seconds/~11 windows per tail: below 20 default training windows','Cart motor disabled: physical cart stationarity unverified; step-derived x fixed is insufficient','No forcing, so input gain and delay structurally unidentifiable','The native fitter cannot accept these zero-input records; no default gates changed','Post-return tail initial state may include mechanical settling and nonviscous effects'],source_hashes={p:hashlib.sha256((BASE/p).read_bytes()).hexdigest() for p in ['passive_tails.py','fit.py','rig_logs.py','analysis-plan.json']})
(BASE/'results'/'passive-tail-diagnostic.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,allow_nan=False))
