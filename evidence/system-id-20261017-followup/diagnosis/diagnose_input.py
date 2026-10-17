#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3"]
# ///
"""DEVELOPMENT ONLY: audit sampled governor input and per-run equilibrium.

No network or device access; no fitting gates or accepted models are changed.
The former heldout recordings are already viewed and remain development here.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np


def velocity_input_integral(t,q,v):
    """Integral -v'(t)*cos(q(t))*phi(t) on piecewise-linear q and v.

Five-point Gauss quadrature per original interval preserves the measured
velocity increment without numerically differentiating either channel.
"""
    t,q,v=map(lambda a:np.asarray(a,float),(t,q,v))
    if t.ndim!=1 or len(t)<2 or q.shape!=t.shape or v.shape!=t.shape or np.any(np.diff(t)<=0):
        raise ValueError('matching strictly ordered vectors required')
    z,w=np.polynomial.legendre.leggauss(5);u=(z+1)/2;w=w/2
    tx=t[:-1,None]+np.diff(t)[:,None]*u
    qx=q[:-1,None]+np.diff(q)[:,None]*u
    s=(tx-t[0])/(t[-1]-t[0]);phi=s*s*(1-s)**2
    return float(np.sum(-np.diff(v)*np.sum(np.cos(qx)*phi*w,axis=1)))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rms(v):return float(np.sqrt(np.mean(np.asarray(v)**2)))


def analyze(repo):
    repo=Path(repo).resolve();sys.path.insert(0,str(repo/'src'))
    from cartpole_sdk.identification.fit import FitConfig,_segments,_windows,_solve,_integral
    source=repo/'evidence/system-id-20261017/analysis/pulse-batch-secondary-historic-offset.json'
    batch=json.loads(source.read_text());cfg=replace(FitConfig(),angle_offset_rad=batch['angle_offset']['value_rad'])
    inputs=batch['inputs'];out=dict(schema='cartpole-input-diagnosis-development-v1',status='DEVELOPMENT; no acceptance or model promotion',source_report_sha256=sha(source),tool_sha256=sha(__file__),raw_inputs=[],sampling=[],variants={})
    groups={}
    out['static_camera_diagnostic']=[]
    for role in ('training','validation'):
        rows=[dict(r) for r in batch['canonical_batches'][role]]
        for item in inputs[role]:
            name=Path(item['spec']).name
            matches=list((repo/'evidence/system-id-20261017').glob('raw-pulse-*/*/'+name+'.gz'))
            if len(matches)!=1:raise ValueError(f'ambiguous source {name}')
            path=matches[0];data=gzip.decompress(path.read_bytes())
            raw_sha=hashlib.sha256(data).hexdigest()
            if raw_sha!=item['identity']['sha256']:raise ValueError('source content changed')
            records=list(map(json.loads,data.splitlines()))
            state={r['state']['unwrapped_us']:r['state'] for r in records if r['type']=='state'}
            selected=[r for r in rows if r['run_id']==raw_sha]
            for r in selected:
                us=round((r['t_s']-item['analysis_start_s']+item['original_start_s'])*1e6)
                r['velocity']=state[us]['velocity'];r['run_label']=path.parent.name
            enabled=[r for r in selected if r['valid']]
            t=np.array([r['t_s'] for r in enabled]);v=np.array([r['velocity'] for r in enabled]);a=np.array([r['cart_acceleration_m_s2'] for r in enabled]);q=np.unwrap([r['theta_rad'] for r in selected]);dt=np.diff(t);dv=np.diff(v);aint=(a[:-1]+a[1:])*dt/2
            out['sampling'].append(dict(run=path.parent.name,role=role,enabled_samples=len(t),median_dt_s=float(np.median(dt)),max_dt_s=float(max(dt)),velocity_increment_rms_m_s=rms(dv),sampled_input_increment_error_rms_m_s=rms(dv-aint),relative_increment_error=rms(dv-aint)/rms(dv),max_cumulative_velocity_error_m_s=float(max(abs(np.cumsum(aint)-(v[1:]-v[0])))),initial_raw_theta_rad=float(np.median(q[:20])),tail_raw_theta_rad=float(np.median(q[-30:]))))
            out['raw_inputs'].append(dict(path=str(path.relative_to(repo)),sha256_decompressed=raw_sha))
            camera_path=path.parent/'vision.ndjson.gz'
            camera_bytes=gzip.decompress(camera_path.read_bytes())
            report=json.loads((path.parent/'report.json').read_text())
            camera_hash=hashlib.sha256(camera_bytes).hexdigest()
            if camera_hash!=report['camera']['sha256']:raise ValueError('camera source content changed')
            references=[r for r in records if r.get('type')=='ringdown_reference']
            origin=references[0]['board_ns']/1e9
            st=list(state.values());bt=np.array([r['unwrapped_us']/1e6 for r in st]);ht=np.array([r['received_ns']/1e9 for r in st]);rawq=np.unwrap([r['theta'] for r in st])
            offset=float(np.median(ht-bt));frames=[]
            for r in map(json.loads,camera_bytes.splitlines()):
                z=r['vision']
                if z.get('detected') and not z.get('stale') and not z.get('worker_error') and z.get('confidence',0)>=.5 and isinstance(z.get('image_angle_rad'),(float,int)):
                    frames.append((z['t']-offset-origin,-z['image_angle_rad']))
            vf=np.array(frames);windows=[]
            for lo,hi in ((-.25,-.05),(3.15,3.65)):
                sm=(bt-origin>=lo)&(bt-origin<=hi);cm=(vf[:,0]>=lo)&(vf[:,0]<=hi)
                windows.append(dict(interval_relative_to_pulse_s=[lo,hi],encoder_samples=int(sum(sm)),camera_samples=int(sum(cm)),encoder_raw_median_rad=float(np.median(rawq[sm])),encoder_raw_span_rad=float(np.ptp(rawq[sm])),negative_image_angle_median_rad=float(np.median(vf[cm,1])),negative_image_angle_iqr_rad=float(np.quantile(vf[cm,1],.75)-np.quantile(vf[cm,1],.25))))
            out['static_camera_diagnostic'].append(dict(run=path.parent.name,source_sha256_decompressed=camera_hash,windows=windows,interpretation='Descriptive same-host receipt proxy with unit-slope median offset; no fitted angle gain/offset; no independent calibration or exposure-time alignment. Last0.5s is a tail, not proof of physical rest.'))
        groups[role]=_segments(rows,'magnetic','commanded',cfg)
    for kind in ('sampled_acceleration','velocity_increments'):
        candidates=[]
        for delay in cfg.delay_candidates_s:
            role_data={}
            for role,segs in groups.items():
                x,y=_windows(segs,delay,cfg);x=x.copy();labels=[];starts=[];extra=[];k=0
                for t,q,a,rows in segs:
                    velocity=np.array([r['velocity'] for r in rows]);start=t[0]+max(cfg.delay_candidates_s)
                    while start+cfg.window_s<=t[-1]+1e-10:
                        ix=np.flatnonzero((t>=start-1e-10)&(t<=start+cfg.window_s+1e-10))
                        if len(ix)>=8:
                            tw=t[ix];qw=q[ix];s=(tw-tw[0])/(tw[-1]-tw[0]);phi=s*s*(1-s)**2
                            if kind=='velocity_increments':x[k,2]=velocity_input_integral(tw,qw,np.interp(tw-delay,t,velocity))
                            labels.append(rows[0]['run_label']);starts.append(float(start-t[0]));extra.append(_integral(np.cos(qw)*phi,tw));k+=1
                        start+=cfg.window_s
                if k!=len(y):raise AssertionError('window identity mismatch')
                role_data[role]=(x,y,labels,starts,np.array(extra))
            x,y,*_=role_data['training'];coef,_,rank,condition=_solve(x,y);loss=rms(y-x@coef)
            candidates.append((loss,delay,coef,condition,role_data))
        loss,delay,coef,condition,data=min(candidates,key=lambda z:z[0]);x,y,labels,starts,extra=data['training'];vx,vy,*_=data['validation'];alpha,gamma,beta=coef
        result=dict(delay_s=delay,parameters=dict(effective_length_m=float(9.81/alpha),angular_damping_per_s=float(gamma),input_gain=float(beta*9.81/alpha)),training_nrmse=loss/float(np.std(y)),old_validation_development_nrmse=rms(vy-vx@coef)/float(np.std(vy)),per_training_run=[])
        residual=y-x@coef
        for label in dict.fromkeys(labels):
            mask=np.array(labels)==label
            result['per_training_run'].append(dict(run=label,windows=int(sum(mask)),residual_rms=rms(residual[mask]),target_rms=rms(y[mask]),mean_residual=float(np.mean(residual[mask])),initial_input_window_residuals=[float(r) for r,s in zip(residual[mask],np.array(starts)[mask]) if s<1]))
        # Nuisance diagnostic only: run-specific constant gravity offsets can
        # represent sensor drift, rest-angle friction or model error, not just zero.
        run_labels=list(dict.fromkeys(labels));d=np.column_stack([extra*(np.array(labels)==label) for label in run_labels]);xx=np.column_stack([x,d]);c,_,rank,condition=_solve(xx,y)
        result['training_run_offset_nuisance_diagnostic']=dict(nrmse=rms(y-xx@c)/float(np.std(y)),condition=condition,effective_length_m=float(9.81/c[0]),angular_damping_per_s=float(c[1]),input_gain=float(c[2]*9.81/c[0]),per_run_additional_phase_rad={label:float(math.atan2(-c[3+i],c[0])) for i,label in enumerate(run_labels)},interpretation='Same-training-run nuisance fit; no validation prediction and no calibration assertion.')
        out['variants'][kind]=result
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3]);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    if args.output.exists():raise FileExistsError('preserve old output; choose a new path')
    result=analyze(args.repo);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result['variants'],indent=2))
if __name__=='__main__':main()
