#!/usr/bin/env python3
"""Offline batch-5 source audit, fixed-method fit, and cross-model comparison.

Run using uv run --locked --extra id --extra plots python THIS_FILE
  --raw-directory EXTRACTED_BATCH5 --output NEW_OUTPUT_DIRECTORY
Never opens hardware, modifies source recordings, or exports a model.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from cartpole_sdk.identification import workflow, passive, release_review, review, fit_review


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compress_report(directory):
    p=directory/'report.json';raw=p.read_bytes()
    (directory/'report.json.gz').write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
    workflow.write_json(directory/'report-archive.json',dict(original_sha256=hashlib.sha256(raw).hexdigest(),uncompressed_bytes=len(raw),archive_sha256=sha(directory/'report.json.gz')))
    p.unlink()  # Only generated analysis; exact original report is retained losslessly.


def summarize_source(directory):
    raw=next(directory.glob('rig-*.jsonl'));r=workflow.read_json(directory/'report.json');vr=workflow.read_json(directory/'vision-report.json')
    records,identity=workflow._read_records(str(raw))  # Diagnostic read, not admission.
    assert identity['sha256']==r['raw_log_sha256']
    assert sha(directory/'vision.ndjson')==vr['sha256']==r['camera']['sha256']
    states=[v['state'] for v in records if v.get('type')=='state'];t=np.array([s['unwrapped_us'] for s in states],float)/1e6;t-=t[0]
    commands=[v['payload'].split()[1] for v in records if v.get('type')=='command']
    assert set(commands)<=set(('HELLO','STOP','STATUS','PING','INFO','PARAM','RATE'))
    assert all(s['mode']==0 and s['fault']==0 and not s['flags']&16 for s in states)
    try:
        workflow.load_records(str(raw));admitted=True;admission_error=None
    except ValueError as exc:
        admitted=False;admission_error=str(exc)
    baseline=next(v['baseline'] for v in records if v.get('type')=='passive_baseline')
    last_rows=[]
    for line in (directory/'vision.ndjson').open():
        row=json.loads(line);v=row['vision'];last_rows.append(dict(stream_seq=row['stream_seq'],collector_received_ns=row['collector_received_ns'],host_t=row['host_t'],frame_seq=v['seq'],frame_t=v['t'],source_age_s=v['age_since_host_read_s'],stale=v['stale'],worker_error=v.get('worker_error')))
    return dict(source_sha256=identity['sha256'],completed=r['completed'],failure=r.get('failure'),camera_failure=vr.get('failure'),admitted=admitted,admission_error=admission_error,records_dropped=r['records_dropped'],state_count=len(states),duration_s=float(t[-1]),max_snapshot_gap_ms=float(np.max(np.diff(t))*1000),final_state=states[-1],termination=records[-1],stop_confirmed_in_completion_report=r.get('stop_confirmed'),baseline=baseline,camera_frames=vr['frames'],camera_last_rows=last_rows[-6:],camera_average_frames_hz=vr['frames']/((vr['finished_ns']-vr['started_ns'])/1e9),finish_reason=r.get('result',{}).get('finish_reason'),files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(directory.iterdir()) if p.is_file()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();evidence=Path(__file__).resolve().parent;out=a.output
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    sources={role:next((a.raw_directory/f'passive-{role}-5').glob('rig-*.jsonl')) for role in ('training','validation')}
    annotations={role:evidence/f'{role}-annotations.json' for role in sources}
    summary=dict(schema='cartpole-passive-batch5-audit-v1',sources={},model_exported=False)
    camera={}
    for role in sources:
        summary['sources'][role]=summarize_source(sources[role].parent)
        assert summary['sources'][role]['admitted']
        review.review_recording(str(sources[role]),out/(role+'-raw-review'))
        camera[role]=release_review.review_releases(str(sources[role]),annotations[role],out/(role+'-camera-review'))
    fit=workflow.fit_passive_logs(str(sources['training']),annotations['training'],str(sources['validation']),annotations['validation'],model='viscous')
    workflow.write_json(out/'passive-fit.json',fit)
    forecasts=fit_review.review_fit(out/'passive-fit.json',str(sources['validation']),annotations['validation'],out/'fit-review',data_label='Batch 5 training → batch 5 held-out validation')
    compress_report(out/'fit-review')
    previous={'batch2':evidence.parent/'passive-batch2-20261017/analysis/passive-fit.json','batch3':evidence.parent/'passive-batch3-20261017/analysis/historical-fit.json'}
    models={name:workflow.read_json(p)['parameters']['linear_coefficients'] for name,p in previous.items()}
    models['batch5']=fit['parameters']['linear_coefficients'];cfg=fit['provenance']['config'];comparisons={}
    for role in sources:
        episodes,identity=workflow.passive_episodes(str(sources[role]),annotations[role]);parts=passive.segments(episodes,cfg);x,y=passive.matrix(parts,cfg,'viscous')
        comparisons[role]=dict(source_sha256=identity['sha256'],annotations_sha256=identity['annotations_sha256'],models={})
        for name,c in models.items():
            result=passive.predict(parts,c,cfg);result['integral_nrmse']=passive.nrmse(x,y,c);result['per_episode']=[]
            for episode in episodes:
                pp=passive.segments([episode],cfg);result['per_episode'].append(dict(episode_id=episode['episode_id'],**passive.predict(pp,c,cfg)))
            comparisons[role]['models'][name]=result
    assert math.isclose(comparisons['validation']['models']['batch5']['prediction_rmse_rad'],fit['validation']['prediction_rmse_rad'],rel_tol=1e-12)
    summary.update(accepted=fit['accepted'],statistical_checks_pass=fit['statistical_checks_pass'],reasons=fit['reasons'],parameters=fit['parameters'],validation=fit['validation'],per_episode_validation=fit['per_episode_validation'],continuous_validation=[dict(episode_id=e['episode_id'],**e['continuous']) for e in forecasts['episodes']],camera=camera,comparisons=comparisons,method_sha256=sha(passive.__file__),analysis_script_sha256=sha(__file__),previous_model_hashes={name:sha(p) for name,p in previous.items()},frozen_model='viscous; unchanged numerical method and gates',limitations=['Raw camera geometry is not a video or an absolute physical-angle calibration.','Cart hand restraint and exact hand-clear timing are not independently certified.','All six releases retained in both datasets. No intervals or model were revised after scoring.','Frozen older models are evaluated on the same batch5 intervals for a like-for-like comparison.','This script never exports or changes a simulator, controller, firmware or saved reference.'])
    workflow.write_json(out/'summary.json',summary)
    print(json.dumps({'accepted':fit['accepted'],'parameters':fit['parameters'],'validation':fit['validation'],'reasons':fit['reasons'],'camera':{role:dict(passed=r['passed'],all_poses_verified=r['all_release_poses_verified']) for role,r in camera.items()},'comparisons':{role:{name:dict(rmse_deg=math.degrees(m['prediction_rmse_rad']),p95_deg=math.degrees(m['prediction_p95_rad'])) for name,m in data['models'].items()} for role,data in comparisons.items()}},indent=2))

if __name__=='__main__':main()
