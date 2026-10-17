#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3", "matplotlib>=3.8,<4"]
# ///
"""Offline passive model development. No hardware or model export.

Run from the repository with uv run --locked --extra id --extra plots
--with scipy==1.16.3 python THIS_FILE --help. --validation is development data
once compared across candidate models here; reserve an untouched later recording.
"""
import argparse,gzip,hashlib,json,math,sys
from pathlib import Path
import numpy as np
from scipy.optimize import lsq_linear
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from cartpole_sdk.identification import workflow,passive,release_review
from dynamics import score,initial_state,ode_solution,metrics
from trajectory import fit_trajectory


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def continuous(parts,c,warmup):
    errors=[];episodes=[]
    for t,q,identity in parts:
        i=int(np.searchsorted(t,t[0]+warmup))
        if i+1>=len(t):raise ValueError('episode shorter than declared initialization history')
        state=initial_state(t,q,i,c,'history_rawq:'+str(warmup));pred=ode_solution(t[i:],state,c)[0]
        e=np.arctan2(np.sin(pred[1:]-q[i+1:]),np.cos(pred[1:]-q[i+1:]));errors.extend(e)
        episodes.append(dict(episode_id=identity[1],metrics=metrics(e),t=t[i:].tolist(),observed=q[i:].tolist(),predicted=pred.tolist()))
    return dict(warmup_s=warmup,metrics=metrics(errors),episodes=episodes)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for role in ['training','validation']:
        p.add_argument('--'+role,required=True,type=Path);p.add_argument('--'+role+'-annotations',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--trajectory-fits',action='store_true',help='Also test full-training-decay viscous, dry-friction and quadratic-drag fits.')
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    eps={};ids={};parts={};cfg=dict(passive.DEFAULT_GATES,window_s=.35);quality={}
    for role in ['training','validation']:
        source=getattr(a,role);ann=getattr(a,role+'_annotations');eps[role],ids[role]=workflow.passive_episodes(str(source),ann);parts[role]=passive.segments(eps[role],cfg)
        quality[role]=release_review.analyze_releases(str(source),ann)
    workflow._independent(ids['training'],ids['validation'])
    x,y=passive.matrix(parts['training'],cfg,'viscous');base,rank,condition,cov=passive.solve(x,y)
    if base is None or rank<3:raise ValueError('viscous model not identifiable')
    models={'weak_viscous':base};model_fits={}
    x,y=passive.matrix(parts['training'],cfg,'viscous_coulomb');sol=lsq_linear(x,y,bounds=([-200,0,-100,0],[200,5,100,20]),tol=1e-12)
    models['weak_coulomb']=sol.x;model_fits['weak_coulomb']=dict(weak_windows=len(y),rank=int(np.linalg.matrix_rank(x)),integral_nrmse=passive.nrmse(x,y,sol.x),success=bool(sol.success))
    if len(y)<cfg['min_windows'] or np.linalg.matrix_rank(x)<4:raise ValueError('Coulomb model has insufficient identifiable training windows')
    if a.trajectory_fits:
        for name in ['viscous','coulomb','quadratic']:
            models['trajectory_'+name],model_fits['trajectory_'+name]=fit_trajectory(parts['training'],base,name)
    report=dict(schema='cartpole-passive-development-v1',accepted=False,model_exported=False,production_method_changed=False,source_identities=ids,camera_quality=quality,model_fits=model_fits,results=[],frozen_gates=cfg,
        method=dict(history_s=.2,history_uses_future_samples=False,short_forecast_horizon_s=.5,continuous_initialization_s=[.25,.5],dry_friction='smooth Coulomb: c*tanh(omega/0.05)',quadratic_drag='d*omega*abs(omega)',solver='SciPy DOP853; analytical sensitivities for full-training-trajectory fit'),
        limitations=['All comparison data are development evidence, not a fresh final holdout.','Camera/pose quality failures remain failures; lower RMS does not override them.','Continuous predictions exclude an explicitly reported initialization interval and receive no subsequent observations.','No source correction, hardware access, firmware change, or simulation export.'],
        tool_hashes={q.name:sha(q) for q in Path(__file__).parent.glob('*.py')})
    a.output.mkdir(parents=True)
    for name,c in models.items():
        methods=['original','history_rawq:0.20'] if name=='weak_viscous' else ['history_rawq:0.20']
        for method in methods:
            row=dict(model=name,initializer=method,coefficients=c.tolist(),results={})
            for role in parts:
                row['results'][role]=score(parts[role],c,method,trace=True)
                if method!='original':row['results'][role]['continuous_after_history']=[continuous(parts[role],c,w) for w in [.25,.5]]
            report['results'].append(row)
            print(json.dumps(dict(model=name,initializer=method,training=row['results']['training']['short'],development=row['results']['validation']['short'])),flush=True)
    raw=json.dumps(report,indent=2,allow_nan=False).encode();(a.output/'report.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    summary={k:v for k,v in report.items() if k not in ['results','camera_quality']};summary['camera_quality']={r:dict(passed=q['passed'],poses_verified=q['all_release_poses_verified'],reasons=q['reasons']) for r,q in quality.items()}
    summary['results']=[dict(model=r['model'],initializer=r['initializer'],coefficients=r['coefficients'],metrics={role:dict(short=v['short'],continuous=v['continuous'],continuous_after_history=[dict(warmup_s=c['warmup_s'],metrics=c['metrics']) for c in v.get('continuous_after_history',[])]) for role,v in r['results'].items()}) for r in report['results']]
    summary['report_sha256']=sha(a.output/'report.json.gz');workflow.write_json(a.output/'summary.json',summary)
if __name__=='__main__':main()
