"""Evaluate explicitly annotated heldout episodes against exact frozen models.

Local/offline only. Does not fit, select intervals, adjust offsets, interpolate
missing samples, access hardware, or promote a simulator model.
"""
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np

FREEZE_SHA256='04befe14b16a54e5288d4326a7ca5d826e8c5a169dc20206dd1108ea160aa744'
STATE_COLUMNS=['unwrapped_us','received_ns','tick','theta','angle_hat','omega','x','velocity','acceleration','flags','fault','mode','last_seq']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_freeze(directory):
    directory=Path(directory);path=directory/'manual-ringdown-train-02-freeze.json'
    if sha(path)!=FREEZE_SHA256:raise ValueError('training freeze manifest changed')
    manifest=json.loads(path.read_text())
    for name,pin in manifest['artifacts'].items():
        if sha(directory/name)!=pin['sha256']:raise ValueError('frozen artifact changed: '+name)
    spec=importlib.util.spec_from_file_location('verified_frozen_passive_fit',directory/'passive_fit.py')
    fitter=importlib.util.module_from_spec(spec);spec.loader.exec_module(fitter)
    summary=json.loads((directory/'manual-ringdown-train-02-summary.json').read_text())
    return fitter,summary,manifest


def score_frozen(episodes,training_report,fitter):
    """Only validation math, with the frozen fitter's exact numerical functions."""
    if not episodes:raise ValueError('need nonempty independent validation episodes')
    run_ids={e['run_id'] for e in episodes}
    if run_ids&set(training_report['provenance']['training_run_ids']):
        raise ValueError('validation recording must be independent')
    report=copy.deepcopy(training_report)
    report['reasons']=[r for r in report['reasons'] if r!='independent heldout validation not provided']
    report['recommended_model']=None;report['statistical_checks_pass']=False
    report['parameters_refitted']=False
    report['provenance']['validation_sha256']=fitter.digest(episodes)
    report['provenance']['validation_run_ids']=sorted(run_ids)
    if not report['parameters']:
        report['validation']={'status':'not scored: no admissible frozen coefficient estimate'}
        return report
    c=np.asarray(report['parameters']['linear_coefficients'],float)
    cfg=report['provenance']['config'];parts=fitter.segments(episodes,cfg)
    x,y=fitter.matrix(parts,cfg,report['model'])
    prediction=fitter.predict(parts,c,cfg)
    prediction['integral_nrmse']=fitter.nrmse(x,y,c);prediction['weak_window_count']=len(y)
    prediction['angle_span_rad']=max((float(np.ptp(q)) for t,q,identity in parts),default=0.)
    report['validation']=prediction
    if prediction['angle_span_rad']<cfg['min_angle_span_rad']:
        report['reasons'].append('insufficient heldout angle excitation')
    if (prediction['prediction_windows']<cfg['min_prediction_windows'] or prediction['prediction_rmse_rad'] is None or
        prediction['prediction_rmse_rad']>cfg['max_prediction_rmse_rad'] or prediction['prediction_p95_rad']>cfg['max_prediction_p95_rad'] or
        prediction['integral_nrmse'] is None or prediction['integral_nrmse']>cfg['max_integral_nrmse']):
        report['reasons'].append('heldout prediction or integral residual exceeds threshold/coverage')
    report['statistical_checks_pass']=not report['reasons']
    return report


def validate_annotations(annotation):
    if annotation.get('selected_before_scoring') is not True:
        raise ValueError('episode annotations must be frozen before scoring')
    for key in ['source_export_sha256','raw_recording_sha256','operator_cart_restraint','selection_method']:
        if not isinstance(annotation.get(key),str) or not annotation[key]:raise ValueError('missing annotation '+key)
    episodes=annotation.get('episodes')
    if not isinstance(episodes,list) or not episodes:raise ValueError('no free episodes annotated')
    last=-math.inf;names=set()
    for ep in episodes:
        lo,hi=ep['board_relative_s']
        if not math.isfinite(lo) or not math.isfinite(hi) or not lo<hi or lo<last:raise ValueError('invalid/overlapping annotations')
        if not ep.get('reason') or not ep.get('episode_id') or ep['episode_id'] in names:raise ValueError('unexplained or repeated episode')
        names.add(ep['episode_id']);last=hi


def canonical_states(states):
    s=np.asarray(states,float)
    if s.ndim!=2 or s.shape[1]!=13 or not np.all(np.isfinite(s)):raise ValueError('invalid state columns')
    if np.any(np.diff(s[:,0])<0):raise ValueError('reversed board timestamps')
    duplicate=np.flatnonzero(np.diff(s[:,0])==0)
    for i in duplicate:
        if not np.array_equal(np.delete(s[i],1),np.delete(s[i+1],1)):raise ValueError('nonidentical duplicate board snapshot')
    s=s[np.r_[True,np.diff(s[:,0])>0]]
    if set(s[:,9])!={205.} or np.any(s[:,10:12]!=0):raise ValueError('recording is not uniformly healthy disabled mode0/flags205')
    return s,len(duplicate)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--annotations',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--freeze-dir',type=Path,default=Path(__file__).resolve().parent.parent)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('output already exists; preserve prior scores')
    fitter,training,manifest=verify_freeze(args.freeze_dir)
    annotation=json.loads(args.annotations.read_text());validate_annotations(annotation)
    raw=args.input.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=annotation['source_export_sha256']:raise ValueError('export/annotation hash mismatch')
    data=json.loads(gzip.decompress(raw))
    if data['state_columns']!=STATE_COLUMNS:raise ValueError('unexpected state column schema')
    raw_hash=data['report']['raw_log_sha256']
    if raw_hash!=annotation['raw_recording_sha256']:raise ValueError('raw recording/annotation hash mismatch')
    if raw_hash not in data['source_hashes'].values():raise ValueError('raw recording/source hash mismatch')
    if set(data['source_hashes'].values())&set(training['source_export']['source_hashes'].values()):raise ValueError('heldout source reused from training')
    s,duplicates=canonical_states(data['states']);t=(s[:,0]-s[0,0])/1e6;q=np.unwrap(s[:,3]);host=s[:,1]/1e9
    vision=[dict(zip(data['vision_columns'],r)) for r in data['vision']]
    episodes=[];camera=[];selection=[]
    for ep in annotation['episodes']:
        lo,hi=ep['board_relative_s'];ix=(t>=lo)&(t<=hi)
        if sum(ix)<8:raise ValueError('annotated episode lacks samples')
        episodes.append(dict(run_id=raw_hash,episode_id=ep['episode_id'],t_s=t[ix].tolist(),theta_rad=q[ix].tolist()))
        hs=host[ix];vv=[v for v in vision if hs[0]<=v['t']<=hs[-1]]
        audit=fitter.camera_stationarity([{'vision':v} for v in vv])
        valid=[v for v in vv if v['image_angle_rad'] is not None and v['pivot_px'] is not None and (v['confidence'] or 0)>=.5]
        camera_status='insufficient raw angle samples'
        if len(valid)>=8:
            vt=np.array([v['t'] for v in valid]);cq=np.unwrap([math.pi-v['image_angle_rad'] for v in valid])
            if np.any(np.diff(vt)<0):raise ValueError('reversed camera timestamps')
            unique=np.r_[True,np.diff(vt)>0];vt=vt[unique];cq=cq[unique]
            cq+=round((math.pi-np.median(cq))/(2*math.pi))*2*math.pi
            camera.append(dict(run_id=data['source_hashes']['vision.ndjson'],episode_id=ep['episode_id'],
                               t_s=(vt-vt[0]+lo).tolist(),theta_rad=cq.tolist()))
            camera_status='raw projection only; no metric/angular calibration or fitted offset adjustment'
        selection.append(dict(annotation=ep,actual_board_relative_s=[float(t[ix][0]),float(t[ix][-1])],
                              source_tick=[int(s[ix][0,2]),int(s[ix][-1,2])],samples=int(sum(ix)),
                              max_board_gap_s=float(np.max(np.diff(t[ix]))),camera=audit,camera_angle_status=camera_status))
    result=dict(status='frozen heldout statistical assessment; physical promotion remains separate',
                selected_model_unchanged='viscous',recommended_model=None,parameters_refitted=False,
                independent_angle_calibration=False,physical_stationarity_certified=False,
                provenance=dict(freeze_manifest_sha256=FREEZE_SHA256,export_sha256=hashlib.sha256(raw).hexdigest(),
                                source_hashes=data['source_hashes'],annotation_sha256=sha(args.annotations),
                                evaluator_sha256=sha(__file__),frozen_source_pins=manifest['artifacts']),
                recording=dict(unique_states=len(s),duplicate_identical_board_snapshots=duplicates,
                               camera_rows=len(vision),duration_s=float(t[-1]),counted_x_span_m=float(np.ptp(s[:,6])),
                               operator_cart_restraint=annotation['operator_cart_restraint']),selection=selection,
                magnetic_reports={m:score_frozen(episodes,r,fitter) for m,r in training['magnetic_reports'].items()},
                provisional_camera_reports={m:score_frozen(camera,r,fitter) for m,r in training['provisional_camera_reports'].items()} if camera else {},
                caveats=['No coefficients, offsets, gates or model choices were selected from heldout.',
                         'Image-plane pivot stability does not certify physical metric stationarity or global angle validity.',
                         'A passed statistical score alone cannot identify masses, actuator input gain/delay or motor force.'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({m:r['validation'] for m,r in result['magnetic_reports'].items()},indent=2))


if __name__=='__main__':main()
