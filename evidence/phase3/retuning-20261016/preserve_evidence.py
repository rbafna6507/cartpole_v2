from pathlib import Path
import json,gzip,hashlib,shutil
ROOT=Path('/tmp/cartpole-retune-20261016');OUT=ROOT/'evidence';OUT.mkdir(exist_ok=True)
sources={}
for p in (ROOT/'collected'/'retune-20261015').glob('*/report.json'):sources[p.parent.name]=p
for p in (ROOT/'reports').glob('*/report.json'):sources[p.parent.name]=p
manifest=[]
for name,p in sorted(sources.items()):
 data=p.read_bytes();r=json.loads(data);dest=OUT/'captures'/name;dest.mkdir(parents=True,exist_ok=True)
 (dest/'report.json.gz').write_bytes(gzip.compress(data,mtime=0))
 manifest.append({'run':name,'remote_path':r.get('path'),'report_sha256':hashlib.sha256(data).hexdigest(),'local_report':str((dest/'report.json.gz').relative_to(OUT)),'ok':r.get('ok'),'kind':r.get('kind'),'requested_s':r.get('requested_s'),'full_raw_logs':'Retained beside report on Jetson; source hashes in session-comparison.json for AUTO trials'})
 for extra in ['camera.json','parameters.json']:
  if (p.parent/extra).exists():(dest/(extra+'.gz')).write_bytes(gzip.compress((p.parent/extra).read_bytes(),mtime=0))
for parent in [ROOT/'collected'/'retune-20261016',ROOT/'retune-20261016']:
 for p in parent.rglob('*.json'):
  dest=OUT/'session'/p.relative_to(parent);dest.parent.mkdir(parents=True,exist_ok=True);dest.with_suffix(dest.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
for name in ['README.txt','tuning-summary.json','candidate-bw10.json','aggregate_runs.py','analyze_runs.py','plot_trials.py','native_trial_encoder.py','native_confirm60.py','native_confirm60_lowalloc.py','clear_recovered_encoder.py','plot_best.py','ag5-timing.txt','ag5-rig.jsonl.gz','zero_hold_encoder.py','matched-length-experiment.json','session-comparison.json','trial-timeline.png','trial-timeline.svg','pw3-holds.png','pw3-holds.svg','filtering-comparison.png','filtering-comparison.svg']:
 p=ROOT/name
 if p.exists():shutil.copy2(p,OUT/name)
(OUT/'manifest.json').write_text(json.dumps({'captures':manifest,'description':'Full reports retained locally as gzip; full board JSONL source logs remain on Jetson. No evidence is labeled as a qualified system-identification or encoder calibration model.'},indent=2)+'\n')
profile=json.loads(next((ROOT/'reports').glob('reference330-pw3-bw10-ag2-*/report.json')).read_text());out={'schema_version':1,'source_firmware':profile['final_info']['firmware'],'parameters':{k:v for k,v in profile['parameters'].items() if k!='rail'}};(OUT/'candidate-20261016-bw10.json').write_text(json.dumps(out,indent=2)+'\n')
print('Preserved',len(manifest),'trial reports')
