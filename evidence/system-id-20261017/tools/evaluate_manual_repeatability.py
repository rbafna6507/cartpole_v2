#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.9,<4", "mujoco>=3.15,<4"]
# ///
"""Score complete new raw passive recordings against frozen Oct16 coefficients.

Annotations must be independently selected/frozen before scoring; their exact
SHA256 is mandatory. Preview/strided data are not accepted raw recordings. No
refitting, hardware, calibration changes, or model promotion. Camera timestamps
are receipt/read proxies on an explicitly asserted common host, not exposures.
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np

FREEZE_SHA='04befe14b16a54e5288d4326a7ca5d826e8c5a169dc20206dd1108ea160aa744'
MODEL_SHA='cc878a16d1611f8f03534a44611f9172c0eab2d2c968a6ce1f0c351b5880c7e0'
SIM_PROVENANCE_SHA='9dad734ef973e93900ae4f8ce55d021a169f18211edd873ab5fe5bab48ab396d'
SIM_SOURCES={'backend.py':'1eadad422f96d8003b652bd43e5fec84b530acec75801737bc8be6b6a081b34f',
    'config.py':'48863494088e95a806cbe66fcf74d6e247d1406dad24807f819edbda55e7cb91',
    'model.py':'090842af8212c34579ebf9653eab34a9ded7772a21fdbead3f2f938a52898d62'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def module_at(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def verify_annotation(path,pin):
    if sha(path)!=pin:raise ValueError('frozen annotation hash mismatch')
    annotation=json.loads(Path(path).read_text())
    if annotation.get('selected_before_scoring') is not True:raise ValueError('annotations not frozen before scoring')
    return annotation


def frozen_method(repo):
    analysis=Path(repo)/'evidence/system-id-20261016/analysis'
    if sha(analysis/'manual-ringdown-train-02-freeze.json')!=FREEZE_SHA:raise ValueError('training freeze changed')
    evaluator=module_at('frozen_repeatability_evaluator',analysis/'heldout/evaluate_passive.py')
    fitter,training,freeze=evaluator.verify_freeze(analysis)
    if training['magnetic_reports']['viscous']['parameters']!=freeze['candidate_parameters']:raise ValueError('frozen coefficients disagree')
    return fitter,training,freeze,evaluator


def score(episodes,training_report,fitter,evaluator):
    aggregate=evaluator.score_frozen(episodes,training_report,fitter)
    individual=[]
    for ep in episodes:
        report=evaluator.score_frozen([ep],training_report,fitter);report['episode_id']=ep['episode_id'];individual.append(report)
    return dict(aggregate=aggregate,per_episode=individual,
        aggregate_fixed_gates_pass=bool(aggregate['statistical_checks_pass']),
        all_episodes_fixed_gates_pass=bool(all(r['statistical_checks_pass'] for r in individual)),
        claim='Unchanged frozen short-horizon gates, reported both aggregate and per annotated release; no promotion.')


def verify_simulator_sources(directory):
    for name,pin in SIM_SOURCES.items():
        if sha(Path(directory)/name)!=pin:raise ValueError('frozen simulator source changed: '+name)


def continuous(episode,parameters,config_path):
    from cartpole_sdk.sim.backend import MujocoBackend
    from cartpole_sdk.sim.config import SimulationConfig
    if sha(config_path)!=MODEL_SHA:raise ValueError('frozen MuJoCo model config changed')
    verify_simulator_sources(Path(sys.modules[MujocoBackend.__module__].__file__).parent)
    provenance_path=Path(config_path).with_name('provenance.json')
    if sha(provenance_path)!=SIM_PROVENANCE_SHA:raise ValueError('frozen simulator provenance changed')
    sim_provenance=json.loads(provenance_path.read_text())
    config=SimulationConfig(**json.loads(Path(config_path).read_text()))
    if asdict(config)!=sim_provenance['full_simulation_config']:raise ValueError('frozen full simulator config changed')
    if config.physics_dt_ns*config.control_steps!=1_000_000:raise ValueError('frozen comparison requires one1ms physics step per call')
    length=parameters['effective_length_m'];gamma=parameters['angular_damping_per_s'];bias=parameters['angle_offset_rad']
    if config.effective_length_m!=length or abs(config.hinge_damping-gamma*.75*config.pole_mass_kg*length**2)>1e-15:
        raise ValueError('MuJoCo physics differs from frozen coefficients')
    t=np.array(episode['t_s'],float);q=np.unwrap(episode['theta_rad']);delta=np.diff(t)
    if len(t)<40 or np.any(delta<=0) or max(delta)>.05:raise ValueError('continuous rollout requires contiguous samples without gaps over50ms')
    i=max(10,int(np.searchsorted(t,t[0]+.1)))
    if i>=len(t)-8:raise ValueError('insufficient rollout after initialization')
    w=float(np.polyfit(t[i-10:i+1]-t[i],q[i-10:i+1],2)[-2]);sim=MujocoBackend(config);rows=[];saturated=False;max_a=0.;max_x=0.;max_force=0.
    try:
        sim.reset(state=(0.,0.,float(q[i]-bias),w))
        for j in range(i+1,len(t)):
            n=round((t[j]-t[j-1])*1000)
            if n<=0 or abs(n*.001-(t[j]-t[j-1]))>1e-7:raise ValueError('observations are not on1ms board grid')
            for _ in range(n):
                sim.step(None);d=sim.diagnostics;saturated|=d.force_saturated;max_a=max(max_a,abs(d.achieved_acceleration_m_s2));max_x=max(max_x,abs(sim.ground_truth.x));max_force=max(max_force,abs(d.applied_force_n))
            predicted=sim.ground_truth.theta+bias;error=math.atan2(math.sin(predicted-q[j]),math.cos(predicted-q[j]));rows.append([float(t[j]),float(q[j]),float(q[j]+error),error])
    finally:sim.close()
    if saturated or max_a>1e-9:raise ValueError('fixed-cart simulation assumption failed')
    errors=np.array(rows)[:,3]
    return dict(episode_id=episode['episode_id'],reset_count=1,initial_t_s=float(t[i]),initial_raw_angle_rad=float(q[i]),initial_omega_rad_s=w,
        initial_velocity_support_s=float(t[i]-t[i-10]),initial_prefix_excluded_s=float(t[i]-t[0]),
        duration_s=float(t[-1]-t[i]),samples=len(rows),rmse_rad=float(np.sqrt(np.mean(errors**2))),p95_rad=float(np.quantile(abs(errors),.95)),
        force_saturated=saturated,maximum_cart_acceleration=max_a,maximum_abs_cart_x_m=max_x,maximum_abs_force_n=max_force,
        full_simulation_config=asdict(config),reading_columns=['board_relative_s','measured_raw_angle_rad','predicted_raw_angle_rad','wrapped_error_rad'],readings=rows,
        scope='One initial condition, past11 angles over40ms at250Hz; continuous diagnostic after~0.1s prefix. Fixed cart and local phase assumed, no acceptance gate.')


def forecast_readings(episode,coefficients,config,fitter):
    """Expose readings from the frozen predict algorithm without changing it."""
    rows=[]
    for t,q,_ in fitter.segments([episode],config):
        i=max(10,int(np.searchsorted(t,t[0]+.1)))
        while i+8<len(t):
            end=int(np.searchsorted(t,t[i]+config['prediction_horizon_s'],side='right'))
            if t[end-1]-t[i]<.9*config['prediction_horizon_s']:break
            w=float(np.polyfit(t[i-10:i+1]-t[i],q[i-10:i+1],2)[-2]);pred=float(q[i]);values=[]
            for j in range(i+1,end):
                dt=t[j]-t[j-1];n=max(1,math.ceil(dt/.001))
                for _ in range(n):pred,w=fitter.advance(pred,w,dt/n,coefficients)
                err=math.atan2(math.sin(pred-q[j]),math.cos(pred-q[j]));values.append([float(t[j]),float(q[j]),float(q[j]+err),err])
            rows.append(dict(start_s=float(t[i]),initial_omega_rad_s=float(np.polyfit(t[i-10:i+1]-t[i],q[i-10:i+1],2)[-2]),readings=values));i=end
    errors=np.array([p[3] for window in rows for p in window['readings']]);reference=fitter.predict(fitter.segments([episode],config),coefficients,config)
    if len(errors) and abs(float(np.sqrt(np.mean(errors**2)))-reference['prediction_rmse_rad'])>1e-12:raise ValueError('plotted forecasts differ from frozen predictor')
    return rows


def secondary_candidate(path,pin):
    if sha(path)!=pin:raise ValueError('secondary candidate source hash mismatch')
    candidate=json.loads(Path(path).read_text());c=candidate['coefficients']
    if len(c)!=4 or any(not math.isfinite(x) for x in c) or c[1]<0 or c[3]<0:raise ValueError('invalid frozen secondary candidate')
    return candidate


def continuous_ode(episode,coefficients,fitter):
    t=np.array(episode['t_s'],float);q=np.unwrap(episode['theta_rad']);delta=np.diff(t)
    if len(t)<40 or np.any(delta<=0) or max(delta)>.05:raise ValueError('continuous ODE requires contiguous samples without gaps over50ms')
    i=max(10,int(np.searchsorted(t,t[0]+.1)))
    if i>=len(t)-8:raise ValueError('insufficient continuous ODE support')
    initial_w=float(np.polyfit(t[i-10:i+1]-t[i],q[i-10:i+1],2)[-2]);pred=float(q[i]);w=initial_w;rows=[]
    for j in range(i+1,len(t)):
        dt=t[j]-t[j-1];n=max(1,math.ceil(dt/.001))
        for _ in range(n):pred,w=fitter.advance(pred,w,dt/n,coefficients)
        error=math.atan2(math.sin(pred-q[j]),math.cos(pred-q[j]));rows.append([float(t[j]),float(q[j]),float(q[j]+error),error])
    errors=np.array(rows)[:,3]
    return dict(episode_id=episode['episode_id'],solver='frozen passive_fit.advance',reset_count=1,initial_t_s=float(t[i]),
        initial_raw_angle_rad=float(q[i]),initial_omega_rad_s=initial_w,initial_velocity_support_s=float(t[i]-t[i-10]),
        duration_s=float(t[-1]-t[i]),rmse_rad=float(np.sqrt(np.mean(errors**2))),p95_rad=float(np.quantile(abs(errors),.95)),
        samples=len(rows),readings=rows,reading_columns=['board_relative_s','measured_raw_angle_rad','predicted_raw_angle_rad','wrapped_error_rad'])


def observed_support(times,lo,hi,*,delivered):
    t=np.asarray(times,float)
    if len(t) and (np.any(np.diff(t)<=0) or t[0]<lo or t[-1]>hi):raise ValueError('ordered interval-local camera support required')
    return dict(valid_samples=len(t),delivered_frames=delivered,valid_fraction_of_delivered=len(t)/delivered if delivered else None,
        max_unobserved_gap_including_edges_s=float(max(np.diff(np.r_[lo,t,hi]))),
        first_last_valid_s=[float(t[0]),float(t[-1])] if len(t) else None,
        time_basis='board-relative receipt mapping proxy; fractions use delivered frames, not expected exposures')


def period_diagnostic(t,q,*,max_gap_s=.05,hysteresis_rad=.025):
    t=np.asarray(t,float);q=np.asarray(q,float)
    if len(t)<8 or t.shape!=q.shape or not np.isfinite(t).all() or not np.isfinite(q).all() or np.any(np.diff(t)<=0):raise ValueError('finite ordered angle samples required')
    center=float(np.median(q));v=q-center;armed=False;candidate=None;crossings=[]
    for i in range(1,len(t)):
        if t[i]-t[i-1]>max_gap_s:armed=False;candidate=None;continue
        if v[i-1]<-hysteresis_rad:armed=True
        if armed and v[i-1]<=0<v[i]:candidate=float(t[i-1]+(t[i]-t[i-1])*(-v[i-1])/(v[i]-v[i-1]))
        if armed and candidate is not None and v[i]>=hysteresis_rad:crossings.append(candidate);armed=False;candidate=None
    periods=np.diff(crossings)
    return dict(center_rad=center,center_method='within-episode median, only for descriptive crossing timing; never applied to frozen forecasts',
        hysteresis_rad=hysteresis_rad,max_interpolation_gap_s=max_gap_s,upward_crossings_s=crossings,periods_s=periods.tolist(),
        median_period_s=float(np.median(periods)) if len(periods) else None,period_min_max_s=[float(min(periods)),float(max(periods))] if len(periods) else None,
        caveat='Missing crossings remain missing and may produce multi-cycle intervals; period variation also reflects finite amplitude, damping, offsets and sensing.')


def camera_diagnostics(repo,raw_records,identity,episodes,vision_path):
    from cartpole_sdk.identification.workflow import _source_stream
    helper_path=Path(repo)/'evidence/system-id-20261017/tools/analyze_camera_step_pulses.py';helper=module_at('repeatability_camera_helper',helper_path)
    rows,pin=helper.load_jsonl(Path(vision_path))
    with _source_stream(identity['collection_report']['path'],max_bytes=4*1024*1024) as f:run_report=json.loads(f.read(4*1024*1024+1))
    if pin['decompressed_sha256']!=run_report.get('camera',{}).get('sha256'):raise ValueError('camera/completion report hash mismatch')
    frames,camera=helper.camera_frames(rows);angles={(r['vision']['seq'],r['vision']['t']):r['vision'].get('image_angle_rad') for r in rows}
    states=[]
    for r in raw_records:
        if r.get('type')=='state' and (not states or r['state']['unwrapped_us']!=states[-1]['unwrapped_us']):states.append(r['state'])
    board=np.array([s['unwrapped_us']/1e6 for s in states]);received=np.array([s['received_ns']/1e9 for s in states]);mapped,mapping=helper.clock_proxy(board,received);origin=board[0]
    map_t=lambda b:mapping['receipt_origin_s']+mapping['intercept_s']+mapping['slope']*(b-mapping['board_origin_s'])
    for frame in frames:frame['t_relative_s']=(frame['t']-mapping['receipt_origin_s']-mapping['intercept_s'])/mapping['slope']+mapping['board_origin_s']-origin
    results=[]
    for ep in episodes:
        lo,hi=ep['t_s'][0],ep['t_s'][-1];chosen=[f for f in frames if lo<=f['t_relative_s']<=hi];good=[f for f in chosen if f['valid'] and helper.finite(angles[(f['seq'],f['t'])])]
        geometry=helper.window_stats(frames,lo,hi);t=np.array(ep['t_s']);q=np.unwrap(ep['theta_rad']);enc_host=np.array([map_t(origin+v) for v in t]);ep_period=period_diagnostic(enc_host,q)
        item=dict(episode_id=ep['episode_id'],geometry=geometry,angle_samples=len(good),encoder_period_host_proxy=ep_period,
            metric_stationarity_certified=False,physical_global_angle_calibration=False,
            angle_support=observed_support([f['t_relative_s'] for f in good],lo,hi,delivered=len(chosen)),
            pivot_support=observed_support([f['t_relative_s'] for f in chosen if f['valid']],lo,hi,delivered=len(chosen)))
        if len(good)>=8:
            ct=np.array([f['t'] for f in good]);cq=np.unwrap([math.pi-angles[(f['seq'],f['t'])] for f in good]);cp=period_diagnostic(ct,cq);pred=helper.interpolate_supported(enc_host,q,ct,max_gap=.05);usable=np.isfinite(pred)
            cmp=dict(samples=int(sum(usable)),relation='raw encoder = descriptive offset + gain*(pi - raw image_angle); same-run agreement only')
            if sum(usable)>=8 and np.ptp(cq[usable])>.05:
                line=np.linalg.lstsq(np.column_stack((np.ones(sum(usable)),cq[usable])),pred[usable],rcond=None)[0];error=pred[usable]-(line[0]+line[1]*cq[usable]);cmp.update(offset_rad=float(line[0]),projection_gain=float(line[1]),rmse_rad=float(np.sqrt(np.mean(error**2))),
                    hanging_branch_offset_rad=float(line[0]+line[1]*math.pi-display_origin(q)),
                    hanging_branch_relation='raw encoder minus its integer-turn hanging branch = offset + gain*(-raw image_angle); equivalent descriptive regression, not angular calibration')
            piv=np.array([[f['x_px'],f['y_px']] for f in good]);distance=np.linalg.norm(piv-np.median(piv,axis=0),axis=1)
            item.update(camera_period=cp,angle_agreement_zero_receipt_proxy_lag=cmp,pivot_radial_p95_px=float(np.quantile(distance,.95)),pivot_radial_max_px=float(max(distance)),
                period_ratio_camera_to_encoder=(cp['median_period_s']/ep_period['median_period_s']) if cp['median_period_s'] and ep_period['median_period_s'] else None,
                camera_points=[[float((tm-map_t(origin+lo))/mapping['slope']+lo),float(angle)] for tm,angle in zip(ct,cq)])
        results.append(item)
    return dict(source=pin,source_helper_sha256=sha(helper_path),source_frames=camera,receipt_proxy=mapping,per_episode=results,
        camera_geometry_source='raw pivot_px/image_angle_rad with confidence>=0.5; no old calibration or mirrored encoder',
        timing_scope='same-host operator assertion; fitted acquisition-snapshot-to-receipt proxy, camera host-read not exposure; no calibrated latency',
        metric_stationarity_certified=False)


def display_origin(raw_unwrapped):
    """Choose only an integer 2pi display branch; never infer an angle zero."""
    return math.pi+2*math.pi*round((float(np.median(raw_unwrapped))-math.pi)/(2*math.pi))


def draw(result,episodes,out):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(episodes),2,figsize=(14,3.3*len(episodes)),squeeze=False,layout='constrained')
    bias=result['frozen_parameters']['angle_offset_rad']
    for i,ep in enumerate(episodes):
        start=ep['t_s'][0];origin=display_origin(np.unwrap(ep['theta_rad']));continuous_result=result['continuous_rollouts'][i]
        for j,win in enumerate(result['short_forecast_readings'][i]['windows']):
            v=np.array(win['readings']);axes[i,0].plot(v[:,0]-start,np.degrees(v[:,1]-origin),color='#165f9b',label='Recorded raw encoder' if j==0 else None);axes[i,0].plot(v[:,0]-start,np.degrees(v[:,2]-origin),'--',color='#d96624',label='Prediction, frozen phase restored' if j==0 else None)
        v=np.array(continuous_result['readings']);axes[i,1].plot(v[:,0]-start,np.degrees(v[:,1]-origin),color='#165f9b');axes[i,1].plot(v[:,0]-start,np.degrees(v[:,2]-origin),'--',color='#d96624')
        stats=result['short_forecasts']['per_episode'][i]['validation'];axes[i,0].set_title(f"{ep['episode_id']}:0.5s forecasts; RMS {math.degrees(stats['prediction_rmse_rad']):.2f}°")
        axes[i,1].set_title(f"Continuous MuJoCo: RMS {math.degrees(continuous_result['rmse_rad']):.2f}°, P95 {math.degrees(continuous_result['p95_rad']):.1f}°")
        for ax in axes[i]:ax.axhline(math.degrees(bias),color='#777',lw=.7);ax.set_xlabel('Seconds from annotated free interval start');ax.set_ylabel('Raw θ − hanging branch (°)');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);fig.suptitle('New manual releases versus unchanged Oct16 passive coefficients',fontsize=16);fig.savefig(out/'frozen-model-comparison.png',dpi=160);fig.savefig(out/'frozen-model-comparison.pdf');plt.close(fig)
    if result.get('secondary_coulomb_ode'):
        fig,axes=plt.subplots(len(episodes),1,figsize=(12,2.8*len(episodes)),squeeze=False,layout='constrained')
        for i,(ep,rollout) in enumerate(zip(episodes,result['secondary_coulomb_ode']['continuous_rollouts'])):
            ax=axes[i,0];v=np.array(rollout['readings']);start=ep['t_s'][0];origin=display_origin(np.unwrap(ep['theta_rad']))
            ax.plot(v[:,0]-start,np.degrees(v[:,1]-origin),color='#165f9b',label='Recorded raw encoder')
            ax.plot(v[:,0]-start,np.degrees(v[:,2]-origin),'--',color='#5b3b92',label='Predeclared Coulomb ODE, one initialization')
            ax.set_title(f"{ep['episode_id']}: continuous secondary ODE RMS {math.degrees(rollout['rmse_rad']):.2f}°, P95 {math.degrees(rollout['p95_rad']):.1f}°")
            ax.set_xlabel('Seconds from annotated interval start');ax.set_ylabel('Raw θ − hanging branch (°)');ax.grid(alpha=.2)
        axes[0,0].legend(fontsize=8);fig.suptitle('Predeclared secondary Coulomb ODE: diagnostic only, no model selection',fontsize=15)
        fig.savefig(out/'secondary-coulomb-ode.png',dpi=160);fig.savefig(out/'secondary-coulomb-ode.pdf');plt.close(fig)
    if result.get('camera'):
        fig,axes=plt.subplots(len(episodes),1,figsize=(12,2.8*len(episodes)),squeeze=False,layout='constrained')
        for i,(ep,diagnostic) in enumerate(zip(episodes,result['camera']['per_episode'])):
            ax=axes[i,0];t=np.array(ep['t_s']);q=np.unwrap(ep['theta_rad']);ax.plot(t-t[0],np.degrees(q-np.median(q)),label='Raw encoder, own median removed',color='#165f9b')
            if diagnostic.get('camera_points'):
                pts=np.array(diagnostic['camera_points']);ax.scatter(pts[:,0]-t[0],np.degrees(pts[:,1]-np.median(pts[:,1])),s=6,label='Raw camera projection, own median removed',color='#d96624')
            coverage=diagnostic['geometry']['coverage'];coverage_label=f'{coverage:.1%}' if coverage is not None else 'no delivered frames'
            ax.set_title(f"{ep['episode_id']}: delivered pivot coverage {coverage_label}");ax.set_xlabel('Seconds from annotated interval, receipt mapping proxy');ax.set_ylabel('Centered angle (°)');ax.grid(alpha=.2)
        axes[0,0].legend(fontsize=8);fig.suptitle('Independent raw angle channels: descriptive alignment, no calibration',fontsize=15);fig.savefig(out/'camera-encoder-comparison.png',dpi=160);fig.savefig(out/'camera-encoder-comparison.pdf');plt.close(fig)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--input',required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--annotations-sha256',required=True);p.add_argument('--vision',type=Path);p.add_argument('--same-host-clocks',action='store_true');p.add_argument('--output',type=Path,required=True);p.add_argument('--no-plot',action='store_true');p.add_argument('--secondary-predeclaration',type=Path);p.add_argument('--secondary-predeclaration-sha256');a=p.parse_args(argv)
    if a.output.exists():p.error('output exists; preserve previous results')
    if a.vision and not a.same_host_clocks:p.error('--same-host-clocks required for camera diagnostics')
    verify_annotation(a.annotations,a.annotations_sha256)
    secondary=None
    if a.secondary_predeclaration:
        if sha(a.secondary_predeclaration)!=a.secondary_predeclaration_sha256:raise ValueError('secondary predeclaration hash mismatch')
        declaration=json.loads(a.secondary_predeclaration.read_text())
        if declaration.get('selected_before_loading_complete_new_raw') is not True:raise ValueError('secondary not predeclared')
        secondary=secondary_candidate(a.repo/declaration['source_path'],declaration['source_sha256'])
        if declaration['frozen_coefficients']!=secondary['coefficients']:raise ValueError('secondary coefficient pin mismatch')
    sys.path.insert(0,str(a.repo/'src'))
    from cartpole_sdk.identification import workflow
    episodes,identity=workflow.passive_episodes(a.input,a.annotations)
    if identity.get('collection_report',{}).get('completed') is not True:raise ValueError('complete bound modern raw recording required')
    if identity['reference'][0]!=330:raise ValueError('raw encoder reference differs from frozen local phase reference330')
    fitter,training,freeze,evaluator=frozen_method(a.repo)
    if identity['sha256'] in freeze['source_export']['source_hashes'].values():raise ValueError('training source cannot be repeated as validation')
    report=training['magnetic_reports']['viscous'];parameters=freeze['candidate_parameters'];cfg=report['provenance']['config'];c=parameters['linear_coefficients']
    short=score(episodes,report,fitter,evaluator);config_path=a.repo/'evidence/system-id-20261016/mujoco-passive-candidate/model-config.json'
    result=dict(schema='cartpole-manual-repeatability-v1',scope='Independent new passive release assessment of exact frozen Oct16 candidate; no retuning or model promotion',
        parameters_refitted=False,frozen_parameters=parameters,local_phase_offset_rad=parameters['angle_offset_rad'],
        independent_global_angle_calibration=False,physical_cart_stationarity_certified=False,recommended_for_hardware_rl=False,
        input=identity,annotations_sha256=a.annotations_sha256,short_forecasts=short,
        short_forecast_readings=[dict(episode_id=ep['episode_id'],windows=forecast_readings(ep,c,cfg,fitter)) for ep in episodes],
        continuous_rollouts=[continuous(ep,parameters,config_path) for ep in episodes],
        caveats=['Operator hand restraint remains an assumption; counted position or pixel stability cannot certify metric stationarity.','Fitted Oct16 local gravity phase is reused unchanged, not an independent global encoder calibration.','Half-second forecasts reinitialize from past raw angles; continuous rollouts initialize only once after~0.1s.','Nominal episode angle labels are operator instructions, not calibrated measured amplitudes.','Plots choose an integer 2pi raw-angle display branch only; no fitted zero or phase is removed from recorded measurements.'])
    if secondary:
        sc=secondary['coefficients'];parts=fitter.segments(episodes,cfg)
        result['secondary_coulomb_ode']=dict(scope='Predeclared secondary ODE diagnostic only, no acceptance or selection; distinct from primary MuJoCo viscous model',
            predeclaration=declaration,predeclaration_sha256=a.secondary_predeclaration_sha256,parameters_refitted=False,coefficients=sc,
            short_forecasts=fitter.predict(parts,sc,cfg),
            per_episode_short_forecasts=[dict(episode_id=ep['episode_id'],**fitter.predict(fitter.segments([ep],cfg),sc,cfg)) for ep in episodes],
            continuous_rollouts=[continuous_ode(ep,sc,fitter) for ep in episodes])
    if a.vision:
        records,_=workflow.load_records(a.input);result['camera']=camera_diagnostics(a.repo,records,identity,episodes,a.vision)
    import mujoco
    result['provenance']=dict(script_sha256=sha(__file__),training_freeze_sha256=FREEZE_SHA,model_config_sha256=sha(config_path),simulator_provenance_sha256=SIM_PROVENANCE_SHA,numpy_version=np.__version__,mujoco_version=mujoco.__version__,
        frozen_method_sha256=sha(a.repo/'evidence/system-id-20261016/analysis/passive_fit.py'),evaluator_sha256=sha(a.repo/'evidence/system-id-20261016/analysis/heldout/evaluate_passive.py'),
        current_sdk=workflow.provenance())
    payload=json.dumps(result,indent=2,allow_nan=False)+'\n';a.output.mkdir(parents=True,exist_ok=False);(a.output/'assessment.json').write_text(payload)
    if not a.no_plot:draw(result,episodes,a.output)
    print(json.dumps(dict(output=str(a.output),aggregate=short['aggregate']['validation'],aggregate_fixed_gates_pass=short['aggregate_fixed_gates_pass'],all_episodes_fixed_gates_pass=short['all_episodes_fixed_gates_pass'],continuous=[{k:v for k,v in r.items() if k not in ('readings','full_simulation_config')} for r in result['continuous_rollouts']]),indent=2))

if __name__=='__main__':main()
