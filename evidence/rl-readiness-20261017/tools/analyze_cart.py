#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3", "mujoco>=3.15,<4", "matplotlib>=3.9,<4"]
# ///
"""Offline replay of the five new bounded pulses; no coefficient or actuator fitting.

Use --repo . --raw-root extracted-directory --output NEW_DIRECTORY.
The signed first10mm pair defines a pixel/count shape map; the second pair
checks repeatability under that frozen map. This is not independent metric
calibration. Local phase from the saved passive model is not global calibration.
"""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np
from scipy.integrate import cumulative_trapezoid


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def metric(values):
    e=np.asarray(values,float)
    return dict(samples=len(e),rms=float(np.sqrt(np.mean(e*e))),p95_abs=float(np.quantile(abs(e),.95)),max_abs=float(max(abs(e))))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','raw-root','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();root=a.repo.resolve()
    if a.output.exists():p.error('new output required')
    sys.path.insert(0,str(root/'src'))
    from cartpole_sdk.sim import MujocoBackend,SimulationConfig
    from cartpole_sdk.contracts import ActionRequest
    camera=module(root/'evidence/system-id-20261017/tools/analyze_camera_step_pulses.py','cam')
    audit=module(root/'evidence/friction-gym-20261017/cart-dynamics/audit.py','replay')
    freeze_path=root/'evidence/system-id-model-review-20261017/candidate-freeze-latest6.json'
    freeze=json.loads(freeze_path.read_text());params=freeze['parameters']
    config=replace(SimulationConfig(**json.loads((root/'training/profiles/rl-encoder-20261017/model.json').read_text())['simulation_config']),control_steps=1,max_steps=10000)
    names=['rl-readiness-pulse-p5-t080-01','rl-readiness-pulse-p10-t045-01',
           'rl-readiness-pulse-n10-t045-01','rl-readiness-pulse-p10-t045-02','rl-readiness-pulse-n10-t045-02']
    optics=[camera.analyze_run(a.raw_root/name) for name in names]
    scale=np.mean([r['shape']['best_lag_diagnostic']['gain_px_per_counted_m'] for r in optics[1:3]])
    lag=np.median([r['shape']['best_lag_diagnostic']['lag_s'] for r in optics[1:3]])
    runs=[];all_q=[]
    for name,optical in zip(names,optics):
        directory=a.raw_root/name;report=json.loads((directory/'report.json').read_text())
        raw,_=camera.load_jsonl(Path(optical['source_hashes']['rig']['path']))
        states=[]
        for row in raw:
            if row.get('type')=='state' and (not states or states[-1]['unwrapped_us']!=row['state']['unwrapped_us']):states.append(row['state'])
        origin=optical['origin_board_s'];duration=report['result']['pulse_seconds']+report['result']['hold_seconds']
        t=np.array([s['unwrapped_us']/1e6-origin for s in states]);use=(t>=0)&(t<=duration)
        t=t[use];selected=[s for s,yes in zip(states,use) if yes]
        assert len(selected)>200 and max(np.diff(t))<.021
        q=np.unwrap([s['theta'] for s in selected])-params['local_angle_offset_rad']
        v=np.array([s['velocity'] for s in selected]);x=np.array([s['x'] for s in selected])
        acc=np.gradient(v,t)
        i=max(6,int(np.searchsorted(t,.1)))
        initial_qw=audit.initialize(t,q,acc,i,params,'history_rawq',history=.1)
        initial=tuple(map(float,(x[i],v[i],initial_qw[0],initial_qw[1])))
        backend=MujocoBackend(config);backend.reset(state=initial);sim=[[t[i],*initial]];forces=[];saturated=0
        for j in range(int(math.floor((t[-1]-t[i])/.001))):
            obs=backend.observation;time=t[i]+obs.available_ns/1e9
            request_a=float((np.interp(time+.001,t,v)-np.interp(time,t,v))/.001)
            request=ActionRequest(obs.session_id,obs.clock_id,j,obs.sequence,obs.available_ns,obs.available_ns+1000000,request_a)
            backend.step(request);s=backend.ground_truth;d=backend.diagnostics
            sim.append([t[i]+s.time_ns/1e9,s.x,s.v,s.theta,s.omega]);forces.append(d.applied_force_n);saturated+=d.force_saturated
        backend.close();sim=np.array(sim);sim[:,3]=np.unwrap(sim[:,3]);sim[:,3]+=round((initial[2]-sim[0,3])/(2*math.pi))*2*math.pi
        target=t[i+1:];target=target[target<=sim[-1,0]];qm=np.interp(target,t,q);qp=np.interp(target,sim[:,0],sim[:,3])
        errors=np.rad2deg(np.arctan2(np.sin(qp-qm),np.cos(qp-qm)));all_q.extend(errors)
        # Use actual pulse duration for quiet tail (the historic helper assumed .65s).
        points=optical['raw_points'];valid=[r for r in points if r['x_px'] is not None]
        tail=[r['x_px'] for r in valid if duration-1<=r['t_s']<=duration]
        base=optical['baseline']['x_px']['median'];count=np.array(optical['counted_points'])
        local=[r for r in valid if -.1<=r['t_s']<=1.1];ct=np.array([r['t_s'] for r in local]);pixel=np.array([r['x_px'] for r in local])-base
        predicted=scale*camera.interpolate_supported(count[:,0],count[:,1],ct-lag)
        good=np.isfinite(predicted)
        qtrace=dict(t_s=target.tolist(),measured_rad=qm.tolist(),predicted_rad=qp.tolist())
        runs.append(dict(name=name,role='pilot' if name==names[0] else 'shape_map_development' if name in names[1:3] else 'repeatability_check',
            source_hashes=optical['source_hashes'],source_status=dict(completed=report['completed'],stop_confirmed=report['stop_confirmed'],records_dropped=report['records_dropped'],policy=report['result']['policy']),
            initial_hanging_rad=report['result']['initial_hanging'],duration_s=duration,initialization_s=float(t[i]),
            camera_coverage=optical['pulse_geometry']['coverage'],camera_gap_max_s=optical['pulse_geometry']['max_valid_frame_gap_s'],
            fitted_shape=optical['shape']['best_lag_diagnostic'],frozen_pair_shape_residual_px=metric(predicted[good]-pixel[good]),
            return_offset_px=float(np.median(tail)-base),count_span_m=float(np.ptp(x)),peak_commanded_velocity_m_s=float(max(abs(v))),
            peak_governor_acceleration_m_s2=float(max(abs(s['acceleration']) for s in selected)),
            cart_integrated_velocity_vs_counts_mm=metric((x[0]+cumulative_trapezoid(v,t,initial=0)-x)*1000),
            replay_cart_vs_counts_mm=metric((np.interp(target,sim[:,0],sim[:,1])-np.interp(target,t,x))*1000),
            replay_angle_deg=metric(errors),max_assumed_force_n=float(max(abs(np.array(forces)))),force_saturated_ticks=int(saturated),
            angle_trace=qtrace,optical_trace=dict(t_s=ct[good].tolist(),measured_px=pixel[good].tolist(),predicted_px=predicted[good].tolist())))
    result=dict(schema='cartpole-rl-readiness-cart-v1',hardware_accepted=False,parameters_fitted=False,
        freeze_sha256=hashlib.sha256(freeze_path.read_bytes()).hexdigest(),frozen_parameters=params,
        optical_shape_map=dict(scale_px_per_counted_m=float(scale),receipt_proxy_lag_s=float(lag),sources=names[1:3],independent_metric_calibration=False),
        continuous_angle_deg=metric(all_q),runs=runs,
        caveats=['Pixel scale is learned from emitted counts; no independent physical ruler scale or fixed-background landmark.',
        'Raw camera pivots are used even though angle calibration is unset; no mirrored/fused data enter fitting.',
        '100Hz governor velocity endpoints reconstruct offline1ms average input; no claim of measured physical velocity or actuator latency.',
        'Only initial pole velocity is fitted from preceding0.1s; phase/physics coefficients fixed before recording. All later samples scored.',
        'Mass, force ceiling, full rail/highspeed dynamics, global angle calibration and closed-loop policy transfer remain unqualified.',
        'First10mm pair is development; second pair is a within-session repeatability check, not blind global validation.'],
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.output.mkdir(parents=True);(a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(runs),2,figsize=(13,14),layout='constrained')
    for row,(left,right) in zip(runs,axes):
        tr=row['angle_trace'];left.plot(tr['t_s'],np.rad2deg(np.array(tr['measured_rad'])-math.pi),label='Recorded encoder + frozen local phase')
        left.plot(tr['t_s'],np.rad2deg(np.array(tr['predicted_rad'])-math.pi),label='MuJoCo, velocity-endpoint input')
        left.set_title(f"{row['name']} | pole RMS {row['replay_angle_deg']['rms']:.2f}°")
        left.set_ylabel('Angle from hanging (deg)')
        op=row['optical_trace'];right.scatter(op['t_s'],op['measured_px'],s=10,label='Camera pivot')
        right.plot(op['t_s'],op['predicted_px'],label='Counts × first-pair map')
        right.set_title(f"{row['role']} | optical RMS {row['frozen_pair_shape_residual_px']['rms']:.2f}px")
        right.set_ylabel('Pivot displacement (px)')
        for ax in (left,right):ax.set_xlabel('Seconds from pulse');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);axes[0,1].legend(fontsize=8)
    fig.suptitle('New bounded cart pulses: fixed passive law, no actuator parameter fit\nLocal count/optical evidence; not full-speed hardware qualification')
    fig.savefig(a.output/'cart-and-pendulum-replay.png',dpi=150);plt.close(fig)
    print(json.dumps(dict(continuous_angle_deg=result['continuous_angle_deg'],runs=[{k:v for k,v in r.items() if k not in ('source_hashes','angle_trace','optical_trace')} for r in runs]),indent=2))

if __name__=='__main__':main()
