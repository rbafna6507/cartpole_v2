#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3", "matplotlib>=3.9,<4"]
# ///
"""Frozen passive-law replay on existing driven development pulses; offline only.

No dynamics/input fit, hardware access, acceptance decision or source mutation.
Use --repo REPO --output NEW_DIRECTORY. All six predefined canonical segments
are kept, including the two previously inspected/clamped 30 mm development runs.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np
from scipy.integrate import solve_ivp, cumulative_trapezoid
from scipy.optimize import least_squares


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def metrics(error):
    e=np.asarray(error,float)
    return dict(samples=len(e),rms=float(np.sqrt(np.mean(e*e))),p95_abs=float(np.quantile(abs(e),.95)),max_abs=float(max(abs(e))))
def angular(error):
    e=np.arctan2(np.sin(error),np.cos(error));return dict(unit='deg',**metrics(np.rad2deg(e)))

def solution(t,initial,source_t,source_a,p,max_step=.001):
    alpha=9.81/p['effective_length_m'];beta=1/p['effective_length_m']
    def rhs(time,state):
        q,w=state;a=float(np.interp(time,source_t,source_a))
        return [w,alpha*math.sin(q)-beta*a*math.cos(q)-p['viscous_per_s']*w-p['coulomb_rad_per_s2']*math.tanh(w/.05)]
    s=solve_ivp(rhs,(float(t[0]),float(t[-1])),initial,t_eval=t,method='DOP853',rtol=2e-9,atol=1e-11,max_step=max_step)
    if not s.success or s.y.shape[1]!=len(t):raise ValueError(s.message)
    return s.y

def initialize(t,q,a,i,p,kind,history=.20):
    if kind=='causal_7point_quadratic':
        return np.array([q[i],np.polyfit(t[i-6:i+1]-t[i],q[i-6:i+1],2)[-2]])
    lo=max(0,int(np.searchsorted(t,t[i]-history-1e-9)));ts=t[lo:i+1];qs=q[lo:i+1]
    guess=[qs[0],np.polyfit(ts-ts[0],qs,2)[-2]]
    fit=least_squares(lambda z:solution(ts,z,t,a,p,max_step=.005)[0]-qs,guess,
                      xtol=1e-7,ftol=1e-7,gtol=1e-7,max_nfev=50,diff_step=1e-4)
    if not fit.success:raise ValueError(f'initial-state optimization did not converge: {fit.message}; cost={fit.cost}; optimality={fit.optimality}')
    state=solution(ts,fit.x,t,a,p,max_step=.005)[:,-1];state[0]=q[i]
    return state

def short_score(segment,p,kind):
    t,q,a,_=segment;i=max(6,int(np.searchsorted(t,t[0]+.1)));errors=[];initial=[]
    while i+8<len(t):
        end=int(np.searchsorted(t,t[i]+.5,side='right'))
        if t[end-1]-t[i]<.45:break
        state=initialize(t,q,a,i,p,kind);pred=solution(t[i:end],state,t,a,p)[0]
        errors.extend(pred[1:]-q[i+1:end]);initial.append(dict(t_s=float(t[i]),state=state.tolist(),end_s=float(t[end-1])))
        i=end
    return dict(**angular(np.array(errors)),windows=len(initial),initial_states=initial),np.array(errors)

def continuous_score(segment,p,duration):
    t,q,a,_=segment;i=max(6,int(np.searchsorted(t,t[0]+duration)))
    state=initialize(t,q,a,i,p,'history_rawq',history=duration)
    pred=solution(t[i:],state,t,a,p)[0];error=pred[1:]-q[i+1:]
    return dict(**angular(error),initialization_s=duration,initial_state=state.tolist(),
        first_scored_s=float(t[i+1]),last_scored_s=float(t[-1]),
        trace=dict(t_s=t.tolist(),measured_rad=q.tolist(),predicted_t_s=t[i:].tolist(),predicted_rad=pred.tolist(),acceleration_m_s2=a.tolist())),error

def counted_kinematics(states,origin):
    rows=[s for s in states if s['unwrapped_us']/1e6>=origin and s['unwrapped_us']/1e6<=origin+3.65]
    t=np.array([s['unwrapped_us']/1e6 for s in rows]);a=np.array([s['acceleration'] for s in rows]);v=np.array([s['velocity'] for s in rows]);x=np.array([s['x'] for s in rows])
    vp=v[0]+cumulative_trapezoid(a,t,initial=0);xp=x[0]+cumulative_trapezoid(vp,t,initial=0)
    x_from_recorded_v=x[0]+cumulative_trapezoid(v,t,initial=0)
    return dict(samples=len(t),duration_s=float(t[-1]-t[0]),sample_gap_max_s=float(max(np.diff(t))),
        counted_x_span_m=float(np.ptp(x)),peak_abs_velocity_m_s=float(max(abs(v))),peak_abs_governor_acceleration_m_s2=float(max(abs(a))),
        velocity_integral_residual_m_s=metrics(vp-v),double_integral_position_residual_mm=metrics((xp-x)*1000),
        recorded_velocity_integral_position_residual_mm=metrics((x_from_recorded_v-x)*1000),
        end_velocity_residual_m_s=float(vp[-1]-v[-1]),end_double_integral_position_residual_mm=float((xp[-1]-x[-1])*1000),
        interpretation='Internal sampled-command/count kinematics only. Position is emitted step count and velocity/acceleration are governor state; none is independent physical cart measurement.')

def frozen_camera_check(run,scale,lag,camera):
    # Scale and lag come entirely from the already archived four-training-run
    # analysis. A new run contributes only its pre-pulse median image origin.
    raw=[p for p in run['raw_points'] if p['x_px'] is not None and -.1<=p['t_s']<=1.1]
    vt=np.array([p['t_s'] for p in raw]);y=np.array([p['x_px'] for p in raw]);count=np.array(run['counted_points'])
    x0=0.;baseline=run['baseline']['x_px']['median']
    x=camera.interpolate_supported(count[:,0],count[:,1],vt-lag);good=np.isfinite(x)
    pred=baseline+scale*(x[good]-x0)
    return dict(unit='px',**metrics(pred-y[good]),scale_px_per_counted_m=scale,lag_s=lag,
        origin_px=baseline,origin_method='per-run pre-pulse median; counted pre-pulse origin is zero',
        points=dict(t_s=vt[good].tolist(),measured_px=(y[good]-baseline).tolist(),predicted_px=(pred-baseline).tolist()))

def draw(runs,out):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(6,2,figsize=(13,17),layout='constrained')
    for axrow,run in zip(axes,runs):
        trace=run['continuous_0_1s']['trace'];t0=trace['t_s'][0]
        ax=axrow[0];ax.plot(np.array(trace['t_s'])-t0,np.rad2deg(np.array(trace['measured_rad'])-math.pi),label='Raw encoder, frozen local phase',lw=1.5)
        ax.plot(np.array(trace['predicted_t_s'])-t0,np.rad2deg(np.array(trace['predicted_rad'])-math.pi),label='Frozen passive law + counted acceleration',lw=1.4)
        ax.axvspan(0,.1,color='gray',alpha=.15,label='Initialization' if ax is axes[0,0] else None)
        ax.set_title(f"{run['name']}: continuous RMS {run['continuous_0_1s']['rms']:.2f}°")
        ax.set_ylabel('Angle from hanging (deg)');ax.set_xlabel('Seconds after canonical control segment begins');ax.grid(alpha=.2)
        px=run['optical_frozen_training_map']['points'];ax=axrow[1]
        ax.scatter(px['t_s'],px['measured_px'],s=9,label='Raw camera pivot');ax.plot(px['t_s'],px['predicted_px'],label='Counted x, frozen training pixel map')
        ax.set_title(f"Camera/count shape RMS {run['optical_frozen_training_map']['rms']:.2f} px; coverage {run['optical']['pulse_geometry']['coverage']:.1%}")
        ax.set_xlabel('Seconds from pulse start (receipt proxy)');ax.set_ylabel('Pivot x − pre-pulse median (px)');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);axes[0,1].legend(fontsize=8)
    fig.suptitle('Existing driven development data: frozen dynamics and optical shape diagnostics\nUnit input gain / zero input delay are assumptions; optical scale and 15 ms lag are training-derived proxies',fontsize=14)
    fig.savefig(out/'driven-replay-and-optical-shape.png',dpi=150);plt.close(fig)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.repo.resolve();out=args.output.resolve()
    if out.exists():parser.error('new output directory required')
    sys.path.insert(0,str(root/'src'))
    from cartpole_sdk.identification.fit import FitConfig,_segments
    from cartpole_sdk.identification.workflow import digest
    camera=module(root/'evidence/system-id-20261017/tools/analyze_camera_step_pulses.py','camera_step_audit')
    driven=module(root/'evidence/system-id-20261017/tools/analyze_driven_friction.py','driven_audit')
    freeze_path=root/'evidence/system-id-model-review-20261017/candidate-freeze-latest6.json';freeze=read(freeze_path);p=freeze['parameters']
    batch_path=root/'evidence/system-id-20261017/analysis/pulse-batch-secondary-historic-offset.json';batch=read(batch_path)
    content=dict(batch);pin=content.pop('content_sha256');assert digest(content)==pin and digest(batch['canonical_batches'])==batch['canonical_sha256']
    historic_path=root/'evidence/system-id-20261017/analysis/camera-step-training/analysis.json';historic=read(historic_path)
    scale=float(np.mean([r['shape']['best_lag_diagnostic']['gain_px_per_counted_m'] for r in historic['runs']]))
    lag=float(np.median([r['shape']['best_lag_diagnostic']['lag_s'] for r in historic['runs']]))
    cfg=replace(FitConfig(),angle_offset_rad=p['local_angle_offset_rad']);runs=[];all_errors={};parity=[]
    for original_role in ['training','validation']:
        role='original_training' if original_role=='training' else 'previous_validation_now_development'
        for source in batch['inputs'][original_role]:
            name=Path(source['spec']).parent.name;folder='raw-pulse-training' if original_role=='training' else 'raw-pulse-validation'
            directory=root/'evidence/system-id-20261017'/folder/name;optical=camera.analyze_run(directory)
            assert optical['source_hashes']['rig']['decompressed_sha256']==source['identity']['sha256']
            report=read(directory/'report.json');raw,_=camera.load_jsonl(Path(optical['source_hashes']['rig']['path']))
            states=[]
            for r in raw:
                if r.get('type')=='state' and (not states or states[-1]['unwrapped_us']!=r['state']['unwrapped_us']):states.append(r['state'])
            rows=[r for r in batch['canonical_batches'][original_role] if r['run_id']==source['identity']['sha256']]
            segments=_segments(rows,'magnetic','commanded',cfg);assert len(segments)==1;segment=segments[0]
            result=dict(name=name,role=role,source_sha256=source['identity']['sha256'],canonical_segment_samples=len(segment[0]),source_status=dict(completed=report['completed'],stop_confirmed=report['stop_confirmed'],records_dropped=report['records_dropped'],original_admission=source['admission'],collector_result=report['result']),
                kinematics=counted_kinematics(states,optical['origin_board_s']),optical=optical,
                optical_frozen_training_map=frozen_camera_check(optical,scale,lag,camera))
            for kind in ['causal_7point_quadratic','history_rawq']:
                score,e=short_score(segment,p,kind);result['short_'+kind]=score;all_errors.setdefault((role,'short_'+kind),[]).extend(e)
            for duration in [.1,.5]:
                score,e=continuous_score(segment,p,duration);key='continuous_'+str(duration).replace('.','_')+'s';result[key]=score;all_errors.setdefault((role,key),[]).extend(e)
            coeff=[9.81/p['effective_length_m'],p['viscous_per_s'],1/p['effective_length_m'],p['coulomb_rad_per_s2']]
            check=driven.predict(segments,coeff,0,cfg)
            parity.append(abs(math.degrees(check['prediction_rmse_rad'])-result['short_causal_7point_quadratic']['rms']))
            runs.append(result)
    assert max(parity)<.002,'independent high-accuracy solver disagrees with archived RK4 predictor'
    # No source clipping, optional coefficient change or scoring-dependent interval choice.
    result=dict(schema='cartpole-frozen-driven-audit-v1',accepted=False,recommended_for_hardware_rl=False,
        frozen_parameters=p,input_gain=1.,input_delay_s=0.,friction_width_rad_s=.05,
        source_status='All six historical pulse runs are development data. The signed 30 mm pair was already inspected before this audit; no untouched driven validation is claimed.',
        input_source='Direct MCU sampled governor acceleration. This is a commanded input, not measured physical acceleration.',
        selection='All original canonical valid rows/segments preserved. No new residual-based interval selection or parameter fit.',
        initialization='Short: original causal seven-point quadratic and causal frozen-ODE history<=0.20s retaining current raw angle. Continuous: first0.1s or0.5s fixed-ODE initial-state fit, raw endpoint angle retained; all later points scored with no measurement correction. Only initial state is estimated, never model/input coefficients.',
        assumptions=['Unit acceleration-servo gain and zero physical input delay','Frozen batch6 local encoder phase applied to older pulse sessions; it is not a global angle calibration','Recorded future governor input is supplied for conditional replay, not forecast before commands exist','Camera scale and lag frozen from historical four-training-run analysis; no independent physical scale or exposure timing','Equivalent rod mass/inertia, cart mass/drag and motor force limits are not identified by these data'],
        optical_map=dict(scale_px_per_counted_m=scale,lag_s=lag,source_sha256=sha(historic_path),method='Mean best-lag scale and median best lag from preserved four-training-run analysis; only each run pre-pulse pixel baseline is new.'),
        aggregate={role:{key:angular(np.array(errors)) for (r,key),errors in all_errors.items() if r==role} for role in ['original_training','previous_validation_now_development']},
        numerical_verification=dict(independent_solver_vs_archived_2ms_rk4_max_rms_difference_deg=max(parity),solver='DOP853 rtol2e-9 atol1e-11 maxstep1ms; initial-state fitting maxstep5ms, least_squares maxnfev50 diff_step1e-4, convergence required'),runs=runs,
        provenance=dict(script_sha256=sha(__file__),freeze_sha256=sha(freeze_path),batch_file_sha256=sha(batch_path),batch_content_sha256=pin,canonical_sha256=batch['canonical_sha256'],camera_tool_sha256=sha(root/'evidence/system-id-20261017/tools/analyze_camera_step_pulses.py'),driven_tool_sha256=sha(root/'evidence/system-id-20261017/tools/analyze_driven_friction.py'),numpy_version=np.__version__))
    out.mkdir(parents=True,exist_ok=False);(out/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');draw(runs,out)
    print(json.dumps(dict(output=str(out),aggregate=result['aggregate'],numerical_verification=result['numerical_verification'],runs=[dict(name=r['name'],kinematics=r['kinematics'],optical_frozen_training_map={k:v for k,v in r['optical_frozen_training_map'].items() if k!='points'},continuous_rms=r['continuous_0_1s']['rms']) for r in runs]),indent=2))

if __name__=='__main__':main()
