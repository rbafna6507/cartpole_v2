#!/usr/bin/env python3
"""Offline reference533 cohort; no hardware I/O, calibration, or acceptance.

python analyze_ref533.py --input RAW_CAMPAIGN --upright RAW_UPRIGHT \
  --lag-from OLD520_ANALYSIS/report.json --output NEW_DIRECTORY
Only ref533 AUTO/BAL recordings with unchanged camera setup are eligible.
The explicit user-handled failed bw6 attempt is always excluded.
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


def _load(name,filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

base=_load('encoder_analysis','analyze.py')
supplement=_load('encoder_supplement','analyze_upright.py')
EXCLUDED={'ref533-bw6-auto25-01':'User confirmed pole handling during initial rest; aborted before any gain write or AUTO. Excluded from performance and calibration.'}


def signal_metrics(t,values):
    t=np.asarray(t,dtype=float);v=np.asarray(values,dtype=float)
    ok=np.isfinite(t)&np.isfinite(v);t=t[ok];v=v[ok]
    if not len(v):return dict(n=0)
    dt=np.diff(t);dv=np.diff(v);adjacent=(dt>0)&(dt<=base.GAP_S+1e-9)
    duration=float(np.sum(dt[adjacent]));tv=float(np.sum(abs(dv[adjacent])))
    centered=t-t[0]
    slope=float(np.polyfit(centered,v,1)[0]) if len(v)>1 and np.ptp(centered)>0 else None
    return dict(n=len(v),mean=float(v.mean()),median=float(np.median(v)),rms=float(np.sqrt(np.mean(v*v))),
        std=float(np.std(v)),max_abs=float(max(abs(v))),p95_abs=float(np.percentile(abs(v),95)),
        min=float(v.min()),max=float(v.max()),span=float(np.ptp(v)),slope_per_s=slope,
        time_span_s=float(t[-1]-t[0]),adjacent_valid_duration_s=duration,gaps_over_30ms=int((dt>base.GAP_S+1e-9).sum()),
        total_variation=tv,total_variation_per_s=tv/duration if duration else None,
        first_difference_rms=float(np.sqrt(np.mean(dv[adjacent]**2))) if adjacent.any() else None,
        difference_rate_rms=float(np.sqrt(np.mean((dv[adjacent]/dt[adjacent])**2))) if adjacent.any() else None,
        variation_rule='Adjacent observed samples only, gaps>30ms omitted. No resampling/FFT/interpolation. Difference metrics depend on telemetry cadence.')


def angle_error_stats(values):
    out=supplement.error_stats(values)
    v=np.asarray(values,dtype=float)
    if len(v):out.update(max_abs_deg=float(np.degrees(max(abs(v)))),mean_deg=float(np.degrees(v.mean())))
    return out


def first_balance_run(t,modes):
    t=np.asarray(t);modes=np.asarray(modes)
    starts=np.flatnonzero(modes==3)
    if not len(starts):return None
    first=last=int(starts[0])
    while last+1<len(t) and modes[last+1]==3 and 0<t[last+1]-t[last]<=base.GAP_S+1e-9:last+=1
    return dict(first_s=float(t[first]),last_s=float(t[last]),duration_s=float(t[last]-t[first]),
        sample_count=last-first+1,later_balance_samples=int(np.sum(modes[last+1:]==3)),
        rule='First contiguous native mode3 segment; any mode exit or >30ms telemetry gap ends it.')


def upright_encoder_angle(anchor,reference):
    return float(base.wrap((anchor['native_encoder_counts']['median']-reference)*base.TAU/4096))


def upright_repeat_difference(before,after):
    encoder=float(base.wrap((after['native_encoder_counts']['median']-before['native_encoder_counts']['median'])*base.TAU/4096))
    camera=float(base.wrap(after['camera_image_angle_rad']['median']-before['camera_image_angle_rad']['median']))
    return dict(native_shift_counts=encoder*4096/base.TAU,native_shift_deg=float(np.degrees(encoder)),
        raw_camera_shift_deg=float(np.degrees(camera)),encoder_minus_camera_shift_deg=float(np.degrees(base.wrap(encoder-camera))),
        encoder_minus_camera_shift_counts=float(base.wrap(encoder-camera)*4096/base.TAU),
        interpretation='Raw native count change minus raw-camera pose change. Saved encoder reference changes cancel by using counts. No recalibration or encoder-only attribution.')


def anchored_pairs(trial,lag,camera_zero):
    pairs=base.paired(trial,lag)
    for r in pairs:
        r['camera_from_user_upright_rad']=float(base.wrap(r['camera_rad']-camera_zero))
        r['camera_minus_encoder_anchored_rad']=float(base.wrap(r['camera_from_user_upright_rad']-r['encoder_rad']))
    return pairs


def camera_coverage(trial,lo,hi,lag):
    selected=[c for c in trial['camera'] if lo<=c['t']+lag<=hi]
    raw={(r.get('vision',{}).get('seq'),r.get('vision',{}).get('t')) for r in trial['raw_camera']
         if isinstance(r.get('vision',{}).get('t'),(int,float)) and lo<=base.camera_clock(r,trial['filter_report']['clock_anchors'])+lag<=hi}
    t=np.array([c['t'] for c in selected]);segments=[c['segment'] for c in selected]
    d=base.durations(t,np.ones(len(t),dtype=bool),segments,max_gap=base.CAMERA_GAP_S)
    return dict(valid_frames=len(selected),raw_unique_frames=len(raw),valid_fraction=len(selected)/len(raw) if raw else None,
        observed_valid_intervals=d,largest_valid_sample_gap_s=float(np.diff(t).max()) if len(t)>1 else None,
        pivot_x_px=base.stats([c['pivot_x'] for c in selected]),pivot_y_px=base.stats([c['pivot_y'] for c in selected]),
        marker_length_px=base.stats([c['length'] for c in selected]),
        note='Valid interval coverage breaks at every rejected frame or camera gap>75ms. Pivot pixel motion is independent geometry, without metric rail calibration.')


def metrics_window(trial,pairs,lo,hi,camera_zero,lag):
    ss=[s for t,s in zip(trial['host'],trial['states']) if lo<=t<=hi and s['mode']==3]
    tt=np.array([t for t,s in zip(trial['host'],trial['states']) if lo<=t<=hi and s['mode']==3])
    rr=[r for r in pairs if lo<=r['encoder_query_host_s']<=hi and r['mode']==3]
    tpair=np.array([r['host_s'] for r in rr]);segments=[r['segment'] for r in rr]
    camera_angles=np.array([r['camera_from_user_upright_rad'] for r in rr])
    residual=np.array([r['camera_minus_encoder_anchored_rad'] for r in rr])
    native_hold=np.array([abs(s['theta'])<=.15 and abs(s['omega'])<=.5 and s['fault']==0 for s in ss])
    centered=np.array([abs(s['x'])<=.05 for s in ss])
    image_hold=np.array([abs(r['camera_from_user_upright_rad'])<=.15 and r['camera_rate_rad_s'] is not None and abs(r['camera_rate_rad_s'])<=.5 for r in rr])
    image_centered=np.array([abs(r['cart_step_m'])<=.05 for r in rr])
    return dict(window_host_s=[lo,hi],requested_window_duration_s=hi-lo,
        telemetry_samples=len(ss),native_bal_observed=base.durations(tt,np.ones(len(tt),dtype=bool)),
        all_samples_healthy=bool(ss) and all(s['fault']==0 and s['flags']&1 for s in ss),
        encoder_angle_deg=signal_metrics(tt,np.degrees([s['theta'] for s in ss])),
        encoder_rate_rad_s=signal_metrics(tt,[s['omega'] for s in ss]),
        cart_step_position_m=signal_metrics(tt,[s['x'] for s in ss]),
        commanded_velocity_m_s=signal_metrics(tt,[s['velocity'] for s in ss]),
        demanded_acceleration_m_s2=signal_metrics(tt,[s['demand'] for s in ss]),
        commanded_acceleration_m_s2=signal_metrics(tt,[s['acceleration'] for s in ss]),
        camera_angle_from_user_upright_deg=angle_error_stats(camera_angles),
        camera_minus_encoder_deg=angle_error_stats(residual),
        camera_coverage=camera_coverage(trial,lo,hi,lag),
        native_angle_rate_criterion=base.durations(tt,native_hold),
        native_angle_rate_and_cart_criterion=base.durations(tt,native_hold&centered),
        independent_camera_angle_rate_criterion=base.durations(tpair,image_hold,segments,max_gap=base.CAMERA_GAP_S),
        independent_camera_angle_rate_and_step_cart_criterion=base.durations(tpair,image_hold&image_centered,segments,max_gap=base.CAMERA_GAP_S),
        cart_center_fraction=float(centered.mean()) if len(centered) else None,
        criterion='Descriptive angle/rate criterion: |angle|<=0.15rad and |rate|<=0.5rad/s. Separate cart centering criterion |step x|<=0.05m. Missing either criterion does not mean fallen or failed BAL. Camera rate is adjacent raw-vector finite difference.',
        velocity_semantics='STATE.velocity, STATE.demand and STATE.acceleration are commands; they do not independently measure cart motion. STATE.x is step-estimated position.')


def analyze_trial(trial,anchor,lag):
    summary,_=base.trial_summary(trial,lag)
    camera_zero=anchor['camera_image_angle_rad']['median']
    pairs=anchored_pairs(trial,lag,camera_zero)
    native=summary['native']
    first=first_balance_run(trial['host'],[s['mode'] for s in trial['states']])
    summary['native']['first_continuous_balance_run']=first
    summary['native']['duration_timebase']='Mapped board clock; host lower-envelope scale retained. Not walltime extrapolation.'
    # Base strict-camera criteria use raw image vertical; replace with explicit
    # anchored windows below instead of mixing two camera zero conventions.
    summary.pop('strict_camera_encoder_and_step_hold',None)
    summary.pop('strict_encoder_and_step_hold',None)
    summary['upright_anchor_same_view_confirmed']=trial['name'] in ('ref533-bw8-auto25-01','ref533-bw8-auto25-02','ref533-bw8-bal10-01')
    summary['interpretation']='Native BAL is a controller state. Angle/rate and cart-centering criteria are separate descriptive observations. STATE.x is step-estimated; velocity and acceleration are commands. Camera user-upright comparisons are qualified by camera_anchor_scope. No physical balance or encoder-map acceptance.'
    summary['camera_anchor_scope']='Confirmed same camera view as upright capture.' if summary['upright_anchor_same_view_confirmed'] else 'After user handling: unchanged camera orientation unverified. Anchored numbers are conditional comparisons, not established physical upright errors. Rest before/after raw image changes remain locally informative.'
    summary['raw_camera_zero_caution']='Base auto_disagreement/angle_bins retain raw image vertical. Physical-upright comparisons are only in new explicit anchored fields.'
    summary['postcapture_windows']={}
    if first:
        lo,hi=first['first_s'],first['last_s']
        summary['postcapture_windows']['entire_first_BAL']=metrics_window(trial,pairs,lo,hi,camera_zero,lag)
        if hi>lo+2:
            start=lo+2
            summary['postcapture_windows']['after_2s']=metrics_window(trial,pairs,start,hi,camera_zero,lag)
            if hi-start>=5:
                first5=metrics_window(trial,pairs,start,start+5,camera_zero,lag)
                last5=metrics_window(trial,pairs,hi-5,hi,camera_zero,lag)
                summary['postcapture_windows']['first_5s_after_2s']=first5
                summary['postcapture_windows']['last_5s']=last5
                summary['first_to_last_5s']=dict(cart_mean_change_m=last5['cart_step_position_m']['mean']-first5['cart_step_position_m']['mean'],
                    encoder_mean_change_deg=last5['encoder_angle_deg']['mean']-first5['encoder_angle_deg']['mean'],
                    windows_overlap=hi-start<10,interpretation='First5s starts2s after first BAL entry; last5s ends at its final observed BAL sample.')
            sensitivity=[]
            for candidate in (lag,0.,lag-.010,lag+.010):
                rr=[r for r in anchored_pairs(trial,candidate,camera_zero) if start<=r['encoder_query_host_s']<=hi and r['mode']==3]
                sensitivity.append(dict(lag_s=candidate,**angle_error_stats([r['camera_minus_encoder_anchored_rad'] for r in rr])))
            summary['postcapture_alignment_sensitivity']=sensitivity
    summary['same_view_up_down_contrasts']=[]
    for phase,rest in summary['rests'].items():
        if not rest.get('encoder_theta_rad') or not rest.get('camera_image_upright_rad'):continue
        result=supplement.anchor_contrast(upright_encoder_angle(anchor,trial['reference']),camera_zero,
            rest['encoder_theta_rad']['median'],rest['camera_image_upright_rad']['median'])
        result.update(phase=phase,upright_anchor_same_view_confirmed=summary['upright_anchor_same_view_confirmed'],encoder_rest_qualified=rest['encoder_rest_qualified'],camera_coverage_qualified=rest['camera_coverage_qualified'],
            camera_valid_fraction=rest['camera_valid_fraction'],
            pivot_delta_from_upright_px=[rest['camera_pivot_x_px']['median']-anchor['camera_pivot_x_px']['median'],rest['camera_pivot_y_px']['median']-anchor['camera_pivot_y_px']['median']],
            vector_length_relative_change=rest['camera_length_px']['median']/anchor['camera_vector_length_px']['median']-1,
            limitation=summary['camera_anchor_scope']+' Cart/pivot location and marker projection still differ. User natural upright is not measured gravity vertical; residual is not a validated encoder map.')
        summary['same_view_up_down_contrasts'].append(result)
    if trial['report'].get('command')=='bal':
        summary['native_command']='BAL'
        summary['duration_end_interpretation']='Direct BAL10 terminates in recorded DURATION fault3; harness success remains false. Mode3 duration and observed behavior are reported separately. No AUTO return expected.'
    else:summary['native_command']='AUTO'
    return summary,pairs


def plot_trial(trial,summary,pairs,anchor,output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'encoder-tightening-matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    first=summary['native']['first_continuous_balance_run']
    active=[t for t,s in zip(trial['host'],trial['states']) if s['mode'] in base.AUTO_MODES]
    if not active:return
    origin=active[0];end=active[-1]
    fig,axes=plt.subplots(5,1,figsize=(12,12),sharex=True,layout='constrained')
    def line(ax,x,y,segments=None,**kwargs):
        xx=[];yy=[]
        for i,(a,b) in enumerate(zip(x,y)):
            if i and (x[i]-x[i-1]>(base.GAP_S if segments is None else base.CAMERA_GAP_S)+1e-9 or segments is not None and segments[i]!=segments[i-1]):xx.append(np.nan);yy.append(np.nan)
            if i and abs(b-y[i-1])>180 and kwargs.get('label','').startswith(('Encoder','Camera')):xx.append(np.nan);yy.append(np.nan)
            xx.append(a-origin);yy.append(b)
        ax.plot(xx,yy,**kwargs)
    tt=trial['host'];ss=trial['states'];cc=trial['camera'];camera_zero=anchor['camera_image_angle_rad']['median']
    line(axes[0],tt,np.degrees([s['theta'] for s in ss]),label='Encoder relative 533',lw=.8)
    line(axes[0],[c['t'] for c in cc],np.degrees(base.wrap(np.array([c['angle'] for c in cc])-camera_zero)),[c['segment'] for c in cc],label='Camera relative user upright',lw=.8,alpha=.85)
    line(axes[1],[r['host_s'] for r in pairs],np.degrees([r['camera_minus_encoder_anchored_rad'] for r in pairs]),[r['segment'] for r in pairs],label='Camera − encoder, fixed −17ms proxy',lw=.8)
    line(axes[2],tt,[100*s['x'] for s in ss],label='Step-estimated cart x',lw=.8)
    line(axes[3],tt,[s['velocity'] for s in ss],label='Commanded velocity',lw=.7)
    line(axes[4],tt,[s['demand'] for s in ss],label='Demanded acceleration',lw=.7,alpha=.35)
    line(axes[4],tt,[s['acceleration'] for s in ss],label='Commanded acceleration',lw=.7)
    for ax,label in zip(axes,['Angle (deg)','Residual (deg)','Cart (cm)','Command (m/s)','Command (m/s²)']):
        ax.set_ylabel(label);ax.grid(alpha=.2);ax.legend(loc='upper right',fontsize=8)
        if first:ax.axvspan(first['first_s']-origin,first['last_s']-origin,color='green',alpha=.08)
    axes[-1].set_xlabel('Seconds from first native active state');axes[-1].set_xlim(-.2,end-origin+.2)
    fig.suptitle(trial['name']+(' — confirmed same-view upright anchor' if summary['upright_anchor_same_view_confirmed'] else ' — conditional upright anchor (post-handling view unverified)')+'; shaded native BAL')
    fig.savefig(output/(trial['name']+'-active.png'),dpi=160)
    if first and first['last_s']-first['first_s']>2:
        axes[-1].set_xlim(first['first_s']+2-origin,first['last_s']-origin)
        win=summary['postcapture_windows']['after_2s']
        ylim=max(2.,win['encoder_angle_deg']['max_abs']*1.2,win['camera_angle_from_user_upright_deg'].get('max_abs_deg',0)*1.1)
        axes[0].set_ylim(-ylim,ylim);axes[1].set_ylim(-max(1,win['camera_minus_encoder_deg'].get('max_abs_deg',0)*1.1),max(1,win['camera_minus_encoder_deg'].get('max_abs_deg',0)*1.1))
        xmax=max(.5,100*win['cart_step_position_m']['max_abs']*1.1);axes[2].set_ylim(-xmax,xmax)
        for ax,key in ((axes[3],'commanded_velocity_m_s'),(axes[4],'demanded_acceleration_m_s2')):
            extent=max(.02,win[key]['max_abs']*1.1);ax.set_ylim(-extent,extent)
        fig.suptitle(trial['name']+' — first continuous BAL, starting 2s after capture')
        fig.savefig(output/(trial['name']+'-postcapture.png'),dpi=160)
    plt.close(fig)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--upright',type=Path,required=True)
    p.add_argument('--lag-from',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--repeat-upright',type=Path,action='append',default=[],help='Additional motor-disabled upright captures; diagnostic only, never replace frozen anchor.')
    a=p.parse_args(argv)
    prior=base.read_json(a.lag_from);lag=prior['frozen_lag']['lag_s']
    upright=base.load_trial(a.upright);anchor=supplement.summarize_anchor(upright)
    paths=[a.input] if (a.input/'report.json').exists() else sorted({f.parent for f in a.input.rglob('report.json') if f.parent.name.startswith('ref533-')})
    upright_repeats=[]
    for path in a.repeat_upright:
        repeat=base.load_trial(path);description=supplement.summarize_anchor(repeat)
        comparison=upright_repeat_difference(anchor,description)
        comparison['pivot_delta_px']=[description['camera_pivot_x_px']['median']-anchor['camera_pivot_x_px']['median'],description['camera_pivot_y_px']['median']-anchor['camera_pivot_y_px']['median']]
        comparison['marker_length_relative_change']=description['camera_vector_length_px']['median']/anchor['camera_vector_length_px']['median']-1
        comparison['camera_view_caution']='Small pivot and marker-length changes support similar image geometry but do not independently certify fixed camera orientation.'
        upright_repeats.append(dict(capture=description,vs_original_upright=comparison,raw_sources=repeat['sources']))
    included=[];excluded=[];sources=[a.lag_from,*upright['sources'],Path(__file__),Path(__file__).with_name('analyze.py'),Path(__file__).with_name('analyze_upright.py')]
    for repeat in upright_repeats:sources.extend(repeat.pop('raw_sources'))
    for path in paths:
        raw=base.read_json(path/'report.json')
        files=[f for f in path.rglob('*') if f.is_file()]
        if path.name in EXCLUDED:
            excluded.append(dict(trial=path.name,reason=EXCLUDED[path.name]));sources.extend(files);continue
        command=raw.get('command')
        if not ('-auto' in path.name or command=='bal'):
            excluded.append(dict(trial=path.name,reason='Recovery/rest session, not an AUTO or BAL performance recording.'));sources.extend(files);continue
        trial=base.load_trial(path)
        if trial['reference']!=533:
            raise ValueError(f'{path}: mixed or non533 reference, refusing upright cohort anchoring')
        if not any(s['mode'] in base.AUTO_MODES for s in trial['states']):
            excluded.append(dict(trial=path.name,reason='No active native AUTO/BAL states; not a performance trial.'));sources.extend(files);continue
        included.append(trial);sources.extend(trial['sources'])
    if not included:raise ValueError('no eligible reference533 trials')
    included.sort(key=lambda t:t['host'][0])
    a.output.mkdir(parents=True,exist_ok=False)
    reports=[]
    for trial in included:
        summary,pairs=analyze_trial(trial,anchor,lag);reports.append(summary)
        (a.output/(trial['name']+'-pairs.ndjson')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in pairs))
        plot_trial(trial,summary,pairs,anchor,a.output)
    unique={str(f.resolve()):f for f in sources}
    report=dict(schema='same-view-reference533-offline-v1',hardware_accepted=False,physical_balance_accepted=False,
        nonlinear_map_validated=False,upright_anchor=anchor,upright_repeats=upright_repeats,reference_counts=533,trials=reports,excluded=excluded,
        timeline='Two BW8 AUTO runs sustained BAL after upright reference520→533 with unchanged gains. User then handled the pole; one BW6 run and a later BW8 run after fullHOME did not sustain BAL. These later failures prevent attributing success/failure solely to bandwidth. Failed handled attempt was excluded before gain write or AUTO.',
        frozen_lag=dict(lag_s=lag,training_trial=prior['frozen_lag']['training_trial'],refit=False,
            interpretation='Fixed old-cohort alignment proxy only; changed view/processing may change latency. Zero and±10ms sensitivity is reported for postcapture data. No calibrated exposure latency claim.'),
        method=dict(camera_angle='atan2(bob_x-pivot_x,pivot_y-bob_y), subtract median from user upright-check-02 only for the new unchanged-camera cohort. No camera fusion/calibrated theta or mirrored encoder is used.',
            geometry='Camera moved before upright-check-02. Same view confirmed for direct BAL10 and first two533 BW8 runs; later post-handling orientation is unverified and anchored figures are conditional. This anchor is never applied to old520 frames. Natural upright is not independent gravity metrology.',
            filters='Base loader: valid measured source, confidence>=0.8, no stale/error, source/collector age<=150ms, finite marker geometry, length within20% of trial median. Every rejected frame breaks camera segments; camera gaps>75ms and telemetry gaps>30ms break interpolation/continuity.',
            native_info='encoder_raw_age_us measures duration since raw count last changed, never acquisition freshness. INFO native counts and STATE reconstructed counts remain separate.',
            jitter='Demanded/governed acceleration RMS, adjacent total variation and first-difference rate RMS are descriptive jitter proxies, not physical cart accelerometry or an independently measured bandwidth.',
            windows='First uninterrupted native BAL segment only. Postcapture window starts2s after entry; first/last5s comparisons are labeled if overlapping. Centering criterion is separate from balance state.',
            uncertainty='Temporally correlated samples; no confidence intervals or acceptance promotion. Step counts do not independently verify physical cart displacement.'),
        source_hashes=[dict(path=str(path),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for path,f in sorted(unique.items())])
    (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for s in reports:
        w=s['postcapture_windows'].get('after_2s',{})
        print(json.dumps(dict(trial=s['trial'],native=s['native'],after2={k:w.get(k) for k in ('encoder_angle_deg','cart_step_position_m','camera_angle_from_user_upright_deg','camera_minus_encoder_deg','demanded_acceleration_m_s2','commanded_acceleration_m_s2')},first_last=s.get('first_to_last_5s'),rest_shift=s['rest_differentials']['before_auto_rest_to_after_auto_rest'])))
    return 0

if __name__=='__main__':raise SystemExit(main())
