#!/usr/bin/env python3
"""Offline original-camera-frame shape supplement. Descriptive fits are NOT calibration.

python analyze_upright.py --analysis PRIOR/report.json --upright RAW_UPRIGHT_RUN
                         --output NEW_DIRECTORY
Only the prior analysis' fixed-reference AUTO trials are considered. The prior
lag remains frozen, and all descriptive model coefficients are fit on its first
AUTO trial then evaluated unchanged on later trials. No hardware/network I/O.
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

_spec=importlib.util.spec_from_file_location('encoder_tightening_base',Path(__file__).with_name('analyze.py'))
base=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

MODELS={
    'constant_timing':['constant'],
    'constant_plus_omega':['constant','omega'],
    'angle_shape':['constant','sin(q)','cos(q)','sin(2q)','cos(2q)'],
    'angle_shape_plus_omega':['constant','sin(q)','cos(q)','sin(2q)','cos(2q)','omega'],
    'angle_shape_omega_direction':['constant','sin(q)','cos(q)','sin(2q)','cos(2q)','omega','sign(omega)'],
}


def anchor_contrast(up_encoder,up_camera,down_encoder,down_camera):
    encoder=float(base.wrap(down_encoder-up_encoder))
    camera=float(base.wrap(down_camera-up_camera))
    residual=float(base.wrap(camera-encoder))
    return dict(encoder_separation_rad=encoder,camera_separation_rad=camera,
        encoder_separation_positive_deg=float(np.degrees(encoder)%360),
        camera_separation_positive_deg=float(np.degrees(camera)%360),
        camera_minus_encoder_separation_rad=residual,camera_minus_encoder_separation_deg=float(np.degrees(residual)),
        meaning='Difference of the two up-to-down angular separations; independent of a constant zero offset for either sensor.')


def error_stats(residual):
    r=np.asarray(residual,dtype=float)
    if not len(r):return dict(n=0)
    return dict(n=len(r),median_deg=float(np.degrees(np.median(r))),
        rms_deg=float(np.degrees(np.sqrt(np.mean(r*r)))),p95_abs_deg=float(np.degrees(np.percentile(abs(r),95))))


def basis(rows,features):
    q=np.array([r['analysis_angle_rad'] for r in rows])
    w=np.array([r['encoder_rate_rad_s'] for r in rows])
    values={'constant':np.ones(len(rows)),'sin(q)':np.sin(q),'cos(q)':np.cos(q),
            'sin(2q)':np.sin(2*q),'cos(2q)':np.cos(2*q),'omega':w,'sign(omega)':np.sign(w)}
    return np.column_stack([values[f] for f in features])


def fit_models(trials):
    if not trials or not trials[0][1]:raise ValueError('first trial must contain AUTO pairs')
    name,training=trials[0]
    y=np.array([r['analysis_residual_rad'] for r in training])
    models={}
    for model,features in MODELS.items():
        x=basis(training,features)
        beta,_,rank,_=np.linalg.lstsq(x,y,rcond=None)
        evaluations=[]
        for trial,rows in trials:
            residual=np.array([r['analysis_residual_rad'] for r in rows])-basis(rows,features)@beta
            evaluations.append(dict(trial=trial,in_sample=trial==name,**error_stats(residual)))
        models[model]=dict(training_trial=name,features=features,coefficients=beta.tolist(),rank=int(rank),
            condition_number=float(np.linalg.cond(x)),evaluation=evaluations,
            units='Angle target is radians. Omega coefficient is rad/(rad/s), numerically seconds; sign coefficient is radians.',
            acceptance=False,interpretation='Descriptive sensor-disagreement model, never an encoder correction. No coefficients refit on later trials.')
    return models


def summarize_anchor(trial):
    states,camera=trial['states'],trial['camera']
    if not camera:raise ValueError('upright run has no qualifying raw camera geometry')
    raw=[i['encoder_raw'] for i in trial['infos'] if isinstance(i.get('encoder_raw'),int)]
    enc=base.circular_summary([s['theta'] for s in states])
    cam=base.circular_summary([c['angle'] for c in camera])
    return dict(trial=trial['name'],reference_during_measurement=trial['reference'],
        native_encoder_counts=base.circular_summary(raw,4096),encoder_angle_rad=enc,camera_image_angle_rad=cam,
        camera_pivot_x_px=base.stats([c['pivot_x'] for c in camera]),camera_pivot_y_px=base.stats([c['pivot_y'] for c in camera]),
        camera_vector_length_px=base.stats([c['length'] for c in camera]),
        upright_camera_minus_encoder_deg=float(np.degrees(base.wrap(cam['median']-enc['median']))),
        encoder_rate_abs_rad_s=base.stats([abs(s['omega']) for s in states]),
        disabled_healthy_all=all(s['mode']==0 and s['flags']&3==1 and s['fault']==0 for s in states),
        camera_filters=trial['filter_report'],basis='User-presented natural upright pose. No independent gravity-vertical instrument is recorded.',
        firmware_calibration_produced=False)


def contrasts(anchor,trial_summaries):
    # The operator confirmed a camera move between these cohorts. Do not form
    # an angular up/down contrast across their different projection geometry.
    result=[]
    ux=anchor['camera_pivot_x_px']['median'];uy=anchor['camera_pivot_y_px']['median']
    for trial in trial_summaries:
        for phase,rest in trial['rests'].items():
            if not rest.get('camera_pivot_x_px'):continue
            dx=rest['camera_pivot_x_px']['median']-ux;dy=rest['camera_pivot_y_px']['median']-uy
            result.append(dict(trial=trial['trial'],phase=phase,available=False,
                reason='Operator confirmed camera framing moved before the upright check. No cross-frame angle anchoring is permitted.',
                pivot_delta_from_upright_px=[dx,dy],pivot_distance_from_upright_px=math.hypot(dx,dy)))
    return result


def group_summaries(trials):
    per_trial=[]
    for name,rows in trials:
        q=np.array([r['analysis_angle_rad'] for r in rows]);w=np.array([r['encoder_rate_rad_s'] for r in rows])
        residual=np.array([r['analysis_residual_rad'] for r in rows])
        angle_bins=[]
        for center in range(-165,180,30):
            mask=abs(base.wrap(q-math.radians(center)))<math.radians(15)
            pos=mask&(w>.3);neg=mask&(w<-.3)
            row=dict(center_deg=center,all=error_stats(residual[mask]),positive=error_stats(residual[pos]),negative=error_stats(residual[neg]))
            row['positive_minus_negative_median_deg']=float(np.degrees(np.median(residual[pos])-np.median(residual[neg]))) if min(pos.sum(),neg.sum())>=10 else None
            angle_bins.append(row)
        speed={}
        for label,lo,hi in [('0_to_0.5',0,.5),('0.5_to_3',.5,3),('3_to_8',3,8),('8_plus',8,float('inf'))]:
            mask=(abs(w)>=lo)&(abs(w)<hi)
            speed[label]=error_stats(residual[mask])
        per_trial.append(dict(trial=name,angle_bins=angle_bins,speed_bins_abs_rad_s=speed,
            near_upright_low_speed=error_stats(residual[(abs(q)<=.25)&(abs(w)<=.5)]),
            interpretation='Angle/speed/direction bins are descriptive and unequally sampled. They do not isolate hysteresis from dynamics, cart location, projection, motion blur, or timing jitter.'))
    return per_trial


def plot_report(anchor,static,trials,models,output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'encoder-tightening-matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    colors=plt.cm.tab10(np.arange(len(trials)))
    for color,(name,rows) in zip(colors,trials):
        q=np.degrees([r['analysis_angle_rad'] for r in rows]);w=np.array([r['encoder_rate_rad_s'] for r in rows]);y=np.degrees([r['analysis_residual_rad'] for r in rows])
        axes[0,0].scatter(q,y,s=6,alpha=.25,color=color,label=name)
        axes[0,1].scatter(w,y,s=6,alpha=.25,color=color,label=name)
    q=np.linspace(-math.pi,math.pi,361)
    grid=[dict(analysis_angle_rad=float(x),encoder_rate_rad_s=0.) for x in q]
    shape=models['angle_shape']
    axes[0,0].plot(np.degrees(q),np.degrees(basis(grid,shape['features'])@np.array(shape['coefficients'])),color='black',lw=2,label='First-trial descriptive shape')
    axes[0,0].set(xlabel='Encoder angle relative to saved520 (degrees)',ylabel='Raw old-frame camera − encoder (degrees)')
    axes[0,1].set(xlabel='Firmware angular rate (rad/s)',ylabel='Raw old-frame camera − encoder (degrees)')
    for ax in axes[0]:ax.axhline(0,color='gray',ls=':');ax.legend(fontsize=7);ax.grid(alpha=.2)
    names=list(models);x=np.arange(len(names));width=.8/len(trials)
    for j,(name,_) in enumerate(trials):
        vals=[models[model]['evaluation'][j]['rms_deg'] for model in names]
        axes[1,0].bar(x+(j-(len(trials)-1)/2)*width,vals,width,label=name,color=colors[j])
    axes[1,0].set_xticks(x,['Offset','Offset + rate','Angle shape','Shape + rate','Shape + rate\n+ direction'],rotation=15)
    axes[1,0].set_ylabel('Residual RMS after descriptive fit (degrees)');axes[1,0].legend(fontsize=7);axes[1,0].grid(axis='y',alpha=.2)
    labels=[r['trial'].replace('bw8-','')+'/'+r['phase'].replace('_rest','').replace('before_auto','before').replace('after_auto','after') for r in static]
    axes[1,1].barh(np.arange(len(static)),[r['pivot_distance_from_upright_px'] for r in static],color='#d48b57')
    axes[1,1].set_yticks(np.arange(len(static)),labels,fontsize=7);axes[1,1].set_xlabel('Pivot displacement from later upright image (pixels)')
    axes[1,1].set_title('Camera moved: cross-frame up/down angle contrast omitted',fontsize=9);axes[1,1].grid(axis='x',alpha=.2)
    fig.suptitle('Original520 frame and frozen-lag diagnostics — no nonlinear calibration validated',fontsize=13)
    fig.savefig(output/'upright-and-shape.png',dpi=170);plt.close(fig)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--upright',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    prior=base.read_json(a.analysis)
    upright=base.load_trial(a.upright)
    anchor=summarize_anchor(upright)
    summaries=[s for s in prior['trials'] if s.get('reference_counts')==anchor['reference_during_measurement'] and s['native']['auto_mode_duration']['sample_count']>0]
    if len(summaries)<2:raise ValueError('need the first training AUTO trial and at least one later fixed-reference trial')
    trials=[];pair_files=[]
    for summary in summaries:
        path=a.analysis.parent/(summary['trial']+'-pairs.ndjson');pair_files.append(path)
        rows=[r for r in base.read_lines(path) if r['mode'] in base.AUTO_MODES]
        for r in rows:
            r['analysis_angle_rad']=r['encoder_rad']
            r['analysis_residual_rad']=r['residual_rad']
        trials.append((summary['trial'],rows))
    models=fit_models(trials)
    static=contrasts(anchor,summaries)
    groups=group_summaries(trials)
    improvements=[]
    for i in range(1,len(trials)):
        constant=models['constant_timing']['evaluation'][i]['rms_deg'];shape=models['angle_shape']['evaluation'][i]['rms_deg']
        improvements.append(dict(trial=trials[i][0],offset_timing_rms_deg=constant,angle_shape_rms_deg=shape,relative_rms_reduction=1-shape/constant))
    a.output.mkdir(parents=True,exist_ok=False)
    sources=[a.analysis,*pair_files,*upright['sources'],Path(__file__),Path(__file__).with_name('analyze.py')]
    report=dict(schema='original520-frame-disagreement-supplement-v2',hardware_accepted=False,nonlinear_calibration_validated=False,
        upright=anchor,frozen_lag=prior['frozen_lag'],static_up_down_contrasts=static,models=models,
        angle_direction_speed_groups=groups,heldout_shape_improvement=improvements,
        conclusions=dict(offset_and_timing_sufficient=False if all(i['relative_rms_reduction']>.15 for i in improvements) else None,
            evidence='A frozen constant+lag leaves several degrees of discrepancy. First-trial angle features reduce RMS on later trials more consistently than a residual rate or direction term; this supports repeatable angle-associated disagreement in these trajectories.',
            scope='The evidence identifies sensor-pair disagreement, not which sensor is wrong. Camera projection/marker geometry, view changes, timing jitter, coupling/loading, and magnetic encoder response remain possible contributors.',
            static_caution='Camera framing moved before the new upright check. Its camera anchor is never applied to old520 images. Cross-frame up/down angular comparisons are unavailable.',
            operational='Saving a measured upright can correct its zero. It cannot by itself establish accuracy away from upright or prove balance performance.'),
        method=dict(anchor='Original520 cohort retains its saved encoder zero and raw image vertical; no new upright anchoring is applied. Later upright summary is independent context only. Raw camera is derived from marker geometry; no fusion or saved camera calibration.',
            models='OLS on first native AUTO trial only, coefficients frozen on later trials; circular residuals kept on their small-error branch. No parameter or firmware calibration is emitted.',
            uncertainty='Frames are temporally correlated and pose/speed/cart state are not independently varied. No formal confidence interval or systematic nonlinear calibration validation.',
            provenance='Prior source hashes are retained in the linked base report; this manifest hashes that report, its paired data, upright raw sources, and both scripts.'),
        source_hashes=[dict(path=str(f.resolve()),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in sources])
    (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    plot_report(anchor,static,trials,models,a.output)
    print(json.dumps(dict(output=str(a.output),upright_counts=anchor['native_encoder_counts'],upright_residual_deg=anchor['upright_camera_minus_encoder_deg'],heldout_shape_improvement=improvements,
        static_contrasts=[{k:r[k] for k in ('trial','phase','available','pivot_delta_from_upright_px')} for r in static]),indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
