#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Refit the preselected dry-friction model on explicit development recordings.
Does not read final holdout data, relax quality gates or export a simulator.
"""
import argparse,datetime,hashlib,json,math,sys
from pathlib import Path
import numpy as np
from scipy.optimize import lsq_linear
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from cartpole_sdk.identification import workflow,passive,release_review

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,action='append',required=True);p.add_argument('--annotations',type=Path,action='append',required=True);p.add_argument('--prior-freeze',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    if len(a.source)!=len(a.annotations):raise ValueError('one annotation per source required')
    eps=[];ids=[];quality=[];seen=set();cfg=dict(passive.DEFAULT_GATES,window_s=.35)
    for src,ann in zip(a.source,a.annotations):
        ee,identity=workflow.passive_episodes(str(src),ann)
        if identity['sha256'] in seen:raise ValueError('duplicate recording')
        seen.add(identity['sha256']);ids.append(identity);eps.extend(ee);quality.append(release_review.analyze_releases(str(src),ann))
    parts=passive.segments(eps,cfg);x,y=passive.matrix(parts,cfg,'viscous_coulomb');rank=int(np.linalg.matrix_rank(x));scales=np.linalg.norm(x,axis=0);condition=float(np.linalg.cond(x/scales))
    if len(y)<cfg['min_windows'] or rank!=4 or condition>cfg['max_condition']:raise ValueError('insufficient identifiable training data')
    sol=lsq_linear(x,y,bounds=([-200,0,-100,0],[200,5,100,20]),tol=1e-12);c=sol.x
    if not sol.success:raise ValueError(sol.message)
    length=9.81/math.hypot(c[0],c[2]);offset=math.atan2(-c[2],c[0])
    if not .05<=length<=1.5 or abs(offset)>.35:raise ValueError('physical parameter bounds failed')
    prior=workflow.read_json(a.prior_freeze);models=[m for m in prior['models'] if m['model']=='weak_viscous'];old=next(m for m in prior['models'] if m['model']=='weak_coulomb');models.append(dict(old,model='batch5_weak_coulomb'));models.append(dict(model='weak_coulomb',initializer='history_rawq:0.20',coefficients=c.tolist()))
    report=dict(schema='cartpole-experimental-passive-freeze-v2',created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),reason='User preference: later recordings are primary. Same previously selected friction law and initialization, refit once on both completed batch6 recordings before inspecting any batch7 model errors. Batch7 is final holdout. Dataset directory/label mismatch is resolved by raw hashes.',models=models,source_identities=ids,training_quality=quality,development_source_sha256=sorted(set(prior['development_source_sha256'])|seen),training=dict(episodes=len(eps),weak_windows=len(y),rank=rank,condition=condition,integral_nrmse=passive.nrmse(x,y,c)),parameters=dict(effective_length_m=length,viscous_per_s=float(c[1]),coulomb_rad_per_s2=float(c[3]),local_angle_offset_rad=offset),continuous_initialization_s=[.25,.5],short_prediction_horizon_s=.5,short_rms_limit_rad=.08,short_p95_limit_rad=.15,final_holdout_reserved='batch7; do not retune after scoring',method_hashes={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['dynamics.py','trajectory.py','compare.py','evaluate.py','refit_latest.py']},prior_freeze_sha256=hashlib.sha256(a.prior_freeze.read_bytes()).hexdigest(),production_export_allowed=False,accepted=False)
    workflow.write_json(a.output,report);print(json.dumps(dict(parameters=report['parameters'],training=report['training']),indent=2))
if __name__=='__main__':main()
