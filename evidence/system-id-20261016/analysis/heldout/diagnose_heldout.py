"""Supplementary per-episode checks; never changes selection or parameters."""
import argparse
import gzip
import json
import math
from pathlib import Path
import numpy as np
import evaluate_passive as evaluator


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--annotations',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('preserve existing diagnostic output')
    fitter,training,_=evaluator.verify_freeze(Path(__file__).resolve().parent.parent)
    annotation=json.loads(args.annotations.read_text());evaluator.validate_annotations(annotation)
    if evaluator.sha(args.input)!=annotation['source_export_sha256']:raise ValueError('wrong source export')
    data=json.loads(gzip.decompress(args.input.read_bytes()))
    s,_=evaluator.canonical_states(data['states']);t=(s[:,0]-s[0,0])/1e6;q=np.unwrap(s[:,3]);host=s[:,1]/1e9
    vision=[dict(zip(data['vision_columns'],x)) for x in data['vision']];results=[]
    for ep in annotation['episodes']:
        lo,hi=ep['board_relative_s'];ix=(t>=lo)&(t<=hi)
        one=[dict(run_id=annotation['raw_recording_sha256'],episode_id=ep['episode_id'],t_s=t[ix].tolist(),theta_rad=q[ix].tolist())]
        score=evaluator.score_frozen(one,training['magnetic_reports']['viscous'],fitter)
        vv=[v for v in vision if host[ix][0]<=v['t']<=host[ix][-1] and v['image_angle_rad'] is not None and v['pivot_px'] is not None and (v['confidence'] or 0)>=.5]
        vt=np.asarray([v['t'] for v in vv]);cq=np.unwrap([math.pi-v['image_angle_rad'] for v in vv])
        cq+=round((math.pi-np.median(cq))/(2*math.pi))*2*math.pi;mq=np.interp(vt,host,q)
        delta=(mq-training['magnetic_reports']['viscous']['parameters']['angle_offset_rad'])-(cq-training['provisional_camera_reports']['viscous']['parameters']['angle_offset_rad'])
        results.append(dict(episode_id=ep['episode_id'],magnetic_validation=score['validation'],
                            diagnostic_only_not_new_acceptance_rule=True,
                            camera_length_px_quantiles=dict(zip(['min','p05','median','p95','max'],np.quantile([v['length_px'] for v in vv],[0,.05,.5,.95,1]).tolist())),
                            frozen_phase_cross_sensor_comparison=dict(rmse_rad=float(np.sqrt(np.mean(delta**2))),
                                median_rad=float(np.median(delta)),p95_absolute_rad=float(np.quantile(np.abs(delta),.95)),
                                explanation='Only frozen training gravity-phase offsets removed; no heldout offset fit. Camera host time vs encoder receipt interpolation, timing/projection still uncalibrated.')))
    args.output.write_text(json.dumps(dict(episodes=results,selection_unchanged=True,parameters_unchanged=True),indent=2)+'\n')


if __name__=='__main__':main()
