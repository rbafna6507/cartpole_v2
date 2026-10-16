"""Exploratory training-only residual diagnostics; no accepted-fit or calibration output."""
import argparse,hashlib,importlib.util,json,math,sys
from dataclasses import replace
from pathlib import Path
import numpy as np
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[3]);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
if args.output.exists():raise FileExistsError(args.output)
ROOT=args.repo_root.resolve();BASE=ROOT/'evidence/python-control-id-20261016/characterization'
spec=importlib.util.spec_from_file_location('audit',BASE/'analyze_characterization.py'); audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
audit.verify_modules(); fit=audit.fit

def harmonics(t,signal,frequencies):
    columns=[np.ones(len(t))]+[f(2*np.pi*hz*t) for hz in frequencies for f in (np.cos,np.sin)]
    x=np.asarray(columns).T; coef=np.linalg.lstsq(x,signal,rcond=None)[0]; predicted=x@coef
    z=[complex(coef[1+2*i],-coef[2+2*i]) for i in range(len(frequencies))]
    return z,dict(offset=float(coef[0]),harmonic_explained_variance=float(1-np.var(signal-predicted)/np.var(signal)),residual_rms=float(np.sqrt(np.mean((signal-predicted)**2))))

def extra_columns(segments,cfg):
    extra=[]
    for t,q,a,_ in segments:
        # Offline centered 70ms local derivative only for qualitative friction diagnostics.
        w=np.empty(len(t))
        for i in range(len(t)):
            lo=max(0,i-3);hi=min(len(t),i+4)
            w[i]=np.polyfit(t[lo:hi]-t[i],q[lo:hi],2)[-2]
        start=t[0]+max(cfg.delay_candidates_s)
        while start+cfg.window_s<=t[-1]+1e-10:
            indices=np.flatnonzero((t>=start-1e-10)&(t<=start+cfg.window_s+1e-10))
            if len(indices)>=8:
                tw=t[indices]; s=(tw-tw[0])/(tw[-1]-tw[0]);phi=s*s*(1-s)**2
                sign=np.where(np.abs(w[indices])>.02,np.sign(w[indices]),0.)
                extra.append([-fit._integral(sign*phi,tw),fit._integral(phi,tw)])
            start+=cfg.window_s
    return np.array(extra)

runs={name:audit.load_run(ROOT/'evidence/python-control-id-20261016/hardware/runs'/('characterization-'+name+'-01')) for name in ('pilot','train')}
train=runs['train'];offset=audit.training_hanging_offset(train)['angle_offset_rad'];cfg=replace(fit.FitConfig(),angle_offset_rad=offset)
result={'status':'exploratory_only_existing_model_rejected','heldout_used_for_new_model_selection':False,'training_offset_rad':offset,'source_files':{name:r['manifest'] for name,r in runs.items()},'source_modules':audit.verify_modules(),'harmonics':{},'training_residual_diagnostics':{},'static_means':{}}
for name,run in runs.items():
    rows,_=audit.selected_rows(run);seg=fit._segments(rows,'magnetic','commanded',cfg);t,q,a,_=seg[0]; t=t-t[0];selection=(t>=2)&(t<=18);frequencies=(.8,1.3,2.1)
    qz,qs=harmonics(t[selection],q[selection],frequencies);az,ass=harmonics(t[selection],a[selection],frequencies)
    result['harmonics'][name]=dict(angle=qs,acceleration=ass,frequencies=[dict(frequency_hz=f,angle_amplitude_rad=abs(x),acceleration_amplitude_m_s2=abs(y),gain_rad_per_m_s2=abs(x/y),phase_rad=math.atan2((x/y).imag,(x/y).real)) for f,x,y in zip(frequencies,qz,az)])
    initial=audit.training_hanging_offset(run)
    refs=[x for x in run['records'] if x['type']=='characterization_reference'];tail=[x['theta'] for x in refs if x['t_s']>=20.5]
    result['static_means'][name]=dict(preflight=initial,tail_mean_rad=float(np.mean(tail)) if tail else None,tail_minus_preflight_rad=float(np.mean(tail)-initial['circular_mean_theta_rad']) if tail else None)
    if name=='train':
        x,y=fit._windows(seg,0,cfg);extra=extra_columns(seg,cfg);dx,dy=fit._windows(seg,0,cfg,include_offset=True)
        for label,features in [('baseline_3term',x),('coulomb_diagnostic',np.column_stack([x,extra[:,0]])),('constant_torque_diagnostic',np.column_stack([x,extra[:,1]])),('coulomb_plus_constant_diagnostic',np.column_stack([x,extra])),('five_term_offset_diagnostic',dx)]:
            c,_,rank,cond=fit._solve(features,y);resid=y-features@c
            result['training_residual_diagnostics'][label]=dict(coefficients=c.tolist(),rank=rank,condition=cond,training_integral_nrmse=float(np.sqrt(np.mean(resid**2))/np.std(y)),parameter_count=features.shape[1],accepted=False,promoted=False)
        c=fit._solve(x,y)[0];resid=y-x@c
        result['training_residual_diagnostics']['baseline_residual_correlation']=dict(coulomb_feature=float(np.corrcoef(resid,extra[:,0])[0,1]),integral_residual_mean=float(np.mean(resid)),note='In-sample correlation only, nonlinear diagnostic derivative is centered/noncausal; no heldout evaluation or model selection.')
# Check complex sign convention against a known sinusoidal response before trusting phase reports.
t=np.arange(0,10,.001);om=2*np.pi*1.3;known=.7*np.cos(om*t-.4)
z,_=harmonics(t,known,(1.3,)); assert abs(z[0]-.7*np.exp(-.4j))<1e-10
assert math.isclose(result['training_residual_diagnostics']['baseline_3term']['training_integral_nrmse'],.34829840659357136,rel_tol=1e-10)
result['verification']={'synthetic_harmonic_sign_and_scale':True,'baseline_matches_frozen_rejected_fit':True}
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('source_files','source_modules')},indent=2))
