#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Pool saved frozen-check residuals; retain every release and quality flag."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'evidence/system-id-model-review-20261017/tools')]
from cartpole_sdk.identification import workflow,passive
from dynamics import ode_solution,metrics
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--recording',nargs=4,action='append',required=True,metavar=('LABEL','SOURCE','ANNOTATIONS','REPORT'))
p.add_argument('--freeze',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
f=json.loads(a.freeze.read_text());freeze_sha=hashlib.sha256(a.freeze.read_bytes()).hexdigest()
pooled={};recordings=[];seen=set()
for label,source,annotations,report in a.recording:
 r=json.loads(gzip.decompress(Path(report).read_bytes()))
 assert r['freeze_sha256']==freeze_sha and r['accepted'] is False
 identity=r['source_identity'];raw=identity['sha256'];assert raw not in seen and raw not in f['development_source_sha256'];seen.add(raw)
 eps,source_id=workflow.passive_episodes(source,Path(annotations));assert source_id['sha256']==raw
 parts={identity[1]:(t,q) for t,q,identity in passive.segments(eps,dict(passive.DEFAULT_GATES,window_s=.35))}
 models=[]
 for result in r['results']:
  key=result['model']+'/'+result['initializer'];bucket=pooled.setdefault(key,dict(short=[],continuous={str(w):[] for w in f['continuous_initialization_s']},numeric=[],coverage=[]));short=[];releases=[]
  for ep in result['metrics']['episodes']:
   t,q=parts[ep['episode_id']];errors=[]
   for initial in ep['initial_states']:
    i=int(np.searchsorted(t,initial['t_s']));assert t[i]==initial['t_s'];end=int(np.searchsorted(t,t[i]+.5,side='right'))
    pred=ode_solution(t[i:end],[initial['q_rad'],initial['w_rad_s']],result['coefficients'])[0]
    errors.extend(np.arctan2(np.sin(pred[1:]-q[i+1:end]),np.cos(pred[1:]-q[i+1:end])))
   if errors:
    check=metrics(errors)
    for name in ['rms_deg','p95_deg']:assert abs(check[name]-ep['short'][name])<1e-8,(label,key,ep['episode_id'],name)
    assert check['samples']==ep['short']['samples']
   short.extend(errors)
   releases.append(dict(episode_id=ep['episode_id'],short=ep['short'],short_windows=len(ep['initial_states']),short_numeric_gates_pass=bool(ep['short'] and np.deg2rad(ep['short']['rms_deg'])<=.08 and np.deg2rad(ep['short']['p95_deg'])<=.15),short_coverage_gates_pass=len(ep['initial_states'])>=passive.DEFAULT_GATES['min_prediction_windows']))
  check=metrics(short)
  for name in ['rms_deg','p95_deg']:assert abs(check[name]-result['metrics']['short'][name])<1e-8
  bucket['short'].extend(short);bucket['numeric'].append(result['short_numeric_gates_pass']);bucket['coverage'].append(result['short_coverage_gates_pass'])
  histories=[]
  for c in result['metrics']['continuous_after_history']:
   errors=[]
   for ep in c['episodes']:
    delta=np.array(ep['predicted'])[1:]-np.array(ep['observed'])[1:];errors.extend(np.arctan2(np.sin(delta),np.cos(delta)))
    row=next(x for x in releases if x['episode_id']==ep['episode_id']);row.setdefault('continuous',{})[str(c['warmup_s'])]=ep['metrics']
   bucket['continuous'][str(c['warmup_s'])].extend(errors);histories.append(dict(warmup_s=c['warmup_s'],metrics=c['metrics']))
  models.append(dict(model=result['model'],initializer=result['initializer'],short=result['metrics']['short'],short_numeric_gates_pass=result['short_numeric_gates_pass'],short_coverage_gates_pass=result['short_coverage_gates_pass'],continuous_after_history=histories,releases=releases,skipped_segments=result['metrics']['skipped_segments']))
 quality=r['camera_quality']
 recordings.append(dict(label=label,role_in_this_review='independent frozen-model validation',raw_sha256=raw,session=identity['session'],collection_protocol=identity['collection_protocol'],camera_passed=quality['passed'],poses_verified=quality['all_release_poses_verified'],camera_reasons=quality['reasons'],camera_releases=quality['episodes'],models=models,report_sha256=hashlib.sha256(Path(report).read_bytes()).hexdigest()))
combined=[]
for key,b in pooled.items():
 model,initializer=key.split('/',1)
 combined.append(dict(model=model,initializer=initializer,short=metrics(b['short']),all_release_short_numeric_gates_pass=all(b['numeric']),all_release_short_coverage_gates_pass=all(b['coverage']),continuous_after_history=[dict(warmup_s=float(w),metrics=metrics(errors)) for w,errors in b['continuous'].items()]))
out=dict(schema='cartpole-later-passive-frozen-summary-v1',accepted=False,refitted=False,batch9_scored=any(Path(source).parent.name.endswith('-9') for label,source,annotations,report in a.recording),freeze_sha256=freeze_sha,raw_hashes_independent_of_development=True,combined_metrics_basis='Pooled individual sample residuals. RMS and P95 are not averages of recording metrics. Short forecasts reconstructed only from the frozen report initial states and verified against each original short score.',recordings=recordings,combined=combined)
a.output.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n');print(json.dumps(combined,indent=2))
