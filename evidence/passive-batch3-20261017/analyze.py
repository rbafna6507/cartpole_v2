#!/usr/bin/env python3
"""Offline batch-3 audit and historical comparison. Never opens hardware or exports.

Run with uv run --locked --extra id --extra plots python THIS_FILE
  --raw-directory EXTRACTED_BATCH3 --historical-directory EXTRACTED_BATCH2
  --output NEW_OUTPUT_DIRECTORY
The batch-2 recovery sidecars must already exist and pass the unchanged loader.
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raw-directory',type=Path,required=True);parser.add_argument('--historical-directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    evidence=Path(__file__).resolve().parent;repo=evidence.parents[1];old=evidence.parent/'passive-batch2-20261017/analysis';out=a.output
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    src=next((a.raw_directory/'passive-training-3').glob('rig-*.jsonl'));ann=evidence/'training-annotations.json'
    vs=next((a.historical_directory/'passive-validation-2').glob('rig-*.jsonl'));va=old/'validation-annotations.json'
    summary=dict(schema='cartpole-passive-batch3-audit-v1',new_validation_incomplete=True,historical_validation_is_development=True,model_exported=False,accepted=False,sources={})
    for name in ('passive-training-3','passive-validation-3'):summary['sources'][name]=summarize_source(a.raw_directory/name)
    assert summary['sources']['passive-training-3']['admitted']
    assert not summary['sources']['passive-validation-3']['admitted']
    review.review_recording(str(src),out/'training-raw-review')
    cr=release_review.review_releases(str(src),ann,out/'training-camera-review')
    report=workflow.fit_passive_logs(str(src),ann,str(vs),va,model='viscous')
    report['historical_comparison_note']='Batch 2 validation has already guided analysis: reused development comparison, not a fresh holdout. Batch 3 failed validation is excluded.'
    workflow.write_json(out/'historical-fit.json',report)
    fit_review.review_fit(out/'historical-fit.json',str(vs),va,out/'historical-fit-review',data_label='Batch 3 fit → batch 2 historical validation (development evidence)')
    compress_report(out/'historical-fit-review')
    oldfit=workflow.read_json(old/'passive-fit.json');cfg=oldfit['provenance']['config'];models={'batch2':oldfit['parameters']['linear_coefficients'],'batch3':report['parameters']['linear_coefficients']}
    comparisons={}
    for name,raw,annotations in [('batch2_training',next((a.historical_directory/'passive-training-2').glob('rig-*.jsonl')),old/'training-annotations.json'),('batch2_validation',vs,va),('batch3_training',src,ann)]:
        episodes,identity=workflow.passive_episodes(str(raw),annotations);parts=passive.segments(episodes,cfg);x,y=passive.matrix(parts,cfg,'viscous');comparisons[name]=dict(source_sha256=identity['sha256'],annotations_sha256=identity['annotations_sha256'],models={})
        for label,c in models.items():
            m=passive.predict(parts,c,cfg);m['integral_nrmse']=passive.nrmse(x,y,c);per=[];traces=[]
            for ep in episodes:
                selected=passive.segments([ep],cfg);ss=[fit_review.forecast_segment(t,q,c,cfg) for t,q,_ in selected];errors=[]
                for seg in ss:
                    trace=seg['continuous'];errors.extend(fit_review._errors(trace['predicted_theta_rad'],trace['recorded_theta_rad']))
                sm=passive.predict(selected,c,cfg);cm=fit_review._metrics(errors);per.append(dict(episode_id=ep['episode_id'],short_forecasts=sm,continuous=cm));traces.append(dict(episode_id=ep['episode_id'],segments=ss,short_forecasts=sm,continuous=cm))
            m['per_episode']=per;comparisons[name]['models'][label]=m
            if name=='batch3_training' and label=='batch2':
                p=out/'old-model-on-new-data';p.mkdir();plot=dict(schema='cartpole-cross-run-diagnostic-v1',fixed_config=cfg,saved_admission={'accepted':False},data_label='Frozen batch 2 model → batch 3 training; diagnostic only',episodes=traces,short_forecasts=m,source_identity=identity,model_coefficients=c,model_source_sha256=sha(old/'passive-fit.json'),model_exported=False)
                fit_review._draw(plot,p);workflow.write_json(p/'report.json',plot);compress_report(p)
    summary.update(camera_passed=cr['passed'],release_poses_verified=cr['all_release_poses_verified'],camera_episodes=cr['episodes'],new_parameters=report['parameters'],old_parameters=oldfit['parameters'],historical_fit_accepted=report['accepted'],historical_fit_reasons=report['reasons'],comparisons=comparisons,annotations_sha256=sha(ann),method_sha256=sha(passive.__file__),analysis_script_sha256=sha(__file__),limitations=['Raw camera geometry is not a video or global angle calibration.','Cart held by hand; pixel stationarity does not independently certify fixed cart.','No failed-source recovery, lowered gate, parameter retuning, firmware change or simulator export.'])
    assert not report['accepted']
    workflow.write_json(out/'summary.json',summary)
    print(json.dumps({'new_parameters':report['parameters'],'historical_fit_reasons':report['reasons'],'camera_passed':cr['passed'],'poses_verified':cr['all_release_poses_verified'],'comparisons':{name:{model:{k:metrics[k] for k in ('prediction_rmse_rad','prediction_p95_rad','integral_nrmse')} for model,metrics in result['models'].items()} for name,result in comparisons.items()}},indent=2))

if __name__=='__main__':main()
