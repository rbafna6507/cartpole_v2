#!/usr/bin/env python3
"""Read report metadata only; include candidate directories without a report."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
roots=['/home/rbafna/cartpole-v2-live','/home/rbafna/cartpole_v2']
rows=[];incomplete=[];errors=[]
for base in roots:
 if not Path(base).exists():
  errors.append({'path':base,'status':'root missing'});continue
 for root,dirs,files in os.walk(base):
  dirs[:]=[d for d in dirs if d not in ['.venv','.git','node_modules','__pycache__','archive']]
  raw=[{'name':f,'bytes':(Path(root)/f).stat().st_size} for f in files if f.startswith('rig-') and f.endswith('.jsonl')]
  if 'report.json' not in files:
   if raw:incomplete.append({'directory':root,'raw_files':raw,'status':'no completion report; not acquired'})
   continue
  p=Path(root)/'report.json'
  try:r=json.loads(p.read_text())
  except Exception as e:errors.append({'path':str(p),'error':repr(e)});continue
  if r.get('procedure')!='passive':continue
  cam=r.get('camera',{});protocol=r.get('collection_protocol',{});result=r.get('result',{})
  rows.append(dict(directory=root,report_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
   raw_sha256_declared=r.get('raw_log_sha256'),raw_hash_recomputed=False,
   completed=r.get('completed'),stop_confirmed=r.get('stop_confirmed'),failure=r.get('failure'),
   camera_failure=cam.get('failure'),camera_frames=cam.get('frames'),records_dropped=r.get('records_dropped'),
   finish_reason=result.get('finish_reason'),session_id=result.get('info',{}).get('sid'),
   raw_files=raw,mtime_ns=p.stat().st_mtime_ns,dataset_role=protocol.get('dataset_role'),
   run_label=protocol.get('run_label'),requested_releases=protocol.get('requested_releases'),
   has_hanging_baseline=bool(result.get('baseline'))))
print(json.dumps(dict(schema='cartpole-later-passive-discovery-v1',observed_at_utc=datetime.now(timezone.utc).isoformat(),
 roots=roots,recordings=sorted(rows,key=lambda r:r['mtime_ns']),
 incomplete_directories=incomplete,errors=errors,
 unique_raw_hashes=len({r['raw_sha256_declared'] for r in rows})),indent=2))
