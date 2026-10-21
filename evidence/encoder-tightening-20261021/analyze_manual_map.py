#!/usr/bin/env python3
"""Offline, motor-disabled slow-rotation comparison; never exports a calibration.

python analyze_manual_map.py --input RAW_RUN --lag-from PRIOR/report.json
                             --output NEW_DIRECTORY
Angle is raw marker geometry relative to image vertical, not a metrology angle.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

spec=importlib.util.spec_from_file_location('manual_map_base',Path(__file__).with_name('analyze.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def error_stats(values):
    r=np.asarray(values,dtype=float)
    if not len(r):return dict(n=0)
    return dict(n=len(r),median_deg=float(np.degrees(np.median(r))),rms_deg=float(np.degrees(np.sqrt(np.mean(r*r)))),
        p95_abs_deg=float(np.degrees(np.percentile(abs(r),95))),max_abs_deg=float(np.degrees(max(abs(r)))))


def periodic_basis(q,order):
    q=np.asarray(q);columns=[np.ones(len(q))]
    for n in range(1,order+1):columns.extend([np.sin(n*q),np.cos(n*q)])
    return np.column_stack(columns)


def fit_periodic_models(training,evaluation):
    q=np.array([r['encoder_rad'] for r in training]);y=np.array([r['residual_rad'] for r in training])
    center=base.circular_summary(y)['median'];y=base.wrap(y-center)+center
    # Equal weight per30-degree encoder bin prevents slower traversal bins from
    # dominating the fit. The opposite direction never enters coefficient fit.
    bins=np.floor((base.wrap(q)+math.pi)/(math.pi/6)).astype(int).clip(0,11)
    count=np.bincount(bins,minlength=12);weight=1/np.sqrt(count[bins])
    output={}
    for order in (0,1,2):
        name='constant' if order==0 else f'periodic_order{order}'
        design=periodic_basis(q,order);beta,_,rank,_=np.linalg.lstsq(design*weight[:,None],y*weight,rcond=None)
        result=dict(order=order,coefficients=beta.tolist(),rank=int(rank),condition_number=float(np.linalg.cond(design*weight[:,None])),
            interpretation='Camera proxy≈encoder+offset+periodic residual. No map exported, deployed, or accepted. Coefficients are radians.')
        for label,rows in [('train',training),('opposite_direction',evaluation)]:
            qq=np.array([r['encoder_rad'] for r in rows]);yy=np.array([r['residual_rad'] for r in rows])
            result[label]=error_stats(base.wrap(yy-periodic_basis(qq,order)@beta))
        grid=np.linspace(-math.pi,math.pi,4097);derivative=np.ones(len(grid))
        for n in range(1,order+1):derivative+=n*beta[2*n-1]*np.cos(n*grid)-n*beta[2*n]*np.sin(n*grid)
        result.update(minimum_derivative=float(derivative.min()),maximum_derivative=float(derivative.max()),
            mathematically_monotonic=bool(derivative.min()>0),monotonicity_check='Positive sampled d(camera proxy)/d(encoder) on4097-point full-circle grid; not calibration validation.')
        output[name]=result
    return output


def quiet_intervals(t,theta,omega,min_duration=.6):
    t=np.asarray(t);theta=np.asarray(theta);omega=np.asarray(omega)
    intervals=[];start=None
    def finish(end):
        if start is None or t[end]-t[start]<min_duration:return
        spread=base.circular_summary(theta[start:end+1])
        intervals.append(dict(first_index=int(start),last_index=int(end),start_s=float(t[start]),end_s=float(t[end]),
            duration_s=float(t[end]-t[start]),encoder_stationary_qualified=spread['span']<=.03,
            encoder_angle_rad=spread,maximum_abs_omega_rad_s=float(max(abs(omega[start:end+1])))))
    for i in range(len(t)):
        if abs(omega[i])<=.04:
            if start is None:start=i
            elif t[i]-t[i-1]>base.GAP_S+1e-9:finish(i-1);start=i
        elif start is not None:finish(i-1);start=None
    if start is not None:finish(len(t)-1)
    return intervals


def direction_support(rows):
    q=np.array([r['encoder_rad'] for r in rows]);bins=np.floor((base.wrap(q)+math.pi)/(math.pi/6)).astype(int).clip(0,11)
    counts=np.bincount(bins,minlength=12)
    sorted_q=np.sort(q%(2*math.pi));gaps=np.diff(np.r_[sorted_q,sorted_q[0]+2*math.pi]) if len(q) else np.array([2*math.pi])
    max_gap=float(np.degrees(max(gaps)))
    supported=len(q)>=100 and int((counts>=5).sum())>=11 and max_gap<=45
    return dict(n=len(q),counts_per_30deg_bin=counts.tolist(),bins_with_at_least5=int((counts>=5).sum()),
        maximum_unobserved_angular_gap_deg=max_gap,supported_for_descriptive_periodic_fit=supported,
        rule='At least100 moving pairs, at least11/12 angular bins with5 pairs, and maximum unobserved gap<=45degrees. This is data support, not hardware acceptance.')


def moving_pairs(trial,lag):
    rows=base.paired(trial,lag)
    for r in rows:
        w=r['encoder_rate_rad_s'];r['direction']=1 if w>=.05 else -1 if w<=-.05 else 0
        r['slow_motion_fit_eligible']=r['mode']==0 and .05<=abs(w)<=1.0
    return rows


def first_rotation_direction(trial):
    accumulated={-1:0.,1:0.}
    ss=trial['states'];tt=trial['host']
    for i in range(1,len(ss)):
        if not 0<tt[i]-tt[i-1]<=base.GAP_S+1e-9:continue
        w=ss[i]['omega'];delta=float(base.wrap(ss[i]['theta']-ss[i-1]['theta']))
        direction=1 if w>=.05 else -1 if w<=-.05 else 0
        if direction and direction*delta>0:accumulated[direction]+=abs(delta)
        if direction and accumulated[direction]>=math.pi/2:return direction
    return None


def approach_direction(t,theta,boundary,before):
    t=np.asarray(t);theta=np.asarray(theta)
    mask=(t>=boundary-2)&(t<boundary) if before else (t>boundary)&(t<=boundary+2)
    x=t[mask];q=theta[mask]
    if len(q)<2 or np.any(np.diff(x)>base.GAP_S+1e-9):return 0
    net=float(np.sum(base.wrap(np.diff(q))))
    return int(np.sign(net)) if abs(net)>=math.radians(10) else 0


def tracking_by_angle(trial,lag):
    unique={}
    for row in trial['raw_camera']:
        v=row.get('vision',{});key=(v.get('seq'),v.get('t'))
        if isinstance(v.get('t'),(int,float)):unique[key]=row
    rows=list(unique.values());query=np.array([base.camera_clock(r,trial['filter_report']['clock_anchors'])+lag for r in rows])
    theta,valid=base.interpolate(trial['host'],np.array([s['theta'] for s in trial['states']]),query,angular=True)
    accepted={(c['seq'],c['source_t']) for c in trial['camera']};total=np.zeros(12,dtype=int);kept=np.zeros(12,dtype=int)
    for row,q,ok in zip(rows,theta,valid):
        if not ok:continue
        index=min(11,max(0,int((q+math.pi)/(math.pi/6))))
        total[index]+=1
        if (row['vision'].get('seq'),row['vision'].get('t')) in accepted:kept[index]+=1
    return [dict(encoder_bin_low_deg=-180+30*i,encoder_bin_high_deg=-150+30*i,raw_frames=int(total[i]),
                 retained_frames=int(kept[i]),retained_fraction=float(kept[i]/total[i]) if total[i] else None) for i in range(12)]


def paused_separation_comparisons(holds):
    output=[]
    for i,a in enumerate(holds):
        if not a['stationary_comparison_qualified']:continue
        for j,b in enumerate(holds[i+1:],i+1):
            if not b['stationary_comparison_qualified']:continue
            encoder=float(base.wrap(b['native_encoder_angle_rad']-a['native_encoder_angle_rad']))
            if abs(encoder)<math.radians(45):continue
            camera=float(base.wrap(b['camera_image_angle_rad']['median']-a['camera_image_angle_rad']['median']))
            output.append(dict(first_hold_index=i,second_hold_index=j,
                encoder_separation_positive_deg=float(np.degrees(encoder)%360),camera_separation_positive_deg=float(np.degrees(camera)%360),
                camera_minus_encoder_separation_deg=float(np.degrees(base.wrap(camera-encoder))),
                interpretation='Difference of quiet-pose sensor separations. A constant zero offset cannot change this discrepancy. Timing influence is reduced by stationary qualification; neither sensor is certified as ground truth.'))
    return output


def hold_reports(trial,models,training_direction):
    ss=trial['states'];tt=trial['host'];theta=np.array([s['theta'] for s in ss]);omega=np.array([s['omega'] for s in ss])
    intervals=quiet_intervals(tt,theta,omega);result=[]
    for hold in intervals:
        lo,hi=hold['start_s']+.1,hold['end_s']-.1
        cc=[c for c in trial['camera'] if lo<=c['t']<=hi]
        ii=[i for i in trial['infos'] if lo<=i['received_ns']/1e9<=hi and isinstance(i.get('encoder_raw'),int)]
        direction_before=approach_direction(tt,theta,hold['start_s'],before=True)
        direction_after=approach_direction(tt,theta,hold['end_s'],before=False)
        camera=base.circular_summary([c['angle'] for c in cc]);native=base.circular_summary([i['encoder_raw'] for i in ii],4096)
        state=base.circular_summary([(trial['reference']+s['theta']*4096/base.TAU)%4096 for s,t in zip(ss,tt) if lo<=t<=hi],4096)
        cam_qualified=bool(camera and camera['n']>=20 and camera['std']<=.005 and camera['p95_minus_p05']<=.015)
        qualified=hold['encoder_stationary_qualified'] and cam_qualified and native is not None
        native_theta=None if native is None else float(base.wrap((native['median']-trial['reference'])*base.TAU/4096))
        residual=None if native_theta is None or camera is None else float(base.wrap(camera['median']-native_theta))
        entry=dict(**hold,measurement_window_s=[lo,hi],native_info_counts=native,reconstructed_state_counts=state,
            camera_image_angle_rad=camera,camera_stationary_qualified=cam_qualified,stationary_comparison_qualified=qualified,
            direction_before=direction_before,direction_after=direction_after,
            role='training_direction' if direction_before==training_direction else 'opposite_direction' if direction_before==-training_direction else 'unassigned',
            camera_pivot_x_px=base.stats([c['pivot_x'] for c in cc]),camera_pivot_y_px=base.stats([c['pivot_y'] for c in cc]),
            marker_length_px=base.stats([c['length'] for c in cc]),native_encoder_angle_rad=native_theta,
            camera_minus_native_encoder_deg=None if residual is None else float(np.degrees(residual)),
            native_info_unchanged_duration_us=base.stats([i.get('encoder_raw_age_us',np.nan) for i in ii]),
            predicted_residual_after_model_deg={})
        if residual is not None:
            for name,model in models.items():
                predicted=float((periodic_basis([native_theta],model['order'])@np.array(model['coefficients']))[0])
                entry['predicted_residual_after_model_deg'][name]=float(np.degrees(base.wrap(residual-predicted)))
        result.append(entry)
    return result


def paused_pair_comparisons(holds):
    result=[]
    for i,a in enumerate(holds):
        if not a['stationary_comparison_qualified'] or not a['direction_before']:continue
        for j,b in enumerate(holds[i+1:],i+1):
            if not b['stationary_comparison_qualified'] or b['direction_before']!=-a['direction_before']:continue
            camera_delta=float(base.wrap(b['camera_image_angle_rad']['median']-a['camera_image_angle_rad']['median']))
            if abs(camera_delta)>math.radians(5):continue
            encoder_delta=float(base.wrap(b['native_encoder_angle_rad']-a['native_encoder_angle_rad']))
            result.append(dict(first_hold_index=i,second_hold_index=j,camera_pose_difference_deg=float(np.degrees(camera_delta)),
                encoder_difference_deg=float(np.degrees(encoder_delta)),encoder_minus_camera_difference_deg=float(np.degrees(base.wrap(encoder_delta-camera_delta))),
                caution='Opposite approaches within5degrees of raw camera pose, not independently fixed known angles. Projection, viewpoint, magnetic response and mechanical loading remain confounds.'))
    return result


def plot_report(trial,pairs,models,holds,training_direction,output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'encoder-tightening-matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    origin=trial['host'][0]
    def line(ax,x,y,max_gap,segments=None,**kw):
        xx=[];yy=[]
        for i,(a,b) in enumerate(zip(x,y)):
            if i and (x[i]-x[i-1]>max_gap+1e-9 or abs(b-y[i-1])>180 or segments is not None and segments[i]!=segments[i-1]):xx.append(np.nan);yy.append(np.nan)
            xx.append(a-origin);yy.append(b)
        ax.plot(xx,yy,**kw)
    line(axes[0,0],trial['host'],np.degrees([s['theta'] for s in trial['states']])%360,base.GAP_S,label='Raw encoder',lw=.8)
    cc=trial['camera'];line(axes[0,0],[c['t'] for c in cc],np.degrees([c['angle'] for c in cc])%360,base.CAMERA_GAP_S,[c['segment'] for c in cc],label='Raw image geometry',lw=.8)
    axes[0,0].set(xlabel='Seconds from first telemetry',ylabel='Angle modulo360°')
    for direction,color in [(1,'#427db9'),(-1,'#bb7041')]:
        rr=[r for r in pairs if r['slow_motion_fit_eligible'] and r['direction']==direction]
        axes[0,1].scatter(np.degrees([r['encoder_rad'] for r in rr]),np.degrees([r['residual_rad'] for r in rr]),s=6,alpha=.4,color=color,label=f'Direction{direction:+d}'+(' (fit)' if direction==training_direction else ' (held out)') if models else f'Direction {direction:+d}')
    grid=np.linspace(-math.pi,math.pi,361)
    for name,model in models.items():
        curve=np.degrees(periodic_basis(grid,model['order'])@np.array(model['coefficients']))
        axes[0,1].plot(np.degrees(grid),curve,lw=1.4,label=name)
        axes[1,0].plot(np.degrees(grid),curve,lw=1.1,label=name)
    for index,h in enumerate(holds):
        if h['camera_minus_native_encoder_deg'] is None:continue
        good=h['stationary_comparison_qualified'];color='#427db9' if h['direction_before']==training_direction else '#bb7041'
        axes[1,0].scatter(np.degrees(h['native_encoder_angle_rad']),h['camera_minus_native_encoder_deg'],color=color,marker='o' if good else 'x',s=45,alpha=1 if good else .4)
        axes[1,0].annotate(str(index),(np.degrees(h['native_encoder_angle_rad']),h['camera_minus_native_encoder_deg']),fontsize=7)
    axes[0,1].set(xlabel='Encoder angle (degrees)',ylabel='Camera − encoder (degrees)',title='Slow-motion directions; fixed timing proxy')
    axes[1,0].set(xlabel='Native INFO encoder angle (degrees)',ylabel='Paused camera − encoder (degrees)',title='Quiet holds: filled=qualified, x=unqualified; labels=index')
    if models:
        names=list(models);xx=np.arange(len(names))
        axes[1,1].bar(xx-.18,[models[n]['train']['rms_deg'] for n in names],.36,label='Fitted direction')
        axes[1,1].bar(xx+.18,[models[n]['opposite_direction']['rms_deg'] for n in names],.36,label='Opposite direction')
        axes[1,1].set_xticks(xx,names,rotation=15);axes[1,1].set_ylabel('Residual RMS (degrees)')
    else:axes[1,1].text(.1,.5,'Insufficient opposing direction/angular support\nNo periodic candidate validated',transform=axes[1,1].transAxes)
    for ax in axes.ravel():
        ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]:ax.legend(fontsize=7)
    fig.suptitle(trial['name']+' — camera tracking does not cover intermediate angles',fontsize=12)
    fig.savefig(output/'passive-map-diagnostics.png',dpi=170);plt.close(fig)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--lag-from',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    trial=base.load_trial(a.input);prior=base.read_json(a.lag_from);lag=prior['frozen_lag']['lag_s']
    healthy=bool(trial['states']) and all(s['mode']==0 and s['flags']&3==1 and s['fault']==0 for s in trial['states'])
    if not healthy or trial['reference'] is None:raise ValueError('Require entirely disabled healthy telemetry and one fixed saved encoder reference; refusing fit.')
    pairs=moving_pairs(trial,lag);directions={d:[r for r in pairs if r['slow_motion_fit_eligible'] and r['direction']==d] for d in (-1,1)}
    support={str(d):direction_support(rows) for d,rows in directions.items()}
    training_direction=first_rotation_direction(trial)
    ready=training_direction is not None and all(s['supported_for_descriptive_periodic_fit'] for s in support.values())
    models=fit_periodic_models(directions[training_direction],directions[-training_direction]) if ready else {}
    holds=hold_reports(trial,models,training_direction or 0)
    sensitivity=[]
    for candidate in (lag,0.,lag-.05,lag+.05):
        candidates=moving_pairs(trial,candidate)
        for name,model in models.items():
            rr=[r for r in candidates if r['slow_motion_fit_eligible'] and r['direction']==-training_direction]
            residual=np.array([r['residual_rad'] for r in rr])-periodic_basis([r['encoder_rad'] for r in rr],model['order'])@np.array(model['coefficients'])
            sensitivity.append(dict(lag_s=candidate,model=name,coefficients_refit=False,opposite_direction=error_stats(base.wrap(residual))))
    source=[*trial['sources'],a.lag_from,Path(__file__),Path(__file__).with_name('analyze.py')]
    collector_source=Path(__file__).with_name('capture-manual-map-used.py')
    if collector_source.exists():source.append(collector_source)
    report=dict(schema='passive-slow-rotation-v1',hardware_accepted=False,calibration_accepted=False,calibration_produced=False,
        trial=trial['name'],source=str(a.input.resolve()),entirely_disabled_healthy=healthy,reference_counts=trial['reference'],
        collector_report_summary={k:v for k,v in trial['report'].items() if k!='samples'},collector_info_samples=len(trial['report'].get('samples',[])),camera_filters=trial['filter_report'],clock=trial['clock'],
        encoder_unwrapped_range_deg=float(np.degrees(np.ptp(np.unwrap([s['theta'] for s in trial['states']])))),
        all_speed_camera_angle_support=direction_support(pairs),tracking_by_encoder_angle=tracking_by_angle(trial,lag),
        telemetry_gap_s=base.stats(np.diff(trial['board'])),camera_gap_s=base.stats(np.diff([c['t'] for c in trial['camera']])),
        step_cart_position_m=base.stats([s['x'] for s in trial['states']]),
        raw_native_info_counts=base.circular_summary([i['encoder_raw'] for i in trial['infos'] if isinstance(i.get('encoder_raw'),int)],4096),
        raw_native_info_note='Whole-rotation count median is not a rest zero; INFO readbacks are separate observations, not independent acquisition cadence. encoder_raw_age_us measures unchanged-value duration only.',
        training_direction=training_direction,opposite_direction_validation_available=ready,direction_support=support,models=models,
        holds=holds,paused_separation_comparisons=paused_separation_comparisons(holds),opposite_approach_paused_comparisons=paused_pair_comparisons(holds),timing_sensitivity=sensitivity,
        method=dict(camera='Raw atan2(bob_x-pivot_x,pivot_y-bob_y), image-vertical proxy. No camera fusion, saved calibration, upright anchor, or mirrored encoder. User requested fixed cart/camera; step counts cannot independently prove physical cart restraint.',
            direction='Direction sign from firmware omega; first direction accumulating90degrees of raw encoder motion is training. All eligible opposite-sign observations remain held out. This does not assume requested rotations were completed.',
            moving_filter='Motor disabled, valid paired camera, 0.05<=|firmware omega|<=1.0rad/s. Base camera confidence>=0.8/fresh valid geometry/length within20% median. Telemetry gaps>30ms never interpolated; rejected camera frames or gaps>75ms break continuity.',
            fitting='Equal30-degree-bin weighted OLS, constant/order1/order2 cyclic residuals, first direction only. Dense derivative check marks mathematical monotonicity but never accepts an encoder map.',
            paused='Consecutive |omega|<=0.04rad/s for>=0.6s, telemetry gaps break holds. Encoder full span<=0.03rad; measurement trimmed0.1s each end. Camera>=20frames, std<=0.005rad and p95−p05<=0.015rad; at least one native INFO count. Failed holds retained. Approach labels require>=10degrees net encoder movement in the adjacent2s; smaller jitter is unassigned.',
            timing=f'Frozen lag{lag:.3f}s from earlier AUTO is a proxy, not an independently bounded latency. Zero and±50ms sensitivity do not establish actual delay bounds. At1rad/s a hypothetical50ms offset contributes2.86degrees; paused poses reduce this confound.',
            limitations='Direction, load, camera projection, magnet/encoder response and fixture motion can produce similar residuals. Correlated frames are not independent replicates. No nonlinear map is systematically validated or deployed.'),
        source_hashes=[dict(path=str(f.resolve()),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in source])
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (a.output/'pairs.ndjson').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in pairs))
    plot_report(trial,pairs,models,holds,training_direction,a.output)
    print(json.dumps(dict(output=str(a.output),training_direction=training_direction,direction_support=support,models=models,
        holds=len(holds),qualified_holds=sum(h['stationary_comparison_qualified'] for h in holds)),indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
