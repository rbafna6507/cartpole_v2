#!/usr/bin/env python3
"""Read recorded JSONL only. No Rig, serial, camera, network or service access."""
import copy
import hashlib
import json
import math
import platform
from pathlib import Path
from dataclasses import asdict, replace
from collections import Counter
import numpy as np
import fit
from rig_logs import rig_log_rows

BASE = Path(__file__).resolve().parent
PLAN = json.loads((BASE / 'analysis-plan.json').read_text())
OUT = BASE / 'results'
OUT.mkdir(exist_ok=True)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
def strict(line):
    return json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
def metrics(values):
    a=np.asarray(values,float)
    if len(a)==0:return None
    return dict(n=len(a), min=float(a.min()),max=float(a.max()),mean=float(a.mean()),std=float(a.std()),p05=float(np.quantile(a,.05)),p95=float(np.quantile(a,.95)))

data={}
for label, desc in PLAN['runs'].items():
    directory=Path(desc['path'])
    raw_path=next(directory.glob('rig-*.jsonl'))
    raw=raw_path.read_bytes()
    records=[strict(line) for line in raw.decode().splitlines() if line.strip()]
    session=next(r['session'] for r in records if r.get('type')=='session')
    rows, admission=rig_log_rows(records,run_id=session['session_id'])
    report_raw=(directory/'report.json').read_bytes()
    report=strict(report_raw)
    file_manifest=[]
    for filename in [raw_path,directory/'report.json',directory/'parameters.json',directory/'camera.json']:
        b=filename.read_bytes(); expected=next(f for f in desc['files'] if f['path']==str(filename))
        assert sha(b)==expected['sha256'], 'recorded source changed: '+str(filename)
        file_manifest.append(dict(path=str(filename),bytes=len(b),sha256=sha(b),matches_prior_manifest=True))
    states=[];seen=set()
    for r in records:
        if r.get('type')=='state':
            s=r['state'];key=s['unwrapped_tick']
            if key not in seen:states.append(s);seen.add(key)
    stats={}
    for mode in sorted({s['mode'] for s in states}):
        ss=[s for s in states if s['mode']==mode]
        stats[str(mode)]=dict(samples=len(ss),theta_rad=metrics([s['theta'] for s in ss]),x_m=metrics([s['x'] for s in ss]),acceleration_m_s2=metrics([s['acceleration'] for s in ss]),velocity_m_s=metrics([s['velocity'] for s in ss]))
    cfg=fit.FitConfig();segments=fit._segments(rows,'magnetic','commanded',cfg)
    segment_stats=[dict(start_board_s=float(t[0]),end_board_s=float(t[-1]),duration_s=float(t[-1]-t[0]),n=len(t),max_gap_s=float(np.diff(t).max()),median_gap_s=float(np.median(np.diff(t))),angle_span_unwrapped_rad=float(np.ptp(q)),acceleration_std=float(a.std())) for t,q,a,_ in segments]
    stopped_tails=[];active=[]
    for s in states:
        eligible=(s['mode']==0 and not s['fault'] and s['acceleration']==0 and s['velocity']==0)
        if eligible:active.append(s)
        elif active:stopped_tails.append(active);active=[]
    if active:stopped_tails.append(active)
    passive=[dict(n=len(ss),start_board_s=ss[0]['unwrapped_us']/1e6,duration_s=(ss[-1]['unwrapped_us']-ss[0]['unwrapped_us'])/1e6,unwrapped_angle_span_rad=float(np.ptp(np.unwrap([s['theta'] for s in ss]))),counted_x_span_m=float(np.ptp([s['x'] for s in ss])),max_abs_reported_omega=float(max(abs(s['omega']) for s in ss))) for ss in stopped_tails if len(ss)>8]
    metadata={k:report.get(k) for k in ['path','kind','requested_s','ok','changes','vision_guard_enabled','control_source','info','applied_info','final_info','settling','parameters','profile','motion_start','records_dropped']}
    metadata.update(raw_sources=file_manifest,admission=admission,canonical_sha256=fit._hash(rows),mode_stats=stats,eligible_segments=segment_stats,stopped_intervals=passive,camera_series_samples=len(strict((directory/'camera.json').read_text())))
    dump(label+'-metadata.json',metadata)
    data[label]=dict(rows=rows,metadata=metadata,states=states)

module_hashes={p:sha((BASE/p).read_bytes()) for p in ['fit.py','rig_logs.py','analyze_current.py','analysis-plan.json']}
summary=dict(plan=PLAN,module_hashes=module_hashes,python=platform.python_version(),numpy=np.__version__,fit_config=asdict(fit.FitConfig()),fits=[],hardware_activity=False)

def residual_diagnostic(rows, report, cfg):
    segments=fit._segments(rows,'magnetic','commanded',cfg)
    p=report['parameters']
    if not p:return {}
    coef=np.array([cfg.gravity_m_s2/p['effective_length_m'],p['angular_damping_per_s'],p['input_gain']/p['effective_length_m']])
    x,y=fit._windows(segments,p['delay_s'],cfg)
    return dict(observed_integrals=y.tolist(),predicted_integrals=(x@coef).tolist(),residuals=(y-x@coef).tolist(),feature_correlation=np.corrcoef(x,rowvar=False).tolist(),window_count=len(y))

def initialization_sensitivity(rows,report,cfg):
    p=report['parameters']
    if not p:return {}
    coef=np.array([cfg.gravity_m_s2/p['effective_length_m'],p['angular_damping_per_s'],p['input_gain']/p['effective_length_m']])
    original=fit._segments(rows,'magnetic','commanded',cfg)
    output={}
    for history in [.04,.08,.12]:
        segments=[]
        for ts,q,a,rr in original:
            r2=[dict(r) for r in rr]
            for i in range(6,len(ts)):
                start=np.searchsorted(ts,ts[i]-history)
                if i-start<6:continue
                r2[i]['omega_rad_s']=float(np.polyfit(ts[start:i+1]-ts[i],q[start:i+1],2)[-2])
                r2[i]['omega_effective_t_s']=float(ts[i])
            segments.append((ts,q,a,r2))
        output[str(history)]=fit._predict(segments,coef,p['delay_s'],cfg)
    return output

def run_pair(train_key,valid_key,cfg,tag):
    tr=data[train_key];va=data[valid_key]
    report=fit.identify_pendulum(tr['rows'],va['rows'],config=cfg,source='magnetic',acceleration_kind='commanded',provenance=dict(analysis_tag=tag,raw_sources_training=tr['metadata']['raw_sources'],raw_sources_validation=va['metadata']['raw_sources'],training_admission=tr['metadata']['admission'],validation_admission=va['metadata']['admission'],module_hashes=module_hashes,hardware_activity=False,calibration_caveat='Reference330 contains an unvalidated hanging-to-upright relationship. Fixed offset sensitivity is not independent calibration. Commanded acceleration and step count do not measure actual motion.')).to_dict()
    report['additional_diagnostics']=dict(training=residual_diagnostic(tr['rows'],report,cfg),validation=residual_diagnostic(va['rows'],report,cfg),heldout_causal_rate_history_sensitivity=initialization_sensitivity(va['rows'],report,cfg),sensitivity_does_not_change_acceptance=True)
    name=f'{tag}-{train_key}-to-{valid_key}.json';dump(name,report)
    small=dict(file=name,training=train_key,validation=valid_key,tag=tag,accepted=report['accepted'],parameters=report['parameters'],training_stats={k:v for k,v in report['training'].items() if k!='delay_profile'},validation_stats=report['validation'],reasons=report['reasons'],rate_history_sensitivity=report['additional_diagnostics']['heldout_causal_rate_history_sensitivity'],recommended_model=report['recommended_model'])
    summary['fits'].append(small)
    print(json.dumps(small,allow_nan=False),flush=True)

cfg=fit.FitConfig()
for val in ['a2','b1','c1','c2','c3']:run_pair('a1',val,cfg,'default')
run_pair('c1','c2',cfg,'secondary-bw8')
fixed=float(PLAN['runs']['a1']['settling']['mean_down_angle'])
for val in ['a2','b1','c1','c2','c3']:run_pair('a1',val,replace(cfg,angle_offset_rad=fixed),'training-hang-offset-sensitivity')
summary['settling_reference_stability']={k:v['metadata']['settling'] for k,v in data.items()}
summary['raw_series_available_locally']=False
summary['camera_use']='No camera signal used: all six camera.json files contain an empty list; before/after images are not calibrated timing or physical motion trajectories.'
dump('summary.json',summary)
print('SAVED '+str(OUT/'summary.json'),flush=True)
