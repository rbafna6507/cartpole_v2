"""Read-only diagnostic extraction from a FAILED recording; not recovery/admission."""
import json,io,hashlib
from pathlib import Path
import numpy as np
from cartpole_sdk.identification import workflow,release_review as rr
root=Path('/home/rbafna/cartpole-v2-live/staging/operator-id-20261017-camera-zero/runs/passive-validation-7');src=next(root.glob('rig-*.jsonl'));report=workflow.read_json(root/'report.json');assert report['completed'] is False
records,identity=workflow._read_records(str(src));assert identity['sha256']==report['raw_log_sha256'];base=next(v['baseline'] for v in records if v.get('type')=='passive_baseline');states=[v['state'] for v in records if v.get('type')=='state'];states=[s for i,s in enumerate(states) if i==0 or s['unwrapped_us']!=states[i-1]['unwrapped_us']]
assert all(s['mode']==0 and s['fault']==0 and s['flags']&15==13 and not s['flags']&304 for s in states)
t=np.array([s['unwrapped_us'] for s in states],float);t=(t-t[0])/1e6;assert np.all(np.diff(t)>0);host=np.array([s['received_ns'] for s in states],float);raw=np.unwrap([s['theta'] for s in states]);q=raw-base['encoder']['raw_angle_rad'];rows,ch=rr._camera_rows(root/'vision.ndjson');vr=workflow.read_json(root/'vision-report.json');assert ch==vr['sha256']==report['camera']['sha256'];frames,dupes=rr._frames(rows,rr._clock(vr['clock_sync']),base['camera'],host,t);good=[f for f in frames if f['valid'] and f['t_s'] is not None]
meta=dict(scope='FAILED recording, diagnostic prefix only. Not recovered, admitted, or independent acceptance evidence.',source_identity=identity,completion_report=report,baseline=base,camera_report=vr,raw_files={p.name:dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in root.iterdir() if p.is_file()},all_recorded_states_healthy_homed_disabled=True,records_tail=records[-6:],last_camera_rows=rows[-3:],commands=[r for r in records if r.get('type')=='command'][-8:])
buf=io.BytesIO();np.savez_compressed(buf,t=t,q=q,raw=raw,ct=np.array([f['t_s'] for f in good]),cq=np.array([f['angle_rad'] for f in good]),metadata=np.frombuffer(json.dumps(meta).encode(),dtype=np.uint8));import sys;sys.stdout.buffer.write(buf.getvalue())
