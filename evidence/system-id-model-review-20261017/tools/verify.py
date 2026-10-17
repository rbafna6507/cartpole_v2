#!/usr/bin/env python3
"""Numerical and causality verification for the offline diagnostic methods."""
import argparse,gzip,json,math,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from dynamics import initial_state,ode_solution
from trajectory import trajectory_sensitivity

def main():
    p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--baseline-fit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    checks={};c=np.array([60.,.35,6.,1.3,.006]);t=np.arange(0,.501,.004);z=np.array([3.5,-1.]);q,jac=trajectory_sensitivity(t,z,c);x=np.r_[c,z];errors=[]
    for k in range(len(x)):
        h=1e-5;xp=x.copy();xm=x.copy();xp[k]+=h;xm[k]-=h
        d=(ode_solution(t,xp[-2:],xp[:-2])[0]-ode_solution(t,xm[-2:],xm[:-2])[0])/(2*h);errors.append(float(np.max(abs(d-jac[:,k]))))
    assert max(errors)<1e-4,errors;checks['sensitivity_max_absolute_error']=max(errors)
    t=np.arange(0,1.001,.004);clean=ode_solution(t,[3.6,0.],c);i=125;s=initial_state(t,clean[0],i,c,'history_rawq:0.20')
    assert np.max(abs(s-clean[:,i]))<1e-5;checks['exact_trajectory_state_error']=float(np.max(abs(s-clean[:,i])))
    changed=clean[0].copy();changed[i+1:]+=np.arange(len(changed)-i-1)*.1;s2=initial_state(t,changed,i,c,'history_rawq:0.20')
    assert np.array_equal(s,s2);checks['future_samples_do_not_affect_initialization']=True
    rng=np.random.default_rng(4);noisy=clean[0]+rng.normal(0,.005,len(t));old=initial_state(t,noisy,i,c,'original');new=initial_state(t,noisy,i,c,'history_rawq:0.20')
    assert abs(new[1]-clean[1,i])<abs(old[1]-clean[1,i]);checks['noisy_synthetic_velocity_errors_rad_s']={'old':float(abs(old[1]-clean[1,i])),'new':float(abs(new[1]-clean[1,i]))}
    report=json.loads(gzip.decompress(a.comparison.read_bytes()));baseline=json.loads(a.baseline_fit.read_text());actual=report['results'][0]['results']['validation']['short'];expected=baseline['validation']
    assert math.isclose(math.radians(actual['rms_deg']),expected['prediction_rmse_rad'],abs_tol=1e-9);assert actual['samples']==expected['prediction_samples'];checks['original_solver_score_reproduced']=True
    assert len({r['results']['validation']['short']['samples'] for r in report['results']})==1;checks['all_short_comparisons_use_same_sample_count']=True
    for r in report['results']:
        c=r['coefficients'];assert c[1]>=0 and all(v>=0 for v in c[3:]);w=np.linspace(-20,20,1001);loss=-c[1]*w*w
        if len(c)>3:loss-=c[3]*w*np.tanh(w/.05)
        if len(c)>4:loss-=c[4]*w*w*abs(w)
        assert np.max(loss)<=1e-12
    checks['all_friction_candidates_dissipate_energy']=True
    a.output.write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
