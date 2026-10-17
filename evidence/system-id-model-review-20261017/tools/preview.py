#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.8,<4"]
# ///
"""Plot complete raw, independently clock-mapped recordings before annotating."""
import argparse,json,sys,math
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from cartpole_sdk.identification import workflow,release_review as rr
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);a=p.parse_args()
if a.output.exists() or a.cache.exists():raise FileExistsError('preview/cache already exists')
rdir=a.source.parent;records,ident=workflow.load_records(str(a.source));report=workflow.read_json(rdir/'report.json');base=rr._baseline(records,report);states=[v['state'] for v in records if v.get('type')=='state'];t=np.array([s['unwrapped_us'] for s in states],float);t=(t-t[0])/1e6;host=np.array([s['received_ns'] for s in states],float);q=np.unwrap([s['theta'] for s in states])-base['encoder']['raw_angle_rad'];rows,ch=rr._camera_rows(rdir/'vision.ndjson');vr=workflow.read_json(rdir/'vision-report.json');assert ch==vr['sha256'];frames,dupes=rr._frames(rows,rr._clock(vr['clock_sync']),base['camera'],host,t);valid=[f for f in frames if f['valid'] and f['t_s'] is not None];ct=np.array([f['t_s'] for f in valid]);cq=np.array([f['angle_rad'] for f in valid]);metadata=dict(source_identity=ident,camera_sha256=ch,baseline=base,finish_reason=report['result']['finish_reason'])
np.savez_compressed(a.cache,t=t,q=q,ct=ct,cq=cq,metadata=np.frombuffer(json.dumps(metadata).encode(),dtype=np.uint8))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
count=math.ceil(t[-1]/60);fig,axes=plt.subplots(count,1,figsize=(15,3*count),layout='constrained',squeeze=False)
for i,ax in enumerate(axes.flat):
 ax.plot(t,np.rad2deg(q),label='raw encoder',lw=.7);ax.plot(ct,np.rad2deg(cq),label='raw camera geometry',lw=.7);ax.set_xlim(i*60,min(t[-1],(i+1)*60));ax.grid(alpha=.3);ax.set_ylim(-110,110);ax.set_ylabel('Angle from initial hanging (degrees)');ax.set_xlabel('Seconds from first board STATE');ax.legend()
fig.savefig(a.output,dpi=130);print(json.dumps(dict(source_sha256=ident['sha256'],duration_s=float(t[-1]),camera_frames=len(ct))))
