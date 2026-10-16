#!/usr/bin/env python3
"""Read-only offline characterization audit and frozen-gate train/heldout fit.

No hardware imports. Outputs are diagnostic; angle validity has not been
independently established and counted cart motion is not physical metrology.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import numpy as np

from cartpole_sdk.identification import fit, rig_logs
from cartpole_sdk.identification.fit import FitConfig, identify_pendulum
from cartpole_sdk.recording import strict_json_loads

BASE=Path(__file__).resolve().parent
EXPECTED={'fit':'0ad92368e93593235438f6dc12601091f03f9aee2c844a42a6392efd6cde1a76',
          'rig_logs':'51c5ebf1dfef771fbc3271c2658ceb57e9fe783737ea5ed2bb6db434dd8d77dc'}
CAVEATS=[
 'Cart x is counted motor steps; v and a are executor command states, not independent physical cart measurements.',
 'Raw theta is decoded magnetic angle; linearity, true vertical zero, scale and relative latency have not been independently established.',
 'Filtered omega is omitted from identification; causal local angle initialization is the unchanged fitter default.',
 'Closed-loop commanded-input gain and delay combine actuator, sensor, observer and clock effects.',
 'A commanded zero-acceleration hold does not prove a fixed physical cart.',
 'No cart/pole mass, force gain, physical motor tracking, or absolute mechanical damping coefficient is identified.',
]

def sha(raw):return hashlib.sha256(raw).hexdigest()
def wrap(q):return math.atan2(math.sin(q),math.cos(q))
def stats(values):
    a=np.asarray(values,float)
    if not len(a):return dict(n=0)
    return dict(n=len(a),min=float(np.min(a)),max=float(np.max(a)),mean=float(np.mean(a)),
                std=float(np.std(a)),rms=float(np.sqrt(np.mean(a*a))),p95_abs=float(np.quantile(np.abs(a),.95)))
def verify_modules():
    result={}
    for name,module in [('fit',fit),('rig_logs',rig_logs)]:
        p=Path(module.__file__);actual=sha(p.read_bytes())
        if actual!=EXPECTED[name]:raise ValueError(f'{name} changed; review/re-freeze analysis before proceeding')
        result[name]=dict(path=str(p),sha256=actual)
    return result
def load_run(directory):
    directory=Path(directory).resolve()
    reports=[p for name in ('report.json','home-report.json') if (p:=directory/name).exists()]
    logs=list(directory.glob('*.jsonl'))+list(directory.glob('*.jsonl.gz'))
    if len(reports)!=1 or len(logs)!=1:raise ValueError('require exactly one report and raw/gzip JSONL per run')
    compressed=logs[0].read_bytes();raw=gzip.decompress(compressed) if logs[0].suffix=='.gz' else compressed
    report=strict_json_loads(reports[0].read_text())
    if report.get('raw_log_sha256') and report['raw_log_sha256']!=sha(raw):raise ValueError('raw log hash differs from hardware report')
    records=[strict_json_loads(line) for line in raw.decode().splitlines() if line.strip()]
    return dict(directory=str(directory),report=report,records=records,
                manifest=dict(report_path=str(reports[0]),report_sha256=sha(reports[0].read_bytes()),
                local_log_path=str(logs[0]),compressed_sha256=sha(compressed),raw_sha256=sha(raw),raw_bytes=len(raw),
                original_remote_log=report.get('log'),raw_hash_matches_report=report.get('raw_log_sha256')==sha(raw) if report.get('raw_log_sha256') else None))

def training_hanging_offset(training):
    records=training['records'];start=next(r for r in records if r['type']=='characterization_start')
    end=start['state']['unwrapped_us'];selected=[]
    for r in records:
        if r is start:break
        if r['type']!='state':continue
        s=r['state']
        if not end-500_000<=s['unwrapped_us']<=end:continue
        if (s['mode']==0 and s['fault']==0 and s['flags']&15==13 and abs(s['x'])<.003 and
                abs(s['velocity'])<.005 and abs(s['acceleration'])<.1 and abs(s['omega'])<.15):selected.append(s)
    if len(selected)<5 or selected[-1]['unwrapped_us']-selected[0]['unwrapped_us']<400_000:
        raise ValueError('insufficient stationary training preflight for conditional offset')
    q=np.array([s['theta'] for s in selected]);mean=math.atan2(float(np.mean(np.sin(q))),float(np.mean(np.cos(q))))
    return dict(angle_offset_rad=wrap(mean-math.pi),circular_mean_theta_rad=mean,samples=len(selected),
                duration_s=(selected[-1]['unwrapped_us']-selected[0]['unwrapped_us'])/1e6,
                circular_deviation_std_rad=float(np.std([wrap(x-mean) for x in q])),
                source='training preflight only',independent_angle_calibration=False)

def selected_rows(run,phase='excitation'):
    refs=[r for r in run['records'] if r['type']=='characterization_reference']
    if not refs:raise ValueError('record lacks characterization reference trace')
    first=refs[0]['board_ns']/1e9
    rows,admission=rig_logs.rig_log_rows(run['records'],run_id=run['manifest']['raw_sha256'])
    low,high=(0.,20.) if phase=='excitation' else (20.5,40.)
    for row in rows:
        if not low-1e-8<=row['t_s']-first<=high+1e-8:
            row['valid']=False;row.setdefault('exclusion_reasons',[]).append(f'outside selected {phase} interval')
    return rows,admission

def audit_run(run):
    records=run['records'];refs=[r for r in records if r['type']=='characterization_reference']
    if not refs:raise ValueError('not a characterization run')
    start=next(r for r in records if r['type']=='characterization_start')
    states={r['state']['unwrapped_tick']:r['state'] for r in records if r['type']=='state'}
    selected=[states[r['observation_sequence']] for r in refs]
    requests=[r['request'] for r in records if r['type']=='action_request']
    by_obs={r['observation_sequence']:r for r in requests}
    if len(by_obs)!=len(requests) or len(requests)!=len(refs):raise ValueError('one action per reference observation required')
    discrepancy=max(abs(r['command']-by_obs[r['observation_sequence']]['acceleration_m_s2']) for r in refs)
    angle_discrepancy=max(abs(wrap(r['theta']-s['theta'])) for r,s in zip(refs,selected))
    if discrepancy>1e-12 or angle_discrepancy>1e-9:raise ValueError('reference/action/state trace mismatch')
    q=np.unwrap([r['theta'] for r in refs]);ex=[r for r in refs if r['phase']=='excitation']
    active=selected[:len(ex)];end=next((r for r in records if r['type']=='policy_end'),None)
    term=next((r for r in records if r['type']=='termination'),None)
    errors=[r for r in records if r['type'] in ('error','policy_failure','stop_failure','bad_frame')]
    tail=[r for r in refs if r['phase']=='commanded_hold']
    summary=dict(source=run['manifest'],configuration=start,counts=dict(Counter(r['type'] for r in records)),
        policy_end=end,termination=term,errors=errors,recorded_duration_s=refs[-1]['t_s'],
        phase_counts=dict(Counter(r['phase'] for r in refs)),action_count=len(requests),
        board_gap_ms=stats(np.diff([r['board_ns'] for r in refs])/1e6),
        host_policy_gap_ms=stats(np.diff([r['host_policy_ns'] for r in refs])/1e6),
        position_counted_m=stats([r['x'] for r in refs]),velocity_commanded_m_s=stats([r['v'] for r in refs]),
        acceleration_requested_m_s2=stats([r['command'] for r in refs]),acceleration_applied_command_m_s2=stats([s['acceleration'] for s in selected]),
        counted_position_tracking_error_m=stats([r['x']-r['x_reference'] for r in ex]),
        commanded_velocity_tracking_error_m_s=stats([r['v']-r['v_reference'] for r in ex]),
        raw_angle_span_rad=float(np.ptp(q)),raw_angle_departure_from_initial_rad=stats([wrap(r['theta']-start['initial_hanging']) for r in refs]),
        filtered_omega_rad_s=stats([r['omega'] for r in refs]),clamped_samples=sum(r['clamped'] for r in refs),
        action_trace_max_difference=discrepancy,angle_trace_max_difference=angle_discrepancy,
        active_firmware_faults=sorted({s['fault'] for s in selected}),active_deadline_miss_delta=selected[-1]['misses']-selected[0]['misses'],
        active_firmware_dropped_delta=selected[-1]['dropped']-selected[0]['dropped'],
        excitation_angle_span_rad=float(np.ptp(np.unwrap([r['theta'] for r in ex]))),
        excitation_acceleration_std_m_s2=float(np.std([s['acceleration'] for s in active])),
        unchanged_excitation_gates=dict(min_angle_span_rad=FitConfig().min_angle_span_rad,min_acceleration_rms_m_s2=FitConfig().min_acceleration_rms_m_s2),
        tail=dict(samples=len(tail),label='commanded_hold',independent_fixed_cart_proof=False,
                  counted_position_range_m=float(np.ptp([r['x'] for r in tail])) if tail else None,
                  velocity_commanded_m_s=stats([r['v'] for r in tail]),
                  post_20_5s_angle=stats([r['theta'] for r in tail if r['t_s']>=20.5]),
                  post_20_5s_unique_angle_values=len({r['theta'] for r in tail if r['t_s']>=20.5}),
                  post_20_5s_angle_span_rad=float(np.ptp(np.unwrap([r['theta'] for r in tail if r['t_s']>=20.5]))) if tail else None,
                  post_20_5s_applied_acceleration=stats([states[r['observation_sequence']]['acceleration'] for r in tail if r['t_s']>=20.5])),
        completion=not errors and not run['report'].get('failure') and term is not None and term.get('error') is None and term.get('records_dropped')==0,
        caveats=CAVEATS)
    summary['excitation_gate_pass']=(summary['excitation_angle_span_rad']>=FitConfig().min_angle_span_rad and summary['excitation_acceleration_std_m_s2']>=FitConfig().min_acceleration_rms_m_s2)
    return summary

def promotion_decision(reports):
    return dict(promoted=False,recommended_model=None,all_software_gates_pass=all(r['accepted'] for r in reports),
                independent_angle_validity_established=False,
                reason='Independent physical angle validity is not established; any failed unchanged fit gates also preclude promotion.')

def fit_pair(training,heldout):
    if training['manifest']['raw_sha256']==heldout['manifest']['raw_sha256']:raise ValueError('training and heldout must be independent recordings')
    verify_modules()
    tr,ta=selected_rows(training);vr,va=selected_rows(heldout)
    offset=training_hanging_offset(training)
    reports={}
    provenance=dict(inputs=dict(training=training['manifest'],heldout=heldout['manifest']),
        admissions=dict(training=ta,heldout=va),selection='excitation only, 0..20 s',
        hardware_activity=False,caveats=CAVEATS)
    for name,value in [('raw_zero',0.),('conditional_training_hanging_offset',offset['angle_offset_rad'])]:
        cfg=replace(FitConfig(),angle_offset_rad=value)
        reports[name]=identify_pendulum(tr,vr,source='magnetic',acceleration_kind='commanded',config=cfg,provenance=provenance).to_dict()
    return dict(training_offset=offset,reports=reports,promotion=promotion_decision(list(reports.values())))

def passive_pair(training,heldout,offset):
    cfg=replace(FitConfig(),angle_offset_rad=offset)
    rows,_=selected_rows(training,'tail');validation,_=selected_rows(heldout,'tail')
    tr=fit._segments(rows,'magnetic','commanded',cfg);vr=fit._segments(validation,'magnetic','commanded',cfg)
    x,y=fit._windows(tr,0.,cfg)
    result=dict(accepted=False,promoted=False,angle_offset_rad=offset,selection='20.5..40 s commanded hold',
                assumption='Treat cart acceleration as physically zero; this is not independently verified.',
                full_model_gates_applicable=False,window_count=len(y),validation_segments=len(vr))
    if len(y)<cfg.min_windows or not vr:return dict(result,reason='insufficient passive windows or independent tail')
    coef,_,rank,condition=fit._solve(x[:,:2],y)
    if coef is None or rank<2:return dict(result,reason='passive rank inadequate')
    alpha,gamma=coef;prediction=fit._predict(vr,(alpha,gamma,0.),0.,cfg)
    vx,vy=fit._windows(vr,0.,cfg)
    result.update(rank=rank,condition=condition,effective_length_m=cfg.gravity_m_s2/float(alpha) if alpha>0 else None,
                  gravity_coefficient_per_s2=float(alpha),angular_damping_per_s=float(gamma),
                  training_angle_span_rad=max(float(np.ptp(s[1])) for s in tr),
                  training_integral_nrmse=float(np.linalg.norm(y-x[:,:2]@coef)/np.sqrt(len(y))/max(np.std(y),1e-12)),
                  validation=prediction,validation_integral_nrmse=float(np.linalg.norm(vy-vx[:,:2]@coef)/np.sqrt(len(vy))/max(np.std(vy),1e-12)) if len(vy) else None,
                  reason='Two-coefficient conditional passive diagnostic only; no independently fixed cart or angular calibration.')
    return result

def home_fault_audit(home,fault_run):
    h=home['report'];records=fault_run['records'];states=[r['state'] for r in records if r['type']=='state']
    i=next(i for i,s in enumerate(states) if s['fault']==5)
    fault=states[i];previous=states[i-1];transitions=[];prior=None
    for r in home['records']:
        if r['type']!='state':continue
        s=r['state'];key=(s['mode'],s['flags'],s['fault'])
        if key!=prior:
            transitions.append({k:s[k] for k in ('unwrapped_tick','unwrapped_us','mode','flags','x','velocity','acceleration','fault')});prior=key
    p=fault_run['report']['parameters'];info=fault_run['report']['before_info']
    return dict(sources=dict(home=home['manifest'],right_fault=fault_run['manifest']),
                first_limit_fault=fault,preceding_active_state=previous,
                raw_limit_bits=(fault['flags']>>4)&15,right_required_switch_asserted=bool(fault['flags']&32),
                home_invalidated=not bool(fault['flags']&4),braking_active_before_fault=bool(previous['brake_direction']),
                counted_fault_x_below_old_rail_half_m=info['rail_half_m']-fault['x'],
                counted_fault_x_below_old_software_hard_boundary_m=p['rail']-p['rail_fault_margin']-fault['x'],
                home_transitions=transitions,home_before=h['before'],home_after=h['after'],
                info_before=h['info_before'],info_after=h['info_after'],
                measured_span_step_change=h['info_after']['measured_span_steps']-h['info_before']['measured_span_steps'],
                measured_step_span_m=h['info_after']['measured_span_steps']*0.0000375,
                geometric_half_of_measured_step_span_m=h['info_after']['measured_span_steps']*0.0000375/2,
                info_rail_half_semantics='derived governor rail reference via cart_homing.safeRail, not exactly geometric half of measured step span',
                manual_cart_movement_between_runs=True,
                conclusions=[
                  'Firmware registered the right required limit input and fault 5, stopped the driver and invalidated home.',
                  'The cart command was already braking but still moving right in the preceding sampled state.',
                  'Subsequent slow two-switch homing completed, reset counted center, and established epoch 14 / 16513 measured steps.',
                  'Manual movement before home breaks correspondence of old counted position with physical cart location.',
                  'Neither cross-run count differences nor a successful slow home prove lost steps, accurate high-speed tracking, or the cause of the early right input.',
                  'Electrical switch assertion is observed; physical contact versus a transient wiring/switch event is not independently established by these logs.'
                ])

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='append',default=[],type=Path)
    parser.add_argument('--training',type=Path);parser.add_argument('--heldout',type=Path)
    parser.add_argument('--home',type=Path);parser.add_argument('--right-fault',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    if bool(args.training)!=bool(args.heldout) or bool(args.home)!=bool(args.right_fault):parser.error('supply both members of each comparison')
    modules=verify_modules();result=dict(status='diagnostic_only_no_model_promotion',hardware_activity=False,
        python=platform.python_version(),numpy=np.__version__,source_modules=modules,fit_config=asdict(FitConfig()),
        plan_sha256=sha((BASE/'analysis-plan.json').read_bytes()),script_sha256=sha(Path(__file__).read_bytes()),runs={},caveats=CAVEATS)
    runs={str(p.resolve()):load_run(p) for p in args.run+[p for p in (args.training,args.heldout) if p]}
    for path,run in runs.items():result['runs'][path]=audit_run(run)
    if args.training:
        tr=runs[str(args.training.resolve())];vr=runs[str(args.heldout.resolve())]
        result['identification']=fit_pair(tr,vr)
        result['passive_diagnostics']={name:passive_pair(tr,vr,offset) for name,offset in [('raw_zero',0.),('conditional_training_hanging_offset',result['identification']['training_offset']['angle_offset_rad'])]}
    if args.home:result['home_right_fault']=home_fault_audit(load_run(args.home),load_run(args.right_fault))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(output=str(args.output),run_count=len(runs),identification_available='identification' in result,promoted=False)))
    return 0

if __name__=='__main__':raise SystemExit(main())
