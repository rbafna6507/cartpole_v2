"""Reproduce the frozen, training-only manual-02 passive audit; no rig access.

Input is the lossless column export identified below. Outputs are compact fit,
source/selection metadata and canonical selected episodes, never a live model.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import passive_fit as fitter

EXPORT_SHA256='47cac6f910a794cbae30a4c3e90a3a0036beacb65f26b7deee7bf7fcd068b37e'
REMOTE='/home/rbafna/cartpole-v2-runs/system-id-20261016/manual-ringdown-train-02'
BOUNDS=[('free_decay_1',64.8,69.4),('free_decay_2',80.,87.4)]


def quantiles(values):
    return dict(zip(['min','p05','median','p95','max'],np.quantile(values,[0,.05,.5,.95,1]).tolist()))


def period_diagnostic(t,q,center):
    # Diagnostic only: a 13-sample (52 ms) moving average suppresses quantization
    # chatter. Same-direction interpolated level crossings give full periods.
    smoothed=np.convolve(q,np.ones(13)/13,mode='valid')-center;tt=t[6:-6]
    periods=[];crossings={}
    for name,direction in [('rising',1),('falling',-1)]:
        ix=np.flatnonzero((smoothed[:-1]*direction<0)&(smoothed[1:]*direction>=0))
        times=[float(tt[i]-smoothed[i]*(tt[i+1]-tt[i])/(smoothed[i+1]-smoothed[i])) for i in ix]
        crossings[name]=times;periods.extend(np.diff(times).tolist())
    return dict(method='13-sample mean; same-direction crossings of training fitted hanging phase; interpolation is diagnostic only',
                crossing_times_s=crossings,full_periods_s=periods,period_s=quantiles(periods) if periods else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();raw=args.input.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPORT_SHA256:raise ValueError('wrong source export hash')
    data=json.loads(gzip.decompress(raw));s=np.asarray(data['states'],float)
    expected=['unwrapped_us','received_ns','tick','theta','angle_hat','omega','x','velocity','acceleration','flags','fault','mode','last_seq']
    if data['state_columns']!=expected:raise ValueError('unexpected state schema')
    if np.any(np.diff(s[:,0])<0):raise ValueError('reversed board timestamp')
    duplicate=np.flatnonzero(np.diff(s[:,0])==0)
    for i in duplicate:
        if not np.array_equal(np.delete(s[i],1),np.delete(s[i+1],1)):raise ValueError('nonidentical board duplicate')
    s=s[np.r_[True,np.diff(s[:,0])>0]]
    if np.any(np.diff(s[:,0])<=0):raise ValueError('nonmonotonic board timestamps')
    if set(s[:,9])!={205.} or np.any(s[:,10:12]!=0):raise ValueError('unexpected enabled/health/mode state')
    t=(s[:,0]-s[0,0])/1e6;q=np.unwrap(s[:,3]);host=s[:,1]/1e9
    vision=[dict(zip(data['vision_columns'],r)) for r in data['vision']]
    runid=data['source_hashes'][next(k for k in data['source_hashes'] if k.startswith('rig-'))]
    if runid!=data['report']['raw_log_sha256']:raise ValueError('raw source hash disagreement')
    episodes=[];camera=[];details=[]
    for name,lo,hi in BOUNDS:
        ix=(t>=lo)&(t<=hi);hs=host[ix]
        episodes.append(dict(run_id=runid,episode_id=name,t_s=t[ix].tolist(),theta_rad=q[ix].tolist()))
        vv=[v for v in vision if hs[0]<=v['t']<=hs[-1]]
        audit=fitter.camera_stationarity([{'vision':v} for v in vv])
        valid=[v for v in vv if v['image_angle_rad'] is not None and v['pivot_px'] is not None and (v['confidence'] or 0)>=.5]
        vt=np.asarray([v['t'] for v in valid]);cq=np.unwrap([math.pi-v['image_angle_rad'] for v in valid])
        cq+=round((math.pi-np.median(cq))/(2*math.pi))*2*math.pi
        if np.any(np.diff(vt)<0):raise ValueError('reversed camera timestamp')
        unique=np.r_[True,np.diff(vt)>0];vt=vt[unique];cq=cq[unique]
        camera.append(dict(run_id=data['source_hashes']['vision.ndjson'],episode_id=name,
                           t_s=(vt-vt[0]+lo).tolist(),theta_rad=cq.tolist()))
        # Interpolation is used only for this cross-sensor diagnostic, never to
        # fill gaps or create fitter observations. The clocks are host proxies.
        mq=np.interp(vt,host,q);error=mq-cq
        design=np.column_stack([np.ones(len(cq)),cq-math.pi]);coef=np.linalg.lstsq(design,mq-math.pi,rcond=None)[0]
        aligned=mq-math.pi-design@coef
        comparison=dict(mapping='q_camera = unwrap(pi - image_angle_rad), integer 2pi shift near pi',
                        synchronization='Camera host timestamp versus interpolated encoder host receipt; exposure/transport delay uncalibrated',
                        raw_magnetic_minus_camera_rad=quantiles(error),correlation=float(np.corrcoef(mq,cq)[0,1]),
                        median_offset_removed_rmse_rad=float(np.sqrt(np.mean((error-np.median(error))**2))),
                        linear_comparison_intercept_rad=float(coef[0]),linear_comparison_scale=float(coef[1]),
                        linear_comparison_rmse_rad=float(np.sqrt(np.mean(aligned**2))),
                        interpretation='Comparison is training-only and provisional; scale, phase, projection and timing are confounded. No encoder correction is applied.')
        details.append(dict(episode=name,requested_relative_board_s=[lo,hi],actual_relative_board_s=[float(t[ix][0]),float(t[ix][-1])],
                            source_tick=[int(s[ix][0,2]),int(s[ix][-1,2])],host_receipt_s=[float(hs[0]),float(hs[-1])],
                            magnetic_samples=int(sum(ix)),max_board_gap_s=float(np.max(np.diff(t[ix]))),
                            camera=audit,camera_length_px_quantiles=quantiles([v['length_px'] for v in valid]),
                            raw_camera_comparison=comparison))
    magnetic={model:fitter.fit_passive(episodes,None,model=model) for model in ('viscous_coulomb','viscous')}
    camfits={model:fitter.fit_passive(camera,None,model=model) for model in ('viscous_coulomb','viscous')}
    center=math.pi+magnetic['viscous']['parameters']['angle_offset_rad']
    for episode,detail in zip(episodes,details):
        detail['period_diagnostic']=period_diagnostic(np.array(episode['t_s']),np.array(episode['theta_rad']),center)
    sourcepins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                [Path(__file__),Path(fitter.__file__),fitter.PLAN_PATH,Path(__file__).with_name('test_passive_fit.py')]}
    summary=dict(status='training_only_no_model_promotion',heldout_read=False,
                 source_export=dict(sha256=EXPORT_SHA256,bytes=len(raw),original_remote=REMOTE+'/columns.json.gz',source_hashes=data['source_hashes']),
                 source_pins=sourcepins,selection=details,magnetic_reports=magnetic,provisional_camera_reports=camfits,
                 recording=dict(unique_states=len(s),camera_rows=len(vision),duplicate_identical_board_snapshots=len(duplicate),
                                first_unwrapped_us=int(s[0,0]),duration_s=float(t[-1]),flags_values=sorted(set(s[:,9].astype(int).tolist())),
                                fault_values=sorted(set(s[:,10].astype(int).tolist())),mode_values=sorted(set(s[:,11].astype(int).tolist())),
                                counted_x_span_m=float(np.ptp(s[:,6])),counted_motion_is_physical_proof=False),
                 operator_cart_restraint='User reports holding cart by hand throughout; no clamp.',
                 selected_model='viscous comparison selected from training only; primary viscous+Coulomb remains rejected',
                 independent_angle_calibration=False,physical_stationarity_certified=False,
                 candidate_parameters=magnetic['viscous']['parameters'],
                 heldout_protocol='New raw recording, no refit/offset adjustment/model or gate selection. Annotate free periods without using residuals. Aim for both release directions and at least 20 weak windows total; driver disabled, cart physically restrained. Preserve camera loss and raw geometry.')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'manual-ringdown-train-02-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    selected=dict(training_episodes=episodes,provisional_camera_episodes=camera)
    packed=json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    (args.output_dir/'manual-ringdown-train-02-selected.json.gz').write_bytes(gzip.compress(packed,mtime=0))
    print(json.dumps(dict(candidate=summary['candidate_parameters'],magnetic_training_pass=magnetic['viscous']['training_checks_pass'],
                          periods=[x['period_diagnostic']['period_s'] for x in details],source_pins=sourcepins),indent=2))


if __name__=='__main__':main()
