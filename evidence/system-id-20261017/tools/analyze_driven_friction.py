#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3"]
# ///
"""Exploratory training-only viscous/regularized-Coulomb comparison.

The already inspected 30 mm pair is DEVELOPMENT data here, not fresh validation.
No model is accepted/promoted and no live configuration is changed.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
from itertools import combinations
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
from cartpole_sdk.identification.fit import FitConfig,_segments,_windows,_integral
from cartpole_sdk.identification.workflow import digest,read_json,write_json,provenance

HISTORIC_OFFSET_RAD=-.11310915597373176
FRICTION_WIDTH_RAD_S=.05
MAX_COULOMB_RAD_S2=20.


def constrained_solve(x,y,cfg):
    """Enumerate active faces of the small convex linear-inequality LS problem."""
    x=np.asarray(x,float);y=np.asarray(y,float);n=x.shape[1]
    if n not in (3,4) or len(y)<n or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError('finite full-rank3/4-column weak equation required')
    scale=np.linalg.norm(x,axis=0)
    if np.any(scale<1e-12) or np.linalg.matrix_rank(x/scale)<n:raise ValueError('rank deficient weak equation')
    lower=cfg.gravity_m_s2/cfg.length_bounds_m[1];upper=cfg.gravity_m_s2/cfg.length_bounds_m[0]
    constraints=[]
    def add(name,coeff,bound):constraints.append((name,[*coeff,*([0.] if n==4 else [])],bound))
    add('alpha_min',[-1.,0.,0.],-lower);add('alpha_max',[1.,0.,0.],upper)
    add('gamma_min',[0.,-1.,0.],0.);add('gamma_max',[0.,1.,0.],cfg.max_damping_per_s)
    add('gain_min',[cfg.gain_bounds[0],0.,-cfg.gravity_m_s2],0.)
    add('gain_max',[-cfg.gain_bounds[1],0.,cfg.gravity_m_s2],0.)
    if n==4:constraints.extend([('coulomb_min',[0.,0.,0.,-1.],0.),('coulomb_max',[0.,0.,0.,1.],MAX_COULOMB_RAD_S2)])
    g=np.array([r[1] for r in constraints])/scale;h=np.array([r[2] for r in constraints]);a=x/scale
    normal=a.T@a;target=a.T@y;best=None
    for count in range(n+1):
        for active in combinations(range(len(h)),count):
            selected=g[list(active)];bounds=h[list(active)]
            matrix=np.block([[normal,selected.T],[selected,np.zeros((count,count))]])
            try:solution=np.linalg.solve(matrix,np.r_[target,bounds])[:n]
            except np.linalg.LinAlgError:continue
            if np.any(g@solution-h>1e-8):continue
            coef=solution/scale
            # Roundoff at a selected constraint is not a physical negative term.
            coef[0]=np.clip(coef[0],lower,upper);coef[1]=np.clip(coef[1],0.,cfg.max_damping_per_s)
            coef[2]=np.clip(coef[2],cfg.gain_bounds[0]*coef[0]/cfg.gravity_m_s2,cfg.gain_bounds[1]*coef[0]/cfg.gravity_m_s2)
            if n==4:coef[3]=np.clip(coef[3],0.,MAX_COULOMB_RAD_S2)
            loss=float(np.mean((y-x@coef)**2))
            if best is None or loss<best[0]:best=(loss,coef,[constraints[i][0] for i in active])
    if best is None:raise ValueError('no feasible constrained fit')
    loss,coef,active=best
    return coef,dict(mean_squared_integral_residual=loss,integral_nrmse=math.sqrt(loss)/max(float(np.std(y)),1e-12),
        condition=float(np.linalg.cond(a)),active_constraints=active)


def friction_windows(segments,delay,cfg):
    """Reuse original weak columns exactly; derivative enters only friction feature."""
    x,y=_windows(segments,delay,cfg);features=[]
    for t,q,_,_ in segments:
        rate=[]
        for i in range(len(t)):
            lo=min(max(0,i-3),len(t)-7);hi=lo+7
            rate.append(float(np.polyfit(t[lo:hi]-t[i],q[lo:hi],2)[-2]))
        friction=np.tanh(np.asarray(rate)/FRICTION_WIDTH_RAD_S)
        start=t[0]+max(cfg.delay_candidates_s)
        while start+cfg.window_s<=t[-1]+1e-10:
            indices=np.flatnonzero((t>=start-1e-10)&(t<=start+cfg.window_s+1e-10))
            if len(indices)>=8:
                tw=t[indices];s=(tw-tw[0])/(tw[-1]-tw[0]);phi=s*s*(1-s)**2
                features.append(-_integral(friction[indices]*phi,tw))
            start+=cfg.window_s
    if len(features)!=len(y):raise ValueError('friction/base window alignment changed')
    return np.column_stack([x,np.asarray(features)]),y


def fit_training(rows,cfg,*,coulomb):
    segments=_segments(rows,'magnetic','commanded',cfg);best=None;profile=[]
    for delay in cfg.delay_candidates_s:
        x,y=friction_windows(segments,delay,cfg) if coulomb else _windows(segments,delay,cfg)
        if len(y)<cfg.min_windows:raise ValueError('insufficient unchanged weak windows')
        coef,stats=constrained_solve(x,y,cfg);profile.append(dict(delay_s=delay,**stats))
        if best is None or stats['mean_squared_integral_residual']<best[0]:
            best=(stats['mean_squared_integral_residual'],delay,coef,stats,len(y))
    _,delay,coef,stats,count=best
    if not coulomb:coef=np.r_[coef,0.]
    length=cfg.gravity_m_s2/coef[0]
    return dict(coefficients=coef.tolist(),parameters=dict(effective_length_m=float(length),
        commanded_input_gain=float(coef[2]*length),angular_damping_per_s=float(coef[1]),
        coulomb_rad_s2=float(coef[3]),delay_s=delay),training=dict(window_count=count,segment_count=len(segments),**stats),delay_profile=profile)


def predict(segments,coef,delay,cfg):
    """Same causal initial-rate rule as base fitter;2ms RK4 resolves regularization."""
    alpha,gamma,beta,coulomb=coef;errors=[];count=0
    def rhs(t,y,ts,acc):
        q,w=y
        return np.array([w,alpha*math.sin(q)-gamma*w-beta*float(np.interp(t-delay,ts,acc))*math.cos(q)-coulomb*math.tanh(w/FRICTION_WIDTH_RAD_S)])
    for ts,q,acc,rows in segments:
        i=int(np.searchsorted(ts,ts[0]+max(cfg.delay_candidates_s)))
        while i+8<len(ts):
            end=int(np.searchsorted(ts,ts[i]+cfg.prediction_horizon_s,side='right'))
            if end>len(ts) or ts[end-1]-ts[i]<cfg.prediction_horizon_s*.9:break
            if rows[i].get('omega_rad_s') is not None:omega=float(rows[i]['omega_rad_s'])
            else:
                if i<6:i=6;continue
                omega=float(np.polyfit(ts[i-6:i+1]-ts[i],q[i-6:i+1],2)[-2])
            state=np.array([q[i],omega])
            for j in range(i+1,end):
                h=ts[j]-ts[j-1];steps=max(1,math.ceil(h/.002));h/=steps;t=ts[j-1]
                for _ in range(steps):
                    k1=rhs(t,state,ts,acc);k2=rhs(t+h/2,state+h*k1/2,ts,acc)
                    k3=rhs(t+h/2,state+h*k2/2,ts,acc);k4=rhs(t+h,state+h*k3,ts,acc)
                    state+=h*(k1+2*k2+2*k3+k4)/6;t+=h
                errors.append(math.atan2(math.sin(state[0]-q[j]),math.cos(state[0]-q[j])))
            count+=1;i=end
    values=np.asarray(errors)
    return dict(prediction_windows=count,prediction_samples=len(errors),
        prediction_rmse_rad=float(np.sqrt(np.mean(values**2))) if len(values) else None,
        prediction_p95_rad=float(np.quantile(np.abs(values),.95)) if len(values) else None,horizon_s=cfg.prediction_horizon_s)


def study(batch):
    content=dict(batch);pin=content.pop('content_sha256',None)
    if pin!=digest(content) or batch.get('canonical_sha256')!=digest(batch['canonical_batches']):raise ValueError('batch content hash mismatch')
    if batch['angle_offset']['value_rad']!=HISTORIC_OFFSET_RAD:raise ValueError('requires predeclared historical phase batch')
    cfg=replace(FitConfig(),angle_offset_rad=HISTORIC_OFFSET_RAD);models={}
    training=batch['canonical_batches']['training'];development=batch['canonical_batches']['validation']
    for name,coulomb in [('viscous',False),('regularized_coulomb_viscous',True)]:
        model=fit_training(training,cfg,coulomb=coulomb);coef=model['coefficients'];delay=model['parameters']['delay_s'];scores=[]
        for role,rows in [('training',training),('development',development)]:
            segments=_segments(rows,'magnetic','commanded',cfg)
            model[role+'_prediction']=predict(segments,coef,delay,cfg)
            x,y=friction_windows(segments,delay,cfg) if coulomb else _windows(segments,delay,cfg)
            model[role+'_integral_nrmse']=float(np.sqrt(np.mean((y-x@np.asarray(coef[:x.shape[1]]))**2))/max(float(np.std(y)),1e-12))
            for run in sorted({r['run_id'] for r in rows}):
                selected=_segments([r for r in rows if r['run_id']==run],'magnetic','commanded',cfg)
                scores.append(dict(role=role,run_id=run,**predict(selected,coef,delay,cfg)))
        model['per_run_predictions']=scores;models[name]=model
    report=dict(schema='cartpole-driven-friction-exploration-v1',accepted=False,recommended_model=None,
        batch_content_sha256=pin,canonical_sha256=batch['canonical_sha256'],models=models,
        training_only_estimation=True,previous_validation_reclassified_as_development=True,
        configuration=dict(angle_offset_rad=HISTORIC_OFFSET_RAD,rate_window_samples=7,rate_polynomial_order=2,
            friction_law='-c*tanh(omega/width)',width_rad_s=FRICTION_WIDTH_RAD_S,max_coulomb_rad_s2=MAX_COULOMB_RAD_S2,
            length_bounds_m=cfg.length_bounds_m,gain_bounds=cfg.gain_bounds,gamma_bounds_per_s=[0,cfg.max_damping_per_s],
            window_s=cfg.window_s,delay_candidates_s=cfg.delay_candidates_s),
        limitations=['Historical phase remains a local diagnostic, not independent global calibration.',
            'MCU acceleration is commanded input; effective input gain is not metric cart calibration.',
            'Regularized Coulomb is an exploratory approximation and omits static stiction, backlash and sensor nonlinearity.',
            'Training derivative is used only to construct the friction regressor; weak equation does not differentiate acceleration.',
            'Both30mm development runs clamped2samples each; original protocol deviation remains.',
            'No fresh validation remains after this exploratory comparison; no acceptance or model promotion.'],
        provenance=dict(tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),sdk=provenance()))
    report['content_sha256']=digest(report);return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True,help='Frozen secondary historic-offset batch JSON.')
    parser.add_argument('--output',type=Path,required=True,help='New immutable exploratory result JSON.')
    args=parser.parse_args(argv)
    if args.output.exists():parser.error('output exists; preserve earlier evidence')
    report=study(read_json(args.batch));write_json(args.output,report)
    import json
    print(json.dumps(dict(output=str(args.output),accepted=False,models={name:dict(parameters=m['parameters'],training=m['training'],development=m['development_prediction']) for name,m in report['models'].items()}),indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
