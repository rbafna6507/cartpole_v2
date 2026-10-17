import os,json,hashlib
from pathlib import Path
rows=[]
for base in [Path('/home/rbafna/cartpole-v2-live'),Path('/home/rbafna/cartpole_v2')]:
 for root,dirs,files in os.walk(base):
  dirs[:]=[d for d in dirs if d not in ['.venv','.git','node_modules','__pycache__','archive']]
  if 'report.json' not in files:continue
  p=Path(root)/'report.json'
  try:r=json.loads(p.read_text())
  except Exception:continue
  if r.get('procedure')!='passive':continue
  cam=r.get('camera',{});protocol=r.get('collection_protocol',{});raw=[dict(name=f,bytes=(Path(root)/f).stat().st_size) for f in files if f.startswith('rig-') and f.endswith('.jsonl')]
  rows.append(dict(directory=root,report_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),raw_sha256=r.get('raw_log_sha256'),completed=r.get('completed'),failure=r.get('failure'),camera_failure=cam.get('failure'),camera_frames=cam.get('frames'),records_dropped=r.get('records_dropped'),finish_reason=r.get('result',{}).get('finish_reason'),raw_files=raw,mtime_ns=p.stat().st_mtime_ns,dataset_role=protocol.get('dataset_role'),run_label=protocol.get('run_label'),requested_releases=protocol.get('requested_releases'),has_hanging_baseline=bool(r.get('result',{}).get('baseline'))))
print(json.dumps(dict(schema='cartpole-passive-discovery-v1',recordings=rows,unique_raw_hashes=len({r['raw_sha256'] for r in rows})),indent=2))
