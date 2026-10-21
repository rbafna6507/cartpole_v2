#!/usr/bin/env python3
"""Offline hardware-trace diagnostics. Never opens a transport or live service.

Examples:
  .venv/bin/python analyze-live.py TRIAL_DIR --output NEW_DIR --actor ACTOR_JSON --vision CAMERA_DIR/vision.ndjson
  .venv/bin/python analyze-live.py ARCHIVE.tar.gz --archive-prefix runs/console-policy-20261021/learned-affinity-02 --output NEW_DIR --actor ACTOR_JSON

Reads only supplied local files. Request and telemetry clocks are kept separate.
Counterfactual feedback/replay is analysis, never a hardware control command.
"""
import argparse
import csv
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import tarfile

import numpy as np
from cartpole_sdk.control.parameters import ControllerParameters, gains
from cartpole_sdk.policies.neural import validate_actor
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend

ROOT=Path(__file__).resolve().parents[3]
FAULTS={0:'none',1:'action_expired',2:'host_timeout',3:'duration',4:'encoder',5:'limit',6:'deadline',7:'rail',8:'controller',9:'homing'}


def digest(raw):return sha256(raw).hexdigest()

def finite(value):return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)

def wrap(value):return np.arctan2(np.sin(value),np.cos(value))

def stats(values):
    x=np.asarray([float(v) for v in values if v is not None and finite(v)],dtype=float)
    if not len(x):return None
    return dict(n=len(x),mean=float(np.mean(x)),median=float(np.median(x)),p01=float(np.percentile(x,1)),p99=float(np.percentile(x,99)),
        min=float(np.min(x)),max=float(np.max(x)),rms=float(np.sqrt(np.mean(x*x))))

def parse(raw):
    def reject(value):raise ValueError('nonfinite JSON token: '+value)
    return json.loads(raw,parse_constant=reject)

def rows(raw):return [parse(line) for line in raw.splitlines() if line.strip()]


def read_inputs(source,prefix=None,vision=None):
    blobs={};identity=dict(path=str(source.resolve()))
    if source.is_file() and source.name.endswith(('.tar.gz','.tgz','.tar')):
        if not prefix:raise ValueError('archive input requires an explicit --archive-prefix')
        identity['archive_sha256']=digest(source.read_bytes());identity['archive_prefix']=prefix
        with tarfile.open(source) as archive:
            candidates=[m for m in archive.getmembers() if m.isfile() and m.name.startswith(prefix.rstrip('/')+'/')]
            for member in candidates:
                name=Path(member.name).name
                if name in ('report.json','vision.ndjson','vision-report.json') or (name.startswith('rig-') and name.endswith('.jsonl')):
                    if name in blobs:raise ValueError('ambiguous archive member: '+name)
                    blobs[name]=archive.extractfile(member).read()
    else:
        folder=source if source.is_dir() else source.parent
        traces=sorted(folder.glob('rig-*.jsonl')) if source.is_dir() else [source]
        for path in traces+[folder/name for name in ('report.json','vision.ndjson','vision-report.json')]:
            if path.is_file():blobs[path.name]=path.read_bytes()
    if vision is not None:
        blobs['vision.ndjson']=vision.read_bytes();identity['external_vision']=str(vision.resolve())
    traces=[name for name in blobs if name.startswith('rig-') and name.endswith('.jsonl')]
    if len(traces)!=1:raise ValueError('provide exactly one trial rig trace, found '+str(traces))
    identity['members']={name:dict(sha256=digest(raw),bytes=len(raw)) for name,raw in blobs.items()}
    return rows(blobs[traces[0]]),parse(blobs['report.json']) if 'report.json' in blobs else {},rows(blobs['vision.ndjson']) if 'vision.ndjson' in blobs else [],identity


def encoded(state):
    healthy=bool(state['flags']&1);homed=bool(state['flags']&4)
    valid=[int(homed),1,int(healthy),int(healthy),int(healthy),1,1]
    values=[state['x'],state['velocity'],math.sin(state['theta']),math.cos(state['theta']),state['omega'],state['acceleration'],state['brake_direction']]
    return dict(state=[v if ok else 0. for v,ok in zip(values,valid)],valid=valid,age_s=[0.]*7)


def observer_lag(states):
    if len(states)<30:return dict(status='insufficient samples')
    t=np.asarray([s['unwrapped_us']/1e6 for s in states]);raw=np.unwrap([s['theta'] for s in states]);filtered=np.unwrap([s['angle_hat'] for s in states])
    filtered+=2*math.pi*round(float(np.median(raw-filtered))/(2*math.pi))
    if np.ptp(raw)<.02:return dict(status='insufficient angle excitation',angle_span_rad=float(np.ptp(raw)))
    selected=t>=t[0]+.1
    if sum(selected)<20:return dict(status='insufficient duration')
    curve=[]
    for lag_ms in range(0,101,2):
        residual=filtered[selected]-np.interp(t[selected]-lag_ms/1000.,t,raw)
        curve.append(dict(lag_ms=lag_ms,rms_deg=float(np.sqrt(np.mean(residual**2)))*180/math.pi))
    best=min(curve,key=lambda r:r['rms_deg'])
    dt=np.diff(t);rate=np.gradient(raw,t)
    smooth_rate=np.array(rate,copy=True)
    for index,center in enumerate(t):
        window=np.abs(t-center)<=.0200001
        if sum(window)>=3:
            tt=t[window]-np.mean(t[window]);yy=raw[window]-np.mean(raw[window])
            smooth_rate[index]=float(np.dot(tt,yy)/np.dot(tt,tt))
    selected_rate=(t>=t[0]+.12)&(t<=t[-1]-.02)
    omega=np.asarray([s['omega'] for s in states]);rate_curve=[]
    if sum(selected_rate)>=20 and np.std(smooth_rate[selected_rate])>.1:
        for lag_ms in range(0,101,2):
            residual=omega[selected_rate]-np.interp(t[selected_rate]-lag_ms/1000.,t,smooth_rate)
            rate_curve.append(dict(lag_ms=lag_ms,rms_rad_s=float(np.sqrt(np.mean(residual**2)))))
    rate_best=min(rate_curve,key=lambda r:r['rms_rad_s']) if rate_curve else None
    return dict(status='descriptive fit only',best_raw_to_filtered_angle_lag_ms=best['lag_ms'],
        zero_lag_rms_deg=curve[0]['rms_deg'],best_lag_rms_deg=best['rms_deg'],curve=curve,
        raw_finite_difference_rate_minus_observer_rad_s=stats(rate-omega),
        rate_lag_fit=dict(best=rate_best,curve=rate_curve,derivative_window_ms=40.,
            semantics='Centered local linear raw-angle derivative, then delayed-reference RMS scan0..100ms. Descriptive observer phase-delay proxy; not causal identification and not a time-shift correction.'),
        timing_gap_max_ms=float(max(dt)*1000),
        semantics='Fits a delayed raw angle to filtered angle on the same board timestamps. Not a causal identification or camera/exposure delay estimate. Raw-angle derivative is quantization-sensitive.')


def camera_analysis(camera,states,active_start,active_end,max_alignment_ms):
    st=np.asarray([s['received_ns']/1e9 for s in states]);theta=np.asarray([s['theta'] for s in states])
    if not camera:return dict(status='no camera recording supplied',physical_cart_tracking='unmeasured'),[]
    sessions={str(s['sid']) for s in states};aligned=[];reject={};old_encoder=0;seen=set();calibrations={}
    def drop(reason):reject[reason]=reject.get(reason,0)+1
    for row in camera:
        packet=(row.get('encoder') or {}).get('packet') or {}
        if packet and str(packet.get('session')) not in sessions:old_encoder+=1
        v=row.get('vision') or {};timestamp=v.get('t');angle=v.get('theta_rad')
        if not (v.get('angle_valid') is True and v.get('calibrated') is True and v.get('stale') is not True and finite(timestamp) and finite(angle)):
            drop('invalid_or_uncalibrated_angle');continue
        token=(v.get('seq'),timestamp)
        if token in seen:drop('duplicate_frame');continue
        seen.add(token)
        if not active_start<=timestamp<=active_end:drop('outside_active_interval');continue
        available=row.get('host_t')
        if finite(available) and not 0<=available-timestamp<=.15:drop('camera_result_age_outside_150ms');continue
        index=int(np.searchsorted(st,timestamp));choices=[i for i in (index-1,index) if 0<=i<len(st)]
        nearest=min(choices,key=lambda i:abs(st[i]-timestamp))
        delta=st[nearest]-timestamp
        if abs(delta)*1000>max_alignment_ms:drop('no_close_host_receipt_match');continue
        state=states[nearest];difference=float(wrap(angle-state['theta']))
        cart_ok=v.get('cart_valid') is True and finite(v.get('cart_x_m')) and not v.get('cart_extrapolated',False)
        calibration=v.get('calibration');key=json.dumps(calibration,sort_keys=True);calibrations[key]=calibration
        aligned.append(dict(camera_host_t=timestamp,relative_active_s=timestamp-active_start,state_host_receipt_t=st[nearest],alignment_delta_ms=delta*1000,
            theta_camera_rad=angle,theta_encoder_rad=state['theta'],camera_minus_encoder_deg=difference*180/math.pi,
            encoder_omega_rad_s=state['omega'],camera_omega_rad_s=v.get('omega_rad_s'),
            x_step_estimate_m=state['x'],camera_x_m=v['cart_x_m'] if cart_ok else None,
            camera_minus_step_x_m=v['cart_x_m']-state['x'] if cart_ok else None,
            camera_cart_valid=cart_ok,recorded_camera_age_ms=(available-timestamp)*1000 if finite(available) else None,
            quiet=abs(state['omega'])<.25 and abs(state['velocity'])<.025 and abs(state['acceleration'])<.2 and finite(v.get('omega_rad_s')) and abs(v['omega_rad_s'])<.5))
    valid_cart=[r for r in aligned if r['camera_cart_valid']]
    return dict(status='aligned' if aligned else 'no usable active camera alignment',frames=len(camera),unique_frames=len(seen),aligned_frames=len(aligned),
        rejected=reject,stale_other_session_embedded_encoder_packets_ignored=old_encoder,
        alignment_delta_ms=stats(r['alignment_delta_ms'] for r in aligned),camera_minus_encoder_deg=stats(r['camera_minus_encoder_deg'] for r in aligned),
        quiet_camera_minus_encoder_deg=stats(r['camera_minus_encoder_deg'] for r in aligned if r['quiet']),
        valid_cart_frames=len(valid_cart),camera_minus_step_x_m=stats(r['camera_minus_step_x_m'] for r in valid_cart),
        recorded_calibrations=list(calibrations.values()),
        physical_cart_tracking='camera comparison available; calibration and exposure-delay limits still apply' if valid_cart else 'unmeasured: no valid calibrated camera cart-position samples',
        semantics='Camera frame host timestamp aligned to this trial state host receipt within the declared tolerance; no embedded encoder packets used. Shared host clock does not remove exposure/processing/serial delay. Angle residual does not by itself identify encoder-zero error or true vertical.'),aligned


def analyze(trace,operation,camera,actor_path,max_alignment_ms):
    state_events=[r for r in trace if r.get('type')=='state'];states=[r['state'] for r in state_events]
    if not states:raise ValueError('no state records')
    if len({s['sid'] for s in states})!=1:raise ValueError('mixed state sessions')
    active=[s for s in states if s['mode']==12 and s['flags']&2]
    role='host-policy'
    if not active:active=[s for s in states if s['mode'] in (2,3,5,6) and s['flags']&2];role='native-auto'
    if not active:active=states;role='stopped-or-preflight-only'
    by_tick={s['unwrapped_tick']:s for s in states};requests=[r for r in trace if r.get('type')=='action_request']
    start=active[0]['unwrapped_us']/1e6;start_host=active[0]['received_ns']/1e9;end_host=active[-1]['received_ns']/1e9
    parameters={r['name']:r['value'] for r in trace if r.get('type')=='parameter'}
    preflights=[r for r in trace if r.get('type')=='neural_preflight']
    if preflights:parameters=preflights[-1]['executor_parameters']
    elif operation.get('parameters'):parameters=operation['parameters']
    feedback={};feedback_error=None
    try:
        config=ControllerParameters(**parameters)
        if set(parameters)!=set(asdict(config)):raise ValueError('incomplete parameter snapshot')
        feedback={label:asdict(gains(config,upright=upright)) for label,upright in (('auto',False),('upright',True))}
    except (ValueError,TypeError) as error:feedback_error=str(error)
    backend=None;actor_info=dict(status='not supplied')
    if actor_path:
        raw=actor_path.read_bytes();actor=validate_actor(parse(raw));expected={r['actor_sha256'] for r in trace if r.get('type') in ('neural_preflight','balance_only_boundary') and r.get('actor_sha256')}
        if expected and expected!={actor['content_sha256']}:raise ValueError('supplied actor content differs from trace admission')
        if operation.get('actor_file_sha256') and digest(raw)!=operation['actor_file_sha256']:raise ValueError('supplied actor file differs from operation receipt')
        if actor['angle_source']!='raw':raise ValueError('offline reconstruction currently requires raw encoder actor')
        backend=NumpyActorBackend(actor)
        actor_info=dict(status='trace-bound' if expected or operation.get('actor_file_sha256') else 'unbound comparison only',path=str(actor_path.resolve()),
            file_sha256=digest(raw),content_sha256=actor['content_sha256'],trace_expected_content_sha256=sorted(expected),
            backend=backend.provenance(),semantics='Offline encoded reconstruction; current deployment loader is not invoked and this grants no runtime/hardware admission.')
    commands={}
    for row in trace:
        tokens=row.get('payload','').split()
        if row.get('type')=='command' and len(tokens)==7 and tokens[:2]==['V2','A']:
            commands[int(tokens[3])]=row
    first_accept={}
    for state in states:
        if state['mode']==12 and state['last_seq']>0:first_accept.setdefault(state['last_seq'],state)
    action_rows=[]
    for event in requests:
        request=event['request'];state=by_tick.get(request['observation_sequence'])
        if state is None:continue
        prediction=backend.predict_encoded(encoded(state)) if backend else None
        command=commands.get(request['sequence']);accepted=first_accept.get(request['sequence'])
        action_rows.append(dict(sequence=request['sequence'],observation_sequence=request['observation_sequence'],
            board_t_s=state['unwrapped_us']/1e6-start,host_request_t_s=event['host_monotonic_ns']/1e9-start_host,
            issued_at_ns=request['issued_at_ns'],requested_raw_m_s2=request['acceleration_m_s2'],replayed_mlp_m_s2=prediction,
            replay_minus_requested_m_s2=prediction-request['acceleration_m_s2'] if prediction is not None else None,
            receipt_to_request_record_ms=(event['host_monotonic_ns']-state['received_ns'])/1e6,
            receipt_to_command_record_ms=(command['host_monotonic_ns']-state['received_ns'])/1e6 if command else None,
            ttl_ms=(request['expires_at_ns']-request['issued_at_ns'])/1e6,
            first_accept_board_age_upper_bound_ms=(accepted['unwrapped_us']*1000-request['issued_at_ns'])/1e6 if accepted else None,
            first_accepted_demand_m_s2=accepted['demand'] if accepted else None,
            accepted_minus_requested_m_s2=accepted['demand']-request['acceleration_m_s2'] if accepted else None))
    aligned=[]
    for state in active:
        row=dict(board_t_s=state['unwrapped_us']/1e6-start,host_receipt_t_s=state['received_ns']/1e9-start_host,
            mode=state['mode'],fault=state['fault'],flags=state['flags'],observation_sequence=state['unwrapped_tick'],last_seq=state['last_seq'],
            theta_encoder_deg=state['theta']*180/math.pi,theta_filtered_deg=state['angle_hat']*180/math.pi,observer_rate_rad_s=state['omega'],
            x_step_estimate_m=state['x'],commanded_velocity_m_s=state['velocity'],governed_acceleration_m_s2=state['acceleration'],
            accepted_demand_m_s2=state['demand'],brake_direction=state['brake_direction'],
            requested_minus_governed_m_s2=state['demand']-state['acceleration'],
            replayed_mlp_m_s2=backend.predict_encoded(encoded(state)) if backend else None)
        for name,k in feedback.items():
            row['counterfactual_'+name+'_linear_raw_angle_m_s2']=-(k['k1']*state['theta']+k['k2']*state['omega']+k['k3']*state['x']+k['k4']*state['velocity'])
            row['counterfactual_'+name+'_linear_filtered_angle_m_s2']=-(k['k1']*state['angle_hat']+k['k2']*state['omega']+k['k3']*state['x']+k['k4']*state['velocity'])
        aligned.append(row)
    quiet=[s for s in states if not s['flags']&2 and abs(s['omega'])<.15 and abs(s['velocity'])<.01]
    infos=[r['info'] for r in trace if r.get('type')=='info']
    references=sorted({r['encoder_upright_raw'] for r in infos})
    faults=[dict(board_t_s=s['unwrapped_us']/1e6-start,code=s['fault'],name=FAULTS.get(s['fault'],'unknown'),mode=s['mode']) for s in states if s['fault']]
    first_brake=next((s['unwrapped_us']/1e6-start for s in active if s['brake_direction']),None)
    def first_cross(value):return next((s['unwrapped_us']/1e6-start for s in active if abs(s['theta'])>value),None)
    cam,cam_rows=camera_analysis(camera,states,start_host,end_host,max_alignment_ms)
    request_host=[r['host_monotonic_ns']/1e6 for r in requests];request_board=[r['request']['issued_at_ns']/1e6 for r in requests]
    observed_intervals=np.diff([s['unwrapped_us']/1000 for s in active]);receipt_intervals=np.diff([s['received_ns']/1e6 for s in active])
    cutoff=min([.5]+[v for v in (first_brake,first_cross(math.radians(15))) if v is not None])
    initial=[r for r in aligned if r['board_t_s']<=cutoff]
    initial_summary=dict(end_s=cutoff,semantics='First0.5s, stopped earlier at first rail brake or abs(encoder angle)>15deg.',
        step_position_change_m=initial[-1]['x_step_estimate_m']-initial[0]['x_step_estimate_m'],
        encoder_angle_change_deg=initial[-1]['theta_encoder_deg']-initial[0]['theta_encoder_deg'],
        accepted_demand_m_s2=stats(r['accepted_demand_m_s2'] for r in initial),
        governed_acceleration_m_s2=stats(r['governed_acceleration_m_s2'] for r in initial),
        replayed_mlp_m_s2=stats(r['replayed_mlp_m_s2'] for r in initial),
        linear_auto_raw_m_s2=stats(r.get('counterfactual_auto_linear_raw_angle_m_s2') for r in initial),
        linear_upright_raw_m_s2=stats(r.get('counterfactual_upright_linear_raw_angle_m_s2') for r in initial))
    snapshots=[dict(requested_time_s=target,**min(aligned,key=lambda r:abs(r['board_t_s']-target)))
        for target in (0.,.05,.1,.2,.3,.5,1.,2.,5.) if target<=aligned[-1]['board_t_s']]
    summaries=dict(role=role,operation_completed=operation.get('success'),operation_error=operation.get('error'),
        semantics='Operation success is not balance success. x is step-count estimate; velocity/acceleration are commanded governor state, not independently measured cart motion.',
        initial_response=initial_summary,response_snapshots=snapshots,
        active_states=len(active),active_span_s=active[-1]['unwrapped_us']/1e6-start,requests=len(requests),action_rows_matched=len(action_rows),
        first_active_state=active[0],last_active_state=active[-1],first_rail_braking_s=first_brake,
        first_abs_encoder_over_5deg_s=first_cross(math.radians(5)),first_abs_encoder_over_15deg_s=first_cross(math.radians(15)),
        max_abs_step_position_m=max(abs(s['x']) for s in active),encoder_angle_deg=stats(s['theta']*180/math.pi for s in active),
        raw_minus_filtered_angle_deg=stats(float(wrap(s['theta']-s['angle_hat']))*180/math.pi for s in active),
        demand_minus_governed_acceleration_m_s2=stats(s['demand']-s['acceleration'] for s in active),
        rail_braking_fraction=sum(s['brake_direction']!=0 for s in active)/len(active),
        timing=dict(board_telemetry_interval_ms=stats(observed_intervals),host_receipt_interval_ms=stats(receipt_intervals),
            request_host_interval_ms=stats(np.diff(request_host)),request_board_interval_ms=stats(np.diff(request_board)),
            receipt_to_request_record_ms=stats(r['receipt_to_request_record_ms'] for r in action_rows),
            receipt_to_command_record_ms=stats(r['receipt_to_command_record_ms'] for r in action_rows),
            first_accept_board_age_upper_bound_ms=stats(r['first_accept_board_age_upper_bound_ms'] for r in action_rows),
            accepted_sequences_seen=sum(r['first_accepted_demand_m_s2'] is not None for r in action_rows),ttl_ms=sorted({r['ttl_ms'] for r in action_rows}),
            action_expiry_fault_observed=any(s['fault']==1 for s in states),faults=faults,
            control_deadline_misses_delta=active[-1]['misses']-active[0]['misses'],
            board_dropped_serial_frames_delta=active[-1]['dropped']-active[0]['dropped'],
            logger_dropped_records=[r.get('records_dropped') for r in trace if r.get('type')=='termination'],
            failure_context=[r for r in trace if r.get('type') in ('policy_failure','error','stop_failure')],
            policy_compute=[r for r in trace if r.get('type')=='policy_end'],
            semantics='Host command record follows transport.write; these intervals are host proxies, not wire/executor latency. First telemetry last_seq observation is an upper bound on acceptance time. Unseen sequence does not prove rejection. dropped_serial_frames can count overwritten telemetry, not lost policy commands.'),
        actor=actor_info,mlp_replay_minus_requested_m_s2=stats(r['replay_minus_requested_m_s2'] for r in action_rows),
        accepted_minus_requested_m_s2=stats(r['accepted_minus_requested_m_s2'] for r in action_rows),
        calibration=dict(saved_reference_counts=references,reference_changed=len(references)>1,
            quiet_stopped_encoder_angle_deg=stats(s['theta']*180/math.pi for s in quiet),
            semantics='Quiet stopped angle does not establish true vertical: the pole can hang or be held at an unknown angle. Saved reference consistency is distinct from physical zero calibration.'),
        observer=observer_lag(active),camera=cam,recorded_parameters=parameters,counterfactual_linear_gains=feedback,linear_parameter_error=feedback_error,
        linear_semantics='Unclipped offline native state-feedback comparison from recorded parameters, using raw or filtered angle; AUTO and upright-only gains differ. This is not the executed controller in host mode.',
        sim_replay=dict(performed=False,reason='Trace cart velocity/acceleration are command states. A matched command-state simulation can be a hypothesis check, but cannot establish actuator tracking or physical initial cart velocity.'),
        evidence_limits=['No hardware/network/transport opened.','No physical cart tracking claim without independently valid camera cart data.','No calibration correction is fitted or applied.','No training, policy selection, or reserved-pose evaluation performed.'])
    return summaries,aligned,action_rows,cam_rows


def write_csv(path,data):
    if not data:return
    fields=list(dict.fromkeys(key for row in data for key in row))
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(data)


def plot(path,aligned,actions,camera):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    t=[r['board_t_s'] for r in aligned]
    fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True,constrained_layout=True)
    axes[0].plot(t,[r['theta_encoder_deg'] for r in aligned],label='Encoder angle')
    axes[0].plot(t,[r['theta_filtered_deg'] for r in aligned],label='Filtered angle',alpha=.8)
    if camera:axes[0].plot([r['relative_active_s'] for r in camera],[r['theta_camera_rad']*180/math.pi for r in camera],label='Valid camera angle (host-time proxy)',alpha=.7)
    axes[0].set_ylabel('Angle (degrees)')
    axes[1].plot(t,[r['x_step_estimate_m'] for r in aligned],label='Step-count position estimate')
    cart=[r for r in camera if r['camera_cart_valid']]
    if cart:axes[1].plot([r['relative_active_s'] for r in cart],[r['camera_x_m'] for r in cart],label='Calibrated camera cart position')
    axes[1].set_ylabel('Cart estimate (m)')
    axes[2].plot(t,[r['accepted_demand_m_s2'] for r in aligned],label='Accepted demand',alpha=.65)
    axes[2].plot(t,[r['governed_acceleration_m_s2'] for r in aligned],label='Governed acceleration')
    if aligned[0].get('replayed_mlp_m_s2') is not None:axes[2].plot(t,[r['replayed_mlp_m_s2'] for r in aligned],label='MLP on same telemetry',lw=.8,alpha=.7)
    axes[2].set_ylabel('Acceleration (m/s²)')
    if actions:axes[3].plot([r['board_t_s'] for r in actions],[r['receipt_to_request_record_ms'] for r in actions],label='Host receipt → request record')
    axes[3].set_ylabel('Host proxy (ms)');axes[3].set_xlabel('Board time since active telemetry began (s)')
    for ax in axes:
        ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]:ax.legend(loc='best')
    fig.suptitle('Offline recorded signals — command-state motion is not physical cart truth')
    fig.savefig(path,dpi=150);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('--archive-prefix');parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--actor',type=Path);parser.add_argument('--vision',type=Path);parser.add_argument('--max-alignment-ms',type=float,default=20.)
    parser.add_argument('--no-plot',action='store_true');args=parser.parse_args()
    if not 0<args.max_alignment_ms<=100:parser.error('max alignment must be within 0..100 ms')
    analyzer_source=Path(__file__).read_bytes()
    trace,operation,camera,identity=read_inputs(args.input,args.archive_prefix,args.vision)
    result,aligned,actions,cam_rows=analyze(trace,operation,camera,args.actor,args.max_alignment_ms)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'analyzer.py').write_bytes(analyzer_source)
    result.update(schema='cartpole-offline-live-trace-analysis-v1',input=identity,analyzer_sha256=digest(analyzer_source),
        analysis_source_sha256={str(path.relative_to(ROOT)):digest(path.read_bytes()) for path in
            (ROOT/'src/cartpole_sdk/policies/neural.py',ROOT/'src/cartpole_sdk/policies/numeric_backend.py',ROOT/'src/cartpole_sdk/control/parameters.py',ROOT/'src/cartpole_sdk/rig/client.py',ROOT/'src/cartpole_sdk/rig/policy.py',ROOT/'firmware/teensy_executor/executor_core.h')},
        max_camera_alignment_ms=args.max_alignment_ms)
    write_csv(args.output/'telemetry.csv',aligned);write_csv(args.output/'actions.csv',actions);write_csv(args.output/'camera-alignment.csv',cam_rows)
    if not args.no_plot:plot(args.output/'signals.png',aligned,actions,cam_rows)
    result['artifacts']={path.name:digest(path.read_bytes()) for path in args.output.iterdir() if path.is_file()}
    with (args.output/'analysis.json').open('x') as stream:json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    print(json.dumps({key:result[key] for key in ('role','active_span_s','requests','first_rail_braking_s','first_abs_encoder_over_5deg_s','mlp_replay_minus_requested_m_s2','camera')},indent=2))


if __name__=='__main__':main()
